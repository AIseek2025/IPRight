from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.document.manual import OPTIONAL_MANUAL_MODULES, REQUIRED_MANUAL_MODULES

logger = logging.getLogger(__name__)
TEXT_MODEL = "deepseek-v4-flash"
REASONING_MODEL = "deepseek-v4-pro"


@dataclass
class LLMConfig:
    provider: str = "deepseek"
    api_key: str = ""
    api_base: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-pro"
    fallback_model: str = "deepseek-v4-flash"
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class LLMResponse:
    success: bool
    text: str = ""
    structured: dict = field(default_factory=dict)
    error: str = ""


class LLMClient:
    """Unified LLM client supporting OpenAI-compatible APIs."""

    def __init__(self, config: LLMConfig | None = None):
        self.config = config or self._load_config()
        self._client = None

    def _load_config(self) -> LLMConfig:
        api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY", "")
        api_base = os.environ.get("DEEPSEEK_API_BASE") or os.environ.get("OPENAI_API_BASE") or "https://api.deepseek.com"
        model = os.environ.get("LLM_MODEL") or "deepseek-v4-pro"
        fallback = os.environ.get("LLM_FALLBACK_MODEL") or "deepseek-v4-flash"
        return LLMConfig(
            api_key=api_key,
            api_base=api_base,
            model=model,
            fallback_model=fallback,
        )

    @staticmethod
    def _coerce_message_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    chunks.append(str(item.get("text", "")))
                else:
                    chunks.append(str(item))
            return "\n".join(chunk for chunk in chunks if chunk)
        if content is None:
            return ""
        return str(content)

    @staticmethod
    def _escape_string_control_chars(raw: str) -> str:
        """Escape raw control characters that occasionally leak into JSON strings."""
        if not raw:
            return raw

        pieces: list[str] = []
        in_string = False
        escaping = False

        for char in raw:
            if in_string:
                if escaping:
                    pieces.append(char)
                    escaping = False
                    continue
                if char == "\\":
                    pieces.append(char)
                    escaping = True
                    continue
                if char == '"':
                    pieces.append(char)
                    in_string = False
                    continue
                if char == "\n":
                    pieces.append("\\n")
                    continue
                if char == "\r":
                    pieces.append("\\r")
                    continue
                if char == "\t":
                    pieces.append("\\t")
                    continue
                if ord(char) < 0x20:
                    pieces.append(f"\\u{ord(char):04x}")
                    continue
                pieces.append(char)
                continue

            pieces.append(char)
            if char == '"':
                in_string = True

        return "".join(pieces)

    @staticmethod
    def _parse_json_object_content(content: str) -> tuple[dict, str]:
        text = (content or "").strip()
        if not text:
            return {}, "empty response body"

        candidates = [text]
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[0].startswith("```") and lines[-1].strip() == "```":
                candidates.append("\n".join(lines[1:-1]).strip())

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start:end + 1].strip())

        last_error = "JSON object not found"
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError as exc:
                repaired = LLMClient._escape_string_control_chars(candidate)
                if repaired != candidate:
                    try:
                        parsed = json.loads(repaired)
                    except json.JSONDecodeError:
                        last_error = str(exc)
                        continue
                    if isinstance(parsed, dict):
                        return parsed, ""
                    last_error = f"expected JSON object but got {type(parsed).__name__}"
                    continue
                last_error = str(exc)
                continue
            if isinstance(parsed, dict):
                return parsed, ""
            last_error = f"expected JSON object but got {type(parsed).__name__}"

        return {}, last_error

    async def chat(self, messages: list, response_format: str = "text") -> LLMResponse:
        """Send a chat completion request with model fallback."""
        return await self.chat_with_models(
            messages,
            response_format=response_format,
            primary_model=self.config.model,
            fallback_model=self.config.fallback_model,
        )

    async def chat_with_models(
        self,
        messages: list,
        response_format: str = "text",
        *,
        primary_model: str,
        fallback_model: str = "",
        parse_json_response: bool = False,
        max_tokens_override: int | None = None,
        temperature_override: float | None = None,
    ) -> LLMResponse:
        """Send a chat completion request with explicit model routing."""
        if not self.config.api_key:
            return LLMResponse(success=False, error="No LLM API key configured")

        models_to_try = [primary_model]
        if fallback_model and fallback_model != primary_model:
            models_to_try.append(fallback_model)

        last_error = ""
        for model in models_to_try:
            try:
                import httpx

                headers = {
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                }
                api_base = self.config.api_base or "https://api.deepseek.com/v1"

                body = {
                    "model": model,
                    "messages": messages,
                    "temperature": self.config.temperature if temperature_override is None else temperature_override,
                    "max_tokens": self.config.max_tokens if max_tokens_override is None else max_tokens_override,
                }

                if response_format == "json_object":
                    body["response_format"] = {"type": "json_object"}

                async with httpx.AsyncClient(timeout=120) as client:
                    resp = await client.post(
                        f"{api_base}/chat/completions",
                        headers=headers,
                        json=body,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        choice = data["choices"][0]
                        message = choice.get("message", {})
                        content = self._coerce_message_text(message.get("content"))

                        structured = {}
                        if response_format == "json_object" or parse_json_response:
                            structured, parse_error = self._parse_json_object_content(content)
                            if parse_error:
                                logger.warning(
                                    "LLM parse failure metadata: model=%s finish_reason=%s message_keys=%s "
                                    "content_len=%s reasoning_len=%s usage=%s raw_head=%s",
                                    model,
                                    choice.get("finish_reason"),
                                    sorted(message.keys()),
                                    len(content or ""),
                                    len(self._coerce_message_text(message.get("reasoning_content")) or ""),
                                    data.get("usage"),
                                    resp.text[:800],
                                )
                                last_error = f"LLM JSON parse error ({model}): {parse_error}; content={content[:300]}"
                                logger.warning(f"Model {model} failed, trying fallback: {last_error}")
                                continue

                        return LLMResponse(success=True, text=content, structured=structured)
                    elif resp.status_code == 401 or resp.status_code == 403:
                        return LLMResponse(success=False, error=f"LLM auth error ({model}): {resp.text[:200]}")
                    else:
                        last_error = f"LLM error ({model}): {resp.status_code}"
                        logger.warning(f"Model {model} failed, trying fallback: {last_error}")

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Model {model} failed: {e}")

        return LLMResponse(success=False, error=last_error or "All models failed")

    async def generate_prd(
        self,
        keyword: str,
        product_name: str,
        version: str,
        industry: str = "",
        notes: str = "",
        plan_seed: dict | None = None,
    ) -> LLMResponse:
        """Generate a product PRD using LLM."""
        system_prompt = """你是一个产品经理。根据用户提供的关键词，生成一个软件产品 PRD。
原始用户输入是唯一主题源。平台提供的规划种子、视觉画像、运行约束和差异化提示，只能作为辅助约束，不能用来篡改、替换或重解释用户原始需求。
产品形态只能在 `admin_web` 与 `desktop_client` 中二选一，必须根据当前产品标题、关键词和产品类型判断，不得默认所有任务都是后台管理型 Web 应用。
无论选择哪种形态，都必须体现当前行业对象、角色分工、业务流程和页面信息架构的专属特征。
除登录、首页、系统设置等硬性页面外，不得把不同项目都写成“数据管理 / 流程管理 / 报表中心 / 系统设置”这一类通用套板。
PRD 中的核心模块、业务对象、角色职责、页面路由、功能命名、页面重点必须围绕当前任务主题重构，不能只是替换标题变量。
输出必须是 JSON 格式，包含:
{
  "prd_markdown": "完整的PRD Markdown内容",
  "prd_summary": {
    "app_type": "admin_web 或 desktop_client",
    "user_roles": ["管理员角色列表"],
    "core_modules": ["核心功能模块列表"],
    "required_pages": ["需要的页面路由列表"],
    "scene": "对当前产品业务主线的简要描述",
    "industry_scope": "当前产品所属行业和业务范围",
    "core_entities": ["当前产品的核心业务对象"]
  },
  "work_order_markdown": "开发任务书Markdown内容"
}
"""

        plan_seed_text = json.dumps(plan_seed or {}, ensure_ascii=False, indent=2)
        raw_user_request = json.dumps(
            {
                "keyword": keyword,
                "product_name": product_name,
                "version": version,
                "industry": industry or "",
                "notes": notes or "",
            },
            ensure_ascii=False,
            indent=2,
        )
        user_prompt = f"""请为以下产品生成 PRD 和开发任务书：
- 原始用户输入（唯一主题源）:
{raw_user_request}

- 平台辅助约束（仅用于补充结构、运行与交付要求；若与原始用户输入冲突，必须以原始用户输入为准）:
{plan_seed_text}

要求:
1. 必须先判断当前产品应做成 `admin_web` 还是 `desktop_client`，并写入 `prd_summary.app_type`
2. 提供至少 4 个核心功能模块，且模块名必须体现当前业务领域，不得使用空泛套板命名
3. 提供至少 3 个页面路由，且路由应与当前业务模块对应，不得大量复用 /data-list、/workflow 之类的通用路径
4. 提供 demo 账号 (admin/admin123)
5. 所有输出必须是中文
6. 优先吸收“任务专属规划种子”里的核心模块、角色、业务对象和场景线索
7. 必须让当前产品与既有任务明显区分，除硬性规范外不要复用统一模版表达
8. 如果标题或关键词显式包含“客户端、桌面端、工作站、终端”等形态词，应优先考虑 `desktop_client`
9. 必须显式吸收 `project_dna`/`differentiation_hint` 中的业务主线、模块签名和风格线索，重新命名模块、角色职责、页面结构和图文表达
10. 不得沿用历史任务中的行业材料、模块命名、业务文案或说明书句式；即便都包含“调度”等泛词，也必须先根据原始用户输入判断当前任务主题，再全新组织产品内容
11. `prd_summary.scene`、`prd_summary.industry_scope`、`prd_summary.core_entities` 必须来自你对原始用户输入的理解，不能由平台预设直接替代
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return await self.chat_with_models(
            messages,
            response_format="json_object",
            primary_model=TEXT_MODEL,
        )

    async def generate_app_code(
        self, prd: str, work_order: str, app_requirements: dict
    ) -> LLMResponse:
        """Generate application code using LLM."""
        system_prompt = """你是一个资深前端工程师，负责补全软件产品的前端页面源码。
要求：
1. 仅输出 JSON。
2. 技术栈固定：
   - 前端：React + Vite + TypeScript
   - 后端：FastAPI + Python
3. 代码必须可读、结构清晰、注释尽量少。
4. 所有页面标题、按钮、表格列、说明文案使用中文；技术名保留英文原名。
5. 前端允许引用 `./generated/appProfile` 中的 `APP_PROFILE`。
6. 后端骨架、健康检查和基础接口已经预置；除非 `required_files` 明确要求，否则不要输出任何 `backend/` 文件。
7. 不要输出 Markdown 代码块，不要输出解释文字。
8. 请控制思考长度，务必把最终 JSON 写入 `content`。
9. 如果 token 紧张，优先保证 `required_files` 中每个文件都给出最小可运行实现，减少注释和重复样板。
10. 只生成本次 `required_files` 列表中的文件，不要额外输出未请求的文件。
11. `frontend/src/main.tsx` 已经预置并负责挂载唯一的 `BrowserRouter`；生成 `frontend/src/App.tsx` 时不要再次渲染 `BrowserRouter`，只输出 `Routes/Route` 或普通页面组件。
12. 登录态需兼容自动验收：如果前端使用 `localStorage`，应优先读取 `ipright_demo_auth`，并兼容 `token`/`user` 这类键。
13. 页面路由必须与功能页面一一对应，不要只做单页内切换后再把未实现路由重定向到同一页面。
14. 页面布局按桌面截图场景优化，默认面向 1440px 以上宽度；不要把侧栏、标题或按钮文字挤成逐字竖排。
15. 中文界面必须使用稳定的中文字体回退链，不要强制指定缺少中文 glyph 的字体；截图中不能出现方框字。
16. 表格、卡片、筛选区应优先横向排布并保持适中的宽高比例，避免生成过窄侧栏或过高空白页面。
17. 除登录页、首页、系统设置等硬性页面外，不要把不同项目都做成同一套通用后台模板；必须根据当前 `scene`、`industry_scope`、`core_entities`、`focus_terms`、`module_pages`、`experience_blueprint`、`visual_profile` 生成专属布局与文案。
18. 若 `module_pages` 中提供了 `page_variant`，生成页面时必须体现该变体的版面特征和信息组织方式，而不是统一复用同一块页面骨架。
19. 不得把多个模块都写成仅更换标题的“数据管理/流程管理/报表中心”套板页面；按钮、卡片标题、表格结构、说明板块必须与当前模块主题一致。
20. 如果 `app_type` 为 `desktop_client`，界面应体现桌面客户端工作台特征，例如标题栏、工具区、分栏工作区、较高的信息密度，而不是普通网页后台。
21. 不同产品的 UI 视觉风格必须重新设计，禁止所有项目都使用同一组导航色、同一组卡片层级和同一块内容骨架。
22. 模块内容区不要使用“上边界一条高饱和蓝色粗边框”的效果，应采用常规完整边框或轻阴影边框。
23. 必须吸收 `project_dna`、`preset_key`、`topic_label`、`differentiation_hint` 中提供的项目专属线索；即便同属一个行业，也要重构模块布局、卡片语义、分析区块、表格字段和首页叙事。
24. 第三方前端依赖只允许使用当前基础环境已覆盖的包：`react`、`react-dom`、`react-router-dom`、`antd`、`@ant-design/icons`、`@ant-design/pro-components`、`axios`、`dayjs`、`echarts`、`echarts-for-react`；不要引入其他 npm 包或需要额外安装的新依赖。
25. 不要默认输出“左侧深色竖向导航 + 右侧内容区”的通用后台框架，除非当前产品的场景和信息架构明确要求这种布局；必须根据当前产品重新设计整体壳层。
26. 当前输入中的 `raw_user_request` 是唯一主题源，其他画像字段只用于补充结构约束；不要假设存在隐藏的固定 UI 套板、固定页面骨架或历史项目可复用壳层，需为本次任务完整生成 `App.tsx`、登录页、首页、模块页，以及 `required_files` 中列出的任务专属前端支撑文件。
27. 必须落实 `experience_blueprint.navigation_variant` 与 `experience_blueprint.shell_layout_hint` 指定的壳层方向；若画像提示顶部导航、指挥条、分析画布、分段导航或协同工作区，则不得退回统一左侧竖栏后台。
28. 如果 `validation_hints` 或 `invalid_core_previews` 出现在输入约束中，说明上一版核心页未通过校验；这次必须逐条修正这些问题，并优先重写 `required_files` 中列出的核心页。
29. 不得挪用任何历史任务的行业素材、模块标题、表格字段、卡片叙事或业务步骤；遇到“调度”“监控”“协同”等跨行业共性词时，必须优先以当前 `preset_key`、`scene`、`industry_scope` 和 `core_entities` 重新建模。
30. 如果 `module_pages` 中提供了 `rows`、`table_headers`、`filter_placeholder` 等任务样例数据，模块页必须直接复用这些真实业务样例组织表格、卡片和筛选区，不能另造 `mockData`、`testData`、“张三/李四/王五”或一眼可见的假数据。
31. `App.tsx` 必须从 `./pages/*` 导入并挂接真实模块页，不得在 `App.tsx` 内联定义 `ModuleShell`、占位页或只显示 0 值统计卡的伪页面。

输出 JSON 结构：
{
  "files": {
    "frontend/src/App.tsx": "文件内容",
    "frontend/src/pages/Login.tsx": "文件内容",
    "frontend/src/pages/Dashboard.tsx": "文件内容",
    "frontend/src/pages/SomePage.tsx": "文件内容"
  }
}
"""

        user_prompt = (
            f"PRD:\n{prd}\n\n"
            f"开发任务书:\n{work_order}\n\n"
            f"应用约束:\n{json.dumps(app_requirements, ensure_ascii=False, indent=2)}\n\n"
            "请基于这些信息生成完整源码文件。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return await self.chat_with_models(
            messages,
            response_format="json_object",
            primary_model=REASONING_MODEL,
            max_tokens_override=12000,
            temperature_override=0.2,
        )

    async def generate_page_description(self, page_title: str, route: str, elements: list[str], model: str = "") -> LLMResponse:
        """Generate a page description for the software manual.
        If model is specified, use that model instead of the default."""
        system_prompt = """你是一个技术文档撰写者。根据页面信息和可见元素，为该页面撰写软件说明书中的操作说明。
输出 JSON: {"caption": "图注", "description": "50-120字页面说明", "steps": ["步骤1", "步骤2"]}
"""

        user_prompt = f"""页面名称: {page_title}
页面路由: {route}
可见元素: {', '.join(elements[:15])}

请生成该页面的操作说明。"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return await self.chat_with_models(
            messages,
            response_format="json_object",
            primary_model=model or TEXT_MODEL,
        )

    async def review_manual_descriptions(self, descriptions_json: str) -> LLMResponse:
        """Use deepseek-v4-pro to review all page descriptions for consistency and quality."""
        system_prompt = """你是一位资深技术文档审核专家。审核以下软件说明书的所有页面描述。
检查:
1. 各页面描述之间的术语一致性
2. 操作步骤的准确性和完整性
3. 图注与页面名称的对应关系
4. 整体文档的专业性和可读性

输出 JSON: {"approved": true/false, "issues": ["发现的问题"], "suggestions": ["改进建议"]}
"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"请审核以下软件说明书的页面描述:\n\n{descriptions_json}"},
        ]
        return await self.chat_with_models(
            messages,
            response_format="json_object",
            primary_model=TEXT_MODEL,
        )

    async def review_manual_content(self, descriptions_json: str) -> LLMResponse:
        """Alias for review_manual_descriptions."""
        return await self.review_manual_descriptions(descriptions_json)

    async def _generate_manual_overview_content(
        self,
        *,
        product_name: str,
        version: str,
        profile: dict,
        prd_summary: dict,
        module_profiles: list[dict],
        screenshot_briefs: list[dict],
    ) -> LLMResponse:
        system_prompt = """你是一位中文软件说明书撰写专家。请基于给定产品信息，输出软件说明书正文所需 JSON。
要求：
1. 全部使用中文撰写，技术名保留英文原名，如 FastAPI、React、TypeScript、PostgreSQL。
2. 不得出现任何模型、供应商或大模型产品名称。
3. 文风自然、专业，避免标题与关键词机械重复。
4. 不要在多个模块里重复使用同一句骨架；每个模块都要写出自己的业务对象、处理动作和输出结果。
5. 优先复用输入中的 module_profiles、screenshots、user_roles 信息，写出与当前产品强绑定的正文。
6. 仅输出 JSON，不要输出 Markdown。
7. 必须吸收 `project_dna` 中的模块签名、业务主线和架构风格，不得把不同项目的说明书写成同一套模板章节句式。
8. `required_manual_modules` 是系统固定必选章节，你无需改动；你需要从 `optional_manual_modules` 备选池中挑选 4 到 7 个最适合当前产品的模块 key，填入 `selected_optional_modules`，让不同产品的说明书扩展章节可以有变化。
9. `selected_optional_modules` 中的 key 必须来自 `optional_manual_modules`，且优先覆盖产品、数据、研发、实施、测试、运维等不同维度，避免每次都选择同一组模块。

输出 JSON 结构：
{
  "development_background": "",
  "development_purpose": "",
  "industry_scope": "",
  "hardware_environment": "",
  "runtime_hardware_environment": "",
  "development_os": "",
  "runtime_platform": "",
  "support_environment": "",
  "development_tools": "",
  "overview_product_intro": "",
  "overview_version_summary": "",
  "system_architecture_summary": "",
  "system_pipeline_summary": "",
  "development_tech_overview": "",
  "development_language_frontend": "",
  "development_language_backend": "",
  "tech_selection_frontend": "",
  "tech_selection_backend": "",
  "tech_selection_data": "",
  "main_functions": "",
  "function_elements_summary": "",
  "business_flow_basic": "",
  "business_flow_materials": "",
  "business_flow_module_collaboration": "",
  "usage_overview": "",
  "technical_features": "",
  "technical_feature_bullets": ["", "", "", ""],
  "role_permissions": {"角色名": "权限说明"},
  "selected_optional_modules": ["optional_key_a", "optional_key_b", "optional_key_c", "optional_key_d"],
  "module_overrides": [
    {"title": "", "description": "", "highlights": ["", ""], "primary_action": ""}
  ]
}
"""
        user_payload = {
            "product_name": product_name,
            "version": version,
            "keyword": profile.get("keyword", product_name),
            "topic_label": profile.get("topic_label", product_name),
            "scene": profile.get("scene", ""),
            "industry_scope": profile.get("industry_scope", ""),
            "software_category": profile.get("software_category", ""),
            "project_dna": profile.get("project_dna", {}),
            "user_roles": profile.get("user_roles", []),
            "core_modules": [module.get("title", "") for module in profile.get("modules", []) if module.get("title")],
            "module_profiles": module_profiles,
            "required_pages": prd_summary.get("required_pages", []),
            "screenshots": screenshot_briefs,
            "required_manual_modules": REQUIRED_MANUAL_MODULES,
            "optional_manual_modules": OPTIONAL_MANUAL_MODULES,
        }
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)},
        ]
        return await self.chat_with_models(
            messages,
            response_format="json_object",
            primary_model=TEXT_MODEL,
            max_tokens_override=5200,
            temperature_override=0.3,
        )

    async def generate_manual_content(
        self,
        *,
        product_name: str,
        version: str,
        profile: dict,
        prd_summary: dict,
        screenshots_meta: list[dict],
    ) -> LLMResponse:
        """Generate manual body content using the text model."""
        module_titles = [module.get("title", "") for module in profile.get("modules", []) if module.get("title")]
        module_profiles = [
            {
                "title": module.get("title", ""),
                "route": module.get("route", ""),
                "primary_action": module.get("primary_action", ""),
                "description": module.get("description", ""),
                "highlights": list(module.get("highlights", [])[:3]),
                "table_headers": list(module.get("table_headers", [])[:6]),
            }
            for module in profile.get("modules", [])[:8]
        ]
        screenshot_briefs = [
            {
                "page_title": item.get("page_title", ""),
                "route": item.get("route", ""),
                "elements": list(item.get("elements", [])[:12]),
            }
            for item in screenshots_meta[:12]
        ]
        overview_resp = await self._generate_manual_overview_content(
            product_name=product_name,
            version=version,
            profile=profile,
            prd_summary=prd_summary,
            module_profiles=module_profiles,
            screenshot_briefs=screenshot_briefs[:6],
        )

        combined: dict[str, Any] = {}
        if overview_resp.success and overview_resp.structured:
            combined.update(overview_resp.structured)

        page_overrides: list[dict[str, Any]] = []
        for item in screenshot_briefs:
            page_title = str(item.get("page_title", "")).strip()
            route = str(item.get("route", "")).strip()
            elements = item.get("elements", [])
            if not page_title:
                continue
            page_resp = await self.generate_page_description(page_title, route, elements, model=TEXT_MODEL)
            if not page_resp.success or not page_resp.structured:
                continue
            page_overrides.append(
                {
                    "page_title": page_title,
                    "route": route,
                    "caption": str(page_resp.structured.get("caption", "")).strip(),
                    "description": str(page_resp.structured.get("description", "")).strip(),
                    "steps": [
                        str(step).strip()
                        for step in (page_resp.structured.get("steps") or [])
                        if str(step).strip()
                    ],
                }
            )

        if page_overrides:
            combined["page_overrides"] = page_overrides

        if combined:
            return LLMResponse(success=True, structured=combined, text=json.dumps(combined, ensure_ascii=False))

        return overview_resp


def get_llm_client() -> LLMClient:
    return LLMClient()
