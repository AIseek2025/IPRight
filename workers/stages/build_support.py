from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path

from workers.stages.generated_backend import GENERATED_BACKEND_APP_FILES
from workers.stages.generated_frontend import (
    _camel_name,
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
_ANTD_ICON_IMPORT_RE = re.compile(r"import\s*\{(?P<icons>[\s\S]*?)\}\s*from\s*['\"]@ant-design/icons['\"]")
_MODULE_INVALID_RETRY_BATCH_SIZE = 1
_CORE_INVALID_RETRY_BATCH_SIZE = 1
_MODULE_INVALID_MAX_RETRY_ROUNDS = 4
_PAGE_LAYOUT_PATTERNS = (
    "标题区 + 左侧筛选带 + 右侧主结果表",
    "顶部摘要卡带 + 下方双列信息区 + 主列表",
    "分段标题 + 横向工具条 + 全宽结果表",
    "标题区 + 三列指标摘要 + 主表格",
    "标题区 + 上下分栏（上筛选/下结果）",
    "标题区 + 左右分栏（左列表/右详情摘要）",
    "标题区 + 顶部时间线/进度条 + 下方主操作区",
    "标题区 + 左侧树形导航 + 右侧内容画布",
    "顶部 Tab 分段 + 每段独立信息区 + 底部汇总",
    "标题区 + 统计摘要带 + 主表格 + 底部操作栏",
    "全宽看板视图 + 横向列分组 + 卡片式条目",
    "标题区 + 搜索/筛选一体工具条 + 卡片网格",
    "左侧摘要面板 + 右侧详情/编辑区 + 底部日志",
    "标题区 + 多维度筛选矩阵 + 下方交叉分析表",
    "顶部状态概览条 + 中部流程节点 + 底部记录列表",
    "标题区 + 地图/画布主区 + 右侧属性面板",
    "标题区 + 上下双表（主表/子表联动）+ 汇总栏",
    "分段折叠面板 + 每段独立数据区 + 全局搜索",
)
_PAGE_VISUAL_ACCENTS = (
    "偏扁平卡片、轻边框",
    "偏分区色块、弱阴影",
    "偏索引条 + 内容画布",
    "偏高密度表格主导",
    "偏摘要带 + 单列主内容",
    "偏圆角卡片 + 渐变强调色",
    "偏紧凑行距 + 数据密度优先",
    "偏留白呼吸感 + 大间距卡片",
    "偏深色主色调 + 白色内容区",
    "偏浅色主题 + 柔和边框",
    "偏信息图表化 + 可视化组件主导",
    "偏工具栏密集 + 操作驱动",
)
_DISALLOWED_FRONTEND_REPORTING_TOKENS = (
    "任务简报",
    "进入前摘要",
    "岗位工作台预览",
    "平台入口概览",
    "软件演示入口",
    "演示入口",
    "开发情况",
    "研发测试",
    "验收建议",
    "交付资料下载",
)
_SUPPORTED_ANTD_ICON_NAMES = {
    "AppstoreOutlined",
    "AuditOutlined",
    "BarChartOutlined",
    "CalendarOutlined",
    "CheckCircleOutlined",
    "ClockCircleOutlined",
    "ExclamationCircleOutlined",
    "FileTextOutlined",
    "PlusOutlined",
    "RightOutlined",
    "TeamOutlined",
    "UserOutlined",
}


def _contains_disallowed_frontend_reporting_copy(content: str) -> bool:
    lowered = content.lower()
    if any(token in content for token in _DISALLOWED_FRONTEND_REPORTING_TOKENS):
        return True
    return any(
        phrase in lowered
        for phrase in (
            "for the platform owner",
            "for the team",
            "development report",
            "delivery summary",
        )
    )


def _extract_antd_icon_names(content: str) -> set[str]:
    icon_names: set[str] = set()
    for match in _ANTD_ICON_IMPORT_RE.finditer(content or ""):
        for raw_token in match.group("icons").replace("\n", " ").split(","):
            token = raw_token.strip()
            if not token:
                continue
            icon_name = token.split(" as ", 1)[0].strip()
            if icon_name:
                icon_names.add(icon_name)
    return icon_names


def _uses_supported_antd_icons(content: str) -> bool:
    icon_names = _extract_antd_icon_names(content)
    return all(icon_name in _SUPPORTED_ANTD_ICON_NAMES for icon_name in icon_names)


def _has_balanced_quote_pairs(content: str, quote: str) -> bool:
    escaped = False
    open_count = 0
    for char in content:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == quote:
            open_count ^= 1
    return open_count == 0


def _has_balanced_delimiters(content: str) -> bool:
    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = {value: key for key, value in pairs.items()}
    stack: list[str] = []
    in_single = False
    in_double = False
    in_backtick = False
    escaped = False

    for char in content:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double and not in_backtick:
            in_single = not in_single
            continue
        if char == '"' and not in_single and not in_backtick:
            in_double = not in_double
            continue
        if char == "`" and not in_single and not in_double:
            in_backtick = not in_backtick
            continue
        if in_single or in_double or in_backtick:
            continue
        if char in pairs:
            stack.append(char)
            continue
        if char in closing:
            if not stack or stack[-1] != closing[char]:
                return False
            stack.pop()

    return not stack and not in_single and not in_double and not in_backtick


def _looks_like_complete_typescript_source(content: str) -> bool:
    text = str(content or "").strip()
    if not text:
        return False
    if not _has_balanced_quote_pairs(text, "'"):
        return False
    if not _has_balanced_quote_pairs(text, '"'):
        return False
    if not _has_balanced_quote_pairs(text, "`"):
        return False
    if not _has_balanced_delimiters(text):
        return False
    return text[-1] in {"}", ")", ";", "]"}


def _imports_appear_before_runtime_code(content: str) -> bool:
    in_block_comment = False
    in_import = False
    saw_runtime_code = False

    for raw_line in str(content or "").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if in_block_comment:
            if "*/" not in stripped:
                continue
            stripped = stripped.split("*/", 1)[1].strip()
            in_block_comment = False
            if not stripped:
                continue
        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block_comment = True
                continue
            stripped = stripped.split("*/", 1)[1].strip()
            if not stripped:
                continue
        if stripped.startswith("//"):
            continue
        if in_import:
            if ";" in stripped:
                in_import = False
            continue
        if re.match(r"^import(?:\s+type\b|\s|{|\*)", stripped):
            if saw_runtime_code:
                return False
            if ";" not in stripped:
                in_import = True
            continue
        saw_runtime_code = True

    return not in_import


def _has_component_default_export(content: str, component_name: str) -> bool:
    escaped_name = re.escape(component_name)
    return any(
        re.search(pattern, content)
        for pattern in (
            rf"\bexport\s+default\s+function\s+{escaped_name}\b",
            rf"\bfunction\s+{escaped_name}\b[\s\S]*?\bexport\s+default\s+{escaped_name}\s*;",
            rf"\bconst\s+{escaped_name}\b[\s\S]*?\bexport\s+default\s+{escaped_name}\s*;",
        )
    )


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _is_macos_metadata_name(name: str) -> bool:
    return name in {"__MACOSX", ".DS_Store"} or name.startswith("._")


def _cleanup_macos_metadata(root: str) -> list[str]:
    root_path = Path(root)
    if not root_path.exists():
        return []

    removed: list[str] = []
    for path in sorted(root_path.rglob("*"), key=lambda item: (len(item.parts), str(item)), reverse=True):
        if not _is_macos_metadata_name(path.name):
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(str(path.relative_to(root_path)))
        except OSError:
            continue
    return removed


def _verify_required_files_on_disk(app_root: str, required_files: list[str]) -> tuple[list[str], list[str]]:
    verified_paths: list[str] = []
    missing_or_empty: list[str] = []
    for relative_path in required_files:
        absolute_path = Path(app_root) / relative_path
        if not absolute_path.exists() or not absolute_path.is_file():
            missing_or_empty.append(relative_path)
            continue
        try:
            content = absolute_path.read_text(encoding="utf-8")
        except OSError:
            missing_or_empty.append(relative_path)
            continue
        if not content.strip():
            missing_or_empty.append(relative_path)
            continue
        verified_paths.append(relative_path)
    return verified_paths, missing_or_empty


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


def _build_page_design_brief(module: dict, profile: dict, module_index: int) -> str:
    """为每个模块页生成独立 design DNA，避免同任务页面收敛到同一骨架。"""
    seed = "|".join(
        [
            str(profile.get("design_seed") or ""),
            str(profile.get("product_name") or ""),
            str(module.get("route") or module.get("key") or ""),
            str(module.get("title") or ""),
            str(module_index),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    layout = _PAGE_LAYOUT_PATTERNS[int(digest[:4], 16) % len(_PAGE_LAYOUT_PATTERNS)]
    accent = _PAGE_VISUAL_ACCENTS[int(digest[4:8], 16) % len(_PAGE_VISUAL_ACCENTS)]
    density = ("信息密度偏高、表格主导", "信息密度适中、摘要+列表并重", "信息密度偏低、摘要先行")[int(digest[8:10], 16) % 3]
    chrome = str((profile.get("experience_blueprint") or {}).get("navigation_variant") or "default")
    return (
        f"layout_pattern={layout}; visual_accent={accent}; density={density}; "
        f"navigation_context={chrome}; variation_token={digest[:12]}; "
        "禁止复用同任务其他模块页的三卡片+单表骨架或相同分区顺序。"
    )


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


def build_seed_copy_ignore(extra_names: set[str] | None = None):
    extra_names = extra_names or set()

    def ignore(_src: str, names: list[str]) -> set[str]:
        ignored = {
            name
            for name in names
            if name in {"node_modules", "dist", ".vite", "__pycache__", "__MACOSX", ".DS_Store"}
            or name.startswith("._")
            or name.endswith(".pyc")
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
    _cleanup_macos_metadata(frontend_dst)
    _cleanup_macos_metadata(backend_dst)
    frontend_ignore = build_seed_copy_ignore()

    def backend_ignore(src: str, names: list[str]) -> set[str]:
        ignored = build_seed_copy_ignore()(src, names)
        if Path(src).resolve() == (backend_src / "app").resolve():
            ignored.update(name for name in names if name in GENERATED_BACKEND_APP_FILES)
        return ignored

    shutil.copytree(frontend_src, frontend_dst, dirs_exist_ok=True, ignore=frontend_ignore)
    shutil.copytree(backend_src, backend_dst, dirs_exist_ok=True, ignore=backend_ignore)
    _write_task_specific_app(frontend_dst, backend_dst, profile)
    _cleanup_macos_metadata(frontend_dst)
    _cleanup_macos_metadata(backend_dst)
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
    seen_module_paths: set[str] = set()
    ui_variation_seed = str(profile.get("design_seed") or profile.get("product_name") or "default")
    for module_index, module in enumerate(profile.get("modules", [])):
        component_name = f"{_camel_name(module.get('route', module['key']))}Page"
        file_path = f"frontend/src/pages/{component_name}.tsx"
        if file_path in seen_module_paths:
            continue
        seen_module_paths.add(file_path)
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
                "page_design_brief": _build_page_design_brief(module, profile, module_index),
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
        "ui_variation_seed": ui_variation_seed,
        "design_seed": profile.get("design_seed", ""),
    }


def build_codegen_batches(codegen_requirements: dict) -> list[dict]:
    if not codegen_requirements.get("required_files"):
        return []
    core_required_files = list(codegen_requirements.get("core_required_files", []))
    support_core_files = [
        path
        for path in core_required_files
        if path
        not in {
            "frontend/src/App.tsx",
            "frontend/src/pages/Login.tsx",
            "frontend/src/pages/Dashboard.tsx",
        }
    ]
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
        "ui_variation_seed": codegen_requirements.get("ui_variation_seed", ""),
        "design_seed": codegen_requirements.get("design_seed", ""),
    }
    batches = []
    if "frontend/src/App.tsx" in core_required_files:
        batches.append(
            {
                "name": "core",
                "required_files": ["frontend/src/App.tsx"],
                "requirements": {
                    **common_requirements,
                    "required_files": ["frontend/src/App.tsx"],
                    "module_pages": list(codegen_requirements.get("module_pages", [])),
                },
            }
        )
    if "frontend/src/pages/Login.tsx" in core_required_files:
        batches.append(
            {
                "name": "core_login",
                "required_files": ["frontend/src/pages/Login.tsx"],
                "requirements": {
                    **common_requirements,
                    "required_files": ["frontend/src/pages/Login.tsx"],
                    "module_pages": [],
                },
            }
        )
    if "frontend/src/pages/Dashboard.tsx" in core_required_files:
        batches.append(
            {
                "name": "core_dashboard",
                "required_files": ["frontend/src/pages/Dashboard.tsx"],
                "requirements": {
                    **common_requirements,
                    "required_files": ["frontend/src/pages/Dashboard.tsx"],
                    "module_pages": [],
                    "single_file_plaintext": True,
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
    seed_modules = _dedupe_str_list(list(plan_seed.get("core_modules") or []))
    seed_routes = _dedupe_str_list(list(plan_seed.get("required_pages") or []))
    base_routes = {"/login", "/dashboard"}
    legacy_business_routes = {"/events", "/tasks", "/monitor", "/reports", "/settings"}
    legacy_modules = {
        "异常事件管理",
        "协同任务管理",
        "冷链数据监控",
        "履约看板",
        "报表与分析",
    }
    current_business_routes = [route for route in current_routes if route not in base_routes]
    seed_business_routes = [route for route in seed_routes if route not in base_routes]
    uses_legacy_prd_family = (
        bool(current_business_routes)
        and bool(seed_business_routes)
        and (
            set(current_business_routes) == legacy_business_routes
            or set(current_modules) == legacy_modules
        )
        and set(seed_business_routes) != legacy_business_routes
    )

    if not current_modules or uses_legacy_prd_family:
        current_modules = list(seed_modules)
    if not current_routes or uses_legacy_prd_family:
        current_routes = list(seed_routes)
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


def _repair_typescript_import_syntax(content: str) -> str:
    text = str(content or "")
    if not text.strip():
        return text
    text = re.sub(
        r"(import\s+(?:type\s+)?(?:\{[^}]*\}|[^;\n]+?)\s*from\s*['\"][^'\"]+['\"])\s+(import\s+(?:type\s+)?)",
        r"\1;\n\2",
        text,
    )
    text = re.sub(
        r"(import\s+(?:type\s+)?(?:\{[^}]*\}|[^;\n]+?)\s*from\s*['\"][^'\"]+['\"])\s+(const|export|function|class|interface|type)\b",
        r"\1;\n\2",
        text,
    )
    text = re.sub(
        r"(const\s+\{[^}]+\}\s*=\s*Typography)\s+(const|export|function|class|interface|type)\b",
        r"\1;\n\2",
        text,
    )
    return text


def _repair_generated_typescript_syntax(generated_files: dict[str, str]) -> dict[str, str]:
    repaired: dict[str, str] = {}
    for relative_path, content in generated_files.items():
        if relative_path.startswith("frontend/") and relative_path.endswith((".ts", ".tsx")):
            repaired[relative_path] = _repair_typescript_import_syntax(content)
        else:
            repaired[relative_path] = str(content)
    return repaired


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
) -> tuple[bool, str | None, list[str], list[str]]:
    missing = [path for path in required_files if not generated_files.get(path)]
    if missing:
        return False, f"Missing generated files: {', '.join(missing[:8])}", [], []

    cleaned_metadata_paths = _cleanup_macos_metadata(app_root)
    for relative_path in required_files:
        content = _strip_code_fence(str(generated_files.get(relative_path, "")))
        if not content:
            return False, f"Generated file is empty: {relative_path}", [], sorted(set(cleaned_metadata_paths))
        absolute_path = os.path.join(app_root, relative_path)
        os.makedirs(os.path.dirname(absolute_path), exist_ok=True)
        _write_text(absolute_path, content)

    cleaned_metadata_paths.extend(_cleanup_macos_metadata(app_root))
    verified_paths, missing_or_empty = _verify_required_files_on_disk(app_root, required_files)
    if missing_or_empty:
        return (
            False,
            "Generated files failed disk verification: " + ", ".join(missing_or_empty[:8]),
            sorted(verified_paths),
            sorted(set(cleaned_metadata_paths)),
        )

    return True, None, sorted(verified_paths), sorted(set(cleaned_metadata_paths))


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
        if str(synthesized.get(relative_path, "")).strip():
            continue
        synthesized[relative_path] = content
        repaired_paths.append(relative_path)

    return synthesized, repaired_paths


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

    def _uses_disallowed_long_route_app_shell(content: str) -> bool:
        router_import_match = re.search(
            r"import\s*\{(?P<imports>[^}]*)\}\s*from\s*['\"]react-router-dom['\"]",
            content,
        )
        router_imports = {
            token.strip()
            for token in (router_import_match.group("imports").split(",") if router_import_match else [])
            if token.strip()
        }
        has_overloaded_router_import = {"Routes", "Route", "Navigate", "Link"}.issubset(router_imports)
        has_generic_redirect_nav = "Navigate to=" in content and "Link to=" in content
        return has_overloaded_router_import or has_generic_redirect_nav

    def _uses_disallowed_heavy_app_shell(content: str) -> bool:
        return _contains_any(
            content,
            [
                "useMemo",
                "useLocation",
                "useNavigate",
                "NavLink",
                "TabsProps",
                "Tabs",
                "Outlet",
                "Row, Col, Card, Button, Space",
            ],
        )

    def _uses_disallowed_dashboard_light_shell(content: str) -> bool:
        padding_tokens = [
            "padding: 24",
            "padding:'24px'",
            "padding: '24px'",
            'padding: "24px"',
            "padding:'20px 24px'",
            "padding: '20px 24px'",
            'padding: "20px 24px"',
            "padding:'1.5rem 2rem'",
            "padding: '1.5rem 2rem'",
            'padding: "1.5rem 2rem"',
        ]
        has_old_light_shell = _contains_any(content, padding_tokens[:4]) and _contains_any(
            content,
            [
                "minHeight: '100vh'",
                'minHeight: "100vh"',
                "background:",
                "<h1>工作台</h1>",
                "<h1>系统首页</h1>",
            ],
        )
        has_flex_shell = _contains_any(content, padding_tokens[4:]) and _contains_any(
            content,
            [
                "异常监控总览",
                "display: 'flex'",
                'display: "flex"',
                "flexDirection: 'column'",
                'flexDirection: "column"',
                "gap: 16",
            ],
        )
        has_workbench_shell = _contains_any(content, padding_tokens[7:]) and _contains_any(
            content,
            [
                "冷链履约异常协同工作台",
                "ExclamationCircleOutlined",
                "import { Card, Statistic, Tag } from 'antd';",
            ],
        )
        has_slice_shell = (
            "import { Card, Statistic } from 'antd';" in content
            and _contains_any(
                content,
                [
                    "padding:'16px'",
                    "padding: '16px'",
                    'padding: "16px"',
                    "padding: 16",
                ],
            )
            and "<h1>工作台</h1>" in content
            and "<p style={{ color: '#555' }}>{APP_PROFILE.product_name}</p>" in content
            and _contains_any(
                content,
                [
                    "APP_PROFILE.dashboard_metrics.slice(0, 4).map",
                    "APP_PROFILE.dashboard_metrics.slice(0,4).map",
                ],
            )
        )
        return has_old_light_shell or has_flex_shell or has_workbench_shell or has_slice_shell

    def _uses_disallowed_dashboard_icon_stats_shell(content: str) -> bool:
        icon_hits = sum(
            1
            for icon_name in [
                "TeamOutlined",
                "CalendarOutlined",
                "FileTextOutlined",
                "UserOutlined",
                "CheckCircleOutlined",
            ]
            if icon_name in content
        )
        return (
            "import { Card, Statistic } from 'antd';" in content
            and icon_hits >= 4
            and _contains_any(
                content,
                [
                    "background: '#f8f5ef'",
                    'background: "#f8f5ef"',
                    "padding: '24px'",
                    'padding: "24px"',
                    "padding: 24",
                ],
            )
        )

    def _uses_disallowed_dashboard_recent_events_shell(content: str) -> bool:
        return (
            "import { Card, Statistic } from 'antd';" in content
            and "const recentEvents = [" in content
            and _contains_any(
                content,
                [
                    "温度超标",
                    "运输延迟",
                    "处理中",
                    "待处理",
                ],
            )
        )

    def _uses_disallowed_dashboard_centered_stats_shell(content: str) -> bool:
        return (
            "import { Card, Statistic } from 'antd';" in content
            and "maxWidth: 1200" in content
            and "margin: '0 auto'" in content
            and "系统首页" in content
            and _contains_any(
                content,
                [
                    "color: '#4f46e5'",
                    'color: "#4f46e5"',
                    "APP_PROFILE.product_name",
                ],
            )
        )

    def _uses_disallowed_dashboard_green_icon_shell(content: str) -> bool:
        return (
            "import { Card, Statistic } from 'antd';" in content
            and "background: '#f0fdf9'" in content
            and _contains_any(
                content,
                [
                    "BarChartOutlined",
                    "ExclamationCircleOutlined",
                    "ClockCircleOutlined",
                    "FileTextOutlined",
                ],
            )
        )

    def _uses_disallowed_dashboard_recent_borrows_shell(content: str) -> bool:
        return (
            "import { Card, Statistic } from 'antd';" in content
            and "const recentBorrows = [" in content
            and _contains_any(
                content,
                [
                    "《计算机程序设计艺术》",
                    "《数据结构》",
                    "《算法导论》",
                ],
            )
            and _contains_any(
                content,
                [
                    "最近借阅记录",
                    "图书",
                    "读者",
                    "借出",
                    "归还",
                    "逾期",
                ],
            )
        )

    def _uses_disallowed_dashboard_recent_exceptions_shell(content: str) -> bool:
        return (
            "import { Card, Statistic } from 'antd';" in content
            and "const recentExceptions = [" in content
            and _contains_any(
                content,
                [
                    "EXC-101",
                    "EXC-102",
                    "ORD-3201",
                    "ORD-3202",
                    "温度超标",
                    "运输延迟",
                    "已恢复",
                    "处理中",
                ],
            )
            and _contains_any(
                content,
                [
                    "ExclamationCircleOutlined",
                    "CheckCircleOutlined",
                    "ClockCircleOutlined",
                ],
            )
        )

    validators = {
        "frontend/src/App.tsx": lambda content: (
            "PlaceholderPage" not in content
            and "模块开发中" not in content
            and "ModuleShell" not in content
            and not _references_unknown_page_import(content)
            and not _uses_disallowed_unified_sidebar(content)
            and not _uses_disallowed_long_route_app_shell(content)
            and not _uses_disallowed_heavy_app_shell(content)
            and not _contains_disallowed_frontend_reporting_copy(content)
            and _contains_any(content, ["export default function App", "function App(", "const App"])
            and _contains_any(content, ["APP_PROFILE", "generated/appProfile"])
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
            and not _contains_disallowed_frontend_reporting_copy(content)
            and _looks_like_complete_typescript_source(content)
            and _uses_supported_antd_icons(content)
            and "export default function Dashboard" in content
            and "import { APP_PROFILE } from '../generated/appProfile';" in content
            and "import { APP_PROFILE } from './generated/appProfile';" not in content
            and "../../generated/appProfile" not in content
            and "import APP_PROFILE from '../generated/appProfile'" not in content
            and "APP_PROFILE.product_name" in content
            and "APP_PROFILE.dashboard_metrics" in content
            and "const metrics = APP_PROFILE.dashboard_metrics" not in content
            and "const metrics = APP_PROFILE.dashboard_metrics || []" not in content
            and "const metrics = (APP_PROFILE as any).dashboard_metrics" not in content
            and "const fallbackMetrics = [" not in content
            and "const recentActivities = [" not in content
            and "const recentEvents = [" not in content
            and "const iconMap" not in content
            and "React.ReactNode" not in content
            and "Typography" not in content
            and "const { Title } = Typography" not in content
            and "const columns = [" not in content
            and "const dataSource = [" not in content
            and "ColumnsType" not in content
            and not _uses_disallowed_dashboard_light_shell(content)
            and not _uses_disallowed_dashboard_icon_stats_shell(content)
            and not _uses_disallowed_dashboard_recent_events_shell(content)
            and not _uses_disallowed_dashboard_centered_stats_shell(content)
            and not _uses_disallowed_dashboard_green_icon_shell(content)
            and not _uses_disallowed_dashboard_recent_borrows_shell(content)
            and not _uses_disallowed_dashboard_recent_exceptions_shell(content)
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
            and not _contains_disallowed_frontend_reporting_copy(content)
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
        row_tokens = [
            str(cell).strip()
            for row in list(module.get("rows", []))[:2]
            for cell in list(row)[:3]
            if str(cell).strip()
        ]
        header_tokens = [str(item).strip() for item in list(module.get("table_headers", []))[:3] if str(item).strip()]
        title = str(module.get("title") or "").strip()
        highlight_tokens = [str(item).strip() for item in list(module.get("highlights", []))[:3] if str(item).strip()]
        anchor_candidates = []
        for token in [
            *header_tokens,
            *row_tokens,
            *highlight_tokens,
            str(module.get("primary_action") or "").strip(),
            str(module.get("filter_placeholder") or "").strip(),
        ]:
            if token and token not in anchor_candidates:
                anchor_candidates.append(token)
        exact_title_hit = bool(title) and title in content
        business_anchor_hits = sum(1 for token in anchor_candidates if token in content)
        required_anchor_hits = min(2, len(anchor_candidates)) if anchor_candidates else 0
        page_variant = str(module.get("page_variant") or "records").strip()
        uses_disallowed_records_light_shell = (
            relative_path.endswith("RecordsPage.tsx")
            and "background: '#f8f5ef'" in content
            and any(token in content for token in ["padding: 24", "padding:'24px'", "padding: '24px'", 'padding: "24px"'])
            and any(token in content for token in ["minHeight: '100vh'", 'minHeight: "100vh"'])
            and any(token in content for token in ["justifyContent: 'space-between'", 'justifyContent: "space-between"'])
            and any(token in content for token in ["alignItems: 'center'", 'alignItems: "center"'])
        )
        uses_disallowed_records_array_shell = (
            relative_path.endswith("RecordsPage.tsx")
            and "const records = [" in content
            and any(token in content for token in ["updateTime:", "updateTime :", "'REC-001'", '"REC-001"', "'REC-002'", '"REC-002"'])
            and any(token in content for token in ["topic:", "tag:", "status:"])
        )
        uses_disallowed_workflow_white_shell = (
            relative_path.endswith("WorkflowPage.tsx")
            and "APP_PROFILE.product_name" in content
            and "候选人管理" in content
            and any(token in content for token in ["padding: 24", "padding:'24px'", "padding: '24px'", 'padding: "24px"'])
            and any(
                token in content
                for token in [
                    "background: '#ffffff'",
                    'background: "#ffffff"',
                    "color: '#888'",
                    'color: "#888"',
                    "fontSize: 12",
                ]
            )
        )
        uses_disallowed_workflow_blue_card_shell = (
            relative_path.endswith("WorkflowPage.tsx")
            and "background: '#f4f6fb'" in content
            and "maxWidth: 1200" in content
            and "margin: '0 auto'" in content
            and "background: '#ffffff'" in content
            and "borderRadius: 8" in content
        )
        uses_disallowed_workflow_records_array_shell = (
            relative_path.endswith("WorkflowPage.tsx")
            and "const records = [" in content
            and any(token in content for token in ["const thStyle =", "const tdStyle ="])
            and any(token in content for token in ["topic:", "role:", "status:", "tag:"])
            and any(token in content for token in ["date:", "date :", "'REC-001'", '"REC-001"', "'REC-002'", '"REC-002"'])
        )
        uses_disallowed_assets_records_array_shell = (
            relative_path.endswith("AssetsPage.tsx")
            and "const records = [" in content
            and any(token in content for token in ["updateTime:", "updateTime :", "'REC-001'", '"REC-001"', "'REC-002'", '"REC-002"'])
            and any(token in content for token in ["topic:", "role:", "status:", "tag:"])
        )
        uses_disallowed_workspace_heavy_antd_shell = (
            page_variant == "workspace"
            and any(
                token in content
                for token in [
                    "import React, { useState } from 'react';",
                    'import React, { useState } from "react";',
                    "import { useState } from 'react';",
                    'import { useState } from "react";',
                    "const [search, setSearch] = useState('');",
                    'const [search, setSearch] = useState("");',
                ]
            )
            and any(token in content for token in ["SearchOutlined", "PlusOutlined"])
            and "from 'antd';" in content
            and all(token in content for token in ["Input", "Button", "Card", "Tag"])
        )
        uses_disallowed_workspace_matrix_shell = (
            page_variant == "workspace"
            and any(
                token in content
                for token in [
                    "import React, { useState } from 'react';",
                    'import React, { useState } from "react";',
                    "import { useState } from 'react';",
                    'import { useState } from "react";',
                    "const [searchText, setSearchText] = useState('');",
                    'const [searchText, setSearchText] = useState("");',
                ]
            )
            and any(token in content for token in ["SearchOutlined", "PlusOutlined"])
            and "from 'antd';" in content
            and all(
                token in content
                for token in ["Card", "Row", "Col", "Statistic", "Input", "Button", "Space", "Table"]
            )
        )
        uses_disallowed_workspace_light_antd_shell = (
            page_variant == "workspace"
            and any(token in content for token in ["SearchOutlined", "PlusOutlined"])
            and "from 'antd';" in content
            and all(token in content for token in ["Input", "Button", "Tag"])
            and "background: '#f0fdf9'" in content
            and any(token in content for token in ["padding: 24", "padding:'24px'", "padding: '24px'", 'padding: "24px"'])
            and any(token in content for token in ["minHeight: '100vh'", 'minHeight: "100vh"'])
        )
        uses_disallowed_orders_supplier_records_shell = (
            relative_path.endswith("OrdersPage.tsx")
            and "const records = [" in content
            and any(
                token in content
                for token in [
                    "const { Title, Text } = Typography",
                    "import { Input, Button, Card, Space, Typography } from 'antd';",
                    "import { Card, Input, Button, Space, Typography } from 'antd';",
                ]
            )
            and any(token in content for token in ["SearchOutlined", "PlusOutlined"])
            and any(token in content for token in ["SUP-401", "SUP-402", "华辰材料", "嘉远供应"])
        )
        uses_disallowed_analytics_heavy_shell = (
            relative_path.endswith("AnalyticsPage.tsx")
            and any(
                token in content
                for token in [
                    "const { Title, Text } = Typography",
                    "const AnalyticsPage: React.FC",
                    "SearchOutlined",
                    "PlusOutlined",
                ]
            )
            and any(
                token in content
                for token in [
                    "import { Typography, Input, Button, Space, Card, Tag } from 'antd';",
                    "import { Input, Button, Space, Card, Tag, Typography } from 'antd';",
                ]
            )
        )
        uses_disallowed_monitor_heavy_shell = (
            relative_path.endswith("MonitorPage.tsx")
            and any(
                token in content
                for token in [
                    "import { useState } from 'react';",
                    'import { useState } from "react";',
                    "const [searchText, setSearchText] = useState('');",
                    'const [searchText, setSearchText] = useState("");',
                    "SearchOutlined",
                    "PlusOutlined",
                ]
            )
            and any(
                token in content
                for token in [
                    "import { Card, Input, Button, Space, Tag, Table } from 'antd';",
                    "import { Input, Button, Card, Space, Tag, Table } from 'antd';",
                    "import { Input, Button, Card, Space, Table, Tag } from 'antd';",
                ]
            )
        )
        uses_disallowed_settings_heavy_shell = (
            relative_path.endswith("SettingsPage.tsx")
            and any(
                token in content
                for token in [
                    "const { Title, Text } = Typography",
                    "SearchOutlined",
                    "const thStyle: React.CSSProperties",
                    "const thStyle =",
                ]
            )
            and any(
                token in content
                for token in [
                    "import { Input, Button, Tag, Space, Typography } from 'antd';",
                    "import { Input, Button, Space, Tag, Typography } from 'antd';",
                    "import { Typography, Input, Button, Tag, Space } from 'antd';",
                ]
            )
        )
        uses_disallowed_settings_green_shell = (
            relative_path.endswith("SettingsPage.tsx")
            and "background: '#f0fdf9'" in content
            and any(token in content for token in ["padding: 24", "padding:'24px'", "padding: '24px'", 'padding: "24px"'])
            and any(token in content for token in ["minHeight: '100vh'", 'minHeight: "100vh"'])
            and any(
                token in content
                for token in [
                    "const cellStyle = {",
                    "border: '1px solid #bbf7d0'",
                    'border: "1px solid #bbf7d0"',
                    "color: '#14532d'",
                    'color: "#14532d"',
                ]
            )
        )
        uses_disallowed_reports_green_shell = (
            relative_path.endswith("ReportsPage.tsx")
            and "background: '#f0fdf9'" in content
            and "fontFamily:" in content
            and any(token in content for token in ["padding: 20", "padding:'20px'", "padding: '20px'", 'padding: "20px"'])
            and any(token in content for token in ["minHeight: '100vh'", 'minHeight: "100vh"'])
            and any(
                token in content
                for token in [
                    "pageStyle: React.CSSProperties",
                    "headerStyle: React.CSSProperties",
                    "borderBottom: '2px solid #16a34a'",
                    'borderBottom: "2px solid #16a34a"',
                ]
            )
        )
        uses_disallowed_reports_blue_shell = (
            relative_path.endswith("ReportsPage.tsx")
            and "background: '#f3f6fb'" in content
            and "fontFamily:" in content
            and "录用与Offer管理" in content
            and any(token in content for token in ["padding: 24", "padding:'24px'", "padding: '24px'", 'padding: "24px"'])
        )
        uses_disallowed_statistics_blue_shell = (
            relative_path.endswith("StatisticsPage.tsx")
            and "background: '#f3f6fb'" in content
            and "padding: '24px 32px'" in content
            and "fontFamily:" in content
        )
        uses_disallowed_statistics_generic_shell = (
            relative_path.endswith("StatisticsPage.tsx")
            and "APP_PROFILE.productName" in content
            and "fontFamily:" in content
            and any(token in content for token in ["统计分析", "统计中心", "数据统计中心"])
            and any(token in content for token in ["padding: 24", "padding:'24px'", "padding: '24px'", 'padding: "24px"'])
        )
        uses_disallowed_statistics_centered_shell = (
            relative_path.endswith("StatisticsPage.tsx")
            and "const { productName } = APP_PROFILE" in content
            and "maxWidth: 1200" in content
            and "margin: '0 auto'" in content
            and "统计分析" in content
            and "分析中心" in content
        )
        uses_disallowed_statistics_green_shell = (
            relative_path.endswith("StatisticsPage.tsx")
            and "background: '#f0fdf9'" in content
            and any(token in content for token in ["padding: 24", "padding:'24px'", "padding: '24px'", 'padding: "24px"'])
            and any(token in content for token in ["minHeight: '100vh'", 'minHeight: "100vh"'])
            and "fontFamily:" in content
            and "APP_PROFILE.product_name" in content
        )
        uses_disallowed_statistics_title_shell = (
            relative_path.endswith("StatisticsPage.tsx")
            and "import React from 'react';" in content
            and "styles.container" in content
            and "styles.title" in content
            and "styles.subtitle" in content
            and "APP_PROFILE.productName" in content
            and "数据分析与看板" in content
        )
        uses_disallowed_statistics_plain_padding_shell = (
            relative_path.endswith("StatisticsPage.tsx")
            and "import React from 'react';" in content
            and "export default function StatisticsPage()" in content
            and any(token in content for token in ["padding: 24", "padding:'24px'", "padding: '24px'", 'padding: "24px"'])
            and "fontSize: 24" in content
            and "fontWeight: 600" in content
            and "APP_PROFILE.product_name" in content
        )
        uses_disallowed_statistics_rows_array_shell = (
            relative_path.endswith("StatisticsPage.tsx")
            and "const rows = [" in content
            and any(token in content for token in ["协同任务看板周报", "协同任务看板月报", "专题分析", "趋势稳定", "需持续跟踪"])
            and any(token in content for token in ["APP_PROFILE", "跨境冷链履约异常协同平台", "V1.0"])
        )
        uses_disallowed_statistics_heavy_shell = (
            relative_path.endswith("StatisticsPage.tsx")
            and any(
                token in content
                for token in [
                    "const StatisticsPage: React.FC",
                    "const { Title, Text } = Typography",
                    "BarChartOutlined",
                    "SearchOutlined",
                ]
            )
            and any(
                token in content
                for token in [
                    "import { Input, Button, Card, Row, Col, Typography } from 'antd';",
                    "import { Input, Button, Card, Row, Col, Typography, Space } from 'antd';",
                    "import { Input, Button, Card, Row, Col, Typography, Table } from 'antd';",
                ]
            )
        )
        is_valid = (
            bool(content)
            and "generated/appProfile" in content
            and "../generated/appProfile" in content
            and "../../generated/appProfile" not in content
            and "import APP_PROFILE from '../generated/appProfile'" not in content
            and "APP_PROFILE" in content
            and "ModuleShell" not in content
            and "模块开发中" not in content
            and not _contains_disallowed_frontend_reporting_copy(content)
            and "const mockData" not in content
            and "mockData:" not in content
            and exact_title_hit
            and business_anchor_hits >= required_anchor_hits
            and _looks_like_complete_typescript_source(content)
            and _imports_appear_before_runtime_code(content)
            and _has_component_default_export(content, component_name)
            and not uses_disallowed_records_light_shell
            and not uses_disallowed_records_array_shell
            and not uses_disallowed_workflow_white_shell
            and not uses_disallowed_workflow_blue_card_shell
            and not uses_disallowed_workflow_records_array_shell
            and not uses_disallowed_assets_records_array_shell
            and not uses_disallowed_workspace_heavy_antd_shell
            and not uses_disallowed_workspace_matrix_shell
            and not uses_disallowed_workspace_light_antd_shell
            and not uses_disallowed_orders_supplier_records_shell
            and not uses_disallowed_analytics_heavy_shell
            and not uses_disallowed_monitor_heavy_shell
            and not uses_disallowed_settings_heavy_shell
            and not uses_disallowed_settings_green_shell
            and not uses_disallowed_reports_green_shell
            and not uses_disallowed_reports_blue_shell
            and not uses_disallowed_statistics_blue_shell
            and not uses_disallowed_statistics_generic_shell
            and not uses_disallowed_statistics_centered_shell
            and not uses_disallowed_statistics_green_shell
            and not uses_disallowed_statistics_title_shell
            and not uses_disallowed_statistics_plain_padding_shell
            and not uses_disallowed_statistics_rows_array_shell
            and not uses_disallowed_statistics_heavy_shell
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
        hints.append(
            "如果当前只回补 App.tsx，请优先输出精简后的单文件路由壳：减少 import、状态、重复菜单配置和超长 JSX，避免再次返回过长 JSON。"
        )
        if module_routes:
            hints.append(
                "App.tsx 必须使用 Routes/Route 或 useRoutes 显式挂接这些模块路由: "
                + ", ".join(module_routes)
            )
        hints.append("App.tsx 不得输出 PlaceholderPage、'模块开发中' 或统一后台占位壳层。")
        hints.append("App.tsx 不得出现任务简报、平台入口概览、软件演示入口、开发情况汇报或任何写给平台拥有者/研发团队的说明性文案。")
        hints.append(
            "App.tsx 回补时应整体替换旧后台模板，不要保留 Layout、Sider、Menu、Dropdown、Breadcrumb、theme=\"dark\"、mode=\"inline\" 等后台壳层残留。"
        )
        hints.append(
            "App.tsx 也不要再写 `useMemo`、`useLocation`、`useNavigate`、`NavLink`、`Outlet`、`TabsProps`、`Tabs`，"
            "也不要导入 `Row, Col, Card, Button, Space` 这种整页装饰性组件组合；请压缩为更短的 `header/nav + Routes` 顶层路由壳。"
        )
        hints.append(
            "App.tsx 若上一版回退成 `import React from 'react';` + "
            "`import { Routes, Route, Navigate, Link } from 'react-router-dom';` 这类长路由壳，"
            "或同时出现 `Navigate to=` 与 `Link to=` 的通用导航/重定向模板，那么这一轮同样一律判失败；"
            "请整体改写成更短的真实任务壳层。"
        )
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
        if navigation_variant == "indexed" or chrome_treatment == "indexed_topbar":
            hints.append(
                "当前任务要求 indexed/indexed_topbar 壳层：App.tsx 必须使用顶部索引导航、顶部切换条或顶部主导航，并配合右侧摘要栏/概览区；禁止使用 Layout.Sider、Menu mode=\"inline\"、theme=\"dark\" 或任何左侧深色竖向导航实现。"
            )
        shell_layout_hint = str((profile.get("experience_blueprint") or {}).get("shell_layout_hint") or "").strip()
        if shell_layout_hint:
            hints.append(
                "App.tsx 必须落实该壳层描述，不得自行回退到通用后台模板："
                + shell_layout_hint
            )
    if "frontend/src/pages/Dashboard.tsx" in invalid_paths:
        hints.append(
            "Dashboard.tsx 必须直接读取 APP_PROFILE.product_name 与 APP_PROFILE.dashboard_metrics，并在页面中展示中文首页/工作台标题。"
        )
        hints.append(
            "Dashboard.tsx 必须使用 `export default function Dashboard()`；不要改成 `React.FC`、`HomeDashboard`、`OverviewPage` 或其他函数名。"
        )
        hints.append(
            "Dashboard.tsx 必须压缩成精简首页：保留 1 个中文 H1（如“系统首页”或“工作台”）、2~4 个统计块、1 个轻量表格/列表即可，避免长图标映射、大量 imports、长篇静态说明或超长 JSX。"
        )
        hints.append(
            "Dashboard.tsx 源码里必须逐字出现 `APP_PROFILE.product_name` 与 `APP_PROFILE.dashboard_metrics`；不要只写成 `const metrics = APP_PROFILE.dashboard_metrics ...`、`const productName = ...` 后面却不再直接引用原字段。"
        )
        hints.append("Dashboard.tsx 必须是正式面向最终用户的首页，不得出现任务简报、岗位工作台预览、开发汇报、处理建议说明等平台侧叙事。")
        hints.append(
            "Dashboard.tsx 若使用 `@ant-design/icons`，只允许使用这些已验证可用的图标名："
            + "、".join(sorted(_SUPPORTED_ANTD_ICON_NAMES))
            + "；禁止 `BriefcaseOutlined` 或其他当前依赖未导出的图标名，否则 verify_run 会编译失败。"
        )
        hints.append(
            "若上一版以 `import React from 'react'; import { Row, Col, Card, Statistic, Table, Tag, Progress, Button } from 'antd';` 这类大体量首页壳开头，请整体改写成更短的实现；优先保证函数名、标题和 APP_PROFILE 字段命中，不要把 token 花在装饰层。"
        )
        hints.append(
            "Dashboard.tsx 不要在组件外声明 `const items = [`、长数组、长映射或大型统计配置；请把 2~3 行轻量样例直接放进组件内部，避免再次生成过长首页壳。"
        )
        hints.append(
            "Dashboard.tsx 不要再写 `const fallbackMetrics = [`、`const metricCards = [` 或其他本地兜底指标数组；请直接基于 `APP_PROFILE.dashboard_metrics` 渲染 2~4 个统计块，不要回退成通用演示数据。"
        )
        hints.append(
            "Dashboard.tsx 不要再写 `const recentActivities = [`、`const activities = [` 或其他顶部最近动态数组；若需要列表，请在组件内部直接内联 2~3 行轻量记录。"
        )
        hints.append(
            "Dashboard.tsx 也不要再写 `const recentEvents = [` 这类事件数组，并搭配“温度超标 / 运输延迟 / 处理中 / 待处理”之类通用异常事件卡片；这仍然是泛化监控首页壳，不是当前任务首页。"
        )
        hints.append(
            "Dashboard.tsx 若上一版又写成 `import { Card, Statistic } from 'antd';`，"
            "并在组件里声明 `const recentEvents = [`，数组项字段继续使用 `code/type/status/time`，"
            "再配合 `E-001 / 温度超标 / 处理中 / 2025-06-01 10:30`、`E-002 / 运输延迟 / 待处理 / 2025-06-01 09:15` 这类通用异常事件，"
            "那么同样一律判失败；必须整体改回当前业务首页，而不是异常监控事件流模板。"
        )
        hints.append(
            "Dashboard.tsx 不要导入 `Typography`、不要写 `const { Title } = Typography`，也不要用 `Title`/`Paragraph` 这一类通用展示壳；请直接使用原生 `h1`、`p` 或最少量 `Card/Statistic` 组织首页。"
        )
        hints.append(
            "Dashboard.tsx 也不要写顶层或组件内的 `const columns = [`、`const dataSource = [` 或 `ColumnsType` 表格配置；不要使用 antd `Table columns` 这一整套写法。若需要轻量表格，请直接改成原生 `<table>` 并把 2~3 行数据内联到 JSX。"
        )
        hints.append(
            "Dashboard.tsx 不要再写 `const metrics = APP_PROFILE.dashboard_metrics || []`、`const metrics = (APP_PROFILE as any).dashboard_metrics`，"
            "也不要返回 `<div style={{ padding: 24 }}>` 或 `<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>` 这类通用轻壳；"
            "H1 必须是中文首页/工作台标题，不能直接把 `APP_PROFILE.product_name` 当成首页主标题，也不要回退成只有“工作台”标题 + 单个统计卡的白页。"
        )
        hints.append(
            "Dashboard.tsx 若上一版再次出现 `import { Card, Statistic } from 'antd'` + 图标导入，"
            "并返回 `<div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>` 这类米色轻壳首页，"
            "或直接用 `Card + Statistic + 3~4 个状态图标` 拼一个通用工作台壳，这一整类写法都判无效，必须整体换成更短、更贴近当前业务首页的实现。"
        )
        hints.append(
            "Dashboard.tsx 若上一版又回退成 `import React from 'react'; import { Card, Statistic } from 'antd';` 开头，"
            "再配合 `<div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 24px' }}>`、"
            "`异常监控总览` 标题或纵向堆叠的统计卡轻壳，这一整类写法同样判无效，必须整体改写为更短的正式首页。"
        )
        hints.append(
            "Dashboard.tsx 若上一版又写成 `import { Card, Statistic, Tag } from 'antd';` + `ExclamationCircleOutlined`，"
            "再配合 `<div style={{ padding: '1.5rem 2rem' }}>`、`冷链履约异常协同工作台` 这类领域名直出 H1、"
            "以及顶部一排告警卡/标签工作台壳，也一律判无效；必须回到更短的正式首页，不要再写监控大盘式轻壳。"
        )
        hints.append(
            "Dashboard.tsx 不要再声明 `const iconMap: Record<string, React.ReactNode>`、不要写成 `React.ReactNode` 图标字典，"
            "也不要导入 `CheckCircleOutlined + ExclamationCircleOutlined + ClockCircleOutlined + TeamOutlined` 这一组四图标再拼统计卡；"
            "这类 iconMap 监控大盘模板一律判无效。"
        )
        hints.append(
            "Dashboard.tsx 若上一版又写成 `import { Card, Statistic } from 'antd';`，"
            "并同时导入 `TeamOutlined + CalendarOutlined + FileTextOutlined + UserOutlined` 这一组四图标，"
            "再拼 3~4 张统计卡首页壳，那么同样一律判无效；必须改回更短的正式首页。"
        )
        hints.append(
            "Dashboard.tsx 若上一版又写成 `import { Card, Statistic } from 'antd';` + `const metrics = APP_PROFILE.dashboard_metrics;`，"
            "再配合 `<div style={{ margin: 24 }}>`、`display: 'flex' + gap: 16 + flexWrap: 'wrap'` 的统计卡壳，"
            "那么同样一律判无效；不要再写 `metrics.map(...)` 这种通用工作台模板。"
        )
        hints.append(
            "Dashboard.tsx 若上一版又写成 `import { Card, Statistic } from 'antd';`，"
            "并同时导入 `CalendarOutlined + TeamOutlined` 这一组图标，"
            "再配合 `<div style={{ padding: '16px' }}>`、`<h1>工作台</h1>`、"
            "`<p style={{ color: '#555' }}>{APP_PROFILE.product_name}</p>` 这种通用白页壳，"
            "那么同样一律判无效；必须改回更短的正式首页，不要再返回产品名副标题 + 统计卡轻壳。"
        )
        hints.append(
            "Dashboard.tsx 若上一版又写成 `import { Card, Statistic } from 'antd';`，"
            "再配合 `<div style={{ padding: '16px' }}>`、`<h1>工作台</h1>`、"
            "`<p style={{ color: '#555' }}>{APP_PROFILE.product_name}</p>`，"
            "并直接使用 `APP_PROFILE.dashboard_metrics.slice(0, 4).map(...)` 渲染 4 张统计卡，"
            "那么同样一律判无效；这仍然是通用工作台白页壳，不是当前任务需要的正式首页。"
        )
        hints.append(
            "Dashboard.tsx 若上一版又写成 `import { Card, Statistic } from 'antd';`，"
            "再配合 `<div style={{ padding: '32px 40px', maxWidth: 1200, margin: '0 auto' }}>`、"
            "`<h1 style={{ fontSize: 22, fontWeight: 600, marginBottom: 8 }}>系统首页</h1>`、"
            "以及紫色 `APP_PROFILE.product_name` 副标题轻壳，那么同样一律判无效；必须整体改回更短的正式首页。"
        )
        hints.append(
            "Dashboard.tsx 若上一版又写成 `import { Card, Statistic } from 'antd';`，"
            "并同时导入 `BarChartOutlined + ExclamationCircleOutlined + ClockCircleOutlined + FileTextOutlined`，"
            "再配合 `<div style={{ padding: '24px 32px', background: '#f0fdf9' }}>` 这种浅绿色统计卡首页壳，"
            "那么同样一律判无效；不要再返回多图标通用数据看板。"
        )
        hints.append(
            "Dashboard.tsx 若上一版又写成 `const recentBorrows = [`，"
            "并在列表里复用 `《计算机程序设计艺术》 / 《数据结构》 / 《算法导论》`、"
            "`最近借阅记录`、`图书 / 读者 / 日期 / 状态`、`借出 / 归还 / 逾期` 这一类图书借阅演示数据，"
            "那么同样一律判无效；这仍然是跨任务复用的通用首页壳，不是当前产品真实首页。"
        )
        hints.append(
            "Dashboard.tsx 若上一版又写成 `const recentExceptions = [`，"
            "并在数组里复用 `EXC-101 / EXC-102 / ORD-3201 / ORD-3202`、"
            "`温度超标 / 运输延迟`、`处理中 / 已恢复` 这类异常演示数据，"
            "再搭配 `ExclamationCircleOutlined + CheckCircleOutlined + ClockCircleOutlined` 统计卡，"
            "那么同样一律判无效；这仍然是泛化异常监控首页壳，不是当前任务真实首页。"
        )
        hints.append(
            "Dashboard.tsx 若上一版错误返回了 `frontend/src/App.tsx`、"
            "或返回内容里出现 `\"frontend/src/App.tsx\"` / `import { Routes, Route, Navigate, Link` 这类壳层路由代码，"
            "那么这一轮同样一律判失败；当前只允许重写 Dashboard.tsx，绝不能越界输出 App.tsx。"
        )
    if "frontend/src/pages/Login.tsx" in invalid_paths:
        hints.append(
            "Login.tsx 必须包含中文登录表单，并通过 onLogin、handleSubmit 或 localStorage(ipright_demo_auth) 完成登录态写入。"
        )
        hints.append("Login.tsx 只能呈现正式登录入口，不得出现平台入口概览、演示入口、任务摘要、角色说明书或写给内部团队的介绍文案。")
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
            f"{relative_path} 必须是 {title} 的真实业务页面。由于文件位于 frontend/src/pages 目录下，只能从 ../generated/appProfile 读取 APP_PROFILE；禁止写成 ../../generated/appProfile、默认导入或其他错误路径，不能使用 ModuleShell、模块开发中、mockData 或 testData 占位实现。"
        )
        hints.append(
            f"{relative_path} 导入 APP_PROFILE 时必须使用命名导入 `import {{ APP_PROFILE }} from '../generated/appProfile';`；禁止 `import APP_PROFILE from '../generated/appProfile'` 这类默认导入写法。"
        )
        hints.append(
            f"{relative_path} 必须导出默认组件，优先使用 `export default function {component_name}()`；如果先声明 `function {component_name}()` 或 `const {component_name} = ...`，文件末尾也必须显式 `export default {component_name};`。"
        )
        hints.append(
            f"{relative_path} 所有 import 必须放在文件顶部；禁止在组件定义、JSX 或其他运行时代码后面再出现 `import` 语句，否则 verify_run 会直接编译失败。"
        )
        hints.append(
            f"{relative_path} 的首屏主标题（H1、页面标题或最显著标题）必须逐字等于 `{title}`，不能改写成历史模块名、近义标题或通用业务名称。"
        )
        hints.append(
            f"{relative_path} 除了主标题命中 `{title}` 之外，正文还必须至少命中 2 个当前模块业务锚点（表头、样例数据、主操作、筛选提示或 highlight），不能只剩标题 + 产品名轻壳。"
        )
        hints.append(
            f"{relative_path} 必须是正式面向最终用户的产品界面，不得出现任务简报、平台说明、开发情况汇报、面向研发团队的提示或演示口径。"
        )
        if route:
            hints.append(f"{relative_path} 必须围绕路由 {route} 的业务语境组织页面内容，不得复用其他模块页面。")
        hints.append(
            f"{relative_path} 必须体现 page_variant={page_variant} 对应的信息组织方式，并根据本模块主题自主设计正文布局，不能套用统一后台骨架。"
        )
        hints.append(
            f"{relative_path} 本轮回补以最小可运行业务页为目标：允许只保留 1 个筛选区、1 个主操作和 1 张轻量表格/列表；不要堆叠 Modal、Drawer、复杂表单、多层 Tabs、长 columns render、useMemo/useCallback 或大段本地状态。"
        )
        hints.append(
            f"{relative_path} 请优先使用原生 table 或最简单的列表结构，尽量不要声明 interface/type、ColumnsType、长 data 数组或复杂映射函数；可直接在 JSX 中写入 2-4 行任务样例数据。"
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
        if page_variant == "workflow":
            hints.append(
                f"{relative_path} 若当前仍然过长，请压缩为“筛选条 + 阶段摘要 + 跟进表/列表”的轻量结构；不要再生成步骤条、时间轴、弹窗或多层联动。"
            )
        if page_variant == "workspace":
            hints.append(
                f"{relative_path} 若上一版仍出现 `import React, {{ useState }} from 'react'`、"
                "`import { Input, Button, Card, Tag, Statistic } from 'antd'`、"
                "`import { SearchOutlined, PlusOutlined } from '@ant-design/icons'`"
                " 或 `const [search, setSearch] = useState('')` 这类重型 antd 工作区模板，"
                "那么本轮必须整体改写为无 hooks 的原生轻量工作区页。"
            )
            hints.append(
                f"{relative_path} 若上一版仍出现 `<div style={{ background: '#f4f6fb', minHeight: '100vh', padding: 24 }}>`、"
                "`<div style={{ maxWidth: 1200, margin: '0 auto', background: '#ffffff', borderRadius: 8, padding: 24 }}>`"
                " 这类蓝底白卡居中轻壳，那么同样一律判失败；必须改回当前模块标题逐字命中的真实工作区页。"
            )
            hints.append(
                f"{relative_path} 若上一版仍出现 `import React from 'react'`、`import {{ Input, Button, Tag }} from 'antd'`、"
                "`import { SearchOutlined, PlusOutlined } from '@ant-design/icons'`，"
                "再配合 `<div style={{ padding: 24, background: '#f0fdf9', minHeight: '100vh' }}>` 这类绿色通用工作区壳，"
                "那么同样一律判失败；不能再退回 Input + 主按钮 + Tag 的泛化协同模板。"
            )
            hints.append(
                f"{relative_path} 若上一版仍出现 `import {{ useState }} from 'react'`、`import {{ Card, Input, Button, Tag }} from 'antd'`、"
                "`const [search, setSearch] = useState('')` 与 `SearchOutlined/PlusOutlined` 的组合，"
                "那么同样一律判失败；这仍然是通用工作区模板，不是当前模块真实业务页。"
            )
            hints.append(
                f"{relative_path} 若上一版仍出现 `import {{ useState }} from 'react'`、"
                "`import { Card, Row, Col, Statistic, Input, Button, Space, Tag, Table } from 'antd'`、"
                "`const [searchText, setSearchText] = useState('')` 与 `SearchOutlined/PlusOutlined` 的组合，"
                "那么同样一律判失败；这仍然是统计卡矩阵 + 检索框的通用工作区模板，不是当前模块真实业务页。"
            )
        if relative_path.endswith("OrdersPage.tsx"):
            hints.append(
                f"{relative_path} 若上一版仍出现 `import React from 'react'`、"
                "`import { Input, Button, Card, Space, Typography } from 'antd'`、"
                "`const { Title, Text } = Typography`、`const records = [`，"
                "并在数组里复用 `SUP-401/SUP-402`、`华辰材料/嘉远供应` 这类供应商题材样例，"
                "那么同样一律判失败；OrdersPage 必须改回当前模块标题逐字命中的真实订单业务页。"
            )
        if relative_path.endswith("WorkflowPage.tsx"):
            hints.append(
                f"{relative_path} 若上一版仍出现 `import React, {{ useState }} from 'react'`、`React.FC`、"
                "`Input/Card/Space/Tag`、默认导入 `import APP_PROFILE from '../generated/appProfile'`、"
                "或受控搜索输入，那么本轮必须整体改写为命名导入 APP_PROFILE 的无 hooks 原生轻量页面。"
            )
            hints.append(
                f"{relative_path} 若上一版仍出现 `const platformName = APP_PROFILE.product_name || '...'`、"
                "通用 `<div style=...>` 壳页面、或页面主标题没有逐字等于当前模块标题，"
                "那么本轮必须整体改写为当前模块标题直出 + 当前任务样例数据直出，不能只展示产品名。"
            )
            hints.append(
                f"{relative_path} 若上一版页面标题写成“候选人管理”等历史主题，或整页仍是通用轻壳而不是当前模块业务页，那么本轮必须整体重写。"
            )
            hints.append(
                f"{relative_path} 若上一版仍出现 `import {{ Button }} from 'antd'`，"
                "再配合统一蓝色内联样式壳（如 `#f3f6fb`/`#1e3a8a`/`#2563eb`）且只放一个主按钮或摘要文字，"
                "那么本轮必须整体重写为含筛选输入 + 业务摘要 + 原生表格/列表的真实业务页。"
            )
            hints.append(
                f"{relative_path} 若上一版仍出现 `import React from 'react'` + `import {{ APP_PROFILE }} from '../generated/appProfile'`，"
                "再配合白底通用内联样式壳（如 `#ffffff`/`#111`/`#555`）且 H1 写成“候选人管理”，"
                "那么本轮必须整体重写为当前模块标题逐字命中的真实业务页。"
            )
            hints.append(
                f"{relative_path} 若上一版仍出现 `const WorkflowPage = () =>`、顶层 `<div style={{ padding: 24 }}>`、"
                "先显示 `APP_PROFILE.product_name` 再把 H1 写成“候选人管理”的通用白页壳，"
                "那么本轮必须整体重写为当前模块标题逐字命中的真实业务页，并直接落下当前模块筛选提示、业务摘要与原生表格/列表。"
            )
            hints.append(
                f"{relative_path} 若上一版又写成 `<div style={{ color: '#888', fontSize: 12 }}>{{APP_PROFILE.product_name}} / 候选人管理</div>`，"
                "再配合顶层 `padding: 24` 白页壳，那么同样一律判失败；不能再输出产品名 / 历史主题的面包屑式轻壳。"
            )
            hints.append(
                f"{relative_path} 若上一版出现 `import React from 'react'` + `function WorkflowPage() {{ return ( <div style={{ padding: 24 }}> ... ) }}`，"
                "顶部先用灰色小字显示 `APP_PROFILE.product_name`，再在正文里放历史模块标题或泛化业务标题，"
                "那么同样一律判失败；这仍然只是产品名面包屑 + 通用轻壳，不是当前模块真实业务页。"
            )
            hints.append(
                f"{relative_path} 若上一版又写成 `const thStyle = ...`、`const tdStyle = ...`、`const records = [`，"
                "并在数组项里复用 `id/topic/role/status/tag/date` 这一套通用记录字段，"
                "再配合 `REC-001/REC-002` 或“图书管理平台读者管理”这类泛化主题，那么同样一律判失败；"
                "WorkflowPage 必须改回当前模块标题逐字命中的真实业务页。"
            )
        if relative_path.endswith("AssetsPage.tsx"):
            hints.append(
                f"{relative_path} 若上一版仍出现 `import React, {{ useState }} from 'react'`、`React.FC`、"
                "`Input/Card/Typography/Tag` 或受控搜索输入，那么本轮必须整体改写为无 hooks 的原生轻量列表页。"
            )
            hints.append(
                f"{relative_path} 若上一版仍出现 `function AssetsPage() {{ const items = [{{ id, topic, role, status, tag, updateTime }}] ... }}`、"
                "或把主题写成“候选人管理”/“人才档案库”/“应聘者全旅程管理”等历史模块，而不是当前模块标题，那么本轮必须整体重写。"
            )
            hints.append(
                f"{relative_path} 若上一版仍出现 `import React from 'react'`、`import {{ Button }} from 'antd'` + `import {{ APP_PROFILE }} from '../generated/appProfile'`，"
                "再配合通用 `<div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>` 轻壳并把 H1 写成“面试管理”，"
                "那么本轮必须整体重写为当前模块标题逐字命中的真实业务表页。"
            )
            hints.append(
                f"{relative_path} 若上一版又写成 `import React from 'react'` + `import {{ APP_PROFILE }} from '../generated/appProfile'`，"
                "再配合 `<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>` 蓝色轻壳，"
                "并把 H1 写成“面试流程管理”或把 `APP_PROFILE.productName` 当成正文说明，那么同样一律判失败；"
                "AssetsPage 必须改回当前模块标题逐字命中的真实业务页。"
            )
            hints.append(
                f"{relative_path} 若上一版又写成 `<div style={{ padding: '24px', maxWidth: '1200px', margin: '0 auto' }}>` 居中轻壳，"
                "并把 H1 写成“读者证管理”等其他资产/证照主题，顶部再用彩色产品名摘要替代真实业务筛选与台账内容，那么同样一律判失败；"
                "必须改回当前模块标题逐字命中的真实业务页，并直接落下当前任务样例字段。"
            )
            hints.append(
                f"{relative_path} 若上一版又写成 `const records = [`，并在数组项里复用 `id/topic/role/status/tag/updateTime` 这一套通用档案字段，"
                "再配合 `REC-001/REC-002` 或“图书管理平台借阅流通管理”这类泛化主题，那么同样一律判失败；"
                "AssetsPage 必须改回当前模块标题逐字命中的真实业务页。"
            )
        if relative_path.endswith("RecordsPage.tsx"):
            hints.append(
                f"{relative_path} 若上一版仍出现 `import React, {{ useState }} from 'react'`、`React.FC`、"
                "`Table/Input/Space/Typography/Tag` 或受控搜索输入，那么本轮必须整体改写为无 hooks 的原生检索表页。"
            )
            hints.append(
                f"{relative_path} 若上一版仍出现默认导入 `import APP_PROFILE from '../generated/appProfile'`、"
                "`const productName = APP_PROFILE?.productName || '...'`、"
                "或页面标题写成“招聘需求管理”/“院校客户管理”/“职位管理”/“职位与需求管理”等历史主题，那么本轮必须整体重写为当前模块标题逐字命中的检索表页。"
            )
            hints.append(
                f"{relative_path} 若上一版仍出现 `const data = [{{ id, topic, role, status, tag, time }}]`、"
                "`const data = [{ id, topic, role, status, tag, updateTime }]`、`MOD0-001`/`MOD0-002` 或“重点事项”这类泛化招聘需求数组，"
                "那么本轮必须改回当前模块真实表头与样例字段，不能继续复用通用数据壳。"
            )
            hints.append(
                f"{relative_path} 若上一版又回退成 `import React from 'react';` + `import {{ APP_PROFILE }} from '../generated/appProfile';`，"
                "再配合 `<div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>`、"
                "`display: 'flex' + justifyContent: 'space-between' + alignItems: 'center'` 的米色通用轻壳页，"
                "那么同样一律判失败；必须改回当前模块标题逐字命中的真实检索表页。"
            )
            hints.append(
                f"{relative_path} 若上一版又写成 `const records = [`，并在数组项里复用 `id/topic/role/status/tag/updateTime` 这一套通用档案字段，"
                "再配合 `REC-001/REC-002`、`图书档案管理协同跟进` 这类泛化主题，那么同样一律判失败；"
                "必须改回当前模块真实表头、真实样例行和真实主操作，不要再输出 records 演示数组壳。"
            )
        if page_variant == "assets":
            hints.append(
                f"{relative_path} 若当前仍然过长，请压缩为“资产筛选 + 主按钮 + 台账表”的轻量结构；不要再生成弹窗、抽屉、批量操作区或复杂状态映射。"
            )
        if page_variant == "records":
            hints.append(
                f"{relative_path} 若当前仍然过长，请压缩为“档案检索 + 新建入口 + 档案表”的轻量结构；不要再生成详情抽屉、批量操作、复杂筛选面板或标签墙。"
            )
        if page_variant == "reports":
            hints.append(
                f"{relative_path} 若当前仍然过长，请压缩为“筛选条 + 少量摘要卡 + 结果表/列表”的轻量结构；不要再生成图表库、Tabs、折叠区、下载弹窗或长篇分析说明。"
            )
        if page_variant == "studio":
            hints.append(
                f"{relative_path} 若当前仍然过长，请压缩为“标题区 + 阶段摘要带 + 主结果表/列表”或“标题区 + 关键节点摘要 + 执行结果区”的中台结构；"
                "不要再生成通用统计中心、纯图表看板、Tabs、下载弹窗、时间轴或长篇说明。"
            )
        if relative_path.endswith("ReportsPage.tsx"):
            hints.append(
                f"{relative_path} 若上一版仍出现 `import React, {{ useState }} from 'react'`、"
                "`Input/Table/Card/Row/Col/Statistic/Typography/Space`、"
                "`SearchOutlined`、`FileTextOutlined` 或通用重型 antd 报表页模板，"
                "那么本轮必须整体改写为无 hooks 的原生轻量报表页。"
            )
            hints.append(
                f"{relative_path} 若上一版又回退成 `<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`，"
                "并把 H1 写成“录用与Offer管理”这类历史主题，那么同样一律判失败；必须改回当前模块标题逐字命中的轻量报表页。"
            )
            hints.append(
                f"{relative_path} 若上一版又回退成 `const pageStyle: React.CSSProperties = ...`、"
                "`const headerStyle: React.CSSProperties = ...`、`borderBottom: '2px solid #16a34a'`，"
                "再配合 `<div style={{ padding: 20, background: '#f0fdf9', minHeight: '100vh' }}>` 这类浅绿色报表轻壳，"
                "那么同样一律判失败；必须改回当前模块标题逐字命中的真实报表页。"
            )
        if relative_path.endswith("AnalyticsPage.tsx"):
            hints.append(
                f"{relative_path} 若上一版仍出现 `const {{ Title, Text }} = Typography`、"
                "`Typography/Input/Button/Space/Card/Tag`、`SearchOutlined`、`PlusOutlined` 或 `const AnalyticsPage: React.FC = ...`，"
                "那么本轮必须整体改写为无 hooks 的原生轻量分析页。"
            )
        if relative_path.endswith("MonitorPage.tsx"):
            hints.append(
                f"{relative_path} 若上一版仍出现 `import {{ useState }} from 'react'`、"
                "`import { Card, Input, Button, Space, Tag, Table } from 'antd'`、"
                "`SearchOutlined`、`PlusOutlined` 或 `const [searchText, setSearchText] = useState('')`，"
                "那么本轮必须整体改写为无 hooks 的原生轻量监控页。"
            )
            hints.append(
                f"{relative_path} MonitorPage 只允许保留“筛选输入 + 主操作 + 结果表/列表”这类最小结构；"
                "不要再生成 Card/Table 组合、受控搜索状态、PlusOutlined 新建按钮壳或通用监控工作区模板。"
            )
        if relative_path.endswith("SettingsPage.tsx"):
            hints.append(
                f"{relative_path} 若上一版仍出现 `import React from 'react'`、"
                "`import { Input, Button, Tag, Space, Typography } from 'antd'`、"
                "`SearchOutlined`、`const {{ Title, Text }} = Typography` 或 `const thStyle: React.CSSProperties = ...`，"
                "那么本轮必须整体改写为无 hooks 的原生轻量设置页。"
            )
            hints.append(
                f"{relative_path} SettingsPage 只允许保留“设置项检索 + 保存入口 + 设置表/列表”这类最小结构；"
                "不要再生成 Typography 标题壳、Tag/Space 组合、受控搜索交互、复杂内联样式表头或通用系统设置模板。"
            )
            hints.append(
                f"{relative_path} 若上一版又回退成 `<div style={{ padding: 24, background: '#f0fdf9', minHeight: '100vh' }}>`、"
                "`const cellStyle = { border: '1px solid #bbf7d0', ... }`、"
                "`<h1 style={{ color: '#14532d', ... }}>` 这类浅绿色通用设置轻壳，那么同样一律判失败；"
                "必须改回当前模块标题逐字命中的真实设置业务页。"
            )
        if relative_path.endswith("StatisticsPage.tsx"):
            hints.append(
                f"{relative_path} 若上一版仍出现 `import React from 'react'`、"
                "`Input/Button/Card/Row/Col/Typography`、`SearchOutlined`、`BarChartOutlined`、"
                "`const {{ Title, Text }} = Typography` 或 `const StatisticsPage: React.FC = ...`，"
                "那么本轮必须整体改写为无 hooks 的原生轻量统计页。"
            )
            hints.append(
                f"{relative_path} 若上一版又回退成 `<div style={{ padding: '24px 32px', background: '#f3f6fb' }}>` 这类蓝色通用轻壳，"
                "那么同样一律判失败；必须改回当前模块标题逐字命中的轻量统计页。"
            )
            hints.append(
                f"{relative_path} 若上一版又写成 `const productName = APP_PROFILE.productName || '...'`，"
                "再配合 `<div style={{ padding: 24, fontFamily: 'system-ui, -apple-system, sans-serif' }}>`、"
                "把 H1 写成“统计分析”或其他通用统计标题，那么同样一律判失败；"
                "必须改回当前模块标题逐字命中的真实统计页，并直接落下当前任务的筛选提示、摘要块和样例表格。"
            )
            hints.append(
                f"{relative_path} 若上一版仍是 `function StatisticsPage() {{ const productName = APP_PROFILE.productName || '...'` 开头，"
                "再配合 `<h1 style={{ marginBottom: 8, fontSize: 24, fontWeight: 600 }}>统计分析</h1>`、"
                "`<div style={{ padding: 24, fontFamily: 'system-ui, -apple-system, sans-serif' }}>` 这类通用统计轻壳，"
                "那么同样一律判失败；必须整体改写成当前模块标题逐字命中的真实统计页。"
            )
            hints.append(
                f"{relative_path} 若上一版又写成 `const {{ productName }} = APP_PROFILE;`，"
                "再配合 `<div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>`、"
                "`<h1 style={{ margin: 0 }}>统计分析</h1>`、`{productName} - 分析中心` 这类居中通用统计壳，"
                "那么同样一律判失败；必须改回当前模块标题逐字命中的真实统计页。"
            )
            hints.append(
                f"{relative_path} 若上一版又回退成 `<div style={{ padding: 24, background: '#f0fdf9', minHeight: '100vh' }}>`，"
                "再配合 `fontFamily:`、`APP_PROFILE.product_name` 和浅绿色全页背景轻壳，"
                "那么同样一律判失败；这仍然是通用统计模板，不是当前模块逐字命中的真实统计页。"
            )
            hints.append(
                f"{relative_path} 若上一版又回退成 `import React from 'react';` 开头，"
                "并使用 `style={styles.container}`、`style={styles.title}`、`style={styles.subtitle}`，"
                "再把主标题写成“数据分析与看板”并直接展示 `APP_PROFILE.productName`，"
                "那么同样一律判失败；必须整体改写，不能再走通用数据看板模板。"
            )
            hints.append(
                f"{relative_path} 若上一版又回退成 `import React from 'react';` + `export default function StatisticsPage()`，"
                "再配合 `<div style={{ padding: '24px' }}>`、`<h1 style={{ fontSize: 24, fontWeight: 600 ... }}>`"
                " 和只展示 `APP_PROFILE.product_name` 的极简标题壳，那么同样一律判失败；"
                "必须改回当前模块标题逐字命中的真实统计页。"
            )
            hints.append(
                f"{relative_path} 若上一版又写成 `const rows = [`，"
                "并在数组项里复用“协同任务看板周报 / 协同任务看板月报 / 专题分析 / 趋势稳定 / 需持续跟踪”这类泛化分析描述，"
                "再把产品名或版本号塞进数组正文，那么同样一律判失败；"
                "StatisticsPage 必须改回当前模块标题逐字命中的真实统计页。"
            )
            if page_variant == "studio":
                hints.append(
                    f"{relative_path} 当前模块 page_variant=studio，若上一版仍回退成“统计分析 / 分析中心 / 数据分析与看板”这类通用统计页，"
                    "或没有直接落下当前任务样例里的履约单号、当前阶段、责任人、结果摘要等执行字段，"
                    "那么同样一律判失败；必须改成围绕当前模块标题组织的执行中台页。"
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
                allowed_batch_files = set(current_required_files)
                unexpected_paths = sorted(
                    relative_path
                    for relative_path in batch_files.keys()
                    if relative_path not in allowed_batch_files
                )
                for relative_path, content in batch_files.items():
                    if relative_path in allowed_batch_files and content:
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
                            (
                                "unexpected files returned: " + ", ".join(unexpected_paths)
                                + (
                                    "; missing generated files: " + ", ".join(pending_files[:8])
                                    if pending_files
                                    else ""
                                )
                            )
                            if unexpected_paths
                            else (
                                f"missing generated files: {', '.join(pending_files[:8])}"
                                if pending_files
                                else None
                            )
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
            "applied_required_file_count": 0,
            "applied_paths": [],
            "generated_paths": sorted(generated_files.keys()),
            "batches": batch_reports,
            "repaired_core_paths": [],
            "repaired_module_paths": [],
            "template_ui_fallback_used": False,
            "repaired_support_paths": [],
            "cleaned_metadata_paths": [],
            "apply_skipped_reason": None,
        }
        report.update(extra)
        return report

    generated_files = hydrate_missing_files_from_template(app_root, generated_files, codegen_requirements["required_files"])
    generated_files = _repair_generated_typescript_syntax(generated_files)
    generated_files, repaired_support_paths = _synthesize_support_runtime_files(
        generated_files,
        profile,
        codegen_requirements["required_files"],
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
                    retry_requirements["single_file_plaintext"] = (
                        len(required_chunk) == 1
                        and required_chunk[0] == "frontend/src/pages/Dashboard.tsx"
                    )
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
                        continue
                    regenerated_paths: list[str] = []
                    for relative_path, content in batch_files.items():
                        if relative_path in required_chunk and content:
                            generated_files[relative_path] = str(content)
                            regenerated_paths.append(relative_path)
                    generated_files, invalid_core_paths = repair_invalid_core_files(app_root, generated_files, profile)
                    remaining_chunk = [relative_path for relative_path in required_chunk if relative_path in invalid_core_paths]
                    if progress_callback is not None:
                        await progress_callback(
                            {
                                "phase": "attempt_completed",
                                "batch": "core_invalid_retry",
                                "attempt": attempt_no,
                                "required_files": list(retry_requirements["required_files"]),
                                "generated_paths": sorted(regenerated_paths),
                                "pending_files": remaining_chunk,
                                "fallback_to_template": bool(remaining_chunk),
                            }
                        )
                    batch_reports.append(
                        {
                            "batch": "core_invalid_retry",
                            "attempt": attempt_no,
                            "required_files": list(retry_requirements["required_files"]),
                            "generated_paths": sorted(regenerated_paths),
                            "fallback_to_template": bool(remaining_chunk),
                            "error": (
                                "still invalid after retry: " + ", ".join(remaining_chunk)
                                if remaining_chunk
                                else None
                            ),
                        }
                    )
                if not invalid_core_paths:
                    break
    repaired_core_paths: list[str] = []
    if invalid_core_paths:
        invalid_core_previews = {
            relative_path: _preview_generated_content(generated_files.get(relative_path, ""))
            for relative_path in invalid_core_paths
        }
        return _build_codegen_report(
            repaired_core_paths=sorted(repaired_core_paths),
            repaired_support_paths=sorted(repaired_support_paths),
            template_ui_fallback_used=False,
            invalid_core_paths=invalid_core_paths,
            invalid_core_previews=invalid_core_previews,
            apply_skipped_reason="invalid_core_paths",
        ), (
            "App code generation failed: missing or invalid LLM-generated core frontend files: "
            + ", ".join(invalid_core_paths)
        )
    generated_files = _repair_generated_typescript_syntax(generated_files)
    generated_files, invalid_module_paths = repair_invalid_module_pages(generated_files, profile)
    repaired_module_paths: list[str] = []
    template_ui_fallback_used = False
    if invalid_module_paths and batches:
        llm = get_llm_client()
        for attempt_no in range(1, _MODULE_INVALID_MAX_RETRY_ROUNDS + 1):
            retry_chunks = _chunk_required_files(invalid_module_paths, _MODULE_INVALID_RETRY_BATCH_SIZE)
            for required_chunk in retry_chunks:
                invalid_module_previews = {
                    relative_path: _preview_generated_content(generated_files.get(relative_path, ""))
                    for relative_path in required_chunk
                }
                retry_module_pages = _select_module_pages_for_files(codegen_requirements, required_chunk)
                for page in retry_module_pages:
                    page["retry_variation_attempt"] = attempt_no
                retry_requirements = {
                    **{
                        key: value
                        for key, value in codegen_requirements.items()
                        if key != "module_pages"
                    },
                    "required_files": list(required_chunk),
                    "module_pages": retry_module_pages,
                    "validation_hints": _build_module_validation_hints(profile, required_chunk),
                    "invalid_module_previews": invalid_module_previews,
                    "single_file_plaintext": len(required_chunk) == 1,
                    "module_retry_attempt": attempt_no,
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
                    continue
                regenerated_paths: list[str] = []
                unexpected_paths = sorted(
                    relative_path
                    for relative_path in batch_files.keys()
                    if relative_path not in required_chunk
                )
                for relative_path, content in batch_files.items():
                    if relative_path in required_chunk and content:
                        generated_files[relative_path] = str(content)
                        regenerated_paths.append(relative_path)
                generated_files, invalid_module_paths = repair_invalid_module_pages(generated_files, profile)
                remaining_chunk = [relative_path for relative_path in required_chunk if relative_path in invalid_module_paths]
                if progress_callback is not None:
                    await progress_callback(
                        {
                            "phase": "attempt_completed",
                            "batch": "module_invalid_retry",
                            "attempt": attempt_no,
                            "required_files": list(retry_requirements["required_files"]),
                            "generated_paths": sorted(regenerated_paths),
                            "pending_files": remaining_chunk,
                            "fallback_to_template": bool(remaining_chunk),
                        }
                    )
                batch_reports.append(
                    {
                        "batch": "module_invalid_retry",
                        "attempt": attempt_no,
                        "required_files": list(retry_requirements["required_files"]),
                        "generated_paths": sorted(regenerated_paths),
                        "fallback_to_template": bool(remaining_chunk),
                        "error": (
                            (
                                "unexpected files returned: " + ", ".join(unexpected_paths)
                                + (
                                    "; still invalid after retry: " + ", ".join(remaining_chunk)
                                    if remaining_chunk
                                    else ""
                                )
                            )
                            if unexpected_paths
                            else (
                                "still invalid after retry: " + ", ".join(remaining_chunk)
                                if remaining_chunk
                                else None
                            )
                        ),
                    }
                )
                if not invalid_module_paths:
                    break
            if not invalid_module_paths:
                break
    generated_files = _repair_generated_typescript_syntax(generated_files)
    if invalid_module_paths:
        invalid_module_previews = {
            relative_path: _preview_generated_content(generated_files.get(relative_path, ""))
            for relative_path in invalid_module_paths
        }
        return _build_codegen_report(
            repaired_core_paths=sorted(repaired_core_paths),
            repaired_module_paths=sorted(repaired_module_paths),
            repaired_support_paths=sorted(repaired_support_paths),
            template_ui_fallback_used=template_ui_fallback_used,
            invalid_module_paths=invalid_module_paths,
            invalid_module_previews=invalid_module_previews,
            apply_skipped_reason="invalid_module_paths",
        ), (
            "App code generation failed: missing or invalid LLM-generated module frontend files: "
            + ", ".join(invalid_module_paths)
        )
    generated_files = normalize_generated_frontend_files(generated_files)
    applied, apply_error, applied_paths, cleaned_metadata_paths = apply_generated_code_bundle(
        app_root,
        generated_files,
        codegen_requirements["required_files"],
    )
    if not applied:
        return _build_codegen_report(
            repaired_core_paths=sorted(repaired_core_paths),
            repaired_module_paths=sorted(repaired_module_paths),
            repaired_support_paths=sorted(repaired_support_paths),
            template_ui_fallback_used=template_ui_fallback_used,
            applied_required_file_count=len(applied_paths),
            applied_paths=applied_paths,
            cleaned_metadata_paths=cleaned_metadata_paths,
            apply_error=apply_error,
            apply_skipped_reason="apply_failed",
        ), f"App code generation failed: {apply_error}"

    sync_frontend_dependencies(os.path.join(app_root, "frontend"))

    return _build_codegen_report(
        repaired_core_paths=sorted(repaired_core_paths),
        repaired_module_paths=sorted(repaired_module_paths),
        repaired_support_paths=sorted(repaired_support_paths),
        template_ui_fallback_used=template_ui_fallback_used,
        applied_required_file_count=len(applied_paths),
        applied_paths=applied_paths,
        cleaned_metadata_paths=cleaned_metadata_paths,
    ), None
