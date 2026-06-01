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


def _contains_any(text: str, tokens: list[str] | tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def _has_power_dispatch_context(text: str) -> bool:
    return _contains_any(
        text,
        (
            "电力",
            "电网",
            "负荷",
            "输电",
            "配电",
            "变电",
            "变电站",
            "调度令",
            "调度指令",
            "工作票",
            "操作票",
            "停电",
            "复电",
            "机组",
            "发电",
            "并网",
            "潮流",
        ),
    )


def _has_logistics_context(text: str) -> bool:
    return _contains_any(
        text,
        (
            "物流",
            "运单",
            "车队",
            "司机",
            "配送",
            "仓配",
            "签收",
            "回单",
            "分拨",
            "在途",
        ),
    )


def _build_raw_user_request(
    keyword: str,
    product_name: str,
    industry: str | None = None,
    notes: str | None = None,
) -> dict:
    return {
        "keyword": _clean_phrase(str(keyword or "")),
        "product_name": _clean_phrase(str(product_name or "")),
        "industry": _clean_phrase(str(industry or "")),
        "notes": _clean_phrase(str(notes or "")),
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


def _logistics_preset() -> DomainPreset:
    return DomainPreset(
        key="logistics",
        name="物流调度",
        scene="运单受理、车队调度、线路跟踪、仓配联动与签收回单",
        short_name="物流调度",
        software_category="物流管理软件",
        core_entities=["运单", "车辆", "司机", "配送线路", "签收回单"],
        user_roles=["管理员", "调度主管", "车队专员", "仓配协同员", "客服专员"],
        dashboard_metrics=[
            {"title": "在途运单", "value": "38", "color": "#1677ff"},
            {"title": "待调度车辆", "value": "12", "color": "#13c2c2"},
            {"title": "异常节点", "value": "4", "color": "#f5222d"},
            {"title": "回单待复核", "value": "9", "color": "#722ed1"},
        ],
        modules=[
            _build_module("运单调度中心", "/dispatch", "🚚"),
            _build_module("车辆与司机协同", "/fleet", "🚛"),
            _build_module("线路监控台", "/routes", "🛰️"),
            _build_module("仓配协同台", "/warehousing", "📦"),
            _build_module("签收回单中心", "/signoffs", "🧾"),
            _build_module("时效预警台", "/alerts", "🚨"),
            _build_module("结算对账", "/settlements", "💰"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        industry_scope="物流调度、车队管理、运输跟踪、仓配协同、签收回单",
        dev_tools="Python 3.11、FastAPI、React、TypeScript、Vite、python-docx、PostgreSQL",
        support_env="主流 Chromium 内核浏览器、Node.js 18+、Python 3.11+、PostgreSQL 或 SQLite",
    )


def _supply_chain_finance_preset() -> DomainPreset:
    return DomainPreset(
        key="supply_chain_finance",
        name="供应链金融",
        scene="核心企业授信分析、融资申请监控、贸易背景核验与资金敞口预警",
        short_name="供应链金融",
        software_category="金融分析软件",
        core_entities=["授信主体", "融资申请", "贸易背景", "资金敞口", "风险事件"],
        user_roles=["管理员", "风控经理", "授信分析师", "资金运营专员", "核心企业协同员"],
        dashboard_metrics=[
            {"title": "授信主体", "value": "24", "color": "#1677ff"},
            {"title": "融资申请", "value": "16", "color": "#13c2c2"},
            {"title": "风险预警", "value": "6", "color": "#f5222d"},
            {"title": "待复核事项", "value": "11", "color": "#722ed1"},
        ],
        modules=[
            _build_module("授信主体管理", "/credit-subjects", "🏦"),
            _build_module("融资申请分析", "/financing", "💹"),
            _build_module("资金敞口监控", "/exposure", "📉"),
            _build_module("贸易背景核验", "/trade-verification", "🔎"),
            _build_module("预警处置中心", "/alerts", "🚨"),
            _build_module("核心企业看板", "/anchor-enterprises", "🏢"),
            _build_module("报表中心", "/reports", "📋"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        industry_scope="供应链金融、核心企业授信、融资监控、贸易背景核验、资金风险预警",
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


def _power_dispatch_preset() -> DomainPreset:
    return DomainPreset(
        key="power_dispatch",
        name="电力调度",
        scene="电网运行监视、负荷调度、检修协同与故障处置",
        short_name="电力调度",
        software_category="电力调度管理软件",
        core_entities=["电网线路", "变电站", "负荷曲线", "检修工作票", "调度指令"],
        user_roles=["管理员", "调度长", "值班调度员", "检修协调员", "运行分析员"],
        dashboard_metrics=[
            {"title": "受控站点", "value": "84", "color": "#1677ff"},
            {"title": "调度指令", "value": "12", "color": "#13c2c2"},
            {"title": "越限告警", "value": "5", "color": "#f5222d"},
            {"title": "待复电任务", "value": "3", "color": "#722ed1"},
        ],
        modules=[
            _build_module("电网运行总览", "/grid-overview", "⚡"),
            _build_module("负荷调度中心", "/load-dispatch", "🧭"),
            _build_module("发电计划协同", "/generation-plans", "🔋"),
            _build_module("输变线路监测", "/transmission-lines", "🗼"),
            _build_module("检修工作票中心", "/work-tickets", "🧾"),
            _build_module("告警与故障联动", "/faults", "🚨"),
            _build_module("调度日志与指令", "/dispatch-orders", "📜"),
            _build_module("系统设置", "/settings", "⚙️"),
        ],
        industry_scope="电网调度、负荷监视、输变线路监测、检修协同、故障处置",
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
    keyword_text = _clean_phrase(str(keyword or "")).lower()
    product_text = _clean_phrase(str(product_name or "")).lower()
    industry_text = _clean_phrase(str(industry or "")).lower()
    source = " ".join(filter(None, [keyword_text, product_text, industry_text]))
    preset_tokens: list[tuple[DomainPreset, list[str]]] = [
        (_media_preset(), ["短剧", "剧集", "演员", "影视", "片单", "内容平台", "评论", "番剧", "节目"]),
        (_marketing_preset(), ["广告", "投放", "kol", "达人", "小红书", "营销", "种草", "流量", "品牌"]),
        (_power_dispatch_preset(), ["电力调度", "电网调度", "电力", "电网", "负荷", "变电", "输电", "配电", "调度令", "调度指令", "工作票", "停电", "复电", "机组", "发电", "并网"]),
        (_logistics_preset(), ["物流", "调度", "运单", "车队", "司机", "配送", "线路", "签收", "仓配", "在途"]),
        (_supply_chain_finance_preset(), ["供应链金融", "融资", "授信", "保理", "应收", "敞口", "核心企业", "资金", "贸易背景", "金融"]),
        (_supply_chain_preset(), ["供应链", "采购", "仓储", "库存", "履约", "供应商", "订单", "对账"]),
        (_finance_preset(), ["股票", "证券", "基金", "量化", "交易", "投研", "风控", "合规", "因子"]),
        (_energy_preset(), ["能耗", "园区", "设备", "巡检", "工单", "告警", "电力", "能源", "运维"]),
        (_manufacturing_preset(), ["制造", "生产", "工厂", "工序", "排程", "质检", "车间", "批次"]),
        (_healthcare_preset(), ["医疗", "医院", "门诊", "病案", "随访", "质控", "护理", "科室"]),
    ]

    best_match: DomainPreset | None = None
    best_score = 0
    for preset, tokens in preset_tokens:
        score = 0
        for token in tokens:
            if token in keyword_text or token in product_text:
                score += 3
            elif token in industry_text:
                score += 2
            elif token in source:
                score += 1
        if preset.key == "supply_chain_finance":
            if any(token in source for token in ["供应链", "核心企业", "订单", "应收"]):
                score += 2
            if any(token in source for token in ["金融", "融资", "授信", "敞口", "资金", "分析", "监控"]):
                score += 4
        if preset.key == "power_dispatch":
            if _has_power_dispatch_context(source):
                score += 6
            if any(token in source for token in ["调度", "值班", "负荷", "复电", "检修", "电网运行"]):
                score += 3
        if preset.key == "logistics":
            if _has_power_dispatch_context(source):
                score -= 6
            elif any(token in source for token in ["调度", "车队", "司机", "运单", "线路", "签收"]):
                score += 3
        if score > best_score:
            best_score = score
            best_match = preset
    if best_match and best_score > 0:
        return best_match
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


def _realistic_plate_number(seed: str) -> str:
    provinces = ["沪", "苏", "浙", "粤", "京", "鲁", "川", "鄂", "闽", "皖"]
    prefix_letters = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    suffix_chars = "ABCDEFGHJKLMNPQRSTUVWXYZ0123456789"
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest().upper()
    province = provinces[int(digest[0:2], 16) % len(provinces)]
    prefix = prefix_letters[int(digest[2:4], 16) % len(prefix_letters)]
    body = "".join(suffix_chars[int(digest[i : i + 2], 16) % len(suffix_chars)] for i in range(4, 12, 2))
    return f"{province}{prefix}·{body[:5]}"


def _realistic_mobile_number(seed: str) -> str:
    prefixes = ["131", "133", "135", "136", "138", "139", "150", "151", "156", "158", "166", "177", "181", "188", "199"]
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    prefix = prefixes[int(digest[0:2], 16) % len(prefixes)]
    tail_number = 10000000 + (int(digest[2:10], 16) % 90000000)
    return f"{prefix}{tail_number:08d}"


def _realistic_waybill_number(seed: str) -> str:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest().upper()
    numeric = str(int(digest[:10], 16)).zfill(10)[-8:]
    return f"YD202605{numeric}"


def _seed_index(seed: str, modulo: int) -> int:
    if modulo <= 0:
        return 0
    return int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:8], 16) % modulo


def _pick_experience_blueprint(product_code: str, preset_key: str, design_seed: str = "") -> dict:
    blueprints = [
        {
            "name": "command_hub",
            "login_variant": "spotlight",
            "dashboard_variant": "command",
            "module_variants": ["operations", "workspace", "insight"],
            "navigation_variant": "top_tabs",
            "shell_layout_hint": "顶部主导航 + 指挥条 + 多区块工作台，避免默认左侧深色竖栏后台",
            "tone": "强调执行节奏、状态看板与统一调度",
        },
        {
            "name": "analysis_studio",
            "login_variant": "briefing",
            "dashboard_variant": "insight",
            "module_variants": ["insight", "records", "workspace"],
            "navigation_variant": "indexed",
            "shell_layout_hint": "顶部索引导航 + 过滤工具带 + 双列或三列分析画布，避免统一侧栏壳层",
            "tone": "强调分析结论、关键洞察与对比视图",
        },
        {
            "name": "collaboration_workspace",
            "login_variant": "workspace",
            "dashboard_variant": "workspace",
            "module_variants": ["workspace", "operations", "records"],
            "navigation_variant": "sectioned",
            "shell_layout_hint": "顶部标题区 + 分段导航 + 协同工作区，可按模块使用二级面板，不要默认整站左侧固定竖栏",
            "tone": "强调岗位协同、分区工作台与任务闭环",
        },
        {
            "name": "signal_gallery",
            "login_variant": "spotlight",
            "dashboard_variant": "insight",
            "module_variants": ["insight", "workspace", "operations"],
            "navigation_variant": "top_tabs",
            "shell_layout_hint": "顶部信号导航 + 横向概览条 + 画廊式主内容区，不要回退为统一后台侧栏",
            "tone": "强调专题焦点、关键信号与模块分镜展示",
        },
        {
            "name": "studio_matrix",
            "login_variant": "briefing",
            "dashboard_variant": "workspace",
            "module_variants": ["workspace", "insight", "records"],
            "navigation_variant": "indexed",
            "shell_layout_hint": "顶部索引区 + 右侧摘要栏 + 分析工作台，不要回退为同一套模块列表页面",
            "tone": "强调专题分镜、摘要索引与操作面板并置",
        },
        {
            "name": "mission_sections",
            "login_variant": "workspace",
            "dashboard_variant": "command",
            "module_variants": ["operations", "records", "workspace"],
            "navigation_variant": "sectioned",
            "shell_layout_hint": "标题区 + 章节导航 + 任务面板式工作区，避免复用统一左侧深色竖栏",
            "tone": "强调任务主线、章节切换与分区执行面板",
        },
    ]
    return blueprints[_seed_index(f"{product_code}|{preset_key}|{design_seed}", len(blueprints))]


def _normalize_app_type(value: str | None) -> str | None:
    token = _clean_phrase(value or "").lower()
    mapping = {
        "admin_web": "admin_web",
        "web": "admin_web",
        "web_app": "admin_web",
        "webapp": "admin_web",
        "browser_app": "admin_web",
        "desktop_client": "desktop_client",
        "desktop_app": "desktop_client",
        "client_app": "desktop_client",
        "client": "desktop_client",
    }
    return mapping.get(token)


def _infer_app_type(keyword: str, product_name: str, industry: str | None, prd_summary: dict | None = None) -> str:
    explicit = _normalize_app_type((prd_summary or {}).get("app_type"))
    if not explicit:
        explicit = _normalize_app_type((prd_summary or {}).get("product_type"))
    if explicit:
        return explicit

    source = " ".join([keyword, product_name, industry or ""]).lower()
    desktop_tokens = [
        "客户端",
        "桌面",
        "桌面端",
        "工作站",
        "终端",
        "本地端",
        "值守端",
        "控制端",
        "分析终端",
        "监控终端",
        "采集端",
    ]
    web_tokens = [
        "平台",
        "系统",
        "门户",
        "网站",
        "网页",
        "web",
        "管理平台",
        "管理系统",
        "云平台",
        "中心",
    ]
    if any(token in source for token in desktop_tokens) and not any(token in source for token in web_tokens):
        return "desktop_client"
    return "admin_web"


def _runtime_platform_by_app_type(app_type: str) -> str:
    if app_type == "desktop_client":
        return "Windows 终端、macOS 终端或 Linux 桌面终端中的桌面客户端环境"
    return "Linux 服务器、Windows 终端或 macOS 终端中的主流浏览器环境"


def _support_env_by_app_type(base_support_env: str, app_type: str) -> str:
    if app_type == "desktop_client":
        return "Windows 10/11、macOS 或 Linux 桌面环境，Node.js 18+、Python 3.11+、PostgreSQL 或 SQLite"
    return base_support_env


def _build_visual_profile(
    product_code: str,
    preset_key: str,
    app_type: str,
    experience_blueprint: dict | None = None,
    design_seed: str = "",
) -> dict:
    blueprint = experience_blueprint or {}
    navigation_variant = str(blueprint.get("navigation_variant") or "").strip()
    shell_layout_hint = str(blueprint.get("shell_layout_hint") or "").strip()
    top_tabs_profiles = [
        {
            "name": "midnight_command_deck",
            "shell_background": "#f5f7fb",
            "nav_background": "#0f172a",
            "nav_text": "#e2e8f0",
            "panel_background": "#ffffff",
            "panel_border": "#dbe3ef",
            "accent": "#2563eb",
            "soft": "#eff6ff",
            "strong": "#1d4ed8",
            "layout_signal": "顶部标签导航 + 横向指挥卡片 + 宽屏工作台，避免默认左侧栏",
            "chrome_treatment": "top_tabs",
        },
        {
            "name": "sandstone_signal_ribbon",
            "shell_background": "#f6f4ef",
            "nav_background": "#43302b",
            "nav_text": "#f8efe4",
            "panel_background": "#fffdf8",
            "panel_border": "#e8dcc7",
            "accent": "#b7791f",
            "soft": "#fff7e6",
            "strong": "#9a6700",
            "layout_signal": "顶部主导航 + 信号条 + 横向运营区，避免默认左侧栏",
            "chrome_treatment": "top_tabs",
        },
        {
            "name": "emerald_command_tabs",
            "shell_background": "#f3faf7",
            "nav_background": "#0f3d3f",
            "nav_text": "#d5f5f6",
            "panel_background": "#ffffff",
            "panel_border": "#d6ebe5",
            "accent": "#0f766e",
            "soft": "#ecfeff",
            "strong": "#115e59",
            "layout_signal": "顶部标签栏 + 指挥区 + 多列工作台，避免侧边栏壳层",
            "chrome_treatment": "top_tabs",
        },
    ]
    indexed_profiles = [
        {
            "name": "slate_analysis_canvas",
            "shell_background": "#f4f6fb",
            "nav_background": "#1f2937",
            "nav_text": "#e5edf7",
            "panel_background": "#ffffff",
            "panel_border": "#d8e0eb",
            "accent": "#4f46e5",
            "soft": "#eef2ff",
            "strong": "#4338ca",
            "layout_signal": "顶部索引导航 + 过滤工具带 + 双列分析画布，避免默认左侧栏",
            "chrome_treatment": "indexed_topbar",
        },
        {
            "name": "linen_insight_grid",
            "shell_background": "#f8f5ef",
            "nav_background": "#5b4636",
            "nav_text": "#f7efe2",
            "panel_background": "#fffdf9",
            "panel_border": "#eadfce",
            "accent": "#c2410c",
            "soft": "#fff7ed",
            "strong": "#9a3412",
            "layout_signal": "顶部索引导航 + 洞察画布 + 并列信息区，避免统一侧栏",
            "chrome_treatment": "indexed_topbar",
        },
        {
            "name": "cobalt_insight_radar",
            "shell_background": "#f3f6fb",
            "nav_background": "#1e3a8a",
            "nav_text": "#dbeafe",
            "panel_background": "#ffffff",
            "panel_border": "#dbe6f5",
            "accent": "#2563eb",
            "soft": "#eff6ff",
            "strong": "#1d4ed8",
            "layout_signal": "顶部索引标签 + 过滤带 + 宽屏分析区，避免左侧竖栏后台",
            "chrome_treatment": "indexed_topbar",
        },
    ]
    sectioned_profiles = [
        {
            "name": "graphite_collaboration_strip",
            "shell_background": "#f4f6fb",
            "nav_background": "#111827",
            "nav_text": "#e5edf7",
            "panel_background": "#ffffff",
            "panel_border": "#d8e0eb",
            "accent": "#334155",
            "soft": "#f1f5f9",
            "strong": "#1f2937",
            "layout_signal": "顶部标题区 + 分段导航 + 协同工作区，不使用整站左侧栏",
            "chrome_treatment": "sectioned_header",
        },
        {
            "name": "amber_team_panels",
            "shell_background": "#faf7f1",
            "nav_background": "#713f12",
            "nav_text": "#fef3c7",
            "panel_background": "#fffdf8",
            "panel_border": "#f1dfb5",
            "accent": "#d97706",
            "soft": "#fffbeb",
            "strong": "#b45309",
            "layout_signal": "顶部标题栏 + 分段导航 + 多面板协作台，避免默认左侧栏",
            "chrome_treatment": "sectioned_header",
        },
        {
            "name": "teal_team_workspace",
            "shell_background": "#f2fbfa",
            "nav_background": "#134e4a",
            "nav_text": "#ccfbf1",
            "panel_background": "#ffffff",
            "panel_border": "#d2f1ec",
            "accent": "#0f766e",
            "soft": "#f0fdfa",
            "strong": "#115e59",
            "layout_signal": "顶部标题区 + 分段标签 + 协同工作台，避免左侧竖栏后台",
            "chrome_treatment": "sectioned_header",
        },
    ]
    default_web_profiles = [
        *top_tabs_profiles,
        *indexed_profiles,
        *sectioned_profiles,
    ]
    client_profiles = [
        {
            "name": "graphite_client",
            "shell_background": "#eef2f7",
            "nav_background": "#1f2937",
            "nav_text": "#e5edf7",
            "panel_background": "#f8fafc",
            "panel_border": "#cfd8e3",
            "accent": "#2563eb",
            "soft": "#e8f0ff",
            "strong": "#1e40af",
        },
        {
            "name": "slate_operator",
            "shell_background": "#f2f4f8",
            "nav_background": "#111827",
            "nav_text": "#dbe6f4",
            "panel_background": "#f9fbfd",
            "panel_border": "#d3dce7",
            "accent": "#475569",
            "soft": "#f1f5f9",
            "strong": "#334155",
        },
    ]
    if app_type == "desktop_client":
        candidates = client_profiles
    elif navigation_variant == "top_tabs":
        candidates = top_tabs_profiles
    elif navigation_variant == "indexed":
        candidates = indexed_profiles
    elif navigation_variant == "sectioned":
        candidates = sectioned_profiles
    else:
        candidates = default_web_profiles
    profile = dict(candidates[_seed_index(f"{product_code}|{preset_key}|{app_type}|{navigation_variant}|{design_seed}", len(candidates))])
    if shell_layout_hint:
        profile.setdefault("layout_signal", shell_layout_hint)
    return profile


def _build_design_seed(
    keyword: str,
    product_name: str,
    industry: str | None,
    notes: str | None,
    raw_user_request: dict | None = None,
) -> str:
    parts: list[str] = [keyword, product_name, industry or "", notes or ""]
    if raw_user_request:
        try:
            parts.append(json.dumps(raw_user_request, ensure_ascii=False, sort_keys=True))
        except TypeError:
            parts.append(str(raw_user_request))
    return "|".join(part.strip() for part in parts if str(part).strip())


def _module_kind(title: str) -> str:
    if any(token in title for token in ["负荷调度", "电力调度", "调度日志", "调度指令", "调度令"]):
        return "power_dispatch"
    if any(token in title for token in ["电网运行", "输变线路", "线路监测", "输电线路", "配电线路", "变电站", "潮流"]):
        return "grid_monitor"
    if any(token in title for token in ["发电计划", "机组", "并网", "新能源", "功率预测"]):
        return "generation"
    if any(token in title for token in ["检修", "工作票", "操作票", "停复电"]):
        return "work_tickets"
    if any(token in title for token in ["故障联动", "故障处置", "停电", "复电"]) and "告警" in title:
        return "power_faults"
    if any(token in title for token in ["授信", "主体"]):
        return "credit_subjects"
    if any(token in title for token in ["融资", "放款", "保理"]):
        return "financing"
    if any(token in title for token in ["敞口", "资金", "头寸"]):
        return "exposure"
    if any(token in title for token in ["贸易背景", "核验", "单据核查", "凭证"]):
        return "trade_verification"
    if any(token in title for token in ["运单", "调度", "派车"]):
        return "dispatch"
    if any(token in title for token in ["车辆", "司机", "车队", "运力"]):
        return "fleet"
    if any(token in title for token in ["线路", "轨迹", "路径"]):
        return "routes"
    if any(token in title for token in ["仓配", "分拨", "仓库协同", "回单"]):
        return "warehousing"
    if any(token in title for token in ["签收", "回单", "妥投"]):
        return "signoffs"
    if any(token in title for token in ["采购", "请购", "寻源"]):
        return "purchases"
    if any(token in title for token in ["销售", "客户订单", "发货"]):
        return "sales"
    if any(token in title for token in ["库存", "仓储", "批次", "库位"]):
        return "inventory"
    if any(token in title for token in ["供应商", "供方", "厂商"]):
        return "suppliers"
    if any(token in title for token in ["履约", "订单", "交付", "执行中心"]):
        return "fulfillment"
    if any(token in title for token in ["结算", "对账", "付款"]):
        return "settlements"
    if any(token in title for token in ["达人", "创作者", "博主"]):
        return "talents"
    if any(token in title for token in ["品牌", "客户"]):
        return "clients"
    if any(token in title for token in ["投放", "活动", "campaign"]):
        return "campaigns"
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
        (["负荷调度", "电力调度", "调度日志", "调度指令", "调度令"], "/load-dispatch"),
        (["电网运行", "输变线路", "线路监测", "输电线路", "配电线路", "变电站", "潮流"], "/transmission-lines"),
        (["发电计划", "机组", "并网", "新能源"], "/generation-plans"),
        (["检修", "工作票", "操作票", "停复电"], "/work-tickets"),
        (["故障联动", "故障处置", "停电", "复电"], "/faults"),
        (["授信", "主体"], "/credit-subjects"),
        (["融资", "放款", "保理"], "/financing"),
        (["敞口", "资金", "头寸"], "/exposure"),
        (["贸易背景", "核验", "单据核查"], "/trade-verification"),
        (["运单", "调度", "派车"], "/dispatch"),
        (["车辆", "司机", "车队", "运力"], "/fleet"),
        (["线路", "轨迹", "路径"], "/routes"),
        (["仓配", "分拨"], "/warehousing"),
        (["签收", "回单", "妥投"], "/signoffs"),
        (["短剧", "剧集", "片单", "内容库"], "/series"),
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
    preferred_route = ""
    if len(page_routes) > index + 2 and page_routes[index + 2]:
        preferred_route = str(page_routes[index + 2]).strip()
    if preferred_route:
        return preferred_route if preferred_route.startswith("/") else f"/{preferred_route.lstrip('/')}"

    fallback_route = str(fallback_route or "").strip()
    if fallback_route:
        return fallback_route if fallback_route.startswith("/") else f"/{fallback_route.lstrip('/')}"

    hinted_route = _module_route_hint(title)
    if hinted_route:
        return hinted_route
    return f"/{_slug_key(title)}"


def _ensure_unique_module_routes(modules: list[dict]) -> list[dict]:
    normalized_modules: list[dict] = []
    used_routes: set[str] = set()

    for index, module in enumerate(modules, start=1):
        normalized_module = dict(module)
        current_route = str(normalized_module.get("route") or "").strip()
        if current_route:
            current_route = current_route if current_route.startswith("/") else f"/{current_route.lstrip('/')}"
        title_route = f"/{_slug_key(str(normalized_module.get('title') or normalized_module.get('key') or f'module-{index}'))}"
        route_candidates = [current_route, title_route]

        chosen_route = ""
        for candidate in route_candidates:
            if candidate and candidate not in {"/", "/login", "/dashboard"} and candidate not in used_routes:
                chosen_route = candidate
                break
        if not chosen_route:
            base_route = title_route if title_route not in {"/", "/login", "/dashboard"} else f"/module-{index}"
            suffix = 2
            chosen_route = base_route
            while chosen_route in used_routes:
                chosen_route = f"{base_route}-{suffix}"
                suffix += 1

        normalized_module["route"] = chosen_route
        used_routes.add(chosen_route)
        normalized_modules.append(normalized_module)

    return normalized_modules


def _module_headers(kind: str) -> list[str]:
    if kind == "power_dispatch":
        return ["指令编号", "调度单元", "负荷水平", "执行状态", "值班调度员", "更新时间"]
    if kind == "grid_monitor":
        return ["线路/站点编号", "线路/站点名称", "运行状态", "越限等级", "责任班组", "更新时间"]
    if kind == "generation":
        return ["计划编号", "机组/电源", "出力目标", "并网状态", "计划周期", "更新时间"]
    if kind == "work_tickets":
        return ["票号", "检修对象", "工作类型", "许可状态", "计划复电时间", "更新时间"]
    if kind == "power_faults":
        return ["事件编号", "故障主题", "影响范围", "处置阶段", "恢复状态", "发现时间"]
    if kind == "credit_subjects":
        return ["主体编号", "核心企业/主体", "授信额度", "评级状态", "预警级别", "更新时间"]
    if kind == "financing":
        return ["申请编号", "融资产品", "申请企业", "审批阶段", "放款状态", "更新时间"]
    if kind == "exposure":
        return ["监控编号", "资金池/项目", "当前敞口", "阈值状态", "责任人", "更新时间"]
    if kind == "trade_verification":
        return ["核验编号", "订单/合同", "背景真实性", "单据完备度", "复核结论", "更新时间"]
    if kind == "dispatch":
        return ["运单编号", "起讫区域", "调度责任人", "运输状态", "承运时效", "更新时间"]
    if kind == "fleet":
        return ["车辆编号", "司机姓名", "司机手机号", "车辆状态", "当前任务", "在途位置", "更新时间"]
    if kind == "routes":
        return ["线路编号", "线路名称", "途经节点", "拥堵等级", "异常状态", "更新时间"]
    if kind == "warehousing":
        return ["协同单号", "仓库/分拨点", "节点状态", "异常原因", "责任角色", "更新时间"]
    if kind == "signoffs":
        return ["回单编号", "客户/站点", "签收状态", "回单完整度", "复核结果", "更新时间"]
    if kind == "purchases":
        return ["采购单号", "物料名称", "申请部门", "供应状态", "到货日期", "更新时间"]
    if kind == "sales":
        return ["销售单号", "客户名称", "交付经理", "履约状态", "回款状态", "更新时间"]
    if kind == "inventory":
        return ["批次编号", "物料名称", "仓位", "可用库存", "预警状态", "更新时间"]
    if kind == "suppliers":
        return ["供应商编号", "供应商名称", "品类范围", "协同状态", "资质状态", "更新时间"]
    if kind == "fulfillment":
        return ["履约单号", "任务主题", "责任人", "当前阶段", "结果摘要", "更新时间"]
    if kind == "settlements":
        return ["结算单号", "业务对象", "应付金额", "审核状态", "付款状态", "更新时间"]
    if kind == "talents":
        return ["达人编号", "达人昵称", "平台", "合作状态", "报价区间", "更新时间"]
    if kind == "clients":
        return ["客户编号", "客户名称", "所属行业", "合作阶段", "负责人", "更新时间"]
    if kind == "campaigns":
        return ["计划编号", "计划名称", "投放渠道", "执行阶段", "预算", "更新时间"]
    if kind == "analytics":
        return ["分析编号", "分析主题", "统计维度", "负责人", "核心结论", "更新时间"]
    if kind == "settings":
        return ["配置项", "当前值", "适用范围", "维护角色", "更新时间", "状态"]
    if kind == "alerts":
        return ["预警编号", "预警主题", "影响范围", "责任角色", "处理状态", "发现时间"]
    if kind == "users":
        return ["账号编号", "姓名", "手机号", "角色", "状态", "最近更新"]
    if kind == "actions":
        return ["任务编号", "任务主题", "执行人", "当前阶段", "结果摘要", "更新时间"]
    return ["记录编号", "主题名称", "责任角色", "当前状态", "业务标签", "更新时间"]


def _module_primary_action(title: str) -> str:
    if any(token in title for token in ["负荷调度", "电力调度", "调度指令", "调度令"]):
        return "下发调度指令"
    if any(token in title for token in ["电网运行", "输变线路", "线路监测", "变电站", "潮流"]):
        return "查看运行断面"
    if any(token in title for token in ["发电计划", "机组", "并网", "新能源"]):
        return "调整发电计划"
    if any(token in title for token in ["检修", "工作票", "操作票", "停复电"]):
        return "签发检修工作票"
    if any(token in title for token in ["故障联动", "故障处置", "停电", "复电"]) and "告警" in title:
        return "发起故障联动"
    if any(token in title for token in ["授信", "主体"]):
        return "新建授信主体"
    if any(token in title for token in ["融资", "放款", "保理"]):
        return "发起融资申请"
    if any(token in title for token in ["敞口", "资金", "头寸"]):
        return "新增敞口监控项"
    if any(token in title for token in ["贸易背景", "核验", "单据核查"]):
        return "提交背景核验"
    if any(token in title for token in ["运单", "调度", "派车"]):
        return "创建调度任务"
    if any(token in title for token in ["车辆", "司机", "车队", "运力"]):
        return "新增车辆档案"
    if any(token in title for token in ["线路", "轨迹", "路径"]):
        return "配置监控线路"
    if any(token in title for token in ["仓配", "分拨"]):
        return "发起仓配协同"
    if any(token in title for token in ["签收", "回单", "妥投"]):
        return "复核签收回单"
    if any(token in title for token in ["采购", "请购", "寻源"]):
        return "发起采购申请"
    if any(token in title for token in ["销售", "客户订单", "发货"]):
        return "新建销售订单"
    if any(token in title for token in ["库存", "仓储", "批次", "库位"]):
        return "发起库存盘点"
    if any(token in title for token in ["供应商", "供方", "厂商"]):
        return "新增供应商档案"
    if any(token in title for token in ["履约", "订单", "交付"]):
        return "创建履约任务"
    if any(token in title for token in ["结算", "对账", "付款"]):
        return "发起结算复核"
    if any(token in title for token in ["达人", "创作者", "博主"]):
        return "新增达人档案"
    if any(token in title for token in ["品牌", "客户"]):
        return "新增客户线索"
    if any(token in title for token in ["投放", "活动", "campaign"]):
        return "新建投放计划"
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
    if any(token in title for token in ["负荷调度", "电力调度", "调度指令", "调度令"]):
        return "搜索指令编号 / 调度单元 / 执行状态"
    if any(token in title for token in ["电网运行", "输变线路", "线路监测", "变电站", "潮流"]):
        return "搜索站点名称 / 线路名称 / 越限等级"
    if any(token in title for token in ["发电计划", "机组", "并网", "新能源"]):
        return "搜索计划编号 / 机组名称 / 并网状态"
    if any(token in title for token in ["检修", "工作票", "操作票", "停复电"]):
        return "搜索票号 / 检修对象 / 许可状态"
    if any(token in title for token in ["故障联动", "故障处置", "停电", "复电"]) and "告警" in title:
        return "搜索事件编号 / 影响范围 / 恢复状态"
    if any(token in title for token in ["授信", "主体"]):
        return "搜索主体编号 / 企业名称 / 评级状态"
    if any(token in title for token in ["融资", "放款", "保理"]):
        return "搜索申请编号 / 企业名称 / 审批阶段"
    if any(token in title for token in ["敞口", "资金", "头寸"]):
        return "搜索资金池 / 敞口状态 / 责任人"
    if any(token in title for token in ["贸易背景", "核验", "单据核查"]):
        return "搜索合同编号 / 订单号 / 核验结论"
    if any(token in title for token in ["运单", "调度", "派车"]):
        return "搜索运单编号 / 起讫区域 / 运输状态"
    if any(token in title for token in ["车辆", "司机", "车队", "运力"]):
        return "搜索车辆编号 / 司机姓名 / 司机手机号"
    if any(token in title for token in ["线路", "轨迹", "路径"]):
        return "搜索线路编号 / 线路名称 / 异常状态"
    if any(token in title for token in ["仓配", "分拨"]):
        return "搜索仓库 / 分拨点 / 节点状态"
    if any(token in title for token in ["签收", "回单", "妥投"]):
        return "搜索回单编号 / 客户名称 / 签收状态"
    if any(token in title for token in ["采购", "请购", "寻源"]):
        return "搜索采购单号 / 物料名称 / 申请部门"
    if any(token in title for token in ["销售", "客户订单", "发货"]):
        return "搜索销售单号 / 客户名称 / 履约状态"
    if any(token in title for token in ["库存", "仓储", "批次", "库位"]):
        return "搜索批次编号 / 物料名称 / 仓位"
    if any(token in title for token in ["供应商", "供方", "厂商"]):
        return "搜索供应商名称 / 资质状态 / 品类"
    if any(token in title for token in ["履约", "订单", "交付"]):
        return "搜索履约单号 / 责任人 / 当前阶段"
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
    if kind == "power_dispatch":
        return [
            [f"{base_code}-181", "华东主网", "78%", "待执行", role_a, "2026-05-02"],
            [f"{base_code}-182", "苏南断面", "82%", "执行中", role_b, "2026-05-01"],
            [f"{base_code}-183", "沿海新能源汇集", "64%", "已完成", role_c, "2026-04-30"],
        ]
    if kind == "grid_monitor":
        return [
            [f"{base_code}-191", "500kV 东枢纽变电站", "正常", "无越限", role_a, "2026-05-02"],
            [f"{base_code}-192", "苏中北环输电线", "重载", "一级告警", role_b, "2026-05-01"],
            [f"{base_code}-193", "滨江配电联络线", "检修切换", "需关注", role_c, "2026-04-30"],
        ]
    if kind == "generation":
        return [
            [f"{base_code}-201", "1号燃机机组", "420MW", "并网运行", "日内计划", "2026-05-02"],
            [f"{base_code}-202", "海上风电场 A 区", "260MW", "计划调整中", "滚动计划", "2026-05-01"],
            [f"{base_code}-203", "光伏汇集站 B", "180MW", "待并网复核", "次日计划", "2026-04-30"],
        ]
    if kind == "work_tickets":
        return [
            [f"{base_code}-211", "220kV 江北变电站", "设备检修", "待许可", "2026-05-02 18:00", "2026-05-02"],
            [f"{base_code}-212", "城西配电线路 3 段", "带电作业", "执行中", "2026-05-01 22:30", "2026-05-01"],
            [f"{base_code}-213", "沿江输电通道", "消缺复电", "已结束", "2026-04-30 20:00", "2026-04-30"],
        ]
    if kind == "power_faults":
        return [
            [f"{base_code}-221", "主网断面越限", "华东主网", "应急处置", "待恢复", "2026-05-02 09:20"],
            [f"{base_code}-222", "变电站保护动作", "苏南片区", "联动核查", "恢复中", "2026-05-01 16:35"],
            [f"{base_code}-223", "配电线路停电事件", "滨江片区", "已闭环", "已复电", "2026-04-30 11:10"],
        ]
    if kind == "credit_subjects":
        return [
            [f"{base_code}-111", f"{focus_a}核心企业", "8,000万", "A 级", "关注", "2026-05-02"],
            [f"{base_code}-112", f"{focus_b}链主企业", "5,500万", "B+级", "正常", "2026-05-01"],
            [f"{base_code}-113", f"{product_code}白名单主体", "3,200万", "A-级", "待复核", "2026-04-30"],
        ]
    if kind == "financing":
        return [
            [f"{base_code}-121", "订单质押融资", f"{focus_a}供应商", "尽调中", "待放款", "2026-05-02"],
            [f"{base_code}-122", "应收账款保理", f"{focus_b}服务商", "授信复核", "审批中", "2026-05-01"],
            [f"{base_code}-123", "仓单融资", f"{product_code}合作方", "已通过", "已放款", "2026-04-30"],
        ]
    if kind == "exposure":
        return [
            [f"{base_code}-131", f"{focus_a}资金池", "2,450万", "接近阈值", role_a, "2026-05-02"],
            [f"{base_code}-132", f"{focus_b}项目组", "1,820万", "状态正常", role_b, "2026-05-01"],
            [f"{base_code}-133", f"{product_code}专项计划", "3,080万", "超限待处置", role_c, "2026-04-30"],
        ]
    if kind == "trade_verification":
        return [
            [f"{base_code}-141", "PO-202605-001", "已核验", "单据齐全", "通过", "2026-05-02"],
            [f"{base_code}-142", "SO-202605-012", "待补充", "发票缺失", "退回补件", "2026-05-01"],
            [f"{base_code}-143", "AR-202604-027", "复核中", "影像待校验", "人工核对", "2026-04-30"],
        ]
    if kind == "dispatch":
        return [
            [_realistic_waybill_number(f"{product_code}|{title}|dispatch|0"), "上海青浦 -> 苏州工业园区", names[0], "待派车", "4h 30m", "2026-05-02"],
            [_realistic_waybill_number(f"{product_code}|{title}|dispatch|1"), "无锡锡山 -> 南京江宁", names[1], "在途", "6h 10m", "2026-05-01"],
            [_realistic_waybill_number(f"{product_code}|{title}|dispatch|2"), "嘉兴南湖 -> 杭州滨江", names[2], "已签收", "2h 50m", "2026-04-30"],
        ]
    if kind == "fleet":
        return [
            [_realistic_plate_number(f"{product_code}|{title}|fleet|0"), names[0], _realistic_mobile_number(f"{product_code}|{title}|fleet|mobile|0"), "待发车", "华东仓配", "嘉定分拨场", "2026-05-02"],
            [_realistic_plate_number(f"{product_code}|{title}|fleet|1"), names[1], _realistic_mobile_number(f"{product_code}|{title}|fleet|mobile|1"), "运输中", "冷链专线", "无锡中转站", "2026-05-01"],
            [_realistic_plate_number(f"{product_code}|{title}|fleet|2"), names[2], _realistic_mobile_number(f"{product_code}|{title}|fleet|mobile|2"), "待回场", "城配末端", "杭州东站点", "2026-04-30"],
        ]
    if kind == "routes":
        return [
            [f"{base_code}-231", "沪宁当日达", "上海-苏州-南京", "轻度拥堵", "需关注", "2026-05-02"],
            [f"{base_code}-232", "华南快配", "广州-东莞-深圳", "通畅", "正常", "2026-05-01"],
            [f"{base_code}-233", "冷链回仓线", "嘉兴-苏州-上海", "中度拥堵", "待调线", "2026-04-30"],
        ]
    if kind == "warehousing":
        return [
            [f"{base_code}-241", "上海主仓", "待出库", "波次待锁定", role_a, "2026-05-02"],
            [f"{base_code}-242", "苏州分拨", "在分拨", "月台拥堵", role_b, "2026-05-01"],
            [f"{base_code}-243", "杭州前置仓", "已回传", "签收回单待复核", role_c, "2026-04-30"],
        ]
    if kind == "signoffs":
        return [
            [f"{base_code}-251", "华东门店群", "待签收", "影像待上传", "待复核", "2026-05-02"],
            [f"{base_code}-252", "医药冷链站点", "已签收", "影像齐全", "通过", "2026-05-01"],
            [f"{base_code}-253", "商超仓配节点", "异常签收", "签章不完整", "退回补传", "2026-04-30"],
        ]
    if kind == "purchases":
        return [
            [f"{base_code}-101", f"{focus_a}核心原料", role_a, "待下单", "2026-05-08", "2026-05-02"],
            [f"{base_code}-102", f"{focus_b}备件采购", role_b, "供应确认中", "2026-05-10", "2026-05-01"],
            [f"{base_code}-103", f"{product_code}加急补货", role_c, "已到货", "2026-05-04", "2026-04-30"],
        ]
    if kind == "sales":
        return [
            [f"{base_code}-201", f"{focus_a}重点订单", "远峰客户", role_a, "待发运", "回款审核中", "2026-05-02"],
            [f"{base_code}-202", f"{focus_b}渠道订单", "晨屿商贸", role_b, "履约中", "已回款", "2026-05-01"],
            [f"{base_code}-203", f"{product_code}复核订单", "星曜客户", role_c, "已完成", "待开票", "2026-04-30"],
        ]
    if kind == "inventory":
        return [
            [f"{base_code}-301", f"{focus_a}主仓批次", "A-01-03", "1260", "低库存预警", "2026-05-02"],
            [f"{base_code}-302", f"{focus_b}周转批次", "B-02-01", "2480", "库存正常", "2026-05-01"],
            [f"{base_code}-303", f"{product_code}锁定批次", "C-03-07", "320", "冻结待复核", "2026-04-30"],
        ]
    if kind == "suppliers":
        return [
            [f"{base_code}-401", "华辰材料有限公司", "金属件", "月度协同", "资质有效", "2026-05-02"],
            [f"{base_code}-402", "远望仓储服务商", "仓配服务", "待续签", "证照待更新", "2026-05-01"],
            [f"{base_code}-403", "衡拓设备厂商", "包装设备", "持续合作", "资质有效", "2026-04-30"],
        ]
    if kind == "fulfillment":
        return [
            [f"{base_code}-501", f"{focus_a}履约任务", names[0], "备货排程", "待仓配确认", "2026-05-02"],
            [f"{base_code}-502", f"{focus_b}执行任务", names[1], "发运执行", "运输节点同步中", "2026-05-01"],
            [f"{base_code}-503", f"{product_code}闭环复核", names[2], "已签收", "结果记录完成", "2026-04-30"],
        ]
    if kind == "settlements":
        return [
            [f"{base_code}-601", "华辰材料有限公司", "86,000", "待复核", "待付款", "2026-05-02"],
            [f"{base_code}-602", "远望仓储服务商", "42,500", "已通过", "付款中", "2026-05-01"],
            [f"{base_code}-603", "衡拓设备厂商", "18,600", "已完成", "已付款", "2026-04-30"],
        ]
    if kind == "talents":
        return [
            [f"{base_code}-701", "晓鹿种草社", "小红书", "合作中", "12k-18k", "2026-05-02"],
            [f"{base_code}-702", "阿木评测", "抖音", "待签约", "20k-30k", "2026-05-01"],
            [f"{base_code}-703", "Melody生活志", "小红书", "长期合作", "8k-12k", "2026-04-30"],
        ]
    if kind == "clients":
        return [
            [f"{base_code}-801", "星曜美妆", "美妆个护", "方案沟通", role_a, "2026-05-02"],
            [f"{base_code}-802", "晨屿食品", "消费食品", "执行中", role_b, "2026-05-01"],
            [f"{base_code}-803", "远峰家居", "家居生活", "复盘中", role_c, "2026-04-30"],
        ]
    if kind == "campaigns":
        return [
            [f"{base_code}-901", "夏季新品种草", "小红书", "执行中", "80,000", "2026-05-02"],
            [f"{base_code}-902", "母亲节礼盒预热", "抖音", "待上线", "35,000", "2026-05-01"],
            [f"{base_code}-903", "618蓄水首轮", "双平台", "待审核", "200,000", "2026-04-30"],
        ]
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
            [f"{base_code}-101", names[0], _realistic_mobile_number(f"{product_code}|{title}|users|0"), role_a, "启用", "2026-05-02"],
            [f"{base_code}-102", names[1], _realistic_mobile_number(f"{product_code}|{title}|users|1"), role_b, "处理中", "2026-05-01"],
            [f"{base_code}-103", names[2], _realistic_mobile_number(f"{product_code}|{title}|users|2"), role_c, "已启用", "2026-04-30"],
        ]
    if kind == "actions":
        return [
            [f"{base_code}-201", f"{focus_a}执行任务", names[0], "待校验", f"{title}进入执行阶段", "2026-05-02"],
            [f"{base_code}-202", f"{focus_b}运行任务", names[1], "执行中", f"{keyword}结果回写", "2026-05-01"],
            [f"{base_code}-203", f"{title}复核任务", names[2], "已完成", f"{product_code}记录留存", "2026-04-30"],
        ]
    return [
        [f"{base_code}-001", f"{focus_a}{title}", role_a, "处理中", focus_b, "2026-05-02"],
        [f"{base_code}-002", f"{keyword}重点事项", role_b, "待审核", title, "2026-05-01"],
        [f"{base_code}-003", f"{product_code}{title}", role_c, "已完成", focus_a, "2026-04-30"],
    ]


def _module_domain_focus(title: str, keyword: str, focus_terms: list[str]) -> str:
    focus = "、".join(focus_terms[:3]) or keyword or title
    if _module_kind(title) == "power_dispatch":
        return "调度指令、负荷水平与执行状态"
    if _module_kind(title) == "grid_monitor":
        return "站点运行状态、断面越限与责任班组"
    if _module_kind(title) == "generation":
        return "机组出力、计划周期与并网状态"
    if _module_kind(title) == "work_tickets":
        return "工作票状态、检修对象与计划复电时间"
    if _module_kind(title) == "power_faults":
        return "故障事件、影响范围与恢复状态"
    if _module_kind(title) == "credit_subjects":
        return "授信主体、评级结论与授信额度"
    if _module_kind(title) == "financing":
        return "融资申请、审批阶段与放款状态"
    if _module_kind(title) == "exposure":
        return "资金敞口、阈值状态与责任归属"
    if _module_kind(title) == "trade_verification":
        return "贸易背景、单据完备度与核验结论"
    if _module_kind(title) == "dispatch":
        return "运单任务、调度状态与在途时效"
    if _module_kind(title) == "fleet":
        return "车辆状态、司机协同与运力位置"
    if _module_kind(title) == "routes":
        return "线路节点、拥堵等级与异常告警"
    if _module_kind(title) == "warehousing":
        return "仓配节点、分拨状态与协同异常"
    if _module_kind(title) == "signoffs":
        return "签收状态、回单完整度与复核结果"
    if _module_kind(title) == "purchases":
        return "采购申请、到货排期与供应状态"
    if _module_kind(title) == "sales":
        return "客户订单、执行进度与回款状态"
    if _module_kind(title) == "inventory":
        return "库存批次、库位余量与预警阈值"
    if _module_kind(title) == "suppliers":
        return "供应资质、协同进度与供方分类"
    if _module_kind(title) == "fulfillment":
        return "履约阶段、责任分工与处理结果"
    if _module_kind(title) == "settlements":
        return "应付金额、审核流转与付款状态"
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
    del role_phrase
    focus = "、".join(focus_terms[:3]) or _module_domain_focus(title, keyword, focus_terms)
    return [
        f"围绕{focus}组织页面信息、处理状态和结果摘要。",
        f"提供与{title}相关的查询、处理和结果查看入口。",
        f"当前页面内容与相关记录保持连续呈现，便于围绕同一主题完成操作。",
    ]


def _module_description(title: str, keyword: str, scene: str, focus_terms: list[str]) -> str:
    focus = _module_domain_focus(title, keyword, focus_terms)
    return (
        f"{title}模块围绕{scene}中的相关处理环节组织页面内容，承接与“{keyword or title}”有关的记录查看、状态处理和结果呈现。"
        f"页面重点展示{focus}等信息，并在统一界面中组织查询、处理和结果查看入口。"
    )


def _module_steps(title: str, primary_action: str, focus_terms: list[str]) -> list[str]:
    focus = _module_domain_focus(title, title, focus_terms)
    return [
        f"进入{title}页面后先查看与{focus}相关的主要信息区域，确认当前处理范围。",
        "结合页面检索区、列表区或摘要区定位目标记录，核对状态与结果信息。",
        f"根据当前处理需要执行“{primary_action}”或相关页面操作，并完成必要的信息更新。",
        "处理完成后复核页面反馈、状态变化和最近更新时间，确认结果已经在页面中正确呈现。",
    ]


def _module_business_value(title: str, keyword: str, scene: str) -> str:
    return (
        f"{title}页面将与{keyword or title}相关的记录、状态和结果信息集中展示在统一界面中，用于围绕{scene}持续查看和处理当前事项。"
    )


def _build_task_specific_module(
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
    if _has_power_dispatch_context(source):
        return "电网运行监视、负荷调度、检修协同与故障处置"
    if any(token in source for token in ["物流", "调度", "运单", "车队", "线路", "签收", "仓配"]):
        return "运单编排、车队调度、线路跟踪与签收回单协同"
    if any(token in source for token in ["金融", "融资", "授信", "敞口", "保理", "资金", "贸易背景", "核心企业"]):
        return "授信分析、融资监控、贸易背景核验与资金风险处置"
    if any(token in source for token in ["股票", "量化", "策略", "回测", "交易", "因子"]):
        return "量化策略研究、市场数据管理、回测分析与交易执行协同"
    if any(token in source for token in ["能耗", "园区", "设备", "巡检", "告警"]):
        return "能耗监测、设备巡检、告警处置与运维协同"
    if any(token in source for token in ["短剧", "剧集", "演员", "片单", "番剧", "内容发行"]):
        return "内容编排、演员协同、用户反馈运营与数据复盘"
    if any(token in source for token in ["投放", "达人", "营销", "品牌", "种草"]):
        return "品牌投放管理、内容协同与效果复盘"
    if any(token in source for token in ["风控", "审计", "合规", "预警"]):
        return "风险监测、审计留痕与预警处置"
    del preset
    anchor = _clean_phrase(keyword or "") or "当前产品"
    return f"{anchor}相关信息处理、页面操作与结果查看"


def _compose_scene(keyword: str, product_name: str, industry: str | None, module_titles: list[str], preset: DomainPreset) -> str:
    scene = _infer_scene(keyword, industry, module_titles, preset)
    industry = _clean_phrase(industry or "")
    if industry and industry not in scene:
        return f"{industry}领域的{scene}"
    return scene


def _compose_industry_scope(keyword: str, industry: str | None, preset: DomainPreset, focus_terms: list[str]) -> str:
    fragments = [industry or "", "、".join(focus_terms[:3])]
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
    del roles, preset, blueprint
    return [
        {"title": "主要页面", "value": str(max(len(modules), 1)), "color": "#1677ff"},
        {"title": "主题要点", "value": str(max(len(focus_terms), 1)), "color": "#52c41a"},
        {"title": "操作视图", "value": str(max(len(modules) + 2, 3)), "color": "#faad14"},
        {"title": "结果信息", "value": str(max(len(modules), 1)), "color": "#722ed1"},
    ]


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
                        {
                            "action": "fill_input",
                            "target": "搜索",
                            "value": search_value,
                            "optional": True,
                        },
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
            f"{product_name}围绕“{topic}”相关业务场景构建，面向{industry_scope}中的日常信息处理、状态查看与结果查询需求。"
            f"软件以前台可见页面和业务操作界面为主要组织方式，包含{module_titles}等核心功能内容，并以{scene}为主线展开页面结构。"
            "相关业务信息在同一套软件界面中连续呈现，便于围绕当前产品主题完成日常处理与结果查看。"
        ),
        100,
        "同时，软件围绕当前产品主题提供统一页面入口、状态反馈和结果查看能力，使主要业务内容能够持续呈现。",
    )


def _build_purpose_text(
    product_name: str,
    keyword: str,
    scene: str,
    roles: list[str],
    modules: list[dict],
) -> str:
    topic = _topic_label(keyword, product_name)
    module_titles = "、".join(module["title"] for module in modules[:6])
    del roles
    return _ensure_min_length(
        (
            f"{product_name}的建设目的在于围绕“{topic}”形成一套可直接投入使用的正式软件产品，"
            f"围绕{scene}提供连续可见的页面入口、处理界面和结果信息。"
            f"软件以{module_titles}作为主要功能内容，将相关业务记录、状态变化和处理结果集中呈现在结构化页面中，"
            "使产品功能、页面信息与操作路径保持清晰一致。"
        ),
        100,
        "软件同时通过清晰的页面入口、结构化信息展示和稳定的操作反馈机制，支持日常使用与持续迭代。",
    )


def _build_main_functions(
    product_name: str,
    keyword: str,
    modules: list[dict],
    roles: list[str],
) -> str:
    topic = _topic_label(keyword, product_name)
    segments = []
    for module in modules[:8]:
        headers = "、".join(module.get("table_headers", [])[:3]) or "页面信息"
        highlights = "；".join(module.get("highlights", [])[:2])
        primary_action = module.get("primary_action") or f"处理{module['title']}"
        segments.append(
            f"{module['title']}围绕{headers}等信息组织页面内容，支持“{primary_action}”等关键处理动作；{highlights}。"
        )
    del roles
    return _ensure_min_length(
        (
            f"{product_name}的软件主要功能围绕“{topic}”相关业务流程展开，在统一系统内组织页面查看、记录处理与结果跟踪。"
            + "".join(segments)
            + "此外，软件还提供统一登录、首页概览、检索筛选、状态更新、结果查询和配置维护等公共能力，"
            "使相关业务信息能够在首页与各页面之间连续呈现。"
        ),
        500,
        "软件通过明确的页面入口、状态标签和结果视图组织功能内容，使当前产品主题能够被连续呈现。",
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
    del roles
    return _ensure_min_length(
        (
            f"{product_name}围绕“{topic}”对应的{scene}需求组织软件功能，采用统一页面入口、结构化信息区域和连续操作路径呈现产品内容。"
            f"软件将{module_titles}等页面组织为相互衔接的功能界面，并通过状态标签、结果摘要和页面反馈保持处理过程清晰可见。"
            "相关功能以浏览器可访问的软件形态提供，便于在正式运行环境中持续使用。"
        ),
        100,
        "同时，软件支持主流浏览器访问、结构化信息展示和连续页面操作，适合持续迭代与长期使用。",
    )


def _architecture_style(preset_key: str, app_type: str, scene: str) -> str:
    if preset_key == "power_dispatch":
        return "control_tower"
    if preset_key == "logistics":
        return "dispatch_flow"
    if preset_key == "supply_chain_finance":
        return "risk_grid"
    if app_type == "desktop_client":
        return "desktop_console"
    if "分析" in scene or "监控" in scene:
        return "analysis_grid"
    return "layered_stack"


def _build_project_dna(
    *,
    keyword: str,
    product_name: str,
    preset: DomainPreset,
    scene: str,
    focus_terms: list[str],
    modules: list[dict],
    experience_blueprint: dict,
    visual_profile: dict,
    app_type: str,
    core_entities: list[str] | None = None,
    raw_user_request: dict | None = None,
) -> dict:
    return {
        "preset_key": preset.key,
        "product_anchor": _topic_label(keyword, product_name),
        "scene": scene,
        "app_type": app_type,
        "focus_terms": list(focus_terms[:5]),
        "module_signature": [module.get("title", "") for module in modules[:6]],
        "interaction_tone": experience_blueprint.get("tone", ""),
        "visual_anchor": visual_profile.get("name", ""),
        "architecture_style": _architecture_style(preset.key, app_type, scene),
        "domain_entities": list((core_entities or preset.core_entities)[:5]),
        "source_of_truth": "raw_user_request",
        "raw_user_request": dict(raw_user_request or {}),
    }


def build_task_profile(
    *,
    keyword: str,
    product_name: str,
    version: str | None = None,
    industry: str | None = None,
    notes: str | None = None,
    prd_summary: dict | None = None,
) -> dict:
    preset = _select_preset(keyword, product_name, industry)
    version = version or DEFAULT_VERSION
    prd_summary = prd_summary or {}
    raw_user_request = dict(
        prd_summary.get("raw_user_request")
        or _build_raw_user_request(keyword, product_name, industry, notes)
    )
    app_type = _infer_app_type(keyword, product_name, industry, prd_summary)
    product_code = _product_code(keyword, product_name)
    module_titles = list(prd_summary.get("core_modules") or [])
    if not module_titles:
        inferred_titles = _split_terms(keyword, product_name, industry or "")
        module_titles = [title for title in inferred_titles if len(title) >= 2][:8]
    if not module_titles:
        module_titles = [product_name or keyword or "核心业务"][:1]
    module_titles = list(dict.fromkeys(str(title).strip() for title in module_titles if str(title).strip()))
    page_routes = list(prd_summary.get("required_pages") or [])
    roles = [
        str(item).strip()
        for item in (prd_summary.get("user_roles") or [])
        if str(item).strip()
    ]
    core_entities = [
        str(item).strip()
        for item in (prd_summary.get("core_entities") or [])
        if str(item).strip()
    ]
    focus_terms = _split_terms(keyword, product_name, industry or "", *module_titles)[:6]
    if not core_entities:
        core_entities = list(focus_terms[:5])
    topic_label = _topic_label(keyword, product_name)
    scene = _clean_phrase(str(prd_summary.get("scene") or "")) or _compose_scene(
        keyword or product_name,
        product_name,
        industry,
        module_titles,
        preset,
    )
    industry_scope = _clean_phrase(str(prd_summary.get("industry_scope") or "")) or _compose_industry_scope(
        keyword,
        industry,
        preset,
        focus_terms,
    )
    design_seed = _build_design_seed(keyword, product_name, industry, notes, raw_user_request)
    experience_blueprint = _pick_experience_blueprint(product_code, preset.key, design_seed)
    visual_profile = _build_visual_profile(product_code, preset.key, app_type, experience_blueprint, design_seed)

    profile_modules = []
    for idx, title in enumerate(module_titles):
        preset_module = _build_module(title, "", _MODULE_ICONS[idx % len(_MODULE_ICONS)])
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
            )
        )
    profile_modules = _ensure_unique_module_routes(profile_modules)

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
    project_dna = _build_project_dna(
        keyword=keyword,
        product_name=product_name,
        preset=preset,
        scene=scene,
        focus_terms=focus_terms,
        modules=profile_modules,
        experience_blueprint=experience_blueprint,
        visual_profile=visual_profile,
        app_type=app_type,
        core_entities=core_entities,
        raw_user_request=raw_user_request,
    )

    created_date = datetime.now().strftime("%Y年%m月%d日")
    profile = {
        "keyword": keyword,
        "product_name": product_name,
        "raw_user_request": raw_user_request,
        "topic_label": topic_label,
        "preset_key": preset.key,
        "app_type": app_type,
        "version": version,
        "short_name": _short_name(product_name, preset.short_name),
        "product_code": product_code,
        "design_seed": design_seed,
        "scene": scene,
        "software_category": preset.software_category,
        "industry_scope": industry_scope,
        "development_date": created_date,
        "hardware_environment": "Intel/AMD x86_64 处理器、8GB 及以上内存、100GB 以上可用磁盘空间、千兆网络环境",
        "runtime_hardware_environment": "Intel/AMD x86_64 处理器、4GB 及以上内存、50GB 以上可用磁盘空间、稳定网络环境",
        "development_os": "Linux / macOS / Windows",
        "runtime_platform": _runtime_platform_by_app_type(app_type),
        "support_environment": _support_env_by_app_type(preset.support_env, app_type),
        "development_tools": preset.dev_tools,
        "programming_language": "Python、TypeScript、JavaScript、SQL",
        "source_code_line_estimate": 0,
        "development_background": _build_background_text(product_name, keyword, scene, industry_scope, profile_modules),
        "development_purpose": _build_purpose_text(product_name, keyword, scene, roles, profile_modules),
        "main_functions": _build_main_functions(product_name, keyword, profile_modules, roles),
        "technical_features": _build_technical_features(product_name, keyword, profile_modules, roles, scene),
        "user_roles": roles,
        "dashboard_metrics": _build_dashboard_metrics(profile_modules, roles, focus_terms, preset, experience_blueprint),
        "modules": profile_modules,
        "screenshot_scenarios": screenshot_scenarios,
        "experience_blueprint": experience_blueprint,
        "project_dna": project_dna,
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
        "core_entities": core_entities,
        "focus_terms": focus_terms,
    }
    return profile


def build_plan_seed(
    keyword: str,
    product_name: str,
    industry: str | None = None,
    notes: str | None = None,
) -> dict:
    keyword = _clean_phrase(str(keyword or ""))
    product_name = _clean_phrase(str(product_name or ""))
    industry = _clean_phrase(str(industry or "")) or None
    raw_user_request = _build_raw_user_request(keyword, product_name, industry, notes)
    preset = _select_preset(keyword, product_name, industry)
    app_type = _infer_app_type(keyword, product_name, industry)
    module_titles = _split_terms(keyword, product_name, industry or "")[:5]
    scene = _compose_scene(keyword or product_name, product_name, industry, module_titles, preset)
    focus_terms = _split_terms(keyword, product_name, industry or "", *module_titles)[:5]
    return {
        "raw_user_request": raw_user_request,
        "source_of_truth": "raw_user_request",
        "app_type": app_type,
        "preset_key": preset.key,
        "preset_name": preset.name,
        "scene": scene,
        "industry_scope": _compose_industry_scope(keyword, industry, preset, focus_terms),
        "core_entities": [],
        "user_roles": [],
        "core_modules": [],
        "required_pages": ["/login", "/dashboard"],
        "focus_terms": focus_terms,
    }


def _frontend_module_profile(module: dict) -> dict:
    return {
        "key": module.get("key", ""),
        "title": module.get("title", ""),
        "route": module.get("route", ""),
        "icon": module.get("icon", ""),
        "highlights": list(module.get("highlights", []) or []),
        "description": module.get("description", ""),
    }


def build_frontend_profile_source(profile: dict) -> str:
    frontend_profile = {
        "keyword": profile.get("keyword", ""),
        "product_name": profile.get("product_name", ""),
        "app_type": profile.get("app_type", "admin_web"),
        "version": profile.get("version", ""),
        "short_name": profile.get("short_name", ""),
        "product_code": profile.get("product_code", ""),
        "scene": profile.get("scene", ""),
        "software_category": profile.get("software_category", ""),
        "industry_scope": profile.get("industry_scope", ""),
        "user_roles": list(profile.get("user_roles", []) or []),
        "dashboard_metrics": list(profile.get("dashboard_metrics", []) or []),
        "nav_items": list(profile.get("nav_items", []) or []),
        "modules": [_frontend_module_profile(module) for module in (profile.get("modules", []) or [])],
        "focus_terms": list(profile.get("focus_terms", []) or []),
    }
    payload = json.dumps(frontend_profile, ensure_ascii=False, indent=2)
    return (
        "export type ModuleProfile = {\n"
        "  key: string;\n"
        "  title: string;\n"
        "  route: string;\n"
        "  icon: string;\n"
        "  highlights: string[];\n"
        "  description: string;\n"
        "};\n\n"
        "export type AppProfile = {\n"
        "  keyword: string;\n"
        "  product_name: string;\n"
        "  topic_label?: string;\n"
        "  preset_key?: string;\n"
        "  app_type: string;\n"
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
        "  focus_terms?: string[];\n"
        "};\n\n"
        f"export const APP_PROFILE: AppProfile = {payload} as unknown as AppProfile;\n"
    )


def build_backend_profile_source(profile: dict) -> str:
    return (
        "from __future__ import annotations\n\n"
        f"APP_PROFILE = {pprint.pformat(profile, width=100, sort_dicts=False)}\n"
    )
