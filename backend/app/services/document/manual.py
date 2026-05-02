from __future__ import annotations

import os
import re
import unicodedata

from docx import Document
from docx.shared import Pt

from app.services.document.base import WordTemplateBase


class SoftwareManualGenerator(WordTemplateBase):
    def __init__(
        self,
        product_name: str,
        version: str,
        doc: Document | None = None,
    ):
        super().__init__(doc)
        self.product_name = product_name
        self.version = version

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

    def generate_document_info(self) -> None:
        self.add_title("文档说明", level=1)
        self.add_paragraph(f"本文档为 {self.product_name} {self.version} 的软件说明书/操作手册。")
        self.add_paragraph("文档内容涵盖引言、系统设计、运行环境、功能结构、软件使用说明、技术特点及常见问题。")
        self.add_paragraph("文档用于帮助使用人员、管理人员与实施人员快速理解软件功能结构、运行方式和实际操作路径。")

    def generate_introduction(self) -> None:
        self.add_title("引言", level=1)
        self.add_title("开发背景", level=2)
        self.add_paragraph(f"{self.product_name} 面向企事业单位的信息化管理场景，用于解决日常业务数据分散、设备状态难以统一掌握、管理流程缺乏集中入口等问题。")
        self.add_title("开发目的", level=2)
        self.add_paragraph("本软件通过统一的业务首页、数据管理、报表统计、告警查看与系统设置模块，为使用单位提供集中、清晰、易于维护的业务管理入口，提升信息查询效率与日常管理规范性。")
        self.add_title("适用领域", level=2)
        self.add_paragraph("本软件适用于园区管理、设备管理、后台信息维护、通用业务数据管理等需要统一管理平台的场景，也适用于具有登录、首页、列表、报表、告警、设置等典型后台系统需求的项目。")
        self.add_title("适用对象", level=2)
        self.add_paragraph("本文档适用于系统使用人员、系统管理人员、项目实施人员和日常维护人员，用于指导软件理解、部署准备、功能认知和实际操作。")

    def generate_overview(self, prd_summary: dict | None = None, modules: list[str] | None = None) -> None:
        self.add_title("软件概述", level=1)
        self.add_title("产品简介", level=2)
        self.add_paragraph(f"{self.product_name} 是一套面向业务管理的 Web 软件系统，支持登录认证、首页展示、数据管理、统计分析、告警查看及系统设置等主要功能。")
        self.add_paragraph(f"当前软件版本为 {self.version}。系统强调页面清晰、操作明确、功能分区稳定，便于用户快速上手和持续使用。")
        self.add_title("软件主要功能", level=2)
        module_items = modules or (prd_summary or {}).get("core_modules") or ["登录认证", "系统首页", "用户管理", "设备管理", "报表统计", "告警中心", "系统设置"]
        for mod in module_items:
            self.add_paragraph(f"- {mod}")
        if prd_summary and prd_summary.get("user_roles"):
            self.add_title("使用角色", level=2)
            for role in prd_summary["user_roles"]:
                self.add_paragraph(f"- {role}")

    def generate_runtime_environment(self) -> None:
        self.add_title("开发运行环境 / 软件适配环境", level=1)
        self.add_title("硬件环境", level=2)
        self.add_paragraph("CPU: 2 核及以上")
        self.add_paragraph("内存: 2GB 及以上")
        self.add_paragraph("磁盘: 10GB 及以上可用空间")
        self.add_title("软件环境", level=2)
        self.add_paragraph("操作系统: Linux / Windows / macOS")
        self.add_paragraph("浏览器: Chrome 90+, Edge 90+, Firefox 88+")
        self.add_paragraph("服务端: Python 3.11+, Node.js 18+")
        self.add_title("适配说明", level=2)
        self.add_paragraph("软件采用浏览器访问方式，建议在主流桌面浏览器环境中使用。系统页面面向常见办公显示分辨率设计，在常规后台管理场景下具备良好的适配性和可读性。")

    def generate_function_structure(self, modules: list[str] | None = None) -> None:
        self.add_title("功能结构说明", level=1)
        modules = modules or ["登录认证", "仪表盘/首页", "用户管理", "设备管理", "报表统计", "告警管理", "系统设置"]
        descriptions = {
            "登录认证": "负责用户身份校验和系统入口控制，确保不同角色在授权范围内使用系统。",
            "仪表盘/首页": "集中展示系统关键指标、近期状态和重要数据摘要，便于用户快速掌握整体运行情况。",
            "用户管理": "提供用户信息查看、维护、状态管理等功能，用于支撑基础账号管理。",
            "设备管理": "用于维护设备基础信息、运行状态和位置等内容，便于设备台账统一管理。",
            "报表统计": "用于集中展示统计结果、业务分析数据和导出相关信息，满足管理分析需求。",
            "告警管理": "用于查看异常告警、状态变化和待处理事项，便于及时响应问题。",
            "系统设置": "用于维护系统基础参数、通知策略和通用配置。",
        }
        for mod in modules:
            self.add_title(mod, level=2)
            self.add_paragraph(descriptions.get(mod, f"{mod}模块提供完整的业务管理和操作支持能力。"))

    def _guess_usage_steps(self, title: str) -> list[str]:
        defaults = {
            "登录页": ["输入系统提供的用户名和密码。", "点击“登录”按钮进入系统。", "登录成功后跳转至系统首页。"],
            "系统首页": ["进入系统首页后查看顶部和主体区域的概览信息。", "根据首页导航或菜单进入对应功能模块。", "结合首页摘要信息快速定位待处理内容。"],
            "用户管理": ["进入用户管理页面查看用户列表。", "通过新增、编辑、删除等操作维护用户信息。", "结合状态、角色和联系方式等字段完成日常管理。"],
            "设备管理": ["进入设备管理页面查看设备清单。", "根据编号、名称、类型和位置查询设备信息。", "根据设备状态开展维护、更新或核查工作。"],
            "报表统计": ["进入报表统计页面查看业务分析结果。", "根据报表类别和完成状态识别重点数据。", "结合统计结果辅助日常管理和决策分析。"],
            "设备告警": ["进入告警页面查看当前异常或历史告警记录。", "根据告警级别和处理状态判断优先级。", "结合告警内容安排后续处理工作。"],
            "系统设置": ["进入系统设置页面查看基础配置。", "根据实际需要调整系统名称、通知和通用参数。", "保存设置后确认页面反馈信息。"],
        }
        return defaults.get(title, ["进入页面后查看主要信息区域。", "按页面中的按钮、输入项和列表完成操作。", "根据结果反馈确认操作是否成功。"])

    def _guess_usage_description(self, title: str, elements: list[str]) -> list[str]:
        visible = "、".join(self._sanitize_ui_elements(elements)[:8])
        base = [
            self._sanitize_doc_text(f"{title}用于承载与该业务主题相关的主要操作和信息展示，是用户完成日常业务处理的重要页面。"),
            self._sanitize_doc_text(f"页面中通常可以看到{visible or '标题、按钮、输入项、列表和状态信息'}等关键元素，用户可围绕这些元素完成查看、维护、查询或配置操作。"),
        ]
        detail_map = {
            "登录页": "用户首先在该页面完成身份验证，输入正确账号和密码后即可进入系统，是整个软件的统一访问入口。",
            "系统首页": "该页面汇总展示系统核心数据、近期动态或常用入口，适合作为用户进入系统后的第一观察界面。",
            "用户管理": "该页面重点用于用户资料的集中维护和状态管理，便于统一管理账号、角色与联系方式等信息。",
            "设备管理": "该页面重点展示设备台账信息，帮助管理人员从设备编号、名称、类型、位置和状态等维度进行核查。",
            "报表统计": "该页面用于集中展示统计结果和分析信息，帮助用户从整体上掌握业务运行情况。",
            "设备告警": "该页面用于识别异常信息和待处理事项，帮助用户快速发现高优先级问题并进行处置。",
            "系统设置": "该页面用于维护系统基础参数和通用配置，确保软件运行方式符合实际管理要求。",
        }
        base.append(self._sanitize_doc_text(detail_map.get(title, "该页面用于承载对应功能模块的主要操作流程，帮助用户在统一界面内完成具体业务处理。")))
        return base

    def generate_page_instructions(self, screenshots_meta: list[dict]) -> None:
        self.add_title("软件使用说明", level=1)
        self.add_title("使用说明总述", level=2)
        self.add_paragraph("用户进入系统后，可按照“登录 -> 首页查看 -> 进入目标功能模块 -> 完成录入、查询、统计或设置操作”的基本路径开展使用。以下内容按照页面顺序给出截图、功能讲解和详细操作说明。")

        self.add_title("主要页面操作说明", level=2)
        if not screenshots_meta:
            self.add_paragraph("（待截图完成后自动生成页面操作说明）")
            return

        for i, meta in enumerate(screenshots_meta):
            title = meta.get("page_title", f"页面 {i+1}")
            caption = meta.get("caption", "") or meta.get("suggested_caption", "") or f"图{i + 1} {title}"
            steps = meta.get("steps", []) or self._guess_usage_steps(title)
            image_path = meta.get("image_path", "")
            elements = self._sanitize_ui_elements(meta.get("elements", []))

            self.add_title(title, level=2)

            if image_path and os.path.exists(image_path):
                self.add_image(image_path, width_inches=6.0)
                self.add_caption(caption)

            self.add_title("功能讲解", level=3)
            for paragraph in self._guess_usage_description(title, elements):
                self.add_paragraph(paragraph)

            self.add_title("详细操作说明", level=3)
            for j, step in enumerate(steps, 1):
                self.add_paragraph(f"{j}. {step}")

            self.add_title("页面要点", level=3)
            if elements:
                self.add_paragraph(self._sanitize_doc_text("本页面关键可见元素包括：" + "、".join(elements[:12]) + "。"))
            else:
                self.add_paragraph("本页面应重点关注标题区、功能按钮区、数据展示区和操作反馈区。")

    def generate_tech_features(self) -> None:
        self.add_title("技术特点说明", level=1)
        features = [
            "采用 B/S 架构，支持主流浏览器访问",
            "页面结构清晰，功能区分明确，便于用户快速定位目标操作",
            "支持多模块统一访问，有利于集中管理业务数据和配置信息",
            "支持多用户并发访问",
            "采用角色权限控制，保证数据安全",
            "支持统计分析、告警查看和基础配置等典型后台管理能力",
        ]
        for f in features:
            self.add_paragraph(f"- {f}")

    def generate_faq(self) -> None:
        self.add_title("常见问题", level=1)
        faqs = [
            ("Q: 推荐使用哪种浏览器？", "A: 推荐使用 Chrome 90+ 或 Edge 90+ 浏览器。"),
            ("Q: 忘记密码怎么办？", "A: 请联系系统管理员重置密码。"),
            ("Q: 系统支持哪些分辨率？", "A: 建议使用 1440x900 及以上分辨率。"),
        ]
        for q, a in faqs:
            self.add_paragraph(q, bold=True)
            self.add_paragraph(a)

    def generate_system_design(self, arch_diagram_path: str = "") -> None:
        self.add_title("开发设计 / 系统设计", level=1)
        self.add_title("系统总体架构", level=2)
        self.add_paragraph(f"{self.product_name} 采用浏览器访问的软件架构，由页面展示层、业务处理层和数据存储层组成。用户通过浏览器进入系统后，可完成登录、首页查看、业务管理、统计分析、告警查看和参数设置等典型操作。")
        self.add_paragraph("系统整体上强调模块清晰、页面稳定、数据入口统一，便于在一个平台中集中完成常见的后台管理工作。")
        self.add_title("开发技术说明", level=2)
        self.add_paragraph("软件采用前后端分层设计思路，页面层负责交互展示和操作入口，后端层负责数据处理、业务校验与接口输出，数据层负责信息保存和状态记录。")
        self.add_paragraph("这种分层设计有利于功能扩展、维护管理和模块化实施，也便于后续围绕用户、设备、报表、告警和系统设置等模块持续增加功能。")
        self.add_title("开发语言说明", level=2)
        self.add_paragraph("本软件前端页面部分采用 TypeScript / JavaScript 进行开发，用于实现页面结构、交互逻辑和浏览器端功能。")
        self.add_paragraph("本软件后端服务部分采用 Python 进行开发，用于完成接口服务、业务处理、数据组织和系统管理相关功能。")
        self.add_title("技术选型说明", level=2)
        self.add_paragraph("页面展示层采用 React 组件化方式构建，以便保持页面结构清晰、交互逻辑稳定并便于后续维护。")
        self.add_paragraph("后端服务层采用 FastAPI 构建接口服务，以支持页面访问、数据处理和业务功能调用。")
        self.add_paragraph("数据存储层支持 PostgreSQL 与 SQLite 两类数据库，用于满足不同环境下的数据保存和读取需求。")
        self.add_title("系统架构图", level=2)

        if arch_diagram_path and os.path.exists(arch_diagram_path):
            self.add_image(arch_diagram_path, width_inches=6.0)
            self.add_caption(f"图1：{self.product_name}系统架构图")
        else:
            self.add_paragraph("（系统架构图待生成后插入）")

        self.add_title("软件核心功能 / 功能元素", level=2)
        self.add_paragraph("软件核心功能包括登录访问、首页概览、用户管理、设备管理、报表统计、告警查看和系统设置。")
        self.add_paragraph("从功能元素上看，系统主要由页面导航、功能按钮、数据列表、表单输入、统计摘要、状态标识和系统设置项等部分组成。")

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

        self.generate_cover()
        self.generate_document_info()
        self.generate_introduction()
        self.generate_system_design(arch_diagram_path)
        self.generate_overview(prd_summary, modules)
        self.generate_runtime_environment()
        self.generate_function_structure(modules)
        self.generate_page_instructions(screenshots_meta or [])
        self.generate_tech_features()
        self.generate_faq()

        return self.doc
