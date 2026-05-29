from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from workers.stages.generated_backend import GENERATED_BACKEND_APP_FILES
from workers.stages.generated_frontend import (
    _camel_name,
    _render_dashboard_page,
    _render_frontend_app,
    _render_login_page,
    _render_module_page,
    _write_task_specific_app,
    sync_frontend_dependencies,
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
_CORE_INVALID_RETRY_BATCH_SIZE = 1
_MODULE_INVALID_RETRY_BATCH_SIZE = 1


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _requires_llm_frontend_generation(relative_path: str) -> bool:
    if relative_path == "frontend/src/App.tsx":
        return True
    if relative_path in {
        "frontend/src/services/api.ts",
        "frontend/src/types/constants.ts",
        "frontend/src/types/models.ts",
    }:
        return True
    return relative_path.startswith("frontend/src/pages/") and relative_path.endswith((".ts", ".tsx", ".js", ".jsx"))


def _select_module_pages_for_files(requirements: dict, required_files: list[str]) -> list[dict]:
    return [
        page
        for page in requirements.get("module_pages", [])
        if page.get("file_path") in required_files
    ]


def _chunk_required_files(required_files: list[str], chunk_size: int) -> list[list[str]]:
    if chunk_size <= 0:
        return [list(required_files)]
    return [
        list(required_files[index:index + chunk_size])
        for index in range(0, len(required_files), chunk_size)
    ]


def _build_route_shell_module_pages(module_pages: list[dict]) -> list[dict]:
    return [
        {
            "title": page.get("title"),
            "route": page.get("route"),
            "file_path": page.get("file_path"),
            "component_name": page.get("component_name"),
        }
        for page in module_pages
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
                "filter_placeholder": module.get("filter_placeholder", ""),
                "table_headers": list(module.get("table_headers", [])),
                "rows": list(module.get("rows", []))[:6],
                "highlights": list(module.get("highlights", [])),
                "page_variant": module.get("page_variant", "records"),
            }
        )
    core_required_files = [
        "frontend/src/App.tsx",
        "frontend/src/pages/Login.tsx",
        "frontend/src/pages/Dashboard.tsx",
        "frontend/src/services/api.ts",
        "frontend/src/types/constants.ts",
        "frontend/src/types/models.ts",
    ]
    required_files = [*core_required_files, *[page["file_path"] for page in module_pages]]
    return {
        "core_required_files": core_required_files,
        "required_files": required_files,
        "raw_user_request": profile.get("raw_user_request", {}),
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
    core_required_files = list(codegen_requirements.get("core_required_files", []))
    route_shell_files = [
        "frontend/src/App.tsx",
        "frontend/src/pages/Login.tsx",
        "frontend/src/pages/Dashboard.tsx",
    ]
    primary_core_files = [path for path in route_shell_files if path in core_required_files]
    support_core_files = [path for path in core_required_files if path not in primary_core_files]
    common_requirements = {
        "raw_user_request": codegen_requirements.get("raw_user_request", {}),
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
    batches = []
    route_shell_module_pages = _build_route_shell_module_pages(list(codegen_requirements.get("module_pages", [])))
    for index, relative_path in enumerate(primary_core_files):
        component_name = Path(relative_path).stem
        batches.append(
            {
                "name": "core" if index == 0 else f"core:{component_name}",
                "required_files": [relative_path],
                "requirements": {
                    **common_requirements,
                    "required_files": [relative_path],
                    "module_pages": (
                        route_shell_module_pages
                        if relative_path == "frontend/src/App.tsx"
                        else []
                    ),
                },
            }
        )
    if support_core_files:
        batches.append(
            {
                "name": "support",
                "required_files": support_core_files,
                "requirements": {
                    **common_requirements,
                    "required_files": support_core_files,
                    "module_pages": [],
                },
            }
        )
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
    normalized["raw_user_request"] = dict(
        normalized.get("raw_user_request") or plan_seed.get("raw_user_request") or {}
    )
    normalized["source_of_truth"] = "raw_user_request"

    def _dedupe_str_list(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            value = str(item).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
        return result

    app_type_aliases = {
        "web": "admin_web",
        "admin": "admin_web",
        "admin_web": "admin_web",
        "desktop": "desktop_client",
        "desktop_client": "desktop_client",
        "client": "desktop_client",
        "workstation": "desktop_client",
    }
    normalized_app_type = app_type_aliases.get(str(normalized.get("app_type") or "").strip().lower(), "")
    normalized["app_type"] = normalized_app_type or plan_seed.get("app_type") or "admin_web"

    current_modules = _dedupe_str_list(list(normalized.get("core_modules") or []))
    current_routes = _dedupe_str_list(list(normalized.get("required_pages") or []))
    current_roles = _dedupe_str_list(list(normalized.get("user_roles") or []))
    current_entities = _dedupe_str_list(list(normalized.get("core_entities") or []))

    if not current_modules:
        current_modules = list(plan_seed.get("core_modules") or [])
    if not current_routes:
        current_routes = list(plan_seed.get("required_pages") or [])
    if not current_roles:
        current_roles = list(plan_seed.get("user_roles") or [])
    if not current_entities:
        current_entities = list(plan_seed.get("core_entities") or [])

    normalized["core_modules"] = current_modules
    normalized["required_pages"] = current_routes
    normalized["user_roles"] = current_roles
    normalized["core_entities"] = current_entities
    if not str(normalized.get("scene") or "").strip():
        normalized["scene"] = plan_seed.get("scene") or ""
    if not str(normalized.get("industry_scope") or "").strip():
        normalized["industry_scope"] = plan_seed.get("industry_scope") or ""
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


def _json_text(value: str) -> str:
    return json.dumps(str(value or ""), ensure_ascii=False)


def _synthesize_support_runtime_files(
    generated_files: dict[str, str],
    profile: dict,
    required_files: list[str],
    *,
    overwrite_existing: bool = False,
) -> tuple[dict[str, str], list[str]]:
    synthesized = dict(generated_files)
    repaired_paths: list[str] = []
    product_name = str(profile.get("product_name") or "业务平台").strip() or "业务平台"
    version = str(profile.get("version") or "V1.0").strip() or "V1.0"

    support_files = {
        "frontend/src/services/api.ts": """export interface ApiResult<T = unknown> {
  success: boolean;
  data?: T;
  message?: string;
}

export async function request<T = unknown>(payload: T): Promise<ApiResult<T>> {
  return { success: true, data: payload };
}

export const api = {
  login: async (username: string, _password: string) =>
    request({
      token: "demo-token",
      user: {
        name: username || "管理员",
        role: "管理员",
      },
    }),
};
""",
        "frontend/src/types/constants.ts": (
            f"export const APP_NAME = {_json_text(product_name)};\n"
            f"export const APP_VERSION = {_json_text(version)};\n"
            "export const DEMO_USERNAME = 'admin';\n"
            "export const DEMO_PASSWORD = 'admin123';\n"
            "export const COLORS = {\n"
            "  primary: '#1677ff',\n"
            "  success: '#52c41a',\n"
            "  warning: '#faad14',\n"
            "  error: '#ff4d4f',\n"
            "  info: '#1890ff',\n"
            "  text: '#334155',\n"
            "  muted: '#64748b',\n"
            "  background: '#f8fafc',\n"
            "  panel: '#ffffff',\n"
            "} as const;\n"
        ),
        "frontend/src/types/models.ts": """export interface DemoUser {
  name: string;
  role: string;
}

export interface LoginResponse {
  token: string;
  user: DemoUser;
}

export interface ApiResult<T = unknown> {
  success: boolean;
  data?: T;
  message?: string;
}
""",
    }

    for relative_path, content in support_files.items():
        if relative_path not in required_files:
            continue
        if not overwrite_existing and str(synthesized.get(relative_path, "")).strip():
            continue
        synthesized[relative_path] = content
        repaired_paths.append(relative_path)

    return synthesized, repaired_paths


def repair_invalid_support_files(
    generated_files: dict[str, str],
    profile: dict,
    required_files: list[str],
) -> tuple[dict[str, str], list[str]]:
    repaired = dict(generated_files)
    invalid_paths: list[str] = []

    validators = {
        "frontend/src/services/api.ts": lambda content: (
            bool(content)
            and "import.meta.env" not in content
            and "ApiResult" in content
            and "request<" in content
            and "login:" in content
        ),
        "frontend/src/types/constants.ts": lambda content: (
            bool(content)
            and "APP_NAME" in content
            and "APP_VERSION" in content
            and "DEMO_USERNAME" in content
            and "DEMO_PASSWORD" in content
            and "COLORS" in content
        ),
        "frontend/src/types/models.ts": lambda content: (
            bool(content)
            and "export interface DemoUser" in content
            and "export interface LoginResponse" in content
            and "export interface ApiResult" in content
        ),
    }

    for relative_path, validator in validators.items():
        if relative_path not in required_files:
            continue
        content = str(repaired.get(relative_path, "") or "")
        if validator(content):
            continue
        invalid_paths.append(relative_path)

    return repaired, invalid_paths


def _build_module_route_specs(profile: dict, generated_files: dict[str, str]) -> list[dict[str, str | bool]]:
    route_specs: list[dict[str, str | bool]] = []
    seen_routes: set[str] = set()
    for index, module in enumerate(profile.get("modules", []), start=1):
        raw_route = str(module.get("route") or "").strip()
        route = raw_route or f"/module-{index}"
        if route in seen_routes:
            continue
        seen_routes.add(route)
        source = module.get("route") or module.get("key") or module.get("title") or route
        component_name = f"{_camel_name(str(source))}Page"
        file_path = f"frontend/src/pages/{component_name}.tsx"
        route_specs.append(
            {
                "route": route,
                "title": str(module.get("title") or f"业务模块{index}").strip() or f"业务模块{index}",
                "description": str(module.get("description") or "").strip(),
                "component_name": component_name,
                "has_component": bool(str(generated_files.get(file_path, "")).strip()),
            }
        )
    return route_specs


def _synthesize_app_tsx(profile: dict, generated_files: dict[str, str]) -> str:
    return _render_frontend_app(profile)


def _synthesize_dashboard_tsx(profile: dict) -> str:
    return _render_dashboard_page(profile)


def _synthesize_login_tsx(profile: dict) -> str:
    return _render_login_page(profile)


def synthesize_recoverable_core_files(
    generated_files: dict[str, str],
    invalid_core_paths: list[str],
    profile: dict,
) -> tuple[dict[str, str], list[str]]:
    synthesized = dict(generated_files)
    repaired_paths: list[str] = []
    builders = {
        "frontend/src/App.tsx": lambda: _synthesize_app_tsx(profile, synthesized),
        "frontend/src/pages/Dashboard.tsx": lambda: _synthesize_dashboard_tsx(profile),
        "frontend/src/pages/Login.tsx": lambda: _synthesize_login_tsx(profile),
    }
    for relative_path in invalid_core_paths:
        builder = builders.get(relative_path)
        if not builder:
            continue
        synthesized[relative_path] = builder()
        repaired_paths.append(relative_path)
    return synthesized, repaired_paths


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
    app_type = str(profile.get("app_type") or "admin_web")
    blueprint = profile.get("experience_blueprint") or {}
    visual_profile = profile.get("visual_profile") or {}
    navigation_variant = str(blueprint.get("navigation_variant") or "").strip()
    chrome_treatment = str(visual_profile.get("chrome_treatment") or "").strip()
    requires_route_shell = bool(expected_module_imports or expected_module_routes)
    allowed_page_imports = {"Login", "Dashboard", *expected_module_imports}
    required_page_import_lines = [
        f"import {component_name} from './pages/{component_name}';"
        for component_name in expected_module_imports
    ]

    def _contains_any(content: str, tokens: list[str]) -> bool:
        return any(token in content for token in tokens if token)

    def _references_unknown_page_import(content: str) -> bool:
        imported_pages = set(
            match.group(1)
            for match in re.finditer(
                r"import\s+([A-Za-z_][A-Za-z0-9_]*)\s+from\s+['\"]\.\/pages\/[A-Za-z_][A-Za-z0-9_]*['\"]",
                content,
            )
        )
        return any(name not in allowed_page_imports for name in imported_pages)

    def _has_duplicate_page_imports_or_routes(content: str) -> bool:
        imported_pages = [
            match.group(1)
            for match in re.finditer(
                r"import\s+([A-Za-z_][A-Za-z0-9_]*)\s+from\s+['\"]\.\/pages\/[A-Za-z_][A-Za-z0-9_]*['\"]",
                content,
            )
        ]
        if len(imported_pages) != len(set(imported_pages)):
            return True

        route_paths = [
            match.group(1).strip()
            for match in re.finditer(
                r"<Route\s+path\s*=\s*['\"]([^'\"]+)['\"]",
                content,
            )
            if match.group(1).strip()
        ]
        return len(route_paths) != len(set(route_paths))

    def _uses_valid_login_entry(content: str) -> bool:
        if "<Login" not in content:
            return True
        return _contains_any(
            content,
            [
                "<Login onLogin={handleLogin}",
                "<Login onLogin={handleLogin} />",
                "<Login onLogin={() => undefined}",
                "<Login onLogin={() => undefined} />",
            ],
        )

    def _supports_login_callback(content: str) -> bool:
        return _contains_any(content, ["onLogin: () => void", "{ onLogin }: { onLogin: () => void }"])

    def _uses_valid_login_component_signature(content: str) -> bool:
        return _supports_login_callback(content) or _contains_any(
            content,
            [
                "export default function Login()",
                "function Login()",
                "const Login = () =>",
                "const Login=() =>",
            ],
        )

    def _uses_dashboard_metric_type_override(content: str) -> bool:
        return bool(
            re.search(
                r"\bconst\s+\w+\s*:\s*(?:Metric\[\]|Array<Metric>)\s*=\s*APP_PROFILE\.dashboard_metrics\b",
                content,
            )
        )

    def _uses_disallowed_unified_sidebar(content: str) -> bool:
        if app_type == "desktop_client":
            return False
        if navigation_variant not in {"top_tabs", "indexed", "sectioned"} and chrome_treatment not in {
            "top_tabs",
            "indexed_topbar",
            "sectioned_header",
        }:
            return False
        sidebar_tokens = [
            "Sider",
            "theme=\"dark\"",
            "mode=\"inline\"",
            "左侧深色竖向导航",
            "左侧导航",
        ]
        return _contains_any(content, sidebar_tokens)

    app_content = str(repaired.get("frontend/src/App.tsx") or "")
    app_requires_login_callback = "<Login onLogin=" in app_content

    validators = {
        "frontend/src/App.tsx": lambda content: (
            "PlaceholderPage" not in content
            and "模块开发中" not in content
            and "ModuleShell" not in content
            and not _contains_any(
                content,
                [
                    "APP_PROFILE.navigation",
                    "APP_PROFILE.name",
                    "APP_PROFILE.appName",
                ],
            )
            and not _references_unknown_page_import(content)
            and not _has_duplicate_page_imports_or_routes(content)
            and not _uses_disallowed_unified_sidebar(content)
            and _contains_any(content, ["export default function App", "function App(", "const App"])
            and _contains_any(content, ["APP_PROFILE", "generated/appProfile"])
            and _uses_valid_login_entry(content)
            and "const handleLogin = (token:" not in content
            and "const handleLogin = (value:" not in content
            and "return <Login />" not in content
            and "return <Login/>" not in content
            and (
                not requires_route_shell
                or (
                    _contains_any(content, ["Routes", "Route", "useRoutes"])
                    and all(import_line in content for import_line in required_page_import_lines)
                    and _contains_any(content, expected_module_routes)
                )
            )
        ),
        "frontend/src/pages/Dashboard.tsx": lambda content: (
            "模块开发中" not in content
            and not _contains_any(
                content,
                [
                    "totalProjects",
                    "activeTasks",
                    "environments",
                    "passedTests",
                    "totalCases",
                    "todayExecutions",
                    "passRate",
                    "totalEvents",
                    "processingOrders",
                    "pendingConfirm",
                    "avgResponseTime",
                    "todayAlerts",
                    "processing",
                    "overdueWarnings",
                    "closed",
                    "openIncidents",
                    "inProgress",
                    "resolvedToday",
                    "escalation",
                    "metric.icon",
                    "metric.label",
                    "item.icon",
                    "item.label",
                    "echarts-for-react/lib/core",
                    "echarts/core",
                    "echarts/charts",
                    "echarts/components",
                    "echarts/renderers",
                    "setMetrics(APP_PROFILE.dashboard_metrics",
                    "setMetrics(APP_PROFILE?.dashboard_metrics",
                    "anomalyTotal",
                    "pendingTasks",
                    "closureRate",
                    "avgProcessHours",
                    "ScheduleOutlined",
                    "CloudServerOutlined",
                    "CodeOutlined",
                    ".strong",
                    ".suffix",
                    ".trend",
                    ".up",
                ],
            )
            and not _uses_dashboard_metric_type_override(content)
            and _contains_any(content, ["export default function Dashboard", "function Dashboard(", "const Dashboard"])
            and _contains_any(content, ["APP_PROFILE", "dashboard_metrics", "product_name"])
            and ("const dashboardVariant =" not in content or "const dashboardVariant: string =" in content)
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
            and (
                _supports_login_callback(content)
                if app_requires_login_callback
                else _uses_valid_login_component_signature(content)
            )
            and ("const loginVariant =" not in content or "const loginVariant: string =" in content)
            and _contains_any(content, ["登录", "密码", "用户名"])
        ),
    }

    for relative_path, validator in validators.items():
        content = repaired.get(relative_path)
        if content and validator(str(content)):
            continue
        invalid_paths.append(relative_path)

    return repaired, invalid_paths


def repair_invalid_module_pages(
    generated_files: dict[str, str],
    profile: dict,
) -> tuple[dict[str, str], list[str]]:
    repaired = dict(generated_files)
    invalid_paths: list[str] = []

    for module in profile.get("modules", []):
        component_name = f"{_camel_name(module.get('route', module['key']))}Page"
        relative_path = f"frontend/src/pages/{component_name}.tsx"
        content = str(repaired.get(relative_path, "") or "")
        normalized_content = content.replace("../../generated/appProfile", "../generated/appProfile")
        if normalized_content != content:
            repaired[relative_path] = normalized_content
            content = normalized_content
        row_tokens = [
            str(cell).strip()
            for row in list(module.get("rows", []))[:2]
            for cell in list(row)[:3]
            if str(cell).strip()
        ]
        header_tokens = [str(item).strip() for item in list(module.get("table_headers", []))[:3] if str(item).strip()]
        has_valid_profile_import = "../generated/appProfile" in content and "../../generated/appProfile" not in content
        must_have_task_data = any(token and token in content for token in [module.get("title", ""), *header_tokens, *row_tokens])
        uses_invalid_profile_alias = any(
            token in content
            for token in [
                "productName",
                "visualConfig",
                "APP_PROFILE.roles",
                "APP_PROFILE.name",
                "APP_PROFILE.appName",
                "APP_PROFILE.navigation",
                "APP_PROFILE.module_pages",
                "APP_PROFILE.title",
                "APP_PROFILE.description",
                "APP_PROFILE.theme",
                "editable:",
            ]
        ) or bool(re.search(r"APP_PROFILE\.visual(?!_profile)\b", content))
        uses_invalid_modal_header_style = "<Modal" in content and "headerStyle=" in content
        imports_unsupported_shared_models = any(
            token in content
            for token in [
                "from '../types/models'",
                'from "../types/models"',
            ]
        )
        uses_invalid_profile_any_cast = "APP_PROFILE as any" in content
        uses_invalid_module_pages_alias = bool(re.search(r"APP_PROFILE[^\n]{0,80}\?\.modulePages\b", content))
        uses_unsafe_visual_profile = "APP_PROFILE.visual_profile." in content
        visual_profile_aliases = {
            match.group("name")
            for match in re.finditer(
                r"\b(?:const|let|var)\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=;]+)?=\s*APP_PROFILE\.visual_profile\s*;",
                content,
            )
        }
        uses_visual_profile_alias_without_guard = any(
            re.search(rf"\b{re.escape(alias)}\.[A-Za-z_]", content)
            for alias in visual_profile_aliases
        )
        references_message_without_import = (
            "message." in content
            and "import { message" not in content
            and "message } from 'antd'" not in content
            and 'message } from "antd"' not in content
            and "message," not in content
        )
        references_statistic_without_import = (
            any(token in content for token in ["<Statistic", " Statistic.", " Statistic "])
            and "import { Statistic" not in content
            and "Statistic } from 'antd'" not in content
            and "Statistic," not in content
        )
        references_typography_without_import = (
            any(token in content for token in ["<Typography", "Typography.", "= Typography"])
            and "import { Typography" not in content
            and "Typography } from 'antd'" not in content
            and 'Typography } from "antd"' not in content
            and "Typography," not in content
        )
        is_valid = (
            bool(content)
            and has_valid_profile_import
            and "APP_PROFILE" in content
            and "ModuleShell" not in content
            and "模块开发中" not in content
            and "const mockData" not in content
            and "mockData:" not in content
            and must_have_task_data
            and not uses_invalid_profile_alias
            and not uses_invalid_modal_header_style
            and not imports_unsupported_shared_models
            and not uses_invalid_profile_any_cast
            and not uses_invalid_module_pages_alias
            and not uses_unsafe_visual_profile
            and not uses_visual_profile_alias_without_guard
            and not references_message_without_import
            and not references_statistic_without_import
            and not references_typography_without_import
        )
        if is_valid:
            continue
        invalid_paths.append(relative_path)

    return repaired, invalid_paths


def synthesize_recoverable_module_files(
    generated_files: dict[str, str],
    invalid_module_paths: list[str],
    profile: dict,
) -> tuple[dict[str, str], list[str]]:
    synthesized = dict(generated_files)
    repaired_paths: list[str] = []
    modules_by_path: dict[str, dict] = {}
    for module in profile.get("modules", []):
        component_name = f"{_camel_name(module.get('route', module['key']))}Page"
        relative_path = f"frontend/src/pages/{component_name}.tsx"
        modules_by_path[relative_path] = module

    for relative_path in invalid_module_paths:
        module = modules_by_path.get(relative_path)
        if not module:
            continue
        synthesized[relative_path] = _render_module_page(module)
        repaired_paths.append(relative_path)

    return synthesized, repaired_paths


def _apply_retry_module_structural_fallback(
    generated_files: dict[str, str],
    required_chunk: list[str],
    profile: dict,
) -> tuple[dict[str, str], list[str], list[str]]:
    synthesized, repaired_paths = synthesize_recoverable_module_files(
        generated_files,
        required_chunk,
        profile,
    )
    if not repaired_paths:
        return generated_files, [], repair_invalid_module_pages(generated_files, profile)[1]
    synthesized, invalid_module_paths = repair_invalid_module_pages(synthesized, profile)
    return synthesized, repaired_paths, invalid_module_paths


def _apply_retry_core_structural_fallback(
    app_root: str,
    generated_files: dict[str, str],
    required_chunk: list[str],
    profile: dict,
) -> tuple[dict[str, str], list[str], list[str]]:
    synthesized, repaired_paths = synthesize_recoverable_core_files(
        generated_files,
        required_chunk,
        profile,
    )
    if not repaired_paths:
        return generated_files, [], repair_invalid_core_files(app_root, generated_files, profile)[1]
    synthesized, invalid_core_paths = repair_invalid_core_files(app_root, synthesized, profile)
    return synthesized, repaired_paths, invalid_core_paths


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
        hints.append("App.tsx 只能引用 Login、Dashboard 和当前任务 required_files 中明确要求的模块页面，不能额外导入不存在的页面组件。")
        hints.append("App.tsx 不得重复导入同一个页面组件，也不得重复声明相同 path 的 Route。")
        if module_routes:
            hints.append(
                "App.tsx 必须使用 Routes/Route 或 useRoutes 显式挂接这些模块路由: "
                + ", ".join(module_routes)
            )
        hints.append("App.tsx 不得输出 PlaceholderPage、'模块开发中' 或统一后台占位壳层。")
        navigation_variant = str((profile.get("experience_blueprint") or {}).get("navigation_variant") or "").strip()
        chrome_treatment = str((profile.get("visual_profile") or {}).get("chrome_treatment") or "").strip()
        if navigation_variant or chrome_treatment:
            hints.append(
                "App.tsx 必须落实当前任务指定的壳层方向，navigation_variant="
                + (navigation_variant or "unknown")
                + "，chrome_treatment="
                + (chrome_treatment or "unknown")
                + "；不得回退为统一左侧深色竖栏后台。"
            )
    if "frontend/src/pages/Dashboard.tsx" in invalid_paths:
        hints.append(
            "Dashboard.tsx 必须直接读取 APP_PROFILE.product_name 与 APP_PROFILE.dashboard_metrics，并在页面中展示中文首页/工作台标题。"
        )
        hints.append(
            "Dashboard.tsx 必须把 APP_PROFILE.dashboard_metrics 当作数组使用，不能访问 openIncidents、inProgress、resolvedToday、escalation 等对象字段。"
        )
    if "frontend/src/pages/Login.tsx" in invalid_paths:
        hints.append(
            "Login.tsx 必须包含中文登录表单，并通过 onLogin、handleSubmit 或 localStorage(ipright_demo_auth) 完成登录态写入。"
        )
    return hints


def _build_module_validation_hints(profile: dict, invalid_paths: list[str]) -> list[str]:
    hints: list[str] = []
    modules_by_path: dict[str, dict] = {}
    for module in profile.get("modules", []):
        component_name = f"{_camel_name(module.get('route', module['key']))}Page"
        relative_path = f"frontend/src/pages/{component_name}.tsx"
        modules_by_path[relative_path] = module

    for relative_path in invalid_paths:
        module = modules_by_path.get(relative_path)
        if not module:
            continue
        title = str(module.get("title") or module.get("key") or relative_path).strip()
        route = str(module.get("route") or "").strip()
        page_variant = str(module.get("page_variant") or "records").strip()
        table_headers = [str(item).strip() for item in list(module.get("table_headers", []))[:5] if str(item).strip()]
        row_tokens = [
            str(cell).strip()
            for row in list(module.get("rows", []))[:2]
            for cell in list(row)[:4]
            if str(cell).strip()
        ]
        highlights = [str(item).strip() for item in list(module.get("highlights", []))[:3] if str(item).strip()]
        primary_action = str(module.get("primary_action") or "").strip()
        filter_placeholder = str(module.get("filter_placeholder") or "").strip()

        hints.append(
            f"{relative_path} 必须是 {title} 的真实业务页面，直接从 ../generated/appProfile 读取 APP_PROFILE，不能使用 ModuleShell、模块开发中、mockData 或 testData 占位实现。"
        )
        if route:
            hints.append(f"{relative_path} 必须围绕路由 {route} 的业务语境组织页面内容，不得复用其他模块页面。")
        hints.append(
            f"{relative_path} 必须体现 page_variant={page_variant} 对应的信息组织方式，并根据本模块主题自主设计正文布局，不能套用统一后台骨架。"
        )
        if table_headers or row_tokens:
            hints.append(
                f"{relative_path} 必须直接复用任务样例数据；至少覆盖这些字段/样例中的大部分："
                + "、".join([*table_headers, *row_tokens][:8])
            )
        if primary_action or filter_placeholder or highlights:
            module_traits = [item for item in [primary_action, filter_placeholder, *highlights] if item]
            hints.append(
                f"{relative_path} 需要把当前模块的主操作、筛选入口和信息重点落到页面中："
                + "、".join(module_traits[:6])
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
    progress_callback=None,
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
        for batch in batches:
            pending_files = [
                relative_path
                for relative_path in batch["required_files"]
                if not generated_files.get(relative_path)
            ]
            if not pending_files:
                continue

            if progress_callback is not None:
                await progress_callback(
                    {
                        "phase": "batch_started",
                        "batch": batch["name"],
                        "required_files": list(pending_files),
                        "required_file_count": len(pending_files),
                    }
                )

            for attempt_no in range(1, 4):
                current_required_files = list(pending_files)
                batch_requirements = dict(batch["requirements"])
                batch_requirements["required_files"] = current_required_files
                if batch["name"] != "core":
                    batch_requirements["module_pages"] = _select_module_pages_for_files(
                        batch_requirements,
                        current_required_files,
                    )

                if progress_callback is not None:
                    await progress_callback(
                        {
                            "phase": "attempt_started",
                            "batch": batch["name"],
                            "attempt": attempt_no,
                            "required_files": list(current_required_files),
                            "required_file_count": len(current_required_files),
                        }
                    )

                codegen_resp = await llm.generate_app_code(prd_content, work_order_content, batch_requirements)
                if not codegen_resp.success or not codegen_resp.structured:
                    if progress_callback is not None:
                        await progress_callback(
                            {
                                "phase": "attempt_failed",
                                "batch": batch["name"],
                                "attempt": attempt_no,
                                "required_files": list(current_required_files),
                                "generated_paths": [],
                                "pending_files": list(current_required_files),
                                "error": codegen_resp.error or "unknown error",
                            }
                        )
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
                    if progress_callback is not None:
                        await progress_callback(
                            {
                                "phase": "attempt_failed",
                                "batch": batch["name"],
                                "attempt": attempt_no,
                                "required_files": list(current_required_files),
                                "generated_paths": [],
                                "pending_files": list(current_required_files),
                                "error": "files payload missing",
                            }
                        )
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
                accepted_files = set(current_required_files)
                for relative_path, content in batch_files.items():
                    if relative_path in accepted_files and content:
                        generated_files[relative_path] = str(content)
                        generated_paths.append(relative_path)

                pending_files = [
                    relative_path
                    for relative_path in current_required_files
                    if not generated_files.get(relative_path)
                ]
                if progress_callback is not None:
                    await progress_callback(
                        {
                            "phase": "attempt_completed",
                            "batch": batch["name"],
                            "attempt": attempt_no,
                            "required_files": list(current_required_files),
                            "generated_paths": sorted(generated_paths),
                            "pending_files": list(pending_files),
                            "fallback_to_template": bool(pending_files),
                        }
                    )
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
            "model_used": "qwen3.7-max" if batches else "template_only",
            "required_files": codegen_requirements["required_files"],
            "generated_file_count": len(generated_files),
            "applied_required_file_count": len(codegen_requirements["required_files"]),
            "generated_paths": sorted(generated_files.keys()),
            "batches": batch_reports,
            "repaired_core_paths": [],
            "repaired_module_paths": [],
            "template_ui_fallback_used": False,
            "repaired_support_paths": [],
        }
        report.update(extra)
        return report

    generated_files = hydrate_missing_files_from_template(app_root, generated_files, codegen_requirements["required_files"])
    generated_files, repaired_support_paths = _synthesize_support_runtime_files(
        generated_files,
        profile,
        codegen_requirements["required_files"],
    )
    generated_files, invalid_support_paths = repair_invalid_support_files(
        generated_files,
        profile,
        codegen_requirements["required_files"],
    )
    if invalid_support_paths:
        generated_files, repaired_invalid_support_paths = _synthesize_support_runtime_files(
            generated_files,
            profile,
            invalid_support_paths,
            overwrite_existing=True,
        )
        if repaired_invalid_support_paths:
            repaired_support_paths = sorted(set([*repaired_support_paths, *repaired_invalid_support_paths]))
            generated_files, invalid_support_paths = repair_invalid_support_files(
                generated_files,
                profile,
                codegen_requirements["required_files"],
            )
            batch_reports.append(
                {
                    "batch": "support_structural_fallback",
                    "attempt": 1,
                    "required_files": list(repaired_invalid_support_paths),
                    "generated_paths": sorted(repaired_invalid_support_paths),
                    "fallback_to_template": bool(invalid_support_paths),
                    "error": (
                        "still invalid after structural fallback: " + ", ".join(invalid_support_paths)
                        if invalid_support_paths
                        else None
                    ),
                }
            )
    if invalid_support_paths:
        invalid_support_previews = {
            relative_path: _preview_generated_content(generated_files.get(relative_path, ""))
            for relative_path in invalid_support_paths
        }
        return _build_codegen_report(
            repaired_support_paths=sorted(repaired_support_paths),
            template_ui_fallback_used=bool(repaired_support_paths),
            invalid_support_paths=invalid_support_paths,
            invalid_support_previews=invalid_support_previews,
        ), (
            "App code generation failed: missing or invalid LLM-generated support frontend files: "
            + ", ".join(invalid_support_paths)
        )
    generated_files, invalid_core_paths = repair_invalid_core_files(app_root, generated_files, profile)
    if invalid_core_paths and batches:
        llm = get_llm_client()
        core_batch = next((batch for batch in batches if batch["name"] == "core"), None)
        if core_batch:
            for attempt_no in range(1, 3):
                retry_chunks = _chunk_required_files(invalid_core_paths, _CORE_INVALID_RETRY_BATCH_SIZE)
                for required_chunk in retry_chunks:
                    invalid_core_previews = {
                        relative_path: _preview_generated_content(generated_files.get(relative_path, ""))
                        for relative_path in required_chunk
                    }
                    retry_requirements = dict(core_batch["requirements"])
                    retry_requirements["required_files"] = list(required_chunk)
                    retry_requirements["validation_hints"] = _build_core_validation_hints(profile, required_chunk)
                    retry_requirements["invalid_core_previews"] = invalid_core_previews
                    if progress_callback is not None:
                        await progress_callback(
                            {
                                "phase": "attempt_started",
                                "batch": "core_invalid_retry",
                                "attempt": attempt_no,
                                "required_files": list(retry_requirements["required_files"]),
                                "required_file_count": len(retry_requirements["required_files"]),
                            }
                        )
                    codegen_resp = await llm.generate_app_code(prd_content, work_order_content, retry_requirements)
                    if not codegen_resp.success or not codegen_resp.structured:
                        if progress_callback is not None:
                            await progress_callback(
                                {
                                    "phase": "attempt_failed",
                                    "batch": "core_invalid_retry",
                                    "attempt": attempt_no,
                                    "required_files": list(retry_requirements["required_files"]),
                                    "generated_paths": [],
                                    "pending_files": list(required_chunk),
                                    "error": codegen_resp.error or "unknown error",
                                }
                            )
                        batch_reports.append(
                            {
                                "batch": "core_invalid_retry",
                                "attempt": attempt_no,
                                "required_files": list(required_chunk),
                                "generated_paths": [],
                                "fallback_to_template": True,
                                "error": codegen_resp.error or "unknown error",
                            }
                        )
                        (
                            generated_files,
                            repaired_retry_core_paths,
                            invalid_core_paths,
                        ) = _apply_retry_core_structural_fallback(
                            app_root,
                            generated_files,
                            list(required_chunk),
                            profile,
                        )
                        if repaired_retry_core_paths:
                            batch_reports.append(
                                {
                                    "batch": "core_retry_structural_fallback",
                                    "attempt": attempt_no,
                                    "required_files": list(required_chunk),
                                    "generated_paths": sorted(repaired_retry_core_paths),
                                    "fallback_to_template": bool(invalid_core_paths),
                                    "error": (
                                        "still invalid after retry structural fallback: "
                                        + ", ".join(invalid_core_paths)
                                        if invalid_core_paths
                                        else None
                                    ),
                                }
                            )
                            if not invalid_core_paths:
                                break
                        continue
                    batch_files = codegen_resp.structured.get("files", {})
                    if not isinstance(batch_files, dict):
                        if progress_callback is not None:
                            await progress_callback(
                                {
                                    "phase": "attempt_failed",
                                    "batch": "core_invalid_retry",
                                    "attempt": attempt_no,
                                    "required_files": list(retry_requirements["required_files"]),
                                    "generated_paths": [],
                                    "pending_files": list(required_chunk),
                                    "error": "files payload missing",
                                }
                            )
                        batch_reports.append(
                            {
                                "batch": "core_invalid_retry",
                                "attempt": attempt_no,
                                "required_files": list(required_chunk),
                                "generated_paths": [],
                                "fallback_to_template": True,
                                "error": "files payload missing",
                            }
                        )
                        (
                            generated_files,
                            repaired_retry_core_paths,
                            invalid_core_paths,
                        ) = _apply_retry_core_structural_fallback(
                            app_root,
                            generated_files,
                            list(required_chunk),
                            profile,
                        )
                        if repaired_retry_core_paths:
                            batch_reports.append(
                                {
                                    "batch": "core_retry_structural_fallback",
                                    "attempt": attempt_no,
                                    "required_files": list(required_chunk),
                                    "generated_paths": sorted(repaired_retry_core_paths),
                                    "fallback_to_template": bool(invalid_core_paths),
                                    "error": (
                                        "still invalid after retry structural fallback: "
                                        + ", ".join(invalid_core_paths)
                                        if invalid_core_paths
                                        else None
                                    ),
                                }
                            )
                            if not invalid_core_paths:
                                break
                        continue
                    regenerated_paths: list[str] = []
                    for relative_path, content in batch_files.items():
                        if relative_path in required_chunk and content:
                            generated_files[relative_path] = str(content)
                            regenerated_paths.append(relative_path)
                    generated_files, invalid_core_paths = repair_invalid_core_files(app_root, generated_files, profile)
                    if progress_callback is not None:
                        await progress_callback(
                            {
                                "phase": "attempt_completed",
                                "batch": "core_invalid_retry",
                                "attempt": attempt_no,
                                "required_files": list(retry_requirements["required_files"]),
                                "generated_paths": sorted(regenerated_paths),
                                "pending_files": list(invalid_core_paths),
                                "fallback_to_template": bool(invalid_core_paths),
                            }
                        )
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
    repaired_core_paths: list[str] = []
    if invalid_core_paths:
        generated_files, repaired_core_paths = synthesize_recoverable_core_files(
            generated_files,
            invalid_core_paths,
            profile,
        )
        if repaired_core_paths:
            generated_files, invalid_core_paths = repair_invalid_core_files(app_root, generated_files, profile)
            batch_reports.append(
                {
                    "batch": "core_structural_fallback",
                    "attempt": 1,
                    "required_files": list(repaired_core_paths),
                    "generated_paths": sorted(repaired_core_paths),
                    "fallback_to_template": bool(invalid_core_paths),
                    "error": (
                        "still invalid after structural fallback: " + ", ".join(invalid_core_paths)
                        if invalid_core_paths
                        else None
                    ),
                }
            )
    if invalid_core_paths:
        invalid_core_previews = {
            relative_path: _preview_generated_content(generated_files.get(relative_path, ""))
            for relative_path in invalid_core_paths
        }
        return _build_codegen_report(
            repaired_core_paths=sorted(repaired_core_paths),
            repaired_support_paths=sorted(repaired_support_paths),
            template_ui_fallback_used=bool(repaired_core_paths or repaired_support_paths),
            invalid_core_paths=invalid_core_paths,
            invalid_core_previews=invalid_core_previews,
        ), (
            "App code generation failed: missing or invalid LLM-generated core frontend files: "
            + ", ".join(invalid_core_paths)
        )
    generated_files, invalid_module_paths = repair_invalid_module_pages(generated_files, profile)
    if invalid_module_paths and batches:
        llm = get_llm_client()
        for attempt_no in range(1, 3):
            retry_chunks = _chunk_required_files(invalid_module_paths, _MODULE_INVALID_RETRY_BATCH_SIZE)
            for required_chunk in retry_chunks:
                invalid_module_previews = {
                    relative_path: _preview_generated_content(generated_files.get(relative_path, ""))
                    for relative_path in required_chunk
                }
                retry_requirements = {
                    **{
                        key: value
                        for key, value in codegen_requirements.items()
                        if key != "module_pages"
                    },
                    "required_files": list(required_chunk),
                    "module_pages": _select_module_pages_for_files(codegen_requirements, required_chunk),
                    "validation_hints": _build_module_validation_hints(profile, required_chunk),
                    "invalid_module_previews": invalid_module_previews,
                }
                if progress_callback is not None:
                    await progress_callback(
                        {
                            "phase": "attempt_started",
                            "batch": "module_invalid_retry",
                            "attempt": attempt_no,
                            "required_files": list(retry_requirements["required_files"]),
                            "required_file_count": len(retry_requirements["required_files"]),
                        }
                    )
                codegen_resp = await llm.generate_app_code(prd_content, work_order_content, retry_requirements)
                if not codegen_resp.success or not codegen_resp.structured:
                    if progress_callback is not None:
                        await progress_callback(
                            {
                                "phase": "attempt_failed",
                                "batch": "module_invalid_retry",
                                "attempt": attempt_no,
                                "required_files": list(retry_requirements["required_files"]),
                                "generated_paths": [],
                                "pending_files": list(required_chunk),
                                "error": codegen_resp.error or "unknown error",
                            }
                        )
                    batch_reports.append(
                        {
                            "batch": "module_invalid_retry",
                            "attempt": attempt_no,
                            "required_files": list(required_chunk),
                            "generated_paths": [],
                            "fallback_to_template": True,
                            "error": codegen_resp.error or "unknown error",
                        }
                    )
                    (
                        generated_files,
                        repaired_retry_module_paths,
                        invalid_module_paths,
                    ) = _apply_retry_module_structural_fallback(
                        generated_files,
                        list(required_chunk),
                        profile,
                    )
                    if repaired_retry_module_paths:
                        batch_reports.append(
                            {
                                "batch": "module_retry_structural_fallback",
                                "attempt": attempt_no,
                                "required_files": list(required_chunk),
                                "generated_paths": sorted(repaired_retry_module_paths),
                                "fallback_to_template": bool(invalid_module_paths),
                                "error": (
                                    "still invalid after retry structural fallback: "
                                    + ", ".join(invalid_module_paths)
                                    if invalid_module_paths
                                    else None
                                ),
                            }
                        )
                        if not invalid_module_paths:
                            break
                    continue
                batch_files = codegen_resp.structured.get("files", {})
                if not isinstance(batch_files, dict):
                    if progress_callback is not None:
                        await progress_callback(
                            {
                                "phase": "attempt_failed",
                                "batch": "module_invalid_retry",
                                "attempt": attempt_no,
                                "required_files": list(retry_requirements["required_files"]),
                                "generated_paths": [],
                                "pending_files": list(required_chunk),
                                "error": "files payload missing",
                            }
                        )
                    batch_reports.append(
                        {
                            "batch": "module_invalid_retry",
                            "attempt": attempt_no,
                            "required_files": list(required_chunk),
                            "generated_paths": [],
                            "fallback_to_template": True,
                            "error": "files payload missing",
                        }
                    )
                    (
                        generated_files,
                        repaired_retry_module_paths,
                        invalid_module_paths,
                    ) = _apply_retry_module_structural_fallback(
                        generated_files,
                        list(required_chunk),
                        profile,
                    )
                    if repaired_retry_module_paths:
                        batch_reports.append(
                            {
                                "batch": "module_retry_structural_fallback",
                                "attempt": attempt_no,
                                "required_files": list(required_chunk),
                                "generated_paths": sorted(repaired_retry_module_paths),
                                "fallback_to_template": bool(invalid_module_paths),
                                "error": (
                                    "still invalid after retry structural fallback: "
                                    + ", ".join(invalid_module_paths)
                                    if invalid_module_paths
                                    else None
                                ),
                            }
                        )
                        if not invalid_module_paths:
                            break
                    continue
                regenerated_paths: list[str] = []
                for relative_path, content in batch_files.items():
                    if relative_path in required_chunk and content:
                        generated_files[relative_path] = str(content)
                        regenerated_paths.append(relative_path)
                generated_files, invalid_module_paths = repair_invalid_module_pages(generated_files, profile)
                if progress_callback is not None:
                    await progress_callback(
                        {
                            "phase": "attempt_completed",
                            "batch": "module_invalid_retry",
                            "attempt": attempt_no,
                            "required_files": list(retry_requirements["required_files"]),
                            "generated_paths": sorted(regenerated_paths),
                            "pending_files": list(invalid_module_paths),
                            "fallback_to_template": bool(invalid_module_paths),
                        }
                    )
                batch_reports.append(
                    {
                        "batch": "module_invalid_retry",
                        "attempt": attempt_no,
                        "required_files": list(retry_requirements["required_files"]),
                        "generated_paths": sorted(regenerated_paths),
                        "fallback_to_template": bool(invalid_module_paths),
                        "error": (
                            "still invalid after retry: " + ", ".join(invalid_module_paths)
                            if invalid_module_paths
                            else None
                        ),
                    }
                )
                if not invalid_module_paths:
                    break
            if not invalid_module_paths:
                break
    repaired_module_paths: list[str] = []
    if invalid_module_paths:
        generated_files, repaired_module_paths = synthesize_recoverable_module_files(
            generated_files,
            invalid_module_paths,
            profile,
        )
        if repaired_module_paths:
            generated_files, invalid_module_paths = repair_invalid_module_pages(generated_files, profile)
            batch_reports.append(
                {
                    "batch": "module_structural_fallback",
                    "attempt": 1,
                    "required_files": list(repaired_module_paths),
                    "generated_paths": sorted(repaired_module_paths),
                    "fallback_to_template": bool(invalid_module_paths),
                    "error": (
                        "still invalid after structural fallback: " + ", ".join(invalid_module_paths)
                        if invalid_module_paths
                        else None
                    ),
                }
            )
    if invalid_module_paths:
        invalid_module_previews = {
            relative_path: _preview_generated_content(generated_files.get(relative_path, ""))
            for relative_path in invalid_module_paths
        }
        return _build_codegen_report(
            repaired_core_paths=sorted(repaired_core_paths),
            repaired_module_paths=sorted(repaired_module_paths),
            repaired_support_paths=sorted(repaired_support_paths),
            template_ui_fallback_used=bool(repaired_core_paths or repaired_module_paths or repaired_support_paths),
            invalid_module_paths=invalid_module_paths,
            invalid_module_previews=invalid_module_previews,
        ), (
            "App code generation failed: missing or invalid LLM-generated module frontend files: "
            + ", ".join(invalid_module_paths)
        )
    generated_files = normalize_generated_frontend_files(generated_files)
    applied, apply_error = apply_generated_code_bundle(app_root, generated_files, codegen_requirements["required_files"])
    if not applied:
        return _build_codegen_report(
            repaired_core_paths=sorted(repaired_core_paths),
            repaired_module_paths=sorted(repaired_module_paths),
            repaired_support_paths=sorted(repaired_support_paths),
            template_ui_fallback_used=bool(repaired_core_paths or repaired_module_paths or repaired_support_paths),
            apply_error=apply_error,
        ), f"App code generation failed: {apply_error}"

    sync_frontend_dependencies(os.path.join(app_root, "frontend"))

    return _build_codegen_report(
        repaired_core_paths=sorted(repaired_core_paths),
        repaired_module_paths=sorted(repaired_module_paths),
        repaired_support_paths=sorted(repaired_support_paths),
        template_ui_fallback_used=bool(repaired_core_paths or repaired_module_paths or repaired_support_paths),
    ), None
