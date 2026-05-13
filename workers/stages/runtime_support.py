from __future__ import annotations

import json
import os
import uuid
from collections.abc import Awaitable, Callable

from app.models.db import Screenshot


def _write_json(path: str, data: dict | list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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

    runtime = SandboxRuntime(workspace_root)
    installed = await runtime.install_dependencies(run_manifest)
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
            "frontend_port": run_manifest.get("ports", {}).get("frontend"),
            "backend_port": run_manifest.get("ports", {}).get("backend"),
            "login_page_ok": False,
        }
        error = "Dependency installation/build failed"
    else:
        services = await runtime.start_services(run_manifest)
        await sleep_fn(5)
        frontend_marker_ok = False
        frontend_marker_error = ""
        login_ok = False
        try:
            health_report = await runtime.run_health_checks(run_manifest, timeout=30, services=services)

            if run_manifest.get("ports", {}).get("frontend"):
                port = run_manifest["ports"]["frontend"]
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
            "frontend_port": run_manifest.get("ports", {}).get("frontend"),
            "backend_port": run_manifest.get("ports", {}).get("backend"),
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
) -> tuple[int, int]:
    from app.services.capture import PlaywrightCapture
    from app.services.runtime import SandboxRuntime

    frontend_port = run_manifest.get("ports", {}).get("frontend", 3000) if run_manifest else 3000
    base_url = f"http://127.0.0.1:{frontend_port}"
    demo_accounts = app_manifest.get("demo_accounts", []) if app_manifest else []

    manifest_path = os.path.join(artifacts_root, "screenshot_manifest.json")
    if os.path.exists(manifest_path):
        os.remove(manifest_path)

    runtime = SandboxRuntime(workspace_root)
    await runtime.start_services(run_manifest or {})
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

        if result.success and result.image_path:
            await create_artifact(
                db_factory,
                task_id,
                build_id,
                "screenshot_image",
                os.path.basename(result.image_path),
                result.image_path,
            )

        async with db_factory()() as db:
            screenshot = Screenshot(
                task_id=uuid.UUID(task_id),
                build_id=uuid.UUID(build_id),
                scenario_id=result.scenario_id,
                page_title=result.page_title,
                route=result.route,
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
    return len(results), success_count
