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

FRONTEND_UI_FONT_STACK = "'IPRight CJK', 'Noto Sans SC', 'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei', sans-serif"
FRONTEND_UI_FONT_STACK_CSS = '"IPRight CJK", "Noto Sans SC", "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", sans-serif'
_FRONTEND_FONT_MATCH_TOKENS = (
    "IPRight CJK",
    "Noto Sans SC",
    "Noto Sans CJK SC",
    "PingFang SC",
    "Microsoft YaHei",
    "Helvetica Neue",
    "Arial",
)
_FONT_FAMILY_PROP_RE = re.compile(r"fontFamily\s*:\s*(?P<value>`[^`]*`|'[^'\n]*'|\"[^\"\n]*\")")
_FONT_FAMILY_CSS_RE = re.compile(r"(font-family\s*:\s*)(?P<value>[^;]+)(;)", re.IGNORECASE)


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _requires_llm_frontend_generation(relative_path: str) -> bool:
    if relative_path == "frontend/src/App.tsx":
        return True
    return relative_path.startswith("frontend/src/pages/") and relative_path.endswith((".ts", ".tsx", ".js", ".jsx"))


def _select_module_pages_for_files(requirements: dict, required_files: list[str]) -> list[dict]:
    return [
        page
        for page in requirements.get("module_pages", [])
        if page.get("file_path") in required_files
    ]


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
        "app_type": profile.get("app_type", "admin_web"),
        "preset_key": profile.get("preset_key", ""),
        "module_pages": module_pages,
        "product_name": profile.get("product_name"),
        "short_name": profile.get("short_name"),
        "topic_label": profile.get("topic_label"),
        "scene": profile.get("scene"),
        "industry_scope": profile.get("industry_scope"),
        "software_category": profile.get("software_category"),
        "user_roles": profile.get("user_roles", []),
        "focus_terms": profile.get("focus_terms", []),
        "core_entities": profile.get("core_entities", []),
        "experience_blueprint": profile.get("experience_blueprint", {}),
        "visual_profile": profile.get("visual_profile", {}),
        "project_dna": profile.get("project_dna", {}),
        "differentiation_hint": profile.get("differentiation_hint", ""),
    }


def build_codegen_batches(codegen_requirements: dict) -> list[dict]:
    if not codegen_requirements.get("required_files"):
        return []
    common_requirements = {
        "app_type": codegen_requirements.get("app_type", "admin_web"),
        "preset_key": codegen_requirements.get("preset_key", ""),
        "product_name": codegen_requirements.get("product_name"),
        "short_name": codegen_requirements.get("short_name"),
        "topic_label": codegen_requirements.get("topic_label"),
        "scene": codegen_requirements.get("scene"),
        "industry_scope": codegen_requirements.get("industry_scope"),
        "software_category": codegen_requirements.get("software_category"),
        "user_roles": codegen_requirements.get("user_roles", []),
        "focus_terms": codegen_requirements.get("focus_terms", []),
        "core_entities": codegen_requirements.get("core_entities", []),
        "experience_blueprint": codegen_requirements.get("experience_blueprint", {}),
        "visual_profile": codegen_requirements.get("visual_profile", {}),
        "project_dna": codegen_requirements.get("project_dna", {}),
        "differentiation_hint": codegen_requirements.get("differentiation_hint", ""),
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

    valid_app_types = {"admin_web", "desktop_client"}
    if normalized.get("app_type") not in valid_app_types:
        normalized["app_type"] = plan_seed.get("app_type") or "admin_web"

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


def _should_normalize_font_value(value: str) -> bool:
    lower_value = value.lower()
    if "monospace" in lower_value:
        return False
    return any(token in value for token in _FRONTEND_FONT_MATCH_TOKENS)


def normalize_generated_frontend_files(generated_files: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for relative_path, content in generated_files.items():
        text = str(content)
        if not relative_path.startswith("frontend/") or not relative_path.endswith((".ts", ".tsx", ".js", ".jsx", ".css")):
            normalized[relative_path] = text
            continue

        text = _FONT_FAMILY_PROP_RE.sub(
            lambda match: (
                f"fontFamily: `{FRONTEND_UI_FONT_STACK}`"
                if _should_normalize_font_value(match.group("value"))
                else match.group(0)
            ),
            text,
        )
        text = _FONT_FAMILY_CSS_RE.sub(
            lambda match: (
                f"{match.group(1)}{FRONTEND_UI_FONT_STACK_CSS}{match.group(3)}"
                if _should_normalize_font_value(match.group("value"))
                else match.group(0)
            ),
            text,
        )
        normalized[relative_path] = text
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
        if _requires_llm_frontend_generation(relative_path):
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
    invalid_paths: list[str] = []

    expected_module_imports = [
        f"{_camel_name(module.get('route', module['key']))}Page"
        for module in profile.get("modules", [])
    ]
    expected_module_routes = [
        str(module.get("route", "")).strip()
        for module in profile.get("modules", [])
        if str(module.get("route", "")).strip()
    ]
    requires_route_shell = bool(expected_module_imports or expected_module_routes)

    def _contains_any(content: str, tokens: list[str]) -> bool:
        return any(token in content for token in tokens if token)

    validators = {
        "frontend/src/App.tsx": lambda content: (
            "PlaceholderPage" not in content
            and "模块开发中" not in content
            and _contains_any(content, ["export default function App", "function App(", "const App"])
            and _contains_any(content, ["APP_PROFILE", "generated/appProfile"])
            and (
                not requires_route_shell
                or (
                    _contains_any(content, ["Routes", "Route", "useRoutes"])
                    and (
                        _contains_any(content, expected_module_imports)
                        or _contains_any(content, expected_module_routes)
                    )
                )
            )
        ),
        "frontend/src/pages/Dashboard.tsx": lambda content: (
            "模块开发中" not in content
            and _contains_any(content, ["export default function Dashboard", "function Dashboard(", "const Dashboard"])
            and _contains_any(content, ["APP_PROFILE", "dashboard_metrics", "product_name"])
            and _contains_any(
                content,
                [
                    "系统首页",
                    "指挥仪表盘",
                    "工作台",
                    "概览",
                    "Statistic",
                    "ReactECharts",
                    "Card",
                    "Progress",
                    "Table",
                ],
            )
        ),
        "frontend/src/pages/Login.tsx": lambda content: (
            "模块开发中" not in content
            and _contains_any(content, ["export default function Login", "function Login(", "const Login"])
            and _contains_any(content, ["onLogin", "ipright_demo_auth", "localStorage", "handleSubmit"])
            and _contains_any(content, ["登录", "密码", "用户名"])
        ),
    }

    for relative_path, validator in validators.items():
        content = repaired.get(relative_path)
        if content and validator(str(content)):
            continue
        invalid_paths.append(relative_path)

    return repaired, invalid_paths


def _preview_generated_content(content: str, limit: int = 320) -> str:
    snippet = " ".join((content or "").split())
    if len(snippet) <= limit:
        return snippet
    return snippet[:limit].rstrip() + "..."


def _build_core_validation_hints(profile: dict, invalid_paths: list[str]) -> list[str]:
    hints: list[str] = []
    module_routes = [
        str(module.get("route", "")).strip()
        for module in profile.get("modules", [])
        if str(module.get("route", "")).strip()
    ]
    if "frontend/src/App.tsx" in invalid_paths:
        hints.append(
            "App.tsx 必须导入并使用 ./generated/appProfile 中的 APP_PROFILE，不能只写静态文案。"
        )
        if module_routes:
            hints.append(
                "App.tsx 必须使用 Routes/Route 或 useRoutes 显式挂接这些模块路由: "
                + ", ".join(module_routes)
            )
        hints.append("App.tsx 不得输出 PlaceholderPage、'模块开发中' 或统一后台占位壳层。")
    if "frontend/src/pages/Dashboard.tsx" in invalid_paths:
        hints.append(
            "Dashboard.tsx 必须直接读取 APP_PROFILE.product_name 与 APP_PROFILE.dashboard_metrics，并在页面中展示中文首页/工作台标题。"
        )
    if "frontend/src/pages/Login.tsx" in invalid_paths:
        hints.append(
            "Login.tsx 必须包含中文登录表单，并通过 onLogin、handleSubmit 或 localStorage(ipright_demo_auth) 完成登录态写入。"
        )
    return hints


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
            pending_files = [
                relative_path
                for relative_path in batch["required_files"]
                if not generated_files.get(relative_path)
            ]
            if not pending_files:
                continue

            for attempt_no in range(1, 4):
                current_required_files = list(pending_files)
                batch_requirements = dict(batch["requirements"])
                batch_requirements["required_files"] = current_required_files
                if batch["name"] != "core":
                    batch_requirements["module_pages"] = _select_module_pages_for_files(
                        batch_requirements,
                        current_required_files,
                    )

                codegen_resp = await llm.generate_app_code(prd_content, work_order_content, batch_requirements)
                if not codegen_resp.success or not codegen_resp.structured:
                    batch_reports.append(
                        {
                            "batch": batch["name"],
                            "attempt": attempt_no,
                            "required_files": current_required_files,
                            "generated_paths": [],
                            "fallback_to_template": True,
                            "error": codegen_resp.error or "unknown error",
                        }
                    )
                    continue

                batch_files = codegen_resp.structured.get("files", {})
                if not isinstance(batch_files, dict):
                    batch_reports.append(
                        {
                            "batch": batch["name"],
                            "attempt": attempt_no,
                            "required_files": current_required_files,
                            "generated_paths": [],
                            "fallback_to_template": True,
                            "error": "files payload missing",
                        }
                    )
                    continue

                generated_paths: list[str] = []
                for relative_path, content in batch_files.items():
                    if relative_path in allowed_files and content:
                        generated_files[relative_path] = str(content)
                        generated_paths.append(relative_path)

                pending_files = [
                    relative_path
                    for relative_path in current_required_files
                    if not generated_files.get(relative_path)
                ]
                batch_reports.append(
                    {
                        "batch": batch["name"],
                        "attempt": attempt_no,
                        "required_files": current_required_files,
                        "generated_paths": sorted(generated_paths),
                        "fallback_to_template": bool(pending_files),
                        "error": (
                            f"missing generated files: {', '.join(pending_files[:8])}"
                            if pending_files
                            else None
                        ),
                    }
                )
                if not pending_files:
                    break

    def _build_codegen_report(**extra: object) -> dict:
        report = {
            "model_used": "deepseek-v4-pro" if batches else "template_only",
            "required_files": codegen_requirements["required_files"],
            "generated_file_count": len(generated_files),
            "applied_required_file_count": len(codegen_requirements["required_files"]),
            "generated_paths": sorted(generated_files.keys()),
            "batches": batch_reports,
            "repaired_core_paths": [],
            "template_ui_fallback_used": False,
        }
        report.update(extra)
        return report

    generated_files = hydrate_missing_files_from_template(app_root, generated_files, codegen_requirements["required_files"])
    generated_files, invalid_core_paths = repair_invalid_core_files(app_root, generated_files, profile)
    if invalid_core_paths and batches:
        llm = get_llm_client()
        core_batch = next((batch for batch in batches if batch["name"] == "core"), None)
        if core_batch:
            for attempt_no in range(1, 3):
                invalid_core_previews = {
                    relative_path: _preview_generated_content(generated_files.get(relative_path, ""))
                    for relative_path in invalid_core_paths
                }
                retry_requirements = dict(core_batch["requirements"])
                retry_requirements["required_files"] = list(invalid_core_paths)
                retry_requirements["validation_hints"] = _build_core_validation_hints(profile, invalid_core_paths)
                retry_requirements["invalid_core_previews"] = invalid_core_previews
                codegen_resp = await llm.generate_app_code(prd_content, work_order_content, retry_requirements)
                if not codegen_resp.success or not codegen_resp.structured:
                    batch_reports.append(
                        {
                            "batch": "core_invalid_retry",
                            "attempt": attempt_no,
                            "required_files": list(invalid_core_paths),
                            "generated_paths": [],
                            "fallback_to_template": True,
                            "error": codegen_resp.error or "unknown error",
                        }
                    )
                    continue
                batch_files = codegen_resp.structured.get("files", {})
                if not isinstance(batch_files, dict):
                    batch_reports.append(
                        {
                            "batch": "core_invalid_retry",
                            "attempt": attempt_no,
                            "required_files": list(invalid_core_paths),
                            "generated_paths": [],
                            "fallback_to_template": True,
                            "error": "files payload missing",
                        }
                    )
                    continue
                regenerated_paths: list[str] = []
                for relative_path, content in batch_files.items():
                    if relative_path in invalid_core_paths and content:
                        generated_files[relative_path] = str(content)
                        regenerated_paths.append(relative_path)
                generated_files, invalid_core_paths = repair_invalid_core_files(app_root, generated_files, profile)
                batch_reports.append(
                    {
                        "batch": "core_invalid_retry",
                        "attempt": attempt_no,
                        "required_files": list(retry_requirements["required_files"]),
                        "generated_paths": sorted(regenerated_paths),
                        "fallback_to_template": bool(invalid_core_paths),
                        "error": (
                            "still invalid after retry: " + ", ".join(invalid_core_paths)
                            if invalid_core_paths
                            else None
                        ),
                    }
                )
                if not invalid_core_paths:
                    break
    if invalid_core_paths:
        invalid_core_previews = {
            relative_path: _preview_generated_content(generated_files.get(relative_path, ""))
            for relative_path in invalid_core_paths
        }
        return _build_codegen_report(
            invalid_core_paths=invalid_core_paths,
            invalid_core_previews=invalid_core_previews,
        ), (
            "App code generation failed: missing or invalid LLM-generated core frontend files: "
            + ", ".join(invalid_core_paths)
        )
    generated_files = normalize_generated_frontend_files(generated_files)
    applied, apply_error = apply_generated_code_bundle(app_root, generated_files, codegen_requirements["required_files"])
    if not applied:
        return _build_codegen_report(apply_error=apply_error), f"App code generation failed: {apply_error}"

    return _build_codegen_report(), None
