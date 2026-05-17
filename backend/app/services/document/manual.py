from __future__ import annotations

import os
import re
import unicodedata

from docx import Document

from app.services.document.base import WordTemplateBase


class SoftwareManualGenerator(WordTemplateBase):
    def __init__(
        self,
        product_name: str,
        version: str,
        profile: dict | None = None,
        doc: Document | None = None,
    ):
        super().__init__(doc)
        self.product_name = product_name
        self.version = version
        self.profile = profile or {}

    def _strip_unsupported_symbols(self, text: str) -> str:
        chars: list[str] = []
        for ch in text:
            if ch in {"\u200b", "\u200c", "\u200d", "\ufeff", "\ufe0f"}:
                continue
            if unicodedata.category(ch) == "So":
                continue
            chars.append(ch)
        return "".join(chars)

    def _normalize_sentence_spacing(self, text: str) -> str:
        text = text.replace("\xa0", " ")
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", text)
        text = re.sub(r"([\u4e00-\u9fff])\s+(V\d)", r"\1\2", text)
        text = re.sub(r"(V\d(?:\.\d+)*)\s+([\u4e00-\u9fff])", r"\1\2", text)
        text = re.sub(r"([，。；：！？、】【（）])\s+([\u4e00-\u9fff])", r"\1\2", text)
        text = re.sub(r"([\u4e00-\u9fff])\s+([，。；：！？、】【（）])", r"\1\2", text)
        return text

    def _sanitize_doc_text(self, text: str) -> str:
        return self._normalize_sentence_spacing(self._strip_unsupported_symbols(text))

    def _sanitize_ui_elements(self, elements: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in elements:
            normalized = self._sanitize_doc_text(item).strip(" 、")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            cleaned.append(normalized)
        return cleaned

    def _module_profiles(self) -> list[dict]:
        return list(self.profile.get("modules") or [])

    def _module_titles(self) -> list[str]:
        return [module.get("title", "") for module in self._module_profiles() if module.get("title")]

    def _profile_text(self, key: str, fallback: str) -> str:
        return self._sanitize_doc_text(self.profile.get(key, fallback))

    def _profile_list(self, key: str, fallback: list[str]) -> list[str]:
        values = self.profile.get(key)
        if isinstance(values, list):
            return [self._sanitize_doc_text(str(item)) for item in values if str(item).strip()]
        return fallback

    def _module_steps(self, module: dict) -> list[str]:
        if module.get("steps"):
            return [self._sanitize_doc_text(str(step)) for step in module["steps"] if str(step).strip()]
        title = module.get("title", "当前模块")
        action = module.get("primary_action", f"处理{title}")
        return [
            f"进入{title}页面后先确认标题区、筛选区和主操作按钮，核对当前处理对象与业务范围。",
            f"通过搜索条件、列表记录和状态标签定位目标事项，并按需执行“{action}”等主操作。",
            f"完成处理后复核页面反馈、更新时间和相关记录，确保结果可追踪、可导出、可沉淀。",
        ]

    def _module_field_summary(self, module: dict) -> str:
        headers = [str(item).strip() for item in module.get("table_headers", []) if str(item).strip()]
        filter_placeholder = self._sanitize_doc_text(str(module.get("filter_placeholder", "")).strip())
        if not headers:
            return "页面通常包含标题区、筛选区、结果列表、状态标签与操作反馈区域。"
        header_text = "页面重点字段包括：" + "、".join(headers[:8]) + "。"
        if filter_placeholder:
            header_text += f" 检索区通常支持按“{filter_placeholder}”快速定位目标记录。"
        return self._sanitize_doc_text(header_text)

    def _module_business_value(self, module: dict) -> str:
        title = module.get("title", "当前模块")
        description = module.get("description", "")
        if description:
            return self._sanitize_doc_text(
                f"{description}该模块将信息采集、处理推进、结果复核与留痕沉淀集中在同一页面内，便于形成清晰稳定的业务闭环。"
            )
        return self._sanitize_doc_text(
            f"{title}模块用于承接当前任务中的关键业务步骤，能够把分散信息统一到标准页面中展示，并支持过程留痕与结果输出。"
        )

    def _role_work_scope(self, role: str, modules: list[str]) -> str:
        module_phrase = "、".join(modules[:4]) if modules else "首页概览、业务处理、结果查询、材料导出"
        return self._sanitize_doc_text(
            f"{role}在日常工作中主要围绕{module_phrase}开展查询、录入、复核、统计或配置操作，并根据权限查看相应的业务结果与过程记录。"
        )

    def _profile_focus_list(self, key: str, fallback: list[str]) -> list[str]:
        values = self.profile.get(key)
        if isinstance(values, list):
            return [self._sanitize_doc_text(str(item)) for item in values if str(item).strip()]
        return [self._sanitize_doc_text(item) for item in fallback]

    def _role_profiles(self, prd_summary: dict | None = None) -> list[str]:
        return (
            list(self.profile.get("user_roles") or [])
            or list((prd_summary or {}).get("user_roles") or [])
            or ["管理员", "业务主管", "运营专员"]
        )

    def generate_cover(self) -> None:
        for _ in range(4):
            self.doc.add_paragraph()
        self.add_title(self.product_name, level=0)
        p = self.doc.add_paragraph()
        p.alignment = 1
        run = p.add_run(f"版本号: {self.version}")
        self._apply_run_font(run, font_name="宋体", font_size=14)
        p2 = self.doc.add_paragraph()
        p2.alignment = 1
        run2 = p2.add_run("软件说明书 / 操作手册")
        self._apply_run_font(run2, font_name="宋体", font_size=14)
        self.doc.add_page_break()

    def generate_document_info(self, screenshots_meta: list[dict]) -> None:
        self.add_title("文档说明", level=1)
        self.add_paragraph(f"本文档为{self.product_name}{self.version}的软件说明书/操作手册。")
        self.add_paragraph(
            self._profile_text(
                "overview_version_summary",
                "文档内容覆盖引言、开发设计/系统设计、开发运行环境、功能结构说明、软件使用说明和技术特点说明。",
            )
        )

    def generate_introduction(self) -> None:
        self.add_title("引言", level=1)
        self.add_title("开发背景", level=2)
        self.add_paragraph(
            self._profile_text(
                "development_background",
                f"{self.product_name}面向企事业单位的信息化管理场景，用于解决业务资料分散、流程执行依赖人工协调以及统计结果回收不及时等问题。",
            )
        )
        self.add_title("开发目的", level=2)
        self.add_paragraph(
            self._profile_text(
                "development_purpose",
                "本软件通过统一入口、结构化页面和标准化模块，帮助使用单位建立清晰、稳定且可追踪的业务管理流程，提升数据可见性和协同效率。",
            )
        )
        self.add_title("适用领域", level=2)
        self.add_paragraph(self.profile.get("industry_scope", "通用业务管理、行业信息化管理和后台协同场景。"))
        self.add_title("适用对象", level=2)
        self.add_paragraph(
            f"本文档适用于{'、'.join(self._role_profiles())}等角色，用于指导页面使用、业务处理和材料整理。"
        )

    def generate_overview(self, prd_summary: dict | None = None, modules: list[str] | None = None) -> None:
        self.add_title("软件概述", level=1)
        self.add_title("产品简介", level=2)
        module_items = modules or self._module_titles() or (prd_summary or {}).get("core_modules") or []
        self.add_paragraph(
            self._profile_text(
                "overview_product_intro",
                f"{self.product_name} 是一套围绕{self.profile.get('scene', '业务管理与流程协同')}构建的 Web 软件系统，主要覆盖{'、'.join(module_items[:6]) if module_items else '统一登录、首页概览和业务处理'}等业务能力。",
            )
        )
        self.add_paragraph(
            self._profile_text(
                "product_positioning",
                f"{self.product_name}围绕{self.profile.get('topic_label', self.product_name)}这一主题构建，强调任务专属页面结构、行业化模块命名和与业务场景相匹配的操作重点，确保不同产品形成清晰可辨的内容侧重点。",
            )
        )
        self.add_paragraph(
            self._profile_text(
                "overview_version_summary",
                f"当前软件版本为{self.version}。系统强调页面分区明确、信息展示直观和操作路径稳定，并根据当前任务标题、关键词、行业和模块结构生成对应的页面内容与说明书正文。",
            )
        )
        self.add_paragraph(
            self._profile_text(
                "design_focus",
                f"本软件在内容组织上重点突出{self.profile.get('scene', '业务协同')}场景中的关键模块、核心数据视图、角色分工和结果输出要求，使说明书能够准确体现当前软件产品的业务特征。",
            )
        )
        self.add_title("软件主要功能", level=2)
        for mod in module_items:
            self.add_paragraph(f"- {mod}")
        self.add_title("使用角色", level=2)
        for role in self._role_profiles(prd_summary):
            self.add_paragraph(f"- {role}")

    def generate_runtime_environment(self) -> None:
        self.add_title("开发运行环境 / 软件适配环境", level=1)
        self.add_title("开发硬件环境", level=2)
        self.add_paragraph(self.profile.get("hardware_environment", "CPU: 2核及以上；内存: 8GB及以上；磁盘: 100GB及以上。"))
        self.add_title("运行硬件环境", level=2)
        self.add_paragraph(self.profile.get("runtime_hardware_environment", "CPU: 2核及以上；内存: 4GB及以上；磁盘: 50GB及以上。"))
        self.add_title("软件环境", level=2)
        self.add_paragraph(f"开发操作系统: {self.profile.get('development_os', 'Linux / Windows / macOS')}")
        self.add_paragraph(f"运行平台/操作系统: {self.profile.get('runtime_platform', 'Linux 服务器 + 主流浏览器环境')}")
        self.add_paragraph(f"运行支撑环境/支持软件: {self.profile.get('support_environment', 'Chrome/Edge 浏览器、Node.js 18+、Python 3.11+、PostgreSQL 或 SQLite')}")
        self.add_paragraph(f"开发工具: {self.profile.get('development_tools', 'Python 3.11、FastAPI、React、TypeScript、Vite、python-docx')}")
        self.add_title("适配说明", level=2)
        self.add_paragraph(
            f"{self.product_name}采用浏览器访问的软件架构，可在常见桌面浏览器环境中稳定运行，并适配日常办公场景下的常用分辨率。"
        )

    def generate_system_design(self, arch_diagram_path: str = "") -> None:
        self.add_title("开发设计 / 系统设计", level=1)
        self.add_title("系统总体架构", level=2)
        self.add_paragraph(
            self._profile_text(
                "system_architecture_summary",
                f"{self.product_name} 采用前后端分层的软件结构，由页面展示层、业务处理层、任务编排层和数据存储层组成。"
            )
        )
        self.add_paragraph(
            self._profile_text(
                "system_pipeline_summary",
                f"系统在设计上将页面、截图采集、说明书编排和导出发布串联为统一流水线，从而保证生成的软件内容、截图内容和导出材料保持一致。"
            )
        )
        self.add_title("开发技术说明", level=2)
        self.add_paragraph(
            self._profile_text(
                "development_tech_overview",
                "软件采用前后端分层与模块化设计方式，前端负责页面展示、状态反馈和下载入口，后端负责任务管理、运行检查、文档生成和导出发布，运行时通过标准清单控制应用启动、截图与导出行为。",
            )
        )
        self.add_title("开发语言说明", level=2)
        self.add_paragraph(self._profile_text("development_language_frontend", "前端页面主要采用 TypeScript / JavaScript 实现页面布局、交互逻辑与浏览器端渲染。"))
        self.add_paragraph(self._profile_text("development_language_backend", "后端服务主要采用 Python 实现任务流转、接口输出、文档生成、截图管理和导出逻辑。"))
        self.add_title("技术选型说明", level=2)
        self.add_paragraph(self._profile_text("tech_selection_frontend", "页面展示层采用 React 组件化方式构建，以保证页面结构清晰、模块职责明确并便于后续扩展。"))
        self.add_paragraph(self._profile_text("tech_selection_backend", "后端服务层采用 FastAPI 构建接口服务，以支持任务管理、下载分发和工件查询。"))
        self.add_paragraph(self._profile_text("tech_selection_data", "数据层支持 PostgreSQL 与 SQLite，用于适配生产环境和轻量测试环境。"))
        self.add_title("产品特性与设计侧重点", level=2)
        for item in self._profile_focus_list(
            "distinguishing_features",
            [
                f"围绕{self.profile.get('topic_label', self.product_name)}主题组织模块内容，突出当前软件产品的核心业务链路。",
                "模块命名、页面字段和说明书正文根据当前任务重新生成，避免不同产品之间出现大段重复描述。",
                "截图、页面说明、功能结构和技术特点保持同一业务主线，便于交付、培训与正式材料整理。",
            ],
        ):
            self.add_paragraph(f"- {item}")
        self.add_title("系统架构图", level=2)
        if arch_diagram_path and os.path.exists(arch_diagram_path):
            if arch_diagram_path.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp")):
                self.add_image(arch_diagram_path, width_inches=6.0)
                self.add_caption(f"图1：{self.product_name}系统架构图")
            else:
                self.add_paragraph("系统架构图生成失败，请检查图片生成链路。")
        else:
            self.add_paragraph("系统架构图生成失败，请检查中文字体与图片生成链路。")
        self.add_title("软件核心功能 / 功能元素", level=2)
        self.add_paragraph(
            self._profile_text(
                "main_functions",
                "软件核心功能包括登录访问、首页概览、业务对象管理、流程推进、资料管理、分析报表、预警提醒与系统配置。",
            )
        )
        self.add_paragraph(self._profile_text("function_elements_summary", "功能元素主要由导航菜单、统计卡片、筛选输入框、列表表格、操作按钮、状态标签、导出入口和配置项组成。"))

    def generate_function_structure(self, modules: list[str] | None = None) -> None:
        self.add_title("功能结构说明", level=1)
        if self._module_profiles():
            for module in self._module_profiles():
                self.add_title(module["title"], level=2)
                self.add_title("功能定位", level=3)
                self.add_paragraph(module.get("description", f"{module['title']}模块用于承载该业务主题的主要操作。"))
                self.add_title("页面构成", level=3)
                self.add_paragraph(self._module_field_summary(module))
                primary_action = module.get("primary_action") or f"处理{module['title']}"
                summary_parts = [f"本模块常用主操作为“{primary_action}”。"]
                if module.get("filter_placeholder"):
                    summary_parts.append(f"检索区会优先围绕“{module['filter_placeholder']}”组织筛选入口。")
                if module.get("page_variant"):
                    summary_parts.append(f"当前页面采用 {module['page_variant']} 版式组织标题区、信息区和结果区。")
                self.add_paragraph(self._sanitize_doc_text(" ".join(summary_parts)))
                self.add_title("功能要点", level=3)
                for highlight in module.get("highlights", []):
                    self.add_paragraph(f"- {highlight}")
                self.add_title("典型操作说明", level=3)
                for index, step in enumerate(self._module_steps(module), 1):
                    self.add_paragraph(f"{index}. {step}")
                self.add_title("业务价值", level=3)
                self.add_paragraph(self._module_business_value(module))
        else:
            modules = modules or ["登录认证", "仪表盘/首页", "数据管理", "报表统计", "告警管理", "系统设置"]
            for mod in modules:
                self.add_title(mod, level=2)
                self.add_paragraph(f"{mod}模块提供完整的业务管理和操作支持能力。")

    def generate_role_permissions(self, prd_summary: dict | None = None) -> None:
        self.add_title("角色权限说明", level=1)
        module_titles = self._module_titles()
        for role in self._role_profiles(prd_summary):
            self.add_title(role, level=2)
            self.add_paragraph(
                self._sanitize_doc_text(
                    (self.profile.get("role_permissions") or {}).get(
                        role,
                        f"{role}可在授权范围内访问与其职责相关的页面、列表和统计数据，并对负责模块执行查询、维护、导出或审核等操作。",
                    )
                )
            )
            self.add_paragraph(self._role_work_scope(role, module_titles))

    def generate_business_flows(self) -> None:
        self.add_title("常见业务流程说明", level=1)
        self.add_title("基础使用流程", level=2)
        self.add_paragraph(
            self._profile_text(
                "business_flow_basic",
                "使用人员首先通过登录页完成身份验证，进入系统首页后查看统计信息与待办摘要，再根据左侧导航进入具体功能模块完成录入、维护、查询、统计或配置等操作。",
            )
        )
        self.add_title("材料生成流程", level=2)
        self.add_paragraph(
            self._profile_text(
                "business_flow_materials",
                "系统在任务创建后依次执行需求整理、应用构建、运行校验、页面截图、说明书生成、源码文档生成和导出发布等阶段，确保最终下载文件与页面展示保持一致。",
            )
        )
        if self._module_profiles():
            self.add_title("模块协同流程", level=2)
            self.add_paragraph(
                self._profile_text(
                    "business_flow_module_collaboration",
                    f"针对“{self.profile.get('keyword', self.product_name)}”任务，用户可沿着当前任务模块顺序完成信息录入、过程推进、结果复核和材料沉淀。",
                )
            )
        self.add_title("典型应用场景", level=2)
        for item in self._profile_focus_list(
            "typical_scenarios",
            [
                f"面向{self.profile.get('industry_scope', '当前行业')}场景中的日常业务受理、状态跟踪与结果复核。",
                "面向需要统一入口、统一字段口径和统一导出材料的业务协同环境。",
                "面向多角色协作、需要保留过程记录和阶段状态的正式交付场景。",
            ],
        ):
            self.add_paragraph(f"- {item}")

    def generate_data_and_output(self) -> None:
        self.add_title("数据组织与结果输出说明", level=1)
        self.add_title("数据组织说明", level=2)
        self.add_paragraph(
            self._profile_text(
                "data_organization",
                f"{self.product_name}围绕{self.profile.get('topic_label', self.product_name)}主题组织业务数据，页面中的列表字段、状态标签、筛选项和操作按钮保持统一命名方式，便于不同角色在同一数据口径下开展协同处理。",
            )
        )
        self.add_title("结果输出说明", level=2)
        self.add_paragraph(
            self._profile_text(
                "result_output",
                "系统支持围绕当前任务输出页面截图、说明书正文、源码文档、申请表与相关工件，使业务结果、页面表现和交付材料可以形成对应关系，便于正式归档与提交。",
            )
        )
        self.add_title("材料整理说明", level=2)
        self.add_paragraph(
            self._profile_text(
                "material_arrangement",
                "在材料整理过程中，应优先核对模块标题、页面图注、关键字段、角色权限说明和导出文件名称，确保说明书内容与当前软件产品的业务主题、功能结构和截图顺序保持一致。",
            )
        )

    def _guess_usage_steps(self, title: str, meta: dict | None = None) -> list[str]:
        if meta and meta.get("steps"):
            return list(meta["steps"])
        return [
            "进入该页面后查看顶部标题区和主体操作区，确认当前业务主题。",
            "根据页面中的搜索框、筛选项或主按钮进入目标业务记录。",
            "结合列表内容、状态标签和结果反馈完成录入、查询、维护或审核操作。",
        ]

    def _guess_usage_description(self, title: str, elements: list[str], meta: dict | None = None) -> list[str]:
        visible = "、".join(self._sanitize_ui_elements(elements)[:10])
        description = meta.get("description") if meta else None
        primary_action = meta.get("primary_action") if meta else ""
        base = [
            self._sanitize_doc_text(
                description
                or f"{title}页面围绕当前业务主题的核心对象、处理动作和结果反馈组织信息，是用户完成日常处理与复核的重要入口。"
            ),
            self._sanitize_doc_text(
                f"页面中通常可以看到{visible or '标题、按钮、筛选项、表格和状态信息'}等关键元素，用户可围绕这些元素开展查询、录入、审核或配置操作。"
            ),
        ]
        if primary_action:
            base.append(self._sanitize_doc_text(f"该页面的常用主操作为“{primary_action}”，通常位于页面主体区域或列表工具栏位置。"))
        return base

    def _is_compact_variant_page(self, meta: dict, seen_routes: set[str]) -> bool:
        title = meta.get("page_title", "")
        route = meta.get("route", "")
        scenario_id = meta.get("scenario_id", "")
        if "筛选结果" in title:
            return True
        if scenario_id.endswith("-filtered"):
            return True
        return bool(route and route in seen_routes)

    def _add_variant_page_instruction(self, title: str, caption: str, image_path: str, elements: list[str], page_profile: dict) -> None:
        self.add_title(title, level=3)
        if image_path and os.path.exists(image_path):
            self.add_image(image_path, width_inches=6.1, max_height_inches=5.8)
            self.add_caption(caption)
        self.add_paragraph(
            self._sanitize_doc_text(
                page_profile.get(
                    "variant_instruction",
                    f"该截图展示了“{title}”在筛选、聚焦或结果定位后的页面状态，用于补充说明同一模块在具体业务条件下的展示效果与处理入口。",
                )
            )
        )
        if elements:
            self.add_paragraph(self._sanitize_doc_text("截图中重点可见元素包括：" + "、".join(elements[:10]) + "。"))
        else:
            self.add_paragraph("该变体页应重点关注筛选条件、结果列表、状态标签和主操作入口。")

    def generate_page_instructions(self, screenshots_meta: list[dict]) -> None:
        self.add_title("软件使用说明", level=1)
        self.add_title("使用说明总述", level=2)
        self.add_paragraph(
            self._profile_text(
                "usage_overview",
                "用户进入系统后，可按照“登录 -> 首页查看 -> 进入目标功能模块 -> 完成录入、查询、统计、审核或配置操作”的基本路径开展使用。后续章节将按页面顺序给出截图、功能讲解和详细操作说明。",
            )
        )
        self.add_title("主要页面操作说明", level=2)
        if not screenshots_meta:
            self.add_paragraph("（待截图完成后自动生成页面操作说明）")
            return

        module_meta = {module["title"]: module for module in self._module_profiles()}
        seen_routes: set[str] = set()
        for i, meta in enumerate(screenshots_meta):
            title = meta.get("page_title", f"页面{i + 1}")
            route = meta.get("route", "")
            caption = meta.get("caption", "") or meta.get("suggested_caption", "") or f"图{i + 1} {title}"
            image_path = meta.get("image_path", "")
            elements = self._sanitize_ui_elements(meta.get("elements", []))
            page_profile = module_meta.get(title) or module_meta.get(title.replace("筛选结果", "").strip()) or {}
            compact_variant = self._is_compact_variant_page(meta, seen_routes)

            if route:
                seen_routes.add(route)

            if compact_variant:
                self._add_variant_page_instruction(title, caption, image_path, elements, page_profile)
                continue

            self.add_title(title, level=2)
            if image_path and os.path.exists(image_path):
                self.add_image(image_path, width_inches=6.2, max_height_inches=6.2)
                self.add_caption(caption)

            self.add_title("功能讲解", level=3)
            for paragraph in self._guess_usage_description(title, elements, page_profile):
                self.add_paragraph(paragraph)

            self.add_title("详细操作说明", level=3)
            for j, step in enumerate(self._guess_usage_steps(title, page_profile), 1):
                self.add_paragraph(f"{j}. {step}")

            self.add_title("适用场景", level=3)
            self.add_paragraph(
                self._sanitize_doc_text(
                    page_profile.get(
                        "business_value",
                        f"{title}适用于当前业务主题下的信息录入、结果查询、状态跟踪、复核确认和材料整理等典型操作场景。",
                    )
                )
            )

            self.add_title("页面要点", level=3)
            if page_profile.get("highlights"):
                for highlight in page_profile["highlights"]:
                    self.add_paragraph(f"- {highlight}")
            if elements:
                self.add_paragraph(self._sanitize_doc_text("本页面关键可见元素包括：" + "、".join(elements[:12]) + "。"))
            else:
                self.add_paragraph("本页面应重点关注标题区、导航区、筛选区、数据展示区和操作反馈区。")

    def generate_tech_features(self) -> None:
        self.add_title("技术特点说明", level=1)
        self.add_paragraph(
            self._profile_text(
                "technical_features",
                "本软件采用 B/S 架构，支持主流浏览器访问，具备模块化页面、统一数据入口、角色权限控制和结果导出等典型后台能力。",
            )
        )
        self.add_paragraph(
            self._profile_text(
                "technical_feature_detail",
                f"{self.product_name}在实现上强调任务专属化内容生成与页面结构稳定并重，既保证不同产品拥有各自的业务重点、模块命名与说明书侧重点，也保证整体交互风格、材料输出和运行访问方式保持统一。",
            )
        )
        features = self._profile_list("technical_feature_bullets", [
            "采用浏览器访问模式，部署与使用门槛较低",
            "页面结构清晰，功能区分明确，便于培训与上手",
            "支持多模块统一访问，有利于集中管理业务数据和配置信息",
            "支持截图、导出、统计和留痕等交付所需能力",
            "支持多角色分工协同与标准化流程推进",
        ])
        for feature in features:
            self.add_paragraph(f"- {feature}")

    def generate_full(
        self,
        prd_summary: dict | None = None,
        screenshots_meta: list[dict] | None = None,
        modules: list[str] | None = None,
        arch_diagram_path: str = "",
    ) -> Document:
        header_text = f"{self.product_name}{self.version} 说明书"
        self.set_header(header_text)
        self.add_page_number()

        screenshots_meta = screenshots_meta or []
        self.generate_cover()
        self.generate_document_info(screenshots_meta)
        self.generate_introduction()
        self.generate_system_design(arch_diagram_path)
        self.generate_overview(prd_summary, modules)
        self.generate_runtime_environment()
        self.generate_function_structure(modules)
        self.generate_role_permissions(prd_summary)
        self.generate_business_flows()
        self.generate_data_and_output()
        self.generate_page_instructions(screenshots_meta)
        self.generate_tech_features()
        return self.doc
