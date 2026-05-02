from __future__ import annotations

import json
import logging
import os
import uuid
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.models.db import Artifact, Build, Task, Screenshot
from app.services.document.manual import SoftwareManualGenerator
from app.services.document.codebook import SourceCodeBookGenerator
from app.services.document.diagrams import generate_system_architecture_diagram
from app.services.validator import ManifestValidator
from workers.orchestrator.runner import StageContext, StageResult, register_stage
from app.core.state_machine import StageName

logger = logging.getLogger(__name__)

validator = ManifestValidator()


def workspace_path(task_id: str) -> str:
    return os.path.join(settings.WORKSPACE_ROOT, "tasks", task_id, "workspace")


def artifacts_dir(task_id: str) -> str:
    p = os.path.join(settings.WORKSPACE_ROOT, "tasks", task_id, "artifacts")
    os.makedirs(p, exist_ok=True)
    return p


def screenshots_dir(task_id: str) -> str:
    p = os.path.join(artifacts_dir(task_id), "screenshots")
    os.makedirs(p, exist_ok=True)
    return p


def exports_dir(task_id: str, build_id: str) -> str:
    p = os.path.join(settings.WORKSPACE_ROOT, "tasks", task_id, "builds", build_id, "exports")
    os.makedirs(p, exist_ok=True)
    return p


def manifests_dir(task_id: str) -> str:
    p = os.path.join(workspace_path(task_id), "manifests")
    os.makedirs(p, exist_ok=True)
    return p


async def _create_artifact(
    db_factory,
    task_id: str,
    build_id: str,
    artifact_type: str,
    artifact_name: str,
    local_path: str | None = None,
    metadata: dict | None = None,
) -> Artifact:
    async with db_factory() as db:
        artifact = Artifact(
            task_id=uuid.UUID(task_id),
            build_id=uuid.UUID(build_id) if build_id else None,
            artifact_type=artifact_type,
            artifact_name=artifact_name,
            local_path=local_path,
            metadata_json=metadata,
        )
        db.add(artifact)
        await db.commit()
        return artifact


def _load_manifest(task_id: str, manifest_name: str) -> dict | None:
    path = os.path.join(manifests_dir(task_id), f"{manifest_name}.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


@register_stage(StageName.PLAN)
async def run_plan_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[plan] Generating PRD for task {ctx.task_id}")

    async with ctx.db_factory() as db:
        task = await db.get(Task, uuid.UUID(ctx.task_id))
        if not task:
            return StageResult(success=False, error="Task not found")

    prd_dir = os.path.join(workspace_path(ctx.task_id), "prd")
    os.makedirs(prd_dir, exist_ok=True)

    # Try real LLM first, fall back to template
    llm_used = "template"
    try:
        from app.services.llm import get_llm_client
        llm = get_llm_client()

        resp = await llm.generate_prd(
            keyword=task.keyword or task.product_name,
            product_name=task.product_name,
            version=task.version,
            industry=task.industry or "",
        )

        if resp.success and resp.structured:
            llm_used = "llm"
            prd_content = resp.structured.get("prd_markdown", "")
            work_order_content = resp.structured.get("work_order_markdown", "")
            prd_summary = resp.structured.get("prd_summary", {})
            logger.info(f"[plan] LLM PRD generated successfully ({len(prd_content)} chars)")

            if not prd_summary.get("app_type"):
                prd_summary["app_type"] = "admin_web"
            if not prd_summary.get("core_modules"):
                prd_summary["core_modules"] = ["首页", "数据管理", "报表统计", "系统设置"]
            if not prd_summary.get("required_pages"):
                prd_summary["required_pages"] = ["/login", "/dashboard", "/data-list", "/settings"]
            if not prd_summary.get("user_roles"):
                prd_summary["user_roles"] = ["admin"]
        else:
            logger.warning(f"[plan] LLM failed, using template: {resp.error}")
            raise ValueError("LLM failed")
    except Exception:
        # Fallback to template
        prd_content = _template_prd(task)
        work_order_content = _template_work_order(task)
        prd_summary = {
            "app_type": "admin_web",
            "user_roles": ["admin"],
            "core_modules": ["首页", "数据管理", "报表统计", "系统设置"],
            "required_pages": ["/login", "/dashboard", "/data-list", "/settings"],
        }

    prd_path = os.path.join(prd_dir, "product_prd.md")
    with open(prd_path, "w", encoding="utf-8") as f:
        f.write(prd_content)

    work_order_path = os.path.join(prd_dir, "development_work_order.md")
    with open(work_order_path, "w", encoding="utf-8") as f:
        f.write(work_order_content)

    summary_path = os.path.join(prd_dir, "product_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(prd_summary, f, ensure_ascii=False, indent=2)

    await _create_artifact(
        ctx.db_factory, ctx.task_id, ctx.build_id,
        "product_prd", "product_prd.md", prd_path,
    )
    await _create_artifact(
        ctx.db_factory, ctx.task_id, ctx.build_id,
        "development_work_order", "development_work_order.md", work_order_path,
    )

    return StageResult(
        success=True,
        artifacts=[],
        metadata={"prd_summary": prd_summary, "llm_used": llm_used},
    )


def _template_prd(task) -> str:
    return f"""# {task.product_name} 产品需求文档

## 产品定位
{task.product_name} 是一款面向 {task.industry or '通用行业'} 的后台管理型 Web 应用系统。

## 技术栈
- 前端: React + Vite + TypeScript + Ant Design
- 后端: FastAPI + Python
- 数据库: PostgreSQL

## 核心功能模块
1. 首页/仪表盘
2. 数据管理
3. 报表统计
4. 系统设置

## 用户角色
- 管理员: 拥有全部权限

## 非功能需求
- 响应式设计，支持主流浏览器
- 提供 RESTful API
"""


def _template_work_order(task) -> str:
    return f"""# {task.product_name} 开发任务书

## 技术栈
- 前端: React + Vite + TypeScript + Ant Design
- 后端: FastAPI
- 数据库: PostgreSQL

## 页面任务
1. LoginPage: /login
2. DashboardPage: /dashboard
3. ListPage: /data-list
4. DetailPage: /data-detail
5. SettingsPage: /settings
"""


@register_stage(StageName.BUILD)
async def run_build_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[build] Generating app and manifests for task {ctx.task_id}")

    async with ctx.db_factory() as db:
        task = await db.get(Task, uuid.UUID(ctx.task_id))
        if not task:
            return StageResult(success=False, error="Task not found")

    mdir = manifests_dir(ctx.task_id)
    product_name = task.product_name
    version = task.version

    app_manifest = {
        "product_name": product_name,
        "version": version,
        "app_type": "admin_web",
        "frontend_framework": "react_vite",
        "backend_framework": "fastapi",
        "entry_routes": ["/login", "/dashboard"],
        "demo_accounts": [
            {"role": "admin", "username": "admin", "password": "admin123"}
        ],
    }

    run_manifest = {
        "install_commands": [
            "cd frontend && npm install",
            "cd backend && pip install -r requirements.txt",
        ],
        "start_commands": [
            "cd frontend && npm run dev -- --host 0.0.0.0 --port 3000",
            "cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000",
        ],
        "ports": {"frontend": 3000, "backend": 8000},
        "health_checks": [
            "http://127.0.0.1:3000/",
            "http://127.0.0.1:8000/health",
        ],
    }

    capture_manifest = {
        "scenarios": [
            {"id": "login-page", "title": "登录页", "route": "/login", "actions": [], "priority": 1},
            {"id": "dashboard", "title": "系统首页", "route": "/dashboard", "actions": ["login_as_admin"], "requires_auth": True, "priority": 2},
            {"id": "data-list", "title": "数据列表页", "route": "/data-list", "actions": ["login_as_admin"], "requires_auth": True, "priority": 3},
            {"id": "settings", "title": "系统设置页", "route": "/settings", "actions": ["login_as_admin"], "requires_auth": True, "priority": 4},
        ],
    }

    code_index_manifest = {
        "include_globs": [
            "frontend/src/**/*.ts",
            "frontend/src/**/*.tsx",
            "backend/app/**/*.py",
        ],
        "exclude_globs": [
            "**/node_modules/**",
            "**/dist/**",
            "**/.next/**",
            "**/*.min.js",
            "**/__pycache__/**",
        ],
        "preferred_order": [
            "frontend/src/main.tsx",
            "frontend/src/App.tsx",
            "frontend/src/pages/*.tsx",
            "backend/app/main.py",
        ],
        "line_density_target": 55,
    }

    manifests = {
        "app_manifest.json": app_manifest,
        "run_manifest.json": run_manifest,
        "capture_manifest.json": capture_manifest,
        "code_index_manifest.json": code_index_manifest,
    }

    for filename, data in manifests.items():
        path = os.path.join(mdir, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    validation = validator.validate_all({
        "app_manifest": app_manifest,
        "run_manifest": run_manifest,
        "capture_manifest": capture_manifest,
        "code_index_manifest": code_index_manifest,
    })

    all_valid = validator.is_all_valid(validation)
    validation_errors = []
    for name, vr in validation.items():
        if not vr.valid:
            validation_errors.extend(vr.errors)

    if not all_valid:
        return StageResult(success=False, error=f"Manifest validation failed: {'; '.join(validation_errors)}")

    for filename in manifests:
        artifact_type = filename.replace(".json", "")
        path = os.path.join(mdir, filename)
        await _create_artifact(
            ctx.db_factory, ctx.task_id, ctx.build_id,
            artifact_type, filename, path,
        )

    return StageResult(
        success=True,
        artifacts=[{"type": "manifests", "name": "all manifests"}],
        metadata={"validation": {k: v.valid for k, v in validation.items()}},
    )


@register_stage(StageName.VERIFY_RUN)
async def run_verify_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[verify_run] Running health checks for task {ctx.task_id}")

    run_manifest = _load_manifest(ctx.task_id, "run_manifest")
    if not run_manifest:
        return StageResult(success=False, error="run_manifest not found")

    wsp = workspace_path(ctx.task_id)

    from app.services.runtime import SandboxRuntime
    runtime = SandboxRuntime(wsp)

    installed = await runtime.install_dependencies(run_manifest)
    if not installed:
        logger.warning(f"[verify_run] Some deps failed to install for task {ctx.task_id}")

    services = await runtime.start_services(run_manifest)
    await asyncio_sleep(5)

    health_report = await runtime.run_health_checks(run_manifest, timeout=30)

    login_ok = False
    if run_manifest.get("ports", {}).get("frontend"):
        port = run_manifest["ports"]["frontend"]
        login_ok = await runtime.check_login_page(f"http://127.0.0.1:{port}")

    runtime.stop_all()

    report_path = os.path.join(artifacts_dir(ctx.task_id), "health_report.json")
    report_data = {
        "success": health_report.success,
        "frontend_ok": health_report.frontend_ok,
        "backend_ok": health_report.backend_ok,
        "login_ok": login_ok,
        "checks": health_report.health_checks,
        "errors": health_report.errors,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    await _create_artifact(
        ctx.db_factory, ctx.task_id, ctx.build_id,
        "health_report", "health_report.json", report_path,
    )

    runtime_status = {
        "running": health_report.success,
        "frontend_port": run_manifest.get("ports", {}).get("frontend"),
        "backend_port": run_manifest.get("ports", {}).get("backend"),
        "login_page_ok": login_ok,
    }
    status_path = os.path.join(artifacts_dir(ctx.task_id), "runtime_status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump(runtime_status, f, ensure_ascii=False, indent=2)

    await _create_artifact(
        ctx.db_factory, ctx.task_id, ctx.build_id,
        "runtime_status", "runtime_status.json", status_path,
    )

    if not health_report.success:
        return StageResult(success=False, error=f"Health check failed: {health_report.errors}")

    return StageResult(success=True, artifacts=[], metadata={"runtime_status": runtime_status})


@register_stage(StageName.CAPTURE)
async def run_capture_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[capture] Capturing screenshots for task {ctx.task_id}")

    capture_manifest = _load_manifest(ctx.task_id, "capture_manifest")
    app_manifest = _load_manifest(ctx.task_id, "app_manifest")
    run_manifest = _load_manifest(ctx.task_id, "run_manifest")

    if not capture_manifest:
        return StageResult(success=False, error="capture_manifest not found")

    frontend_port = run_manifest.get("ports", {}).get("frontend", 3000) if run_manifest else 3000
    base_url = f"http://127.0.0.1:{frontend_port}"
    demo_accounts = app_manifest.get("demo_accounts", []) if app_manifest else []

    output_dir = screenshots_dir(ctx.task_id)

    from app.services.capture import PlaywrightCapture
    capture = PlaywrightCapture(base_url=base_url, output_dir=output_dir, headless=True)
    results = await capture.capture_scenarios(capture_manifest, demo_accounts)

    screenshot_manifest_data = []
    for r in results:
        screenshot_manifest_data.append({
            "scenario_id": r.scenario_id,
            "page_title": r.page_title,
            "route": r.route,
            "image_file": os.path.basename(r.image_path) if r.image_path else "",
            "success": r.success,
            "caption": r.caption,
            "elements": r.elements,
            "error": r.error,
        })

        if r.success and r.image_path:
            await _create_artifact(
                ctx.db_factory, ctx.task_id, ctx.build_id,
                "screenshot_image", os.path.basename(r.image_path), r.image_path,
            )

        async with ctx.db_factory() as db:
            screenshot = Screenshot(
                task_id=uuid.UUID(ctx.task_id),
                build_id=uuid.UUID(ctx.build_id),
                scenario_id=r.scenario_id,
                page_title=r.page_title,
                route=r.route,
                caption=r.caption,
            )
            db.add(screenshot)
            await db.commit()

    manifest_path = os.path.join(artifacts_dir(ctx.task_id), "screenshot_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(screenshot_manifest_data, f, ensure_ascii=False, indent=2)

    await _create_artifact(
        ctx.db_factory, ctx.task_id, ctx.build_id,
        "screenshot_manifest", "screenshot_manifest.json", manifest_path,
    )

    success_count = sum(1 for r in results if r.success)
    return StageResult(
        success=success_count >= 1,
        error=None if success_count >= 1 else "No screenshots captured successfully",
        metadata={"screenshots_total": len(results), "screenshots_ok": success_count},
    )


@register_stage(StageName.COMPOSE_MANUAL)
async def run_compose_manual_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[compose_manual] Generating software manual for task {ctx.task_id}")

    async with ctx.db_factory() as db:
        task = await db.get(Task, uuid.UUID(ctx.task_id))
        if not task:
            return StageResult(success=False, error="Task not found")

    screenshot_manifest_path = os.path.join(artifacts_dir(ctx.task_id), "screenshot_manifest.json")
    screenshots_meta = []
    if os.path.exists(screenshot_manifest_path):
        with open(screenshot_manifest_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            for item in raw:
                image_file = item.get("image_file", "")
                screenshots_meta.append({
                    "page_title": item.get("page_title", ""),
                    "caption": item.get("caption", ""),
                    "image_path": os.path.join(screenshots_dir(ctx.task_id), image_file) if image_file else "",
                    "steps": item.get("steps", []),
                })

    generator = SoftwareManualGenerator(
        product_name=task.product_name,
        version=task.version,
    )
    export_dir = exports_dir(ctx.task_id, ctx.build_id)
    arch_diagram_path = os.path.join(export_dir, "system_architecture.png")
    generate_system_architecture_diagram(arch_diagram_path, task.product_name)
    generator.generate_full(
        prd_summary=None,
        screenshots_meta=screenshots_meta,
        modules=["登录认证", "仪表盘/首页", "用户管理", "设备管理", "报表统计", "告警管理", "系统设置"],
        arch_diagram_path=arch_diagram_path,
    )

    output_path = os.path.join(export_dir, "software_manual.docx")
    generator.save(output_path)

    await _create_artifact(
        ctx.db_factory, ctx.task_id, ctx.build_id,
        "software_manual_docx", "software_manual.docx", output_path,
    )

    return StageResult(success=True, artifacts=[], metadata={"export_path": output_path})


@register_stage(StageName.COMPOSE_CODE_BOOK)
async def run_compose_code_book_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[compose_code_book] Generating source code book for task {ctx.task_id}")

    async with ctx.db_factory() as db:
        task = await db.get(Task, uuid.UUID(ctx.task_id))
        if not task:
            return StageResult(success=False, error="Task not found")

    code_index = _load_manifest(ctx.task_id, "code_index_manifest")
    if not code_index:
        return StageResult(success=False, error="code_index_manifest not found")

    wsp = workspace_path(ctx.task_id)
    generator = SourceCodeBookGenerator(
        product_name=task.product_name,
        version=task.version,
    )

    export_dir = exports_dir(ctx.task_id, ctx.build_id)
    output_path = os.path.join(export_dir, "source_code_book.docx")
    generator.generate(code_index, wsp)
    generator.save(output_path)

    await _create_artifact(
        ctx.db_factory, ctx.task_id, ctx.build_id,
        "source_code_book_docx", "source_code_book.docx", output_path,
    )

    return StageResult(
        success=True,
        artifacts=[],
        metadata={
            "export_path": output_path,
        },
    )


@register_stage(StageName.PUBLISH)
async def run_publish_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[publish] Publishing exports for task {ctx.task_id}")

    async with ctx.db_factory() as db:
        task = await db.get(Task, uuid.UUID(ctx.task_id))
        if not task:
            return StageResult(success=False, error="Task not found")

        from app.models.db import Export

        for export_type, filename in [
            ("manual_docx", "software_manual.docx"),
            ("source_code_docx", "source_code_book.docx"),
        ]:
            export = Export(
                task_id=uuid.UUID(ctx.task_id),
                build_id=uuid.UUID(ctx.build_id),
                export_type=export_type,
                file_name=filename,
                download_url=f"/api/v1/exports/{{export_id}}/download",
                status="ready",
            )
            db.add(export)

        await db.commit()

    return StageResult(success=True, artifacts=[], metadata={"published": True})


import asyncio as _asyncio


async def asyncio_sleep(seconds: float) -> None:
    await _asyncio.sleep(seconds)
