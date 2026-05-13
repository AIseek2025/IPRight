from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from workers.stages.generated_backend import GENERATED_BACKEND_APP_FILES
from workers.stages.generated_frontend import (
    _camel_name,
    _write_task_specific_app,
)


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def build_seed_copy_ignore(extra_names: set[str] | None = None):
    extra_names = extra_names or set()

    def ignore(_src: str, names: list[str]) -> set[str]:
        ignored = {
            name
            for name in names
            if name in {"node_modules", "dist", ".vite", "__pycache__"} or name.endswith(".pyc")
        }
        ignored.update(name for name in names if name in extra_names)
        return ignored

    return ignore


def prepare_seed_application(app_root: str, profile: dict) -> tuple[str, str]:
    frontend_dst = os.path.join(app_root, "frontend")
    backend_dst = os.path.join(app_root, "backend")
    repo_root = Path(__file__).resolve().parents[2]
    frontend_src = repo_root / "examples" / "demo_app" / "frontend"
    backend_src = repo_root / "examples" / "demo_app" / "backend"

    os.makedirs(app_root, exist_ok=True)
    frontend_ignore = build_seed_copy_ignore()

    def backend_ignore(src: str, names: list[str]) -> set[str]:
        ignored = build_seed_copy_ignore()(src, names)
        if Path(src).resolve() == (backend_src / "app").resolve():
            ignored.update(name for name in names if name in GENERATED_BACKEND_APP_FILES)
        return ignored

    shutil.copytree(frontend_src, frontend_dst, dirs_exist_ok=True, ignore=frontend_ignore)
    shutil.copytree(backend_src, backend_dst, dirs_exist_ok=True, ignore=backend_ignore)
    _write_task_specific_app(frontend_dst, backend_dst, profile)
    return frontend_dst, backend_dst


def _strip_code_fence(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 3:
            return "\n".join(lines[1:-1]).strip()
    return stripped


def build_codegen_requirements(profile: dict) -> dict:
    module_pages: list[dict] = []
    for module in profile.get("modules", []):
        component_name = f"{_camel_name(module.get('route', module['key']))}Page"
        file_path = f"frontend/src/pages/{component_name}.tsx"
        module_pages.append(
            {
                "title": module.get("title"),
                "route": module.get("route"),
                "file_path": file_path,
                "component_name": component_name,
                "description": module.get("description", ""),
                "primary_action": module.get("primary_action", ""),
                "table_headers": list(module.get("table_headers", [])),
                "highlights": list(module.get("highlights", [])),
                "page_variant": module.get("page_variant", "records"),
            }
        )
    core_required_files = [
        "frontend/src/App.tsx",
        "frontend/src/pages/Login.tsx",
        "frontend/src/pages/Dashboard.tsx",
    ]
    required_files = [*core_required_files, *[page["file_path"] for page in module_pages]]
    return {
        "core_required_files": core_required_files,
        "required_files": required_files,
        "module_pages": module_pages,
        "product_name": profile.get("product_name"),
        "scene": profile.get("scene"),
        "industry_scope": profile.get("industry_scope"),
        "user_roles": profile.get("user_roles", []),
        "focus_terms": profile.get("focus_terms", []),
        "core_entities": profile.get("core_entities", []),
        "experience_blueprint": profile.get("experience_blueprint", {}),
    }


def build_codegen_batches(codegen_requirements: dict) -> list[dict]:
    if not codegen_requirements.get("required_files"):
        return []
    common_requirements = {
        "product_name": codegen_requirements.get("product_name"),
        "scene": codegen_requirements.get("scene"),
        "industry_scope": codegen_requirements.get("industry_scope"),
        "user_roles": codegen_requirements.get("user_roles", []),
    }
    batches = [
        {
            "name": "core",
            "required_files": list(codegen_requirements.get("core_required_files", [])),
            "requirements": {
                **common_requirements,
                "required_files": list(codegen_requirements.get("core_required_files", [])),
                "module_pages": list(codegen_requirements.get("module_pages", [])),
            },
        }
    ]
    for module_page in codegen_requirements.get("module_pages", []):
        batches.append(
            {
                "name": f"page:{module_page.get('component_name', module_page.get('title', 'page'))}",
                "required_files": [module_page["file_path"]],
                "requirements": {
                    **common_requirements,
                    "required_files": [module_page["file_path"]],
                    "module_pages": [module_page],
                },
            }
        )
    return batches


def normalize_prd_summary_with_plan_seed(prd_summary: dict, plan_seed: dict) -> dict:
    normalized = dict(prd_summary or {})
    generic_modules = {"首页概览", "数据管理", "流程管理", "报表中心", "系统设置", "首页", "概览仪表盘"}
    current_modules = [str(item).strip() for item in normalized.get("core_modules") or [] if str(item).strip()]
    current_routes = [str(item).strip() for item in normalized.get("required_pages") or [] if str(item).strip()]
    current_roles = [str(item).strip() for item in normalized.get("user_roles") or [] if str(item).strip()]

    if not normalized.get("app_type"):
        normalized["app_type"] = "admin_web"

    should_reset_modules = (
        not current_modules
        or sum(item in generic_modules for item in current_modules) >= max(2, len(current_modules) - 1)
    )
    should_reset_routes = not current_routes or "/data-list" in current_routes or "/workflow" in current_routes

    if plan_seed.get("preset_key") == "media" and current_modules:
        expected_modules = set(plan_seed.get("core_modules") or [])
        themed_tokens = ("剧", "演员", "内容", "评论", "排期", "投放", "数据", "审核", "标签", "选角", "播放")
        overlap = sum(item in expected_modules for item in current_modules)
        themed_count = sum(any(token in item for token in themed_tokens) for item in current_modules)
        duplicate_routes = len(set(current_routes)) < len(current_routes) if current_routes else True
        if overlap < max(2, min(3, len(expected_modules) - 1)):
            should_reset_modules = True
        if duplicate_routes or themed_count < max(2, len(current_modules) - 1):
            should_reset_routes = True
        if should_reset_modules:
            should_reset_routes = True

    if should_reset_modules:
        normalized["core_modules"] = list(plan_seed["core_modules"])
    if should_reset_routes:
        normalized["required_pages"] = list(plan_seed["required_pages"])
    if not current_roles or current_roles in (["admin"], ["admin", "operator"]):
        normalized["user_roles"] = list(plan_seed["user_roles"])

    return normalized


def apply_generated_code_bundle(
    app_root: str,
    generated_files: dict,
    required_files: list[str],
) -> tuple[bool, str | None]:
    missing = [path for path in required_files if not generated_files.get(path)]
    if missing:
        return False, f"Missing generated files: {', '.join(missing[:8])}"

    for relative_path in required_files:
        content = _strip_code_fence(str(generated_files.get(relative_path, "")))
        if not content:
            return False, f"Generated file is empty: {relative_path}"
        absolute_path = os.path.join(app_root, relative_path)
        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        _write_text(absolute_path, content)

    return True, None


def hydrate_missing_files_from_template(
    app_root: str,
    generated_files: dict[str, str],
    required_files: list[str],
) -> dict[str, str]:
    hydrated = dict(generated_files)
    for relative_path in required_files:
        if hydrated.get(relative_path):
            continue
        absolute_path = os.path.join(app_root, relative_path)
        if not os.path.exists(absolute_path):
            continue
        try:
            with open(absolute_path, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError:
            continue
        if content.strip():
            hydrated[relative_path] = content
    return hydrated


def repair_invalid_core_files(
    app_root: str,
    generated_files: dict[str, str],
    profile: dict,
) -> tuple[dict[str, str], list[str]]:
    repaired = dict(generated_files)
    repaired_paths: list[str] = []

    expected_module_imports = [
        f"{_camel_name(module.get('route', module['key']))}Page"
        for module in profile.get("modules", [])
    ]
    validators = {
        "frontend/src/App.tsx": lambda content: (
            "PlaceholderPage" not in content
            and "模块开发中" not in content
            and "APP_PROFILE.product_name" in content
            and all(symbol in content for symbol in expected_module_imports)
        ),
        "frontend/src/pages/Dashboard.tsx": lambda content: (
            "系统首页" in content
            and "APP_PROFILE.product_name" in content
            and "APP_PROFILE.dashboard_metrics" in content
        ),
        "frontend/src/pages/Login.tsx": lambda content: "onLogin" in content,
    }

    for relative_path, validator in validators.items():
        content = repaired.get(relative_path)
        if content and validator(str(content)):
            continue
        absolute_path = os.path.join(app_root, relative_path)
        if not os.path.exists(absolute_path):
            continue
        try:
            with open(absolute_path, "r", encoding="utf-8") as f:
                template_content = f.read()
        except OSError:
            continue
        if not template_content.strip():
            continue
        repaired[relative_path] = template_content
        repaired_paths.append(relative_path)

    return repaired, repaired_paths


def count_source_lines(root: str) -> int:
    total = 0
    for ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".json"):
        for path in Path(root).rglob(f"*{ext}"):
            if any(part in {"node_modules", "dist", "__pycache__"} for part in path.parts):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    total += sum(1 for _ in f)
            except OSError:
                continue
    return total


async def generate_task_app_code(
    app_root: str,
    prd_root: str,
    profile: dict,
) -> tuple[dict | None, str | None]:
    from app.services.llm import get_llm_client

    with open(os.path.join(prd_root, "product_prd.md"), "r", encoding="utf-8") as f:
        prd_content = f.read()
    with open(os.path.join(prd_root, "development_work_order.md"), "r", encoding="utf-8") as f:
        work_order_content = f.read()

    codegen_requirements = build_codegen_requirements(profile)
    generated_files: dict[str, str] = {}
    batch_reports = []
    batches = build_codegen_batches(codegen_requirements)
    if batches:
        llm = get_llm_client()
        allowed_files = set(codegen_requirements["required_files"])
        for batch in batches:
            missing_for_batch = [
                relative_path
                for relative_path in batch["required_files"]
                if not generated_files.get(relative_path)
            ]
            if not missing_for_batch:
                continue

            batch_requirements = dict(batch["requirements"])
            batch_requirements["required_files"] = missing_for_batch
            if batch["name"] != "core":
                batch_requirements["module_pages"] = [
                    page
                    for page in batch_requirements.get("module_pages", [])
                    if page.get("file_path") in missing_for_batch
                ]

            codegen_resp = await llm.generate_app_code(prd_content, work_order_content, batch_requirements)
            if not codegen_resp.success or not codegen_resp.structured:
                if batch["name"] == "core":
                    return None, f"App code generation failed: batch {batch['name']}: {codegen_resp.error or 'unknown error'}"
                batch_reports.append(
                    {
                        "batch": batch["name"],
                        "required_files": list(missing_for_batch),
                        "generated_paths": [],
                        "fallback_to_template": True,
                        "error": codegen_resp.error or "unknown error",
                    }
                )
                continue

            batch_files = codegen_resp.structured.get("files", {})
            if not isinstance(batch_files, dict):
                if batch["name"] == "core":
                    return None, f"App code generation failed: batch {batch['name']}: files payload missing"
                batch_reports.append(
                    {
                        "batch": batch["name"],
                        "required_files": list(missing_for_batch),
                        "generated_paths": [],
                        "fallback_to_template": True,
                        "error": "files payload missing",
                    }
                )
                continue

            missing_after_generation = [
                relative_path for relative_path in missing_for_batch if not batch_files.get(relative_path)
            ]
            if missing_after_generation:
                if batch["name"] == "core":
                    return None, (
                        f"App code generation failed: batch {batch['name']}: missing generated files: "
                        f"{', '.join(missing_after_generation[:8])}"
                    )
                batch_reports.append(
                    {
                        "batch": batch["name"],
                        "required_files": list(missing_for_batch),
                        "generated_paths": sorted(path for path in batch_files.keys() if path in allowed_files),
                        "fallback_to_template": True,
                        "error": f"missing generated files: {', '.join(missing_after_generation[:8])}",
                    }
                )
                continue

            for relative_path, content in batch_files.items():
                if relative_path in allowed_files and content:
                    generated_files[relative_path] = str(content)
            batch_reports.append(
                {
                    "batch": batch["name"],
                    "required_files": list(missing_for_batch),
                    "generated_paths": sorted(path for path in batch_files.keys() if path in allowed_files),
                    "fallback_to_template": False,
                }
            )

    generated_files = hydrate_missing_files_from_template(app_root, generated_files, codegen_requirements["required_files"])
    generated_files, repaired_core_paths = repair_invalid_core_files(app_root, generated_files, profile)
    applied, apply_error = apply_generated_code_bundle(app_root, generated_files, codegen_requirements["required_files"])
    if not applied:
        return None, f"App code generation failed: {apply_error}"

    return {
        "model_used": "deepseek-v4-pro" if batches else "template_only",
        "required_files": codegen_requirements["required_files"],
        "generated_file_count": len(generated_files),
        "applied_required_file_count": len(codegen_requirements["required_files"]),
        "generated_paths": sorted(generated_files.keys()),
        "batches": batch_reports,
        "repaired_core_paths": repaired_core_paths,
    }, None
