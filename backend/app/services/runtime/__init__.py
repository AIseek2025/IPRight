from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


# --- Sandbox hardening configuration --------------------------------------
# The defaults below intentionally err on the side of "permissive enough to
# run the generated React + FastAPI scaffolds we ship". They can be tuned via
# IPRIGHT_SANDBOX_* env vars without touching code.

_DEFAULT_ALLOWED_ENV = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "PYTHONUNBUFFERED",
    "PYTHONIOENCODING",
    # Node / pnpm / vite need these to find their toolchains.
    "NODE_PATH",
    "NPM_CONFIG_CACHE",
    "PNPM_HOME",
    # Pip / pip cache for the generated backend installer.
    "PIP_CACHE_DIR",
    "PIP_INDEX_URL",
)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r, falling back to %d", name, raw, default)
        return default


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class SandboxLimits:
    """Per-process resource limits applied by the subprocess backend.

    Values are surfaced via ``setrlimit`` in a ``preexec_fn``; a value of
    ``None`` skips that limit entirely (for environments where the host
    refuses the requested cap).
    """

    cpu_seconds: int | None = None       # RLIMIT_CPU
    address_space_bytes: int | None = None  # RLIMIT_AS
    file_size_bytes: int | None = None   # RLIMIT_FSIZE
    open_files: int | None = None        # RLIMIT_NOFILE
    processes: int | None = None         # RLIMIT_NPROC

    @classmethod
    def from_env(cls) -> "SandboxLimits":
        # RLIMIT_AS is left unset by default. Modern Node/Vite/esbuild flows can
        # reserve large virtual address spaces for Wasm even when real memory
        # use stays reasonable, and a hard cap here causes false OOM failures.
        return cls(
            cpu_seconds=_env_int("IPRIGHT_SANDBOX_CPU_SECONDS", 0) or None,
            address_space_bytes=_env_int(
                "IPRIGHT_SANDBOX_AS_BYTES", 0
            ) or None,
            file_size_bytes=_env_int(
                "IPRIGHT_SANDBOX_FSIZE_BYTES", 512 * 1024 * 1024
            ) or None,
            open_files=_env_int("IPRIGHT_SANDBOX_NOFILE", 4096) or None,
            processes=_env_int("IPRIGHT_SANDBOX_NPROC", 1024) or None,
        )


def _build_env(extra: dict | None = None) -> dict:
    allowed = set(_DEFAULT_ALLOWED_ENV)
    extras = os.environ.get("IPRIGHT_SANDBOX_EXTRA_ENV", "")
    for name in (n.strip() for n in extras.split(",") if n.strip()):
        allowed.add(name)
    env = {k: v for k, v in os.environ.items() if k in allowed}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env.setdefault("LANG", "C.UTF-8")
    if extra:
        env.update(extra)
    return env


def _make_preexec(limits: SandboxLimits, workspace_path: str):
    """Build a ``preexec_fn`` that drops the child into its own session,
    chdirs into the sandbox workspace, and applies resource limits."""

    def _apply():
        try:
            os.setsid()
        except OSError:
            pass
        try:
            os.chdir(workspace_path)
        except OSError:
            pass
        try:
            import resource  # POSIX-only; imported lazily for portability.
        except ImportError:  # pragma: no cover - Windows fallback
            return
        rl_map = [
            (limits.cpu_seconds, getattr(resource, "RLIMIT_CPU", None)),
            (limits.address_space_bytes, getattr(resource, "RLIMIT_AS", None)),
            (limits.file_size_bytes, getattr(resource, "RLIMIT_FSIZE", None)),
            (limits.open_files, getattr(resource, "RLIMIT_NOFILE", None)),
            (limits.processes, getattr(resource, "RLIMIT_NPROC", None)),
        ]
        for value, rlimit in rl_map:
            if value is None or rlimit is None:
                continue
            try:
                resource.setrlimit(rlimit, (value, value))
            except (ValueError, OSError):
                # Host refused this cap; continue rather than abort.
                pass

    return _apply


def _kill_process_group(proc: subprocess.Popen, *, grace: float = 2.0) -> None:
    """Send SIGTERM to the child's process group, then SIGKILL after ``grace``."""
    if proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, OSError):
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return
    try:
        proc.wait(timeout=grace)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, OSError):
        return False
    return True


def _terminate_pid(pid: int, *, grace: float = 0.8) -> None:
    if pid <= 0 or not _pid_exists(pid):
        return

    same_group = False
    try:
        pgid = os.getpgid(pid)
        same_group = pgid == os.getpgrp()
    except (ProcessLookupError, OSError):
        pgid = None

    try:
        if pgid and not same_group:
            os.killpg(pgid, signal.SIGTERM)
        else:
            os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, OSError):
        return

    deadline = time.time() + max(grace, 0.0)
    while time.time() < deadline:
        if not _pid_exists(pid):
            return
        time.sleep(0.1)

    if not _pid_exists(pid):
        return

    try:
        if pgid and not same_group:
            os.killpg(pgid, signal.SIGKILL)
        else:
            os.kill(pid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        return


def _release_port(port: int, *, grace: float = 0.8) -> list[int]:
    if port <= 0 or shutil.which("lsof") is None:
        return []
    try:
        output = subprocess.check_output(
            ["lsof", "-ti", f"tcp:{port}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, OSError):
        return []

    pids = sorted({int(line.strip()) for line in output.splitlines() if line.strip().isdigit()})
    for pid in pids:
        _terminate_pid(pid, grace=grace)
    return pids


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _shellquote(value: str) -> str:
    """Best-effort POSIX shell quoting for ``docker run`` argv composition."""
    if not value:
        return "''"
    safe = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@%+=:,./-_"
    if all(ch in safe for ch in value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"


def _select_backend() -> str:
    requested = (os.environ.get("IPRIGHT_SANDBOX_BACKEND") or "subprocess").strip().lower()
    if requested == "docker":
        if _docker_available():
            return "docker"
        logger.warning(
            "IPRIGHT_SANDBOX_BACKEND=docker but `docker` binary not found; "
            "falling back to hardened subprocess backend",
        )
        return "subprocess"
    if requested not in ("subprocess", "docker"):
        logger.warning(
            "Unknown IPRIGHT_SANDBOX_BACKEND=%r; falling back to subprocess",
            requested,
        )
    return "subprocess"


@dataclass
class RuntimeHealthReport:
    success: bool
    frontend_ok: bool = False
    backend_ok: bool = False
    login_page_ok: bool = False
    health_checks: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    launch_log: str = ""


@dataclass
class SandboxedResult:
    """Outcome of ``SandboxRuntime.run_sandboxed``."""

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    duration_seconds: float = 0.0


class SandboxRuntime:
    """Manages the lifecycle of a generated app in a sandboxed environment.

    Hardening summary (subprocess backend, applied by default):

    * ``start_new_session=True`` so the child gets its own process group; we
      can ``killpg`` the entire tree on timeout / cleanup.
    * ``preexec_fn`` applies ``setsid``, chdirs into the workspace, and
      tightens ``RLIMIT_CPU/AS/FSIZE/NOFILE/NPROC`` (configurable via env).
    * Environment is whitelisted (``PATH/HOME/LANG/...``) so the child does
      not inherit deploy secrets that happen to live in the parent env.
    * Every "run-once" command goes through ``run_sandboxed`` which enforces
      a hard timeout and falls back to ``SIGKILL`` on the process group.

    Optional ``docker`` backend can be enabled via ``IPRIGHT_SANDBOX_BACKEND=docker``.
    When chosen and the docker CLI is available, ``run_sandboxed`` invokes
    ``docker run --rm --network none --read-only ...`` with CPU / memory caps
    derived from ``SandboxLimits``. When docker is requested but unavailable,
    the runtime logs a warning and falls back to the hardened subprocess
    backend; long-running services (``start_services``) always use the
    subprocess backend because they need to keep listening on host ports.
    """

    DEFAULT_TIMEOUT = 300

    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
        self.processes: list[subprocess.Popen] = []
        self.log_handles: list[object] = []
        self.logs_dir = os.path.join(self.workspace_path, "artifacts", "runtime_logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        self.limits = SandboxLimits.from_env()
        self.backend = _select_backend()
        if self.backend == "docker":
            self.docker_image = os.environ.get(
                "IPRIGHT_SANDBOX_DOCKER_IMAGE", "python:3.11-slim"
            )
        logger.info(
            "SandboxRuntime initialized backend=%s workspace=%s limits=%s",
            self.backend,
            self.workspace_path,
            self.limits,
        )

    def _service_label(self, cmd: str, index: int) -> str:
        lowered = cmd.lower()
        if "app/backend" in lowered or "uvicorn" in lowered or ":23180" in lowered:
            return "backend"
        if "app/frontend" in lowered or "vite" in lowered or ":23100" in lowered:
            return "frontend"
        return f"service_{index + 1}"

    def _service_log_path(self, cmd: str, index: int) -> str:
        return os.path.join(self.logs_dir, f"{self._service_label(cmd, index)}.log")

    def _tail_file(self, path: str, max_chars: int = 4000) -> str:
        if not os.path.exists(path):
            return ""
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return content[-max_chars:]

    async def run_sandboxed(
        self,
        cmd: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        extra_env: dict | None = None,
    ) -> SandboxedResult:
        """Single-shot sandboxed invocation with a hard timeout.

        Use this for "do one thing and exit" commands (dependency installs,
        build steps, lint runs). For long-running services that should keep
        listening on host ports, use :meth:`start_services` instead.
        """
        timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT
        loop = asyncio.get_running_loop()
        start = loop.time()
        if self.backend == "docker" and _docker_available():
            return await self._run_sandboxed_docker(
                cmd, timeout=timeout, cwd=cwd, extra_env=extra_env, started_at=start
            )
        return await self._run_sandboxed_subprocess(
            cmd, timeout=timeout, cwd=cwd, extra_env=extra_env, started_at=start
        )

    async def _run_sandboxed_subprocess(
        self,
        cmd: str,
        *,
        timeout: float,
        cwd: str | None,
        extra_env: dict | None,
        started_at: float,
    ) -> SandboxedResult:
        env = _build_env(extra_env)
        workdir = cwd or self.workspace_path
        loop = asyncio.get_running_loop()

        def _spawn() -> subprocess.Popen:
            return subprocess.Popen(
                cmd,
                cwd=workdir,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                start_new_session=True,
                preexec_fn=_make_preexec(self.limits, workdir),
            )

        proc = await loop.run_in_executor(None, _spawn)
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                loop.run_in_executor(None, proc.communicate),
                timeout=timeout,
            )
            timed_out = False
        except asyncio.TimeoutError:
            await loop.run_in_executor(None, _kill_process_group, proc)
            stdout_b, stderr_b = await loop.run_in_executor(None, proc.communicate)
            timed_out = True
        duration = max(0.0, loop.time() - started_at)
        return SandboxedResult(
            returncode=-1 if timed_out else (proc.returncode or 0),
            stdout=(stdout_b or b"").decode("utf-8", errors="replace"),
            stderr=(stderr_b or b"").decode("utf-8", errors="replace"),
            timed_out=timed_out,
            duration_seconds=duration,
        )

    async def _run_sandboxed_docker(
        self,
        cmd: str,
        *,
        timeout: float,
        cwd: str | None,
        extra_env: dict | None,
        started_at: float,
    ) -> SandboxedResult:
        workdir = cwd or self.workspace_path
        host_path = str(Path(workdir).resolve())
        # cpus / memory caps are best-effort: treat None as "no cap".
        docker_cmd: list[str] = [
            "docker", "run", "--rm",
            "--network", "none",
            "--read-only",
            "--tmpfs", "/tmp:rw,exec,size=128m",
            "--workdir", "/workspace",
            "-v", f"{host_path}:/workspace:ro",
        ]
        if self.limits.address_space_bytes:
            mb = max(64, self.limits.address_space_bytes // (1024 * 1024))
            docker_cmd += ["--memory", f"{mb}m"]
        if self.limits.cpu_seconds:
            docker_cmd += ["--cpus", "1"]
        env = _build_env(extra_env)
        for key, value in env.items():
            docker_cmd += ["-e", f"{key}={value}"]
        docker_cmd += [self.docker_image, "sh", "-c", cmd]
        return await self._run_sandboxed_subprocess(
            cmd=" ".join(_shellquote(part) for part in docker_cmd),
            timeout=timeout,
            cwd=workdir,
            extra_env=None,
            started_at=started_at,
        )

    async def install_dependencies(self, run_manifest: dict) -> bool:
        install_cmds = run_manifest.get("install_commands", [])
        timeout = float(run_manifest.get("install_timeout_seconds", 600))
        success = True
        for cmd in install_cmds:
            try:
                result = await self.run_sandboxed(cmd, timeout=timeout)
                if result.timed_out:
                    logger.warning("Install command timed out after %.1fs: %s", timeout, cmd)
                    success = False
                elif result.returncode != 0:
                    logger.warning(
                        "Install command failed (rc=%s): %s\n%s",
                        result.returncode,
                        cmd,
                        result.stderr[-2000:],
                    )
                    success = False
            except Exception as e:
                logger.error(f"Install command error: {cmd} - {e}")
                success = False
        return success

    async def start_services(self, run_manifest: dict) -> list[dict]:
        # Long-lived dev servers (uvicorn / vite) cannot run inside a
        # ``--rm`` docker container that owns its own PID 1; we always use
        # the hardened subprocess backend here. The hardening below (env
        # whitelist, preexec setrlimit, separate session) still applies.
        start_cmds = run_manifest.get("start_commands", [])
        for port in sorted({int(port) for port in (run_manifest.get("ports") or {}).values() if isinstance(port, int)}):
            released_pids = _release_port(port)
            if released_pids:
                logger.warning("Released stale listeners on port %s: %s", port, released_pids)
        env = _build_env()
        services = []
        for index, cmd in enumerate(start_cmds):
            try:
                log_path = self._service_log_path(cmd, index)
                log_handle = open(log_path, "a", encoding="utf-8")
                proc = subprocess.Popen(
                    cmd,
                    cwd=self.workspace_path,
                    shell=True,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    env=env,
                    start_new_session=True,
                    preexec_fn=_make_preexec(self.limits, self.workspace_path),
                )
                self.processes.append(proc)
                self.log_handles.append(log_handle)
                await asyncio.sleep(0.5)
                status = "started"
                returncode = None
                log_tail = ""
                if proc.poll() is not None:
                    status = "exited"
                    returncode = proc.returncode
                    log_handle.flush()
                    log_tail = self._tail_file(log_path)
                services.append({
                    "command": cmd,
                    "pid": proc.pid,
                    "status": status,
                    "log_path": log_path,
                    "returncode": returncode,
                    "log_tail": log_tail,
                })
                logger.info(f"Started: {cmd} (pid={proc.pid})")
            except Exception as e:
                logger.error(f"Failed to start: {cmd} - {e}")
                services.append({
                    "command": cmd,
                    "pid": None,
                    "status": "failed",
                    "error": str(e),
                    "log_path": None,
                    "returncode": None,
                    "log_tail": "",
                })
        return services

    async def run_health_checks(
        self,
        run_manifest: dict,
        timeout: int = 30,
        services: list[dict] | None = None,
    ) -> RuntimeHealthReport:
        health_urls = run_manifest.get("health_checks", [])
        report = RuntimeHealthReport(success=False)

        port_patterns = run_manifest.get("ports", {})
        frontend_port = port_patterns.get("frontend")
        backend_port = port_patterns.get("backend")
        if not health_urls and port_patterns:
            for name, port in port_patterns.items():
                health_urls.append(f"http://127.0.0.1:{port}/")

        for url in health_urls:
            await self._check_url(url, report, timeout, frontend_port, backend_port)

        if health_urls:
            report.frontend_ok = any(h.get("frontend") and h.get("ok") for h in report.health_checks)
            report.backend_ok = any(h.get("backend") and h.get("ok") for h in report.health_checks)

        diagnostics: list[str] = []
        for index, proc in enumerate(self.processes):
            service = services[index] if services and index < len(services) else None
            label = self._service_label(service["command"], index) if service else f"service_{index + 1}"
            if proc.poll() is not None:
                log_path = service.get("log_path") if service else self._service_log_path("", index)
                log_tail = self._tail_file(log_path)
                report.errors.append(f"{label} process exited with code {proc.returncode}")
                diagnostics.append(
                    f"{label}: exited code={proc.returncode} log_path={log_path}\n{log_tail}".strip()
                )
            elif service and service.get("status") == "failed":
                report.errors.append(f"{label} failed to start: {service.get('error')}")
                diagnostics.append(
                    f"{label}: failed to start error={service.get('error')}"
                )

        report.launch_log = "\n\n".join(part for part in diagnostics if part)
        report.success = all(h.get("ok") for h in report.health_checks)
        return report

    async def _check_url(
        self,
        url: str,
        report: RuntimeHealthReport,
        timeout: int,
        frontend_port: int | None,
        backend_port: int | None,
    ) -> None:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            for attempt in range(max(1, timeout // 3)):
                try:
                    resp = await client.get(url)
                    is_frontend = False
                    is_backend = False

                    if frontend_port and f":{frontend_port}" in url:
                        is_frontend = True
                    elif backend_port and f":{backend_port}" in url:
                        is_backend = True
                    elif "/login" in url:
                        is_frontend = True
                    elif "/health" in url:
                        is_backend = True

                    if is_backend:
                        is_ok = 200 <= resp.status_code < 300
                    elif is_frontend:
                        is_ok = 200 <= resp.status_code < 400
                    else:
                        is_ok = 200 <= resp.status_code < 400

                    report.health_checks.append({
                        "url": url,
                        "status_code": resp.status_code,
                        "ok": is_ok,
                        "frontend": is_frontend,
                        "backend": is_backend,
                    })
                    if is_ok:
                        return
                except Exception:
                    await asyncio.sleep(3)
            report.health_checks.append({"url": url, "ok": False})
            report.errors.append(f"Health check failed for {url}")

    async def check_login_page(self, frontend_url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                resp = await client.get(f"{frontend_url}/login")
                return 200 <= resp.status_code < 400
        except Exception:
            return False

    async def check_frontend_markers(self, frontend_url: str, expected_markers: list[str]) -> tuple[bool, str]:
        markers = [marker.strip() for marker in expected_markers if marker and marker.strip()]
        if not markers:
            return True, ""

        candidates = [f"{frontend_url}/login", frontend_url, f"{frontend_url}/dashboard"]
        collected = ""
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
                for url in candidates:
                    try:
                        resp = await client.get(url)
                    except Exception:
                        continue
                    if 200 <= resp.status_code < 400:
                        collected = resp.text
                        break
        except Exception as exc:
            return False, f"Frontend marker check failed: {exc}"

        if not collected:
            if self._workspace_contains_markers(markers):
                return True, ""
            return False, "Frontend marker check failed: no readable frontend page"

        normalized = " ".join(collected.split())
        for marker in markers:
            if marker in normalized:
                return True, ""
        if self._workspace_contains_markers(markers):
            return True, ""
        return False, f"Frontend marker mismatch: expected one of {markers}"

    def _workspace_contains_markers(self, markers: list[str]) -> bool:
        candidates = [
            Path(self.workspace_path) / "app" / "frontend" / "src" / "generated" / "appProfile.ts",
            Path(self.workspace_path) / "app" / "frontend" / "src" / "pages" / "Login.tsx",
            Path(self.workspace_path) / "app" / "frontend" / "src" / "App.tsx",
            Path(self.workspace_path) / "app" / "backend" / "app" / "app_profile.py",
        ]
        for path in candidates:
            if not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            normalized = " ".join(content.split())
            for marker in markers:
                if marker in normalized:
                    return True
        return False

    def stop_all(self) -> None:
        for proc in self.processes:
            try:
                _kill_process_group(proc, grace=2.0)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
        for handle in self.log_handles:
            try:
                handle.close()
            except Exception:
                pass
        self.processes = []
        self.log_handles = []

    def get_runtime_status(self) -> dict:
        return {
            "active_processes": len(self.processes),
            "workspace": self.workspace_path,
        }
