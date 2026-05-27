from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path

from app.services.project_profile import build_frontend_profile_source

from workers.stages.generated_backend import write_generated_backend_files


def _write_text(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


_CORE_FRONTEND_DEPENDENCIES = {
    "@fontsource/noto-sans-sc": "latest",
    "@ant-design/icons": "^5.3.0",
    "antd": "^5.15.0",
    "axios": "^1.6.0",
    "dayjs": "^1.11.0",
}

_OPTIONAL_FRONTEND_DEPENDENCIES = {
    "@ant-design/pro-components": "^2.8.6",
    "echarts": "^5.5.0",
    "echarts-for-react": "^3.0.2",
}


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
    needs_pro_components = "@ant-design/pro-components" in imported_modules
    needs_echarts_for_react = "echarts-for-react" in imported_modules
    needs_echarts = needs_echarts_for_react or "echarts" in imported_modules

    if needs_pro_components:
        dependencies.setdefault("@ant-design/pro-components", _OPTIONAL_FRONTEND_DEPENDENCIES["@ant-design/pro-components"])
    else:
        dependencies.pop("@ant-design/pro-components", None)

    if needs_echarts:
        dependencies.setdefault("echarts", _OPTIONAL_FRONTEND_DEPENDENCIES["echarts"])
    else:
        dependencies.pop("echarts", None)

    if needs_echarts_for_react:
        dependencies.setdefault("echarts-for-react", _OPTIONAL_FRONTEND_DEPENDENCIES["echarts-for-react"])
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


def _module_code(module: dict) -> str:
    route = str(module.get("route", "")).strip("/") or str(module.get("key", "module"))
    parts = [part for part in re.split(r"[^0-9A-Za-z]+", route) if part]
    if not parts:
        return "MOD"
    if len(parts) == 1:
        token = parts[0][:4]
    else:
        token = "".join(part[:3] for part in parts[:2])
    return token.upper()


def _module_theme(module: dict) -> dict:
    route = str(module.get("route", ""))
    mapping = {
        "/purchases": {"accent": "#1d4ed8", "soft": "#eff6ff", "strong": "#1e40af"},
        "/sales": {"accent": "#0f766e", "soft": "#f0fdfa", "strong": "#115e59"},
        "/inventory": {"accent": "#7c3aed", "soft": "#f5f3ff", "strong": "#6d28d9"},
        "/suppliers": {"accent": "#b45309", "soft": "#fffbeb", "strong": "#92400e"},
        "/orders": {"accent": "#dc2626", "soft": "#fef2f2", "strong": "#b91c1c"},
        "/talents": {"accent": "#2563eb", "soft": "#eff6ff", "strong": "#1d4ed8"},
        "/clients": {"accent": "#7c3aed", "soft": "#f5f3ff", "strong": "#6d28d9"},
        "/campaigns": {"accent": "#ea580c", "soft": "#fff7ed", "strong": "#c2410c"},
        "/assets": {"accent": "#0891b2", "soft": "#ecfeff", "strong": "#0e7490"},
        "/analytics": {"accent": "#16a34a", "soft": "#f0fdf4", "strong": "#15803d"},
        "/settlements": {"accent": "#ca8a04", "soft": "#fefce8", "strong": "#a16207"},
        "/risks": {"accent": "#dc2626", "soft": "#fef2f2", "strong": "#b91c1c"},
        "/settings": {"accent": "#475569", "soft": "#f8fafc", "strong": "#334155"},
        "/records": {"accent": "#0284c7", "soft": "#f0f9ff", "strong": "#0369a1"},
        "/workflow": {"accent": "#9333ea", "soft": "#faf5ff", "strong": "#7e22ce"},
        "/reports": {"accent": "#0f766e", "soft": "#f0fdfa", "strong": "#115e59"},
        "/alerts": {"accent": "#e11d48", "soft": "#fff1f2", "strong": "#be123c"},
        "/audit": {"accent": "#4f46e5", "soft": "#eef2ff", "strong": "#4338ca"},
    }
    return mapping.get(route, {"accent": "#1677ff", "soft": "#eff6ff", "strong": "#1d4ed8"})

def _route_copy(route: str, module_code: str | None = None) -> dict:
    route = (route or "").strip()
    route_key = route or "/module"
    code = module_code or _module_code({"route": route_key})
    fallback_title = "综合业务模块"
    fallback = {
        "title": fallback_title,
        "summary": f"{fallback_title}模块用于处理业务查询、状态更新、结果导出和留痕管理。",
        "action": f"进入{fallback_title}",
        "placeholder": f"搜索{fallback_title} / 负责人 / 状态",
        "headers": ["编号", "名称", "周期", "负责人", "状态", "操作"],
        "rows": [
            [f"{code}-101", f"{fallback_title}任务一", "2026W18", "陈思远", "就绪", "查看"],
            [f"{code}-102", f"{fallback_title}任务二", "2026-05", "周可欣", "进行中", "跟进"],
            [f"{code}-103", f"{fallback_title}任务三", "2026-05", "林柏宇", "已完成", "导出"],
        ],
        "highlights": [
            f"{code}模块状态可视化",
            f"{code}结果同步查看",
            f"{code}支持直接导出",
        ],
        "tips": [
            f"先通过搜索框快速定位目标{fallback_title}记录。",
            f"再通过主按钮发起{fallback_title}相关新增、维护或审核动作。",
            "导出前请确认负责人、状态和更新时间等信息准确无误。",
            "保持页面中的时间线和状态标识完整可见，便于留痕和复核。",
        ],
    }
    mapping = {
        "/dashboard": {
            "title": "系统首页",
            "summary": "用于统一查看业务概览、模块状态、风险提示和最新执行信号。",
        },
        "/records": {
            "title": "客户与对象管理",
            "summary": "用于维护核心业务对象、负责人、状态流转和最新更新记录。",
            "action": "新增档案",
            "placeholder": "搜索名称 / 负责人 / 编号",
            "headers": ["编号", "名称", "负责人", "状态", "更新时间", "备注"],
            "rows": [
                ["REC-101", "北辰项目", "陈思远", "启用", "2026-05-02", "重点跟进"],
                ["REC-102", "远望对象", "周可欣", "处理中", "2026-05-01", "待补资料"],
                ["REC-103", "星河归档", "林柏宇", "归档", "2026-04-30", "历史记录"],
            ],
            "highlights": ["支持统一建档", "支持负责人筛选", "支持留痕备注回查"],
        },
        "/workflow": {
            "title": "流程计划管理",
            "summary": "用于跟踪阶段进度、截止时间、责任人和下一步处理动作。",
            "action": "新建流程计划",
            "placeholder": "搜索流程名称 / 阶段 / 责任人",
            "headers": ["计划编号", "计划名称", "责任人", "当前阶段", "截止时间", "状态"],
            "rows": [
                ["WF-201", "资料整理一期", "孙悦", "校验中", "2026-05-10", "进行中"],
                ["WF-202", "功能审核二期", "周澄", "待分配", "2026-05-08", "待启动"],
                ["WF-203", "月度归档汇总", "张岚", "已完成", "2026-05-01", "已完成"],
            ],
            "highlights": ["支持阶段推进记录", "支持责任人分派", "支持截止时间同步"],
        },
        "/assets": {
            "title": "资料中心",
            "summary": "用于统一管理说明文档、业务附件和参考资料，并跟踪审核状态。",
            "action": "上传资料",
            "placeholder": "搜索资料名称 / 分类 / 状态",
            "headers": ["资料编号", "资料名称", "分类", "提交人", "审核状态", "更新时间"],
            "rows": [
                ["DOC-201", "项目说明书初稿", "说明文档", "陈思远", "已通过", "2026-05-02"],
                ["DOC-202", "统计附件", "附件资料", "孙悦", "待审核", "2026-05-01"],
                ["DOC-203", "基础信息清单", "主数据", "周可欣", "已打回", "2026-04-29"],
            ],
            "highlights": ["支持分类管理", "支持审核状态回写", "支持按更新时间排序"],
        },
        "/analytics": {
            "title": "业务分析",
            "summary": "用于查看趋势快照、周期统计结果、分析结论和完成情况。",
            "action": "生成分析结果",
            "placeholder": "搜索统计维度 / 周期 / 负责人",
            "headers": ["分析编号", "主题", "统计周期", "负责人", "核心结论", "状态"],
            "rows": [
                ["ANA-301", "周度业务分析", "2026W18", "林柏宇", "趋势稳定", "已发布"],
                ["ANA-302", "月度项目复盘", "2026-04", "周澄", "需优化流程", "待确认"],
                ["ANA-303", "专项执行分析", "2026-05", "张岚", "完成率较高", "已发布"],
            ],
            "highlights": ["支持周期统计", "支持结论沉淀", "支持按主题查看分析结果"],
        },
        "/reports": {
            "title": "报表中心",
            "summary": "用于集中展示各类业务报表、周期汇总结果和导出材料。",
            "action": "生成报表",
            "placeholder": "搜索报表名称 / 周期 / 状态",
            "headers": ["报表编号", "报表名称", "周期", "制表人", "更新时间", "状态"],
            "rows": [
                ["RPT-401", "月度执行报表", "2026-04", "系统", "2026-05-02", "已完成"],
                ["RPT-402", "周度进度报表", "2026W18", "孙悦", "2026-05-01", "已完成"],
                ["RPT-403", "专项核查报表", "2026-05", "周可欣", "2026-04-30", "处理中"],
            ],
            "highlights": ["支持报表导出", "支持状态查看", "支持周期筛选"],
        },
        "/alerts": {
            "title": "风险与提醒",
            "summary": "用于集中展示超期事项、资料缺失、异常风险和待办提醒。",
            "action": "新增提醒规则",
            "placeholder": "搜索提醒类型 / 状态 / 责任人",
            "headers": ["提醒编号", "提醒主题", "严重程度", "责任人", "发现时间", "处理状态"],
            "rows": [
                ["ALT-501", "流程节点超期", "高", "陈思远", "2026-05-02", "处理中"],
                ["ALT-502", "资料缺失", "中", "周可欣", "2026-05-01", "待处理"],
                ["ALT-503", "审批未完成", "高", "张岚", "2026-04-30", "已关闭"],
            ],
            "highlights": ["支持阈值提醒", "支持责任人查看", "支持关闭与复盘"],
        },
        "/audit": {
            "title": "审计留痕",
            "summary": "用于查看关键操作行为、发生时间、模块轨迹和执行结果。",
            "action": "导出审计记录",
            "placeholder": "搜索操作人 / 模块 / 时间",
            "headers": ["审计编号", "操作模块", "操作人", "操作摘要", "发生时间", "结果"],
            "rows": [
                ["ADT-601", "流程计划管理", "陈思远", "更新计划状态", "2026-05-02 10:32", "成功"],
                ["ADT-602", "资料中心", "周可欣", "提交资料审核", "2026-05-01 16:18", "成功"],
                ["ADT-603", "系统设置", "管理员", "调整通知规则", "2026-04-30 09:20", "成功"],
            ],
            "highlights": ["支持操作追踪", "支持时间过滤", "支持导出审计记录"],
        },
        "/settings": {
            "title": "系统设置",
            "summary": "用于维护平台名称、路由规则、归档策略和基础参数配置。",
            "action": "保存设置",
            "placeholder": "搜索配置项 / 关键字",
            "headers": ["配置项", "当前值", "说明", "维护人", "更新时间", "状态"],
            "rows": [
                ["CFG-101", "系统名称", "综合运营管理平台", "管理员", "2026-05-01", "启用"],
                ["CFG-102", "通知策略", "站内+邮件", "业务主管", "2026-05-01", "启用"],
                ["CFG-103", "归档周期", "30天", "管理员", "2026-04-30", "启用"],
            ],
            "highlights": ["支持基础参数维护", "支持通知规则配置", "支持归档和权限模板调整"],
        },
        "/talents": {
            "title": "达人库管理",
            "summary": "用于管理达人档案、投放平台、标签能力、报价和合作状态。",
            "action": "新增达人档案",
            "placeholder": "搜索达人昵称 / 平台 / 标签",
            "headers": ["达人编号", "达人昵称", "平台", "粉丝量级", "合作状态", "最近更新"],
            "rows": [
                ["TAL-001", "晓鹿种草社", "小红书", "50万+", "合作中", "2026-05-02"],
                ["TAL-002", "阿木评测", "抖音", "120万+", "待签约", "2026-05-01"],
                ["TAL-003", "Melody生活志", "小红书", "18万+", "已归档", "2026-04-30"],
            ],
            "highlights": ["支持达人标签化归类", "支持合作状态筛选", "支持历史报价回查"],
        },
        "/clients": {
            "title": "品牌客户管理",
            "summary": "用于跟踪客户需求、行业分类、预算区间、负责人和合作进展。",
            "action": "新增客户需求",
            "placeholder": "搜索品牌名称 / 行业 / 负责人",
            "headers": ["客户编号", "品牌名称", "所属行业", "负责人", "合作阶段", "更新时间"],
            "rows": [
                ["CLI-101", "星曜美妆", "美妆个护", "周铭", "方案沟通", "2026-05-02"],
                ["CLI-102", "晨屿食品", "消费食品", "孙恬", "执行中", "2026-05-01"],
                ["CLI-103", "远峰家居", "家居生活", "刘楠", "复盘中", "2026-04-29"],
            ],
            "highlights": ["支持客户需求池管理", "支持阶段推进记录", "支持行业预算统计"],
        },
        "/campaigns": {
            "title": "投放计划管理",
            "summary": "用于统筹投放节奏、预算安排、责任人分工和上线窗口。",
            "action": "新建投放计划",
            "placeholder": "搜索计划名称 / 负责人 / 阶段",
            "headers": ["计划编号", "计划名称", "负责人", "投放周期", "预算", "执行状态"],
            "rows": [
                ["CAM-210", "夏季新品种草", "林嘉", "05-01 ~ 05-20", "80,000", "执行中"],
                ["CAM-211", "母亲节礼盒预热", "唐悦", "04-28 ~ 05-08", "35,000", "待上线"],
                ["CAM-212", "618蓄水首轮", "韩舟", "05-10 ~ 05-31", "200,000", "待审核"],
            ],
            "highlights": ["支持计划分期管理", "支持预算排期查看", "支持节点提醒看板"],
        },
        "/settlements": {
            "title": "结算与对账",
            "summary": "用于处理费用清单、付款进度、审批状态和对账结果。",
            "action": "新增结算单",
            "placeholder": "搜索结算编号 / 达人 / 状态",
            "headers": ["结算编号", "合作对象", "费用类型", "金额", "审核状态", "付款进度"],
            "rows": [
                ["SET-501", "晓鹿种草社", "达人服务费", "18,000", "待复核", "未付款"],
                ["SET-502", "阿木评测", "内容制作费", "26,000", "已通过", "付款中"],
                ["SET-503", "Melody生活志", "佣金结算", "8,500", "已完成", "已付款"],
            ],
            "highlights": ["支持账单审核流程", "支持付款状态追踪", "支持费用分类统计"],
        },
    }
    result = dict(fallback)
    result.update(mapping.get(route_key, {}))
    return result


def _render_login_page(profile: dict | None = None) -> str:
    blueprint = (profile or {}).get("experience_blueprint") or {}
    login_variant = json.dumps(str(blueprint.get("login_variant") or "spotlight"), ensure_ascii=False)
    return """import { APP_PROFILE } from '../generated/appProfile';

const uiFont = `'Noto Sans SC', 'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei', 'IPRight CJK', sans-serif`;
const loginVariant = __LOGIN_VARIANT__;

export default function Login({ onLogin }: { onLogin: () => void }) {
  const previewModules = APP_PROFILE.modules.slice(0, 4);
  return (
    <div style={{ minHeight: '100vh', background: '#f3f6fb', fontFamily: uiFont, padding: '40px 32px' }}>
      <div style={{ maxWidth: 1280, margin: '0 auto', display: 'grid', gridTemplateColumns: loginVariant === 'workspace' ? '1.12fr 380px' : '420px 1fr', gap: 24, alignItems: 'stretch' }}>
      <div style={{ padding: 40, background: '#fff', borderRadius: 16, boxShadow: '0 12px 32px rgba(15, 23, 42, 0.08)' }}>
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 28, fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>{APP_PROFILE.product_name}</div>
          <div style={{ color: '#475569', lineHeight: 1.7 }}>
            {loginVariant === 'briefing'
              ? `${APP_PROFILE.scene}软件演示入口，当前登录前先展示角色摘要、主题对象与任务边界。`
              : loginVariant === 'workspace'
                ? `${APP_PROFILE.scene}软件演示入口，强调岗位协同、模块分工与进入系统后的工作台流转。`
                : `${APP_PROFILE.scene}软件演示入口，支持统一登录、首页概览、模块管理、统计分析和交付资料下载等功能。`}
          </div>
          <div style={{ marginTop: 10, fontSize: 13, letterSpacing: 1.1, color: '#1677ff', fontWeight: 700 }}>
            {APP_PROFILE.short_name} / {APP_PROFILE.version}
          </div>
        </div>
        <div style={{ display: 'grid', gap: 16 }}>
          <div>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>用户名</label>
            <input
              name="username"
              placeholder="请输入用户名"
              defaultValue="admin"
              style={{ width: '100%', padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: 10, boxSizing: 'border-box', fontFamily: uiFont }}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 6, fontWeight: 600 }}>密码</label>
            <input
              name="password"
              type="password"
              placeholder="请输入密码"
              defaultValue="admin123"
              style={{ width: '100%', padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: 10, boxSizing: 'border-box', fontFamily: uiFont }}
            />
          </div>
          <button
            type="button"
            onClick={onLogin}
            style={{ width: '100%', padding: '12px', background: '#1677ff', color: '#fff', border: 'none', borderRadius: 10, cursor: 'pointer', fontSize: 16, fontWeight: 600, fontFamily: uiFont }}
          >
            登录系统
          </button>
        </div>
        <div style={{ marginTop: 20, color: '#64748b', lineHeight: 1.8, fontSize: 13 }}>
          <div>演示账号：admin / admin123</div>
          <div>软件版本：{APP_PROFILE.version}</div>
          <div>覆盖角色：{APP_PROFILE.user_roles.join('、')}</div>
        </div>
      </div>
      <div style={{ display: 'grid', gap: 20 }}>
        {loginVariant === 'briefing' ? (
          <section style={{ background: '#0f172a', color: '#fff', borderRadius: 18, padding: 28, minHeight: 220 }}>
            <div style={{ fontSize: 13, letterSpacing: 1.2, opacity: 0.78 }}>任务简报</div>
            <h2 style={{ margin: '12px 0 10px', fontSize: 30 }}>{APP_PROFILE.short_name} 进入前摘要</h2>
            <div style={{ lineHeight: 1.9, opacity: 0.9 }}>
              当前产品围绕 {APP_PROFILE.industry_scope} 组织角色分工、业务对象和关键处理链路，
              登录后优先进入专题洞察与岗位工作台。
            </div>
            <div style={{ marginTop: 18, display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
              <div style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(255,255,255,0.10)' }}>
                <div style={{ fontSize: 12, opacity: 0.72 }}>当前版本</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{APP_PROFILE.version}</div>
              </div>
              <div style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(255,255,255,0.10)' }}>
                <div style={{ fontSize: 12, opacity: 0.72 }}>角色覆盖</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{APP_PROFILE.user_roles.length} 类</div>
              </div>
              <div style={{ padding: '12px 14px', borderRadius: 14, background: 'rgba(255,255,255,0.10)' }}>
                <div style={{ fontSize: 12, opacity: 0.72 }}>核心模块</div>
                <div style={{ marginTop: 6, fontWeight: 700 }}>{APP_PROFILE.modules.length} 个</div>
              </div>
            </div>
          </section>
        ) : loginVariant === 'workspace' ? (
          <section style={{ background: '#ffffff', borderRadius: 18, padding: 24, boxShadow: '0 8px 24px rgba(15, 23, 42, 0.05)' }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: '#0f172a', marginBottom: 10 }}>岗位工作台预览</div>
            <div style={{ color: '#475569', lineHeight: 1.8, marginBottom: 16 }}>
              登录后可按岗位进入对应工作区，围绕主题对象、处理中事项与归档结果展开协同处理。
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12 }}>
              {APP_PROFILE.user_roles.slice(0, 3).map((role, index) => (
                <div key={role || index} style={{ border: '1px solid #dbeafe', borderRadius: 14, padding: 16, background: '#f8fbff' }}>
                  <div style={{ fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>{role}</div>
                  <div style={{ color: '#475569', lineHeight: 1.7, fontSize: 14 }}>
                    负责查看 {APP_PROFILE.modules[index]?.title || '核心模块'}、处理当前事项并同步结果。
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : (
          <section style={{ background: '#0f172a', color: '#fff', borderRadius: 18, padding: 28, minHeight: 220 }}>
            <div style={{ fontSize: 13, letterSpacing: 1.2, opacity: 0.78 }}>平台入口</div>
            <h2 style={{ margin: '12px 0 10px', fontSize: 30 }}>{APP_PROFILE.short_name} 控制台</h2>
            <div style={{ lineHeight: 1.9, opacity: 0.9 }}>
              围绕 {APP_PROFILE.industry_scope} 场景提供统一登录、模块访问、状态监控、报表输出和交付材料查看能力，
              让用户进入平台后即可快速完成查询、处理与导出。
            </div>
            <div style={{ marginTop: 18, display: 'flex', flexWrap: 'wrap', gap: 12 }}>
              <div style={{ padding: '8px 12px', borderRadius: 999, background: 'rgba(255,255,255,0.12)' }}>当前版本 {APP_PROFILE.version}</div>
              <div style={{ padding: '8px 12px', borderRadius: 999, background: 'rgba(255,255,255,0.12)' }}>角色覆盖 {APP_PROFILE.user_roles.length} 类</div>
              <div style={{ padding: '8px 12px', borderRadius: 999, background: 'rgba(255,255,255,0.12)' }}>核心模块 {APP_PROFILE.modules.length} 个</div>
            </div>
          </section>
        )}
        <section style={{ background: '#fff', borderRadius: 18, padding: 24, boxShadow: '0 8px 24px rgba(15, 23, 42, 0.05)' }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: '#0f172a', marginBottom: 10 }}>平台入口概览</div>
          <div style={{ color: '#475569', lineHeight: 1.8, marginBottom: 16 }}>
            {loginVariant === 'briefing'
              ? '登录后先进入专题洞察首页，再根据岗位进入模块处理区、分析区和文档导出区。'
              : loginVariant === 'workspace'
                ? '登录后按岗位工作台进入不同模块，系统会保留模块摘要、处理动作和结果反馈。'
                : '登录后可依次进入系统首页、业务模块、统计分析与文档导出区域，所有页面均保留中文标题、模块摘要与操作入口。'}
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 14 }}>
            {previewModules.map((module, index) => (
              <div key={module.key || module.route || index} style={{ border: '1px solid #dbeafe', borderRadius: 14, padding: 16, background: '#f8fbff' }}>
                <div style={{ fontWeight: 700, color: '#0f172a', marginBottom: 8 }}>{module.title}</div>
                <div style={{ color: '#475569', lineHeight: 1.7, fontSize: 14 }}>{module.description}</div>
              </div>
            ))}
          </div>
        </section>
      </div>
      </div>
    </div>
  );
}
""".replace("__LOGIN_VARIANT__", login_variant)


def _render_dashboard_page(profile: dict | None = None) -> str:
    blueprint = (profile or {}).get("experience_blueprint") or {}
    dashboard_variant = json.dumps(str(blueprint.get("dashboard_variant") or "command"), ensure_ascii=False)
    return """import type { CSSProperties } from 'react';
import { APP_PROFILE } from '../generated/appProfile';

const uiFont = `'Noto Sans SC', 'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei', 'IPRight CJK', sans-serif`;
const dashboardVariant = __DASHBOARD_VARIANT__;

const cardStyle: CSSProperties = {
  background: '#fff',
  borderRadius: 16,
  padding: 20,
  boxShadow: '0 8px 24px rgba(15, 23, 42, 0.05)',
};

export default function Dashboard() {
  const modulesPreview = APP_PROFILE.modules.slice(0, 4);
  const metricLabels = APP_PROFILE.dashboard_metrics.map((metric) => metric.title);
  return (
    <div style={{ display: 'grid', gap: 20, fontFamily: uiFont }}>
      <section style={cardStyle}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 24, alignItems: 'flex-start' }}>
          <div>
            <h1 style={{ margin: '0 0 8px', fontSize: 28, color: '#0f172a' }}>系统首页</h1>
            <div style={{ color: '#475569', lineHeight: 1.8 }}>
              {dashboardVariant === 'insight'
                ? `${APP_PROFILE.product_name}面向${APP_PROFILE.industry_scope}场景，首页以专题洞察、关键趋势和分析结论为主。`
                : dashboardVariant === 'workspace'
                  ? `${APP_PROFILE.product_name}面向${APP_PROFILE.industry_scope}场景，首页突出岗位协同、处理中任务和工作区入口。`
                  : `${APP_PROFILE.product_name}面向${APP_PROFILE.industry_scope}场景，当前版本为 ${APP_PROFILE.version}，支持统一入口查看业务概览、模块状态和处理建议。`}
            </div>
            <div style={{ marginTop: 10, display: 'inline-flex', gap: 10, alignItems: 'center', padding: '6px 10px', background: '#0f172a', color: '#fff', borderRadius: 999 }}>
              <span style={{ fontWeight: 700, letterSpacing: 1 }}>{APP_PROFILE.short_name}</span>
              <span style={{ opacity: 0.8 }}>{dashboardVariant === 'insight' ? '专题洞察' : dashboardVariant === 'workspace' ? '协同总览' : '场景总览'}</span>
            </div>
          </div>
          <div style={{ minWidth: 240, padding: 16, borderRadius: 14, background: '#eff6ff', color: '#1d4ed8' }}>
            <div style={{ fontWeight: 700, marginBottom: 8 }}>{dashboardVariant === 'workspace' ? '协同摘要' : '场景摘要'}</div>
            <div style={{ lineHeight: 1.7 }}>{APP_PROFILE.scene}</div>
          </div>
        </div>
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 16 }}>
        {APP_PROFILE.dashboard_metrics.map((metric, index) => (
          <div key={metric.title} style={cardStyle}>
            <div style={{ fontSize: 30, fontWeight: 700, color: metric.color }}>{metric.value}</div>
            <div style={{ marginTop: 10, color: '#64748b' }}>{metricLabels[index] || `指标 ${index + 1}`}</div>
          </div>
        ))}
      </section>

      <section style={{ display: 'grid', gridTemplateColumns: dashboardVariant === 'workspace' ? '1fr 1.1fr' : '1.2fr 1fr', gap: 20 }}>
        <div style={cardStyle}>
          <h2 style={{ marginTop: 0, marginBottom: 12 }}>
            {dashboardVariant === 'insight' ? '专题洞察视图' : dashboardVariant === 'workspace' ? '岗位工作区总览' : '核心模块总览'}
          </h2>
          <div style={{ display: 'grid', gap: 12 }}>
            {modulesPreview.map((module) => (
              <div key={module.key} style={{ border: '1px solid #e2e8f0', borderRadius: 12, padding: 14 }}>
                <div style={{ fontWeight: 700, color: '#0f172a', marginBottom: 6 }}>{module.title || '功能模块'}</div>
                <div style={{ color: '#475569', lineHeight: 1.7 }}>
                  {dashboardVariant === 'workspace'
                    ? `${module.description} 当前优先服务于 ${APP_PROFILE.user_roles[0] || '业务人员'} 的工作台处理。`
                    : module.description}
                </div>
              </div>
            ))}
          </div>
        </div>
        <div style={cardStyle}>
          <h2 style={{ marginTop: 0, marginBottom: 12 }}>
            {dashboardVariant === 'insight' ? '关键分析结论' : dashboardVariant === 'workspace' ? '岗位协同任务' : '最近工作动态'}
          </h2>
          {dashboardVariant === 'insight' ? (
            <div style={{ display: 'grid', gap: 12 }}>
              {APP_PROFILE.modules.slice(0, 4).map((module, index) => (
                <div key={module.key} style={{ border: '1px solid #e2e8f0', borderRadius: 12, padding: 14, background: '#fafcff' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                    <strong>{module.title}</strong>
                    <span style={{ color: '#1677ff' }}>专题 {index + 1}</span>
                  </div>
                  <div style={{ marginTop: 8, color: '#475569', lineHeight: 1.7 }}>
                    围绕 {module.title} 汇总当前关注字段、状态趋势和处理结论，便于首页快速掌握重点。
                  </div>
                </div>
              ))}
            </div>
          ) : dashboardVariant === 'workspace' ? (
            <div style={{ display: 'grid', gap: 12 }}>
              {APP_PROFILE.user_roles.slice(0, 4).map((role, index) => (
                <div key={role || index} style={{ border: '1px solid #e2e8f0', borderRadius: 12, padding: 14 }}>
                  <div style={{ fontWeight: 700, color: '#0f172a' }}>{role}</div>
                  <div style={{ marginTop: 8, color: '#475569', lineHeight: 1.7 }}>
                    当前负责 {APP_PROFILE.modules[index]?.title || '核心模块'}，可在工作区中查看待处理事项与结果回写。
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid #e2e8f0' }}>
                  <th style={{ padding: '10px 0', textAlign: 'left' }}>时间</th>
                  <th style={{ padding: '10px 0', textAlign: 'left' }}>模块</th>
                  <th style={{ padding: '10px 0', textAlign: 'left' }}>进展</th>
                </tr>
              </thead>
              <tbody>
                {APP_PROFILE.modules.slice(0, 5).map((module, index) => (
                  <tr key={module.key} style={{ borderBottom: '1px solid #f1f5f9' }}>
                    <td style={{ padding: '10px 0', color: '#64748b' }}>2026-05-0{index + 1} 10:{index}0</td>
                    <td style={{ padding: '10px 0' }}>{module.title || '功能模块'}</td>
                    <td style={{ padding: '10px 0', color: '#16a34a' }}>状态正常，已同步最新处理结果</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </section>
    </div>
  );
}
""".replace("__DASHBOARD_VARIANT__", dashboard_variant)


def _render_module_page(module: dict) -> str:
    component_name = f"{_camel_name(module.get('route', module['key']))}Page"
    module_code = _module_code(module)
    theme = _module_theme(module)
    route_copy = _route_copy(str(module.get("route", "")), module_code)
    module_title = str(module.get("title") or route_copy["title"])
    module_summary = str(module.get("description") or route_copy["summary"])
    module_action = str(module.get("primary_action") or route_copy["action"])
    module_placeholder = str(module.get("filter_placeholder") or route_copy["placeholder"])
    module_headers = list(module.get("table_headers") or route_copy["headers"])
    module_rows = list(module.get("rows") or route_copy["rows"])
    module_highlights = list(module.get("highlights") or route_copy["highlights"])
    route_badge = f"{module_title}业务界面"
    page_variant = str(module.get("page_variant") or "records")
    return f"""import type {{ CSSProperties }} from 'react';
import {{ APP_PROFILE }} from '../generated/appProfile';

const uiFont = `'Noto Sans SC', 'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei', 'IPRight CJK', sans-serif`;

const panelStyle: CSSProperties = {{
  background: (APP_PROFILE.visual_profile?.panel_background as string) || '#fff',
  borderRadius: 16,
  padding: 16,
  boxShadow: '0 8px 24px rgba(15, 23, 42, 0.05)',
  border: `1px solid ${{(APP_PROFILE.visual_profile?.panel_border as string) || '#dbe3ef'}}`,
}};

const moduleTheme = {json.dumps(theme, ensure_ascii=False)};
const moduleTitle = {json.dumps(module_title, ensure_ascii=False)};
const moduleSummary = {json.dumps(module_summary, ensure_ascii=False)};
const moduleAction = {json.dumps(module_action, ensure_ascii=False)};
const modulePlaceholder = {json.dumps(module_placeholder, ensure_ascii=False)};
const moduleHeaders = {json.dumps(module_headers, ensure_ascii=False)};
const moduleRows = {json.dumps(module_rows, ensure_ascii=False)};
const moduleHighlights = {json.dumps(module_highlights, ensure_ascii=False)};
const routeBadge = {json.dumps(route_badge, ensure_ascii=False)};
const pageVariant: string = {json.dumps(page_variant, ensure_ascii=False)};
const visualProfile = APP_PROFILE.visual_profile || {{}};
const moduleRowsSafe = moduleRows.length > 0
  ? moduleRows
  : [
      ['DEMO-001', moduleTitle, '系统', '处理中', '示例记录', '2026-05-08'],
      ['DEMO-002', `${{moduleTitle}}重点事项`, '系统', '已完成', '示例记录', '2026-05-07'],
    ];
const modulePrimaryRow = moduleRowsSafe[0] || [];
const moduleTopCards = [
  {{
    label: pageVariant === 'operations' ? '执行焦点' : pageVariant === 'insight' ? '重点指标' : pageVariant === 'workspace' ? '岗位视角' : '主数据范围',
    value: moduleHeaders.slice(0, 2).join(' / ') || moduleTitle,
    detail: `当前页面围绕${{moduleHeaders.slice(0, 3).join('、') || moduleTitle}}组织信息展示与操作。`,
  }},
  {{
    label: pageVariant === 'operations' ? '首个任务' : pageVariant === 'insight' ? '预警样例' : pageVariant === 'workspace' ? '当前事项' : (moduleHeaders[0] || '首条记录'),
    value: modulePrimaryRow[0] || moduleTitle,
    detail: `${{moduleHeaders[1] || '主题字段'}}：${{modulePrimaryRow[1] || moduleSummary}}`,
  }},
  {{
    label: pageVariant === 'operations' ? '节点关注' : pageVariant === 'insight' ? '分析结论' : pageVariant === 'workspace' ? '协同提醒' : '业务亮点',
    value: moduleHighlights[0] || moduleAction,
    detail: moduleHighlights.slice(1, 3).join('；') || `围绕${{moduleAction}}、状态校核和结果留痕开展处理。`,
  }},
];
const moduleBusinessPanels = [
  {{
    label: '当前焦点',
    value: routeBadge,
    detail: `围绕${{moduleTitle}}组织核心业务内容、流程入口和状态反馈。`,
  }},
  {{
    label: '数据样例',
    value: modulePrimaryRow[1] || moduleTitle,
    detail: `${{moduleHeaders[2] || '责任字段'}}：${{modulePrimaryRow[2] || '系统'}}，${{moduleHeaders[3] || '状态字段'}}：${{modulePrimaryRow[3] || '处理中'}}`,
  }},
  {{
    label: '角色视角',
    value: APP_PROFILE.user_roles?.[0] || '业务人员',
    detail: `当前页面支持${{moduleAction}}、查询定位、结果复核和导出归档等动作。`,
  }},
];
const moduleExecutionBoard = [
  `进入${{moduleTitle}}后先查看标题区与筛选区，确认当前处理对象与业务范围。`,
  '根据搜索条件、状态标签或列表记录定位目标事项，再执行对应主操作。',
  '处理完成后复核结果字段、更新时间与状态反馈，确保记录准确并可追溯。',
];

export default function {component_name}() {{
  return (
    <div style={{{{ display: 'grid', gap: 16, fontFamily: uiFont }}}}>
      <section style={{{{
        ...panelStyle,
        background: `linear-gradient(135deg, ${{moduleTheme.soft}} 0%, ${{(visualProfile.panel_background as string) || '#ffffff'}} 62%)`,
      }}}}>
        <div style={{{{ display: 'flex', justifyContent: 'space-between', gap: 16, alignItems: 'flex-start' }}}}>
          <div>
            <h1 style={{{{ margin: '0 0 10px', fontSize: 26 }}}}>{{moduleTitle}}</h1>
            <div style={{{{ color: '#475569', lineHeight: 1.8 }}}}>{{moduleSummary}}</div>
            <div style={{{{ marginTop: 12, display: 'flex', flexWrap: 'wrap', gap: 10 }}}}>
              <span style={{{{ padding: '6px 10px', borderRadius: 999, background: moduleTheme.accent, color: '#fff', fontWeight: 700 }}}}>
                当前模块
              </span>
              <span style={{{{ padding: '6px 10px', borderRadius: 999, background: '#0f172a', color: '#fff', fontWeight: 600 }}}}>
                版本 {{APP_PROFILE.version}}
              </span>
              <span style={{{{ padding: '6px 10px', borderRadius: 999, background: '#fff', color: moduleTheme.strong, border: `1px solid ${{moduleTheme.accent}}44`, fontWeight: 600 }}}}>
                {{moduleAction}}
              </span>
            </div>
          </div>
          <button
            type="button"
            style={{{{ border: 'none', background: moduleTheme.accent, color: '#fff', padding: '10px 16px', borderRadius: 10, cursor: 'pointer', fontWeight: 600, fontFamily: uiFont }}}}
          >
            {{moduleAction}}
          </button>
        </div>
      </section>

      <section style={{{{ display: 'grid', gridTemplateColumns: pageVariant === 'workspace' ? '1.15fr 0.85fr 0.85fr' : 'repeat(3, minmax(0, 1fr))', gap: 12 }}}}>
        {{moduleTopCards.map((card) => (
          <div key={{card.label}} style={{{{
            ...panelStyle,
            border: `1px solid ${{moduleTheme.accent}}33`,
            boxShadow: '0 10px 24px rgba(15, 23, 42, 0.04)',
          }}}}>
            <div style={{{{ color: '#64748b', fontSize: 12, letterSpacing: 1.1 }}}}>{{card.label}}</div>
            <div style={{{{ marginTop: 8, fontSize: 22, fontWeight: 700, color: card.label === '核心字段' ? moduleTheme.strong : '#0f172a' }}}}>{{card.value}}</div>
            <div style={{{{ marginTop: 8, color: '#475569', lineHeight: 1.6 }}}}>{{card.detail}}</div>
          </div>
        ))}}
      </section>

      <section style={{{{ display: 'grid', gridTemplateColumns: pageVariant === 'insight' ? '1.2fr 1fr 1fr' : 'repeat(3, minmax(0, 1fr))', gap: 12 }}}}>
        {{moduleBusinessPanels.map((panel) => (
          <div key={{panel.label}} style={{{{ ...panelStyle, border: `1px solid ${{moduleTheme.accent}}22` }}}}>
            <div style={{{{ color: '#64748b', fontSize: 12, letterSpacing: 1.1 }}}}>{{panel.label}}</div>
            <div style={{{{ marginTop: 8, fontSize: 22, fontWeight: 700, color: moduleTheme.strong }}}}>{{panel.value}}</div>
            <div style={{{{ marginTop: 8, color: '#475569', lineHeight: 1.7 }}}}>{{panel.detail}}</div>
          </div>
        ))}}
      </section>

      <section style={{panelStyle}}>
        <div style={{{{ display: 'flex', gap: 12, marginBottom: 16 }}}}>
          <input
            name="搜索"
            placeholder={{modulePlaceholder}}
            aria-label={{modulePlaceholder}}
            type="search"
            autoComplete="off"
            style={{{{ flex: 1, padding: '10px 12px', border: '1px solid #cbd5e1', borderRadius: 10, fontFamily: uiFont }}}}
          />
          <button type="button" style={{{{ padding: '10px 16px', borderRadius: 10, border: '1px solid #cbd5e1', background: '#fff', fontFamily: uiFont }}}}>查询列表</button>
          <button type="button" style={{{{ padding: '10px 16px', borderRadius: 10, border: '1px solid #cbd5e1', background: '#fff', fontFamily: uiFont }}}}>导出结果</button>
        </div>
        <table style={{{{ width: '100%', borderCollapse: 'collapse' }}}}>
          <thead>
            <tr style={{{{ borderBottom: '1px solid #e2e8f0' }}}}>
              {{moduleHeaders.map((header) => (
                <th key={{header}} style={{{{ padding: '10px 12px', textAlign: 'left', color: '#475569' }}}}>{{header}}</th>
              ))}}
            </tr>
          </thead>
          <tbody>
            {{moduleRowsSafe.map((row, rowIndex) => (
              <tr key={{rowIndex}} style={{{{ borderBottom: '1px solid #f1f5f9' }}}}>
                {{row.map((cell, cellIndex) => (
                  <td key={{cellIndex}} style={{{{ padding: '12px' }}}}>{{cell}}</td>
                ))}}
              </tr>
            ))}}
          </tbody>
        </table>
      </section>

      {{pageVariant === 'operations' ? (
        <section style={{{{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}}}>
          <div style={{{{ ...panelStyle, background: moduleTheme.soft, border: `1px solid ${{moduleTheme.accent}}22` }}}}>
            <h2 style={{{{ marginTop: 0 }}}}>执行节奏</h2>
            <div style={{{{ display: 'grid', gap: 10 }}}}>
              {{moduleExecutionBoard.map((item) => (
                <div key={{item}} style={{{{ padding: '12px 14px', borderRadius: 12, background: '#ffffff', color: moduleTheme.strong, border: `1px solid ${{moduleTheme.accent}}33`, lineHeight: 1.7 }}}}>
                  {{item}}
                </div>
              ))}}
            </div>
          </div>
          <div style={{{{ ...panelStyle, border: `1px solid ${{moduleTheme.accent}}22` }}}}>
            <h2 style={{{{ marginTop: 0 }}}}>结果亮点</h2>
            <div style={{{{ display: 'grid', gap: 10 }}}}>
              {{moduleHighlights.map((item) => (
                <div key={{item}} style={{{{ padding: '12px 14px', borderRadius: 12, background: '#f8fafc', color: '#334155', lineHeight: 1.7 }}}}>
                  {{item}}
                </div>
              ))}}
            </div>
          </div>
        </section>
      ) : pageVariant === 'insight' ? (
        <section style={{{{ display: 'grid', gridTemplateColumns: '1.15fr 0.85fr', gap: 16 }}}}>
          <div style={{{{ ...panelStyle, background: moduleTheme.soft, border: `1px solid ${{moduleTheme.accent}}22` }}}}>
            <h2 style={{{{ marginTop: 0 }}}}>分析透视</h2>
            <div style={{{{ display: 'grid', gap: 10 }}}}>
              {{moduleHighlights.map((item) => (
                <div key={{item}} style={{{{ border: `1px solid ${{moduleTheme.accent}}33`, background: '#ffffff', color: moduleTheme.strong, padding: '12px 14px', borderRadius: 12 }}}}>
                  {{item}}
                </div>
              ))}}
            </div>
          </div>
          <div style={{{{ ...panelStyle, border: `1px solid ${{moduleTheme.accent}}22` }}}}>
            <h2 style={{{{ marginTop: 0 }}}}>业务处理说明</h2>
            <div style={{{{ display: 'grid', gap: 10 }}}}>
              {{moduleExecutionBoard.map((item) => (
                <div key={{item}} style={{{{ padding: '12px 14px', borderRadius: 12, background: '#f8fafc', color: '#334155', lineHeight: 1.7 }}}}>
                  {{item}}
                </div>
              ))}}
            </div>
          </div>
        </section>
      ) : (
        <section style={{{{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}}}>
        <div style={{{{ ...panelStyle, background: moduleTheme.soft, border: `1px solid ${{moduleTheme.accent}}22` }}}}>
          <h2 style={{{{ marginTop: 0 }}}}>功能亮点</h2>
          <div style={{{{ display: 'grid', gap: 10 }}}}>
            {{moduleHighlights.map((item) => (
              <div key={{item}} style={{{{ border: `1px solid ${{moduleTheme.accent}}33`, background: '#ffffff', color: moduleTheme.strong, padding: '12px 14px', borderRadius: 12 }}}}>
                {{item}}
              </div>
            ))}}
          </div>
        </div>
        <div style={{{{ ...panelStyle, border: `1px solid ${{moduleTheme.accent}}22` }}}}>
          <h2 style={{{{ marginTop: 0 }}}}>业务处理说明</h2>
          <div style={{{{ display: 'grid', gap: 10 }}}}>
            {{moduleExecutionBoard.map((item) => (
              <div key={{item}} style={{{{ padding: '12px 14px', borderRadius: 12, background: '#f8fafc', color: '#334155', lineHeight: 1.7 }}}}>
                {{item}}
              </div>
            ))}}
          </div>
        </div>
        </section>
      )}}
    </div>
  );
}}
"""


def _render_frontend_app(profile: dict) -> str:
    imports = ["import { useState } from 'react';", "import { Routes, Route, useNavigate, useLocation } from 'react-router-dom';", "import './font.css';", "import Login from './pages/Login';", "import Dashboard from './pages/Dashboard';", "import { APP_PROFILE } from './generated/appProfile';"]
    route_imports = []
    route_lines = [
        "          <Route path=\"/\" element={<Dashboard />} />",
        "          <Route path=\"/dashboard\" element={<Dashboard />} />",
    ]
    for module in profile.get("modules", []):
        component_name = f"{_camel_name(module.get('route', module['key']))}Page"
        route_imports.append(f"import {component_name} from './pages/{component_name}';")
        route_lines.append(f"          <Route path=\"{module['route']}\" element={{<{component_name} />}} />")

    imports.extend(route_imports)
    imports_block = "\n".join(imports)
    routes_block = "\n".join(route_lines)
    nav_aliases = {"/dashboard": "系统首页"}
    for module in profile.get("modules", []):
        nav_aliases[module["route"]] = module.get("title", _route_copy(module["route"]).get("title", "功能页面"))
    return f"""{imports_block}

const AUTH_KEY = 'ipright_demo_auth';
const uiFont = `'Noto Sans SC', 'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei', 'IPRight CJK', sans-serif`;
const navAliases: Record<string, string> = {json.dumps(nav_aliases, ensure_ascii=False, indent=2)};

export default function App() {{
  const [loggedIn, setLoggedIn] = useState(() => localStorage.getItem(AUTH_KEY) === 'true');
  const navigate = useNavigate();
  const location = useLocation();
  const isDesktopClient = APP_PROFILE.app_type === 'desktop_client';
  const visualProfile = APP_PROFILE.visual_profile || {{}};
  const chromeTreatment = String((visualProfile.chrome_treatment as string) || (isDesktopClient ? 'desktop_workbench' : 'top_tabs'));
  const currentLabel = navAliases[location.pathname] || '系统首页';
  const focusTerms = Array.isArray(APP_PROFILE.focus_terms) ? APP_PROFILE.focus_terms.slice(0, 4) : [];

  const handleLogin = () => {{
    localStorage.setItem(AUTH_KEY, 'true');
    setLoggedIn(true);
    navigate('/dashboard');
  }};

  const handleLogout = () => {{
    localStorage.removeItem(AUTH_KEY);
    setLoggedIn(false);
    navigate('/login');
  }};

  if (!loggedIn) {{
    return <Login onLogin={{handleLogin}} />;
  }}

  const routes = (
    <Routes>
{routes_block}
    </Routes>
  );

  return (
    <div style={{{{ minHeight: '100vh', background: (visualProfile.shell_background as string) || '#f8fafc', fontFamily: uiFont }}}}>
      {{isDesktopClient ? (
        <>
          <header style={{{{
            height: 54,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 16px 0 18px',
            background: (visualProfile.nav_background as string) || '#111827',
            color: (visualProfile.nav_text as string) || '#fff',
            borderBottom: '1px solid rgba(148, 163, 184, 0.18)',
          }}}}>
            <div style={{{{ display: 'flex', alignItems: 'center', gap: 12 }}}}>
              <div style={{{{ display: 'flex', gap: 6, alignItems: 'center' }}}}>
                <span style={{{{ width: 10, height: 10, borderRadius: '50%', background: '#fb7185', display: 'inline-block' }}}} />
                <span style={{{{ width: 10, height: 10, borderRadius: '50%', background: '#fbbf24', display: 'inline-block' }}}} />
                <span style={{{{ width: 10, height: 10, borderRadius: '50%', background: '#4ade80', display: 'inline-block' }}}} />
              </div>
              <div style={{{{ fontWeight: 700 }}}}>{{APP_PROFILE.product_name}}</div>
              <div style={{{{ fontSize: 12, opacity: 0.78 }}}}>桌面客户端工作台</div>
            </div>
            <div style={{{{ display: 'flex', alignItems: 'center', gap: 10 }}}}>
              <div style={{{{ padding: '6px 10px', borderRadius: 999, background: 'rgba(255,255,255,0.08)', fontSize: 12 }}}}>
                {{APP_PROFILE.version}}
              </div>
              <div style={{{{ padding: '6px 10px', borderRadius: 999, background: 'rgba(37, 99, 235, 0.22)', fontSize: 12, color: '#dbeafe' }}}}>
                {{APP_PROFILE.short_name}}
              </div>
            </div>
          </header>
          <section style={{{{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 16,
            padding: '12px 18px',
            background: '#f8fafc',
            borderBottom: '1px solid rgba(203, 213, 225, 0.8)',
          }}}}>
            <div style={{{{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}}}>
              <span style={{{{ padding: '6px 10px', borderRadius: 999, background: '#dbeafe', color: '#1d4ed8', fontWeight: 700, fontSize: 12 }}}}>
                当前模块 {{currentLabel}}
              </span>
              <span style={{{{ padding: '6px 10px', borderRadius: 999, background: '#e2e8f0', color: '#334155', fontSize: 12 }}}}>
                {{APP_PROFILE.scene}}
              </span>
            </div>
            <div style={{{{ display: 'flex', alignItems: 'center', gap: 10 }}}}>
              <button type="button" style={{{{ padding: '8px 12px', borderRadius: 10, border: '1px solid #cbd5e1', background: '#fff', cursor: 'pointer', fontFamily: uiFont }}}}>刷新视图</button>
              <button type="button" style={{{{ padding: '8px 12px', borderRadius: 10, border: '1px solid #bfdbfe', background: '#eff6ff', color: '#1d4ed8', cursor: 'pointer', fontFamily: uiFont }}}}>打开工作区</button>
            </div>
          </section>
          <div style={{{{ display: 'flex', minHeight: 'calc(100vh - 102px)' }}}}>
            <nav style={{{{
              width: 268,
              minWidth: 268,
              background: (visualProfile.nav_background as string) || '#0f172a',
              color: (visualProfile.nav_text as string) || '#fff',
              padding: 16,
              borderRight: '1px solid rgba(148, 163, 184, 0.18)',
              writingMode: 'horizontal-tb',
              textOrientation: 'mixed',
            }}}}>
              <div style={{{{ marginBottom: 24 }}}}>
                <div style={{{{ marginBottom: 14, padding: '8px 10px', borderRadius: 10, background: 'rgba(255,255,255,0.08)', fontSize: 12, letterSpacing: 1.1 }}}}>
                  桌面客户端工作台
                </div>
                <div style={{{{
                  fontSize: 20,
                  fontWeight: 700,
                  marginBottom: 8,
                  lineHeight: 1.45,
                  writingMode: 'horizontal-tb',
                  textOrientation: 'mixed',
                  wordBreak: 'keep-all',
                  overflowWrap: 'break-word',
                  whiteSpace: 'normal',
                }}}}>{{APP_PROFILE.product_name}}</div>
                <div style={{{{ display: 'inline-flex', alignItems: 'center', gap: 8, marginBottom: 10, padding: '6px 10px', borderRadius: 999, background: 'rgba(22, 119, 255, 0.18)', color: '#dbeafe', fontWeight: 700 }}}}>
                  <span>当前版本</span>
                  <span>{{APP_PROFILE.version}}</span>
                </div>
                <div style={{{{ marginBottom: 10, fontSize: 12, color: '#93c5fd', letterSpacing: 1.4 }}}}>{{APP_PROFILE.short_name}}</div>
                <div style={{{{ fontSize: 13, lineHeight: 1.7, color: '#cbd5e1' }}}}>{{APP_PROFILE.scene}}</div>
              </div>
              {{APP_PROFILE.nav_items.map((item) => (
                <div
                  key={{item.path}}
                  onClick={{() => navigate(item.path)}}
                  style={{{{
                    padding: '10px 14px',
                    cursor: 'pointer',
                    borderRadius: 10,
                    background: location.pathname === item.path ? ((visualProfile.accent as string) || '#1677ff') : 'transparent',
                    marginBottom: 8,
                    color: (visualProfile.nav_text as string) || '#fff',
                  }}}}
                >
                  <div style={{{{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}}}>
                    <span style={{{{ width: 20, textAlign: 'center', flexShrink: 0 }}}}>{{item.icon}}</span>
                    <div style={{{{
                      fontWeight: 600,
                      lineHeight: 1.45,
                      writingMode: 'horizontal-tb',
                      textOrientation: 'mixed',
                      wordBreak: 'keep-all',
                      overflowWrap: 'break-word',
                      whiteSpace: 'normal',
                    }}}}>{{navAliases[item.path] || item.label || '功能页面'}}</div>
                  </div>
                </div>
              ))}}
              <div
                onClick={{handleLogout}}
                style={{{{ padding: '10px 14px', cursor: 'pointer', borderRadius: 10, marginTop: 24, color: '#fda4af', border: '1px solid rgba(253, 164, 175, 0.3)' }}}}
              >
                退出登录
              </div>
            </nav>
            <main style={{{{ flex: 1, padding: 18 }}}}>{{routes}}</main>
          </div>
        </>
      ) : chromeTreatment === 'indexed_topbar' ? (
        <>
          <header style={{{{
            padding: '20px 28px 14px',
            background: (visualProfile.panel_background as string) || '#ffffff',
            borderBottom: `1px solid ${{(visualProfile.panel_border as string) || '#dbe3ef'}}`,
          }}}}>
            <div style={{{{ display: 'flex', justifyContent: 'space-between', gap: 18, alignItems: 'flex-start' }}}}>
              <div>
                <div style={{{{ display: 'inline-flex', padding: '6px 12px', borderRadius: 999, background: (visualProfile.soft as string) || '#eff6ff', color: (visualProfile.strong as string) || '#1d4ed8', fontWeight: 700, marginBottom: 12 }}}}>
                  索引导航视图
                </div>
                <div style={{{{ fontSize: 28, fontWeight: 700, color: '#0f172a' }}}}>{{APP_PROFILE.product_name}}</div>
                <div style={{{{ marginTop: 8, color: '#475569', lineHeight: 1.8, maxWidth: 920 }}}}>{{APP_PROFILE.scene}}</div>
              </div>
              <button type="button" onClick={{handleLogout}} style={{{{ padding: '10px 14px', borderRadius: 12, border: `1px solid ${{(visualProfile.panel_border as string) || '#dbe3ef'}}`, background: '#fff', cursor: 'pointer', fontFamily: uiFont }}}}>
                退出登录
              </button>
            </div>
            <div style={{{{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 10 }}}}>
              {{APP_PROFILE.nav_items.map((item) => (
                <button
                  key={{item.path}}
                  type="button"
                  onClick={{() => navigate(item.path)}}
                  style={{{{
                    border: 'none',
                    cursor: 'pointer',
                    padding: '10px 14px',
                    borderRadius: 12,
                    background: location.pathname === item.path ? ((visualProfile.accent as string) || '#2563eb') : ((visualProfile.soft as string) || '#eff6ff'),
                    color: location.pathname === item.path ? '#fff' : ((visualProfile.strong as string) || '#1d4ed8'),
                    fontWeight: 700,
                    fontFamily: uiFont,
                  }}}}
                >
                  {{navAliases[item.path] || item.label}}
                </button>
              ))}}
            </div>
          </header>
          <div style={{{{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: 20, padding: 24 }}}}>
            <main style={{{{
              minHeight: 'calc(100vh - 180px)',
              padding: 20,
              borderRadius: 20,
              background: (visualProfile.panel_background as string) || '#ffffff',
              boxShadow: '0 10px 30px rgba(15, 23, 42, 0.06)',
              border: `1px solid ${{(visualProfile.panel_border as string) || '#dbe3ef'}}`,
            }}}}>
              {{routes}}
            </main>
            <aside style={{{{ display: 'grid', gap: 16, alignContent: 'start' }}}}>
              <section style={{{{
                padding: 18,
                borderRadius: 18,
                background: 'linear-gradient(160deg, rgba(255,255,255,0.95), rgba(255,255,255,0.82))',
                border: `1px solid ${{(visualProfile.panel_border as string) || '#dbe3ef'}}`,
              }}}}>
                <div style={{{{ color: '#64748b', fontSize: 12, letterSpacing: 1.2 }}}}>当前索引</div>
                <div style={{{{ marginTop: 8, fontSize: 24, fontWeight: 700, color: '#0f172a' }}}}>{{currentLabel}}</div>
                <div style={{{{ marginTop: 10, color: '#475569', lineHeight: 1.7 }}}}>{{APP_PROFILE.industry_scope}}</div>
              </section>
              <section style={{{{
                padding: 18,
                borderRadius: 18,
                background: (visualProfile.panel_background as string) || '#ffffff',
                border: `1px solid ${{(visualProfile.panel_border as string) || '#dbe3ef'}}`,
              }}}}>
                <div style={{{{ color: '#64748b', fontSize: 12, letterSpacing: 1.2 }}}}>任务焦点</div>
                <div style={{{{ display: 'grid', gap: 10, marginTop: 14 }}}}>
                  {{(focusTerms.length ? focusTerms : [APP_PROFILE.short_name, APP_PROFILE.version, currentLabel]).map((term) => (
                    <div key={{term}} style={{{{ padding: '10px 12px', borderRadius: 12, background: (visualProfile.soft as string) || '#eff6ff', color: (visualProfile.strong as string) || '#1d4ed8', fontWeight: 700 }}}}>
                      {{term}}
                    </div>
                  ))}}
                </div>
              </section>
            </aside>
          </div>
        </>
      ) : chromeTreatment === 'sectioned_header' ? (
        <>
          <header style={{{{
            padding: '22px 28px',
            background: (visualProfile.nav_background as string) || '#111827',
            color: (visualProfile.nav_text as string) || '#fff',
          }}}}>
            <div style={{{{ display: 'flex', justifyContent: 'space-between', gap: 20, alignItems: 'flex-start' }}}}>
              <div>
                <div style={{{{ fontSize: 28, fontWeight: 700 }}}}>{{APP_PROFILE.product_name}}</div>
                <div style={{{{ marginTop: 8, lineHeight: 1.8, maxWidth: 920, opacity: 0.86 }}}}>{{APP_PROFILE.scene}}</div>
              </div>
              <button type="button" onClick={{handleLogout}} style={{{{ padding: '10px 14px', borderRadius: 12, border: '1px solid rgba(255,255,255,0.18)', background: 'rgba(255,255,255,0.08)', color: '#fff', cursor: 'pointer', fontFamily: uiFont }}}}>
                退出登录
              </button>
            </div>
          </header>
          <div style={{{{ display: 'grid', gridTemplateColumns: '280px minmax(0, 1fr)', gap: 18, padding: 22 }}}}>
            <aside style={{{{ display: 'grid', gap: 14, alignContent: 'start' }}}}>
              {{APP_PROFILE.nav_items.map((item) => (
                <div
                  key={{item.path}}
                  onClick={{() => navigate(item.path)}}
                  style={{{{
                    cursor: 'pointer',
                    padding: '16px 16px 14px',
                    borderRadius: 18,
                    background: location.pathname === item.path ? ((visualProfile.soft as string) || '#eff6ff') : '#ffffff',
                    border: `1px solid ${{location.pathname === item.path ? ((visualProfile.accent as string) || '#2563eb') + '44' : ((visualProfile.panel_border as string) || '#dbe3ef')}}`,
                    boxShadow: location.pathname === item.path ? '0 10px 24px rgba(15, 23, 42, 0.06)' : 'none',
                  }}}}
                >
                  <div style={{{{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}}}>
                    <span>{{item.icon}}</span>
                    <strong style={{{{ color: '#0f172a' }}}}>{{navAliases[item.path] || item.label}}</strong>
                  </div>
                  <div style={{{{ color: '#475569', lineHeight: 1.7 }}}}>
                    {{item.path === '/dashboard' ? APP_PROFILE.scene : `${{navAliases[item.path] || item.label}}围绕当前产品模块展开。`}}
                  </div>
                </div>
              ))}}
            </aside>
            <main style={{{{ display: 'grid', gap: 16, alignContent: 'start' }}}}>
              <section style={{{{
                padding: 18,
                borderRadius: 18,
                background: 'linear-gradient(135deg, rgba(255,255,255,0.98), rgba(255,255,255,0.84))',
                border: `1px solid ${{(visualProfile.panel_border as string) || '#dbe3ef'}}`,
              }}}}>
                <div style={{{{ display: 'flex', flexWrap: 'wrap', gap: 10, marginBottom: 10 }}}}>
                  <span style={{{{ padding: '6px 10px', borderRadius: 999, background: (visualProfile.soft as string) || '#eff6ff', color: (visualProfile.strong as string) || '#1d4ed8', fontWeight: 700 }}}}>当前章节 {{currentLabel}}</span>
                  <span style={{{{ padding: '6px 10px', borderRadius: 999, background: '#ffffff', border: `1px solid ${{(visualProfile.panel_border as string) || '#dbe3ef'}}`, color: '#475569' }}}}>{{APP_PROFILE.short_name}}</span>
                </div>
                <div style={{{{ color: '#475569', lineHeight: 1.8 }}}}>{{APP_PROFILE.industry_scope}}</div>
              </section>
              <section style={{{{
                minHeight: 'calc(100vh - 220px)',
                padding: 20,
                borderRadius: 20,
                background: (visualProfile.panel_background as string) || '#ffffff',
                border: `1px solid ${{(visualProfile.panel_border as string) || '#dbe3ef'}}`,
                boxShadow: '0 10px 30px rgba(15, 23, 42, 0.06)',
              }}}}>
                {{routes}}
              </section>
            </main>
          </div>
        </>
      ) : (
        <>
          <header style={{{{
            padding: '18px 26px 16px',
            background: (visualProfile.nav_background as string) || '#0f172a',
            color: (visualProfile.nav_text as string) || '#fff',
          }}}}>
            <div style={{{{ display: 'flex', justifyContent: 'space-between', gap: 18, alignItems: 'flex-start' }}}}>
              <div>
                <div style={{{{ display: 'inline-flex', padding: '6px 12px', borderRadius: 999, background: 'rgba(255,255,255,0.12)', fontWeight: 700, marginBottom: 12 }}}}>
                  顶部导航工作台
                </div>
                <div style={{{{ fontSize: 28, fontWeight: 700 }}}}>{{APP_PROFILE.product_name}}</div>
                <div style={{{{ marginTop: 8, lineHeight: 1.8, maxWidth: 920, opacity: 0.88 }}}}>{{APP_PROFILE.scene}}</div>
              </div>
              <button type="button" onClick={{handleLogout}} style={{{{ padding: '10px 14px', borderRadius: 12, border: '1px solid rgba(255,255,255,0.18)', background: 'rgba(255,255,255,0.08)', color: '#fff', cursor: 'pointer', fontFamily: uiFont }}}}>
                退出登录
              </button>
            </div>
            <div style={{{{ display: 'flex', flexWrap: 'wrap', gap: 10, marginTop: 16 }}}}>
              {{APP_PROFILE.nav_items.map((item) => (
                <button
                  key={{item.path}}
                  type="button"
                  onClick={{() => navigate(item.path)}}
                  style={{{{
                    border: 'none',
                    cursor: 'pointer',
                    padding: '10px 14px',
                    borderRadius: 12,
                    background: location.pathname === item.path ? '#ffffff' : 'rgba(255,255,255,0.12)',
                    color: location.pathname === item.path ? ((visualProfile.strong as string) || '#1d4ed8') : '#ffffff',
                    fontWeight: 700,
                    fontFamily: uiFont,
                  }}}}
                >
                  {{navAliases[item.path] || item.label}}
                </button>
              ))}}
            </div>
          </header>
          <section style={{{{
            margin: '18px 24px 0',
            padding: '18px 20px',
            borderRadius: 18,
            background: `linear-gradient(135deg, ${{(visualProfile.soft as string) || '#eff6ff'}} 0%, rgba(255,255,255,0.92) 72%)`,
            border: `1px solid ${{(visualProfile.panel_border as string) || '#dbe3ef'}}`,
          }}}}>
            <div style={{{{ display: 'flex', justifyContent: 'space-between', gap: 18, alignItems: 'flex-start' }}}}>
              <div>
                <div style={{{{ color: '#64748b', fontSize: 12, letterSpacing: 1.2 }}}}>当前视图</div>
                <div style={{{{ marginTop: 8, fontSize: 24, fontWeight: 700, color: '#0f172a' }}}}>{{currentLabel}}</div>
                <div style={{{{ marginTop: 8, color: '#475569', lineHeight: 1.8 }}}}>{{APP_PROFILE.industry_scope}}</div>
              </div>
              <div style={{{{ display: 'flex', flexWrap: 'wrap', gap: 10, justifyContent: 'flex-end' }}}}>
                {{(focusTerms.length ? focusTerms : [APP_PROFILE.short_name, APP_PROFILE.version]).map((term) => (
                  <span key={{term}} style={{{{ padding: '8px 12px', borderRadius: 999, background: '#ffffff', border: `1px solid ${{(visualProfile.panel_border as string) || '#dbe3ef'}}`, color: '#334155' }}}}>
                    {{term}}
                  </span>
                ))}}
              </div>
            </div>
          </section>
          <main style={{{{
            padding: 24,
          }}}}>
            <div style={{{{
              minHeight: 'calc(100vh - 250px)',
              padding: 20,
              borderRadius: 20,
              background: (visualProfile.panel_background as string) || '#ffffff',
              border: `1px solid ${{(visualProfile.panel_border as string) || '#dbe3ef'}}`,
              boxShadow: '0 10px 30px rgba(15, 23, 42, 0.06)',
            }}}}>
              {{routes}}
            </div>
          </main>
        </>
      )}}
    </div>
  );
}}
"""


def _render_font_css() -> str:
    return """@import "@fontsource/noto-sans-sc/chinese-simplified.css";

:root {
  --app-ui-font: 'Noto Sans SC', 'Noto Sans CJK SC', 'PingFang SC', 'Microsoft YaHei', 'IPRight CJK', sans-serif;
}

@font-face {
  font-family: 'IPRight CJK';
  src: url('/fonts/IPRightCJK.ttf') format('truetype');
  font-display: swap;
}

html, body, #root {
  margin: 0;
  min-width: 1360px;
  font-family: var(--app-ui-font);
  writing-mode: horizontal-tb;
  text-orientation: mixed;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

input, button, textarea, select {
  font-family: var(--app-ui-font);
}

*, *::before, *::after {
  box-sizing: border-box;
}

nav, aside, .sidebar, [class*='sidebar'], [class*='nav'] {
  writing-mode: horizontal-tb;
  text-orientation: mixed;
}
"""


def _render_app_css() -> str:
    return """@import "./font.css";

#root {
  min-height: 100vh;
}
"""


def _ensure_main_imports_font_css(frontend_root: str) -> None:
    main_path = Path(frontend_root) / "src" / "main.tsx"
    if not main_path.exists():
        return

    content = main_path.read_text(encoding="utf-8")
    if "import './font.css';" in content or 'import "./font.css";' in content:
        return

    lines = content.splitlines()
    insert_at = 0
    while insert_at < len(lines) and lines[insert_at].startswith("import "):
        insert_at += 1
    lines.insert(insert_at, "import './font.css';")
    main_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_task_specific_app(frontend_root: str, backend_root: str, profile: dict) -> None:
    _ensure_frontend_dependencies(frontend_root)
    _ensure_backend_dependencies(backend_root)
    package_lock_path = Path(frontend_root) / "package-lock.json"
    if package_lock_path.exists():
        package_lock_path.unlink()
    _write_text(os.path.join(frontend_root, "src", "generated", "appProfile.ts"), build_frontend_profile_source(profile))
    _write_text(os.path.join(frontend_root, "src", "font.css"), _render_font_css())
    _write_text(os.path.join(frontend_root, "src", "App.css"), _render_app_css())
    _ensure_main_imports_font_css(frontend_root)
    # Remove seed UI source so core pages must come from the current task's LLM output.
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

    font_source = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "IPRightCJK.ttf"
    if font_source.exists():
        font_target = Path(frontend_root) / "public" / "fonts" / "IPRightCJK.ttf"
        font_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(font_source, font_target)

    write_generated_backend_files(backend_root, profile, _write_text)
