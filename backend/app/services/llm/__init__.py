from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


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
        # DeepSeek takes priority, then OpenAI, then generic
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

    async def chat(self, messages: list, response_format: str = "text") -> LLMResponse:
        """Send a chat completion request with model fallback."""
        if not self.config.api_key:
            return LLMResponse(success=False, error="No LLM API key configured")

        models_to_try = [self.config.model]
        if self.config.fallback_model and self.config.fallback_model != self.config.model:
            models_to_try.append(self.config.fallback_model)

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
                    "temperature": self.config.temperature,
                    "max_tokens": self.config.max_tokens,
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
                        content = data["choices"][0]["message"]["content"]

                        structured = {}
                        if response_format == "json_object":
                            try:
                                structured = json.loads(content)
                            except json.JSONDecodeError:
                                pass

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

    async def generate_prd(self, keyword: str, product_name: str, version: str, industry: str = "") -> LLMResponse:
        """Generate a product PRD using LLM."""
        system_prompt = """你是一个产品经理。根据用户提供的关键词，生成一个后台管理型 Web 应用的 PRD。
限制该产品为后台管理型（admin dashboard）应用。
输出必须是 JSON 格式，包含:
{
  "prd_markdown": "完整的PRD Markdown内容",
  "prd_summary": {
    "app_type": "admin_web",
    "user_roles": ["管理员角色列表"],
    "core_modules": ["核心功能模块列表"],
    "required_pages": ["需要的页面路由列表"]
  },
  "work_order_markdown": "开发任务书Markdown内容"
}
"""

        user_prompt = f"""请为以下产品生成 PRD 和开发任务书：
- 关键词: {keyword}
- 软件名称: {product_name}
- 版本号: {version}
- 行业: {industry or '通用'}

要求:
1. 必须是后台管理型 Web 应用
2. 提供至少 4 个核心功能模块
3. 提供至少 3 个页面路由
4. 提供 demo 账号 (admin/admin123)
5. 所有输出必须是中文
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return await self.chat(messages, response_format="json_object")

    async def generate_app_code(
        self, prd: str, work_order: str, app_requirements: dict
    ) -> LLMResponse:
        """Generate application code using LLM."""
        system_prompt = """你是一个全栈软件工程师。根据 PRD 和开发任务书生成可运行的后台管理型 Web 应用。
你必须输出符合 IPRight App Contract 的完整应用，包含:
- app_manifest.json
- run_manifest.json
- capture_manifest.json
- code_index_manifest.json

技术栈限制为:
- 前端: React + Vite + TypeScript
- 后端: FastAPI + Python
- UI: 简单 HTML/CSS，不依赖额外UI库

所有输出必须是 JSON 格式。
"""

        user_prompt = f"""PRD:\n{prd}\n\n开发任务书:\n{work_order}\n
生成一个完整的后台管理型 Web 应用。要求:
1. 包含所有 Manifest
2. 前端页面能正常渲染
3. 后端有 /health 端点
4. 提供 demo 账号
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        return await self.chat(messages)

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

        if model:
            saved_model = self.config.model
            self.config.model = model
            try:
                result = await self.chat(messages, response_format="json_object")
            finally:
                self.config.model = saved_model
            return result

        return await self.chat(messages, response_format="json_object")

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
        return await self.chat(messages, response_format="json_object")

    async def review_manual_content(self, descriptions_json: str) -> LLMResponse:
        """Alias for review_manual_descriptions."""
        return await self.review_manual_descriptions(descriptions_json)


class TemplateLLMClient:
    """Template-based LLM client that works without API keys.
    Generates structured data based on templates - used as fallback."""

    async def generate_prd(self, keyword: str, product_name: str, version: str, industry: str = "") -> LLMResponse:
        modules = ["首页/仪表盘", "数据管理", "报表统计", "系统设置"]
        pages = ["/login", "/dashboard", "/data-list", "/settings"]

        prd = f"""# {product_name} 产品需求文档

## 产品定位
{product_name} 是一款面向 {industry or '通用行业'} 的后台管理型 Web 应用系统。

## 核心功能模块
{chr(10).join(f'{i+1}. {m}' for i, m in enumerate(modules))}

## 页面结构
{chr(10).join(f'- {p}:' for p in pages)}

## 技术栈
- 前端: React + Vite + TypeScript
- 后端: FastAPI
- 数据库: PostgreSQL

## Demo 账号
- admin / admin123
"""

        work_order = f"""# {product_name} 开发任务书

## 页面任务
{chr(10).join(f'{i+1}. {p}' for i, p in enumerate(pages))}

## Demo 账号
- admin / admin123
"""

        return LLMResponse(
            success=True,
            text=prd,
            structured={
                "prd_markdown": prd,
                "prd_summary": {
                    "app_type": "admin_web",
                    "user_roles": ["admin"],
                    "core_modules": modules,
                    "required_pages": pages,
                },
                "work_order_markdown": work_order,
            },
        )

    async def generate_app_code(self, prd: str, work_order: str, app_requirements: dict) -> LLMResponse:
        return LLMResponse(success=False, error="Template LLM does not generate code. Use the demo_app template.")


def get_llm_client() -> LLMClient | TemplateLLMClient:
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY", "")
    if api_key:
        return LLMClient()
    return TemplateLLMClient()
