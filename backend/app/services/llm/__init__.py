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
        system_prompt = """你负责根据用户原始输入生成一个正式软件产品的 PRD 和开发任务书。
只使用原始输入理解产品，不要引入平台模板、行业套话、通用后台骨架或额外假设。
仅输出 JSON，结构如下：
{
  "prd_markdown": "完整 PRD Markdown",
  "prd_summary": {
    "app_type": "admin_web 或 desktop_client",
    "user_roles": ["角色列表"],
    "core_modules": ["核心模块列表"],
    "required_pages": ["页面路由列表"],
    "scene": "业务主线描述",
    "industry_scope": "行业范围",
    "core_entities": ["核心业务对象"]
  },
  "work_order_markdown": "开发任务书 Markdown"
}
"""
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
        user_prompt = f"""请直接根据以下原始输入生成 PRD 和开发任务书：

原始输入:
{raw_user_request}

要求:
1. 所有输出必须是中文
2. `prd_summary.required_pages` 必须至少包含 11 个真实用户界面路由
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
            temperature_override=0.7,
        )

    async def generate_app_code(
        self, prd: str, work_order: str, app_requirements: dict
    ) -> LLMResponse:
        """Generate application code using LLM."""
        system_prompt = """你负责根据产品 PRD 直接完成正式软件产品的源码。
要求：
1. 仅输出 JSON。
2. 直接按照 PRD 开发，产品必须是正式面向市场和最终用户的正式版本，不是测试版、演示版、原型稿或后台模板。
3. 页面、文案、流程、模块都直接服务最终用户或业务对象，不要出现开发说明、模块说明、调试说明、审核说明、占位解释或面向老板/团队负责人的描述。
4. 产品必须包含大于 10 个真实可访问界面，并且各界面是实际业务页面，不是换标题的重复壳子。
5. 代码必须可读、结构清晰、注释尽量少。
6. 所有页面标题、按钮、表格列、说明文案使用中文；技术名保留英文原名。
7. 只生成本次 `required_files` 列表中的文件，不要额外输出未请求的文件。
8. 不要输出 Markdown 代码块，不要输出解释文字。

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

        minimal_requirements = {
            "required_files": list(app_requirements.get("required_files", [])),
            "module_pages": [
                {
                    "title": page.get("title"),
                    "route": page.get("route"),
                    "file_path": page.get("file_path"),
                    "component_name": page.get("component_name"),
                }
                for page in app_requirements.get("module_pages", [])
            ],
        }
        user_prompt = (
            f"PRD:\n{prd}\n\n"
            f"本次只需要输出这些文件:\n{json.dumps(minimal_requirements, ensure_ascii=False, indent=2)}\n\n"
            "请严格依据 PRD 完成这些源码文件，未要求的文件不要输出。"
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
            temperature_override=0.75,
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
        screenshot_briefs: list[dict],
    ) -> LLMResponse:
        system_prompt = """你负责根据产品 PRD 和产品截图信息，直接生成正式软件说明书/申请表所需正文 JSON。
要求：
1. 全部使用中文撰写，技术名保留英文原名。
2. 仅依据给定 PRD 和截图信息理解产品，不要引入平台模板、行业套话或额外假设。
3. 必须以正式软件产品的口吻陈述功能、页面、流程和技术实现，不要写测试说明、研发建议、验收建议、部署建议、模块说明或面向老板/团队负责人的解释。
4. 页面说明必须直接围绕页面功能本身展开，不要写“该截图展示了”“从截图可以看出”等围绕截图本身的套话。
5. 仅输出 JSON，不要输出 Markdown。

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
  ],
  "page_overrides": [
    {"page_title": "", "route": "", "caption": "", "description": "", "highlights": ["", ""], "steps": ["", ""]}
  ]
}
"""
        user_payload = {
            "product_name": product_name,
            "version": version,
            "raw_user_request": profile.get("raw_user_request", {}),
            "prd_markdown": prd_summary.get("prd_markdown", ""),
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
            max_tokens_override=7600,
            temperature_override=0.7,
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
            screenshot_briefs=screenshot_briefs[:6],
        )
        return overview_resp


def get_llm_client() -> LLMClient:
    return LLMClient()
