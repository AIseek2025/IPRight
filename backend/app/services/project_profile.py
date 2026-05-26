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


def _module_code_prefix(kind: str, index: int) -> str:
    prefixes = {
        "recruitment_demands": "REQ",
        "recruitment_candidates": "CAN",
        "recruitment_interviews": "INT",
        "recruitment_offers": "OFF",
        "talent_pool": "TAL",
        "recruitment_reports": "RPT",
        "power_dispatch": "DSP",
        "grid_monitor": "GRD",
        "generation": "GEN",
        "work_tickets": "WRK",
        "power_faults": "FLT",
        "credit_subjects": "CRD",
        "financing": "FIN",
        "exposure": "EXP",
        "trade_verification": "TRD",
        "dispatch": "LOG",
        "fleet": "VEH",
        "routes": "RTE",
        "warehousing": "WRH",
        "signoffs": "POD",
        "purchases": "PUR",
        "sales": "SAL",
        "inventory": "INV",
        "suppliers": "SUP",
        "fulfillment": "FUL",
        "settlements": "STL",
        "talents": "KOL",
        "clients": "CLT",
        "campaigns": "CMP",
        "analytics": "ANL",
        "settings": "CFG",
        "alerts": "ALT",
        "users": "USR",
        "actions": "ACT",
        "records": "REC",
    }
    return prefixes.get(kind, f"M{index + 1:02d}")


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


def _clean_fragment(text: str) -> str:
    return _clean_phrase(text).rstrip("，,。；;：:、 ")


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


def _pick_experience_blueprint(product_code: str, preset_key: str, design_seed: str = "") -> dict:
    seed = f"{product_code}|{preset_key}|{design_seed}"
    navigation_variant = ["top_tabs", "indexed", "sectioned"][_seed_index(seed, 3)]
    login_variant = ["spotlight", "briefing", "workspace", "editorial"][_seed_index(f"{seed}|login", 4)]
    dashboard_variant = ["command", "insight", "workspace", "storyboard"][_seed_index(f"{seed}|dashboard", 4)]
    module_pool = ["operations", "workspace", "insight", "records", "studio", "board"]
    offset = _seed_index(f"{seed}|modules", len(module_pool))
    module_variants = [module_pool[(offset + idx) % len(module_pool)] for idx in range(3)]
    shell_hints = {
        "top_tabs": [
            "顶部主导航 + 横向概览带 + 自由组合内容画布，避免默认左侧深色竖栏后台",
            "顶部标签导航 + 主题摘要区 + 多节内容面板，避免复用统一后台骨架",
            "顶部导航条 + 模块切换条 + 宽屏工作台画布，避免整站左侧固定竖栏",
            "顶部导航 + 横向任务带 + 重点内容分镜区，避免通用后台套板",
        ],
        "indexed": [
            "顶部索引导航 + 过滤工具带 + 双列或三列分析画布，避免统一侧栏壳层",
            "顶部索引区 + 摘要栏 + 模块化内容画布，避免复用单一后台模板",
            "顶部索引导航 + 横向筛选区 + 并列信息面板，避免默认左侧竖栏后台",
            "顶部索引标签 + 内容分栏区 + 分析摘要面板，避免整站同一套后台骨架",
        ],
        "sectioned": [
            "顶部标题区 + 分段导航 + 协同工作区，不要默认整站左侧固定竖栏",
            "标题区 + 章节导航 + 多面板工作区，避免复用统一左侧深色竖栏",
            "顶部标题条 + 分区导航 + 模块工作台，不要回退为通用后台侧栏",
            "标题区 + 分段标签 + 自由排布工作面板，避免同一套后台壳层",
        ],
    }
    tones = {
        "top_tabs": [
            "强调任务节奏、横向信息组织与首页工作入口",
            "强调主题切换、内容分镜与宽屏工作台",
            "强调导航编排、模块分镜和操作聚焦",
        ],
        "indexed": [
            "强调分析结论、关键洞察与对比视图",
            "强调索引检索、摘要导航与信息分层",
            "强调多维观察、过滤比较与重点提炼",
        ],
        "sectioned": [
            "强调岗位协同、分区工作台与任务闭环",
            "强调章节切换、多人协作与过程承接",
            "强调模块分段、责任边界与执行面板",
        ],
    }
    return {
        "name": f"{navigation_variant}_{dashboard_variant}_{_seed_index(f'{seed}|name', 97)}",
        "login_variant": login_variant,
        "dashboard_variant": dashboard_variant,
        "module_variants": module_variants,
        "navigation_variant": navigation_variant,
        "shell_layout_hint": shell_hints[navigation_variant][_seed_index(f"{seed}|shell", len(shell_hints[navigation_variant]))],
        "tone": tones[navigation_variant][_seed_index(f"{seed}|tone", len(tones[navigation_variant]))],
    }


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
        {
            "name": "plum_signal_gallery",
            "shell_background": "#faf5ff",
            "nav_background": "#581c87",
            "nav_text": "#f3e8ff",
            "panel_background": "#ffffff",
            "panel_border": "#e9d5ff",
            "accent": "#9333ea",
            "soft": "#f5f3ff",
            "strong": "#7e22ce",
            "layout_signal": "顶部主导航 + 横向主题带 + 分镜式工作画布，避免统一后台套板",
            "chrome_treatment": "top_tabs",
        },
        {
            "name": "sunrise_operation_ribbon",
            "shell_background": "#fff8f1",
            "nav_background": "#7c2d12",
            "nav_text": "#ffedd5",
            "panel_background": "#fffdf9",
            "panel_border": "#fed7aa",
            "accent": "#ea580c",
            "soft": "#fff7ed",
            "strong": "#c2410c",
            "layout_signal": "顶部导航条 + 横向运营带 + 多区块工作台，避免左侧竖栏后台",
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
        {
            "name": "jade_observer_grid",
            "shell_background": "#f0fdf9",
            "nav_background": "#14532d",
            "nav_text": "#dcfce7",
            "panel_background": "#ffffff",
            "panel_border": "#bbf7d0",
            "accent": "#16a34a",
            "soft": "#f0fdf4",
            "strong": "#15803d",
            "layout_signal": "顶部索引导航 + 内容分栏区 + 摘要面板，避免通用后台壳层",
            "chrome_treatment": "indexed_topbar",
        },
        {
            "name": "rose_story_matrix",
            "shell_background": "#fff4f6",
            "nav_background": "#9f1239",
            "nav_text": "#ffe4e6",
            "panel_background": "#fffdfd",
            "panel_border": "#fecdd3",
            "accent": "#e11d48",
            "soft": "#fff1f2",
            "strong": "#be123c",
            "layout_signal": "顶部索引区 + 叙事摘要栏 + 分析矩阵区，避免复用统一后台模板",
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
        {
            "name": "violet_case_panels",
            "shell_background": "#f7f5ff",
            "nav_background": "#4c1d95",
            "nav_text": "#ede9fe",
            "panel_background": "#ffffff",
            "panel_border": "#ddd6fe",
            "accent": "#7c3aed",
            "soft": "#f5f3ff",
            "strong": "#6d28d9",
            "layout_signal": "顶部标题区 + 分段导航 + 案例式工作面板，避免默认左侧后台壳层",
            "chrome_treatment": "sectioned_header",
        },
        {
            "name": "olive_process_board",
            "shell_background": "#f7fee7",
            "nav_background": "#365314",
            "nav_text": "#ecfccb",
            "panel_background": "#fdfffa",
            "panel_border": "#d9f99d",
            "accent": "#65a30d",
            "soft": "#f7fee7",
            "strong": "#4d7c0f",
            "layout_signal": "标题区 + 分段标签 + 过程面板工作区，避免复用单一后台骨架",
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
    if any(token in title for token in ["招聘需求"]):
        return "recruitment_demands"
    if any(token in title for token in ["职位与候选人", "候选人", "岗位管理", "职位管理"]):
        return "recruitment_candidates"
    if any(token in title for token in ["面试与流程", "面试流程", "流程管理"]):
        return "recruitment_interviews"
    if any(token in title for token in ["录用与入职", "Offer", "入职管理", "入职流程"]):
        return "recruitment_offers"
    if any(token in title for token in ["人才库", "资料中心", "人才档案"]):
        return "talent_pool"
    if any(token in title for token in ["招聘数据分析", "招聘报表", "招聘分析", "招聘数据分析与报表", "数据分析看板"]):
        return "recruitment_reports"
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
    if len(page_routes) > index + 2 and page_routes[index + 2]:
        return page_routes[index + 2]
    hinted_route = _module_route_hint(title)
    if hinted_route:
        return hinted_route
    if fallback_route:
        return fallback_route
    return f"/{_slug_key(title)}"


def _module_headers(kind: str) -> list[str]:
    if kind == "recruitment_demands":
        return ["需求编号", "需求主题", "用人部门", "招聘阶段", "优先级", "更新时间"]
    if kind == "recruitment_candidates":
        return ["候选人编号", "候选人姓名", "应聘岗位", "当前阶段", "来源渠道", "更新时间"]
    if kind == "recruitment_interviews":
        return ["流程编号", "候选人姓名", "面试环节", "安排状态", "面试官", "更新时间"]
    if kind == "recruitment_offers":
        return ["录用编号", "候选人姓名", "录用岗位", "办理阶段", "责任人", "更新时间"]
    if kind == "talent_pool":
        return ["人才编号", "人才方向", "最近进展", "储备等级", "归属顾问", "更新时间"]
    if kind == "recruitment_reports":
        return ["报表编号", "报表主题", "统计周期", "负责人", "核心结论", "更新时间"]
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
        return ["车辆编号", "司机姓名", "车辆状态", "当前任务", "在途位置", "更新时间"]
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
        return ["账号编号", "姓名", "角色", "负责范围", "状态", "最近更新"]
    if kind == "actions":
        return ["任务编号", "任务主题", "执行人", "当前阶段", "结果摘要", "更新时间"]
    return ["记录编号", "主题名称", "责任角色", "当前状态", "业务标签", "更新时间"]


def _module_primary_action(title: str) -> str:
    if any(token in title for token in ["招聘需求"]):
        return "新建招聘需求"
    if any(token in title for token in ["职位与候选人", "候选人", "岗位管理", "职位管理"]):
        return "新增候选人推进记录"
    if any(token in title for token in ["面试与流程", "面试流程", "流程管理"]):
        return "安排面试流程"
    if any(token in title for token in ["录用与入职", "Offer", "入职管理", "入职流程"]):
        return "发起录用与入职流程"
    if any(token in title for token in ["人才库", "资料中心", "人才档案"]):
        return "录入人才档案"
    if any(token in title for token in ["招聘数据分析", "招聘报表", "招聘分析", "招聘数据分析与报表", "数据分析看板"]):
        return "生成招聘分析报表"
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
    if any(token in title for token in ["招聘需求"]):
        return "搜索需求编号 / 用人部门 / 招聘阶段"
    if any(token in title for token in ["职位与候选人", "候选人", "岗位管理", "职位管理"]):
        return "搜索候选人姓名 / 应聘岗位 / 当前阶段"
    if any(token in title for token in ["面试与流程", "面试流程", "流程管理"]):
        return "搜索候选人姓名 / 面试环节 / 安排状态"
    if any(token in title for token in ["录用与入职", "Offer", "入职管理", "入职流程"]):
        return "搜索候选人姓名 / 录用岗位 / 办理阶段"
    if any(token in title for token in ["人才库", "资料中心", "人才档案"]):
        return "搜索人才方向 / 储备等级 / 归属顾问"
    if any(token in title for token in ["招聘数据分析", "招聘报表", "招聘分析", "招聘数据分析与报表", "数据分析看板"]):
        return "搜索报表主题 / 统计周期 / 负责人"
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
        return "搜索运单编号 / 起讫区域 / 调度责任人"
    if any(token in title for token in ["车辆", "司机", "车队", "运力"]):
        return "搜索车辆编号 / 司机姓名 / 任务状态"
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
    base_code = _ascii_token(title, _module_code_prefix(kind, index))[:4]
    names = _pick_names(f"{product_code}|{title}", 3)
    focus_a = focus_terms[0] if focus_terms else keyword
    focus_b = focus_terms[1] if len(focus_terms) > 1 else title
    role_a = roles[0] if roles else "管理员"
    role_b = roles[1] if len(roles) > 1 else role_a
    role_c = roles[2] if len(roles) > 2 else role_b
    if kind == "recruitment_demands":
        return [
            ["REQ-202605-013", "初中数学教研岗补录", "师资发展中心", "简历初筛", "高", "2026-05-22 09:30"],
            ["REQ-202605-009", "双语科学教师储备", "国际课程部", "部门复核", "中", "2026-05-21 16:20"],
            ["REQ-202605-004", "校招班主任岗位扩编", "学生发展处", "已发布", "高", "2026-05-20 11:10"],
        ]
    if kind == "recruitment_candidates":
        return [
            ["CAN-202605-031", names[0], "初中数学教研岗", "复试安排", "校园宣讲会", "2026-05-22 10:10"],
            ["CAN-202605-018", names[1], "双语科学教师", "用人部门评估", "内部推荐", "2026-05-21 18:05"],
            ["CAN-202605-007", names[2], "班主任储备岗", "Offer沟通", "招聘官网", "2026-05-20 14:40"],
        ]
    if kind == "recruitment_interviews":
        return [
            ["INT-202605-021", names[0], "试讲评估", "已排期", "教研主任", "2026-05-22 13:30"],
            ["INT-202605-014", names[1], "综合复试", "待确认", "招聘主管", "2026-05-21 17:50"],
            ["INT-202605-006", names[2], "终面沟通", "已完成", "校区负责人", "2026-05-20 15:05"],
        ]
    if kind == "recruitment_offers":
        return [
            ["OFF-202605-015", names[0], "初中数学教研岗", "Offer审批中", "招聘主管", "2026-05-22 15:20"],
            ["OFF-202605-011", names[1], "双语科学教师", "待发入职材料", "HR专员", "2026-05-21 19:00"],
            ["OFF-202605-004", names[2], "班主任储备岗", "已完成入职", "校区负责人", "2026-05-20 17:10"],
        ]
    if kind == "talent_pool":
        return [
            ["TAL-202605-082", "理科教师储备", "完成首轮沟通并补充试讲视频", "A", "校招顾问", "2026-05-22 08:55"],
            ["TAL-202605-057", "双语教师储备", "更新海外课程经历与证书材料", "A-", "招聘顾问", "2026-05-21 19:15"],
            ["TAL-202605-024", "德育管理储备", "进入校区意向跟进阶段", "B+", "人才运营", "2026-05-20 10:25"],
        ]
    if kind == "recruitment_reports":
        return [
            ["RPT-202605-011", "周度岗位转化分析", "2026W21", role_a, "数学教师岗位复试转化率提升至42%", "2026-05-22 09:05"],
            ["RPT-202605-008", "渠道到面效率对比", "2026年05月", role_b, "内部推荐渠道到面效率最高", "2026-05-21 18:40"],
            ["RPT-202605-003", "校招储备结构复盘", "春招阶段", role_c, "双语教师储备仍需补强", "2026-05-20 16:30"],
        ]
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
            [f"{base_code}-211", "沪宁专线", names[0], "待派车", "4h 30m", "2026-05-02"],
            [f"{base_code}-212", "华东集配", names[1], "在途", "6h 10m", "2026-05-01"],
            [f"{base_code}-213", "冷链次晨达", names[2], "已签收", "2h 50m", "2026-04-30"],
        ]
    if kind == "fleet":
        return [
            [f"{base_code}-221", "沪A-3278D", names[0], "待发车", "华东仓配", "嘉定分拨场", "2026-05-02"],
            [f"{base_code}-222", "苏B-9182K", names[1], "运输中", "冷链专线", "无锡中转站", "2026-05-01"],
            [f"{base_code}-223", "浙C-7731P", names[2], "待回场", "城配末端", "杭州东站点", "2026-04-30"],
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
            [f"{base_code}-243", "杭州前置仓", "已回传", "签收回单待归档", role_c, "2026-04-30"],
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
            [f"{base_code}-403", "衡拓设备厂商", "包装设备", "已归档", "资质有效", "2026-04-30"],
        ]
    if kind == "fulfillment":
        return [
            [f"{base_code}-501", f"{focus_a}履约任务", names[0], "备货排程", "待仓配确认", "2026-05-02"],
            [f"{base_code}-502", f"{focus_b}交付任务", names[1], "发运执行", "运输节点同步中", "2026-05-01"],
            [f"{base_code}-503", f"{product_code}闭环复核", names[2], "已签收", "结果归档完成", "2026-04-30"],
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
            [f"{base_code}-703", "Melody生活志", "小红书", "已归档", "8k-12k", "2026-04-30"],
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
        [f"{base_code}-002", f"{title}协同跟进", role_b, "待审核", focus_a, "2026-05-01"],
        [f"{base_code}-003", f"{product_code}{title}", role_c, "已完成", focus_a, "2026-04-30"],
    ]


def _module_domain_focus(title: str, keyword: str, focus_terms: list[str]) -> str:
    selected_terms: list[str] = []
    for term in [title, *focus_terms, keyword]:
        normalized = str(term).strip()
        if not normalized or normalized in selected_terms:
            continue
        selected_terms.append(normalized)
        if len(selected_terms) >= 3:
            break
    focus = "、".join(selected_terms) or keyword or title
    if _module_kind(title) == "recruitment_demands":
        return "需求编号、用人部门与招聘阶段"
    if _module_kind(title) == "recruitment_candidates":
        return "候选人姓名、应聘岗位与推进阶段"
    if _module_kind(title) == "recruitment_interviews":
        return "面试环节、安排状态与面试官"
    if _module_kind(title) == "recruitment_offers":
        return "候选人姓名、录用岗位与办理阶段"
    if _module_kind(title) == "talent_pool":
        return "人才方向、储备等级与跟进进展"
    if _module_kind(title) == "recruitment_reports":
        return "统计周期、渠道表现与转化结论"
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
        return "运单任务、调度责任人与在途时效"
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
        return "客户订单、交付承诺与回款状态"
    if _module_kind(title) == "inventory":
        return "库存批次、库位余量与预警阈值"
    if _module_kind(title) == "suppliers":
        return "供应资质、协同进度与供方分类"
    if _module_kind(title) == "fulfillment":
        return "履约阶段、责任分工与交付结果"
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
    focus = _module_domain_focus(title, keyword, focus_terms)
    kind = _module_kind(title)
    if kind == "recruitment_demands":
        return [
            "支持围绕需求编号、用人部门和招聘阶段统一查看岗位需求流转情况",
            "支持按岗位方向、优先级和处理阶段快速定位待推进的招聘需求",
            f"支持{role_phrase}同步需求确认结果、编制信息和发布时间节点",
        ]
    if kind == "recruitment_candidates":
        return [
            "支持围绕候选人姓名、应聘岗位和当前阶段持续跟踪推进进度",
            "支持按来源渠道、候选人状态和岗位方向快速筛查重点人选",
            f"支持{role_phrase}共享评估意见、沟通记录和Offer推进结果",
        ]
    if kind == "recruitment_interviews":
        return [
            "支持围绕面试环节、安排状态和面试官统一查看流程推进情况",
            "支持按候选人姓名、流程阶段和排期结果快速定位待确认事项",
            f"支持{role_phrase}同步试讲反馈、复试结论和终面安排记录",
        ]
    if kind == "recruitment_offers":
        return [
            "支持围绕候选人姓名、录用岗位和办理阶段统一查看录用推进情况",
            "支持按审批状态、入职材料和责任人快速定位待处理的录用事项",
            f"支持{role_phrase}同步 Offer 审批、材料回收和入职确认结果",
        ]
    if kind == "talent_pool":
        return [
            "支持围绕人才方向、储备等级和最近进展统一维护人才档案",
            "支持按归属顾问、储备状态和关键标签快速筛查重点储备人选",
            f"支持{role_phrase}共享跟进结论、资料更新和后续联系计划",
        ]
    if kind == "recruitment_reports":
        return [
            "支持围绕招聘周期、渠道表现和转化结果生成统计报表",
            "支持按岗位方向、统计周期和负责人快速定位需要复盘的分析结果",
            f"支持{role_phrase}共享复盘结论、趋势判断和优化建议",
        ]
    if kind == "power_dispatch":
        return [
            "支持围绕调度单元、负荷水平和执行状态统一查看日内调度指令",
            "支持按值班调度员、执行状态和负荷区间快速定位重点指令",
            f"支持{role_phrase}同步调度令、负荷调整结果和执行反馈",
        ]
    if kind == "grid_monitor":
        return [
            "支持围绕输变线路、站点状态和断面越限统一查看电网运行健康度",
            "支持按线路名称、越限等级和责任班组快速筛查重点风险",
            f"支持{role_phrase}共享断面监测结果、处置建议和运行留痕",
        ]
    if kind == "generation":
        return [
            "支持围绕机组出力、新能源并网和滚动计划统一维护发电计划",
            "支持按机组、电源类型和计划周期快速定位需调整的计划项",
            f"支持{role_phrase}同步计划修订、功率目标和并网反馈",
        ]
    if kind == "work_tickets":
        return [
            "支持围绕检修对象、工作票状态和计划复电时间统一查看检修安排",
            "支持按票号、许可状态和检修类型筛查待协同事项",
            f"支持{role_phrase}共享检修许可、停复电进度和安全措施记录",
        ]
    if kind == "power_faults":
        return [
            "支持围绕越限告警、停电事件和保护动作统一组织故障联动处置",
            "支持按影响范围、恢复状态和处置阶段快速筛查重点事件",
            f"支持{role_phrase}同步故障研判、恢复进度和复盘留痕",
        ]
    if kind == "credit_subjects":
        return [
            "支持围绕核心企业、供应商与渠道主体维护授信额度和评级结果",
            "支持按授信状态、预警等级和额度占用快速筛查重点主体",
            f"支持{role_phrase}共享授信结论、评级依据和后续复核记录",
        ]
    if kind == "financing":
        return [
            "支持围绕融资申请、审批阶段和放款状态跟踪项目进展",
            "支持按融资产品、申请企业和复核状态定位重点申请",
            f"支持{role_phrase}同步尽调意见、放款条件和资金安排",
        ]
    if kind == "exposure":
        return [
            "支持围绕资金池、项目和责任角色监控敞口变化与超限风险",
            "支持按阈值状态、监控对象和责任人快速定位高风险敞口",
            f"支持{role_phrase}共享敞口处置建议、预警结果和跟踪记录",
        ]
    if kind == "trade_verification":
        return [
            "支持围绕合同、订单、发票和影像资料开展贸易背景核验",
            "支持按真实性结论、单据完备度和复核状态筛查异常材料",
            f"支持{role_phrase}共享核验结论、补件意见和复核证据",
        ]
    if kind == "dispatch":
        return [
            "支持围绕运单、起讫区域和调度责任人推进派车与节点跟踪",
            "支持按运输状态、线路时效和在途异常快速定位重点任务",
            f"支持{role_phrase}同步调度计划、节点反馈和客户通知结果",
        ]
    if kind == "fleet":
        return [
            "支持围绕车辆、司机和当前任务统一查看运力分布与状态",
            "支持按车辆状态、任务优先级和在途位置调度车队资源",
            f"支持{role_phrase}共享司机反馈、运力安排和回场结果",
        ]
    if kind == "routes":
        return [
            "支持围绕线路节点、拥堵等级和异常事件监控运输路径健康度",
            "支持按线路名称、拥堵等级和异常状态筛查需调线任务",
            f"支持{role_phrase}共享线路调整建议、绕行方案和到达预测",
        ]
    if kind == "warehousing":
        return [
            "支持围绕出库、分拨、到仓和回传节点查看仓配协同进度",
            "支持按仓库、分拨点和异常原因快速定位仓配堵点",
            f"支持{role_phrase}共享波次安排、异常说明和协同留痕",
        ]
    if kind == "signoffs":
        return [
            "支持围绕签收状态、回单影像和复核结论统一整理回单材料",
            "支持按客户、站点和签收异常快速筛查待补件记录",
            f"支持{role_phrase}共享回单复核结果、影像附件和归档状态",
        ]
    if kind == "purchases":
        return [
            "支持按采购单、物料和申请部门追踪请购进度与到货排期",
            "支持围绕供应确认、加急补货和到货节点组织采购协同处理",
            f"支持{role_phrase}共享采购结果、补货原因与供应风险留痕",
        ]
    if kind == "sales":
        return [
            "支持围绕客户订单、交付节点和回款状态开展销售履约跟踪",
            "支持按客户、订单阶段和交付经理快速定位重点订单",
            f"支持{role_phrase}同步交付结果、客户反馈与回款进度",
        ]
    if kind == "inventory":
        return [
            "支持围绕库存批次、库位余量和冻结数量识别库存波动",
            "支持按仓位、物料和预警等级查看库存健康状态",
            f"支持{role_phrase}对低库存、锁定库存和补货建议形成闭环处理",
        ]
    if kind == "suppliers":
        return [
            "支持统一维护供应商资质、合作范围和协同状态",
            "支持按品类、资质状态和续签节点快速筛查供方风险",
            f"支持{role_phrase}共享供方协同记录、资质变更和履约反馈",
        ]
    if kind == "fulfillment":
        return [
            "支持围绕履约阶段、责任人和交付结果跟踪执行闭环",
            "支持查看备货、发运、签收等关键节点的同步状态",
            f"支持{role_phrase}共享履约过程记录、异常说明与结果回写",
        ]
    if kind == "settlements":
        return [
            "支持集中维护结算单、审核意见和付款状态",
            "支持按业务对象、结算阶段和付款进度快速定位账务事项",
            f"支持{role_phrase}共享复核结果、凭证状态与付款留痕",
        ]
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
    kind = _module_kind(title)
    scene_scope = _clean_fragment(scene) or "当前业务场景"
    if kind == "recruitment_demands":
        return (
            f"{title}模块围绕岗位需求确认、优先级排序和发布时间安排组织页面信息，用于支撑{scene_scope}中的需求受理与推进。"
            f"页面重点展示{focus}，便于统一查看需求主题、用人部门和当前招聘阶段。"
        )
    if kind == "recruitment_candidates":
        return (
            f"{title}模块用于统一维护候选人档案、应聘岗位和推进状态，帮助团队在{scene_scope}中持续跟踪重点人选。"
            f"页面重点展示{focus}，便于快速查看候选人来源、应聘岗位和当前进度。"
        )
    if kind == "recruitment_interviews":
        return (
            f"{title}模块围绕候选人面试安排、反馈结论和后续推进组织页面信息，用于支撑{scene_scope}中的流程协同与进度确认。"
            f"页面重点展示{focus}，便于统一查看面试环节、安排状态和责任人。"
        )
    if kind == "recruitment_offers":
        return (
            f"{title}模块用于统一跟踪 Offer 审批、入职材料回收和报到确认，帮助团队在{scene_scope}中完成录用决策后的闭环办理。"
            f"页面重点展示{focus}，便于快速查看候选人状态、录用岗位和当前办理进度。"
        )
    if kind == "recruitment_reports":
        return (
            f"{title}模块面向{scene_scope}相关的复盘分析与结论输出，重点汇总{focus}，用于快速形成统计视图和阶段判断。"
        )
    if kind == "power_dispatch":
        return (
            f"{title}模块围绕负荷平衡、调度指令和执行反馈组织页面信息，用于支撑{scene}中的日内指令下发与执行跟踪。"
            f"页面重点展示{focus}，方便调度长和值班调度员快速确认调度动作与执行结果。"
        )
    if kind == "grid_monitor":
        return (
            f"{title}模块用于统一查看输变线路、关键站点和断面越限状态，帮助团队在{scene}中及时识别运行风险并联动处置。"
            f"页面重点展示{focus}，便于快速完成运行监视、断面研判和风险升级。"
        )
    if kind == "generation":
        return (
            f"{title}模块聚焦机组出力、新能源并网和滚动计划编排，用于协调{scene}中的发电计划调整与执行反馈。"
            f"页面重点展示{focus}，便于统一查看计划目标、修订原因和计划周期。"
        )
    if kind == "work_tickets":
        return (
            f"{title}模块用于维护检修对象、工作票状态和停复电安排，帮助团队在{scene}中快速完成检修许可、协同确认和闭环留痕。"
            f"页面重点展示{focus}，便于统一查看工作类型、许可状态和计划复电时间。"
        )
    if kind == "power_faults":
        return (
            f"{title}模块围绕故障事件、影响范围和恢复进度组织页面信息，用于支撑{scene}中的故障联动、停复电协同和过程复盘。"
            f"页面重点展示{focus}，方便统一查看事件分级、恢复状态和待办事项。"
        )
    if kind == "credit_subjects":
        return (
            f"{title}模块用于维护核心企业、上下游主体与授信状态，重点服务于{scene}中的评级复核、额度配置和主体准入。"
            f"页面重点展示{focus}，便于授信分析师快速确认白名单主体、授信策略和额度使用情况。"
        )
    if kind == "financing":
        return (
            f"{title}模块围绕融资产品、申请企业和审批节点组织页面信息，用于支撑{scene}中的尽调、审批和放款跟踪。"
            f"页面重点展示{focus}，方便统一查看融资进展、复核意见和待办事项。"
        )
    if kind == "exposure":
        return (
            f"{title}模块聚焦资金池、项目敞口和阈值监测，用于在{scene}过程中及时识别额度占用、超限风险和责任归属。"
            f"页面重点展示{focus}，便于风控角色快速完成预警复核和处置追踪。"
        )
    if kind == "trade_verification":
        return (
            f"{title}模块用于核验订单、合同、影像和票据等贸易背景材料，帮助团队在{scene}中快速识别真实性风险和补件事项。"
            f"页面重点展示{focus}，便于完成单据核验、结论记录和复核留痕。"
        )
    if kind == "dispatch":
        return (
            f"{title}模块面向运单编排、派车执行和节点同步场景，用于协调起运、在途跟踪和异常处置。"
            f"页面重点展示{focus}，方便调度主管按时效、区域和责任人查看任务进度。"
        )
    if kind == "fleet":
        return (
            f"{title}模块用于统一维护车辆、司机和运力状态，帮助团队在{scene}中快速判断可调度资源和在途位置。"
            f"页面重点展示{focus}，便于完成车队协同、任务分配和资源复核。"
        )
    if kind == "routes":
        return (
            f"{title}模块用于监控线路节点、拥堵等级和异常事件，帮助团队在{scene}中快速识别延迟风险并调整运输方案。"
            f"页面重点展示{focus}，便于统一查看绕行建议、节点耗时和异常分布。"
        )
    if kind == "warehousing":
        return (
            f"{title}模块聚焦主仓、分拨点和末端站点之间的仓配协同，用于在{scene}过程中跟踪出库、分拨和回传节点。"
            f"页面重点展示{focus}，便于仓配角色快速完成异常复核、节点交接和结果留痕。"
        )
    if kind == "signoffs":
        return (
            f"{title}模块围绕签收状态、回单影像和复核结果组织页面信息，用于支撑{scene}中的签收确认、补件处理和正式归档。"
            f"页面重点展示{focus}，方便统一查看客户签收结果、回单完整度和待办事项。"
        )
    if kind == "purchases":
        return (
            f"{title}模块用于汇总采购申请、物料需求和到货排期，重点支撑{scene}中的请购审批、供应确认与补货跟踪。"
            f"页面核心内容围绕{focus}展开，便于快速判断是否需要加急下单、调整到货日期或联动供应商。"
        )
    if kind == "sales":
        return (
            f"{title}模块围绕客户订单、交付承诺和回款状态组织页面信息，用于支撑{scene}中的订单推进、发运协调与结果回写。"
            f"页面重点展示{focus}，方便统一查看客户需求、履约状态与回款进度。"
        )
    if kind == "inventory":
        return (
            f"{title}模块聚焦库存批次、库位余量和安全阈值管理，用于在{scene}过程中及时识别低库存、冻结库存和补货需求。"
            f"页面重点展示{focus}，便于仓储角色快速完成盘点、预警复核和批次追踪。"
        )
    if kind == "suppliers":
        return (
            f"{title}模块用于统一维护供方资质、合作范围和协同进度，帮助团队在{scene}中快速识别关键供方和续签风险。"
            f"页面重点展示{focus}，便于完成供方筛选、资质核验和协同记录沉淀。"
        )
    if kind == "fulfillment":
        return (
            f"{title}模块面向订单执行、节点推进和结果回写场景，用于协调备货、发运、签收和异常反馈。"
            f"页面重点展示{focus}，方便按阶段查看责任人、执行结果和待处理事项。"
        )
    if kind == "settlements":
        return (
            f"{title}模块用于归集应付金额、审核意见和付款状态，帮助团队在{scene}中形成从账单复核到付款完成的闭环。"
            f"页面重点展示{focus}，便于财务与业务角色同步核验结算结果。"
        )
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
    if kind == "analytics":
        return (
            f"{title}模块面向{scene_scope}相关的复盘分析与结论输出，重点汇总{focus}，用于快速形成统计视图和阶段判断。"
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
        f"{title}模块围绕{keyword}的业务主题构建，主要服务于{scene_scope}相关的日常处理、结果确认和记录留痕。"
        f"页面重点展示{focus}，使用户能够在同一页面内完成查询、录入、审核或跟踪操作。"
    )


def _module_steps(title: str, primary_action: str, focus_terms: list[str]) -> list[str]:
    focus = _module_domain_focus(title, title, focus_terms)
    kind = _module_kind(title)
    if kind == "power_dispatch":
        return [
            "进入负荷调度页面后先查看指令编号、调度单元、负荷水平和执行状态。",
            "通过调度单元、值班调度员或执行状态筛选重点指令，确认是否需要调整负荷或补充执行说明。",
            f"根据业务需要执行“{primary_action}”，同步指令内容、目标出力和执行反馈。",
            "处理完成后复核执行状态、负荷水平和更新时间，确保调度过程闭环可追踪。",
        ]
    if kind == "grid_monitor":
        return [
            "进入电网运行页面后先查看站点名称、运行状态、越限等级和责任班组。",
            "通过线路名称、断面状态或越限等级筛选重点对象，确认是否存在重载、检修切换或风险升级。",
            f"根据业务需要执行“{primary_action}”，补充运行断面、处置建议和监测结果。",
            "处理完成后复核运行状态、越限等级和更新时间，确保监视结果可持续跟踪。",
        ]
    if kind == "generation":
        return [
            "进入发电计划页面后优先查看机组/电源、出力目标、并网状态和计划周期。",
            "通过机组名称、计划周期或并网状态筛选重点计划，确认是否需要调整出力或修订滚动计划。",
            f"执行“{primary_action}”或详情处理动作，更新功率目标、修订原因和协同结果。",
            "处理后复核出力目标、并网状态和更新时间，确保计划变更结果一致可见。",
        ]
    if kind == "work_tickets":
        return [
            "进入检修工作票页面后先查看票号、检修对象、许可状态和计划复电时间。",
            "通过票号、工作类型或许可状态筛选重点票据，确认是否存在待许可或待复电事项。",
            f"根据业务需要执行“{primary_action}”，补充安全措施、停复电安排和协同说明。",
            "处理完成后复核许可状态、计划复电时间和更新时间，确保检修链路完整可审计。",
        ]
    if kind == "power_faults":
        return [
            "进入故障联动页面后先查看事件编号、影响范围、处置阶段和恢复状态。",
            "通过影响范围、事件等级或恢复状态筛选重点事件，确认是否需要联动检修、复电或升级处置。",
            f"根据业务需要执行“{primary_action}”，补充事件研判、联动记录和恢复进度。",
            "处理完成后复核恢复状态、处置阶段和更新时间，确保事件处置闭环清晰可追踪。",
        ]
    if kind == "credit_subjects":
        return [
            "进入授信主体页面后先查看主体编号、授信额度、评级状态和预警级别。",
            "通过主体名称、评级状态或额度区间筛选重点企业，确认是否存在待复核主体。",
            f"执行“{primary_action}”或详情维护操作，补充额度信息、评级依据和授信策略。",
            "处理完成后复核授信额度、评级状态和更新时间，确保主体信息可追踪、可复核、可导出。",
        ]
    if kind == "financing":
        return [
            "进入融资申请分析页面后先查看申请编号、融资产品、审批阶段和放款状态。",
            "通过申请企业、融资产品或审批阶段筛选重点申请，确认是否存在待尽调或待放款事项。",
            f"根据业务需要执行“{primary_action}”，补充尽调意见、审批结果和资金安排。",
            "处理完成后复核审批阶段、放款状态和更新时间，确保融资进展与复核意见保持一致。",
        ]
    if kind == "exposure":
        return [
            "进入资金敞口监控页面后优先查看资金池、当前敞口、阈值状态和责任人。",
            "通过项目、阈值等级或责任人筛选重点敞口，确认是否存在超限或临界状态。",
            f"执行“{primary_action}”或详情处理动作，更新处置建议、跟踪状态和责任分工。",
            "处理后复核敞口数值、阈值状态和更新时间，确保风险变化能够被持续跟踪。",
        ]
    if kind == "trade_verification":
        return [
            "进入贸易背景核验页面后先查看订单/合同编号、单据完备度和复核结论。",
            "通过合同编号、核验结论或补件状态筛选重点材料，确认是否存在真实性风险。",
            f"执行“{primary_action}”或详情核验操作，补充核验说明、补件要求和复核依据。",
            "处理完成后复核背景真实性、复核结论和更新时间，确保材料链路完整可审计。",
        ]
    if kind == "dispatch":
        return [
            "进入运单调度中心后先查看运单编号、起讫区域、运输状态和承运时效。",
            "通过运单编号、区域或责任人筛选重点任务，确认是否需要派车、改派或催办。",
            f"根据业务需要执行“{primary_action}”，同步调度计划、节点进展和异常说明。",
            "处理完成后复核运输状态、承运时效和更新时间，确保调度任务闭环可追踪。",
        ]
    if kind == "fleet":
        return [
            "进入车辆与司机协同页面后先查看车辆编号、司机姓名、当前任务和在途位置。",
            "通过车辆状态、司机姓名或任务类型筛选重点运力，确认可调度车辆和异常资源。",
            f"执行“{primary_action}”或详情维护动作，补充车辆信息、司机安排和任务归属。",
            "处理完成后复核运力状态、在途位置和更新时间，确保车队协同结果一致可见。",
        ]
    if kind == "routes":
        return [
            "进入线路监控台后先查看线路名称、途经节点、拥堵等级和异常状态。",
            "通过线路编号、拥堵等级或异常状态筛选重点线路，确认是否需要绕行或调线。",
            f"根据业务需要执行“{primary_action}”，补充线路策略、异常说明和到达预测。",
            "处理完成后复核线路状态、异常等级和更新时间，确保路径调整可追踪。",
        ]
    if kind == "warehousing":
        return [
            "进入仓配协同台后先查看仓库/分拨点、节点状态、异常原因和责任角色。",
            "通过仓库、节点状态或异常原因筛选重点协同单，确认是否存在出库、分拨或回传堵点。",
            f"执行“{primary_action}”或详情处理动作，更新节点进展、协同说明和责任归属。",
            "处理后复核节点状态、异常说明和更新时间，确保仓配协同链路完整可追溯。",
        ]
    if kind == "signoffs":
        return [
            "进入签收回单中心后先查看回单编号、签收状态、回单完整度和复核结果。",
            "通过客户名称、签收状态或回单完整度筛选重点记录，确认是否存在补传或异常签收。",
            f"根据业务需要执行“{primary_action}”，补充回单影像、签收说明和复核结论。",
            "处理完成后复核签收状态、回单完整度和更新时间，确保正式归档材料准确可用。",
        ]
    if kind == "purchases":
        return [
            "进入采购管理页面后先查看采购单号、物料名称、申请部门和到货日期等关键信息。",
            "通过物料名称、申请部门或供应状态筛选待处理采购单，确认是否存在加急补货或排期冲突。",
            f"执行“{primary_action}”或详情复核操作，补充采购原因、到货计划和供应确认结果。",
            "处理完成后复核到货日期、供应状态和更新时间，确保采购进度可追溯、可同步、可导出。",
        ]
    if kind == "sales":
        return [
            "进入销售管理页面后先查看客户名称、履约状态、回款状态和最近更新时间。",
            "通过客户名称或订单阶段筛选重点订单，确认交付承诺与回款计划是否一致。",
            f"根据业务需要执行“{primary_action}”，补充订单信息、更新履约状态并回写客户反馈。",
            "处理完成后复核订单状态、回款结果和更新时间，确保销售与交付信息保持一致。",
        ]
    if kind == "inventory":
        return [
            "进入库存管理页面后优先查看批次编号、库位、可用库存和预警状态。",
            "通过物料名称、仓位或预警等级筛选重点批次，确认是否需要盘点或触发补货。",
            f"执行“{primary_action}”或详情处理动作，更新盘点结果、冻结状态和安全库存阈值。",
            "处理后复核库存数量、预警状态和更新时间，确保批次信息准确并可用于后续履约。",
        ]
    if kind == "suppliers":
        return [
            "进入供应商管理页面后先查看供应商名称、品类范围、协同状态和资质状态。",
            "通过品类、资质状态或续签节点筛选关键供方，确认当前需要补齐的资料或风险项。",
            f"执行“{primary_action}”或详情维护操作，补充资质文件、合作范围和协同记录。",
            "处理后复核资质状态、协同节点和更新时间，确保供方档案后续可检索、可复盘、可验收。",
        ]
    if kind == "fulfillment":
        return [
            "进入订单履约中心后先查看履约单号、当前阶段、责任人和结果摘要。",
            "通过责任人、当前阶段或履约单号筛选重点任务，确认备货、发运或签收节点状态。",
            f"根据业务需要执行“{primary_action}”，同步执行进度、异常说明和交付反馈。",
            "处理完成后复核当前阶段、结果摘要与更新时间，确保履约闭环记录完整可追踪。",
        ]
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
    kind = _module_kind(title)
    scene_scope = _clean_fragment(scene) or "当前业务场景"
    if kind == "power_dispatch":
        return "负荷调度中心将调度指令、执行状态和负荷变化统一呈现，有助于值班调度岗位快速协调电网运行与出力平衡。"
    if kind == "grid_monitor":
        return "输变线路监测将关键站点、断面越限和运行状态集中展示，便于团队及时发现运行风险并联动处置。"
    if kind == "generation":
        return "发电计划协同把机组出力、新能源并网和计划修订放到同一工作台中，有助于提升计划调整效率和协同一致性。"
    if kind == "work_tickets":
        return "检修工作票中心将停复电安排、检修许可和工作票流转集中维护，有助于降低跨班组协同中的信息遗漏风险。"
    if kind == "power_faults":
        return "告警与故障联动把故障研判、影响范围和恢复进度串成统一链路，便于团队快速完成停复电协同与复盘留痕。"
    if kind == "credit_subjects":
        return "授信主体管理把核心企业、授信额度和评级结果集中维护，便于风控与授信角色统一判断主体准入和额度策略。"
    if kind == "financing":
        return "融资申请分析将尽调、审批与放款状态串成统一链路，能够降低授信、资金和业务团队之间的信息割裂。"
    if kind == "exposure":
        return "资金敞口监控通过统一展示敞口数值、阈值状态和责任归属，帮助团队更快识别高风险项目和超限事项。"
    if kind == "trade_verification":
        return "贸易背景核验将合同、订单、票据和影像的复核动作汇聚到同一页面，有助于提高材料真实性核验效率并强化审计留痕。"
    if kind == "dispatch":
        return "运单调度中心把派车、在途跟踪和异常反馈整合到统一驾驶舱，便于调度岗位快速协调区域任务和时效承诺。"
    if kind == "fleet":
        return "车辆与司机协同通过统一展示运力状态、司机安排和当前位置，帮助团队更高效地完成运力分配与回场统筹。"
    if kind == "routes":
        return "线路监控台将路径节点、拥堵状态和异常事件集中呈现，有助于及时调整绕行策略并降低运输延误风险。"
    if kind == "warehousing":
        return "仓配协同台把主仓、分拨和末端节点串成完整协同链路，便于责任角色快速定位堵点并同步处理结果。"
    if kind == "signoffs":
        return "签收回单中心将签收结果、回单影像和复核结论集中整理，有助于正式归档、客户对账和后续异常追踪。"
    if kind == "purchases":
        return "采购管理将请购单、到货排期与供应确认整合在同一工作台，便于采购与仓储角色同步判断补货优先级和到货风险。"
    if kind == "sales":
        return "销售管理把客户订单、履约状态和回款反馈纳入同一页面，能够降低销售、交付与财务之间的信息割裂。"
    if kind == "inventory":
        return "库存管理通过统一展示批次余量、库位分布和预警状态，帮助团队更快识别补货需求和冻结风险。"
    if kind == "suppliers":
        return "供应商管理将供方资质、合作范围和续签节点集中维护，有助于降低供方协同中的资料遗漏和履约风险。"
    if kind == "fulfillment":
        return "订单履约中心把备货、发运、签收和异常说明串成完整执行链路，便于责任人快速定位堵点并同步结果。"
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
        f"{title}页面将与“{keyword}”相关的核心业务处理集中到统一界面中，适用于{scene_scope}相关的受理、跟踪、复核和结果沉淀。"
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
    industry_label = _clean_fragment(industry_scope) or "当前行业"
    scene_scope = _clean_fragment(scene) or "当前业务场景"
    return _ensure_min_length(
        (
            f"{product_name}围绕“{topic}”这一任务主题建设，面向{industry_label}相关场景，重点解决线下信息分散、关键处理环节缺少统一入口、"
            f"结果反馈不够及时以及材料整理依赖人工汇总等问题。系统以{scene_scope}为业务主线，把{module_titles}等核心模块纳入同一套操作界面，"
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
    scene_scope = _clean_fragment(scene) or "当前业务场景"
    return _ensure_min_length(
        (
            f"{product_name}的开发目的在于针对“{topic}”对应的业务需求搭建一套可持续复用的业务支撑平台，让{role_phrase}能够围绕{scene_scope}开展统一登录、"
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
    scene_scope = _clean_fragment(scene) or "当前业务场景"
    return _ensure_min_length(
        (
            f"{product_name}采用前后端分层、模块化页面与任务画像驱动的生成方式，围绕“{topic}”对应的{scene_scope}需求组织软件结构。"
            f"系统会结合当前任务画像重新组织导航、信息分区、数据承载方式与结果出口，使{module_titles}等模块保持业务连贯的同时避免回落到固定后台套板。"
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
    industry_label = _clean_fragment(industry_scope) or "当前行业"
    scene_scope = _clean_fragment(scene) or "当前业务场景"
    return _ensure_min_length(
        (
            f"{product_name}面向{industry_label}相关场景设计，围绕“{keyword or product_name}”这一业务主题构建产品定位。"
            f"系统通过{module_titles}等模块组织页面内容，突出{scene_scope}相关的关键业务对象、处理动作与结果输出要求。"
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
    scene_scope = _clean_fragment(scene) or "当前业务场景"
    return _ensure_min_length(
        (
            f"{product_name}在设计上重点突出{scene_scope}相关的角色协同、页面字段组织和业务状态反馈。"
            f"系统会围绕{focus}等主题信息安排页面结构，使{role_phrase}能够快速理解当前产品的处理重点、数据重点和交付重点。"
        ),
        90,
        "因此，不同产品生成的说明书会在模块名称、正文论述、页面要点和技术特点上呈现出明显差异。",
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


def _build_distinguishing_features(
    product_name: str,
    keyword: str,
    industry_scope: str,
    modules: list[dict],
    focus_terms: list[str],
) -> list[str]:
    module_titles = [module["title"] for module in modules[:4]]
    focus = "、".join(focus_terms[:3]) or keyword or product_name
    industry_label = _clean_fragment(industry_scope) or "当前行业"
    return [
        f"围绕“{keyword or product_name}”组织产品内容，说明书正文突出{industry_label}相关的任务目标、核心数据和流程特征。",
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
    preset_modules = _preset_modules_for_product(preset, product_code)
    module_titles = list(prd_summary.get("core_modules") or [])
    if not module_titles:
        module_titles = [module["title"] for module in preset_modules]
    page_routes = list(prd_summary.get("required_pages") or [])
    roles = list(prd_summary.get("user_roles") or []) or list(preset.user_roles)
    core_entities = [
        str(item).strip()
        for item in (prd_summary.get("core_entities") or [])
        if str(item).strip()
    ] or list(preset.core_entities)
    focus_terms = _split_terms(keyword, product_name, industry or "", *module_titles)[:6]
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
        "product_positioning": _build_product_positioning(product_name, keyword, industry_scope, scene, profile_modules),
        "design_focus": _build_design_focus(product_name, keyword, scene, roles, focus_terms),
        "distinguishing_features": _build_distinguishing_features(product_name, keyword, industry_scope, profile_modules, focus_terms),
        "typical_scenarios": _build_typical_scenarios(product_name, keyword, scene, profile_modules),
        "user_roles": roles,
        "dashboard_metrics": _build_dashboard_metrics(profile_modules, roles, focus_terms, preset, experience_blueprint),
        "modules": profile_modules,
        "screenshot_scenarios": screenshot_scenarios,
        "experience_blueprint": experience_blueprint,
        "visual_profile": visual_profile,
        "project_dna": project_dna,
        "differentiation_hint": (
            "当前任务必须以 raw_user_request 中的原始用户输入为唯一主题源，"
            f"页面、截图与说明书围绕{'、'.join(focus_terms[:3]) or product_name}展开；"
            "平台画像仅用于补充结构与运行约束，不得改写行业、模块主线或产品定位，也不得把所有任务压成同一套顶栏+表格后台骨架。"
        ),
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
    product_code = _product_code(keyword, product_name)
    preset_modules = _preset_modules_for_product(preset, product_code)
    module_titles = [module["title"] for module in preset_modules[:5]]
    scene = _compose_scene(keyword or product_name, product_name, industry, module_titles, preset)
    focus_terms = _split_terms(keyword, product_name, industry or "", *module_titles)[:5]
    design_seed = _build_design_seed(keyword, product_name, industry, notes, raw_user_request)
    blueprint = _pick_experience_blueprint(product_code, preset.key, design_seed)
    visual_profile = _build_visual_profile(product_code, preset.key, app_type, blueprint, design_seed)
    seed_dna = _build_project_dna(
        keyword=keyword,
        product_name=product_name,
        preset=preset,
        scene=scene,
        focus_terms=focus_terms,
        modules=preset_modules[:6],
        experience_blueprint=blueprint,
        visual_profile=visual_profile,
        app_type=app_type,
        core_entities=list(preset.core_entities[:5]),
        raw_user_request=raw_user_request,
    )
    return {
        "raw_user_request": raw_user_request,
        "source_of_truth": "raw_user_request",
        "app_type": app_type,
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
        "visual_profile": visual_profile,
        "design_seed": design_seed,
        "project_dna": seed_dna,
        "differentiation_hint": (
            "必须优先遵循 raw_user_request 中的原始用户输入；"
            f"平台仅建议围绕{'、'.join(focus_terms[:3]) or product_name}组织模块与页面，"
            "不得私自改写行业、主题或产品定位。"
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
        "  design_seed?: string;\n"
        "  visual_profile?: Record<string, string>;\n"
        "  project_dna?: Record<string, unknown>;\n"
        "  differentiation_hint?: string;\n"
        "};\n\n"
        f"export const APP_PROFILE: AppProfile = {payload} as AppProfile;\n"
    )


def build_backend_profile_source(profile: dict) -> str:
    return (
        "from __future__ import annotations\n\n"
        f"APP_PROFILE = {pprint.pformat(profile, width=100, sort_dicts=False)}\n"
    )
