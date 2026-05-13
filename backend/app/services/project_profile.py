from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import pprint
import re


DEFAULT_VERSION = "V1.0"
_GENERIC_TERMS = {
    "平台",
    "系统",
    "软件",
    "智能",
    "管理",
    "业务",
    "项目",
    "解决方案",
    "ai",
}
_REALISTIC_NAMES = [
    "周铭",
    "林嘉",
    "唐悦",
    "韩舟",
    "陈思远",
    "周可欣",
    "孙悦",
    "张岚",
    "许知夏",
    "顾言川",
    "罗宁",
    "沈清和",
]
_MODULE_ICONS = ["📋", "📈", "🗂️", "📦", "🧾", "🔍", "🚨", "⚙️", "👥", "💹"]


@dataclass(frozen=True)
class DomainPreset:
    key: str
    name: str
    scene: str
    short_name: str
    software_category: str
    core_entities: list[str]
    user_roles: list[str]
    modules: list[dict]
    dashboard_metrics: list[dict]
    industry_scope: str
    dev_tools: str
    support_env: str


def _slug_key(text: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", text).strip("-").lower()
    return value or "module"


def _build_module(
    title: str,
    route: str,
    icon: str,
    primary_action: str = "",
    filter_placeholder: str = "",
    table_headers: list[str] | None = None,
    rows: list[list[str]] | None = None,
    highlights: list[str] | None = None,
    description: str = "",
) -> dict:
    return {
        "key": _slug_key(title),
        "title": title,
        "route": route,
        "icon": icon,
        "primary_action": primary_action,
        "filter_placeholder": filter_placeholder,
        "table_headers": table_headers or [],
        "rows": rows or [],
        "highlights": highlights or [],
        "description": description,
    }


def _marketing_preset() -> DomainPreset:
    return DomainPreset(
        key="marketing",
        name="营销投放",
        scene="内容营销与投放运营",
        short_name="营销投放",
        software_category="信息管理软件",
        core_entities=["达人", "品牌方", "投放计划", "素材", "复盘数据"],
        user_roles=["管理员", "运营经理", "投放专员", "数据分析师", "财务审核员"],
        dashboard_metrics=[
            {"title": "活跃项目", "value": "18", "color": "#1677ff"},
            {"title": "重点模块", "value": "8", "color": "#52c41a"},
            {"title": "待办事项", "value": "12", "color": "#faad14"},
            {"title": "角色数量", "value": "5", "color": "#722ed1"},
        ],
        modules=[
            _build_module("达人库管理", "/talents", "👥"),
            _build_module("品牌客户管理", "/clients", "🏢"),
            _build_module("投放计划管理", "/campaigns", "🚀"),
            _build_module("素材中心", "/assets", "🖼️"),
            _build_module("数据复盘中心", "/analytics", "📈"),
            _build_module("结算与对账", "/settlements", "💰"),
            _build_module("预警与风险中心", "/risks", "🚨"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        industry_scope="品牌营销、社媒运营、达人投放、内容种草、电商增长",
        dev_tools="Python 3.11、FastAPI、React、TypeScript、Vite、python-docx、PostgreSQL",
        support_env="主流 Chromium 内核浏览器、Node.js 18+、Python 3.11+、PostgreSQL 或 SQLite",
    )


def _supply_chain_preset() -> DomainPreset:
    return DomainPreset(
        key="supply_chain",
        name="供应链协同",
        scene="采购协同、库存控制、订单履约与供应商联动",
        short_name="供应链协同",
        software_category="供应链管理软件",
        core_entities=["采购单", "供应商", "库存批次", "销售订单", "履约节点"],
        user_roles=["管理员", "采购经理", "仓储主管", "供应商专员", "财务结算员"],
        dashboard_metrics=[
            {"title": "在途订单", "value": "26", "color": "#1677ff"},
            {"title": "低库存预警", "value": "7", "color": "#fa8c16"},
            {"title": "协同供应商", "value": "15", "color": "#13c2c2"},
            {"title": "待结算单据", "value": "9", "color": "#722ed1"},
        ],
        modules=[
            _build_module("采购管理", "/purchases", "🧾"),
            _build_module("销售管理", "/sales", "💼"),
            _build_module("库存管理", "/inventory", "📦"),
            _build_module("供应商管理", "/suppliers", "🤝"),
            _build_module("订单履约中心", "/orders", "🚚"),
            _build_module("结算对账", "/settlements", "💰"),
            _build_module("预警中心", "/alerts", "🚨"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        industry_scope="采购协同、仓储履约、供应商协作、订单交付、结算对账",
        dev_tools="Python 3.11、FastAPI、React、TypeScript、Vite、python-docx、PostgreSQL",
        support_env="主流 Chromium 内核浏览器、Node.js 18+、Python 3.11+、PostgreSQL 或 SQLite",
    )


def _finance_preset() -> DomainPreset:
    return DomainPreset(
        key="finance",
        name="投研风控",
        scene="投研分析、风险监测、交易执行与合规留痕",
        short_name="投研风控",
        software_category="金融分析软件",
        core_entities=["策略组合", "风险指标", "交易指令", "行情快照", "预警事件"],
        user_roles=["管理员", "策略研究员", "风控主管", "交易员", "合规审计员"],
        dashboard_metrics=[
            {"title": "监控组合", "value": "18", "color": "#1677ff"},
            {"title": "预警事件", "value": "5", "color": "#f5222d"},
            {"title": "待复核指令", "value": "11", "color": "#faad14"},
            {"title": "合规检查", "value": "23", "color": "#722ed1"},
        ],
        modules=[
            _build_module("策略研究中心", "/strategies", "📈"),
            _build_module("交易执行监控", "/trades", "💹"),
            _build_module("风险预警台", "/risks", "🚨"),
            _build_module("组合分析中心", "/portfolios", "🧠"),
            _build_module("行情数据管理", "/market-data", "📊"),
            _build_module("合规审计台", "/compliance", "🧾"),
            _build_module("报表中心", "/reports", "📋"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        industry_scope="投研分析、量化研究、交易执行、风控预警、合规审计",
        dev_tools="Python 3.11、FastAPI、React、TypeScript、Vite、python-docx、PostgreSQL",
        support_env="主流 Chromium 内核浏览器、Node.js 18+、Python 3.11+、PostgreSQL 或 SQLite",
    )


def _energy_preset() -> DomainPreset:
    return DomainPreset(
        key="energy",
        name="能源运维",
        scene="能耗监测、设备巡检、告警处置与工单协同",
        short_name="能源运维",
        software_category="运维管理软件",
        core_entities=["站点", "设备", "能耗曲线", "工单", "告警"],
        user_roles=["管理员", "运维主管", "设备专员", "值班工程师", "能效分析师"],
        dashboard_metrics=[
            {"title": "监测站点", "value": "31", "color": "#1677ff"},
            {"title": "巡检任务", "value": "14", "color": "#52c41a"},
            {"title": "异常告警", "value": "6", "color": "#f5222d"},
            {"title": "节能专题", "value": "9", "color": "#13c2c2"},
        ],
        modules=[
            _build_module("能耗总览", "/energy", "⚡"),
            _build_module("设备巡检中心", "/inspection", "🛠️"),
            _build_module("工单调度台", "/workorders", "🗂️"),
            _build_module("告警联动中心", "/alerts", "🚨"),
            _build_module("资产台账", "/assets", "🏭"),
            _build_module("能效分析中心", "/efficiency", "📈"),
            _build_module("报表中心", "/reports", "📋"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        industry_scope="园区运维、设备管理、能耗监测、巡检协同、告警处置",
        dev_tools="Python 3.11、FastAPI、React、TypeScript、Vite、python-docx、PostgreSQL",
        support_env="主流 Chromium 内核浏览器、Node.js 18+、Python 3.11+、PostgreSQL 或 SQLite",
    )


def _manufacturing_preset() -> DomainPreset:
    return DomainPreset(
        key="manufacturing",
        name="生产制造",
        scene="生产排程、质量追溯、设备协同与工序监控",
        short_name="生产制造",
        software_category="制造执行软件",
        core_entities=["工单", "工序", "设备", "批次", "质检记录"],
        user_roles=["管理员", "生产主管", "质检员", "设备工程师", "计划专员"],
        dashboard_metrics=[
            {"title": "排产工单", "value": "42", "color": "#1677ff"},
            {"title": "质检批次", "value": "19", "color": "#52c41a"},
            {"title": "停机事件", "value": "3", "color": "#f5222d"},
            {"title": "待复核工序", "value": "12", "color": "#722ed1"},
        ],
        modules=[
            _build_module("生产排程中心", "/scheduling", "🏭"),
            _build_module("工序执行台", "/operations", "⚙️"),
            _build_module("质量追溯中心", "/quality", "🔎"),
            _build_module("设备管理台", "/equipment", "🛠️"),
            _build_module("批次物料管理", "/batches", "📦"),
            _build_module("异常预警台", "/alerts", "🚨"),
            _build_module("报表中心", "/reports", "📋"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        industry_scope="生产排程、设备协同、质量追溯、批次管理、制造执行",
        dev_tools="Python 3.11、FastAPI、React、TypeScript、Vite、python-docx、PostgreSQL",
        support_env="主流 Chromium 内核浏览器、Node.js 18+、Python 3.11+、PostgreSQL 或 SQLite",
    )


def _healthcare_preset() -> DomainPreset:
    return DomainPreset(
        key="healthcare",
        name="医疗服务",
        scene="档案管理、服务跟踪、质量复核与风险提醒",
        short_name="医疗服务",
        software_category="医疗信息软件",
        core_entities=["档案", "服务记录", "科室", "随访任务", "质控事件"],
        user_roles=["管理员", "科室主任", "质控专员", "服务专员", "数据管理员"],
        dashboard_metrics=[
            {"title": "在管档案", "value": "68", "color": "#1677ff"},
            {"title": "待随访任务", "value": "13", "color": "#52c41a"},
            {"title": "质控提醒", "value": "4", "color": "#f5222d"},
            {"title": "科室覆盖", "value": "12", "color": "#722ed1"},
        ],
        modules=[
            _build_module("档案中心", "/records", "🧾"),
            _build_module("服务跟踪台", "/services", "🩺"),
            _build_module("随访管理", "/follow-ups", "📞"),
            _build_module("质控复核中心", "/quality", "✅"),
            _build_module("预警中心", "/alerts", "🚨"),
            _build_module("统计分析", "/analytics", "📈"),
            _build_module("报表中心", "/reports", "📋"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        industry_scope="医疗服务、档案管理、随访协同、质控复核、统计分析",
        dev_tools="Python 3.11、FastAPI、React、TypeScript、Vite、python-docx、PostgreSQL",
        support_env="主流 Chromium 内核浏览器、Node.js 18+、Python 3.11+、PostgreSQL 或 SQLite",
    )


def _media_preset() -> DomainPreset:
    return DomainPreset(
        key="media",
        name="内容发行",
        scene="内容编排、演员协同、用户反馈运营与数据复盘",
        short_name="内容发行",
        software_category="内容管理软件",
        core_entities=["剧集", "演员", "标签分类", "用户评论", "播放数据"],
        user_roles=["管理员", "内容运营", "选角统筹", "社区客服", "数据策划"],
        dashboard_metrics=[
            {"title": "在运营剧集", "value": "24", "color": "#1677ff"},
            {"title": "待上架内容", "value": "9", "color": "#fa8c16"},
            {"title": "重点评论", "value": "15", "color": "#13c2c2"},
            {"title": "周复盘专题", "value": "6", "color": "#722ed1"},
        ],
        modules=[
            _build_module("剧集管理", "/series", "🎬"),
            _build_module("演员管理", "/actors", "🎭"),
            _build_module("分类管理", "/categories", "🗂️"),
            _build_module("用户管理", "/users", "👥"),
            _build_module("评论管理", "/comments", "💬"),
            _build_module("数据统计", "/statistics", "📊"),
            _build_module("内容排期", "/schedules", "🗓️"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        industry_scope="内容平台、短剧运营、剧集发行、社区反馈、数据复盘",
        dev_tools="Python 3.11、FastAPI、React、TypeScript、Vite、python-docx、PostgreSQL",
        support_env="主流 Chromium 内核浏览器、Node.js 18+、Python 3.11+、PostgreSQL 或 SQLite",
    )


def _media_module_variants() -> list[list[dict]]:
    return [
        [
            _build_module("剧集管理", "/series", "🎬"),
            _build_module("演员管理", "/actors", "🎭"),
            _build_module("分类管理", "/categories", "🗂️"),
            _build_module("评论管理", "/comments", "💬"),
            _build_module("数据统计", "/statistics", "📊"),
            _build_module("投放计划", "/campaigns", "🚀"),
            _build_module("排期管理", "/schedules", "🗓️"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        [
            _build_module("内容库管理", "/series", "🎞️"),
            _build_module("剧集审核", "/reviews", "✅"),
            _build_module("演员协同", "/actors", "🎭"),
            _build_module("社区反馈", "/comments", "💬"),
            _build_module("投放管理", "/campaigns", "🚀"),
            _build_module("播放复盘", "/statistics", "📈"),
            _build_module("排期管理", "/schedules", "🗓️"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        [
            _build_module("短剧内容管理", "/series", "🎬"),
            _build_module("创作者与演员管理", "/actors", "🎭"),
            _build_module("广告投放管理", "/campaigns", "🚀"),
            _build_module("排期管理", "/schedules", "🗓️"),
            _build_module("播放数据统计", "/statistics", "📊"),
            _build_module("评论运营", "/comments", "💬"),
            _build_module("标签推荐", "/categories", "🏷️"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
    ]


def _generic_preset() -> DomainPreset:
    return DomainPreset(
        key="generic",
        name="综合运营管理",
        scene="综合业务管理与流程协同",
        short_name="综合运营",
        software_category="行业管理软件",
        core_entities=["客户", "项目", "资料", "报表", "任务"],
        user_roles=["管理员", "业务主管", "运营专员", "审计人员", "维护人员"],
        dashboard_metrics=[
            {"title": "业务项目", "value": "12", "color": "#1677ff"},
            {"title": "在管模块", "value": "8", "color": "#52c41a"},
            {"title": "待处理事项", "value": "6", "color": "#faad14"},
            {"title": "在线角色", "value": "5", "color": "#722ed1"},
        ],
        modules=[
            _build_module("客户与对象管理", "/records", "👥"),
            _build_module("流程计划管理", "/workflow", "🗂️"),
            _build_module("资料中心", "/assets", "📁"),
            _build_module("业务分析", "/analytics", "📈"),
            _build_module("报表中心", "/reports", "📋"),
            _build_module("风险与提醒", "/alerts", "🚨"),
            _build_module("审计留痕", "/audit", "🧾"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        industry_scope="通用行业管理、项目运营、资料流转、流程协同",
        dev_tools="Python 3.11、FastAPI、React、TypeScript、Vite、python-docx、PostgreSQL",
        support_env="主流 Chromium 内核浏览器、Node.js 18+、Python 3.11+、PostgreSQL 或 SQLite",
    )


def _select_preset(keyword: str, product_name: str, industry: str | None) -> DomainPreset:
    source = " ".join(
        filter(
            None,
            [
                _clean_phrase(str(keyword or "")),
                _clean_phrase(str(product_name or "")),
                _clean_phrase(str(industry or "")),
            ],
        )
    ).lower()
    preset_tokens: list[tuple[DomainPreset, list[str]]] = [
        (_media_preset(), ["短剧", "剧集", "演员", "影视", "片单", "内容平台", "评论", "番剧", "节目"]),
        (_marketing_preset(), ["广告", "投放", "kol", "达人", "小红书", "营销", "种草", "流量", "品牌"]),
        (_supply_chain_preset(), ["供应链", "采购", "仓储", "库存", "物流", "履约", "供应商", "订单", "对账"]),
        (_finance_preset(), ["股票", "证券", "基金", "量化", "交易", "投研", "风控", "合规", "因子"]),
        (_energy_preset(), ["能耗", "园区", "设备", "巡检", "工单", "告警", "电力", "能源", "运维"]),
        (_manufacturing_preset(), ["制造", "生产", "工厂", "工序", "排程", "质检", "车间", "批次"]),
        (_healthcare_preset(), ["医疗", "医院", "门诊", "病案", "随访", "质控", "护理", "科室"]),
    ]
    for preset, tokens in preset_tokens:
        if any(token in source for token in tokens):
            return preset
    return _generic_preset()


def _short_name(product_name: str, fallback: str) -> str:
    cleaned = re.sub(r"[（(].*?[)）]", "", product_name).strip()
    return cleaned[:12] if cleaned else fallback


def _ascii_token(text: str, fallback: str) -> str:
    token = re.sub(r"[^0-9A-Za-z]+", "", text or "").upper()
    return token[:12] if token else fallback


def _product_code(keyword: str, product_name: str) -> str:
    seed = f"{keyword}|{product_name}".encode("utf-8")
    digest = hashlib.md5(seed).hexdigest()[:6].upper()
    return f"APP-{digest}"


def _nav_code(path: str, label: str, index: int) -> str:
    token = re.sub(r"[^0-9A-Za-z]+", "", (path or "").strip("/")).upper()
    if token:
        return token[:10]
    label_token = _ascii_token(label, f"MOD{index:02d}")
    return label_token or f"MOD{index:02d}"


def _ensure_min_length(text: str, minimum: int, filler: str) -> str:
    normalized = (text or "").strip()
    if len(normalized) >= minimum:
        return normalized
    parts = [normalized] if normalized else []
    while len("".join(parts)) < minimum:
        parts.append(filler)
    return "".join(parts)


def _clean_phrase(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _split_terms(*texts: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9+\-.]*|[\u4e00-\u9fff]{2,}", text or ""):
            normalized = token.strip("（）()[]【】,，。；;：:")
            if not normalized:
                continue
            lower = normalized.lower()
            if lower in _GENERIC_TERMS or normalized in _GENERIC_TERMS:
                continue
            if lower in seen:
                continue
            seen.add(lower)
            terms.append(normalized)
    return terms


def _pick_names(seed: str, count: int) -> list[str]:
    offset = int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:4], 16) % len(_REALISTIC_NAMES)
    return [_REALISTIC_NAMES[(offset + idx) % len(_REALISTIC_NAMES)] for idx in range(count)]


def _seed_index(seed: str, modulo: int) -> int:
    if modulo <= 0:
        return 0
    return int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:8], 16) % modulo


def _pick_experience_blueprint(product_code: str, preset_key: str) -> dict:
    blueprints = [
        {
            "name": "command_hub",
            "login_variant": "spotlight",
            "dashboard_variant": "command",
            "module_variants": ["operations", "workspace", "insight"],
            "navigation_variant": "sidebar",
            "tone": "强调执行节奏、状态看板与统一调度",
        },
        {
            "name": "analysis_studio",
            "login_variant": "briefing",
            "dashboard_variant": "insight",
            "module_variants": ["insight", "records", "workspace"],
            "navigation_variant": "indexed",
            "tone": "强调分析结论、关键洞察与对比视图",
        },
        {
            "name": "collaboration_workspace",
            "login_variant": "workspace",
            "dashboard_variant": "workspace",
            "module_variants": ["workspace", "operations", "records"],
            "navigation_variant": "sectioned",
            "tone": "强调岗位协同、分区工作台与任务闭环",
        },
    ]
    return blueprints[_seed_index(f"{product_code}|{preset_key}", len(blueprints))]


def _module_kind(title: str) -> str:
    if any(token in title for token in ["报表", "分析", "复盘", "统计", "看板", "指标"]):
        return "analytics"
    if any(token in title for token in ["设置", "配置", "参数", "权限"]):
        return "settings"
    if any(token in title for token in ["风险", "预警", "提醒", "告警"]):
        return "alerts"
    if any(token in title for token in ["用户", "角色", "账户", "成员"]):
        return "users"
    if any(token in title for token in ["交易", "订单", "执行", "调仓", "策略"]):
        return "actions"
    return "records"


def _module_route_hint(title: str) -> str | None:
    mapping = [
        (["剧集", "片单", "内容库"], "/series"),
        (["创作者", "演员", "艺人"], "/actors"),
        (["广告投放", "投放计划", "投放", "campaign"], "/campaigns"),
        (["分类", "标签", "题材"], "/categories"),
        (["用户", "账号", "会员"], "/users"),
        (["评论", "反馈", "社区"], "/comments"),
        (["数据统计", "统计", "分析", "复盘", "看板"], "/statistics"),
        (["排期", "日历", "档期"], "/schedules"),
        (["预警", "提醒", "告警"], "/alerts"),
        (["设置", "配置", "权限"], "/settings"),
    ]
    for tokens, route in mapping:
        if any(token in title for token in tokens):
            return route
    return None


def _preset_modules_for_product(preset: DomainPreset, product_code: str) -> list[dict]:
    if preset.key != "media":
        return list(preset.modules)
    variants = _media_module_variants()
    return [dict(module) for module in variants[_seed_index(f"{preset.key}|{product_code}", len(variants))]]


def _match_preset_module(preset_modules: list[dict], title: str, index: int) -> dict:
    for module in preset_modules:
        if module.get("title") == title:
            return dict(module)
    hinted_route = _module_route_hint(title)
    if hinted_route:
        for module in preset_modules:
            if module.get("route") == hinted_route:
                return dict(module)
    if index < len(preset_modules):
        return dict(preset_modules[index])
    return _build_module(title, "", _MODULE_ICONS[index % len(_MODULE_ICONS)])


def _module_route(title: str, index: int, fallback_route: str, page_routes: list[str]) -> str:
    hinted_route = _module_route_hint(title)
    if hinted_route:
        return hinted_route
    if fallback_route:
        return fallback_route
    if len(page_routes) > index + 2 and page_routes[index + 2]:
        return page_routes[index + 2]
    return f"/{_slug_key(title)}"


def _module_headers(kind: str) -> list[str]:
    if kind == "analytics":
        return ["分析编号", "分析主题", "统计维度", "负责人", "核心结论", "更新时间"]
    if kind == "settings":
        return ["配置项", "当前值", "适用范围", "维护角色", "更新时间", "状态"]
    if kind == "alerts":
        return ["预警编号", "预警主题", "影响范围", "责任角色", "处理状态", "发现时间"]
    if kind == "users":
        return ["账号编号", "姓名", "角色", "负责范围", "状态", "最近更新"]
    if kind == "actions":
        return ["任务编号", "任务主题", "执行人", "当前阶段", "结果摘要", "更新时间"]
    return ["记录编号", "主题名称", "责任角色", "当前状态", "业务标签", "更新时间"]


def _module_primary_action(title: str) -> str:
    if any(token in title for token in ["报表", "分析", "复盘", "统计"]):
        return f"生成{title}"
    if any(token in title for token in ["设置", "配置", "权限"]):
        return "保存配置"
    if any(token in title for token in ["风险", "预警", "提醒", "告警"]):
        return "新增预警规则"
    if any(token in title for token in ["用户", "角色", "账户", "成员"]):
        return "新增角色账号"
    if "剧集" in title:
        return "新建剧集并维护上架信息"
    if "演员" in title:
        return "新增演员资料并关联作品"
    if "分类" in title:
        return "维护分类标签"
    if "评论" in title:
        return "审核评论并处理反馈"
    return f"新建{title}事项"


def _module_filter(title: str, focus_terms: list[str]) -> str:
    focus = "/".join(focus_terms[:2]) or "关键字/负责人/状态"
    return f"搜索{title}相关的{focus}"


def _module_rows(
    title: str,
    kind: str,
    index: int,
    keyword: str,
    product_code: str,
    roles: list[str],
    focus_terms: list[str],
) -> list[list[str]]:
    base_code = _ascii_token(title, f"MOD{index + 1:02d}")[:4]
    names = _pick_names(f"{product_code}|{title}", 3)
    focus_a = focus_terms[0] if focus_terms else keyword
    focus_b = focus_terms[1] if len(focus_terms) > 1 else title
    role_a = roles[0] if roles else "管理员"
    role_b = roles[1] if len(roles) > 1 else role_a
    role_c = roles[2] if len(roles) > 2 else role_b
    if kind == "analytics":
        return [
            [f"{base_code}-301", f"{title}周报", focus_a, names[0], f"{focus_a}趋势稳定", "2026-05-02"],
            [f"{base_code}-302", f"{title}月报", focus_b, names[1], f"{focus_b}需持续跟踪", "2026-05-01"],
            [f"{base_code}-303", f"{keyword}专题分析", title, names[2], "输出优化建议", "2026-04-30"],
        ]
    if kind == "settings":
        return [
            [f"{title}默认视图", "概览模式", title, role_a, "2026-05-02", "启用"],
            [f"{focus_a}阈值", "自动校验", keyword, role_b, "2026-05-01", "启用"],
            [f"{product_code}通知规则", "站内提醒", "全局", role_c, "2026-04-30", "启用"],
        ]
    if kind == "alerts":
        return [
            [f"{base_code}-501", f"{focus_a}阈值预警", title, role_a, "处理中", "2026-05-02"],
            [f"{base_code}-502", f"{focus_b}状态异常", keyword, role_b, "待处理", "2026-05-01"],
            [f"{base_code}-503", f"{title}超期提醒", product_code, role_c, "已关闭", "2026-04-30"],
        ]
    if kind == "users":
        return [
            [f"{base_code}-101", names[0], role_a, title, "启用", "2026-05-02"],
            [f"{base_code}-102", names[1], role_b, keyword, "处理中", "2026-05-01"],
            [f"{base_code}-103", names[2], role_c, focus_a, "已归档", "2026-04-30"],
        ]
    if kind == "actions":
        return [
            [f"{base_code}-201", f"{focus_a}执行任务", names[0], "待校验", f"{title}进入执行阶段", "2026-05-02"],
            [f"{base_code}-202", f"{focus_b}运行任务", names[1], "执行中", f"{keyword}结果回写", "2026-05-01"],
            [f"{base_code}-203", f"{title}复核任务", names[2], "已完成", f"{product_code}留痕归档", "2026-04-30"],
        ]
    return [
        [f"{base_code}-001", f"{focus_a}{title}", role_a, "处理中", focus_b, "2026-05-02"],
        [f"{base_code}-002", f"{keyword}重点事项", role_b, "待审核", title, "2026-05-01"],
        [f"{base_code}-003", f"{product_code}{title}", role_c, "已完成", focus_a, "2026-04-30"],
    ]


def _module_domain_focus(title: str, keyword: str, focus_terms: list[str]) -> str:
    focus = "、".join(focus_terms[:3]) or keyword or title
    if "剧集" in title:
        return "剧集条目、题材标签与上架节奏"
    if "演员" in title:
        return "演员资料、参演作品与合作状态"
    if "分类" in title:
        return "内容题材、运营标签与推荐分组"
    if "评论" in title:
        return "评论内容、违规风险与回复状态"
    if "用户" in title:
        return "账号身份、角色归属与负责范围"
    kind = _module_kind(title)
    if kind == "analytics":
        return "分析主题、统计维度与核心结论"
    if kind == "settings":
        return "配置项、适用范围与启停状态"
    if kind == "alerts":
        return "异常事件、影响范围与处置进度"
    if kind == "actions":
        return "执行阶段、责任人和结果摘要"
    return focus


def _module_highlights(title: str, keyword: str, focus_terms: list[str], role_phrase: str) -> list[str]:
    focus = _module_domain_focus(title, keyword, focus_terms)
    kind = _module_kind(title)
    if "剧集" in title:
        return [
            "支持围绕剧集名称、题材、上架状态和更新进度进行统一检索与维护",
            f"支持{role_phrase}围绕排期、上架和内容编修协同处理剧集事项",
            "支持沉淀剧集资料、标签信息和运营处理记录，便于后续复盘与导出",
        ]
    if "演员" in title:
        return [
            "支持维护演员基础资料、合作状态和参演作品关联关系",
            f"支持{role_phrase}按职责查看演员档案、档期信息与处理记录",
            "支持围绕演员资料输出检索结果、合作清单与留痕材料",
        ]
    if "分类" in title:
        return [
            "支持维护题材、风格、标签等多层分类结构",
            "支持将分类结果与剧集内容绑定，提升运营分组与推荐效率",
            f"支持{role_phrase}依据标签口径协同整理内容资料与页面结果",
        ]
    if "评论" in title:
        return [
            "支持按剧集、用户和风险状态筛选评论并快速定位重点反馈",
            "支持批量审核、隐藏、回复等评论处理动作",
            f"支持{role_phrase}围绕舆情反馈沉淀处置记录与复核依据",
        ]
    if "用户" in title:
        return [
            "支持按角色批量维护账号、负责范围与启停状态",
            "支持查看账号最新变更记录与协作边界",
            f"支持{role_phrase}根据岗位分工配置访问权限和处理范围",
        ]
    if kind == "analytics":
        return [
            f"支持围绕{focus}生成统计视图、对比分析与阶段结论",
            "支持输出可复用的数据复盘结果与图表摘要",
            f"支持{role_phrase}共享分析结果并跟踪后续动作",
        ]
    if kind == "settings":
        return [
            f"支持围绕{focus}集中维护参数项与适用范围",
            "支持记录配置生效状态与变更时间",
            f"支持{role_phrase}在统一界面完成配置保存与校验",
        ]
    if kind == "alerts":
        return [
            f"支持围绕{focus}识别异常、分级提醒和处置留痕",
            "支持查看预警状态、影响范围和处理进度",
            f"支持{role_phrase}基于同一页面开展提醒分发与复核",
        ]
    if kind == "actions":
        return [
            f"支持围绕{focus}跟踪执行阶段、责任人与结果摘要",
            "支持关键动作的状态推进与节点复核",
            f"支持{role_phrase}共享执行过程记录与结果输出",
        ]
    focus = "、".join(focus_terms[:2]) or "当前任务主题"
    return [
        f"支持围绕{title}对{focus}进行统一检索、状态跟踪与结果留痕",
        f"支持{role_phrase}按照职责查看{title}相关结果、明细字段和处理记录",
        f"支持在{title}页面中沉淀当前任务的过程数据、执行结论与导出材料",
    ]


def _module_description(title: str, keyword: str, scene: str, focus_terms: list[str]) -> str:
    focus = _module_domain_focus(title, keyword, focus_terms)
    if "剧集" in title:
        return (
            f"{title}模块聚焦短剧内容台账、题材标签与上架节奏的统一管理，主要服务于{scene}中的内容编排与进度跟踪。"
            f"页面重点展示{focus}，便于团队快速完成剧集录入、状态调整与资料复核。"
        )
    if "演员" in title:
        return (
            f"{title}模块用于维护演员档案、参演关系和合作状态，帮助团队围绕{keyword}快速完成选角资料整理与协同确认。"
            f"页面重点展示{focus}，便于在同一入口查看档案、更新状态并导出演员信息。"
        )
    if "分类" in title:
        return (
            f"{title}模块承担内容题材、风格标签和推荐分组的维护工作，用于保证{keyword}相关内容在运营、检索与展示中的分类口径一致。"
            f"页面重点展示{focus}，支持快速完成标签配置、绑定与复核。"
        )
    if "评论" in title:
        return (
            f"{title}模块围绕用户反馈、社区互动与风险内容处置展开，用于支撑{scene}中的评论审核、回复与异常跟踪。"
            f"页面重点展示{focus}，便于快速定位重点反馈并完成处理留痕。"
        )
    if "用户" in title:
        return (
            f"{title}模块用于统一维护账号资料、岗位角色与负责范围，使{scene}中的多角色协作边界更加清晰。"
            f"页面重点展示{focus}，便于完成账号启停、角色调整与权限核对。"
        )
    kind = _module_kind(title)
    if kind == "analytics":
        return (
            f"{title}模块面向{scene}中的复盘分析与结论输出，重点汇总{focus}，用于快速形成统计视图和阶段判断。"
        )
    if kind == "settings":
        return (
            f"{title}模块负责集中维护运行参数、配置策略和适用范围，确保当前产品在不同角色和页面之间保持一致配置口径。"
        )
    if kind == "alerts":
        return (
            f"{title}模块用于识别异常、跟踪处理进度并汇总提醒结果，帮助团队围绕{focus}及时开展处置与复核。"
        )
    return (
        f"{title}模块围绕{keyword}的业务主题构建，主要服务于{scene}中的日常处理、结果确认和记录留痕。"
        f"页面重点展示{focus}，使用户能够在同一页面内完成查询、录入、审核或跟踪操作。"
    )


def _module_steps(title: str, primary_action: str, focus_terms: list[str]) -> list[str]:
    focus = _module_domain_focus(title, title, focus_terms)
    if "剧集" in title:
        return [
            "进入剧集管理页面后先核对剧集名称、题材标签、上架状态和更新时间等核心信息。",
            "通过搜索条件或状态筛选快速定位目标剧集，确认当前需要处理的内容条目。",
            f"根据业务需要执行“{primary_action}”，补充剧集资料、调整状态或完善标签配置。",
            "处理完成后复核页面反馈和导出结果，确保剧集信息可追踪、可复查、可用于后续发行安排。",
        ]
    if "演员" in title:
        return [
            "进入演员管理页面后查看演员姓名、合作状态、参演作品和最近更新时间。",
            f"通过搜索或筛选定位与{focus}相关的目标档案，确认需要维护的演员资料。",
            f"执行“{primary_action}”或详情维护操作，补充演员信息并校验关联作品。",
            "完成维护后复核状态反馈和记录留痕，确保档案信息后续可检索、可导出、可复盘。",
        ]
    if "评论" in title:
        return [
            "进入评论管理页面后优先查看风险状态、所属剧集和用户反馈摘要。",
            "通过关键字、风险标签或处理状态筛选需要优先处置的评论记录。",
            f"根据业务需要执行“{primary_action}”，完成审核、回复或异常内容处理。",
            "处理后复核处置结果与更新时间，确保反馈链路清晰、证据可留存、结果可导出。",
        ]
    return [
        f"进入{title}页面后查看顶部标题区、检索区和列表区，确认当前业务主题与处理范围。",
        f"通过搜索条件、状态标签或筛选项定位与{focus}相关的目标记录。",
        f"根据业务需要执行“{primary_action}”、查看详情、维护字段或更新当前状态。",
        "完成处理后复核页面反馈、更新时间和相关结果，确保记录可追溯、可复查、可导出。",
    ]


def _module_business_value(title: str, keyword: str, scene: str) -> str:
    if "剧集" in title:
        return "剧集管理将内容资料、题材标签、上架进度和处理记录集中到统一页面，有助于提升内容运营效率并降低跨表沟通成本。"
    if "演员" in title:
        return "演员管理将档案维护、作品关联和合作状态整合到同一工作台，便于选角统筹、内容运营与资料复核同步协作。"
    if "分类" in title:
        return "分类管理通过统一标签口径和推荐分组配置，帮助团队快速组织内容结构，并提升后续检索、编排与推荐效率。"
    if "评论" in title:
        return "评论管理把用户反馈筛查、风险识别与回复处理聚合到一个页面中，便于快速形成闭环处置与社区运营复盘。"
    if "用户" in title:
        return "用户管理通过统一维护账号、角色和负责范围，帮助团队明确协作边界，降低跨角色操作与权限核对成本。"
    return (
        f"{title}页面将与“{keyword}”相关的核心业务处理集中到统一界面中，适用于{scene}场景下的受理、跟踪、复核和结果沉淀。"
    )


def _build_task_specific_module(
    *,
    title: str,
    index: int,
    preset_module: dict,
    page_routes: list[str],
    roles: list[str],
    keyword: str,
    product_name: str,
    scene: str,
    focus_terms: list[str],
    product_code: str,
    page_variant: str,
) -> dict:
    kind = _module_kind(title)
    route = _module_route(title, index, preset_module.get("route", ""), page_routes)
    role_phrase = "、".join(roles[:3]) or "管理员"
    return _build_module(
        title=title,
        route=route,
        icon=preset_module.get("icon") or _MODULE_ICONS[index % len(_MODULE_ICONS)],
        primary_action=_module_primary_action(title),
        filter_placeholder=_module_filter(title, focus_terms),
        table_headers=_module_headers(kind),
        rows=_module_rows(title, kind, index, keyword, product_code, roles, focus_terms),
        highlights=_module_highlights(title, keyword, focus_terms, role_phrase),
        description=_module_description(title, keyword, scene, focus_terms),
    ) | {
        "steps": _module_steps(title, _module_primary_action(title), focus_terms),
        "business_value": _module_business_value(title, keyword, scene),
        "page_variant": page_variant,
    }


def _same_topic(keyword: str, product_name: str) -> bool:
    return _clean_phrase(keyword) == _clean_phrase(product_name)


def _topic_label(keyword: str, product_name: str) -> str:
    keyword = _clean_phrase(keyword)
    product_name = _clean_phrase(product_name)
    if not keyword:
        return product_name
    if not product_name:
        return keyword
    if _same_topic(keyword, product_name):
        return product_name
    if keyword in product_name:
        return product_name
    if product_name in keyword:
        return keyword
    return f"{product_name}（{keyword}）"


def _infer_scene(keyword: str, industry: str | None, module_titles: list[str], preset: DomainPreset) -> str:
    source = " ".join([keyword, industry or "", *module_titles])
    if any(token in source for token in ["股票", "量化", "策略", "回测", "交易", "因子"]):
        return "量化策略研究、市场数据管理、回测分析与交易执行协同"
    if any(token in source for token in ["能耗", "园区", "设备", "巡检", "告警"]):
        return "能耗监测、设备巡检、告警处置与运维协同"
    if any(token in source for token in ["投放", "达人", "营销", "品牌", "内容", "种草"]):
        return "品牌投放管理、内容协同与效果复盘"
    if any(token in source for token in ["风控", "审计", "合规", "预警"]):
        return "风险监测、审计留痕与预警处置"
    return preset.scene


def _compose_scene(keyword: str, product_name: str, industry: str | None, module_titles: list[str], preset: DomainPreset) -> str:
    scene = _infer_scene(keyword, industry, module_titles, preset)
    industry = _clean_phrase(industry or "")
    if industry and industry not in scene:
        return f"{industry}领域的{scene}"
    return scene


def _compose_industry_scope(keyword: str, industry: str | None, preset: DomainPreset, focus_terms: list[str]) -> str:
    fragments = [industry or "", preset.industry_scope, "、".join(focus_terms[:2])]
    cleaned = [item for item in (_clean_phrase(fragment) for fragment in fragments) if item]
    joined = "、".join(dict.fromkeys(cleaned))
    return _ensure_min_length(joined, 4, "行业管理")


def _build_dashboard_metrics(
    modules: list[dict],
    roles: list[str],
    focus_terms: list[str],
    preset: DomainPreset,
    blueprint: dict,
) -> list[dict]:
    metrics = [dict(item) for item in preset.dashboard_metrics[:4]]
    if not metrics:
        metrics = [
            {"title": "核心模块", "value": str(len(modules)), "color": "#1677ff"},
            {"title": "使用角色", "value": str(len(roles)), "color": "#52c41a"},
            {"title": "主题要点", "value": str(max(len(focus_terms), 1)), "color": "#faad14"},
            {"title": "交付阶段", "value": "已规划", "color": "#722ed1"},
        ]
    if len(metrics) >= 4:
        metrics[0]["value"] = str(max(len(modules) * 2, int(metrics[0]["value"] or "0")))
        metrics[1]["value"] = str(max(len(roles) + len(focus_terms), 1))
        metrics[2]["value"] = str(max(len(focus_terms) * 2, 3))
        metrics[3]["value"] = blueprint.get("name", "已规划").replace("_", " ").title()
    return metrics


def _ensure_minimum_screenshot_scenarios(
    screenshot_scenarios: list[dict],
    modules: list[dict],
    focus_terms: list[str],
    minimum: int = 10,
) -> list[dict]:
    scenarios = list(screenshot_scenarios)
    if len(scenarios) >= minimum:
        return scenarios

    search_terms = focus_terms or ["关键字"]
    variant_index = 1

    while len(scenarios) < minimum:
        if modules:
            module = modules[(variant_index - 1) % len(modules)]
            search_value = search_terms[(variant_index - 1) % len(search_terms)] or module["title"]
            kind_prefix = _module_kind(module.get("title", ""))
            scenarios.append(
                {
                    "id": f"{kind_prefix}-filtered-{variant_index}",
                    "title": f"{module['title']}筛选结果",
                    "route": module["route"],
                    "actions": [
                        "login_as_admin",
                        {"action": "fill_input", "target": "搜索", "value": search_value},
                    ],
                    "requires_auth": True,
                    "priority": len(scenarios) + 1,
                }
            )
        else:
            scenarios.append(
                {
                    "id": f"dashboard-focused-{variant_index}",
                    "title": f"系统首页概览视图{variant_index}",
                    "route": "/dashboard",
                    "actions": ["login_as_admin"],
                    "requires_auth": True,
                    "priority": len(scenarios) + 1,
                }
            )
        variant_index += 1

    return scenarios


def _build_background_text(
    product_name: str,
    keyword: str,
    scene: str,
    industry_scope: str,
    modules: list[dict],
) -> str:
    topic = _clean_phrase(keyword) or _topic_label(keyword, product_name)
    module_titles = "、".join(module["title"] for module in modules[:5])
    return _ensure_min_length(
        (
            f"{product_name}围绕“{topic}”这一任务主题建设，面向{industry_scope}场景，重点解决线下信息分散、关键处理环节缺少统一入口、"
            f"结果反馈不够及时以及材料整理依赖人工汇总等问题。系统以{scene}为业务主线，把{module_titles}等核心模块纳入同一套操作界面，"
            "使不同岗位能够基于统一数据视图协同处理业务、查看阶段状态并输出交付材料。"
        ),
        100,
        "同时，系统通过统一的页面结构、列表视图和留痕机制降低培训成本，帮助使用单位在新任务切换时快速完成业务适配。",
    )


def _build_purpose_text(
    product_name: str,
    keyword: str,
    scene: str,
    roles: list[str],
    modules: list[dict],
) -> str:
    topic = _topic_label(keyword, product_name)
    role_phrase = "、".join(roles[:4]) or "管理员、业务主管、运营专员"
    module_titles = "、".join(module["title"] for module in modules[:6])
    return _ensure_min_length(
        (
            f"{product_name}的开发目的在于针对“{topic}”对应的业务需求搭建一套可持续复用的业务支撑平台，让{role_phrase}能够围绕{scene}开展统一登录、"
            f"信息录入、状态跟踪、结果分析和材料导出。系统以{module_titles}作为主要功能骨架，把原本分散在表格、消息和人工交接中的流程沉淀为"
            "标准化页面操作，提升任务推进效率、结果可追溯性和正式交付的一致性。"
        ),
        100,
        "软件还通过统一的数据口径、页面命名和操作反馈机制，帮助项目在版本迭代过程中保持稳定的培训、扩展和验收体验。",
    )


def _build_main_functions(
    product_name: str,
    keyword: str,
    modules: list[dict],
    roles: list[str],
) -> str:
    topic = _topic_label(keyword, product_name)
    role_phrase = "、".join(roles[:4]) or "管理员、业务主管、运营专员"
    segments = []
    for module in modules[:8]:
        headers = "、".join(module.get("table_headers", [])[:3]) or "关键字段"
        highlights = "；".join(module.get("highlights", [])[:2])
        primary_action = module.get("primary_action") or f"处理{module['title']}"
        segments.append(
            f"{module['title']}围绕{headers}等信息组织页面内容，支持“{primary_action}”等关键动作；{highlights}。"
        )
    return _ensure_min_length(
        (
            f"{product_name}的软件主要功能围绕“{topic}”任务全流程展开，服务对象包括{role_phrase}等岗位。"
            + "".join(segments)
            + "此外，系统支持统一登录、首页概览、检索筛选、状态更新、结果留痕、截图采集、文档导出和配置维护等公共能力，"
            "使使用人员能够在一套连续页面中完成从业务受理到结果归档的完整闭环。"
        ),
        500,
        "系统还可根据任务角色和模块顺序调整页面展示重点，从而保证不同标题和不同业务主题生成的说明书正文具有明显差异。",
    )


def _build_technical_features(
    product_name: str,
    keyword: str,
    modules: list[dict],
    roles: list[str],
    scene: str,
) -> str:
    topic = _topic_label(keyword, product_name)
    module_titles = "、".join(module["title"] for module in modules[:5])
    role_phrase = "、".join(roles[:3]) or "管理员、业务主管、运营专员"
    return _ensure_min_length(
        (
            f"{product_name}采用前后端分层、模块化页面与任务画像驱动的生成方式，围绕“{topic}”对应的{scene}需求组织软件结构。"
            f"系统通过统一导航、标准表格、状态标签、结果导出和截图留痕等机制，把{module_titles}等模块纳入一致的交互风格。"
            f"在使用层面，系统支持{role_phrase}按职责访问对应页面；在工程层面，系统保留 FastAPI、React、TypeScript、PostgreSQL 等通用技术原名，"
            "便于开发、测试、部署和后续扩展协同。"
        ),
        100,
        "同时，软件在页面命名、文档生成和导出发布链路上保持一致，确保每次任务生成的正文、截图与交付物能够相互对应。",
    )


def _build_product_positioning(
    product_name: str,
    keyword: str,
    industry_scope: str,
    scene: str,
    modules: list[dict],
) -> str:
    module_titles = "、".join(module["title"] for module in modules[:4]) or "核心模块"
    return _ensure_min_length(
        (
            f"{product_name}面向{industry_scope}场景进行设计，围绕“{keyword or product_name}”这一业务主题构建产品定位。"
            f"系统通过{module_titles}等模块组织页面内容，突出{scene}中的关键业务对象、处理动作与结果输出要求。"
        ),
        90,
        "说明书内容、页面命名与功能讲解均根据当前产品主题进行重构，以形成具有辨识度的产品表达。",
    )


def _build_design_focus(
    product_name: str,
    keyword: str,
    scene: str,
    roles: list[str],
    focus_terms: list[str],
) -> str:
    role_phrase = "、".join(roles[:3]) or "管理员、业务主管、运营专员"
    focus = "、".join(focus_terms[:3]) or keyword or product_name
    return _ensure_min_length(
        (
            f"{product_name}在设计上重点突出{scene}中的角色协同、页面字段组织和业务状态反馈。"
            f"系统会围绕{focus}等主题信息安排页面结构，使{role_phrase}能够快速理解当前产品的处理重点、数据重点和交付重点。"
        ),
        90,
        "因此，不同产品生成的说明书会在模块名称、正文论述、页面要点和技术特点上呈现出明显差异。",
    )


def _build_distinguishing_features(
    product_name: str,
    keyword: str,
    industry_scope: str,
    modules: list[dict],
    focus_terms: list[str],
) -> list[str]:
    module_titles = [module["title"] for module in modules[:4]]
    focus = "、".join(focus_terms[:3]) or keyword or product_name
    return [
        f"围绕“{keyword or product_name}”组织产品内容，说明书正文突出{industry_scope}中的任务目标、核心数据和流程特征。",
        f"优先以{ '、'.join(module_titles) if module_titles else '当前核心模块'}承接当前软件产品的专属业务主线，避免不同产品之间出现同质化模块表达。",
        f"页面说明、截图图注与功能结构统一围绕{focus}等重点内容展开，使当前产品形成清晰可辨的业务侧重点。",
    ]


def _build_typical_scenarios(
    product_name: str,
    keyword: str,
    scene: str,
    modules: list[dict],
) -> list[str]:
    module_titles = [module["title"] for module in modules[:3]]
    return [
        f"适用于围绕“{keyword or product_name}”开展日常受理、执行推进和结果复核的业务场景。",
        f"适用于需要通过{ '、'.join(module_titles) if module_titles else '核心模块'}进行统一管理、统一检索和统一留痕的协同场景。",
        f"适用于{scene}过程中需要同步整理页面结果、截图材料和正式交付文档的工作场景。",
    ]


def build_task_profile(
    *,
    keyword: str,
    product_name: str,
    version: str | None = None,
    industry: str | None = None,
    prd_summary: dict | None = None,
) -> dict:
    preset = _select_preset(keyword, product_name, industry)
    version = version or DEFAULT_VERSION
    prd_summary = prd_summary or {}
    product_code = _product_code(keyword, product_name)
    preset_modules = _preset_modules_for_product(preset, product_code)
    module_titles = list(prd_summary.get("core_modules") or [])
    if not module_titles:
        module_titles = [module["title"] for module in preset_modules]
    page_routes = list(prd_summary.get("required_pages") or [])
    roles = list(prd_summary.get("user_roles") or []) or list(preset.user_roles)
    focus_terms = _split_terms(keyword, product_name, industry or "", *module_titles)[:6]
    topic_label = _topic_label(keyword, product_name)
    scene = _compose_scene(keyword or product_name, product_name, industry, module_titles, preset)
    industry_scope = _compose_industry_scope(keyword, industry, preset, focus_terms)
    experience_blueprint = _pick_experience_blueprint(product_code, preset.key)

    profile_modules = []
    for idx, title in enumerate(module_titles):
        preset_module = _match_preset_module(preset_modules, title, idx)
        profile_modules.append(
            _build_task_specific_module(
                title=title,
                index=idx,
                preset_module=preset_module,
                page_routes=page_routes,
                roles=roles,
                keyword=keyword,
                product_name=product_name,
                scene=scene,
                focus_terms=focus_terms,
                product_code=product_code,
                page_variant=experience_blueprint["module_variants"][idx % len(experience_blueprint["module_variants"])],
            )
        )

    screenshot_scenarios = [
        {"id": "login-page", "title": "登录页", "route": "/login", "actions": [], "priority": 1},
        {"id": "dashboard", "title": "系统首页", "route": "/dashboard", "actions": ["login_as_admin"], "requires_auth": True, "priority": 2},
    ]
    for idx, module in enumerate(profile_modules, start=3):
        screenshot_scenarios.append(
            {
                "id": module["key"],
                "title": module["title"],
                "route": module["route"],
                "actions": ["login_as_admin"],
                "requires_auth": True,
                "priority": idx,
            }
        )
    screenshot_scenarios = _ensure_minimum_screenshot_scenarios(
        screenshot_scenarios,
        profile_modules,
        focus_terms,
        minimum=10,
    )

    created_date = datetime.now().strftime("%Y年%m月%d日")
    profile = {
        "keyword": keyword,
        "product_name": product_name,
        "topic_label": topic_label,
        "preset_key": preset.key,
        "version": version,
        "short_name": _short_name(product_name, preset.short_name),
        "product_code": product_code,
        "scene": scene,
        "software_category": preset.software_category,
        "industry_scope": industry_scope,
        "development_date": created_date,
        "hardware_environment": "Intel/AMD x86_64 处理器、8GB 及以上内存、100GB 以上可用磁盘空间、千兆网络环境",
        "runtime_hardware_environment": "Intel/AMD x86_64 处理器、4GB 及以上内存、50GB 以上可用磁盘空间、稳定网络环境",
        "development_os": "Linux / macOS / Windows",
        "runtime_platform": "Linux 服务器、Windows 终端或 macOS 终端中的主流浏览器环境",
        "support_environment": preset.support_env,
        "development_tools": preset.dev_tools,
        "programming_language": "Python、TypeScript、JavaScript、SQL",
        "source_code_line_estimate": 0,
        "development_background": _build_background_text(product_name, keyword, scene, industry_scope, profile_modules),
        "development_purpose": _build_purpose_text(product_name, keyword, scene, roles, profile_modules),
        "main_functions": _build_main_functions(product_name, keyword, profile_modules, roles),
        "technical_features": _build_technical_features(product_name, keyword, profile_modules, roles, scene),
        "product_positioning": _build_product_positioning(product_name, keyword, industry_scope, scene, profile_modules),
        "design_focus": _build_design_focus(product_name, keyword, scene, roles, focus_terms),
        "distinguishing_features": _build_distinguishing_features(product_name, keyword, industry_scope, profile_modules, focus_terms),
        "typical_scenarios": _build_typical_scenarios(product_name, keyword, scene, profile_modules),
        "user_roles": roles,
        "dashboard_metrics": _build_dashboard_metrics(profile_modules, roles, focus_terms, preset, experience_blueprint),
        "modules": profile_modules,
        "screenshot_scenarios": screenshot_scenarios,
        "experience_blueprint": experience_blueprint,
        "nav_items": [
            {"path": "/dashboard", "label": "首页", "icon": "📊", "code": _nav_code("/dashboard", "首页", 1)},
            *[
                {
                    "path": module["route"],
                    "label": module["title"],
                    "icon": module["icon"],
                    "code": _nav_code(module["route"], module["title"], idx + 2),
                }
                for idx, module in enumerate(profile_modules)
            ],
        ],
        "core_entities": preset.core_entities,
        "focus_terms": focus_terms,
    }
    return profile


def build_plan_seed(keyword: str, product_name: str, industry: str | None = None) -> dict:
    keyword = _clean_phrase(str(keyword or ""))
    product_name = _clean_phrase(str(product_name or ""))
    industry = _clean_phrase(str(industry or "")) or None
    preset = _select_preset(keyword, product_name, industry)
    product_code = _product_code(keyword, product_name)
    preset_modules = _preset_modules_for_product(preset, product_code)
    module_titles = [module["title"] for module in preset_modules[:5]]
    scene = _compose_scene(keyword or product_name, product_name, industry, module_titles, preset)
    focus_terms = _split_terms(keyword, product_name, industry or "", *module_titles)[:5]
    blueprint = _pick_experience_blueprint(product_code, preset.key)
    return {
        "preset_key": preset.key,
        "preset_name": preset.name,
        "scene": scene,
        "industry_scope": _compose_industry_scope(keyword, industry, preset, focus_terms),
        "core_entities": list(preset.core_entities[:5]),
        "user_roles": list(preset.user_roles[:4]),
        "core_modules": module_titles,
        "required_pages": ["/login", "/dashboard", *[module["route"] for module in preset_modules[:5]]],
        "focus_terms": focus_terms,
        "experience_blueprint": blueprint,
        "differentiation_hint": (
            f"当前任务优先体现{preset.name}领域特征，页面与模块命名围绕"
            f"{'、'.join(focus_terms[:3]) or product_name}展开，不使用通用综合运营套板。"
        ),
    }


def build_frontend_profile_source(profile: dict) -> str:
    payload = json.dumps(profile, ensure_ascii=False, indent=2)
    return (
        "export type ModuleProfile = {\n"
        "  key: string;\n"
        "  title: string;\n"
        "  route: string;\n"
        "  icon: string;\n"
        "  primary_action: string;\n"
        "  filter_placeholder: string;\n"
        "  table_headers: string[];\n"
        "  rows: string[][];\n"
        "  highlights: string[];\n"
        "  description: string;\n"
        "};\n\n"
        "export type AppProfile = {\n"
        "  keyword: string;\n"
        "  product_name: string;\n"
        "  version: string;\n"
        "  short_name: string;\n"
        "  product_code: string;\n"
        "  scene: string;\n"
        "  software_category: string;\n"
        "  industry_scope: string;\n"
        "  user_roles: string[];\n"
        "  dashboard_metrics: { title: string; value: string; color: string }[];\n"
        "  nav_items: { path: string; label: string; icon: string; code: string }[];\n"
        "  modules: ModuleProfile[];\n"
        "};\n\n"
        f"export const APP_PROFILE: AppProfile = {payload} as AppProfile;\n"
    )


def build_backend_profile_source(profile: dict) -> str:
    return (
        "from __future__ import annotations\n\n"
        f"APP_PROFILE = {pprint.pformat(profile, width=100, sort_dicts=False)}\n"
    )
