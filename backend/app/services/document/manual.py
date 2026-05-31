from __future__ import annotations

import hashlib
import os
import re
import unicodedata

from docx import Document

from app.services.document.base import WordTemplateBase, pick_word_style_profile

REQUIRED_MANUAL_MODULES = [
    {"key": "overview", "title": "软件产品说明"},
    {"key": "function_structure", "title": "功能说明"},
    {"key": "page_instructions", "title": "操作手册"},
]

OPTIONAL_MANUAL_MODULES = [
    {"key": "introduction", "title": "引言", "description": "简要说明软件名称、版本与文档用途。"},
    {"key": "system_design", "title": "系统组成说明", "description": "客观说明软件由哪些页面与功能模块组成。"},
    {"key": "runtime_environment", "title": "运行环境说明", "description": "说明软件的运行环境与使用方式。"},
    {"key": "business_flows", "title": "业务流程说明", "description": "说明软件中的主要处理流程与页面衔接关系。"},
    {"key": "data_and_output", "title": "数据与结果说明", "description": "围绕页面数据内容、结果信息和导出内容做事实性说明。"},
    {"key": "tech_features", "title": "软件特点说明", "description": "围绕已具备的软件功能与页面组织方式做客观说明。"},
    {"key": "security_and_maintenance", "title": "运行维护说明", "description": "说明访问控制、运行检查与维护要点。"},
    {"key": "version_evolution_and_change_management", "title": "版本信息说明", "description": "说明软件版本标识与版本更新信息。"},
    {"key": "appendix", "title": "附录与补充说明", "description": "补充术语与说明。"},
]


class SoftwareManualGenerator(WordTemplateBase):
    def __init__(
        self,
        product_name: str,
        version: str,
        profile: dict | None = None,
        doc: Document | None = None,
    ):
        resolved_profile = profile or {}
        super().__init__(doc, style_profile=pick_word_style_profile(self._manual_style_seed(product_name, version, resolved_profile)))
        self.product_name = product_name
        self.version = version
        self.profile = resolved_profile

    def _manual_style_seed(self, product_name: str, version: str, profile: dict) -> str:
        parts = [
            str(profile.get("design_seed") or "").strip(),
            str(profile.get("keyword") or "").strip(),
            str(profile.get("product_name") or product_name).strip(),
            str(version or "").strip(),
        ]
        return "|".join(parts)

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

    def _selected_optional_module_keys(self) -> list[str]:
        ordered_keys = [item["key"] for item in OPTIONAL_MANUAL_MODULES]
        configured = self.profile.get("selected_optional_modules")
        if isinstance(configured, list):
            valid = []
            seen: set[str] = set()
            for item in configured:
                key = str(item).strip()
                if key in ordered_keys and key not in seen:
                    valid.append(key)
                    seen.add(key)
            if valid:
                return valid
        default_keys = [
            "introduction",
            "runtime_environment",
            "business_flows",
            "data_and_output",
            "tech_features",
        ]
        seed = self._manual_style_seed(self.product_name, self.version, self.profile)
        if seed and int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:2], 16) % 2 == 0:
            default_keys.append("version_evolution_and_change_management")
        return [key for key in default_keys if key in ordered_keys]

    def _module_steps(self, module: dict) -> list[str]:
        if module.get("steps"):
            return [self._sanitize_doc_text(str(step)) for step in module["steps"] if str(step).strip()]
        title = module.get("title", "当前模块")
        action = module.get("primary_action", f"处理{title}")
        return [
            f"进入{title}页面后先确认标题区、筛选区和主操作按钮，核对当前处理对象与业务范围。",
            f"通过搜索条件、列表记录和状态标签定位目标事项，并按需执行“{action}”等主操作。",
            f"完成处理后复核页面反馈、更新时间和相关记录，确认当前处理结果已经正确保存。",
        ]

    def _module_field_summary(self, module: dict) -> str:
        headers = [str(item).strip() for item in module.get("table_headers", []) if str(item).strip()]
        if not headers:
            return "页面通常由标题信息区、查询条件区、结果列表区和操作反馈区构成。"
        header_text = "页面主要展示以下信息：" + "、".join(headers[:8]) + "。"
        rows = [list(row) for row in module.get("rows", []) if isinstance(row, list)]
        if rows:
            header_text += " 页面列表区会结合实际业务记录展示对应字段值，并支持对单条记录进行查看或处理。"
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

    def _module_example_record(self, module: dict) -> str:
        headers = [str(item).strip() for item in module.get("table_headers", []) if str(item).strip()]
        rows = [list(row) for row in module.get("rows", []) if isinstance(row, list)]
        if not headers or not rows:
            return "页面通常以标题区、筛选区、主表格和操作区组织一线业务数据。"
        first_row = [self._sanitize_doc_text(str(cell)) for cell in rows[0][: len(headers)]]
        pairs = [f"{header}为“{value}”" for header, value in zip(headers[:4], first_row[:4]) if value]
        if not pairs:
            return "模块数据样例会围绕编号、主题、责任角色、状态和更新时间等字段展开。"
        return self._sanitize_doc_text("例如列表首条业务记录中，" + "，".join(pairs) + "，便于用户快速理解当前模块的数据口径。")

    def _module_tech_notes(self, module: dict) -> list[str]:
        title = module.get("title", "当前模块")
        headers = [str(item).strip() for item in module.get("table_headers", []) if str(item).strip()]
        primary_action = self._sanitize_doc_text(str(module.get("primary_action", f"处理{title}")))
        focus = "、".join(headers[:4]) if headers else "标题、筛选项、结果列表与状态反馈"
        return [
            self._sanitize_doc_text(
                f"{title}页面围绕“{primary_action}”组织标题信息、查询条件、结果列表和处理入口，使相关业务记录能够集中展示。"
            ),
            self._sanitize_doc_text(
                f"模块核心字段围绕{focus}展开，便于用户在单页内完成查询、录入、复核和结果确认。"
            ),
            self._sanitize_doc_text(
                f"相关处理结果会在页面反馈信息、状态标识和记录更新时间中同步体现，便于后续查询、核对与结果留存。"
            ),
        ]

    def _core_entities_text(self) -> str:
        entities = [self._sanitize_doc_text(str(item)) for item in self.profile.get("core_entities", []) if str(item).strip()]
        if not entities:
            return "系统围绕业务资料、处理记录、状态结果和输出信息等基础数据内容组织页面展示与结果输出。"
        return self._sanitize_doc_text(
            "系统中的主要数据内容包括"
            + "、".join(entities[:6])
            + "等信息项，这些内容会在相关页面和输出结果中保持统一命名。"
        )

    def _project_dna_notes(self) -> list[str]:
        project_dna = self.profile.get("project_dna") or {}
        visual_profile = self.profile.get("visual_profile") or {}
        experience_blueprint = self.profile.get("experience_blueprint") or {}
        notes = [
            self._sanitize_doc_text(
                f"项目主题以“{self.profile.get('topic_label', self.product_name)}”为核心主线，页面结构、截图说明与导出文档均围绕该主题组织，避免出现与当前产品定位无关的模块语义。"
            ),
            self._sanitize_doc_text(
                f"在交互设计上，系统优先采用{visual_profile.get('layout_signal', '清晰稳定的业务工作台布局')}，并通过 {visual_profile.get('chrome_treatment', '统一导航结构')} 保证用户进入系统后能够快速识别当前模块与工作入口。"
            ),
            self._sanitize_doc_text(
                f"项目架构风格参考 {project_dna.get('architecture_style', '模块化业务协同')} 进行拆解，强调首页概览、模块处理、状态反馈、结果导出与材料沉淀的连续性。"
            ),
            self._sanitize_doc_text(
                f"页面体验蓝图采用 {experience_blueprint.get('navigation_variant', '稳定导航')} 导航方式，并结合模块变体 {', '.join(experience_blueprint.get('module_variants', [])[:4]) or '列表、概览、分析和流程'} 组织不同业务页面。"
            ),
        ]
        return notes

    def _module_delivery_notes(self, module: dict) -> list[str]:
        title = module.get("title", "当前模块")
        primary_action = self._sanitize_doc_text(str(module.get("primary_action", f"处理{title}")))
        roles = "、".join(self._role_profiles()[:3])
        return [
            self._sanitize_doc_text(
                f"{title}在交付时不仅需要完成页面开发，还需要同步确认字段命名、默认筛选项、操作反馈文案和图注说明，使真实运行页面与说明书正文保持同一语义。"
            ),
            self._sanitize_doc_text(
                f"若该模块需要承接“{primary_action}”等关键动作，实施阶段应重点验证角色权限、状态流转、列表结果和导出内容是否与业务规则一致。"
            ),
            self._sanitize_doc_text(
                f"在系统使用与交付过程中，{roles or '管理员、业务主管、业务专员'}通常分别从配置维护、日常处理和结果复核角度参与该模块的使用与确认，使页面能够稳定支撑真实工作流程。"
            ),
        ]

    def _module_acceptance_notes(self, module: dict) -> list[str]:
        title = module.get("title", "当前模块")
        headers = [str(item).strip() for item in module.get("table_headers", []) if str(item).strip()]
        checks = "、".join(headers[:4]) if headers else "模块标题、筛选条件、列表结果、状态反馈"
        return [
            self._sanitize_doc_text(
                f"{title}在交付核对过程中，{checks}等关键内容需要与业务规则保持一致，页面中的主操作、回显信息和说明书图注之间也需要形成对应关系。"
            ),
            self._sanitize_doc_text(
                f"若{title}承接正式业务处理，相关记录通常会同时保留样例数据、处理结果、责任角色和时间信息，以支撑后续运维、审计和材料归档。"
            ),
            self._sanitize_doc_text(
                f"模块上线后还应持续关注字段口径变更、列表状态演进和导出格式调整，避免页面、截图和交付文档出现信息漂移。"
            ),
        ]

    def _module_data_dictionary_notes(self, module: dict) -> list[str]:
        title = module.get("title", "当前模块")
        headers = [self._sanitize_doc_text(str(item)) for item in module.get("table_headers", []) if str(item).strip()]
        if not headers:
            return [
                self._sanitize_doc_text(
                    f"{title}页面通常包含业务编号、主题对象、处理状态、更新时间和结果说明等基础字段，用于展示当前记录信息。"
                )
            ]
        notes: list[str] = []
        for idx, header in enumerate(headers[:6], start=1):
            notes.append(
                self._sanitize_doc_text(
                    f"{idx}. 字段“{header}”用于标识{title}页面中的对应信息项，便于用户在查询、列表查看和详情处理时快速识别记录内容。"
                )
            )
        return notes

    def _module_collaboration_notes(self, module: dict) -> list[str]:
        title = module.get("title", "当前模块")
        roles = self._role_profiles()
        role_text = "、".join(roles[:4]) if roles else "管理员、业务主管、业务专员"
        return [
            self._sanitize_doc_text(
                f"{title}通常需要{role_text}等角色协同参与，其中部分角色负责录入与维护，部分角色负责复核、审批、处置跟踪或结果汇总，从而形成明确的职责边界。"
            ),
            self._sanitize_doc_text(
                f"在协同过程中，模块页面应能够清晰展示当前记录由谁创建、当前处于何种状态、下一步由谁继续处理，以及最终结果如何沉淀到正式材料中。"
            ),
        ]

    def _core_entity_details(self) -> list[str]:
        entities = [self._sanitize_doc_text(str(item)) for item in self.profile.get("core_entities", []) if str(item).strip()]
        if not entities:
            entities = ["业务对象", "处理记录", "状态结果", "审计日志"]
        notes: list[str] = []
        for entity in entities[:8]:
            notes.append(
                self._sanitize_doc_text(
                    f"{entity}属于系统中的关键业务对象，其命名、状态和关联关系需要在首页统计、模块列表、说明书正文和导出材料中保持一致，避免不同环节对同一对象出现多套解释。"
                )
            )
        return notes

    def _module_risk_and_controls(self, module: dict) -> list[str]:
        title = module.get("title", "当前模块")
        return [
            self._sanitize_doc_text(
                f"{title}在运行过程中可能面临数据遗漏、状态误判、角色越权、结果回填不一致等风险，因此页面设计需要同步提供清晰的状态标签、提示信息和结果留痕。"
            ),
            self._sanitize_doc_text(
                f"从控制措施看，可通过字段校验、操作确认、权限控制、日志记录和导出复核等方式降低{title}处理过程中的业务偏差与交付风险。"
            ),
        ]

    def _role_module_matrix_notes(self, role: str) -> list[str]:
        modules = self._module_profiles()
        if not modules:
            return [
                self._sanitize_doc_text(
                    f"{role}需要围绕首页概览、业务处理、结果复核和导出归档等环节开展工作，并结合授权范围完成相应操作。"
                )
            ]
        notes: list[str] = []
        for module in modules[:6]:
            title = module.get("title", "当前模块")
            action = self._sanitize_doc_text(str(module.get("primary_action", f"处理{title}")))
            notes.append(
                self._sanitize_doc_text(
                    f"在“{title}”模块中，{role}通常需要重点关注与其职责相关的查询、录入、复核或“{action}”等关键动作，确保页面结果、处理状态和导出内容保持一致。"
                )
            )
        return notes

    def _page_business_rule_notes(self, title: str, page_profile: dict) -> list[str]:
        primary_action = self._sanitize_doc_text(str(page_profile.get("primary_action", f"处理{title}")))
        filter_placeholder = self._sanitize_doc_text(str(page_profile.get("filter_placeholder", "")).strip())
        headers = [self._sanitize_doc_text(str(item)) for item in page_profile.get("table_headers", []) if str(item).strip()]
        field_focus = "、".join(headers[:4]) if headers else "编号、主题、状态、责任人"
        notes = [
            self._sanitize_doc_text(
                f"{title}页面的业务规则通常围绕{field_focus}等字段展开，用户在页面中进行筛选、查看和处理时，需要保证这些字段与正式业务口径完全一致。"
            ),
            self._sanitize_doc_text(
                f"页面内的主操作“{primary_action}”通常对应一个明确的业务节点，因此在页面设计与实施培训中，应说明该动作的触发条件、执行结果、状态变化和后续责任归属。"
            ),
        ]
        if filter_placeholder:
            notes.append(
                self._sanitize_doc_text(
                    f"对于检索区中的“{filter_placeholder}”等条件，应明确其适用范围、默认值和组合筛选逻辑，避免用户因检索口径不一致而误判页面结果。"
                )
            )
        return notes

    def _page_collaboration_and_output_notes(self, title: str, page_profile: dict) -> list[str]:
        roles = "、".join(self._role_profiles()[:4]) or "管理员、业务主管、业务专员"
        return [
            self._sanitize_doc_text(
                f"{title}不仅服务于单个用户的页面操作，还承接{roles}等角色之间的信息协同，因此页面中的状态标签、更新时间、责任信息和结果摘要都应具备清晰的解释性。"
            ),
            self._sanitize_doc_text(
                f"从交付视角看，{title}页面中的字段展示、图注说明和截图顺序会直接影响软件说明书、培训资料和正式验收材料，因此页面输出必须兼顾业务使用与文档归档双重要求。"
            ),
            self._sanitize_doc_text(
                f"若该页面需要支持导出、汇总或结果沉淀，则应在使用说明中交代导出内容的命名规范、字段范围、使用场景以及与后续审核、归档环节的关系。"
            ),
        ]

    def _page_exception_notes(self, title: str, page_profile: dict) -> list[str]:
        return [
            self._sanitize_doc_text(
                f"{title}在实际运行中常见的异常包括筛选结果为空、状态回显不一致、关键字段缺失、角色权限不足或操作反馈不明确。页面说明中应提前提示这些风险点，帮助使用人员快速判断当前页面是否符合预期。"
            ),
            self._sanitize_doc_text(
                f"在实施和运维过程中，{title}通常配套固定巡检项，包括页面标题、筛选入口、表格字段、主操作按钮、状态标签、时间信息和截图内容是否齐全，以便在问题出现时快速定位。"
            ),
            self._sanitize_doc_text(
                f"若页面需要作为说明书截图来源，还应在验收时同步检查页面布局稳定性、中文字体显示、数据样例完整性和图注对应关系，避免页面可运行但截图材料不可用的情况再次发生。"
            ),
        ]

    def _variant_page_review_notes(self, title: str, page_profile: dict) -> list[str]:
        return [
            self._sanitize_doc_text(
                page_profile.get(
                    "variant_review_note",
                    f"{title}用于展示同一模块在特定筛选条件、聚焦结果或状态组合下的页面表现，便于说明业务规则在不同条件下的可视化差异。"
                )
            ),
            self._sanitize_doc_text(
                f"在正式验收时，这类变体页应重点核对筛选条件是否生效、结果数量是否合理、状态标签是否与主页面一致，以及图注描述能否准确反映当前页面所处的业务语境。"
            ),
        ]

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
        self._apply_run_font(run, font_name=self.style_profile["cover_font"], font_size=14)
        p2 = self.doc.add_paragraph()
        p2.alignment = 1
        run2 = p2.add_run("软件说明书 / 操作手册")
        self._apply_run_font(run2, font_name=self.style_profile["cover_font"], font_size=14)
        self.doc.add_page_break()

    def generate_document_info(self, screenshots_meta: list[dict]) -> None:
        self.add_title("文档说明", level=1)
        self.add_paragraph(f"本文档为{self.product_name}{self.version}的软件说明书/操作手册。")
        self.add_paragraph(
            self._profile_text(
                "overview_version_summary",
                "文档内容主要包括软件概述、运行环境、功能结构、业务流程、页面操作说明以及运行维护等内容。",
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
                "overview_version_summary",
                f"当前软件版本为{self.version}。系统采用浏览器访问方式，围绕统一入口、模块页面、状态结果和输出内容组织整体功能。",
            )
        )
        self.add_title("软件主要功能", level=2)
        for mod in module_items:
            self.add_paragraph(f"- {mod}")
        self.add_title("产品目标", level=2)
        self.add_paragraph(
            self._profile_text(
                "development_purpose",
                "本软件的目标是通过统一页面和标准化业务记录方式，提高日常处理、查询复核和结果输出的效率与一致性。",
            )
        )

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
        self.add_title("系统组成说明", level=1)
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
                "系统通过统一的数据组织方式和模块页面结构承接信息录入、查询处理、状态反馈和结果输出，使软件各功能模块保持连贯一致。"
            )
        )
        self.add_title("开发技术说明", level=2)
        self.add_paragraph(
            self._profile_text(
                "development_tech_overview",
                "软件采用前后端分层与模块化组织方式，前端负责页面展示、交互处理和结果回显，后端负责业务处理、数据组织、状态记录和结果输出。",
            )
        )
        self.add_title("开发语言说明", level=2)
        self.add_paragraph(self._profile_text("development_language_frontend", "前端页面主要采用 TypeScript / JavaScript 实现页面布局、交互逻辑与浏览器端渲染。"))
        self.add_paragraph(self._profile_text("development_language_backend", "后端服务主要采用 Python 实现任务流转、接口输出、文档生成、截图管理和导出逻辑。"))
        self.add_title("技术选型说明", level=2)
        self.add_paragraph(self._profile_text("tech_selection_frontend", "页面展示层采用 React 组件化方式构建，以保证页面结构清晰、模块职责明确并便于后续扩展。"))
        self.add_paragraph(self._profile_text("tech_selection_backend", "后端服务层采用 FastAPI 构建接口服务，以支持任务管理、下载分发和工件查询。"))
        self.add_paragraph(self._profile_text("tech_selection_data", "数据层支持 PostgreSQL 与 SQLite，用于适配生产环境和轻量测试环境。"))
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
                self.add_title("功能说明", level=3)
                self.add_paragraph(module.get("description", f"{module['title']}模块用于承载该业务主题的主要操作。"))
                self.add_title("主要数据内容", level=3)
                self.add_paragraph(self._module_field_summary(module))
                self.add_title("功能要点", level=3)
                for highlight in module.get("highlights", []):
                    self.add_paragraph(f"- {highlight}")
                self.add_title("典型操作说明", level=3)
                for index, step in enumerate(self._module_steps(module), 1):
                    self.add_paragraph(f"{index}. {step}")
                self.add_title("处理说明", level=3)
                self.add_paragraph(self._module_business_value(module))
                self.add_title("数据样例", level=3)
                self.add_paragraph(self._module_example_record(module))
                self.add_title("结果记录说明", level=3)
                for note in self._module_tech_notes(module):
                    self.add_paragraph(note)
                self.add_title("字段说明", level=3)
                for note in self._module_data_dictionary_notes(module):
                    self.add_paragraph(note)
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
            self.add_title("职责覆盖模块", level=3)
            for note in self._role_module_matrix_notes(role):
                self.add_paragraph(note)
            self.add_title("角色交付关注点", level=3)
            self.add_paragraph(
                self._sanitize_doc_text(
                    f"{role}在参与正式交付时，不仅需要关注自身日常使用页面，还需要关注截图是否真实反映业务数据、说明书是否准确描述角色职责、以及导出结果是否符合实际业务口径。"
                )
            )
            self.add_paragraph(
                self._sanitize_doc_text(
                    f"若{role}承担复核、审批或归档职责，还应在培训和验收中重点检查状态流转、责任边界、结果留痕和导出材料名称，避免上线后因职责定义不清导致业务推进受阻。"
                )
            )

    def generate_business_flows(self) -> None:
        self.add_title("常见业务流程说明", level=1)
        self.add_title("基础使用流程", level=2)
        self.add_paragraph(
            self._profile_text(
                "business_flow_basic",
                "使用人员首先通过登录页完成身份验证，进入系统首页后查看统计信息与待办摘要，再根据左侧导航进入具体功能模块完成录入、维护、查询、统计或配置等操作。",
            )
        )
        self.add_title("功能处理流程", level=2)
        self.add_paragraph(
            self._profile_text(
                "business_flow_materials",
                "系统围绕信息录入、结果查询、状态流转、处理反馈和结果输出形成连续处理链路，使页面操作与结果记录保持一致。",
            )
        )
        if self._module_profiles():
            self.add_title("模块协同流程", level=2)
            self.add_paragraph(
                self._profile_text(
                    "business_flow_module_collaboration",
                    f"围绕{self.product_name}的功能模块，软件支持按照模块顺序完成信息登记、处理推进、结果查看和记录留存。"
                )
            )

    def generate_data_and_output(self) -> None:
        self.add_title("数据组织与结果输出说明", level=1)
        self.add_title("数据组织说明", level=2)
        self.add_paragraph(
            self._profile_text(
                "data_organization",
                f"{self.product_name}围绕软件中的业务记录、状态信息、查询条件和结果数据组织页面内容，页面中的字段名称、状态标签、筛选项和操作入口保持统一命名方式。",
            )
        )
        self.add_title("结果输出说明", level=2)
        self.add_paragraph(
            self._profile_text(
                "result_output",
                "系统中的处理结果可通过页面回显、列表记录、详情信息和导出内容进行查看，用于保留业务处理过程与结果信息。",
            )
        )
        self.add_title("数据一致性说明", level=2)
        self.add_paragraph(
            self._profile_text(
                "material_arrangement",
                "同一类业务数据在不同页面中保持统一编号方式、字段命名和状态表达，便于对相关记录进行查询、统计和结果核对。",
            )
        )
        self.add_title("主要数据内容说明", level=2)
        self.add_paragraph(self._core_entities_text())
        self.add_paragraph(
            self._sanitize_doc_text(
                "同一类业务对象在首页统计、模块列表、详情信息和结果输出中的命名应保持统一，避免出现字段别名或状态描述不一致的情况。"
            )
        )

    def generate_business_object_details(self) -> None:
        self.add_title("核心业务对象详解", level=1)
        self.add_title("对象范围说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                f"{self.product_name}并不是只展示页面，而是围绕若干真实业务对象组织数据、流程和结果输出。为了让产品说明、页面行为和交付材料保持统一，需要先明确系统内哪些对象是平台处理的核心主线。"
            )
        )
        for note in self._core_entity_details():
            self.add_paragraph(note)
        self.add_title("对象间关系说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "从业务关系上看，核心对象通常会形成“基础资料 -> 处理记录 -> 状态结果 -> 导出材料 -> 审计留痕”的串联关系。页面中的统计卡片、筛选区、表格列和图注说明，实质上都是围绕这一对象关系链展开。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "当用户在不同模块间切换时，系统应保证这些对象的编号、主题、状态和责任信息不会发生语义漂移，使培训、实施和后续版本迭代都能基于同一套对象定义推进。"
            )
        )
        self.add_title("对象口径治理说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "项目实施过程中通常同步建立对象口径表，用于明确对象名称、主键字段、状态枚举、责任角色、更新时间和归档位置。该口径表既支撑说明书正文，也支撑接口联调、截图校验和正式交付时的统一表述。"
            )
        )

    def generate_interface_and_data_flow(self) -> None:
        self.add_title("接口协同与数据流转说明", level=1)
        self.add_title("页面到服务的数据路径", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "在系统实现上，页面层会围绕列表加载、筛选查询、详情查看、主操作提交和导出下载等典型动作访问后端服务。后端再根据任务状态、项目画像和页面路由返回结构化结果，使前端能够稳定展示标题、卡片、表格、状态与图注。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "这一路径之所以重要，是因为说明书中的页面截图、字段说明和图注内容都依赖同一条数据链路。如果页面与服务返回的数据口径不一致，最终交付文档也会出现错位。"
            )
        )
        self.add_title("任务工件流转", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "任务级工件通常包括需求摘要、项目画像、页面源码、运行清单、截图清单、软件说明书、源码文档和发布包等。这些工件并不是彼此独立，而是逐级承接。项目画像决定页面模块和字段，截图清单决定说明书插图，说明书和源码文档又共同构成正式交付件。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "因此，在系统设计中必须把工件流转看作正式开发的一部分，而不是附属产物。只有工件链路清晰，才能在出现异常时通过时间线、阶段日志和工件内容快速定位根因。"
            )
        )
        self.add_title("一致性控制说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "系统围绕模块名称、页面路由、字段标题、样例数据、截图标题和导出文件名称建立一致性控制。版本变化涉及上述任一内容时，页面、说明书和交付清单会同步更新，避免运行页面与正式材料脱节。"
            )
        )

    def generate_test_and_quality_plan(self) -> None:
        self.add_title("测试策略与质量保障说明", level=1)
        self.add_title("测试范围", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "测试范围应覆盖登录入口、首页概览、模块页面、关键路由跳转、主操作反馈、截图采集、说明书生成、源码文档生成以及整包下载等交付全链路能力。对于真实产品交付，不宜只验证页面能打开，还应验证页面展示内容是否真正反映业务语义。"
            )
        )
        self.add_title("功能核查内容", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "功能核查内容覆盖模块标题、筛选区、表格字段、样例数据、按钮文案、状态标签和导出行为。若任何一个模块仍残留占位内容、假数据或与产品主题无关的行业语义，则页面内容与当前产品主题不一致。"
            )
        )
        self.add_title("文档一致性测试", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "文档一致性测试主要确认说明书中的章节、模块名、图注、截图顺序、关键字段、角色职责和技术说明是否与页面产物相匹配。页面和文档不一致时，即使系统功能可运行，也会对客户培训、正式验收和归档申报造成实质影响。"
            )
        )
        self.add_title("发布前检查清单", level=2)
        checks = [
            "确认登录页、首页及核心模块页均可正常访问",
            "确认截图数量满足项目要求，且核心页面无缺失",
            "确认说明书包含产品、技术、实施、运维等完整章节",
            "确认源码文档、申请表和下载包均已成功生成",
            "确认页面字段、图注说明和导出文件名称保持一致",
        ]
        for item in checks:
            self.add_paragraph(f"- {item}")

    def generate_training_and_rollout(self) -> None:
        self.add_title("培训推广与上线准备说明", level=1)
        self.add_title("培训分层说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                f"系统培训内容围绕{'、'.join(self._role_profiles()[:4])}等角色进行分层组织。管理角色重点理解首页看板、权限边界与结果汇总，执行角色重点掌握筛选、录入、处理和导出操作，复核角色重点关注状态流转、结果校验和材料归档。"
            )
        )
        self.add_title("上线准备项", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "上线前应完成账号准备、角色映射、默认演示数据确认、模块路由检查、截图与说明书校验、导出链路核查以及版本信息留档。只有同时满足运行、展示和文档交付三方面要求，才适合进入正式上线窗口。"
            )
        )
        self.add_title("推广与持续使用说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "系统投入使用后，说明书和截图清单共同构成培训底稿，并结合真实页面开展场景化演示。对于首次接触系统的使用单位，培训材料通常围绕登录、首页、核心模块和导出结果四条主线组织，帮助使用角色快速建立整体认知。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "在持续使用阶段，页面变更、字段调整、模块新增和说明书更新点会按月份或版本维度整理，使培训资料与当前系统保持同步，避免文档脱离实际页面。"
            )
        )

    def generate_appendix(self) -> None:
        self.add_title("附录与补充说明", level=1)
        self.add_title("术语与缩略语说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "本文档中的“模块”通常指具备独立页面入口和业务职责的功能单元；“工件”指任务在执行过程中生成并可复核的中间或最终产物；“交付物”指说明书、源码文档、申请表、截图材料和下载包等正式对外交付内容。"
            )
        )
        self.add_title("维护记录说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "后续版本通常维护变更记录表，用于记录每次版本迭代涉及的模块、字段、截图、导出物和说明书章节变化。该记录既便于内部回顾，也便于交付阶段理解版本差异。"
            )
        )
        self.add_title("模块补充清单", level=2)
        for module in self._module_profiles():
            self.add_paragraph(
                self._sanitize_doc_text(
                    f"{module.get('title', '当前模块')}：附录中补充字段口径、责任角色、主操作入口、状态流转、导出结果和培训要点等信息，用于后续版本迭代与项目复盘时统一参考。"
                )
            )

    def generate_data_governance_and_caliber(self) -> None:
        self.add_title("数据治理与口径控制说明", level=1)
        self.add_title("字段口径统一原则", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "系统中的编号、主题、状态、责任角色、更新时间、处理结果等字段应在页面展示、截图图注、说明书正文、导出材料和后续培训资料中保持统一命名，避免同一对象出现多套口径。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                f"对于{self.product_name}这类真实业务产品，项目实施早期通常同步建立字段口径表，明确字段定义、来源系统、更新频率、展示位置和归档用途，从源头减少页面、截图和说明书之间的语义偏差。"
            )
        )
        self.add_title("样例数据与页面一致性", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "说明书中的截图、页面说明和字段样例必须引用当前任务真实生成的页面数据结构，不得混用占位数据、行业无关示例或与当前任务无关的旧任务术语。"
            )
        )
        for module in self._module_profiles()[:6]:
            self.add_paragraph(
                self._sanitize_doc_text(
                    f"{module.get('title', '当前模块')}对应模块标题、表格字段、筛选条件、主操作入口和结果回显，需要与截图图注、页面说明和导出材料保持一致。"
                )
            )

    def generate_implementation_milestones_and_collaboration(self) -> None:
        self.add_title("项目实施里程碑与角色协同矩阵", level=1)
        self.add_title("实施里程碑说明", level=2)
        milestones = [
            "完成需求确认、业务对象梳理和角色职责对齐",
            "完成页面结构设计、模块顺序确认和字段口径冻结",
            "完成前后端联调、运行验证和截图场景校验",
            "完成说明书、源码文档、申请表和发布包整理",
            "完成培训演示、交付验收与版本归档",
        ]
        for idx, item in enumerate(milestones, start=1):
            self.add_paragraph(f"{idx}. {item}")
        self.add_title("角色协同矩阵说明", level=2)
        roles = self._role_profiles()[:4]
        modules = self._module_titles()[:6]
        if roles and modules:
            for role in roles:
                self.add_paragraph(
                    self._sanitize_doc_text(
                        f"{role}通常需要围绕{'、'.join(modules)}等模块参与需求确认、业务处理、结果复核、材料确认或培训推广中的一个或多个环节，并对本角色关注的数据与结果负责。"
                    )
                )
        else:
            self.add_paragraph("项目成员通常围绕需求确认、页面实现、运行验证、截图核对和交付整理等环节形成协同配合。")

    def generate_operations_checklist_and_incident_response(self) -> None:
        self.add_title("运维巡检与异常处置清单", level=1)
        self.add_title("日常巡检项", level=2)
        checklist = [
            "检查登录页、首页和核心模块页是否可正常访问",
            "检查关键字段、样例数据、状态标签和主操作按钮是否完整显示",
            "检查截图数量、图注顺序和说明书章节是否与当前任务一致",
            "检查导出文件、整包下载和时间线事件是否可正常使用",
            "检查近期版本变更是否同步更新到页面、截图和说明书",
        ]
        for idx, item in enumerate(checklist, start=1):
            self.add_paragraph(f"{idx}. {item}")
        self.add_title("异常处置说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "若运行中发现页面缺页、截图缺失、说明书章节异常、导出文件不一致或任务长时间停留在单阶段，应优先结合阶段日志、工件落盘时间、运行清单和截图清单定位问题来源，再执行定点修复。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "对于正式交付场景，异常关闭前应补充复核记录，确认页面、截图、说明书、源码文档和下载包重新恢复一致，避免修复页面后遗漏文档或导出材料。"
            )
        )

    def generate_version_evolution_and_change_management(self) -> None:
        self.add_title("版本演进与变更管理说明", level=1)
        self.add_title("版本演进说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                f"{self.product_name}在后续版本演进中，会围绕模块新增、字段调整、角色变化、截图更新和说明书章节同步建立变更记录，确保版本差异可以被实施人员和交付人员快速理解。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "每次版本升级时，除页面和接口本身外，还应同步复核截图清单、图注、说明书正文、源码文档目录和发布包内容，避免代码已更新而正式材料仍停留在旧版。"
            )
        )
        self.add_title("变更管理控制点", level=2)
        controls = [
            "模块标题、页面路由与角色权限变化时同步更新说明书章节",
            "字段口径、状态枚举与导出格式变化时同步更新截图和图注",
            "新增业务流程或页面变体时同步更新培训资料和验收清单",
            "发布前复核导出文件名称、版本号、页数和截图数量",
        ]
        for idx, item in enumerate(controls, start=1):
            self.add_paragraph(f"{idx}. {item}")

    def generate_development_details(self) -> None:
        self.add_title("产品开发与技术实现说明", level=1)
        self.add_title("前端实现说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                f"{self.product_name}前端采用 React + TypeScript 的组件化组织方式，围绕登录页、首页、模块页和导出入口构成统一交互层。页面实现重点在于导航壳层、筛选区、统计卡片、结果表格、操作按钮和状态反馈的协同，使用户在单个模块内即可完成查询、录入、复核与结果输出。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "在页面工程上，系统通过统一字体链、桌面端布局宽度、模块化路由和任务画像驱动的数据结构约束，保证不同产品既具备专属业务表达，又保留稳定的运行和截图效果。"
            )
        )
        self.add_title("后端实现说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "后端采用 FastAPI 提供接口、运行校验和导出服务，并通过任务编排机制串联需求整理、应用构建、运行验证、截图采集、说明书生成、源码文档生成与发布等阶段。这样可以确保页面内容、截图内容和导出材料来源一致，减少交付过程中的信息偏差。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "服务侧重点不仅包括业务接口本身，还包括健康检查、任务状态记录、导出文件登记、截图工件落盘、说明书组装和下载分发等支撑能力，从而形成完整的项目交付闭环。"
            )
        )
        self.add_title("前端工程分层", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "前端工程通常由登录入口、首页工作台、模块页面、公共样式、路由管理和画像数据源等部分构成。登录页负责完成身份进入与演示账号写入，首页负责展示当前产品主题、统计摘要和模块入口，模块页负责承载真实业务数据与主操作流程。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "在真实项目开发中，这种分层方式有利于把页面壳层稳定性、模块业务表达和截图采集一致性拆开治理，既保证系统可以运行，也保证说明书中的页面说明能够准确对应到真实可访问的功能路由。"
            )
        )
        self.add_title("后端服务分层", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "后端服务通常拆分为接口访问层、任务编排层、运行校验层、截图采集层、文档生成层和发布分发层。接口层负责提供任务、工件和时间线访问能力，任务编排层负责推进各阶段状态，文档层负责把页面产物、截图材料和正式说明书组织为统一交付件。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "这种服务分层不是单纯为了代码整洁，更重要的是让问题定位路径足够清晰。例如页面生成异常、截图缺页、说明书过薄或导出文件缺失等问题，都可以回溯到具体阶段并通过日志快速确认根因。"
            )
        )
        self.add_title("任务编排与工件流转", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "从交付流水线看，系统会依次经历需求整理、应用构建、运行验证、页面截图、说明书生成、源码文档生成和导出发布。每个阶段既要产出当前工件，也要为下一个阶段提供可复核的输入，例如截图清单直接影响说明书插图数量，项目画像直接影响页面字段与正文结构。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "在真实项目实施中，这种分阶段工件流转机制可以显著降低返工成本。当某个阶段发现异常时，可以围绕对应清单、日志和产物做定点修复，而不是整体推倒重来。"
            )
        )
        self.add_title("模块实现拆解", level=2)
        for module in self._module_profiles():
            self.add_title(module.get("title", "当前模块"), level=3)
            self.add_paragraph(self._sanitize_doc_text(f"{module.get('title', '当前模块')}在开发时需要同步考虑页面布局、字段组织、筛选逻辑、主操作入口、结果反馈和页面说明生成。"))
            self.add_paragraph(self._module_example_record(module))
            for note in self._module_tech_notes(module):
                self.add_paragraph(note)
            for note in self._module_delivery_notes(module):
                self.add_paragraph(note)
        self.add_title("数据与页面联动说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "系统通过任务画像中的模块列表、字段标题、样例数据、角色列表和业务亮点驱动页面渲染，使首页指标、模块表格、截图说明和说明书正文能够围绕同一套业务语义展开。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "在真实交付过程中，这种数据联动方式可以减少前端页面、截图材料和文档正文之间的语义漂移，提升验收、培训和后续维护的一致性。"
            )
        )
        self.add_title("研发测试与验收情况", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "系统研发阶段同步覆盖页面可访问性检查、关键路由检查、截图质量检查、说明书结构检查和导出物一致性检查。只有页面真实渲染模块字段和样例数据，截图与说明书才能准确反映软件成品质量。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "系统交付核对内容覆盖模块标题、列表字段、数据样例、截图数量、图注描述、角色权限说明和导出文件名称，并结合时间线日志确认各阶段产物均已完成。"
            )
        )

    def generate_delivery_and_acceptance(self) -> None:
        self.add_title("实施交付与验收说明", level=1)
        self.add_title("实施阶段划分", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "正式实施通常可划分为需求确认、原型对齐、页面开发、接口联调、运行验证、截图取证、说明书整理和交付验收等阶段。每个阶段都应输出明确的中间结果，以保证项目过程可追踪、交付边界可确认。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                f"对于{self.product_name}这类真实业务产品，需求确认阶段会同步整理主题对象、角色职责、模块顺序、字段口径和导出材料要求，从而减少后续页面和文档返工。"
            )
        )
        self.add_title("培训与上线说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                f"上线前会围绕{'、'.join(self._role_profiles()[:4])}等角色开展分角色培训，分别说明首页看板、模块入口、关键字段、主操作、异常反馈和结果导出方式，使不同岗位都能够按照各自职责进入系统开展工作。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "培训资料应与说明书、截图和真实页面保持一致，避免培训话术与系统实际界面不一致。对于需要正式申报、归档或交付的软件产品，还应同步整理源码文档、申请表、版本信息和下载包。"
            )
        )
        self.add_title("交付物清单说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "标准交付物通常包括运行中的应用页面、页面截图清单、软件说明书、源码文档、申请表、运行清单、项目画像和发布包。若客户需要正式验收材料，还可补充阶段日志、截图质量记录和版本说明。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "验收环节应把截图数量、说明书页数、关键章节完整度和导出包可下载性作为硬指标；只有同时满足页面可运行、内容可复核和材料可归档，才算真正完成交付。"
            )
        )
        self.add_title("后续迭代说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "后续版本迭代时，项目画像中的模块语义、字段示例和角色分工会先完成同步更新，随后再更新页面、截图和说明书，从而保证版本变化不仅体现在代码中，也完整反映到交付文档与培训材料中。"
            )
        )

    def generate_security_and_maintenance(self) -> None:
        self.add_title("安全、审计与运维说明", level=1)
        self.add_title("权限与访问控制", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                f"{self.product_name}按照账号权限控制页面访问范围，不同账号可在授权范围内查看对应数据并执行相关操作。通过统一登录、页面权限和过程记录，系统能够降低误操作风险并提升结果可追溯性。"
            )
        )
        self.add_title("日志与审计留痕", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "系统在任务执行、页面截图、导出生成和状态切换过程中保留关键事件记录，用于定位异常、解释交付结果和追溯关键节点。对于正式业务模块，也可围绕编号、状态、责任角色、更新时间等字段建立审计维度。"
            )
        )
        self.add_title("运行维护说明", level=2)
        self.add_paragraph(
            self._sanitize_doc_text(
                "运维侧需要重点关注依赖安装、前后端启动、健康检查、截图质量、工件落盘和导出文件发布等环节。若其中任一阶段异常，系统应能够通过任务时间线、阶段状态和日志信息快速定位问题，避免用户误判为长时间卡住。"
            )
        )
        self.add_paragraph(
            self._sanitize_doc_text(
                "在版本迭代过程中，模块标题、页面路由、截图数量、说明书页数和导出内容会同步更新，以确保软件功能与相关说明保持一致。"
            )
        )

    def _guess_usage_steps(self, title: str, meta: dict | None = None) -> list[str]:
        if meta and meta.get("steps"):
            return list(meta["steps"])
        return []

    def _guess_usage_description(self, title: str, elements: list[str], meta: dict | None = None) -> list[str]:
        visible = "、".join(self._sanitize_ui_elements(elements)[:10])
        description = meta.get("description") if meta else None
        primary_action = meta.get("primary_action") if meta else ""
        base = []
        if description:
            base.append(self._sanitize_doc_text(description))
        elif visible:
            base.append(self._sanitize_doc_text(f"{title}围绕{visible}等信息元素组织页面内容，用于承载当前业务主题下的关键处理动作与结果反馈。"))
        else:
            base.append(self._sanitize_doc_text(f"{title}用于承载当前业务主题下的关键处理动作、信息呈现与结果反馈。"))
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
                    f"{title}用于呈现在筛选、聚焦或结果定位条件下的业务处理状态，便于说明同一模块在具体业务条件下的信息组织方式、结果呈现逻辑和处理入口。",
                )
            )
        )
        if elements:
            self.add_paragraph(self._sanitize_doc_text("该功能主要涵盖：" + "、".join(elements[:10]) + "。"))
        else:
            self.add_paragraph("该功能状态下应重点关注筛选条件、结果列表、状态标签和主操作入口。")
        self.add_title("变体页验收说明", level=4)
        for note in self._variant_page_review_notes(title, page_profile):
            self.add_paragraph(note)

    def generate_page_instructions(self, screenshots_meta: list[dict]) -> None:
        self.add_title("软件操作说明", level=1)
        self.add_title("操作说明总述", level=2)
        self.add_paragraph(
            self._profile_text(
                "usage_overview",
                "系统围绕“登录 -> 首页查看 -> 进入目标功能模块 -> 完成录入、查询、统计、审核或配置操作”的基本路径组织主要功能。后续章节将按页面顺序陈述各页面的职责、信息重点与典型操作。",
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

            for paragraph in self._guess_usage_description(title, elements, page_profile):
                self.add_paragraph(paragraph)

            business_value = self._sanitize_doc_text(
                page_profile.get(
                    "business_value",
                    f"{title}对应当前软件中的重点业务环节，用于衔接信息录入、结果查询、状态跟踪与处理反馈。",
                )
            )
            self.add_paragraph(business_value)

            highlights = [
                self._sanitize_doc_text(str(item))
                for item in (page_profile.get("highlights") or [])
                if str(item).strip()
            ]
            if highlights:
                self.add_title("页面重点", level=3)
                for highlight in highlights[:5]:
                    self.add_paragraph(f"- {highlight}")
            elif elements:
                self.add_title("页面重点", level=3)
                self.add_paragraph(self._sanitize_doc_text("本页面重点包括：" + "、".join(elements[:12]) + "。"))

            steps = [self._sanitize_doc_text(step) for step in self._guess_usage_steps(title, page_profile) if step]
            if steps:
                self.add_title("操作流程", level=3)
                for j, step in enumerate(steps, 1):
                    self.add_paragraph(f"{j}. {step}")

    def generate_tech_features(self) -> None:
        self.add_title("软件特点说明", level=1)
        self.add_paragraph(
            self._profile_text(
                "technical_features",
                "本软件采用 B/S 架构，支持主流浏览器访问，具备统一入口、模块化页面、业务记录查询、状态反馈和结果输出等功能特点。",
            )
        )
        self.add_paragraph(
            self._profile_text(
                "technical_feature_detail",
                f"{self.product_name}通过统一的数据组织方式和清晰的模块入口承接各项业务处理，能够在同一系统中完成信息维护、状态查看、结果查询和记录留存。",
            )
        )
        features = self._profile_list("technical_feature_bullets", [
            "采用浏览器访问模式，部署与使用门槛较低",
            "页面结构清晰，功能区分明确，便于快速理解和使用",
            "支持多模块统一访问，有利于集中管理业务数据和配置信息",
            "支持截图、导出、统计和记录留存等常用功能",
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
        selected_optional_modules = set(self._selected_optional_module_keys())
        self.generate_cover()
        self.generate_document_info(screenshots_meta)
        self.generate_overview(prd_summary, modules)
        self.generate_function_structure(modules)
        self.generate_page_instructions(screenshots_meta)
        if "introduction" in selected_optional_modules:
            self.generate_introduction()
        if "system_design" in selected_optional_modules:
            self.generate_system_design(arch_diagram_path)
        if "runtime_environment" in selected_optional_modules:
            self.generate_runtime_environment()
        if "business_flows" in selected_optional_modules:
            self.generate_business_flows()
        if "data_and_output" in selected_optional_modules:
            self.generate_data_and_output()
        if "tech_features" in selected_optional_modules:
            self.generate_tech_features()
        if "security_and_maintenance" in selected_optional_modules:
            self.generate_security_and_maintenance()
        if "version_evolution_and_change_management" in selected_optional_modules:
            self.generate_version_evolution_and_change_management()
        if "appendix" in selected_optional_modules:
            self.generate_appendix()
        return self.doc
