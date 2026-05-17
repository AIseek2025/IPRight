from __future__ import annotations

import copy
import json
import hashlib
import logging
import os
import shutil
import uuid

from sqlalchemy import select

from app.core.config import settings
from app.models.db import Artifact, Task
from app.services.project_profile import (
    build_plan_seed,
    build_task_profile,
)
from app.services.validator import ManifestValidator
from workers.orchestrator.runner import StageContext, StageResult, register_stage
from app.core.state_machine import StageName
from workers.stages.build_support import (
    count_source_lines,
    generate_task_app_code,
    normalize_prd_summary_with_plan_seed,
    prepare_seed_application,
)
from workers.stages.runtime_support import (
    execute_capture_flow,
    verify_runtime_execution,
)
from workers.stages.delivery_support import (
    generate_code_book_delivery,
    generate_manual_delivery,
    load_screenshots_meta,
    publish_task_exports,
)

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


def reset_screenshots_dir(task_id: str) -> str:
    p = screenshots_dir(task_id)
    shutil.rmtree(p, ignore_errors=True)
    os.makedirs(p, exist_ok=True)
    return p


def exports_dir(task_id: str, build_id: str) -> str:
    p = os.path.join(settings.WORKSPACE_ROOT, "tasks", task_id, "builds", build_id, "exports")
    os.makedirs(p, exist_ok=True)
    return p


def _derive_run_ports(task_id: str, build_id: str) -> dict[str, int]:
    digest = hashlib.md5(f"{task_id}:{build_id}".encode("utf-8")).hexdigest()
    slot = int(digest[:8], 16) % 10_000
    frontend_port = 24000 + slot * 2
    return {"frontend": frontend_port, "backend": frontend_port + 1}


def manifests_dir(task_id: str) -> str:
    p = os.path.join(workspace_path(task_id), "manifests")
    os.makedirs(p, exist_ok=True)
    return p


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def _create_artifact(
    db_factory,
    task_id: str,
    build_id: str,
    artifact_type: str,
    artifact_name: str,
    local_path: str | None = None,
    metadata: dict | None = None,
) -> Artifact:
    async with db_factory()() as db:
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


def _write_manifest(task_id: str, manifest_name: str, data: dict) -> None:
    _write_json(os.path.join(manifests_dir(task_id), f"{manifest_name}.json"), data)


def _load_prd_summary(task_id: str) -> dict:
    summary_path = os.path.join(workspace_path(task_id), "prd", "product_summary.json")
    if not os.path.exists(summary_path):
        return {}
    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _merge_manual_llm_content(project_profile: dict, llm_content: dict, screenshots_meta: list[dict]) -> dict:
    merged = copy.deepcopy(project_profile or {})
    if not isinstance(llm_content, dict):
        return merged

    # Merge top-level narrative sections consumed by the manual generator.
    scalar_keys = [
        "development_background",
        "development_purpose",
        "industry_scope",
        "hardware_environment",
        "runtime_hardware_environment",
        "development_os",
        "runtime_platform",
        "support_environment",
        "development_tools",
        "overview_product_intro",
        "overview_version_summary",
        "system_architecture_summary",
        "system_pipeline_summary",
        "development_tech_overview",
        "development_language_frontend",
        "development_language_backend",
        "tech_selection_frontend",
        "tech_selection_backend",
        "tech_selection_data",
        "main_functions",
        "function_elements_summary",
        "business_flow_basic",
        "business_flow_materials",
        "business_flow_module_collaboration",
        "usage_overview",
        "technical_features",
        "technical_feature_detail",
        "data_organization",
    ]
    for key in scalar_keys:
        value = llm_content.get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()

    for key in ("technical_feature_bullets", "typical_scenarios"):
        value = llm_content.get(key)
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            if cleaned:
                merged[key] = cleaned

    role_permissions = llm_content.get("role_permissions")
    if isinstance(role_permissions, dict):
        cleaned_permissions = {
            str(role).strip(): str(desc).strip()
            for role, desc in role_permissions.items()
            if str(role).strip() and str(desc).strip()
        }
        if cleaned_permissions:
            merged["role_permissions"] = cleaned_permissions

    modules = [copy.deepcopy(module) for module in (merged.get("modules") or []) if isinstance(module, dict)]
    module_by_title = {
        str(module.get("title", "")).strip(): module
        for module in modules
        if str(module.get("title", "")).strip()
    }
    for override in llm_content.get("module_overrides", []) or []:
        if not isinstance(override, dict):
            continue
        title = str(override.get("title", "")).strip()
        target = module_by_title.get(title)
        if not target:
            continue
        for field in ("description", "primary_action", "business_value", "variant_instruction"):
            value = override.get(field)
            if isinstance(value, str) and value.strip():
                target[field] = value.strip()
        for field in ("highlights", "steps"):
            value = override.get(field)
            if isinstance(value, list):
                cleaned = [str(item).strip() for item in value if str(item).strip()]
                if cleaned:
                    target[field] = cleaned
    if modules:
        merged["modules"] = modules

    page_overrides = llm_content.get("page_overrides", []) or []
    for override in page_overrides:
        if not isinstance(override, dict):
            continue
        page_title = str(override.get("page_title", "")).strip()
        route = str(override.get("route", "")).strip()
        for screenshot in screenshots_meta:
            if not isinstance(screenshot, dict):
                continue
            title_matches = page_title and screenshot.get("page_title") == page_title
            route_matches = route and screenshot.get("route") == route
            if not title_matches and not route_matches:
                continue
            for field in ("caption", "description", "primary_action", "business_value", "variant_instruction"):
                value = override.get(field)
                if isinstance(value, str) and value.strip():
                    screenshot[field] = value.strip()
            for field in ("highlights", "steps"):
                value = override.get(field)
                if isinstance(value, list):
                    cleaned = [str(item).strip() for item in value if str(item).strip()]
                    if cleaned:
                        screenshot[field] = cleaned

    return merged


@register_stage(StageName.PLAN)
async def run_plan_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[plan] Generating PRD for task {ctx.task_id}")

    async with ctx.db_factory()() as db:
        task = await db.get(Task, uuid.UUID(ctx.task_id))
        if not task:
            return StageResult(success=False, error="Task not found")

    prd_dir = os.path.join(workspace_path(ctx.task_id), "prd")
    os.makedirs(prd_dir, exist_ok=True)

    llm_used = "deepseek-v4-flash"
    prd_content = ""
    work_order_content = ""
    prd_summary = {}
    plan_seed = build_plan_seed(task.keyword or task.product_name, task.product_name, task.industry)

    def _fallback_plan_content(current_task: Task) -> tuple[str, str, dict]:
        kw = current_task.keyword or current_task.product_name
        ver = current_task.version or "V1.0"
        module_titles = list(plan_seed["core_modules"])
        summary = {
            "app_type": plan_seed.get("app_type") or "admin_web",
            "core_modules": module_titles,
            "required_pages": list(plan_seed["required_pages"]),
            "user_roles": list(plan_seed["user_roles"]),
        }
        prd_md = (
            f"# {current_task.product_name}{ver} 产品需求文档\n\n"
            f"## 1. 背景\n围绕“{kw}”构建面向{plan_seed['industry_scope']}的专属业务管理与交付支撑平台。\n\n"
            "## 2. 核心模块\n"
            + "\n".join(f"- {name}" for name in module_titles)
            + "\n\n## 3. 业务对象\n"
            + "\n".join(f"- {name}" for name in plan_seed["core_entities"])
            + "\n\n## 4. 非功能要求\n- 页面稳定可访问\n- 关键操作可留痕\n- 支持文档与材料导出\n"
        )
        work_order_md = (
            f"# {current_task.product_name} 开发工单\n\n"
            "## 阶段拆分\n"
            "1. 生成应用骨架与页面\n"
            "2. 运行健康检查\n"
            "3. 采集截图并生成说明书/源码文档\n"
            "4. 导出交付材料\n"
        )
        return prd_md, work_order_md, summary
    try:
        from app.services.llm import get_llm_client
        llm = get_llm_client()

        resp = await llm.generate_prd(
            keyword=task.keyword or task.product_name,
            product_name=task.product_name,
            version=task.version,
            industry=task.industry or "",
            plan_seed=plan_seed,
        )

        if resp.success and resp.structured:
            prd_content = resp.structured.get("prd_markdown", "")
            work_order_content = resp.structured.get("work_order_markdown", "")
            prd_summary = normalize_prd_summary_with_plan_seed(resp.structured.get("prd_summary", {}), plan_seed)
            logger.info(f"[plan] LLM PRD generated successfully ({len(prd_content)} chars)")
        else:
            logger.warning("[plan] LLM unavailable, fallback to template: %s", resp.error or "unknown error")
            prd_content, work_order_content, prd_summary = _fallback_plan_content(task)
            llm_used = "template_fallback"
    except Exception as exc:
        logger.warning("[plan] LLM exception, fallback to template: %s", exc)
        prd_content, work_order_content, prd_summary = _fallback_plan_content(task)
        llm_used = "template_fallback"

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
@register_stage(StageName.BUILD)
async def run_build_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[build] Generating app and manifests for task {ctx.task_id}")

    async with ctx.db_factory()() as db:
        task = await db.get(Task, uuid.UUID(ctx.task_id))
        if not task:
            return StageResult(success=False, error="Task not found")

    mdir = manifests_dir(ctx.task_id)
    prd_root = os.path.join(workspace_path(ctx.task_id), "prd")
    product_name = task.product_name
    version = task.version
    prd_summary = _load_prd_summary(ctx.task_id)
    profile = build_task_profile(
        keyword=task.keyword or task.product_name,
        product_name=task.product_name,
        version=task.version,
        industry=task.industry,
        prd_summary=prd_summary,
    )

    app_root = os.path.join(workspace_path(ctx.task_id), "app")
    prepare_seed_application(app_root, profile)
    codegen_report_data: dict | None = None
    try:
        codegen_report_data, codegen_error = await generate_task_app_code(app_root, prd_root, profile)
        if codegen_error:
            if codegen_report_data:
                _write_manifest(ctx.task_id, "app_codegen_report", codegen_report_data)
            return StageResult(success=False, error=codegen_error)
    except Exception as exc:
        return StageResult(success=False, error=f"App code generation failed: {exc}")

    profile["source_code_line_estimate"] = count_source_lines(app_root)

    app_manifest = {
        "product_name": product_name,
        "version": version,
        "app_type": profile.get("app_type", "admin_web"),
        "frontend_framework": "react_vite",
        "backend_framework": "fastapi",
        "entry_routes": ["/login", "/dashboard", *[item["route"] for item in profile.get("modules", [])]],
        "demo_accounts": [
            {"role": "admin", "username": "admin", "password": "admin123"}
        ],
        "profile": {
            "scene": profile.get("scene"),
            "software_category": profile.get("software_category"),
            "industry_scope": profile.get("industry_scope"),
        },
    }

    run_ports = _derive_run_ports(ctx.task_id, ctx.build_id)
    run_manifest = {
        "install_commands": [
            "cd app/frontend && npm install && node node_modules/vite/bin/vite.js build",
            "/opt/ipright/backend/.venv/bin/python -m pip install -r app/backend/requirements.txt",
        ],
        "start_commands": [
            f"cd app/frontend && node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port {run_ports['frontend']} --strictPort",
            f"cd app/backend && /opt/ipright/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port {run_ports['backend']}",
        ],
        "ports": run_ports,
        "health_checks": [
            f"http://127.0.0.1:{run_ports['frontend']}/",
            f"http://127.0.0.1:{run_ports['backend']}/health",
        ],
    }

    capture_manifest = {
        "scenarios": profile.get("screenshot_scenarios", []),
    }

    code_index_manifest = {
        "include_globs": [
            "app/frontend/package.json",
            "app/frontend/package-lock.json",
            "app/frontend/index.html",
            "app/frontend/src/main.tsx",
            "app/frontend/src/App.tsx",
            "app/frontend/src/**/*.ts",
            "app/frontend/src/**/*.tsx",
            "app/frontend/src/**/*.css",
            "app/frontend/src/font.css",
            "app/frontend/src/pages/Login.tsx",
            "app/frontend/src/pages/Dashboard.tsx",
            "app/frontend/src/pages/*Page.tsx",
            "app/frontend/tsconfig.json",
            "app/frontend/vite.config.ts",
            "app/backend/requirements.txt",
            "app/backend/tests/**/*.py",
            "app/backend/app/**/*.py",
            "app/backend/app/app_profile.py",
            "app/backend/app/main.py",
            "app/backend/app/routes.py",
            "app/backend/app/models.py",
            "app/backend/app/services.py",
            "manifests/*.json",
        ],
        "exclude_globs": [
            "**/node_modules/**",
            "**/dist/**",
            "**/.next/**",
            "**/*.min.js",
            "**/__pycache__/**",
        ],
        "preferred_order": [
            "app/frontend/package.json",
            "app/frontend/package-lock.json",
            "app/frontend/src/main.tsx",
            "app/frontend/src/App.tsx",
            "app/frontend/src/**/*.ts",
            "app/frontend/src/**/*.tsx",
            "app/frontend/src/pages/Login.tsx",
            "app/frontend/src/pages/Dashboard.tsx",
            "app/frontend/src/pages/*Page.tsx",
            "app/backend/requirements.txt",
            "app/backend/app/**/*.py",
            "app/backend/tests/**/*.py",
            "app/backend/app/app_profile.py",
            "app/backend/app/main.py",
            "manifests/*.json",
        ],
        "line_density_target": 55,
    }

    manifests = {
        "app_manifest.json": app_manifest,
        "run_manifest.json": run_manifest,
        "capture_manifest.json": capture_manifest,
        "code_index_manifest.json": code_index_manifest,
        "project_profile.json": profile,
    }
    if codegen_report_data:
        manifests["app_codegen_report.json"] = codegen_report_data

    for filename, data in manifests.items():
        _write_json(os.path.join(mdir, filename), data)

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
        metadata={"validation": {k: v.valid for k, v in validation.items()}, "codegen_model": "deepseek-v4-pro"},
    )


@register_stage(StageName.VERIFY_RUN)
async def run_verify_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[verify_run] Running health checks for task {ctx.task_id}")

    run_manifest = _load_manifest(ctx.task_id, "run_manifest")
    app_manifest = _load_manifest(ctx.task_id, "app_manifest")
    if not run_manifest:
        return StageResult(success=False, error="run_manifest not found")

    success, error, runtime_status = await verify_runtime_execution(
        task_id=ctx.task_id,
        build_id=ctx.build_id,
        workspace_root=workspace_path(ctx.task_id),
        artifacts_root=artifacts_dir(ctx.task_id),
        run_manifest=run_manifest,
        app_manifest=app_manifest,
        create_artifact=_create_artifact,
        db_factory=ctx.db_factory,
        sleep_fn=asyncio_sleep,
    )
    if not success:
        return StageResult(success=False, error=error)

    return StageResult(success=True, artifacts=[], metadata={"runtime_status": runtime_status})


@register_stage(StageName.CAPTURE)
async def run_capture_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[capture] Capturing screenshots for task {ctx.task_id}")

    capture_manifest = _load_manifest(ctx.task_id, "capture_manifest")
    app_manifest = _load_manifest(ctx.task_id, "app_manifest")
    run_manifest = _load_manifest(ctx.task_id, "run_manifest")

    if not capture_manifest:
        return StageResult(success=False, error="capture_manifest not found")

    output_dir = reset_screenshots_dir(ctx.task_id)
    total_count, success_count = await execute_capture_flow(
        task_id=ctx.task_id,
        build_id=ctx.build_id,
        workspace_root=workspace_path(ctx.task_id),
        screenshots_root=output_dir,
        artifacts_root=artifacts_dir(ctx.task_id),
        capture_manifest=capture_manifest,
        app_manifest=app_manifest,
        run_manifest=run_manifest,
        create_artifact=_create_artifact,
        db_factory=ctx.db_factory,
        sleep_fn=asyncio_sleep,
    )
    return StageResult(
        success=success_count >= 1,
        error=None if success_count >= 1 else "No screenshots captured successfully",
        metadata={"screenshots_total": total_count, "screenshots_ok": success_count},
    )


@register_stage(StageName.COMPOSE_MANUAL)
async def run_compose_manual_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[compose_manual] Generating software manual for task {ctx.task_id}")

    async with ctx.db_factory()() as db:
        task = await db.get(Task, uuid.UUID(ctx.task_id))
        if not task:
            return StageResult(success=False, error="Task not found")

    screenshots_meta = load_screenshots_meta(
        ctx.task_id,
        artifacts_dir,
        screenshots_dir,
        lambda manifest_name: _load_manifest(ctx.task_id, manifest_name),
    )
    project_profile = _load_manifest(ctx.task_id, "project_profile") or {}
    prd_summary = _load_prd_summary(ctx.task_id)
    output_path, application_form_path, screenshot_count, manual_llm_used = await generate_manual_delivery(
        task=task,
        task_id=ctx.task_id,
        build_id=ctx.build_id,
        project_profile=project_profile,
        prd_summary=prd_summary,
        screenshots_meta=screenshots_meta,
        exports_dir_fn=exports_dir,
        create_artifact=_create_artifact,
        merge_manual_llm_content=_merge_manual_llm_content,
        db_factory=ctx.db_factory,
    )

    return StageResult(
        success=True,
        artifacts=[],
        metadata={
            "export_path": output_path,
            "application_form_path": application_form_path,
            "screenshot_count": screenshot_count,
            "llm_used": manual_llm_used,
        },
    )


@register_stage(StageName.COMPOSE_CODE_BOOK)
async def run_compose_code_book_stage(ctx: StageContext) -> StageResult:
    logger.info(f"[compose_code_book] Generating source code book for task {ctx.task_id}")

    async with ctx.db_factory()() as db:
        task = await db.get(Task, uuid.UUID(ctx.task_id))
        if not task:
            return StageResult(success=False, error="Task not found")

    code_index = _load_manifest(ctx.task_id, "code_index_manifest")
    if not code_index:
        return StageResult(success=False, error="code_index_manifest not found")

    output_path = await generate_code_book_delivery(
        task=task,
        task_id=ctx.task_id,
        build_id=ctx.build_id,
        code_index=code_index,
        workspace_root=workspace_path(ctx.task_id),
        exports_dir_fn=exports_dir,
        create_artifact=_create_artifact,
        db_factory=ctx.db_factory,
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

    async with ctx.db_factory()() as db:
        task = await db.get(Task, uuid.UUID(ctx.task_id))
        if not task:
            return StageResult(success=False, error="Task not found")

    await publish_task_exports(ctx.task_id, ctx.build_id, ctx.db_factory)

    return StageResult(success=True, artifacts=[], metadata={"published": True})


import asyncio as _asyncio


async def asyncio_sleep(seconds: float) -> None:
    await _asyncio.sleep(seconds)
