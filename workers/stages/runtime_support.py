from __future__ import annotations

import copy
import json
import os
import re
import socket
import uuid
from collections.abc import Awaitable, Callable

from app.models.db import Screenshot


def _write_json(path: str, data: dict | list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


_RUN_PORT_MIN = 24000
_RUN_PORT_MAX = 43998


def _port_is_available(port: int) -> bool:
    if not isinstance(port, int) or port <= 0:
        return False
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
    except OSError:
        return False
    finally:
        sock.close()
    return True


def _iter_port_candidates(preferred_port: int):
    if preferred_port < _RUN_PORT_MIN or preferred_port > _RUN_PORT_MAX:
        preferred_port = _RUN_PORT_MIN
    yield preferred_port
    for port in range(preferred_port + 1, _RUN_PORT_MAX + 1):
        yield port
    for port in range(_RUN_PORT_MIN, preferred_port):
        yield port


def _find_available_port(preferred_port: int, reserved: set[int] | None = None) -> int:
    blocked = reserved or set()
    for port in _iter_port_candidates(preferred_port):
        if port in blocked:
            continue
        if _port_is_available(port):
            return port
    return preferred_port


def _replace_port_reference(text: str, old_port: int, new_port: int) -> str:
    if not text or old_port == new_port:
        return text
    updated = re.sub(rf"(?<=:){old_port}(?=\b)", str(new_port), text)
    updated = re.sub(rf"(?<=--port ){old_port}(?=\b)", str(new_port), updated)
    return updated


def _rewrite_run_manifest_ports(
    run_manifest: dict,
    *,
    frontend_port: int | None,
    backend_port: int | None,
) -> dict:
    updated = copy.deepcopy(run_manifest or {})
    updated_ports = dict(updated.get("ports") or {})
    old_frontend = updated_ports.get("frontend")
    old_backend = updated_ports.get("backend")

    if isinstance(frontend_port, int):
        updated_ports["frontend"] = frontend_port
    if isinstance(backend_port, int):
        updated_ports["backend"] = backend_port
    updated["ports"] = updated_ports

    start_commands = list(updated.get("start_commands") or [])
    health_checks = list(updated.get("health_checks") or [])
    if isinstance(old_frontend, int) and isinstance(frontend_port, int):
        start_commands = [
            _replace_port_reference(command, old_frontend, frontend_port)
            for command in start_commands
        ]
        health_checks = [
            _replace_port_reference(url, old_frontend, frontend_port)
            for url in health_checks
        ]
    if isinstance(old_backend, int) and isinstance(backend_port, int):
        start_commands = [
            _replace_port_reference(command, old_backend, backend_port)
            for command in start_commands
        ]
        health_checks = [
            _replace_port_reference(url, old_backend, backend_port)
            for url in health_checks
        ]
    updated["start_commands"] = start_commands
    updated["health_checks"] = health_checks
    return updated


def _prepare_runtime_manifest(run_manifest: dict | None) -> dict:
    prepared = copy.deepcopy(run_manifest or {})
    ports = prepared.get("ports") or {}
    frontend_port = ports.get("frontend")
    backend_port = ports.get("backend")

    if isinstance(frontend_port, int) and isinstance(backend_port, int) and backend_port == frontend_port + 1:
        if _port_is_available(frontend_port) and _port_is_available(backend_port):
            return _rewrite_run_manifest_ports(
                prepared,
                frontend_port=frontend_port,
                backend_port=backend_port,
            )
        for candidate_frontend in _iter_port_candidates(frontend_port):
            candidate_backend = candidate_frontend + 1
            if candidate_backend > 65535:
                continue
            if not _port_is_available(candidate_frontend):
                continue
            if not _port_is_available(candidate_backend):
                continue
            return _rewrite_run_manifest_ports(
                prepared,
                frontend_port=candidate_frontend,
                backend_port=candidate_backend,
            )
        return _rewrite_run_manifest_ports(
            prepared,
            frontend_port=frontend_port,
            backend_port=backend_port,
        )

    reserved: set[int] = set()
    next_frontend = frontend_port if isinstance(frontend_port, int) else None
    next_backend = backend_port if isinstance(backend_port, int) else None
    if isinstance(next_frontend, int):
        if not _port_is_available(next_frontend):
            next_frontend = _find_available_port(next_frontend)
        reserved.add(next_frontend)
    if isinstance(next_backend, int):
        if next_backend in reserved or not _port_is_available(next_backend):
            next_backend = _find_available_port(next_backend, reserved=reserved)
    return _rewrite_run_manifest_ports(
        prepared,
        frontend_port=next_frontend,
        backend_port=next_backend,
    )


async def verify_runtime_execution(
    task_id: str,
    build_id: str,
    workspace_root: str,
    artifacts_root: str,
    run_manifest: dict,
    app_manifest: dict | None,
    create_artifact: Callable[..., Awaitable],
    db_factory,
    sleep_fn: Callable[[float], Awaitable[None]],
) -> tuple[bool, str | None, dict]:
    from app.services.runtime import RuntimeHealthReport, SandboxRuntime

    prepared_run_manifest = _prepare_runtime_manifest(run_manifest)
    runtime = SandboxRuntime(workspace_root)
    installed = await runtime.install_dependencies(prepared_run_manifest)
    if not installed:
        health_report = RuntimeHealthReport(
            success=False,
            errors=["Dependency installation/build failed"],
        )
        report_data = {
            "success": False,
            "dependency_install_ok": False,
            "frontend_ok": False,
            "backend_ok": False,
            "login_ok": False,
            "checks": [],
            "errors": health_report.errors,
            "services": [],
            "launch_log": "",
        }
        runtime_status = {
            "running": False,
            "dependency_install_ok": False,
            "frontend_port": prepared_run_manifest.get("ports", {}).get("frontend"),
            "backend_port": prepared_run_manifest.get("ports", {}).get("backend"),
            "login_page_ok": False,
        }
        error = "Dependency installation/build failed"
    else:
        services = await runtime.start_services(prepared_run_manifest)
        await sleep_fn(5)
        frontend_marker_ok = False
        frontend_marker_error = ""
        login_ok = False
        try:
            health_report = await runtime.run_health_checks(prepared_run_manifest, timeout=30, services=services)

            if prepared_run_manifest.get("ports", {}).get("frontend"):
                port = prepared_run_manifest["ports"]["frontend"]
                frontend_url = f"http://127.0.0.1:{port}"
                login_ok = await runtime.check_login_page(frontend_url)
                expected_markers = [
                    app_manifest.get("product_name", "") if app_manifest else "",
                    app_manifest.get("version", "") if app_manifest else "",
                ]
                frontend_marker_ok, frontend_marker_error = await runtime.check_frontend_markers(
                    frontend_url,
                    expected_markers,
                )
                if not frontend_marker_ok:
                    health_report.success = False
                    health_report.frontend_ok = False
                    health_report.errors.append(frontend_marker_error)
        finally:
            runtime.stop_all()

        report_data = {
            "success": health_report.success,
            "dependency_install_ok": True,
            "frontend_ok": health_report.frontend_ok,
            "backend_ok": health_report.backend_ok,
            "login_ok": login_ok,
            "frontend_marker_ok": frontend_marker_ok,
            "checks": health_report.health_checks,
            "errors": health_report.errors,
            "services": services,
            "launch_log": health_report.launch_log,
        }
        runtime_status = {
            "running": health_report.success,
            "dependency_install_ok": True,
            "frontend_port": prepared_run_manifest.get("ports", {}).get("frontend"),
            "backend_port": prepared_run_manifest.get("ports", {}).get("backend"),
            "login_page_ok": login_ok,
            "frontend_marker_ok": frontend_marker_ok,
        }
        error = None if health_report.success else f"Health check failed: {health_report.errors}"

    report_path = os.path.join(artifacts_root, "health_report.json")
    _write_json(report_path, report_data)
    await create_artifact(
        db_factory,
        task_id,
        build_id,
        "health_report",
        "health_report.json",
        report_path,
    )

    status_path = os.path.join(artifacts_root, "runtime_status.json")
    _write_json(status_path, runtime_status)
    await create_artifact(
        db_factory,
        task_id,
        build_id,
        "runtime_status",
        "runtime_status.json",
        status_path,
    )

    return error is None, error, runtime_status


async def execute_capture_flow(
    task_id: str,
    build_id: str,
    workspace_root: str,
    screenshots_root: str,
    artifacts_root: str,
    capture_manifest: dict,
    app_manifest: dict | None,
    run_manifest: dict | None,
    create_artifact: Callable[..., Awaitable],
    db_factory,
    sleep_fn: Callable[[float], Awaitable[None]],
) -> tuple[int, int, list[str]]:
    from app.services.capture import PlaywrightCapture
    from app.services.runtime import SandboxRuntime

    prepared_run_manifest = _prepare_runtime_manifest(run_manifest or {})
    frontend_port = prepared_run_manifest.get("ports", {}).get("frontend", 3000)
    base_url = f"http://127.0.0.1:{frontend_port}"
    demo_accounts = app_manifest.get("demo_accounts", []) if app_manifest else []

    manifest_path = os.path.join(artifacts_root, "screenshot_manifest.json")
    if os.path.exists(manifest_path):
        os.remove(manifest_path)

    runtime = SandboxRuntime(workspace_root)
    await runtime.start_services(prepared_run_manifest)
    await sleep_fn(8)

    capture = PlaywrightCapture(base_url=base_url, output_dir=screenshots_root, headless=True)
    try:
        results = await capture.capture_scenarios(capture_manifest, demo_accounts)
    finally:
        runtime.stop_all()

    screenshot_manifest_data = []
    for result in results:
        screenshot_manifest_data.append(
            {
                "scenario_id": result.scenario_id,
                "page_title": result.page_title,
                "route": result.route,
                "image_file": os.path.basename(result.image_path) if result.image_path else "",
                "success": result.success,
                "caption": result.caption,
                "elements": result.elements,
                "error": result.error,
            }
        )

        image_artifact = None
        if result.success and result.image_path:
            image_artifact = await create_artifact(
                db_factory,
                task_id,
                build_id,
                "screenshot_image",
                os.path.basename(result.image_path),
                result.image_path,
            )

        if image_artifact is not None:
            async with db_factory()() as db:
                screenshot = Screenshot(
                    task_id=uuid.UUID(task_id),
                    build_id=uuid.UUID(build_id),
                    scenario_id=result.scenario_id,
                    page_title=result.page_title,
                    route=result.route,
                    image_artifact_id=image_artifact.id,
                    caption=result.caption,
                )
                db.add(screenshot)
                await db.commit()

    _write_json(manifest_path, screenshot_manifest_data)
    await create_artifact(
        db_factory,
        task_id,
        build_id,
        "screenshot_manifest",
        "screenshot_manifest.json",
        manifest_path,
    )

    success_count = sum(1 for item in results if item.success)
    essential_titles = _collect_missing_essential_titles(capture_manifest, results)
    return len(results), success_count, essential_titles


def _collect_missing_essential_titles(capture_manifest: dict, results: list) -> list[str]:
    results_by_id = {str(item.scenario_id): item for item in results}
    missing_titles: list[str] = []
    for scenario in capture_manifest.get("scenarios", []):
        title = str(scenario.get("title", scenario.get("id", ""))).strip()
        scenario_id = str(scenario.get("id", "")).strip()
        if not title or not scenario_id:
            continue
        if "筛选结果" in title or "-filtered-" in scenario_id or scenario_id.endswith("-filtered"):
            continue
        result = results_by_id.get(scenario_id)
        if result is None or not result.success or not getattr(result, "image_path", ""):
            missing_titles.append(title)
    return missing_titles
