from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unicodedata
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
    segments: list[str] = []
    ascii_buffer: list[str] = []
    for char in str(value or ""):
        if char.isascii() and char.isalnum():
            ascii_buffer.append(char)
            continue
        if ascii_buffer:
            segments.append("".join(ascii_buffer))
            ascii_buffer = []
        if unicodedata.category(char)[:1] in {"L", "N"}:
            segments.append(f"U{ord(char):X}")
    if ascii_buffer:
        segments.append("".join(ascii_buffer))
    cleaned = "".join(
        segment if segment.startswith("U") else segment[:1].upper() + segment[1:]
        for segment in segments
        if segment
    )
    if not cleaned:
        return "Module"
    if cleaned[0].isdigit():
        return f"Module{cleaned}"
    return cleaned


def _render_frontend_package_json() -> str:
    return json.dumps(
        {
            "name": "generated-app-frontend",
            "private": True,
            "version": "1.0.0",
            "type": "module",
            "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview"},
            "dependencies": {
                "react": "^18.3.0",
                "react-dom": "^18.3.0",
                "react-router-dom": "^6.22.0",
            },
            "devDependencies": {
                "@types/react": "^18.3.0",
                "@types/react-dom": "^18.3.0",
                "@vitejs/plugin-react": "^4.2.0",
                "typescript": "^5.4.0",
                "vite": "^5.4.0",
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def _render_frontend_index_html(profile: dict) -> str:
    product_name = str(profile.get("product_name") or "生成软件").strip()
    version = str(profile.get("version") or "").strip()
    title = f"{product_name} {version}".strip()
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '  <meta charset="UTF-8" />\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n'
        f"  <title>{title}</title>\n"
        "</head>\n"
        "<body>\n"
        '  <div id="root"></div>\n'
        '  <script type="module" src="/src/main.tsx"></script>\n'
        "</body>\n"
        "</html>\n"
    )


def _render_frontend_tsconfig() -> str:
    return """{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false
  },
  "include": ["src"]
}
"""


def _render_frontend_vite_config() -> str:
    return """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
});
"""


def _render_frontend_main_tsx() -> str:
    return """import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
"""


def _render_backend_requirements() -> str:
    return "fastapi>=0.100\nuvicorn[standard]>=0.20\n"


def _bootstrap_task_scaffold(frontend_root: str, backend_root: str, profile: dict) -> None:
    if os.path.exists(frontend_root):
        shutil.rmtree(frontend_root)
    if os.path.exists(backend_root):
        shutil.rmtree(backend_root)

    _write_text(os.path.join(frontend_root, "package.json"), _render_frontend_package_json())
    _write_text(os.path.join(frontend_root, "index.html"), _render_frontend_index_html(profile))
    _write_text(os.path.join(frontend_root, "tsconfig.json"), _render_frontend_tsconfig())
    _write_text(os.path.join(frontend_root, "vite.config.ts"), _render_frontend_vite_config())
    _write_text(os.path.join(frontend_root, "src", "main.tsx"), _render_frontend_main_tsx())

    _write_text(os.path.join(backend_root, "requirements.txt"), _render_backend_requirements())
    _write_text(os.path.join(backend_root, "app", "__init__.py"), "")
    _write_text(os.path.join(backend_root, "tests", "__init__.py"), "")


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
    import_lines = [
        "import type { ReactNode } from 'react';",
        "import { useEffect, useState } from 'react';",
        "import { Navigate, Route, Routes, useLocation } from 'react-router-dom';",
        "import Login from './pages/Login';",
        "import Dashboard from './pages/Dashboard';",
    ]
    for page in module_pages:
        component_name = page.get("component_name")
        if component_name:
            import_lines.append(f"import {component_name} from './pages/{component_name}';")

    protected_routes = [
        '      <Route path="/dashboard" element={<ProtectedView loggedIn={loggedIn}><Dashboard /></ProtectedView>} />'
    ]
    for page in module_pages:
        component_name = page.get("component_name")
        route = str(page.get("route") or "").strip()
        if component_name and route:
            protected_routes.append(
                '      <Route path="'
                + route
                + '" element={<ProtectedView loggedIn={loggedIn}><'
                + component_name
                + ' /></ProtectedView>} />'
            )

    fallback_dashboard_route = "/dashboard"
    return "\n".join(
        [
            *import_lines,
            "",
            "const AUTH_KEY = 'ipright_demo_auth';",
            "",
            "function readLoggedIn(): boolean {",
            "  if (typeof window === 'undefined') {",
            "    return false;",
            "  }",
            "  const storage = window.localStorage;",
            "  return Boolean(storage.getItem(AUTH_KEY) || storage.getItem('token') || storage.getItem('user'));",
            "}",
            "",
            "function ProtectedView({ loggedIn, children }: { loggedIn: boolean; children: ReactNode }) {",
            "  if (!loggedIn) {",
            "    return <Navigate to=\"/login\" replace />;",
            "  }",
            "  return <>{children}</>;",
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


def _render_structured_login_tsx(profile: dict) -> str:
    product_name = json.dumps(str(profile.get("product_name") or "业务平台"), ensure_ascii=False)
    return "\n".join(
        [
            "const AUTH_KEY = 'ipright_demo_auth';",
            "",
            "function persistDemoLogin(): void {",
            "  if (typeof window === 'undefined') return;",
            "  try {",
            "    window.localStorage.setItem(AUTH_KEY, 'true');",
            "    window.localStorage.setItem('token', 'demo-token');",
            "    window.localStorage.setItem('user', '管理员');",
            "  } catch {",
            "  }",
            "}",
            "",
            "function redirectToDashboard(): void {",
            "  if (typeof window === 'undefined') return;",
            "  window.location.href = '/dashboard';",
            "}",
            "",
            "export default function Login() {",
            "  const handleLogin = () => {",
            "    persistDemoLogin();",
            "    redirectToDashboard();",
            "  };",
            "",
            "  return (",
            "    <div>",
            f"      <h1>{product_name}</h1>",
            "      <p>已切换为结构化登录页，可直接进入系统继续验收应用功能。</p>",
            "      <button type=\"button\" onClick={handleLogin}>",
            "        进入系统",
            "      </button>",
            "    </div>",
            "  );",
            "}",
            "",
        ]
    )


def _render_structured_dashboard_tsx(profile: dict) -> str:
    product_name = json.dumps(str(profile.get("product_name") or "业务平台"), ensure_ascii=False)
    module_pages = _build_route_shell_module_pages(build_codegen_requirements(profile).get("module_pages", []))
    link_lines = []
    for page in module_pages:
        route = json.dumps(str(page.get("route") or "/dashboard"), ensure_ascii=False)
        title = json.dumps(str(page.get("title") or page.get("component_name") or "业务页面"), ensure_ascii=False)
        link_lines.append(f"        <li><a href={route}>{title}</a></li>")
    if not link_lines:
        link_lines.append("        <li>当前暂无业务模块，已保留安全首页。</li>")
    return "\n".join(
        [
            "export default function Dashboard() {",
            "  return (",
            "    <div>",
            f"      <h1>{product_name}</h1>",
            "      <p>已切换为结构化首页，可继续访问各个业务模块。</p>",
            "      <ul>",
            *link_lines,
            "      </ul>",
            "    </div>",
            "  );",
            "}",
            "",
        ]
    )


def _render_terminal_safe_app_tsx(profile: dict) -> str:
    module_pages = _build_route_shell_module_pages(build_codegen_requirements(profile).get("module_pages", []))
    import_lines = [
        "import Login from './pages/Login';",
        "import Dashboard from './pages/Dashboard';",
    ]
    route_lines = [
        "    if (path === '/dashboard') return <Dashboard />;",
    ]
    for page in module_pages:
        component_name = str(page.get("component_name") or "").strip()
        route = str(page.get("route") or "").strip()
        if not component_name or not route:
            continue
        import_lines.append(f"import {component_name} from './pages/{component_name}';")
        route_lines.append(f"    if (path === {json.dumps(route, ensure_ascii=False)}) return <{component_name} />;")
    return "\n".join(
        [
            *import_lines,
            "",
            "const AUTH_KEY = 'ipright_demo_auth';",
            "",
            "function bootstrapTokenFromUrl(): void {",
            "  if (typeof window === 'undefined') return;",
            "  try {",
            "    const url = new URL(window.location.href);",
            "    const hash = url.hash.startsWith('#') ? url.hash.slice(1) : url.hash;",
            "    const hashParams = new URLSearchParams(hash);",
            "    const token = url.searchParams.get('token') || url.searchParams.get('api_token') || hashParams.get('token') || hashParams.get('api_token');",
            "    if (!token) return;",
            "    window.localStorage.setItem('token', token);",
            "    window.localStorage.setItem(AUTH_KEY, 'true');",
            "    url.searchParams.delete('token');",
            "    url.searchParams.delete('api_token');",
            "    const cleanHash = new URLSearchParams(hash);",
            "    cleanHash.delete('token');",
            "    cleanHash.delete('api_token');",
            "    const nextHash = cleanHash.toString();",
            "    const cleanUrl = `${url.pathname}${url.search}${nextHash ? `#${nextHash}` : ''}`;",
            "    window.history.replaceState({}, '', cleanUrl);",
            "  } catch {",
            "  }",
            "}",
            "",
            "function getCurrentPath(): string {",
            "  if (typeof window === 'undefined') return '/';",
            "  const path = window.location.pathname || '/';",
            "  if (!path) return '/';",
            "  if (path.length > 1 && path.endsWith('/')) return path.slice(0, -1);",
            "  return path;",
            "}",
            "",
            "function renderCurrentPage(path: string) {",
            "  if (path === '/' || path === '/login') return <Login />;",
            "  if (path === '/index.html') return <Dashboard />;",
            *route_lines,
            "  return <Dashboard />;",
            "}",
            "",
            "export default function App() {",
            "  bootstrapTokenFromUrl();",
            "  const path = getCurrentPath();",
            "  return renderCurrentPage(path);",
            "}",
            "",
        ]
    )


def _render_terminal_safe_request_runtime() -> str:
    return "\n".join(
        [
            "export const TOKEN_STORAGE_KEY = 'ipright_api_token';",
            "export const BASE_URL = '/api/v1';",
            "",
            "export type QueryValue = string | number | boolean | null | undefined;",
            "export type QueryParams = Record<string, QueryValue>;",
            "export type RequestOptions = {",
            "  method?: string;",
            "  params?: QueryParams;",
            "  data?: unknown;",
            "  body?: unknown;",
            "  headers?: Record<string, string>;",
            "};",
            "",
            "export type ApiResponse = {",
            "  success: boolean;",
            "  data?: unknown;",
            "  message?: string;",
            "  code?: string;",
            "  [key: string]: unknown;",
            "};",
            "",
            "function buildUrl(url: string, params?: QueryParams): string {",
            "  const search = new URLSearchParams();",
            "  const entries = Object.entries(params || {});",
            "  for (const [key, value] of entries) {",
            "    if (value === undefined || value === null || value === '') continue;",
            "    search.append(key, String(value));",
            "  }",
            "  const query = search.toString();",
            "  return query ? `${BASE_URL}${url}?${query}` : `${BASE_URL}${url}`;",
            "}",
            "",
            "function normalizeBody(value: unknown): string | undefined {",
            "  if (value === undefined || value === null) return undefined;",
            "  if (typeof value === 'string') return value;",
            "  return JSON.stringify(value);",
            "}",
            "",
            "export function getApiToken(): string {",
            "  if (typeof window === 'undefined') return '';",
            "  try {",
            "    return window.localStorage.getItem(TOKEN_STORAGE_KEY) || window.localStorage.getItem('token') || '';",
            "  } catch {",
            "    return '';",
            "  }",
            "}",
            "",
            "export function setApiToken(token: string): void {",
            "  if (typeof window === 'undefined') return;",
            "  try {",
            "    if (token) {",
            "      window.localStorage.setItem(TOKEN_STORAGE_KEY, token);",
            "      window.localStorage.setItem('token', token);",
            "    } else {",
            "      window.localStorage.removeItem(TOKEN_STORAGE_KEY);",
            "      window.localStorage.removeItem('token');",
            "    }",
            "  } catch {",
            "  }",
            "}",
            "",
            "export function withTokenQuery(url: string): string {",
            "  const token = getApiToken();",
            "  if (!token) return url;",
            "  const separator = url.includes('?') ? '&' : '?';",
            "  return `${url}${separator}token=${encodeURIComponent(token)}`;",
            "}",
            "",
            "export function withAuthorizedUrl(url: string): string {",
            "  return withTokenQuery(url);",
            "}",
            "",
            "async function requestCore(url: string, options: RequestOptions = {}): Promise<ApiResponse> {",
            "  try {",
            "    const token = getApiToken();",
            "    const response = await fetch(buildUrl(url, options.params), {",
            "      method: options.method || 'GET',",
            "      headers: {",
            "        'Content-Type': 'application/json',",
            "        ...(token ? { Authorization: `Bearer ${token}` } : {}),",
            "        ...(options.headers || {}),",
            "      },",
            "      ...(options.body !== undefined ? { body: normalizeBody(options.body) } : {}),",
            "      ...(options.body === undefined && options.data !== undefined ? { body: normalizeBody(options.data) } : {}),",
            "    });",
            "    const text = await response.text();",
            "    let parsed: unknown = undefined;",
            "    try {",
            "      parsed = text ? JSON.parse(text) : undefined;",
            "    } catch {",
            "      parsed = text || undefined;",
            "    }",
            "    if (!response.ok) {",
            "      return {",
            "        success: false,",
            "        data: parsed,",
            "        message: typeof parsed === 'string' ? parsed : `请求失败: ${response.status}`,",
            "        code: String(response.status),",
            "      };",
            "    }",
            "    return { success: true, data: parsed };",
            "  } catch (error) {",
            "    return { success: false, message: String(error) };",
            "  }",
            "}",
            "",
            "export const request: any = function(url: string, options?: RequestOptions) {",
            "  return requestCore(url, options || {});",
            "};",
            "request.get = function(url: string, params?: QueryParams, options?: RequestOptions) {",
            "  return requestCore(url, { ...(options || {}), method: 'GET', params });",
            "};",
            "request.post = function(url: string, data?: unknown, options?: RequestOptions) {",
            "  return requestCore(url, { ...(options || {}), method: 'POST', data });",
            "};",
            "request.put = function(url: string, data?: unknown, options?: RequestOptions) {",
            "  return requestCore(url, { ...(options || {}), method: 'PUT', data });",
            "};",
            "request.delete = function(url: string, params?: QueryParams, options?: RequestOptions) {",
            "  return requestCore(url, { ...(options || {}), method: 'DELETE', params });",
            "};",
            "request.remove = request.delete;",
            "",
            "export const get = request.get;",
            "export const post = request.post;",
            "export const put = request.put;",
            "export const del = request.delete;",
            "export const remove = request.remove;",
            "",
            "export const client = {",
            "  get,",
            "  post,",
            "  put,",
            "  delete: del,",
            "  request,",
            "  interceptors: {",
            "    request: { use: () => undefined },",
            "    response: { use: () => undefined },",
            "  },",
            "};",
            "",
            "export function login(payload?: Record<string, unknown>) {",
            "  return post('/auth/login', payload);",
            "}",
            "",
            "export function getTaskBundleDownload(taskId: string): string {",
            "  return `/api/v1/tasks/${taskId}/bundle/download`;",
            "}",
            "",
            "export function getTaskStreamUrl(taskId: string): string {",
            "  return withTokenQuery(`/api/v1/tasks/${taskId}/stream`);",
            "}",
            "",
            "export const api = { get, post, put, delete: del, request, client, login };",
            "export default api;",
            "",
        ]
    )


def _terminal_safe_frontend_paths(profile: dict) -> set[str]:
    paths = {
        "frontend/src/App.tsx",
        "frontend/src/pages/Login.tsx",
        "frontend/src/pages/Dashboard.tsx",
        "frontend/src/services/api.ts",
        "frontend/src/types/constants.ts",
        "frontend/src/types/models.ts",
    }
    codegen_requirements = build_codegen_requirements(profile)
    for module_page in codegen_requirements.get("module_pages", []):
        relative_path = str(module_page.get("file_path") or "").strip()
        if relative_path:
            paths.add(relative_path)
    return paths


def _render_terminal_safe_api_file() -> str:
    return _render_terminal_safe_request_runtime()


def _build_terminal_safe_frontend_bundle(profile: dict) -> dict[str, str]:
    codegen_requirements = build_codegen_requirements(profile)
    terminal_bundle = {
        "frontend/src/App.tsx": _render_terminal_safe_app_tsx(profile),
        "frontend/src/pages/Login.tsx": _render_structured_login_tsx(profile),
        "frontend/src/pages/Dashboard.tsx": _render_structured_dashboard_tsx(profile),
        "frontend/src/services/api.ts": _render_terminal_safe_api_file(),
        "frontend/src/types/constants.ts": _render_terminal_safe_constants_file(profile),
        "frontend/src/types/models.ts": _render_terminal_safe_models_file(),
    }
    for module_page in codegen_requirements.get("module_pages", []):
        relative_path = str(module_page.get("file_path") or "").strip()
        if relative_path:
            terminal_bundle[relative_path] = _render_terminal_safe_module_page(relative_path, profile)
    return terminal_bundle


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
        if not (overwrite_existing or not content.strip()):
            continue
        if relative_path == "frontend/src/App.tsx":
            synthesized[relative_path] = _render_structured_app_tsx(profile, synthesized)
            repaired_paths.append(relative_path)
            continue
        if relative_path == "frontend/src/pages/Login.tsx":
            synthesized[relative_path] = _render_structured_login_tsx(profile)
            repaired_paths.append(relative_path)
            continue
        if relative_path == "frontend/src/pages/Dashboard.tsx":
            if overwrite_existing:
                synthesized[relative_path] = _render_structured_dashboard_tsx(profile)
                repaired_paths.append(relative_path)
                continue
            normalized = content
            changed = False
            for invalid_icon, safe_icon in {
                "SnowflakeOutlined": "CloudServerOutlined",
            }.items():
                if invalid_icon in normalized:
                    normalized = re.sub(rf"\b{invalid_icon}\b", safe_icon, normalized)
                    changed = True
            if changed:
                synthesized[relative_path] = _dedupe_ant_icon_imports(normalized)
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

    os.makedirs(app_root, exist_ok=True)
    _bootstrap_task_scaffold(frontend_dst, backend_dst, profile)
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


def _normalize_overescaped_jsx_attributes(relative_path: str, content: str) -> str:
    if not relative_path.endswith((".tsx", ".jsx")):
        return content
    if '\\"' not in content:
        return content

    overescaped_attr_hits = len(re.findall(r'=\\"[^"\n]*\\"', content))
    if overescaped_attr_hits < 2:
        return content
    return content.replace('\\"', '"')


def _normalize_svg_component_props(content: str) -> str:
    if "React.FC = () => (" not in content or "<svg " not in content:
        return content
    updated = re.sub(
        r"const\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*React\.FC\s*=\s*\(\)\s*=>\s*\(",
        r"const \1: React.FC<React.SVGProps<SVGSVGElement>> = (props) => (",
        content,
    )
    if updated == content:
        return content
    return updated.replace("<svg ", "<svg {...props} ", 1)


def _escape_jsx_text_symbols(relative_path: str, content: str) -> str:
    if not relative_path.endswith((".tsx", ".jsx")):
        return content

    pattern = re.compile(
        r"(?P<open><(?P<tag>[A-Za-z][A-Za-z0-9._-]*)(?:\s[^>{}]*)?>)"
        r"(?P<text>(?:(?!</?[A-Za-z]).)*?[<>](?:(?!</?[A-Za-z]).)*?)"
        r"(?P<close></(?P=tag)>)"
    )

    def _replace(match: re.Match[str]) -> str:
        text = match.group("text")
        if "{" in text or "}" in text:
            return match.group(0)
        if "<" not in text and ">" not in text:
            return match.group(0)
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return f"{match.group('open')}{escaped}{match.group('close')}"

    return pattern.sub(_replace, content)


def _normalize_encoded_jsx_tag_close(relative_path: str, content: str) -> str:
    if not relative_path.endswith((".tsx", ".jsx")):
        return content
    return content.replace("}&gt;", "}>")


def _normalize_encoded_jsx_expression_entities(relative_path: str, content: str) -> str:
    if not relative_path.endswith((".tsx", ".jsx")):
        return content
    return (
        content.replace("=&gt;", "=>")
        .replace("&gt;=", ">=")
        .replace("&lt;=", "<=")
        .replace("&amp;&amp;", "&&")
    )


def _normalize_style_shorthand_literals(relative_path: str, content: str) -> str:
    if not relative_path.endswith((".tsx", ".jsx")):
        return content

    def _replace_flex(match: re.Match[str]) -> str:
        grow = match.group("grow")
        shrink = match.group("shrink")
        basis = match.group("basis")
        return f"{match.group('prefix')}flex: '{grow} {shrink} {basis}px',"

    content = re.sub(
        r"(?P<prefix>^|\s)flex:\s*(?P<grow>\d+(?:\.\d+)?)\s+(?P<shrink>\d+(?:\.\d+)?)\s+(?P<basis>\d+(?:\.\d+)?)\s*,",
        _replace_flex,
        content,
        flags=re.MULTILINE,
    )
    return content


def normalize_generated_frontend_files(
    generated_files: dict[str, str],
    preserve_paths: set[str] | None = None,
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    preserved = preserve_paths or set()
    for relative_path, content in generated_files.items():
        text = str(content)
        if relative_path in preserved:
            normalized[relative_path] = text
            continue
        text = _normalize_overescaped_jsx_attributes(relative_path, text)
        text = _normalize_encoded_jsx_tag_close(relative_path, text)
        text = _normalize_encoded_jsx_expression_entities(relative_path, text)
        text = _escape_jsx_text_symbols(relative_path, text)
        text = _normalize_style_shorthand_literals(relative_path, text)
        text = _normalize_svg_component_props(text)
        normalized[relative_path] = text
    return normalized


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
    preserve_paths: set[str] | None = None,
) -> tuple[bool, str | None]:
    missing = [path for path in required_files if not generated_files.get(path)]
    if missing:
        return False, f"Missing generated files: {', '.join(missing[:8])}"

    preserved = preserve_paths or set()
    for relative_path in required_files:
        raw_content = str(generated_files.get(relative_path, ""))
        content = raw_content if relative_path in preserved else _strip_code_fence(raw_content)
        if not content:
            return False, f"Generated file is empty: {relative_path}"
        absolute_path = os.path.join(app_root, relative_path)
        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        _write_text(absolute_path, content)

    return True, None


def _apply_normalized_generated_code_bundle(
    app_root: str,
    generated_files: dict[str, str],
    required_files: list[str],
    preserve_paths: set[str] | None = None,
) -> tuple[dict[str, str], bool, str | None]:
    normalized_files = normalize_generated_frontend_files(generated_files, preserve_paths=preserve_paths)
    applied, apply_error = apply_generated_code_bundle(
        app_root,
        normalized_files,
        required_files,
        preserve_paths=preserve_paths,
    )
    return normalized_files, applied, apply_error


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


def _render_safe_constants_file(profile: dict, *, extended_colors: bool) -> str:
    product_name = json.dumps(str(profile.get("product_name") or "业务分析平台"), ensure_ascii=False)
    version = json.dumps(str(profile.get("version") or "V1.0"), ensure_ascii=False)
    color_lines = [
        "export const COLORS = {",
        "  primary: '#1677ff',",
        "  success: '#52c41a',",
        "  warning: '#faad14',",
        "  error: '#ff4d4f',",
    ]
    if extended_colors:
        color_lines.extend(
            [
                "  info: '#1890ff',",
                "  text: '#334155',",
                "  muted: '#64748b',",
                "  background: '#f8fafc',",
                "  panel: '#ffffff',",
            ]
        )
    color_lines.append("} as const;")

    return "\n".join(
        [
            f"export const APP_NAME = {product_name};",
            f"export const APP_VERSION = {version};",
            "export const SYSTEM_NAME = APP_NAME;",
            "export const DEMO_USERNAME = 'admin';",
            "export const DEMO_PASSWORD = 'admin123';",
            "",
            *color_lines,
            "export const THEME_COLORS = COLORS;",
            "",
            "export const DataSourceType = { DATABASE: 'database', API: 'api', FILE: 'file', EXCEL: 'excel', CSV: 'csv' } as const;",
            "export type DataSourceType = (typeof DataSourceType)[keyof typeof DataSourceType];",
            "export const CleanRuleType = { DEDUPLICATE: 'deduplicate', FILL_MISSING: 'fill_missing', FORMAT: 'format', FILTER: 'filter' } as const;",
            "export type CleanRuleType = (typeof CleanRuleType)[keyof typeof CleanRuleType];",
            "export const StatsModelType = { SUM: 'sum', AVERAGE: 'average', TREND: 'trend', COMPARISON: 'comparison' } as const;",
            "export type StatsModelType = (typeof StatsModelType)[keyof typeof StatsModelType];",
            "export const ChartType = { LINE: 'line', BAR: 'bar', PIE: 'pie', AREA: 'area', TABLE: 'table' } as const;",
            "export type ChartType = (typeof ChartType)[keyof typeof ChartType];",
            "export const UserRole = { ADMIN: 'admin', ANALYST: 'analyst', OPERATOR: 'operator', VIEWER: 'viewer' } as const;",
            "export type UserRole = (typeof UserRole)[keyof typeof UserRole];",
            "export const ReportStatus = { DRAFT: 'draft', GENERATED: 'generated', FAILED: 'failed' } as const;",
            "export type ReportStatus = (typeof ReportStatus)[keyof typeof ReportStatus];",
            "export const AnalysisStatus = { PENDING: 'pending', RUNNING: 'running', COMPLETED: 'completed', FAILED: 'failed' } as const;",
            "export type AnalysisStatus = (typeof AnalysisStatus)[keyof typeof AnalysisStatus];",
            "export const ExportFormat = { PDF: 'PDF', EXCEL: 'Excel', IMAGE: '图片' } as const;",
            "export type ExportFormat = (typeof ExportFormat)[keyof typeof ExportFormat];",
            "",
            "export const DATA_SOURCE_TYPE_OPTIONS: DataSourceType[] = ['database', 'api', 'file', 'excel', 'csv'];",
            "export const CLEAN_RULE_TYPE_OPTIONS: CleanRuleType[] = ['deduplicate', 'fill_missing', 'format', 'filter'];",
            "export const STATS_MODEL_TYPE_OPTIONS: StatsModelType[] = ['sum', 'average', 'trend', 'comparison'];",
            "export const CHART_TYPE_OPTIONS: ChartType[] = ['line', 'bar', 'pie', 'area', 'table'];",
            "export const USER_ROLE_OPTIONS: UserRole[] = ['admin', 'analyst', 'operator', 'viewer'];",
            "export const REPORT_STATUS_OPTIONS: ReportStatus[] = ['draft', 'generated', 'failed'];",
            "export const ANALYSIS_STATUS_OPTIONS: AnalysisStatus[] = ['pending', 'running', 'completed', 'failed'];",
            "export const EXPORT_FORMAT_OPTIONS: ExportFormat[] = ['PDF', 'Excel', '图片'];",
            "",
            "const constants = {",
            "  APP_NAME,",
            "  APP_VERSION,",
            "  SYSTEM_NAME,",
            "  DEMO_USERNAME,",
            "  DEMO_PASSWORD,",
            "  COLORS,",
            "  THEME_COLORS,",
            "  DataSourceType,",
            "  CleanRuleType,",
            "  StatsModelType,",
            "  ChartType,",
            "  UserRole,",
            "  ReportStatus,",
            "  AnalysisStatus,",
            "  ExportFormat,",
            "  DATA_SOURCE_TYPE_OPTIONS,",
            "  CLEAN_RULE_TYPE_OPTIONS,",
            "  STATS_MODEL_TYPE_OPTIONS,",
            "  CHART_TYPE_OPTIONS,",
            "  USER_ROLE_OPTIONS,",
            "  REPORT_STATUS_OPTIONS,",
            "  ANALYSIS_STATUS_OPTIONS,",
            "  EXPORT_FORMAT_OPTIONS,",
            "};",
            "",
            "export default constants;",
            "",
        ]
    )


def _render_compile_safe_constants_file(profile: dict) -> str:
    return _render_safe_constants_file(profile, extended_colors=True)


def _render_terminal_safe_models_file() -> str:
    return "\n".join(
        [
            "export interface ApiResponse<T = unknown> {",
            "  success: boolean;",
            "  data?: T;",
            "  message?: string;",
            "  code?: string;",
            "  [key: string]: unknown;",
            "}",
            "",
            "export interface PageResult<T = unknown> {",
            "  items: T[];",
            "  total: number;",
            "  page?: number;",
            "  pageSize?: number;",
            "}",
            "",
            "export interface BaseEntity {",
            "  id: string;",
            "  name?: string;",
            "  status?: string;",
            "  createdAt?: string;",
            "  updatedAt?: string;",
            "  [key: string]: unknown;",
            "}",
            "",
            "export interface User extends BaseEntity {",
            "  username?: string;",
            "  role?: string;",
            "  email?: string;",
            "}",
            "",
            "export type PageParams = Record<string, unknown>;",
            "",
        ]
    )


def _render_compile_safe_models_file() -> str:
    return "\n".join(
        [
            "export interface BaseEntity {",
            "  id: string;",
            "  name?: string;",
            "  status?: string;",
            "  createdAt?: string;",
            "  updatedAt?: string;",
            "  [key: string]: unknown;",
            "}",
            "",
            "export interface User extends BaseEntity {",
            "  username?: string;",
            "  role?: string;",
            "  email?: string;",
            "}",
            "",
            "export interface Supplier extends BaseEntity {",
            "  contact?: string;",
            "  phone?: string;",
            "}",
            "",
            "export interface DataSource extends BaseEntity {",
            "  type?: string;",
            "  description?: string;",
            "}",
            "",
            "export interface Report extends BaseEntity {",
            "  status?: string;",
            "  exportFormats?: string[];",
            "}",
            "",
            "export interface AnalysisTask extends BaseEntity {",
            "  status?: string;",
            "  result?: string;",
            "}",
            "",
            "export interface ReportTemplate extends BaseEntity {",
            "  exportFormats?: string[];",
            "}",
            "",
            "export interface DashboardStats extends BaseEntity {",
            "  total?: number;",
            "  success?: number;",
            "  pending?: number;",
            "}",
            "",
            "export type PageParams = Record<string, unknown>;",
            "",
        ]
    )


def _render_terminal_safe_constants_file(profile: dict) -> str:
    return _render_safe_constants_file(profile, extended_colors=True)


def _render_terminal_safe_api_file() -> str:
    return _render_terminal_safe_request_runtime()


def _render_terminal_safe_module_page(relative_path: str, profile: dict) -> str:
    page_meta = _find_module_page_metadata(profile, relative_path)
    component_name = _camel_name(Path(relative_path).stem)
    title = json.dumps(str(page_meta.get("title") or Path(relative_path).stem.replace("Page", "")).strip() or "业务页面", ensure_ascii=False)
    description = json.dumps(
        str(page_meta.get("description") or "当前页面已切换为终端编译安全模式，仅保留基础信息展示。").strip(),
        ensure_ascii=False,
    )
    route = json.dumps(str(page_meta.get("route") or "/dashboard").strip() or "/dashboard", ensure_ascii=False)
    return "\n".join(
        [
            "import React from 'react';",
            "",
            f"export default function {component_name}() {{",
            "  return (",
            "    <div>",
            f"      <h2>{title}</h2>",
            f"      <p>{description}</p>",
            "      <p>当前页面已切换为终端编译安全模式</p>",
            f"      <p>{route}</p>",
            "    </div>",
            "  );",
            "}",
            "",
        ]
    )


def _apply_terminal_compile_fallback(
    generated_files: dict[str, str],
    profile: dict,
    invalid_paths: list[str],
) -> tuple[dict[str, str], list[str]]:
    synthesized = dict(generated_files)
    if not invalid_paths:
        return synthesized, []

    terminal_bundle = _build_terminal_safe_frontend_bundle(profile)
    for relative_path, content in terminal_bundle.items():
        synthesized[relative_path] = content

    return synthesized, sorted(terminal_bundle)


def _synthesize_support_runtime_files(
    generated_files: dict[str, str],
    profile: dict,
    required_files: list[str],
    *,
    overwrite_existing: bool = False,
    force_runtime_fallback: bool = False,
) -> tuple[dict[str, str], list[str]]:
    del overwrite_existing
    synthesized = dict(generated_files)
    repaired_paths: list[str] = []

    request_runtime = """export const TOKEN_STORAGE_KEY = 'ipright_api_token';
type RuntimeGlobals = typeof globalThis & {
  __IPRIGHT_API_BASE_URL__?: string;
  __IPRIGHT_API_TOKEN__?: string;
};
const runtimeGlobals = globalThis as RuntimeGlobals;
export const BASE_URL = runtimeGlobals.__IPRIGHT_API_BASE_URL__ || '/api/v1';

type QueryValue = string | number | boolean | null | undefined;
export type QueryParams = Record<string, QueryValue>;
export type RequestOptions = {
  method?: string;
  params?: QueryParams;
  data?: unknown;
  body?: unknown;
  headers?: Record<string, string>;
};

export interface ApiResponse<T = unknown> {
  success: boolean;
  data?: T;
  message?: string;
  code?: string;
  [key: string]: unknown;
}

function buildQueryString(params?: QueryParams): string {
  const entries = Object.entries(params ?? {}).filter(([, value]) => value !== undefined && value !== null && value !== '');
  if (!entries.length) return '';
  return '?' + entries.map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`).join('&');
}

export function getApiToken(): string {
  if (runtimeGlobals.__IPRIGHT_API_TOKEN__) return runtimeGlobals.__IPRIGHT_API_TOKEN__;
  if (typeof window !== 'undefined') {
    try {
      const fromStorage = window.localStorage?.getItem(TOKEN_STORAGE_KEY) || window.localStorage?.getItem('token');
      if (fromStorage) return fromStorage;
    } catch {
    }
  }
  return '';
}

export function setApiToken(token: string): void {
  runtimeGlobals.__IPRIGHT_API_TOKEN__ = token || undefined;
  if (typeof window === 'undefined') return;
  try {
    if (token) {
      window.localStorage?.setItem(TOKEN_STORAGE_KEY, token);
    } else {
      window.localStorage?.removeItem(TOKEN_STORAGE_KEY);
    }
  } catch {
  }
}

export function withTokenQuery(url: string): string {
  const token = getApiToken();
  if (!token) return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}token=${encodeURIComponent(token)}`;
}

export function withAuthorizedUrl(url: string): string {
  return withTokenQuery(url);
}

function normalizeBody(value: unknown): unknown {
  if (value === undefined || value === null) return undefined;
  if (typeof value === 'string') {
    return value;
  }
  return JSON.stringify(value);
}

async function requestCore<T = unknown>(url: string, options: RequestOptions = {}): Promise<ApiResponse<T>> {
  const { params, data, headers, body, method } = options;
  const token = getApiToken();
  const requestBody = body ?? normalizeBody(data);
  const response = await fetch(`${BASE_URL}${url}${buildQueryString(params)}`, {
    method: method || 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(headers ?? {}),
    },
    ...(requestBody === undefined ? {} : { body: requestBody as string }),
  });

  const text = await response.text();
  let parsed: unknown = undefined;
  try {
    parsed = text ? JSON.parse(text) : undefined;
  } catch {
    parsed = text || undefined;
  }

  if (parsed && typeof parsed === 'object' && ('success' in (parsed as Record<string, unknown>) || 'data' in (parsed as Record<string, unknown>) || 'code' in (parsed as Record<string, unknown>))) {
    return parsed as ApiResponse<T>;
  }
  if (!response.ok) {
    return {
      success: false,
      message: typeof parsed === 'string' ? parsed : `请求失败: ${response.status}`,
      code: String(response.status),
      data: parsed as T,
    };
  }
  return { success: true, data: parsed as T };
}

export const get = <T = unknown>(url: string, params?: QueryParams, options?: RequestOptions) => requestCore<T>(url, { ...(options ?? {}), method: 'GET', params });
export const post = <T = unknown>(url: string, data?: unknown, options?: RequestOptions) => requestCore<T>(url, { ...(options ?? {}), method: 'POST', data });
export const put = <T = unknown>(url: string, data?: unknown, options?: RequestOptions) => requestCore<T>(url, { ...(options ?? {}), method: 'PUT', data });
export const del = <T = unknown>(url: string, params?: QueryParams, options?: RequestOptions) => requestCore<T>(url, { ...(options ?? {}), method: 'DELETE', params });
export const remove = del;

export const request = Object.assign(requestCore, { get, post, put, delete: del, remove });

export const client = {
  get,
  post,
  put,
  delete: del,
  request,
  interceptors: {
    request: { use: () => undefined },
    response: { use: () => undefined },
  },
};

export async function login<T = unknown>(payload?: Record<string, unknown>) {
  return post<T>('/auth/login', payload);
}

export function getTaskBundleDownload(taskId: string): string {
  return `/api/v1/tasks/${taskId}/bundle/download`;
}

export function getTaskStreamUrl(taskId: string): string {
  return withTokenQuery(`/api/v1/tasks/${taskId}/stream`);
}

export const api = {
  get,
  post,
  put,
  delete: del,
  request,
  client,
  login,
};

export default api;
"""
    constants_runtime = _render_compile_safe_constants_file(profile)
    models_runtime = _render_compile_safe_models_file()

    def _ensure_constants_import(text: str, names: list[str]) -> str:
        match = re.search(r"import\s*\{(?P<body>[\s\S]*?)\}\s*from\s*['\"]\.\./types/constants['\"];", text)
        if not match:
            return text
        current = [part.strip() for part in match.group("body").replace("\n", " ").split(",") if part.strip()]
        for name in names:
            if name not in current:
                current.append(name)
        replacement = "import { " + ", ".join(current) + " } from '../types/constants';"
        return text[: match.start()] + replacement + text[match.end() :]

    for relative_path in required_files:
        content = str(synthesized.get(relative_path, "") or "")
        if relative_path == "frontend/src/types/constants.ts":
            if force_runtime_fallback:
                if content.strip() != constants_runtime.strip():
                    synthesized[relative_path] = constants_runtime
                    repaired_paths.append(relative_path)
                continue
            if not content.strip():
                continue
            normalized = content
            changed = False
            if "import.meta.env" in normalized or "process.env" in normalized:
                normalized = constants_runtime
                changed = True
            if changed:
                synthesized[relative_path] = normalized
                repaired_paths.append(relative_path)
            continue
        if relative_path == "frontend/src/types/models.ts":
            if force_runtime_fallback:
                if content.strip() != models_runtime.strip():
                    synthesized[relative_path] = models_runtime
                    repaired_paths.append(relative_path)
                continue
            if not content.strip():
                continue
            if not _has_balanced_delimiters(content):
                synthesized[relative_path] = models_runtime
                repaired_paths.append(relative_path)
            continue
        if relative_path != "frontend/src/services/api.ts":
            continue
        if force_runtime_fallback:
            if content.strip() != request_runtime.strip():
                synthesized[relative_path] = request_runtime
                repaired_paths.append(relative_path)
            continue
        if not content.strip():
            continue

        changed = False
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
        if normalized != content:
            changed = True
        normalized = re.sub(
            r"const\s+BASE_URL\s*=\s*import\.meta\.env\.[A-Z0-9_]+\s*\|\|\s*(['\"][^'\"]+['\"]);",
            r"const BASE_URL = ((globalThis as { __IPRIGHT_API_BASE_URL__?: string }).__IPRIGHT_API_BASE_URL__) || \1;",
            normalized,
        )
        normalized = re.sub(
            r"const\s+(?:baseUrl|baseURL|apiBaseUrl|apiBaseURL|API_BASE_URL)\s*=\s*import\.meta\.env\.[A-Z0-9_]+\s*;",
            "const BASE_URL = ((globalThis as { __IPRIGHT_API_BASE_URL__?: string }).__IPRIGHT_API_BASE_URL__) || '/api/v1';",
            normalized,
        )
        normalized = re.sub(
            r"\$\{(?:baseUrl|baseURL|apiBaseUrl|apiBaseURL)\}",
            "${BASE_URL}",
            normalized,
        )
        normalized = re.sub(
            r"const\s+(?:baseUrl|baseURL|apiBaseUrl|apiBaseURL|API_BASE_URL)\s*=\s*import\.meta\.env\.[A-Z0-9_]+\s*\|\|\s*(['\"][^'\"]+['\"]);",
            r"const BASE_URL = ((globalThis as { __IPRIGHT_API_BASE_URL__?: string }).__IPRIGHT_API_BASE_URL__) || \1;",
            normalized,
        )
        normalized = re.sub(
            r"import\.meta\.env\.[A-Z0-9_]+",
            "((globalThis as { __IPRIGHT_API_BASE_URL__?: string }).__IPRIGHT_API_BASE_URL__) || '/api/v1'",
            normalized,
        )
        normalized = normalized.replace(
            "get: <T>(url: string, params?: Record<string, string | number | boolean | undefined>) => {",
            "get: <T>(url: string, params?: Record<string, unknown>) => {",
        )
        request_import_pattern = re.compile(
            r"import\s+(?:\{[^}]*\}\s+from\s+|[A-Za-z_$][\w$]*\s+from\s+)?['\"][^'\"]*request(?:\.[a-z]+)?['\"];\s*",
        )
        if request_import_pattern.search(normalized):
            normalized = request_import_pattern.sub(request_runtime, normalized, count=1)
            changed = True
        if any(token in normalized for token in ("status: 'generated'", 'status: "generated"', "status: 'draft'", 'status: "draft"', "status: 'failed'", 'status: "failed"')):
            normalized = _ensure_constants_import(normalized, ["ReportStatus"])
        if "status: 'generated'" in normalized or 'status: "generated"' in normalized:
            normalized = normalized.replace("status: 'generated'", "status: ReportStatus.GENERATED")
            normalized = normalized.replace('status: "generated"', "status: ReportStatus.GENERATED")
        if "status: 'draft'" in normalized or 'status: "draft"' in normalized:
            normalized = normalized.replace("status: 'draft'", "status: ReportStatus.DRAFT")
            normalized = normalized.replace('status: "draft"', "status: ReportStatus.DRAFT")
        if "status: 'failed'" in normalized or 'status: "failed"' in normalized:
            normalized = normalized.replace("status: 'failed'", "status: ReportStatus.FAILED")
            normalized = normalized.replace('status: "failed"', "status: ReportStatus.FAILED")
        if any(token in normalized for token in ("status: 'pending'", 'status: "pending"', "status: 'running'", 'status: "running"', "status: 'completed'", 'status: "completed"')):
            normalized = _ensure_constants_import(normalized, ["AnalysisStatus"])
            normalized = normalized.replace("status: 'pending'", "status: AnalysisStatus.PENDING")
            normalized = normalized.replace('status: "pending"', "status: AnalysisStatus.PENDING")
            normalized = normalized.replace("status: 'running'", "status: AnalysisStatus.RUNNING")
            normalized = normalized.replace('status: "running"', "status: AnalysisStatus.RUNNING")
            normalized = normalized.replace("status: 'completed'", "status: AnalysisStatus.COMPLETED")
            normalized = normalized.replace('status: "completed"', "status: AnalysisStatus.COMPLETED")
        if any(token in normalized for token in ("= 'pending'", '= "pending"', "= 'running'", '= "running"', "= 'completed'", '= "completed"', "= 'failed'", '= "failed"')):
            normalized = _ensure_constants_import(normalized, ["AnalysisStatus"])
            normalized = normalized.replace("= 'pending'", "= AnalysisStatus.PENDING")
            normalized = normalized.replace('= "pending"', "= AnalysisStatus.PENDING")
            normalized = normalized.replace("= 'running'", "= AnalysisStatus.RUNNING")
            normalized = normalized.replace('= "running"', "= AnalysisStatus.RUNNING")
            normalized = normalized.replace("= 'completed'", "= AnalysisStatus.COMPLETED")
            normalized = normalized.replace('= "completed"', "= AnalysisStatus.COMPLETED")
            normalized = normalized.replace("= 'failed'", "= AnalysisStatus.FAILED")
            normalized = normalized.replace('= "failed"', "= AnalysisStatus.FAILED")
        if "exportFormats:" in normalized and any(token in normalized for token in ("'PDF'", '"PDF"', "'Excel'", '"Excel"', "'图片'", '"图片"')):
            normalized = _ensure_constants_import(normalized, ["ExportFormat"])
            normalized = normalized.replace("'PDF'", "ExportFormat.PDF")
            normalized = normalized.replace('"PDF"', "ExportFormat.PDF")
            normalized = normalized.replace("'Excel'", "ExportFormat.EXCEL")
            normalized = normalized.replace('"Excel"', "ExportFormat.EXCEL")
            normalized = normalized.replace("'图片'", "ExportFormat.IMAGE")
            normalized = normalized.replace('"图片"', "ExportFormat.IMAGE")
        if normalized != content:
            changed = True
        if changed:
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


def _inject_string_number_index_signatures(content: str) -> str:
    if "[key: string]:" in content:
        return content
    if not re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\[[A-Za-z_][A-Za-z0-9_]*\]", content):
        return content
    if "interface " not in content:
        return content

    lines = content.splitlines()
    rewritten: list[str] = []
    index = 0
    changed = False
    while index < len(lines):
        line = lines[index]
        rewritten.append(line)
        match = re.match(r"^(\s*)interface\s+[A-Za-z_][A-Za-z0-9_]*\s*\{\s*$", line)
        if not match:
            index += 1
            continue

        indent = match.group(1) + "  "
        block_index = index + 1
        block_lines: list[str] = []
        while block_index < len(lines):
            block_line = lines[block_index]
            if re.match(rf"^{re.escape(match.group(1))}\}};?\s*$", block_line):
                break
            block_lines.append(block_line)
            block_index += 1
        if block_lines and not any("[key: string]:" in block_line for block_line in block_lines):
            rewritten.append(f"{indent}[key: string]: unknown;")
            changed = True
        index += 1
    return "\n".join(rewritten) if changed else content


def _normalize_nullable_numeric_comparisons(content: str) -> str:
    pattern = re.compile(r"(?P<expr>[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)+)\s*>\s*0")

    def _replace(match: re.Match[str]) -> str:
        expr = match.group("expr")
        if "??" in expr or "?." in expr:
            return match.group(0)
        return f"({expr} ?? 0) > 0"

    return pattern.sub(_replace, content)


def _normalize_stats_trend_literals(content: str) -> str:
    pattern = re.compile(
        r"trend:\s*(?P<expr>[^,\n]+?\?\s*'up'\s*:\s*[^,\n]+?\?\s*'down'\s*:\s*'stable')"
    )

    def _replace(match: re.Match[str]) -> str:
        expr = match.group("expr").strip()
        if "StatResultTrend['trend']" in expr:
            return match.group(0)
        return f"trend: ({expr}) as StatResultTrend['trend']"

    return pattern.sub(_replace, content)


def _normalize_svg_setattribute_calls(content: str) -> str:
    numeric_attrs = {
        "x",
        "y",
        "x1",
        "y1",
        "x2",
        "y2",
        "cx",
        "cy",
        "r",
        "rx",
        "ry",
        "width",
        "height",
    }
    pattern = re.compile(r"(?P<prefix>\.setAttribute\(\s*['\"](?P<attr>[^'\"]+)['\"]\s*,\s*)(?P<expr>[^;\n]+?)(?P<suffix>\s*\);)")

    def _replace(match: re.Match[str]) -> str:
        attr = match.group("attr")
        expr = match.group("expr").strip()
        if attr == "fill" and "=>" in expr:
            return f"{match.group('prefix')}'#333'{match.group('suffix')}"
        if attr not in numeric_attrs:
            return match.group(0)
        if expr.startswith(("'", '"', "`")) or expr.startswith("String(") or expr.endswith(".toString()"):
            return match.group(0)
        return f"{match.group('prefix')}String({expr}){match.group('suffix')}"

    return pattern.sub(_replace, content)


def _find_module_page_metadata(profile: dict, relative_path: str) -> dict[str, object]:
    for page in build_codegen_requirements(profile).get("module_pages", []):
        if page.get("file_path") == relative_path:
            return dict(page)
    component_name = Path(relative_path).stem
    return {
        "title": component_name.replace("Page", "") or component_name,
        "route": f"/{component_name.replace('Page', '').lower()}",
        "description": "",
        "primary_action": "查看详情",
        "filter_placeholder": "请输入关键词筛选",
        "table_headers": ["项目名称", "当前状态", "更新时间"],
        "rows": [],
        "highlights": [],
    }


def _coerce_compile_safe_rows(page_meta: dict[str, object]) -> list[dict[str, str]]:
    rows = list(page_meta.get("rows") or [])
    if rows:
        safe_rows: list[dict[str, str]] = []
        for index, row in enumerate(rows[:6], start=1):
            if isinstance(row, dict):
                safe_row = {str(key): str(value) for key, value in row.items()}
            else:
                safe_row = {"项目名称": str(row)}
            safe_row.setdefault("id", str(index))
            safe_rows.append(safe_row)
        return safe_rows

    highlights = [str(item).strip() for item in list(page_meta.get("highlights") or []) if str(item).strip()]
    table_headers = [str(item).strip() for item in list(page_meta.get("table_headers") or []) if str(item).strip()]
    primary_header = table_headers[0] if table_headers else "项目名称"
    status_header = table_headers[1] if len(table_headers) > 1 else "当前状态"
    time_header = table_headers[2] if len(table_headers) > 2 else "更新时间"
    source_items = highlights[:4] or [str(page_meta.get("title") or "业务对象"), "关键指标", "分析任务", "处理记录"]
    return [
        {
            "id": str(index),
            primary_header: item,
            status_header: "正常" if index % 2 else "关注中",
            time_header: f"2026-06-{index + 1:02d} 09:{index * 7:02d}",
        }
        for index, item in enumerate(source_items, start=1)
    ]


def _render_compile_safe_module_page(relative_path: str, profile: dict) -> str:
    page_meta = _find_module_page_metadata(profile, relative_path)
    title = str(page_meta.get("title") or Path(relative_path).stem.replace("Page", "")).strip() or "业务页面"
    description = str(page_meta.get("description") or f"{title}帮助业务团队查看关键指标、处理状态和近期变化。").strip()
    route = str(page_meta.get("route") or "").strip()
    primary_action = str(page_meta.get("primary_action") or "查看详情").strip() or "查看详情"
    filter_placeholder = str(page_meta.get("filter_placeholder") or "请输入关键词筛选").strip() or "请输入关键词筛选"
    highlights = [str(item).strip() for item in list(page_meta.get("highlights") or []) if str(item).strip()][:4]
    if not highlights:
        highlights = ["关键指标总览", "任务状态追踪", "异常问题定位", "结果导出复核"]
    rows = _coerce_compile_safe_rows(page_meta)
    header_candidates = [str(item).strip() for item in list(page_meta.get("table_headers") or []) if str(item).strip()]
    all_headers = list(dict.fromkeys(["id", *header_candidates, *[key for row in rows for key in row.keys() if key != "id"]]))
    column_headers = [header for header in all_headers if header != "id"]
    summary_cards = [
        {"label": "记录数", "value": len(rows)},
        {"label": "重点事项", "value": len(highlights)},
        {"label": "当前路由", "value": route or "/dashboard"},
    ]
    component_name = _camel_name(Path(relative_path).stem)
    route_label = route or "/dashboard"

    return "\n".join(
        [
            "import React from 'react';",
            "",
            f"const summaryCards: Array<{{ label: string; value: string | number }}> = {json.dumps(summary_cards, ensure_ascii=False, indent=2)};",
            f"const highlightItems: string[] = {json.dumps(highlights, ensure_ascii=False, indent=2)};",
            f"const tableData: Array<Record<string, string>> = {json.dumps(rows, ensure_ascii=False, indent=2)};",
            f"const tableHeaders: string[] = {json.dumps(column_headers, ensure_ascii=False, indent=2)};",
            "",
            f"export default function {component_name}() {{",
            "  return (",
            "    <div>",
            "      <section>",
            f"        <h2>{json.dumps(title, ensure_ascii=False)}</h2>",
            f"        <p>{json.dumps(description, ensure_ascii=False)}</p>",
            f"        <p>{json.dumps(f'当前页面已启用编译安全渲染，保留 {title} 的核心信息展示与检视能力。', ensure_ascii=False)}</p>",
            "      </section>",
            "      <section>",
            "        <ul>",
            "        {summaryCards.map((item) => (",
            "          <li key={item.label}>",
            "            <strong>{item.label}</strong>: {String(item.value)}",
            "          </li>",
            "        ))}",
            "        </ul>",
            "      </section>",
            "      <section>",
            "        <ul>",
            "          {highlightItems.map((item) => (",
            "            <li key={item}>{item}</li>",
            "          ))}",
            "        </ul>",
            "      </section>",
            "      <section>",
            f"        <input aria-label=\"compile-safe-filter\" placeholder={json.dumps(filter_placeholder, ensure_ascii=False)} />",
            f"        <button type=\"button\">{json.dumps(primary_action, ensure_ascii=False)}</button>",
            "      </section>",
            "      <section>",
            f"        <p>{json.dumps(f'页面路由：{route_label}', ensure_ascii=False)}</p>",
            "          <table>",
            "            <thead>",
            "              <tr>",
            "                {tableHeaders.map((header) => (",
            "                  <th key={header}>{header}</th>",
            "                ))}",
            "              </tr>",
            "            </thead>",
            "            <tbody>",
            "              {tableData.map((row) => (",
            "                <tr key={String(row.id)}>",
            "                  {tableHeaders.map((header) => (",
            "                    <td key={`${row.id}-${header}`}>{String(row[header] ?? '')}</td>",
            "                  ))}",
            "                </tr>",
            "              ))}",
            "            </tbody>",
            "          </table>",
            "      </section>",
            "    </div>",
            "  );",
            "}",
            "",
        ]
    )


def _synthesize_module_compile_files(
    generated_files: dict[str, str],
    profile_or_required_files: dict | list[str] | None,
    required_files: list[str] | None = None,
    *,
    overwrite_existing: bool = False,
    force_safe_fallback: bool = False,
) -> tuple[dict[str, str], list[str]]:
    del overwrite_existing
    if required_files is None:
        profile = {}
        required_files = list(profile_or_required_files or [])
    else:
        profile = dict(profile_or_required_files or {})
    synthesized = dict(generated_files)
    repaired_paths: list[str] = []
    icon_replacements = {
        "DataSourceOutlined": "DatabaseOutlined",
        "RouteOutlined": "NodeIndexOutlined",
        "OutboxOutlined": "ExportOutlined",
        "SnowflakeOutlined": "CloudServerOutlined",
        "CleaningServicesOutlined": "ToolOutlined",
        "CleaningOutlined": "ClearOutlined",
    }
    for relative_path in required_files:
        if not relative_path.startswith("frontend/src/pages/") or (
            not relative_path.endswith("Page.tsx") and relative_path != "frontend/src/pages/Dashboard.tsx"
        ):
            continue
        content = str(synthesized.get(relative_path, "") or "")
        fallback_page = _render_compile_safe_module_page(relative_path, profile)
        if not content.strip():
            if force_safe_fallback:
                synthesized[relative_path] = fallback_page
                repaired_paths.append(relative_path)
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
        if "Checkbox" in normalized and "from 'antd'" in normalized:
            antd_import_match = re.search(r"import\s*\{(?P<body>[\s\S]*?)\}\s*from\s*'antd';", normalized)
            if antd_import_match and "Checkbox" not in antd_import_match.group("body"):
                body_parts = [part.strip() for part in antd_import_match.group("body").replace("\n", " ").split(",") if part.strip()]
                body_parts.append("Checkbox")
                replacement = "import {\n  " + ", ".join(dict.fromkeys(body_parts)) + "\n} from 'antd';"
                normalized = normalized[: antd_import_match.start()] + replacement + normalized[antd_import_match.end() :]
                changed = True
        normalized_checkbox_event = re.sub(r"onChange=\{\((e)\)\s*=>", r"onChange={(\1: { target: { checked: boolean } }) =>", normalized)
        if normalized_checkbox_event != normalized and "Checkbox" in normalized:
            normalized = normalized_checkbox_event
            changed = True
        if 'align="right"' in normalized:
            normalized = normalized.replace('align="right"', 'align="end"')
            changed = True
        if "align='right'" in normalized:
            normalized = normalized.replace("align='right'", "align='end'")
            changed = True
        if "styles." in normalized and "const styles =" not in normalized:
            style_keys = sorted(set(re.findall(r"styles\.([A-Za-z_][A-Za-z0-9_]*)", normalized)))
            style_entries = "\n".join([f"  {key}: {{}} as React.CSSProperties," for key in style_keys])
            if not style_entries:
                style_entries = "  container: {} as React.CSSProperties,"
            styles_block = "const styles = {\n" + style_entries + "\n};\n"
            import_block = re.match(r"((?:import[^\n]*\n)+)", normalized)
            if import_block:
                normalized = normalized[: import_block.end()] + "\n" + styles_block + "\n" + normalized[import_block.end() :]
            else:
                normalized = styles_block + "\n" + normalized
            changed = True
        normalized_indexed = _inject_string_number_index_signatures(normalized)
        if normalized_indexed != normalized:
            normalized = normalized_indexed
            changed = True
        normalized_trend = _normalize_stats_trend_literals(normalized)
        if normalized_trend != normalized:
            normalized = normalized_trend
            changed = True
        normalized_nullable_numbers = _normalize_nullable_numeric_comparisons(normalized)
        if normalized_nullable_numbers != normalized:
            normalized = normalized_nullable_numbers
            changed = True
        normalized_safe_rule = normalized.replace("detailModal.rule.dataSourceId", "detailModal.rule?.dataSourceId ?? ''")
        if normalized_safe_rule != normalized:
            normalized = normalized_safe_rule
            changed = True
        if "Transfer" in normalized and "setSelectedFields(" in normalized:
            normalized_transfer_keys = re.sub(
                r"setSelectedFields\((?P<keys>[A-Za-z_][A-Za-z0-9_]*)\)",
                r"setSelectedFields(\g<keys> as string[])",
                normalized,
            )
            if normalized_transfer_keys != normalized:
                normalized = normalized_transfer_keys
                changed = True
        normalized_onfilter = re.sub(r"onFilter:\s*\((value):\s*string,\s*(record)\s*:", r"onFilter: (\1: string | number | boolean, \2:", normalized)
        if normalized_onfilter != normalized:
            normalized = normalized_onfilter
            changed = True
        if "render:" in normalized:
            normalized_columns = re.sub(
                r"const\s+([A-Za-z_][A-Za-z0-9_]*Columns)\s*=\s*\[",
                r"const \1: any[] = [",
                normalized,
            )
            if normalized_columns != normalized:
                normalized = normalized_columns
                changed = True
        normalized_svg_component = _normalize_svg_component_props(normalized)
        if normalized_svg_component != normalized:
            normalized = normalized_svg_component
            changed = True
        normalized_svg = _normalize_svg_setattribute_calls(normalized)
        if normalized_svg != normalized:
            normalized = normalized_svg
            changed = True
        if changed:
            normalized = _dedupe_ant_icon_imports(normalized)
        if force_safe_fallback and not changed:
            normalized = fallback_page
            changed = True
        if changed:
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
    llm = get_llm_client() if batches else None
    if batches and llm:
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
        configured_model = getattr(getattr(llm, "config", None), "code_model", "")
        report = {
            "model_used": configured_model or ("llm_generated" if llm and batches else "template_only"),
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
        has_partial_support = any(
            str(generated_files.get(relative_path, "") or "").strip()
            for relative_path in invalid_support_paths
        )
        generated_files, repaired_invalid_support_paths = _synthesize_support_runtime_files(
            generated_files,
            profile,
            invalid_support_paths,
            overwrite_existing=True,
            force_runtime_fallback=has_partial_support,
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
        generated_files, repaired_invalid_module_paths = _synthesize_module_compile_files(
            generated_files,
            profile,
            invalid_module_paths,
            overwrite_existing=True,
            force_safe_fallback=True,
        )
        if repaired_invalid_module_paths:
            repaired_module_paths = sorted(set([*repaired_module_paths, *repaired_invalid_module_paths]))
            generated_files, invalid_module_paths = repair_invalid_module_pages(generated_files, profile)
            batch_reports.append(
                {
                    "batch": "module_structural_fallback",
                    "attempt": 1,
                    "required_files": list(repaired_invalid_module_paths),
                    "generated_paths": sorted(repaired_invalid_module_paths),
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
            invalid_module_paths=invalid_module_paths,
            invalid_module_previews=invalid_module_previews,
        ), (
            "App code generation failed: missing or invalid LLM-generated module frontend files: "
            + ", ".join(invalid_module_paths)
        )
    generated_files, applied, apply_error = _apply_normalized_generated_code_bundle(
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
    compile_invalid_core_paths = [
        path
        for path in invalid_compile_paths
        if path in {
            "frontend/src/App.tsx",
            "frontend/src/pages/Login.tsx",
            "frontend/src/pages/Dashboard.tsx",
        }
    ]
    if compile_invalid_core_paths:
        generated_files, repaired_compile_core_paths = _synthesize_structured_core_files(
            generated_files,
            profile,
            compile_invalid_core_paths,
            overwrite_existing=True,
        )
        if repaired_compile_core_paths:
            repaired_core_paths = sorted(set([*repaired_core_paths, *repaired_compile_core_paths]))
            generated_files, applied, apply_error = _apply_normalized_generated_code_bundle(
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
                    "required_files": list(repaired_compile_core_paths),
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
            generated_files, applied, apply_error = _apply_normalized_generated_code_bundle(
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
        and path not in {
            "frontend/src/pages/Login.tsx",
            "frontend/src/pages/Dashboard.tsx",
        }
    ]
    if compile_invalid_module_paths:
        generated_files, repaired_compile_module_paths = _synthesize_module_compile_files(
            generated_files,
            profile,
            compile_invalid_module_paths,
            overwrite_existing=True,
            force_safe_fallback=True,
        )
        if repaired_compile_module_paths:
            repaired_module_paths = sorted(set([*repaired_module_paths, *repaired_compile_module_paths]))
            generated_files, applied, apply_error = _apply_normalized_generated_code_bundle(
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
        generated_files, repaired_terminal_paths = _apply_terminal_compile_fallback(
            generated_files,
            profile,
            invalid_compile_paths,
        )
        if repaired_terminal_paths:
            terminal_core_paths = [
                path
                for path in repaired_terminal_paths
                if path in {
                    "frontend/src/App.tsx",
                    "frontend/src/pages/Login.tsx",
                    "frontend/src/pages/Dashboard.tsx",
                }
            ]
            terminal_module_paths = [
                path
                for path in repaired_terminal_paths
                if path.startswith("frontend/src/pages/")
                and path not in {
                    "frontend/src/pages/Login.tsx",
                    "frontend/src/pages/Dashboard.tsx",
                }
            ]
            terminal_support_paths = [
                path
                for path in repaired_terminal_paths
                if path in {
                    "frontend/src/services/api.ts",
                    "frontend/src/types/constants.ts",
                    "frontend/src/types/models.ts",
                }
            ]
            if terminal_core_paths:
                repaired_core_paths = sorted(set([*repaired_core_paths, *terminal_core_paths]))
            if terminal_module_paths:
                repaired_module_paths = sorted(set([*repaired_module_paths, *terminal_module_paths]))
            if terminal_support_paths:
                repaired_support_paths = sorted(set([*repaired_support_paths, *terminal_support_paths]))
            generated_files, applied, apply_error = _apply_normalized_generated_code_bundle(
                app_root,
                generated_files,
                codegen_requirements["required_files"],
                preserve_paths=_terminal_safe_frontend_paths(profile),
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
                    "batch": "terminal_compile_fallback",
                    "attempt": 1,
                    "required_files": list(repaired_terminal_paths),
                    "generated_paths": sorted(repaired_terminal_paths),
                    "fallback_to_template": bool(invalid_compile_paths),
                    "error": (
                        "still invalid after terminal fallback: " + ", ".join(invalid_compile_paths)
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
