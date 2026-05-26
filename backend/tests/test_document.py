from __future__ import annotations

import json
import os
import tempfile
import zipfile

from app.services.document.application_form import ApplicationFormGenerator
from app.services.document.manual import SoftwareManualGenerator
from app.services.document.codebook import SourceCodeBookGenerator
from app.services.document.diagrams import generate_system_architecture_diagram
from app.services.project_profile import build_plan_seed, build_task_profile


def test_manual_can_generate():
    gen = SoftwareManualGenerator(product_name="TestApp", version="V1.0")
    gen.generate_full(
        prd_summary={"core_modules": ["A", "B"]},
        screenshots_meta=[],
    )
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        gen.save(f.name)
        assert os.path.getsize(f.name) > 0
        os.unlink(f.name)


def test_manual_has_header():
    gen = SoftwareManualGenerator(product_name="TestApp", version="V1.0")
    gen.generate_full()
    for section in gen.doc.sections:
        assert section.header.paragraphs
        text = section.header.paragraphs[0].text
        assert "TestApp" in text


def test_manual_excludes_removed_sections_and_text():
    gen = SoftwareManualGenerator(product_name="TestApp", version="V1.0")
    gen.generate_full(
        screenshots_meta=[{
            "page_title": "登录页",
            "caption": "图1 登录页",
            "image_path": "",
            "elements": ["TestApp V1.0", "👥 用户管理"],
        }],
    )
    joined = "\n".join(p.text for p in gen.doc.paragraphs)
    assert "文档中的截图均来自软件真实运行界面" not in joined
    assert "本次说明书基于真实运行页面自动采集" not in joined
    assert "开发设计流程" not in joined
    assert "开发设计流程图" not in joined
    assert "开发语言说明" in joined
    assert "技术选型说明" in joined
    assert "数据组织与结果输出说明" in joined
    assert "图1：TestApp系统架构图" not in joined
    assert "TestApp V1.0" in joined
    assert "👥 用户管理" not in joined
    assert "部署维护说明" not in joined
    assert "部署说明" not in joined
    assert "运行维护说明" in joined
    assert "数据与材料管理说明" not in joined
    assert "常见问题" not in joined
    assert "研发测试与验收建议" not in joined
    assert "功能测试建议" not in joined
    assert "培训与上线建议" not in joined
    assert "交付物清单建议" not in joined
    assert "后续迭代建议" not in joined
    assert "建议在研发阶段同步执行" not in joined
    assert "验收时应重点核对" not in joined


def test_manual_normalizes_spacing_and_ui_symbols():
    gen = SoftwareManualGenerator(product_name="智慧园区管理平台", version="V1.0")
    gen.generate_full(
        screenshots_meta=[{
            "page_title": "用户管理",
            "caption": "图1 用户管理",
            "image_path": "",
            "elements": ["智慧园区管理平台 V1.0", "👥 用户管理"],
        }],
    )
    joined = "\n".join(p.text for p in gen.doc.paragraphs)
    assert "智慧园区管理平台 面向企事业单位的信息化管理场景" not in joined
    assert "智慧园区管理平台 采用浏览器访问的软件架构" not in joined
    assert "智慧园区管理平台面向企事业单位的信息化管理场景" in joined
    assert "智慧园区管理平台采用浏览器访问的软件架构" in joined
    assert "本功能主要包括：智慧园区管理平台V1.0、用户管理。" in joined


def test_manual_includes_generated_architecture_diagram_when_image_exists():
    with tempfile.TemporaryDirectory() as tmpdir:
        arch_path = os.path.join(tmpdir, "system_architecture.png")
        actual_path = generate_system_architecture_diagram(arch_path, "测试平台")
        assert os.path.exists(actual_path)

        gen = SoftwareManualGenerator(product_name="测试平台", version="V1.0")
        gen.generate_full(arch_diagram_path=actual_path)
        joined = "\n".join(p.text for p in gen.doc.paragraphs)

        assert "（系统架构图待生成后插入）" not in joined
        assert "图1：测试平台系统架构图" in joined


def test_manual_embeds_screenshot_images_when_paths_exist():
    with tempfile.TemporaryDirectory() as tmpdir:
        screenshot_path = os.path.join(tmpdir, "login-page.png")
        arch_path = os.path.join(tmpdir, "system_architecture.png")
        actual_arch = generate_system_architecture_diagram(arch_path, "测试平台")
        actual_screenshot = generate_system_architecture_diagram(screenshot_path, "测试页面")

        gen = SoftwareManualGenerator(product_name="测试平台", version="V1.0")
        gen.generate_full(
            arch_diagram_path=actual_arch,
            screenshots_meta=[
                {
                    "page_title": "登录页",
                    "caption": "图2 登录页",
                    "image_path": actual_screenshot,
                    "elements": ["登录", "用户名", "密码"],
                }
            ],
        )

        output_path = os.path.join(tmpdir, "software_manual.docx")
        gen.save(output_path)
        with zipfile.ZipFile(output_path) as handle:
            media = [name for name in handle.namelist() if name.startswith("word/media/")]

        assert len(media) >= 2


def test_manual_rejects_text_architecture_diagram_fallback():
    with tempfile.TemporaryDirectory() as tmpdir:
        text_path = os.path.join(tmpdir, "system_architecture.txt")
        with open(text_path, "w", encoding="utf-8") as handle:
            handle.write("系统架构图 - 测试平台 V1.0\n页面展示层 -> 业务处理层 -> 数据存储层")

        gen = SoftwareManualGenerator(product_name="测试平台", version="V1.0")
        gen.generate_full(arch_diagram_path=text_path)
        joined = "\n".join(p.text for p in gen.doc.paragraphs)

        assert "（系统架构图待生成后插入）" not in joined
        assert "图1：测试平台系统架构图（文本版）" not in joined
        assert "系统架构图生成失败，请检查图片生成链路。" in joined


def test_manual_text_does_not_include_model_vendor_names():
    gen = SoftwareManualGenerator(product_name="测试平台", version="V1.0")
    gen.generate_runtime_environment()
    gen.generate_system_design()
    joined = "\n".join(p.text for p in gen.doc.paragraphs)

    assert "DeepSeek" not in joined
    assert "OpenAI" not in joined
    assert "Claude" not in joined


def test_manual_profile_can_expand_sections_for_task_specific_content():
    profile = build_task_profile(
        keyword="小红书达人投放",
        product_name="星曜投放协同平台",
        version="V2.3",
        industry="品牌营销",
        prd_summary={"user_roles": ["管理员", "投放专员"]},
    )
    screenshots = [
        {
            "page_title": item["title"],
            "caption": f"图{index + 1} {item['title']}",
            "image_path": "",
            "elements": [item["title"], item["primary_action"]],
        }
        for index, item in enumerate(profile["modules"][:10])
    ]
    gen = SoftwareManualGenerator(product_name="星曜投放协同平台", version="V2.3", profile=profile)
    gen.generate_full(prd_summary={"user_roles": profile["user_roles"]}, screenshots_meta=screenshots)
    joined = "\n".join(p.text for p in gen.doc.paragraphs)
    assert "星曜投放协同平台" in joined
    assert "达人库管理" in joined
    assert "结算与对账" in joined
    assert "后续章节将按页面顺序陈述各项功能用途、处理步骤和页面要点" in joined
    assert "星曜投放协同平台围绕“小红书达人投放”这一任务主题建设" in joined
    assert "典型应用场景" in joined
    assert "数据组织与结果输出说明" in joined
    assert "产品开发与技术实现说明" in joined
    assert "模块实现拆解" in joined
    assert "实施交付与验收说明" in joined
    assert "交互与版式策略" in joined
    assert "页面研发补充说明" in joined
    assert "安全、审计与运维说明" in joined
    assert "FastAPI" in joined
    assert "React" in joined


def test_build_task_profile_generic_modules_keep_own_focus_terms():
    profile = build_task_profile(
        keyword="融合招聘一体化软件",
        product_name="融合招聘一体化软件",
        version="V1.0",
        industry="教育",
        prd_summary={
            "user_roles": ["管理员", "招聘主管", "HR专员"],
            "core_modules": [
                "招聘需求管理",
                "职位与候选人管理",
                "面试与流程管理",
                "人才库与资料中心",
                "招聘数据分析与报表",
            ],
        },
    )

    modules = {module["title"]: module for module in profile["modules"]}
    workflow_module = modules["职位与候选人管理"]
    assets_module = modules["面试与流程管理"]

    assert "职位与候选人管理" in workflow_module["description"]
    assert "招聘需求管理，使用户能够" not in workflow_module["description"]
    assert "候选人姓名、应聘岗位与推进阶段" in workflow_module["steps"][1]
    assert "招聘需求管理相关" not in workflow_module["steps"][1]

    assert "面试与流程管理" in assets_module["description"]
    assert "招聘需求管理，使用户能够" not in assets_module["description"]
    assert "面试环节、安排状态与面试官" in assets_module["steps"][1]
    assert "招聘需求管理相关" not in assets_module["steps"][1]


def test_build_task_profile_recruitment_modules_have_distinct_realistic_rows():
    profile = build_task_profile(
        keyword="融合招聘一体化软件",
        product_name="融合招聘一体化软件",
        version="V1.0",
        industry="教育",
        prd_summary={
            "user_roles": ["管理员", "招聘主管", "HR专员", "面试官"],
            "core_modules": [
                "招聘需求管理",
                "职位与候选人管理",
                "面试与流程管理",
                "人才库与资料中心",
                "招聘数据分析与报表",
            ],
        },
    )

    modules = {module["title"]: module for module in profile["modules"]}

    records = modules["招聘需求管理"]
    workflow = modules["职位与候选人管理"]
    interview = modules["面试与流程管理"]
    talent_pool = modules["人才库与资料中心"]
    reports = modules["招聘数据分析与报表"]

    assert records["table_headers"] == ["需求编号", "需求主题", "用人部门", "招聘阶段", "优先级", "更新时间"]
    assert workflow["table_headers"] == ["候选人编号", "候选人姓名", "应聘岗位", "当前阶段", "来源渠道", "更新时间"]
    assert interview["table_headers"] == ["流程编号", "候选人姓名", "面试环节", "安排状态", "面试官", "更新时间"]
    assert talent_pool["table_headers"] == ["人才编号", "人才方向", "最近进展", "储备等级", "归属顾问", "更新时间"]
    assert reports["table_headers"] == ["报表编号", "报表主题", "统计周期", "负责人", "核心结论", "更新时间"]

    assert records["rows"][0][0].startswith("REQ-")
    assert workflow["rows"][0][0].startswith("CAN-")
    assert interview["rows"][0][0].startswith("INT-")
    assert talent_pool["rows"][0][0].startswith("TAL-")
    assert reports["rows"][0][0].startswith("RPT-")

    assert workflow["rows"][0][2] == "初中数学教研岗"
    assert interview["rows"][0][2] == "试讲评估"
    assert talent_pool["rows"][0][1] == "理科教师储备"
    assert "转化率" in reports["rows"][0][4]

    all_rows = json.dumps(profile["modules"], ensure_ascii=False)
    assert "MOD0-001" not in all_rows
    assert "重点事项" not in all_rows
    assert "张三" not in all_rows
    assert "李四" not in all_rows
    assert "王五" not in all_rows


def test_build_task_profile_recruitment_offer_and_dashboard_modules_avoid_placeholder_text():
    profile = build_task_profile(
        keyword="融合招聘一体化软件",
        product_name="融合招聘一体化软件",
        version="V1.0",
        industry="教育",
        prd_summary={
            "user_roles": ["系统管理员", "招聘专员", "招聘主管", "校领导"],
            "core_modules": [
                "招聘需求管理",
                "候选人库",
                "面试流程管理",
                "录用与入职管理",
                "数据分析看板",
            ],
            "scene": "教育行业的一站式招聘管理平台，涵盖从岗位发布到入职的全流程协同。",
            "industry_scope": "教育行业，包括学校、教育培训机构等单位的招聘业务。",
        },
    )

    modules = {module["title"]: module for module in profile["modules"]}
    offers = modules["录用与入职管理"]
    reports = modules["数据分析看板"]

    assert offers["table_headers"] == ["录用编号", "候选人姓名", "录用岗位", "办理阶段", "责任人", "更新时间"]
    assert offers["rows"][0][0].startswith("OFF-")
    assert offers["description"].startswith("录用与入职管理模块用于统一跟踪 Offer 审批")
    assert "中的日常处理" not in offers["description"]

    assert reports["table_headers"] == ["报表编号", "报表主题", "统计周期", "负责人", "核心结论", "更新时间"]
    assert reports["rows"][0][0].startswith("RPT-")
    assert reports["description"].startswith("数据分析看板模块面向")

    serialized = json.dumps(profile, ensure_ascii=False)
    for banned in [
        "MOD0-001",
        "MOD0-301",
        "重点事项",
        "场景进行设计",
        "中的任务目标",
        "中的日常处理",
        "。中的",
    ]:
        assert banned not in serialized


def test_manual_profile_text_excludes_placeholder_and_broken_phrases_for_recruitment_flow():
    profile = build_task_profile(
        keyword="融合招聘一体化软件",
        product_name="融合招聘一体化软件",
        version="V1.0",
        industry="教育",
        prd_summary={
            "user_roles": ["系统管理员", "招聘专员", "招聘主管", "校领导"],
            "core_modules": [
                "招聘需求管理",
                "候选人库",
                "面试流程管理",
                "录用与入职管理",
                "数据分析看板",
            ],
            "scene": "教育行业的一站式招聘管理平台，涵盖从岗位发布到入职的全流程协同。",
            "industry_scope": "教育行业，包括学校、教育培训机构等单位的招聘业务。",
        },
    )
    screenshots = [
        {
            "page_title": item["title"],
            "caption": f"图{index + 1} {item['title']}",
            "image_path": "",
            "elements": [item["title"], item["primary_action"]],
        }
        for index, item in enumerate(profile["modules"][:5])
    ]
    gen = SoftwareManualGenerator(product_name="融合招聘一体化软件", version="V1.0", profile=profile)
    gen.generate_full(prd_summary={"user_roles": profile["user_roles"]}, screenshots_meta=screenshots)
    joined = "\n".join(p.text for p in gen.doc.paragraphs)

    assert "录用与入职管理" in joined
    assert "数据分析看板" in joined
    for banned in ["MOD0-", "重点事项", "场景进行设计", "中的任务目标", "中的日常处理", "。中的"]:
        assert banned not in joined


def test_manual_renders_only_selected_optional_modules():
    selected = [
        "data_and_output",
        "development_details",
        "security_and_maintenance",
        "version_evolution_and_change_management",
    ]
    profile = {
        "selected_optional_modules": selected,
        "modules": [
            {
                "title": "风险评估中心",
                "primary_action": "发起评估",
                "description": "用于执行评估任务。",
                "table_headers": ["评估编号", "评估对象", "状态", "更新时间"],
                "rows": [["PG-2026-001", "债券组合A", "评估中", "2026-05-18 10:00"]],
            }
        ],
        "user_roles": ["管理员", "风控专员"],
    }
    gen = SoftwareManualGenerator(product_name="测试平台", version="V1.0", profile=profile)
    gen.generate_full(
        prd_summary={"user_roles": profile["user_roles"]},
        screenshots_meta=[{"page_title": "风险评估中心", "caption": "图1 风险评估中心", "image_path": "", "elements": ["风险评估中心", "发起评估"]}],
    )
    joined = "\n".join(p.text for p in gen.doc.paragraphs)
    assert "数据组织与结果输出说明" in joined
    assert "产品开发与技术实现说明" in joined
    assert "安全、审计与运维说明" in joined
    assert "版本演进与变更管理说明" in joined
    assert "核心业务对象详解" not in joined
    assert "实施交付与验收说明" not in joined
    assert "附录与补充说明" not in joined


def test_application_form_can_generate_required_fields():
    profile = build_task_profile(
        keyword="小红书达人投放",
        product_name="星曜投放协同平台",
        version="V2.3",
        industry="品牌营销",
    )
    gen = ApplicationFormGenerator(product_name="星曜投放协同平台", version="V2.3")
    gen.generate(profile)
    joined = "\n".join(p.text for p in gen.doc.paragraphs)
    table_text = "\n".join(cell.text for table in gen.doc.tables for row in table.rows for cell in row.cells)
    assert "软件著作权申请表" in joined
    assert "软件名称" in table_text
    assert "软件的主要功能" in table_text
    assert "星曜投放协同平台" in table_text
    assert "以下内容根据当前任务产物自动整理" not in joined
    assert "说明：本申请表为系统自动生成的填写稿" not in joined


def test_application_form_main_functions_is_padded_to_minimum_length():
    gen = ApplicationFormGenerator(product_name="测试平台", version="V1.0")
    gen.generate({
        "product_name": "测试平台",
        "version": "V1.0",
        "main_functions": "支持登录、查询和导出。",
    })
    table_text = "\n".join(cell.text for table in gen.doc.tables for row in table.rows for cell in row.cells)
    assert "软件的主要功能" in table_text
    main_functions_text = next(
        row.cells[1].text
        for table in gen.doc.tables
        for row in table.rows
        if row.cells[0].text == "软件的主要功能"
    )
    assert len(main_functions_text) >= 500
    assert main_functions_text.count("系统还支持统一登录、信息检索、状态跟踪、结果留痕、导出归档与权限控制等能力") == 1
    assert "在交付层面，系统可输出说明书、申请表、源码文档和截图材料" in main_functions_text
    assert "补充说明" not in main_functions_text


def test_application_form_dedupes_repeated_main_function_sentences():
    gen = ApplicationFormGenerator(product_name="测试平台", version="V1.0")
    gen.generate({
        "product_name": "测试平台",
        "version": "V1.0",
        "main_functions": (
            "系统支持统一登录、统一登录。"
            "系统可输出说明书、申请表和源码文档。"
            "系统可输出说明书、申请表和源码文档。"
        ),
    })
    main_functions_text = next(
        row.cells[1].text
        for table in gen.doc.tables
        for row in table.rows
        if row.cells[0].text == "软件的主要功能"
    )
    assert main_functions_text.count("系统支持统一登录、统一登录。") == 1
    assert main_functions_text.count("系统可输出说明书、申请表和源码文档。") == 1


def test_manual_data_dictionary_notes_use_distinct_field_explanations():
    profile = {
        "modules": [
            {
                "title": "供应商与承运商协同门户",
                "description": "用于处理供应商协同、承运计划和运输反馈。",
                "primary_action": "发起协同处理",
                "table_headers": ["供应商编号", "供应商名称", "协同状态", "更新时间", "处理说明"],
                "highlights": ["支持供应商协同", "支持运输反馈"],
            }
        ]
    }
    gen = SoftwareManualGenerator(product_name="测试平台", version="V1.0", profile=profile)
    gen.generate_function_structure()
    joined = "\n".join(p.text for p in gen.doc.paragraphs)
    assert "字段“供应商编号”作为供应商与承运商协同门户的唯一定位标识" in joined
    assert "字段“协同状态”用于描述供应商与承运商协同门户当前所处的处理阶段或状态" in joined
    assert "字段“更新时间”用于记录供应商与承运商协同门户的关键时间节点" in joined
    assert "既服务于页面检索和列表展示，也用于说明书、导出文件和后续归档中的统一口径" not in joined


def test_manual_compacts_filtered_variant_pages():
    gen = SoftwareManualGenerator(product_name="测试平台", version="V1.0")
    gen.generate_full(
        screenshots_meta=[
            {
                "page_title": "用户管理",
                "caption": "图1 用户管理",
                "route": "/users",
                "image_path": "",
                "elements": ["用户管理", "搜索", "导出"],
            },
            {
                "page_title": "用户管理筛选结果",
                "caption": "图2 用户管理筛选结果",
                "route": "/users",
                "image_path": "",
                "elements": ["用户管理", "搜索", "导出", "筛选结果"],
            },
        ],
    )
    joined = "\n".join(p.text for p in gen.doc.paragraphs)
    assert "用户管理筛选结果" in joined
    assert joined.count("\n详细操作说明\n") == 1
    assert "该功能主要涵盖：用户管理、搜索、导出、筛选结果。" in joined
    assert "该截图展示了" not in joined
    assert "截图中重点可见" not in joined


def test_task_profile_builds_more_than_ten_screenshot_scenarios():
    profile = build_task_profile(
        keyword="小红书达人投放",
        product_name="星曜投放协同平台",
        version="V2.3",
        industry="品牌营销",
    )
    assert len(profile["screenshot_scenarios"]) >= 10
    assert any(item["title"] == "达人库管理" for item in profile["modules"])


def test_task_profile_uses_media_preset_for_short_drama_products():
    profile = build_task_profile(
        keyword="短剧平台",
        product_name="星映短剧运营平台",
        version="V1.0",
        industry="内容平台",
    )
    assert profile["preset_key"] == "media"
    assert profile["modules"][0]["title"] == "剧集管理"
    assert profile["modules"][0]["route"] == "/series"
    assert any(item["title"] == "评论管理" for item in profile["modules"])


def test_task_profile_infers_desktop_client_from_title():
    profile = build_task_profile(
        keyword="量化交易终端",
        product_name="星河量化交易客户端",
        version="V1.0",
        industry="证券投资",
    )
    assert profile["app_type"] == "desktop_client"
    assert "桌面客户端环境" in profile["runtime_platform"]


def test_plan_seed_preserves_app_type_hint():
    seed = build_plan_seed(
        keyword="设备巡检工作站",
        product_name="园区设备巡检客户端",
        industry="园区运维",
    )
    assert seed["app_type"] == "desktop_client"
    assert seed["visual_profile"]["name"]


def test_task_profile_accepts_product_type_hint_alias():
    profile = build_task_profile(
        keyword="综合值守平台",
        product_name="园区综合值守软件",
        version="V1.0",
        industry="园区运维",
        prd_summary={"product_type": "desktop_client"},
    )
    assert profile["app_type"] == "desktop_client"


def test_task_profile_prefers_content_route_hints_over_old_preset_routes():
    profile = build_task_profile(
        keyword="短剧平台",
        product_name="短剧平台",
        version="V1.0",
        industry="内容平台",
        prd_summary={
            "core_modules": ["短剧内容管理", "创作者与演员管理", "广告投放管理", "播放数据统计"],
            "required_pages": ["/login", "/dashboard", "/series", "/actors", "/campaigns", "/statistics"],
            "user_roles": ["超级管理员", "内容审核员", "运营专员"],
        },
    )
    route_by_title = {module["title"]: module["route"] for module in profile["modules"]}
    assert route_by_title["短剧内容管理"] == "/series"
    assert route_by_title["创作者与演员管理"] == "/actors"
    assert route_by_title["广告投放管理"] == "/campaigns"
    assert route_by_title["播放数据统计"] == "/statistics"


def test_task_profile_prefers_required_pages_over_title_route_hints():
    profile = build_task_profile(
        keyword="跨境冷链履约异常协同平台 V1.0",
        product_name="跨境冷链履约异常协同平台 V1.0",
        version="V1.0",
        industry="冷链物流",
        prd_summary={
            "core_modules": ["温控数据看板", "统计与报告", "告警处理台", "系统设置"],
            "required_pages": ["/login", "/dashboard", "/collaboration", "/reports", "/alerts", "/settings"],
            "user_roles": ["管理员", "调度主管", "履约专员"],
        },
    )

    route_by_title = {module["title"]: module["route"] for module in profile["modules"]}

    assert route_by_title["温控数据看板"] == "/collaboration"
    assert route_by_title["统计与报告"] == "/reports"
    assert route_by_title["告警处理台"] == "/alerts"
    assert route_by_title["系统设置"] == "/settings"
    assert len({module["route"] for module in profile["modules"]}) == len(profile["modules"])


def test_media_plan_seed_is_stable_for_same_product():
    first = build_plan_seed(keyword="短剧平台", product_name="短剧平台", industry="内容平台")
    second = build_plan_seed(keyword="短剧平台", product_name="短剧平台", industry="内容平台")
    assert first["preset_key"] == "media"
    assert first["core_modules"] == second["core_modules"]
    assert first["required_pages"] == second["required_pages"]
    assert len(set(first["required_pages"][2:])) == len(first["required_pages"][2:])


def test_task_profile_pads_screenshot_scenarios_when_module_count_is_small():
    profile = build_task_profile(
        keyword="AI股票量化投资平台",
        product_name="星河量化决策平台",
        version="V1.0",
        industry="证券投资",
        prd_summary={
            "user_roles": ["管理员", "策略研究员", "交易员"],
            "core_modules": ["用户管理", "策略管理", "交易管理", "风险控制", "系统配置"],
            "required_pages": ["/login", "/dashboard", "/users", "/strategies", "/trades", "/risk", "/settings"],
        },
    )
    assert len(profile["modules"]) == 5
    assert len(profile["screenshot_scenarios"]) >= 10
    assert any(item["id"].startswith("users-filtered-") for item in profile["screenshot_scenarios"])
    assert any(item["title"].endswith("筛选结果") for item in profile["screenshot_scenarios"])
    filtered = next(item for item in profile["screenshot_scenarios"] if item["id"].startswith("users-filtered-"))
    assert filtered["actions"][1]["action"] == "fill_input"
    assert filtered["actions"][1]["target"] == "搜索"
    assert filtered["actions"][1]["optional"] is True


def test_task_profile_rebuilds_content_for_new_title_and_modules():
    first = build_task_profile(
        keyword="AI股票量化投资平台",
        product_name="星河量化决策平台",
        version="V1.0",
        industry="证券投资",
        prd_summary={
            "user_roles": ["管理员", "策略研究员", "交易员"],
            "core_modules": ["策略因子管理", "组合回测中心", "交易执行监控", "风控预警中心", "系统设置"],
            "required_pages": ["/login", "/dashboard", "/factors", "/backtests", "/trades", "/risks", "/settings"],
        },
    )
    second = build_task_profile(
        keyword="智慧园区能耗管理平台",
        product_name="云枢能耗协同平台",
        version="V1.0",
        industry="园区运维",
        prd_summary={
            "user_roles": ["管理员", "运维主管", "设备专员"],
            "core_modules": ["能耗总览", "设备巡检中心", "告警处理台", "报表分析中心", "系统设置"],
            "required_pages": ["/login", "/dashboard", "/energy", "/inspection", "/alerts", "/reports", "/settings"],
        },
    )

    assert first["development_background"] != second["development_background"]
    assert first["main_functions"] != second["main_functions"]
    assert [item["title"] for item in first["modules"][:4]] == ["策略因子管理", "组合回测中心", "交易执行监控", "风控预警中心"]
    assert [item["title"] for item in second["modules"][:4]] == ["能耗总览", "设备巡检中心", "告警处理台", "报表分析中心"]
    assert "AI股票量化投资平台" in first["development_purpose"]
    assert "智慧园区能耗管理平台" in second["development_purpose"]
    assert "策略因子管理" in first["main_functions"]
    assert "能耗总览" in second["main_functions"]
    assert "量化策略研究" in first["scene"]
    assert "AI股票量化投资平台在AI股票量化投资平台相关的" not in first["technical_features"]


def test_supply_chain_modules_use_distinct_business_copy():
    profile = build_task_profile(
        keyword="供应链核心企业金融数据分析与监控平台 V2.0",
        product_name="供应链核心企业金融数据分析与监控平台 V2.0",
        version="V2.0",
        industry="供应链协同",
        prd_summary={
            "core_modules": ["采购管理", "库存管理", "供应商管理", "订单履约中心"],
            "required_pages": ["/login", "/dashboard", "/purchases", "/inventory", "/suppliers", "/orders"],
            "user_roles": ["管理员", "采购经理", "仓储主管", "供应商专员"],
        },
    )
    modules = {item["title"]: item for item in profile["modules"]}
    assert modules["采购管理"]["table_headers"][0] == "采购单号"
    assert modules["库存管理"]["table_headers"][0] == "批次编号"
    assert modules["供应商管理"]["table_headers"][0] == "供应商编号"
    assert modules["订单履约中心"]["table_headers"][0] == "履约单号"
    assert "到货排期" in modules["采购管理"]["description"]
    assert "库存批次" in modules["库存管理"]["description"]
    assert "供方资质" in modules["供应商管理"]["description"]
    assert "履约阶段" in modules["订单履约中心"]["description"]


def test_task_profile_distinguishes_logistics_and_supply_chain_finance_presets():
    logistics = build_task_profile(
        keyword="物流调度管理后台",
        product_name="物流调度管理后台",
        version="V1.0",
        industry="物流运输",
    )
    finance = build_task_profile(
        keyword="供应链核心企业金融数据分析与监控平台 V2.0",
        product_name="供应链核心企业金融数据分析与监控平台 V2.0",
        version="V2.0",
        industry="供应链金融",
    )

    assert logistics["preset_key"] == "logistics"
    assert finance["preset_key"] == "supply_chain_finance"
    assert [item["title"] for item in logistics["modules"][:4]] == [
        "运单调度中心",
        "车辆与司机协同",
        "线路监控台",
        "仓配协同台",
    ]
    assert [item["title"] for item in finance["modules"][:4]] == [
        "授信主体管理",
        "融资申请分析",
        "资金敞口监控",
        "贸易背景核验",
    ]
    assert logistics["project_dna"]["architecture_style"] == "dispatch_flow"
    assert finance["project_dna"]["architecture_style"] == "risk_grid"


def test_task_profile_distinguishes_power_dispatch_from_logistics():
    power = build_task_profile(
        keyword="电力调度平台",
        product_name="电力调度平台",
        version="V1.0",
        industry="电网调度",
    )

    assert power["preset_key"] == "power_dispatch"
    assert [item["title"] for item in power["modules"][:5]] == [
        "电网运行总览",
        "负荷调度中心",
        "发电计划协同",
        "输变线路监测",
        "检修工作票中心",
    ]
    assert "电网运行监视" in power["scene"]
    assert power["project_dna"]["architecture_style"] == "control_tower"
    joined = json.dumps(power, ensure_ascii=False)
    assert "运单调度中心" not in joined
    assert "仓配协同台" not in joined
    assert "签收回单中心" not in joined


def test_task_profile_prefers_prd_summary_semantics_over_platform_defaults():
    profile = build_task_profile(
        keyword="电力调度平台",
        product_name="电力调度平台",
        version="V1.0",
        industry="电网调度",
        notes="重点关注调度令、检修工作票和停复电联动",
        prd_summary={
            "core_modules": ["主网态势总览", "调度指令中心", "停复电协同", "检修工作票台"],
            "required_pages": ["/login", "/dashboard", "/grid", "/dispatch-orders", "/restoration", "/tickets"],
            "user_roles": ["值班长", "调度员", "检修协调员"],
            "scene": "主网运行监视、调度指令下发与停复电协同",
            "industry_scope": "电网调度与检修协同",
            "core_entities": ["调度令", "工作票", "停复电任务"],
            "raw_user_request": {
                "keyword": "电力调度平台",
                "product_name": "电力调度平台",
                "industry": "电网调度",
                "notes": "重点关注调度令、检修工作票和停复电联动",
            },
        },
    )

    assert [item["title"] for item in profile["modules"][:4]] == ["主网态势总览", "调度指令中心", "停复电协同", "检修工作票台"]
    assert profile["scene"] == "主网运行监视、调度指令下发与停复电协同"
    assert profile["industry_scope"] == "电网调度与检修协同"
    assert profile["core_entities"] == ["调度令", "工作票", "停复电任务"]
    assert profile["raw_user_request"]["notes"] == "重点关注调度令、检修工作票和停复电联动"
    assert profile["project_dna"]["source_of_truth"] == "raw_user_request"


def test_task_profile_visual_profile_uses_non_sidebar_blueprint():
    profile = build_task_profile(
        keyword="物流调度管理后台",
        product_name="物流调度管理后台",
        version="V1.0",
        industry="物流运输",
    )
    seed = build_plan_seed(
        keyword="物流调度管理后台",
        product_name="物流调度管理后台",
        industry="物流运输",
    )

    for payload in (profile, seed):
        assert payload["experience_blueprint"]["navigation_variant"] in {"top_tabs", "indexed", "sectioned"}
        assert "sidebar" not in payload["visual_profile"]["name"]
        expected_treatment = {
            "top_tabs": "top_tabs",
            "indexed": "indexed_topbar",
            "sectioned": "sectioned_header",
        }[payload["experience_blueprint"]["navigation_variant"]]
        assert payload["visual_profile"]["chrome_treatment"] == expected_treatment
        assert any(token in payload["visual_profile"]["layout_signal"] for token in ("顶部", "分段", "索引"))
        assert any(
            token in payload["visual_profile"]["layout_signal"]
            for token in ("避免左侧竖栏后台", "避免左侧栏", "避免统一后台", "避免复用单一后台骨架")
        )


def test_architecture_diagram_changes_with_project_profile():
    logistics = build_task_profile(
        keyword="物流调度管理后台",
        product_name="物流调度管理后台",
        version="V1.0",
        industry="物流运输",
    )
    finance = build_task_profile(
        keyword="供应链核心企业金融数据分析与监控平台 V2.0",
        product_name="供应链核心企业金融数据分析与监控平台 V2.0",
        version="V2.0",
        industry="供应链金融",
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        logistics_path = os.path.join(tmpdir, "logistics.png")
        finance_path = os.path.join(tmpdir, "finance.png")
        generate_system_architecture_diagram(logistics_path, logistics["product_name"], profile=logistics)
        generate_system_architecture_diagram(finance_path, finance["product_name"], profile=finance)

        assert os.path.exists(logistics_path)
        assert os.path.exists(finance_path)
        assert open(logistics_path, "rb").read() != open(finance_path, "rb").read()


def test_task_profile_design_seed_produces_distinct_visual_profiles_for_similar_projects():
    cold_chain = build_task_profile(
        keyword="冷链履约异常协同平台",
        product_name="冷链履约异常协同平台",
        version="V1.0",
        industry="冷链物流",
    )
    dispatch = build_task_profile(
        keyword="冷链在途调度联控平台",
        product_name="冷链在途调度联控平台",
        version="V1.0",
        industry="冷链物流",
    )

    assert cold_chain["experience_blueprint"]["shell_layout_hint"] != dispatch["experience_blueprint"]["shell_layout_hint"]
    assert cold_chain["visual_profile"]["name"] != dispatch["visual_profile"]["name"]
    assert (
        cold_chain["visual_profile"]["nav_background"],
        cold_chain["visual_profile"]["accent"],
    ) != (
        dispatch["visual_profile"]["nav_background"],
        dispatch["visual_profile"]["accent"],
    )


def test_task_profile_avoids_duplicate_topic_phrasing_when_keyword_equals_product_name():
    profile = build_task_profile(
        keyword="AI股票量化投资平台",
        product_name="AI股票量化投资平台",
        version="V1.0",
        prd_summary={
            "user_roles": ["超级管理员", "策略分析师", "数据管理员"],
            "core_modules": ["概览仪表盘", "策略管理", "数据源管理", "回测管理", "用户与权限管理"],
            "required_pages": ["/login", "/dashboard", "/overview", "/strategies", "/datasets", "/backtests", "/users"],
        },
    )
    assert profile["topic_label"] == "AI股票量化投资平台"
    assert "量化策略研究" in profile["scene"]
    assert "AI股票量化投资平台在AI股票量化投资平台相关的" not in profile["technical_features"]
    assert "围绕“AI股票量化投资平台”对应的" in profile["technical_features"]
    assert "统一导航、标准表格、状态标签、结果导出和截图留痕" not in profile["technical_features"]
    assert "避免回落到固定后台套板" in profile["technical_features"]
    assert "不得把所有任务压成同一套顶栏+表格后台骨架" in profile["differentiation_hint"]


def test_codebook_empty_workspace():
    gen = SourceCodeBookGenerator(product_name="TestApp", version="V1.0")
    with tempfile.TemporaryDirectory() as tmpdir:
        code_index = {
            "include_globs": ["**/*.py"],
            "exclude_globs": [],
            "preferred_order": [],
        }
        gen.generate(code_index, tmpdir)
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            gen.save(f.name)
            assert os.path.getsize(f.name) > 0
            os.unlink(f.name)


def test_codebook_pagination():
    gen = SourceCodeBookGenerator(product_name="TestApp", version="V1.0")
    lines = ["line " + str(i) for i in range(200)]
    pages = gen._paginate(lines)
    assert len(pages) > 0
    for page in pages:
        assert len(page) <= gen.LINES_PER_PAGE


def test_codebook_generate_full_document():
    gen = SourceCodeBookGenerator(product_name="TestApp", version="V1.0")
    with tempfile.TemporaryDirectory() as tmpdir:
        code_index = {
            "include_globs": ["**/*.py"],
            "exclude_globs": [],
            "preferred_order": [],
        }
        sample = os.path.join(tmpdir, "a.py")
        with open(sample, "w", encoding="utf-8") as handle:
            for i in range(4000):
                handle.write(f"print({i})\n")
        gen.generate(code_index, tmpdir)
        assert len(gen.doc.paragraphs) > 0


def test_codebook_sanitizes_xml_incompatible_control_chars():
    gen = SourceCodeBookGenerator(product_name="TestApp", version="V1.0")
    with tempfile.TemporaryDirectory() as tmpdir:
        code_index = {
            "include_globs": ["**/*.py"],
            "exclude_globs": [],
            "preferred_order": [],
        }
        sample = os.path.join(tmpdir, "bad.py")
        with open(sample, "w", encoding="utf-8") as handle:
            handle.write("print('ok')\n")
            handle.write("bad = 'A\\x00B\\x01C'\n")
        gen.generate(code_index, tmpdir)
        joined = "\n".join(p.text for p in gen.doc.paragraphs)
        assert "A\uFFFDB\uFFFDC" in joined


def test_codebook_skips_binary_files():
    gen = SourceCodeBookGenerator(product_name="TestApp", version="V1.0")
    with tempfile.TemporaryDirectory() as tmpdir:
        code_index = {
            "include_globs": ["**/*"],
            "exclude_globs": [],
            "preferred_order": [],
        }
        binary_file = os.path.join(tmpdir, "IPRightCJK.ttf")
        with open(binary_file, "wb") as handle:
            handle.write(b"\x00\x01\x02binary-font")
        gen.generate(code_index, tmpdir)
        joined = "\n".join(p.text for p in gen.doc.paragraphs)
        assert "[跳过二进制文件: IPRightCJK.ttf]" in joined


def test_manual_markdown_validation_detects_missing_required_modules():
    from app.services.document.manual_compose import validate_required_manual_modules

    ok, missing = validate_required_manual_modules("## 引言\n内容")
    assert not ok
    assert "软件概述" in missing


def test_manual_markdown_renderer_supports_screenshot_markers():
    from app.services.document.manual_compose import render_manual_markdown_to_docx
    from PIL import Image

    with tempfile.TemporaryDirectory() as tmpdir:
        image_path = os.path.join(tmpdir, "page.png")
        Image.new("RGB", (20, 20), "white").save(image_path)
        arch_path = os.path.join(tmpdir, "arch.png")
        generate_system_architecture_diagram(arch_path, "测试平台")

        markdown = "\n".join([
            "# 测试平台",
            "## 文档说明",
            "说明正文。",
            "## 引言",
            "引言正文。",
            "## 开发设计 / 系统设计",
            "[[SCREENSHOT:ARCH]]",
            "## 软件概述",
            "概述正文。",
            "## 开发运行环境 / 软件适配环境",
            "环境正文。",
            "## 功能结构说明",
            "功能正文。",
            "## 角色权限说明",
            "角色正文。",
            "## 业务流程说明",
            "流程正文。",
            "## 软件使用说明",
            "### 登录页",
            "[[SCREENSHOT:登录页]]",
            "页面说明。",
            "## 技术特点说明",
            "技术正文。",
        ])
        doc = render_manual_markdown_to_docx(
            markdown=markdown,
            product_name="测试平台",
            version="V1.0",
            screenshots_meta=[{"page_title": "登录页", "caption": "图1 登录页", "image_path": image_path}],
            arch_diagram_path=arch_path,
        )
        joined = "\n".join(p.text for p in doc.paragraphs)
        assert "文档说明" in joined
        assert "登录页" in joined
        assert "图1 登录页" in joined


def test_fallback_manual_markdown_varies_with_seed():
    from app.services.document.manual_compose import build_fallback_manual_markdown

    profile = build_task_profile(
        keyword="物流调度管理后台",
        product_name="物流调度管理后台",
        version="V1.0",
        industry="物流运输",
    )
    first = build_fallback_manual_markdown(
        product_name="物流调度管理后台",
        version="V1.0",
        profile=profile,
        prd_summary={},
        screenshots_meta=[{"page_title": "登录页", "route": "/login"}],
        variation_seed="aaaaaaaaaaaaaaaa",
    )
    second = build_fallback_manual_markdown(
        product_name="物流调度管理后台",
        version="V1.0",
        profile=profile,
        prd_summary={},
        screenshots_meta=[{"page_title": "登录页", "route": "/login"}],
        variation_seed="bbbbbbbbbbbbbbbb",
    )
    assert first != second


def test_arrow_endpoints_land_on_box_edges_not_centers():
    from app.services.document.diagrams import arrow_points_between_boxes

    left = (100, 120, 360, 280)
    right = (520, 120, 780, 280)
    x1, y1, x2, y2 = arrow_points_between_boxes(left, right)
    left_cx, left_cy = (left[0] + left[2]) // 2, (left[1] + left[3]) // 2
    right_cx, right_cy = (right[0] + right[2]) // 2, (right[1] + right[3]) // 2
    assert (x1, y1) != (left_cx, left_cy)
    assert (x2, y2) != (right_cx, right_cy)

    def _on_rect_edge(box, x, y):
        x1b, y1b, x2b, y2b = box
        on_vertical = x in (x1b, x2b) and y1b <= y <= y2b
        on_horizontal = y in (y1b, y2b) and x1b <= x <= x2b
        return on_vertical or on_horizontal

    assert _on_rect_edge(left, x1, y1)
    assert _on_rect_edge(right, x2, y2)


def test_architecture_diagram_accepts_llm_spec():
    from app.services.document.diagrams import generate_system_architecture_diagram

    spec = {
        "title": "测试平台系统架构图",
        "caption": "图1：测试平台采用模块化协同架构。",
        "nodes": [
            {"title": "访问入口", "body": "登录与首页导航", "x": 8, "y": 18, "w": 26, "h": 16, "kind": "primary"},
            {"title": "业务处理层", "body": "模块协同与状态流转", "x": 38, "y": 18, "w": 26, "h": 16, "kind": "secondary"},
            {"title": "数据沉淀层", "body": "对象口径与结果留痕", "x": 68, "y": 18, "w": 26, "h": 16, "kind": "accent"},
            {"title": "交付支撑层", "body": "截图与文档导出", "x": 24, "y": 52, "w": 52, "h": 18, "kind": "accent"},
        ],
        "arrows": [{"from_index": 0, "to_index": 1}, {"from_index": 1, "to_index": 2}, {"from_index": 2, "to_index": 3}],
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = os.path.join(tmpdir, "arch.png")
        generate_system_architecture_diagram(output_path, "测试平台", profile={}, diagram_spec=spec)
        assert os.path.exists(output_path)
        assert os.path.getsize(output_path) > 0
