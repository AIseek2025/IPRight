from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from app.services.document.manual import OPTIONAL_MANUAL_MODULES, REQUIRED_MANUAL_MODULES

logger = logging.getLogger(__name__)
TEXT_MODEL = "qwen3.7-max"
REASONING_MODEL = "qwen3.7-max"
DEFAULT_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass
class LLMConfig:
    provider: str = "dashscope"
    api_key: str = ""
    api_base: str = DEFAULT_API_BASE
    model: str = REASONING_MODEL
    fallback_model: str = TEXT_MODEL
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
        api_key = (
            os.environ.get("DASHSCOPE_API_KEY")
            or os.environ.get("DEEPSEEK_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("LLM_API_KEY", "")
        )
        api_base = (
            os.environ.get("DASHSCOPE_API_BASE")
            or os.environ.get("DEEPSEEK_API_BASE")
            or os.environ.get("OPENAI_API_BASE")
            or DEFAULT_API_BASE
        )
        model = os.environ.get("LLM_MODEL") or REASONING_MODEL
        fallback = os.environ.get("LLM_FALLBACK_MODEL") or TEXT_MODEL
        return LLMConfig(
            provider=os.environ.get("LLM_PROVIDER") or "dashscope",
            api_key=api_key,
            api_base=api_base.strip().strip("`").strip().strip('"').strip("'"),
            model=model,
            fallback_model=fallback,
        )

    @staticmethod
    def _should_enable_thinking(model: str) -> bool:
        normalized = (model or "").strip().lower()
        return normalized.startswith("qwen")

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
                api_base = (self.config.api_base or DEFAULT_API_BASE).rstrip("/")

                body = {
                    "model": model,
                    "messages": messages,
                    "temperature": self.config.temperature if temperature_override is None else temperature_override,
                    "max_tokens": self.config.max_tokens if max_tokens_override is None else max_tokens_override,
                }

                if response_format == "json_object":
                    body["response_format"] = {"type": "json_object"}
                if self._should_enable_thinking(model):
                    body["enable_thinking"] = True

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
        system_prompt = """你是一个资深产品负责人。请直接根据当前任务的原始需求，独立完成一个软件产品的 PRD 和开发任务书。
原始用户输入是唯一主题源。平台提供的规划种子、视觉画像、运行约束和差异化提示只用于补充信息，不能主导产品定位、模块命名、页面结构或业务主线。
你必须把当前任务当成一个全新产品来理解和规划，自主完成模块拆分、角色设计、页面路由和业务流程，不得复用既有项目的行业套话、模块命名或后台模板思路。
产品形态只能在 `admin_web` 与 `desktop_client` 中二选一，必须根据当前产品标题、关键词和产品类型判断，不得默认所有任务都是后台管理型 Web 应用。
无论选择哪种形态，都必须体现当前行业对象、角色分工、业务流程和页面信息架构的专属特征。
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
2. 提供至少 4 个核心功能模块，但模块数量、命名方式和边界划分必须服务于当前产品，不得机械套用固定模块池
3. 提供至少 3 个页面路由，且页面路由、信息架构和功能分层必须贴合当前产品主题，不得大量复用 `/data-list`、`/workflow` 一类通用路径
4. 提供 demo 账号 (admin/admin123)
5. 所有输出必须是中文
6. 如果标题或关键词显式包含“客户端、桌面端、工作站、终端”等形态词，应优先考虑 `desktop_client`
7. 必须显式吸收 `raw_user_request`、`project_dna`、`differentiation_hint` 中的任务线索，但不得把平台建议直接照搬为模块标题或正文段落
8. `prd_summary.scene`、`prd_summary.industry_scope`、`prd_summary.core_entities` 必须来自你对原始用户输入的理解，不能由平台预设直接替代
9. 不得沿用历史任务中的行业材料、模块命名、业务文案、说明书句式或固定后台壳层思路
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return await self.chat_with_models(
            messages,
            response_format="json_object",
            primary_model=REASONING_MODEL,
            max_tokens_override=9000,
            temperature_override=0.6,
        )

    async def generate_app_code(
        self, prd: str, work_order: str, app_requirements: dict
    ) -> LLMResponse:
        """Generate application code using LLM."""
        system_prompt = """你是当前任务唯一的前端主创工程师，负责从零完成本次软件产品的前端页面源码。
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
8. 只生成本次 `required_files` 列表中的文件，不要额外输出未请求的文件。
9. `frontend/src/main.tsx` 已经预置并负责挂载唯一的 `BrowserRouter`；生成 `frontend/src/App.tsx` 时不要再次渲染 `BrowserRouter`，只输出 `Routes/Route` 或普通页面组件。
10. 登录态需兼容自动验收：如果前端使用 `localStorage`，应优先读取 `ipright_demo_auth`，并兼容 `token`/`user` 这类键。
11. 页面路由必须与功能页面一一对应，不要把未实现路由全部重定向到同一页面。
12. 中文界面必须使用稳定的中文字体回退链，不要强制指定缺少中文 glyph 的字体；截图中不能出现方框字。
13. 第三方前端依赖只允许使用当前基础环境已覆盖的包：`react`、`react-dom`、`react-router-dom`、`antd`、`@ant-design/icons`、`@ant-design/pro-components`、`axios`、`dayjs`、`echarts`、`echarts-for-react`；不要引入其他 npm 包或需要额外安装的新依赖。
14. 当前输入中的 `raw_user_request` 是唯一主题源，其他画像字段只用于补充结构约束；必须围绕当前任务重新设计整体壳层、页面节奏、信息分区、字段语义和业务叙事。
15. 除运行兼容性约束外，不存在隐藏的固定 UI 模板、固定页面骨架或历史项目可复用壳层；你需要把这次任务当成一次全新产品设计与实现。
16. 如果 `module_pages` 中提供了 `rows`、`table_headers`、`filter_placeholder` 等任务样例数据，模块页必须直接复用这些真实业务样例组织表格、卡片和筛选区，不能另造 `mockData`、`testData`、“张三/李四/王五”一类明显假数据。
17. 如果 `validation_hints`、`invalid_core_previews` 或 `invalid_module_previews` 出现在输入约束中，说明上一版页面未通过校验；这次必须逐条修正这些问题，并优先重写 `required_files` 中列出的对应页面，不得沿用旧骨架。
18. 请主动拉开登录页、首页、模块页之间的视觉与信息结构差异，让它们共同服务当前任务，而不是复用统一后台套板。

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
            max_tokens_override=16000,
            temperature_override=0.65,
        )

    async def generate_page_description(self, page_title: str, route: str, elements: list[str], model: str = "") -> LLMResponse:
        """Generate a page description for the software manual.
        If model is specified, use that model instead of the default."""
        system_prompt = """你是一位企业软件说明书撰写专家，当前正在为企业准备提交给版权局的软件著作权申请材料。
写作前提：
1. 必须以企业申报软件著作权的正式口吻撰写，目标是陈述软件产品设计、功能构成、页面用途和处理流程等客观事实。
2. 页面标题已经出现在对应图片上方，因此不要再使用“该截图展示了”“截图中重点可见”“从截图可以看出”“下图所示”等围绕截图本身的提示语。
3. 描述应直接围绕当前标题所代表的功能展开，使用“本功能用于……”“系统提供……”“该页面支持……”这类陈述式表达。
4. 不得写成面向终端用户的口语化教程，不要使用“你可以”“用户只需”“点击这里即可”等提示式措辞。
5. 不得出现 AI、自动生成、模型、供应商、平台自动采集等表述。
6. 当前文档属于企业提交给版权局的软件产品说明书/操作手册，不是给研发或测试团队的建议书；不得输出“建议先”“验收时应”“测试建议”“优化建议”等建议式措辞。
输出 JSON: {"caption": "图注", "description": "80-180字页面说明", "steps": ["步骤1", "步骤2", "步骤3"], "highlights": ["页面重点1", "页面重点2"]}
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
            temperature_override=0.6,
        )

    async def review_manual_descriptions(self, descriptions_json: str) -> LLMResponse:
        """Use the configured LLM to review all page descriptions for consistency and quality."""
        system_prompt = """你是一位资深企业技术文档审核专家。当前文档将用于版权局软件著作权申请，请审核以下软件说明书的所有页面描述。
检查:
1. 各页面描述之间的术语一致性
2. 操作步骤的准确性和完整性
3. 图注与页面名称的对应关系
4. 整体文档的专业性和可读性
5. 是否存在“该截图展示了”“截图中重点可见”“从截图可以看出”等不适合软著申报的措辞
6. 是否以企业陈述软件设计与功能事实的正式口吻撰写
7. 是否出现“建议在研发阶段……”“验收时应重点核对……”“功能测试建议”“后续迭代建议”等建议式标题或正文

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
        system_prompt = """你是一位中文软件说明书撰写专家。当前说明书将由企业提交给版权局，用于申请软件著作权。请基于给定产品信息，输出软件说明书正文所需 JSON。
要求：
1. 全部使用中文撰写，技术名保留英文原名，如 FastAPI、React、TypeScript、PostgreSQL。
2. 不得出现任何模型、供应商或大模型产品名称。
3. 文风自然、专业，避免标题与关键词机械重复。
4. 不要在多个模块里重复使用同一句骨架；每个模块都要写出自己的业务对象、处理动作和输出结果。
5. 优先复用输入中的 module_profiles、screenshots、user_roles 信息，写出与当前产品强绑定的正文。
6. 仅输出 JSON，不要输出 Markdown。
7. 必须吸收 `project_dna` 中的模块签名、业务主线和架构风格，不得把不同项目的说明书写成同一套模板章节句式。
8. `required_manual_modules` 是系统固定必选章节，你无需改动；你需要从 `optional_manual_modules` 备选池中挑选 4 到 7 个最适合当前产品的模块 key，填入 `selected_optional_modules`，让不同产品的说明书扩展章节明显分化。
9. `selected_optional_modules` 中的 key 必须来自 `optional_manual_modules`，且优先覆盖产品、数据、研发、实施、测试、运维等不同维度，避免每次都选择同一组模块。
10. 必须以企业身份撰写，用于正式陈述软件产品设计、功能结构、页面用途、业务流程和技术实现事实，不得写成面向终端用户的营销文案、培训话术或聊天式说明。
11. 页面标题与图片已在文档结构中给出，正文和页面说明里不要再使用“该截图展示了”“截图中重点可见”“下图所示”“从截图可以看出”等围绕截图本身的提示语，应直接进入功能陈述。
12. 应优先使用“本软件提供……”“系统实现了……”“该功能用于……”“该页面支持……”等企业陈述式表达，避免“你可以”“用户只需”“建议先点击”“通过截图可见”等指导式或观察式措辞。
13. 该文档属于企业提交给版权局了解项目真实开发情况的软件产品说明书/操作手册，不是模型给团队出的研发建议书、测试建议书、部署建议书、优化迭代建议书或验收建议书。
14. 不得出现“建议在研发阶段……”“验收时应重点核对……”“建议围绕……开展培训”“后续迭代建议”“功能测试建议”“研发测试与验收建议”这类面向团队的建议式标题或正文；相关内容如确需体现，必须改写为当前软件已经采用的设计、已有的功能机制、既定的检查项、既有的角色分工或正式交付内容。
15. 必须始终以当前产品自身为叙述主体，围绕本产品当前页面、模块、字段、角色、流程、截图、导出物和技术实现做事实性描述，不得把模型自己写成评审者、顾问、实施教练或测试负责人。

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
  "page_style_summary": "",
  "usage_flow_summary": "",
  "module_overrides": [
    {"title": "", "description": "", "highlights": ["", ""], "primary_action": "", "business_value": ""}
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
            "raw_user_request": profile.get("raw_user_request", {}),
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
            temperature_override=0.6,
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
                    "highlights": [
                        str(item).strip()
                        for item in (page_resp.structured.get("highlights") or [])
                        if str(item).strip()
                    ],
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
