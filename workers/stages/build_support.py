from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from app.services.project_profile import build_frontend_profile_source
from workers.stages.generated_backend import GENERATED_BACKEND_APP_FILES, write_generated_backend_files
_CORE_INVALID_RETRY_BATCH_SIZE = 1
_MODULE_INVALID_RETRY_BATCH_SIZE = 1
_CORE_FRONTEND_DEPENDENCIES = {
    "@ant-design/icons": "^5.3.0",
    "antd": "^5.15.0",
    "axios": "^1.6.0",
    "dayjs": "^1.11.0",
}
_OPTIONAL_FRONTEND_DEPENDENCIES = {
    "@ant-design/charts": "^2.6.5",
    "@ant-design/pro-components": "^2.8.6",
    "echarts": "^5.5.0",
    "echarts-for-react": "^3.0.2",
}
_UNSUPPORTED_UTILITY_CLASS_TOKENS = (
    "bg-",
    "text-",
    "grid-cols-",
    "rounded-",
    "shadow",
    "p-",
    "m-",
    "px-",
    "py-",
    "gap-",
    "space-y-",
    "min-h-screen",
)


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _iter_frontend_source_imports(frontend_root: str) -> set[str]:
    src_root = Path(frontend_root) / "src"
    if not src_root.exists():
        return set()

    imports: set[str] = set()
    import_re = re.compile(r"""(?:from|import)\s+['"](?P<module>[^'"]+)['"]""")
    for source_path in src_root.rglob("*"):
        if source_path.suffix not in {".ts", ".tsx", ".js", ".jsx"}:
            continue
        content = source_path.read_text(encoding="utf-8")
        for match in import_re.finditer(content):
            imports.add(match.group("module"))
    return imports


def sync_frontend_dependencies(frontend_root: str) -> None:
    package_json_path = Path(frontend_root) / "package.json"
    if not package_json_path.exists():
        return

    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
    dependencies = package_json.setdefault("dependencies", {})
    for name, version in _CORE_FRONTEND_DEPENDENCIES.items():
        dependencies.setdefault(name, version)

    imported_modules = _iter_frontend_source_imports(frontend_root)
    needs_ant_design_charts = "@ant-design/charts" in imported_modules
    needs_pro_components = "@ant-design/pro-components" in imported_modules
    needs_echarts_for_react = "echarts-for-react" in imported_modules
    needs_echarts = needs_echarts_for_react or "echarts" in imported_modules

    if needs_ant_design_charts:
        dependencies.setdefault(
            "@ant-design/charts",
            _OPTIONAL_FRONTEND_DEPENDENCIES["@ant-design/charts"],
        )
    else:
        dependencies.pop("@ant-design/charts", None)

    if needs_pro_components:
        dependencies.setdefault(
            "@ant-design/pro-components",
            _OPTIONAL_FRONTEND_DEPENDENCIES["@ant-design/pro-components"],
        )
    else:
        dependencies.pop("@ant-design/pro-components", None)

    if needs_echarts:
        dependencies.setdefault("echarts", _OPTIONAL_FRONTEND_DEPENDENCIES["echarts"])
    else:
        dependencies.pop("echarts", None)

    if needs_echarts_for_react:
        dependencies.setdefault(
            "echarts-for-react",
            _OPTIONAL_FRONTEND_DEPENDENCIES["echarts-for-react"],
        )
    else:
        dependencies.pop("echarts-for-react", None)

    _write_json(str(package_json_path), package_json)


def _ensure_frontend_dependencies(frontend_root: str) -> None:
    package_json_path = os.path.join(frontend_root, "package.json")
    if not os.path.exists(package_json_path):
        return
    with open(package_json_path, "r", encoding="utf-8") as f:
        package_json = json.load(f)
    dependencies = package_json.setdefault("dependencies", {})
    for name, version in _CORE_FRONTEND_DEPENDENCIES.items():
        dependencies.setdefault(name, version)
    _write_json(package_json_path, package_json)


def _ensure_backend_dependencies(backend_root: str) -> None:
    requirements_path = os.path.join(backend_root, "requirements.txt")
    if not os.path.exists(requirements_path):
        return

    with open(requirements_path, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]

    normalized = [line.strip().lower() for line in lines if line.strip()]
    if not any(line.startswith("pyjwt") for line in normalized):
        lines.append("PyJWT>=2.8")

    with open(requirements_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def _camel_name(value: str) -> str:
    parts = re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", value)
    cleaned = "".join(part[:1].upper() + part[1:] for part in parts if part)
    if not cleaned:
        return "ModulePage"
    if cleaned[0].isdigit():
        return f"Module{cleaned}"
    return cleaned


def _write_task_specific_app(frontend_root: str, backend_root: str, profile: dict) -> None:
    _ensure_frontend_dependencies(frontend_root)
    _ensure_backend_dependencies(backend_root)
    package_lock_path = Path(frontend_root) / "package-lock.json"
    if package_lock_path.exists():
        package_lock_path.unlink()
    _write_text(
        os.path.join(frontend_root, "src", "generated", "appProfile.ts"),
        build_frontend_profile_source(profile),
    )

    app_entry = Path(frontend_root) / "src" / "App.tsx"
    pages_dir = Path(frontend_root) / "src" / "pages"
    seed_support_files = [
        Path(frontend_root) / "src" / "services" / "api.ts",
        Path(frontend_root) / "src" / "types" / "constants.ts",
        Path(frontend_root) / "src" / "types" / "models.ts",
    ]
    if app_entry.exists():
        app_entry.unlink()
    if pages_dir.exists():
        shutil.rmtree(pages_dir)
    for seed_path in seed_support_files:
        if seed_path.exists():
            seed_path.unlink()

    write_generated_backend_files(backend_root, profile, _write_text)


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


def _build_available_route_shell_module_pages(
    profile: dict,
    generated_files: dict[str, str],
) -> list[dict]:
    module_pages = _build_route_shell_module_pages(build_codegen_requirements(profile).get("module_pages", []))
    module_page_by_component = {
        str(page.get("component_name") or "").strip(): page
        for page in module_pages
        if str(page.get("component_name") or "").strip()
    }
    available_pages: list[dict] = []
    for relative_path in sorted(generated_files):
        if not relative_path.startswith("frontend/src/pages/") or not relative_path.endswith(".tsx"):
            continue
        component_name = Path(relative_path).stem
        if component_name in {"Login", "Dashboard"}:
            continue
        module_page = module_page_by_component.get(component_name)
        if not module_page:
            continue
        available_pages.append(
            {
                "title": module_page.get("title"),
                "route": module_page.get("route"),
                "file_path": relative_path,
                "component_name": component_name,
            }
        )
    return available_pages


def _render_structured_app_tsx(profile: dict, generated_files: dict[str, str]) -> str:
    module_pages = _build_available_route_shell_module_pages(profile, generated_files)
    route_items = [{"key": "/dashboard", "label": "首页"}]
    route_items.extend(
        {
            "key": str(page.get("route") or "").strip(),
            "label": str(page.get("title") or page.get("component_name") or "").strip(),
        }
        for page in module_pages
        if str(page.get("route") or "").strip()
    )
    import_lines = [
        "import type { ReactNode } from 'react';",
        "import { useEffect, useMemo, useState } from 'react';",
        "import { Avatar, Layout, Menu, Space, Typography } from 'antd';",
        "import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';",
        "import Login from './pages/Login';",
        "import Dashboard from './pages/Dashboard';",
        "import { APP_PROFILE } from './generated/appProfile';",
    ]
    for page in module_pages:
        component_name = page.get("component_name")
        if component_name:
            import_lines.append(f"import {component_name} from './pages/{component_name}';")

    protected_routes = [
        '      <Route path="/dashboard" element={loggedIn ? <AppShell><Dashboard /></AppShell> : <Navigate to="/login" replace />} />'
    ]
    for page in module_pages:
        component_name = page.get("component_name")
        route = str(page.get("route") or "").strip()
        if component_name and route:
            protected_routes.append(
                '      <Route path="'
                + route
                + '" element={loggedIn ? <AppShell><'
                + component_name
                + ' /></AppShell> : <Navigate to="/login" replace />} />'
            )

    fallback_dashboard_route = "/dashboard"
    route_items_json = json.dumps(route_items, ensure_ascii=False)
    return "\n".join(
        [
            *import_lines,
            "",
            "const AUTH_KEY = 'ipright_demo_auth';",
            f"const ROUTE_ITEMS = {route_items_json};",
            "",
            "function readLoggedIn(): boolean {",
            "  if (typeof window === 'undefined') {",
            "    return false;",
            "  }",
            "  const storage = window.localStorage;",
            "  return Boolean(storage.getItem(AUTH_KEY) || storage.getItem('token') || storage.getItem('user'));",
            "}",
            "",
            "function findCurrentRoute(pathname: string): string {",
            "  const matched = ROUTE_ITEMS.find((item) => item.key !== '/dashboard' && pathname.startsWith(item.key));",
            "  return matched?.key || '/dashboard';",
            "}",
            "",
            "function findCurrentTitle(pathname: string): string {",
            "  return ROUTE_ITEMS.find((item) => item.key === findCurrentRoute(pathname))?.label || '系统首页';",
            "}",
            "",
            "function AppShell({ children }: { children: ReactNode }) {",
            "  const location = useLocation();",
            "  const navigate = useNavigate();",
            "  const selectedKey = useMemo(() => findCurrentRoute(location.pathname), [location.pathname]);",
            "  const pageTitle = useMemo(() => findCurrentTitle(location.pathname), [location.pathname]);",
            "  return (",
            "    <Layout style={{ minHeight: '100vh', background: '#f6f8fb' }}>",
            "      <Layout.Header",
            "        style={{",
            "          display: 'flex',",
            "          alignItems: 'center',",
            "          paddingInline: 28,",
            "          background: '#ffffff',",
            "          borderBottom: '1px solid #e5e7eb',",
            "          position: 'sticky',",
            "          top: 0,",
            "          zIndex: 10,",
            "        }}",
            "      >",
            "        <Space size={14} style={{ marginRight: 24 }}>",
            "          <Avatar style={{ backgroundColor: '#1d4ed8', color: '#fff' }}>软</Avatar>",
            "          <div>",
            "            <Typography.Text style={{ color: '#64748b', fontSize: 12 }}>软件页面入口</Typography.Text>",
            "            <Typography.Title level={5} style={{ color: '#0f172a', margin: 0 }}>{APP_PROFILE.product_name}</Typography.Title>",
            "          </div>",
            "        </Space>",
            "        <Menu",
            "          mode=\"horizontal\"",
            "          selectedKeys={[selectedKey]}",
            "          onClick={({ key }) => navigate(String(key))}",
            "          items={ROUTE_ITEMS.map((item) => ({ key: item.key, label: item.label }))}",
            "          style={{ flex: 1, minWidth: 0, background: 'transparent', borderBottom: 'none' }}",
            "        />",
            "      </Layout.Header>",
            "      <Layout.Content style={{ padding: '28px 32px 40px' }}>",
            "        <div style={{ maxWidth: 1440, margin: '0 auto' }}>",
            "          <div",
            "            style={{",
            "              background: '#ffffff',",
            "              borderRadius: 20,",
            "              padding: 24,",
            "              boxShadow: '0 18px 45px rgba(15, 23, 42, 0.06)',",
            "              minHeight: 'calc(100vh - 220px)',",
            "            }}",
            "          >",
            "            <Typography.Title level={4} style={{ marginTop: 0, marginBottom: 20 }}>{pageTitle}</Typography.Title>",
            "            {children}",
            "          </div>",
            "        </div>",
            "      </Layout.Content>",
            "    </Layout>",
            "  );",
            "}",
            "",
            "export default function App() {",
            "  const [loggedIn, setLoggedIn] = useState<boolean>(() => readLoggedIn());",
            "  const location = useLocation();",
            "",
            "  useEffect(() => {",
            "    setLoggedIn(readLoggedIn());",
            "  }, [location.pathname]);",
            "",
            "  useEffect(() => {",
            "    const originalSetItem = window.localStorage.setItem.bind(window.localStorage);",
            "    window.localStorage.setItem = ((key: string, value: string) => {",
            "      originalSetItem(key, value);",
            "      if (key === AUTH_KEY || key === 'token' || key === 'user') {",
            "        setLoggedIn(readLoggedIn());",
            "      }",
            "    }) as typeof window.localStorage.setItem;",
            "    return () => {",
            "      window.localStorage.setItem = originalSetItem;",
            "    };",
            "  }, []);",
            "",
            "  return (",
            "    <Routes>",
            '      <Route path="/" element={<Navigate to={loggedIn ? "'
            + fallback_dashboard_route
            + '" : "/login"} replace />} />',
            '      <Route path="/login" element={loggedIn ? <Navigate to="/dashboard" replace /> : <Login />} />',
            *protected_routes,
            '      <Route path="*" element={<Navigate to={loggedIn ? "'
            + fallback_dashboard_route
            + '" : "/login"} replace />} />',
            "    </Routes>",
            "  );",
            "}",
            "",
        ]
    )


def _synthesize_structured_core_files(
    generated_files: dict[str, str],
    profile: dict,
    required_files: list[str],
    *,
    overwrite_existing: bool = False,
) -> tuple[dict[str, str], list[str]]:
    synthesized = dict(generated_files)
    repaired_paths: list[str] = []

    for relative_path in required_files:
        content = str(synthesized.get(relative_path, "") or "")
        if relative_path == "frontend/src/App.tsx" and (overwrite_existing or not content.strip()):
            synthesized[relative_path] = _render_structured_app_tsx(profile, synthesized)
            repaired_paths.append(relative_path)

    return synthesized, repaired_paths


def build_seed_copy_ignore(extra_names: set[str] | None = None):
    extra_names = extra_names or set()

    def ignore(_src: str, names: list[str]) -> set[str]:
        ignored = {
            name
            for name in names
            if (
                name in {"node_modules", "dist", ".vite", "__pycache__", ".DS_Store", "__MACOSX"}
                or name.startswith("._")
                or name.endswith(".pyc")
            )
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
        "module_pages": module_pages,
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
    common_requirements: dict[str, object] = {}
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

    normalized["core_modules"] = current_modules
    normalized["required_pages"] = current_routes
    normalized["user_roles"] = current_roles
    normalized["core_entities"] = current_entities
    if not str(normalized.get("scene") or "").strip():
        normalized["scene"] = plan_seed.get("scene") or ""
    if not str(normalized.get("industry_scope") or "").strip():
        normalized["industry_scope"] = plan_seed.get("industry_scope") or ""
    return normalized


def normalize_generated_frontend_files(generated_files: dict[str, str]) -> dict[str, str]:
    return {relative_path: str(content) for relative_path, content in generated_files.items()}


def _extract_frontend_compile_error_paths(log_output: str) -> list[str]:
    paths: list[str] = []
    for match in re.finditer(r"(?m)^src/([^\n:]+\.(?:ts|tsx|js|jsx))\(\d+,\d+\): error ", log_output):
        relative_path = f"frontend/src/{match.group(1)}"
        if relative_path not in paths:
            paths.append(relative_path)
    return paths


def validate_generated_frontend_build(app_root: str) -> tuple[list[str], str | None]:
    frontend_root = Path(app_root) / "frontend"
    package_json = frontend_root / "package.json"
    if not package_json.exists():
        return [], None

    package_lock = frontend_root / "package-lock.json"
    if package_lock.exists():
        package_lock.unlink()

    commands = [
        ["npm", "install"],
        ["node", "node_modules/typescript/bin/tsc", "-b"],
        ["node", "node_modules/vite/bin/vite.js", "build"],
    ]
    combined_logs: list[str] = []
    for command in commands:
        result = subprocess.run(
            command,
            cwd=str(frontend_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=600,
            check=False,
        )
        output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
        if output:
            combined_logs.append(output)
        if result.returncode == 0:
            continue
        compile_log = "\n\n".join(combined_logs).strip()
        return _extract_frontend_compile_error_paths(compile_log), (compile_log[-4000:] if compile_log else "frontend build failed")

    return [], None


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
        except (OSError, UnicodeDecodeError):
            continue
        if content.strip():
            hydrated[relative_path] = content
    return hydrated


def _has_balanced_delimiters(content: str) -> bool:
    stack: list[str] = []
    pairs = {"}": "{", "]": "[", ")": "("}
    opening = set(pairs.values())
    closing = set(pairs.keys())
    in_string: str | None = None
    in_line_comment = False
    in_block_comment = False
    escaped = False

    index = 0
    while index < len(content):
        char = content[index]
        next_char = content[index + 1] if index + 1 < len(content) else ""

        if in_line_comment:
            if char == "\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            if char == "*" and next_char == "/":
                in_block_comment = False
                index += 2
                continue
            index += 1
            continue

        if in_string is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
            index += 1
            continue

        if char == "/" and next_char == "/":
            in_line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            in_block_comment = True
            index += 2
            continue
        if char in {"'", '"', "`"}:
            in_string = char
            index += 1
            continue
        if char in opening:
            stack.append(char)
        elif char in closing:
            if not stack or stack[-1] != pairs[char]:
                return False
            stack.pop()
        index += 1

    return not stack and in_string is None and not in_block_comment


def _uses_unsupported_utility_classes(content: str) -> bool:
    class_names = re.findall(r'className\s*=\s*["\']([^"\']+)["\']', content or "")
    if not class_names:
        return False

    hits = 0
    for class_name in class_names:
        tokens = [token.strip() for token in class_name.split() if token.strip()]
        for token in tokens:
            if any(marker in token for marker in _UNSUPPORTED_UTILITY_CLASS_TOKENS):
                hits += 1
        if hits >= 3:
            return True
    return False


def _synthesize_support_runtime_files(
    generated_files: dict[str, str],
    profile: dict,
    required_files: list[str],
    *,
    overwrite_existing: bool = False,
) -> tuple[dict[str, str], list[str]]:
    synthesized = dict(generated_files)
    repaired_paths: list[str] = []

    for relative_path in required_files:
        content = str(synthesized.get(relative_path, "") or "")
        if relative_path != "frontend/src/services/api.ts" or not content.strip():
            continue

        normalized = content.replace(
            "PageParams & Record<string, unknown>",
            "PageParams | Record<string, unknown>",
        ).replace(
            "Record<string, unknown> & PageParams",
            "PageParams | Record<string, unknown>",
        ).replace(
            " as Record<string, unknown>",
            " as unknown as Record<string, unknown>",
        ).replace(
            "function qs(params: Record<string, string | number | boolean | undefined>): string {",
            "function qs(params?: Record<string, unknown>): string {",
        ).replace(
            "  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== '');",
            "  const entries = Object.entries(params ?? {}).filter(([, v]) => v !== undefined && v !== null && v !== '');",
        )
        request_import_patterns = [
            "import { request } from './request';",
            'import { request } from "./request";',
            "import request from './request';",
            'import request from "./request";',
        ]
        request_runtime = """const BASE_URL = '/api/v1';

type RequestOptions = RequestInit & {
  params?: Record<string, unknown>;
};

const buildQueryString = (params?: Record<string, unknown>) => {
  const entries = Object.entries(params ?? {}).filter(([, value]) => value !== undefined && value !== null && value !== '');
  if (!entries.length) return '';
  return '?' + entries.map(([key, value]) => `${key}=${encodeURIComponent(String(value))}`).join('&');
};

async function doRequest<T>(url: string, options: RequestOptions = {}): Promise<T> {
  const token = localStorage.getItem('token');
  const { params, headers, ...rest } = options;
  const response = await fetch(`${BASE_URL}${url}${buildQueryString(params)}`, {
    ...rest,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers ?? {}),
    },
  });
  if (!response.ok) {
    throw new Error(`请求失败: ${response.status}`);
  }
  return (await response.json()) as T;
}

const request = {
  get: <T>(url: string, options?: RequestOptions) => doRequest<T>(url, { ...(options ?? {}), method: 'GET' }),
  post: <T>(url: string, data?: unknown, options?: RequestOptions) =>
    doRequest<T>(url, { ...(options ?? {}), method: 'POST', body: data === undefined ? undefined : JSON.stringify(data) }),
  put: <T>(url: string, data?: unknown, options?: RequestOptions) =>
    doRequest<T>(url, { ...(options ?? {}), method: 'PUT', body: data === undefined ? undefined : JSON.stringify(data) }),
  delete: <T>(url: string, options?: RequestOptions) => doRequest<T>(url, { ...(options ?? {}), method: 'DELETE' }),
};
"""
        for pattern in request_import_patterns:
            if pattern in normalized:
                normalized = normalized.replace(pattern, request_runtime, 1)
                break
        if normalized != content:
            synthesized[relative_path] = normalized
            repaired_paths.append(relative_path)

    return synthesized, repaired_paths


def _dedupe_ant_icon_imports(content: str) -> str:
    pattern = re.compile(
        r"import\s*\{(?P<body>[\s\S]*?)\}\s*from\s*['\"]@ant-design/icons['\"];?",
        re.MULTILINE,
    )

    def _replace(match: re.Match[str]) -> str:
        parts = [part.strip() for part in match.group("body").replace("\n", " ").split(",")]
        deduped: list[str] = []
        seen: set[str] = set()
        for part in parts:
            if not part or part in seen:
                continue
            seen.add(part)
            deduped.append(part)
        return "import {\n  " + ", ".join(deduped) + "\n} from '@ant-design/icons';"

    return pattern.sub(_replace, content, count=1)


def _synthesize_module_compile_files(
    generated_files: dict[str, str],
    required_files: list[str],
    *,
    overwrite_existing: bool = False,
) -> tuple[dict[str, str], list[str]]:
    del overwrite_existing
    synthesized = dict(generated_files)
    repaired_paths: list[str] = []
    icon_replacements = {
        "RouteOutlined": "NodeIndexOutlined",
        "OutboxOutlined": "ExportOutlined",
        "SnowflakeOutlined": "CloudServerOutlined",
    }
    styles_block = """const styles = {
  legend: { display: 'flex', gap: 16, flexWrap: 'wrap' as const, marginBottom: 16 },
  legendItem: { display: 'flex', alignItems: 'center', gap: 8, color: '#475569' },
  legendColor: { width: 12, height: 12, borderRadius: 999 },
  slotGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 12 },
  slotCell: { color: '#fff', borderRadius: 12, padding: 12, minHeight: 84, boxShadow: '0 10px 25px rgba(15, 23, 42, 0.12)' },
};
"""

    for relative_path in required_files:
        if not relative_path.startswith("frontend/src/pages/") or (
            not relative_path.endswith("Page.tsx") and relative_path != "frontend/src/pages/Dashboard.tsx"
        ):
            continue
        content = str(synthesized.get(relative_path, "") or "")
        if not content.strip():
            continue

        normalized = content
        changed = False
        for invalid_icon, safe_icon in icon_replacements.items():
            if invalid_icon in normalized:
                normalized = re.sub(rf"\b{invalid_icon}\b", safe_icon, normalized)
                changed = True
        status_toggle_patterns = [
            (
                "status: item.status === 'active' ? 'inactive' : 'active'",
                "status: (item.status === 'active' ? 'inactive' : 'active') as RouteRecord['status']",
            ),
            (
                'status: item.status === "active" ? "inactive" : "active"',
                'status: (item.status === "active" ? "inactive" : "active") as RouteRecord["status"]',
            ),
        ]
        for source, target in status_toggle_patterns:
            if source in normalized:
                normalized = normalized.replace(source, target)
                changed = True
        if 'align="right"' in normalized:
            normalized = normalized.replace('align="right"', 'align="end"')
            changed = True
        if "align='right'" in normalized:
            normalized = normalized.replace("align='right'", "align='end'")
            changed = True
        if "styles." in normalized and "const styles =" not in normalized:
            import_block = re.match(r"((?:import[^\n]*\n)+)", normalized)
            if import_block:
                normalized = normalized[: import_block.end()] + "\n" + styles_block + "\n" + normalized[import_block.end() :]
            else:
                normalized = styles_block + "\n" + normalized
            changed = True
        if changed:
            normalized = _dedupe_ant_icon_imports(normalized)
        if normalized != content:
            synthesized[relative_path] = normalized
            repaired_paths.append(relative_path)

    return synthesized, repaired_paths


def repair_invalid_support_files(
    generated_files: dict[str, str],
    profile: dict,
    required_files: list[str],
) -> tuple[dict[str, str], list[str]]:
    repaired = dict(generated_files)
    invalid_paths: list[str] = []

    for relative_path in (
        "frontend/src/services/api.ts",
        "frontend/src/types/constants.ts",
        "frontend/src/types/models.ts",
    ):
        if relative_path not in required_files:
            continue
        content = str(repaired.get(relative_path, "") or "")
        if content.strip() and _has_balanced_delimiters(content):
            continue
        invalid_paths.append(relative_path)

    return repaired, invalid_paths


def repair_invalid_core_files(
    app_root: str,
    generated_files: dict[str, str],
    profile: dict,
) -> tuple[dict[str, str], list[str]]:
    repaired = dict(generated_files)
    invalid_paths: list[str] = []

    allowed_page_imports = {
        "Login",
        "Dashboard",
        *[
            f"{_camel_name(module.get('route', module['key']))}Page"
            for module in profile.get("modules", [])
        ],
    }

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

    def _has_component_export(content: str, component_name: str) -> bool:
        return _contains_any(
            content,
            [
                f"export default function {component_name}",
                f"function {component_name}(",
                f"const {component_name}",
            ],
        )

    validators = {
        "frontend/src/App.tsx": lambda content: (
            bool(content.strip())
            and "模块开发中" not in content
            and "BrowserRouter" not in content
            and _has_balanced_delimiters(content)
            and not _uses_unsupported_utility_classes(content)
            and not _references_unknown_page_import(content)
            and not _has_duplicate_page_imports_or_routes(content)
            and _has_component_export(content, "App")
        ),
        "frontend/src/pages/Dashboard.tsx": lambda content: (
            bool(content.strip())
            and "模块开发中" not in content
            and _has_balanced_delimiters(content)
            and not _uses_unsupported_utility_classes(content)
            and _has_component_export(content, "Dashboard")
        ),
        "frontend/src/pages/Login.tsx": lambda content: (
            bool(content.strip())
            and "模块开发中" not in content
            and _has_balanced_delimiters(content)
            and not _uses_unsupported_utility_classes(content)
            and _has_component_export(content, "Login")
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
        is_valid = (
            bool(content.strip())
            and "模块开发中" not in content
            and not _uses_unsupported_utility_classes(content)
        )
        if is_valid:
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
    if "frontend/src/App.tsx" in invalid_paths:
        hints.append("App.tsx 需要输出完整可运行组件，不能留空，也不要保留“模块开发中”占位文本。")
        hints.append("App.tsx 只能引用当前批次真实存在的页面组件，避免导入不存在页面或重复声明同一路由。")
        hints.append("`frontend/src/main.tsx` 已负责挂载路由容器，`App.tsx` 不要再次渲染 `BrowserRouter`。")
        hints.append("不要输出依赖 Tailwind utility class 的页面骨架；若未同时生成完整样式配置，请改用当前工程可直接运行的组件和样式。")
    if "frontend/src/pages/Dashboard.tsx" in invalid_paths:
        hints.append("Dashboard.tsx 需要输出完整可运行组件，不能留空，也不要保留“模块开发中”占位文本。")
        hints.append("Dashboard.tsx 中的指标、表格和摘要请优先读取 `APP_PROFILE` 提供的任务数据，不要硬编码通用 demo 数组。")
    if "frontend/src/pages/Login.tsx" in invalid_paths:
        hints.append("Login.tsx 需要输出完整可运行组件，不能留空，也不要保留“模块开发中”占位文本。")
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
        hints.append(f"{relative_path} 需要输出 {title} 的完整可运行页面组件，不能留空，也不要保留“模块开发中”占位文本。")
        if route:
            hints.append(f"{relative_path} 应与路由 {route} 对应，避免输出与当前模块无关的页面内容。")
        hints.append(f"{relative_path} 请优先读取 `APP_PROFILE` 中的字段、样例记录和指标数据，避免硬编码通用后台示例。")
        hints.append(f"{relative_path} 不要只写 Tailwind utility class；如果没有完整样式配置，请改用当前工程可直接运行的组件和样式。")
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
                            "fallback_to_template": False,
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
                            "fallback_to_template": False,
                                "error": "files payload missing",
                            }
                        )
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
        generated_files, repaired_invalid_core_paths = _synthesize_structured_core_files(
            generated_files,
            profile,
            invalid_core_paths,
            overwrite_existing=True,
        )
        if repaired_invalid_core_paths:
            repaired_core_paths = sorted(set([*repaired_core_paths, *repaired_invalid_core_paths]))
            generated_files, invalid_core_paths = repair_invalid_core_files(app_root, generated_files, profile)
            batch_reports.append(
                {
                    "batch": "core_structural_fallback",
                    "attempt": 1,
                    "required_files": list(repaired_invalid_core_paths),
                    "generated_paths": sorted(repaired_invalid_core_paths),
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
                            "fallback_to_template": False,
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
                            "fallback_to_template": False,
                            "error": "files payload missing",
                        }
                    )
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
        invalid_module_previews = {
            relative_path: _preview_generated_content(generated_files.get(relative_path, ""))
            for relative_path in invalid_module_paths
        }
        return _build_codegen_report(
            repaired_core_paths=sorted(repaired_core_paths),
            repaired_module_paths=sorted(repaired_module_paths),
            repaired_support_paths=sorted(repaired_support_paths),
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
            apply_error=apply_error,
        ), f"App code generation failed: {apply_error}"

    sync_frontend_dependencies(os.path.join(app_root, "frontend"))
    invalid_compile_paths, compile_error = validate_generated_frontend_build(app_root)
    if "frontend/src/App.tsx" in invalid_compile_paths:
        generated_files, repaired_compile_core_paths = _synthesize_structured_core_files(
            generated_files,
            profile,
            ["frontend/src/App.tsx"],
            overwrite_existing=True,
        )
        if repaired_compile_core_paths:
            repaired_core_paths = sorted(set([*repaired_core_paths, *repaired_compile_core_paths]))
            applied, apply_error = apply_generated_code_bundle(
                app_root,
                generated_files,
                codegen_requirements["required_files"],
            )
            if not applied:
                return _build_codegen_report(
                    repaired_core_paths=sorted(repaired_core_paths),
                    repaired_module_paths=sorted(repaired_module_paths),
                    repaired_support_paths=sorted(repaired_support_paths),
                    apply_error=apply_error,
                ), f"App code generation failed: {apply_error}"
            sync_frontend_dependencies(os.path.join(app_root, "frontend"))
            invalid_compile_paths, compile_error = validate_generated_frontend_build(app_root)
            batch_reports.append(
                {
                    "batch": "core_compile_fallback",
                    "attempt": 1,
                    "required_files": ["frontend/src/App.tsx"],
                    "generated_paths": sorted(repaired_compile_core_paths),
                    "fallback_to_template": bool(invalid_compile_paths),
                    "error": (
                        "still invalid after compile fallback: " + ", ".join(invalid_compile_paths)
                        if invalid_compile_paths
                        else None
                    ),
                }
            )
    compile_invalid_support_paths = [
        path
        for path in invalid_compile_paths
        if path in {
            "frontend/src/services/api.ts",
            "frontend/src/types/constants.ts",
            "frontend/src/types/models.ts",
        }
    ]
    if compile_invalid_support_paths:
        generated_files, repaired_compile_support_paths = _synthesize_support_runtime_files(
            generated_files,
            profile,
            compile_invalid_support_paths,
            overwrite_existing=True,
        )
        if repaired_compile_support_paths:
            repaired_support_paths = sorted(set([*repaired_support_paths, *repaired_compile_support_paths]))
            applied, apply_error = apply_generated_code_bundle(
                app_root,
                generated_files,
                codegen_requirements["required_files"],
            )
            if not applied:
                return _build_codegen_report(
                    repaired_core_paths=sorted(repaired_core_paths),
                    repaired_module_paths=sorted(repaired_module_paths),
                    repaired_support_paths=sorted(repaired_support_paths),
                    apply_error=apply_error,
                ), f"App code generation failed: {apply_error}"
            sync_frontend_dependencies(os.path.join(app_root, "frontend"))
            invalid_compile_paths, compile_error = validate_generated_frontend_build(app_root)
            batch_reports.append(
                {
                    "batch": "support_compile_fallback",
                    "attempt": 1,
                    "required_files": list(repaired_compile_support_paths),
                    "generated_paths": sorted(repaired_compile_support_paths),
                    "fallback_to_template": bool(invalid_compile_paths),
                    "error": (
                        "still invalid after compile fallback: " + ", ".join(invalid_compile_paths)
                        if invalid_compile_paths
                        else None
                    ),
                }
            )
    compile_invalid_module_paths = [
        path
        for path in invalid_compile_paths
        if path.startswith("frontend/src/pages/")
        and path != "frontend/src/pages/Login.tsx"
    ]
    if compile_invalid_module_paths:
        generated_files, repaired_compile_module_paths = _synthesize_module_compile_files(
            generated_files,
            compile_invalid_module_paths,
            overwrite_existing=True,
        )
        if repaired_compile_module_paths:
            repaired_module_paths = sorted(set([*repaired_module_paths, *repaired_compile_module_paths]))
            applied, apply_error = apply_generated_code_bundle(
                app_root,
                generated_files,
                codegen_requirements["required_files"],
            )
            if not applied:
                return _build_codegen_report(
                    repaired_core_paths=sorted(repaired_core_paths),
                    repaired_module_paths=sorted(repaired_module_paths),
                    repaired_support_paths=sorted(repaired_support_paths),
                    apply_error=apply_error,
                ), f"App code generation failed: {apply_error}"
            sync_frontend_dependencies(os.path.join(app_root, "frontend"))
            invalid_compile_paths, compile_error = validate_generated_frontend_build(app_root)
            batch_reports.append(
                {
                    "batch": "module_compile_fallback",
                    "attempt": 1,
                    "required_files": list(repaired_compile_module_paths),
                    "generated_paths": sorted(repaired_compile_module_paths),
                    "fallback_to_template": bool(invalid_compile_paths),
                    "error": (
                        "still invalid after compile fallback: " + ", ".join(invalid_compile_paths)
                        if invalid_compile_paths
                        else None
                    ),
                }
            )
    if invalid_compile_paths:
        compile_error_previews = {
            relative_path: _preview_generated_content(generated_files.get(relative_path, ""))
            for relative_path in invalid_compile_paths
        }
        return _build_codegen_report(
            repaired_core_paths=sorted(repaired_core_paths),
            repaired_module_paths=sorted(repaired_module_paths),
            repaired_support_paths=sorted(repaired_support_paths),
            invalid_compile_paths=invalid_compile_paths,
            invalid_compile_previews=compile_error_previews,
            compile_error=compile_error,
        ), (
            "App code generation failed: invalid frontend build artifacts: "
            + ", ".join(invalid_compile_paths)
        )

    return _build_codegen_report(
        repaired_core_paths=sorted(repaired_core_paths),
        repaired_module_paths=sorted(repaired_module_paths),
        repaired_support_paths=sorted(repaired_support_paths),
    ), None
