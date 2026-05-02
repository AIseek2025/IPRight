from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


@dataclass
class RuntimeHealthReport:
    success: bool
    frontend_ok: bool = False
    backend_ok: bool = False
    login_page_ok: bool = False
    health_checks: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    launch_log: str = ""


class SandboxRuntime:
    """Manages the lifecycle of a generated app in a sandboxed environment."""

    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
        self.processes: list[subprocess.Popen] = []

    async def install_dependencies(self, run_manifest: dict) -> bool:
        install_cmds = run_manifest.get("install_commands", [])
        success = True
        for cmd in install_cmds:
            try:
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    cwd=self.workspace_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    logger.warning(f"Install command failed: {cmd}\n{stderr.decode()}")
                    success = False
            except Exception as e:
                logger.error(f"Install command error: {cmd} - {e}")
                success = False
        return success

    async def start_services(self, run_manifest: dict) -> list[dict]:
        start_cmds = run_manifest.get("start_commands", [])
        services = []
        for cmd in start_cmds:
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=self.workspace_path,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.processes.append(proc)
                services.append({"command": cmd, "pid": proc.pid, "status": "started"})
                logger.info(f"Started: {cmd} (pid={proc.pid})")
            except Exception as e:
                logger.error(f"Failed to start: {cmd} - {e}")
                services.append({"command": cmd, "pid": None, "status": "failed", "error": str(e)})
        return services

    async def run_health_checks(self, run_manifest: dict, timeout: int = 30) -> RuntimeHealthReport:
        health_urls = run_manifest.get("health_checks", [])
        report = RuntimeHealthReport(success=False)

        port_patterns = run_manifest.get("ports", {})
        if not health_urls and port_patterns:
            for name, port in port_patterns.items():
                health_urls.append(f"http://127.0.0.1:{port}/")

        for url in health_urls:
            await self._check_url(url, report, timeout)

        if health_urls:
            report.frontend_ok = any(h.get("frontend") for h in report.health_checks)
            report.backend_ok = any(h.get("backend") for h in report.health_checks)

        report.success = all(h.get("ok") for h in report.health_checks)
        return report

    async def _check_url(self, url: str, report: RuntimeHealthReport, timeout: int) -> None:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            for attempt in range(max(1, timeout // 3)):
                try:
                    resp = await client.get(url)
                    is_ok = resp.status_code < 500
                    is_frontend = "/login" in url or ":3000" in url
                    report.health_checks.append({
                        "url": url,
                        "status_code": resp.status_code,
                        "ok": is_ok,
                        "frontend": is_frontend,
                        "backend": not is_frontend,
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
                return resp.status_code < 500
        except Exception:
            return False

    def stop_all(self) -> None:
        for proc in self.processes:
            try:
                proc.terminate()
            except Exception:
                pass
        self.processes = []

    def get_runtime_status(self) -> dict:
        return {
            "active_processes": len(self.processes),
            "workspace": self.workspace_path,
        }
