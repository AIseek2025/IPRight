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

    @staticmethod
    def _extract_code_content(content: str) -> str:
        text = (content or "").strip()
        if not text:
            return ""

        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[0].startswith("```"):
                fence_end = None
                for idx in range(1, len(lines)):
                    if lines[idx].strip() == "```":
                        fence_end = idx
                        break
                if fence_end is not None:
                    return "\n".join(lines[1:fence_end]).strip()

        return text

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
        required_files = [
            str(path).strip()
            for path in list(app_requirements.get("required_files", []))
            if str(path).strip()
        ]
        invalid_core_previews = app_requirements.get("invalid_core_previews") or {}
        invalid_module_previews = app_requirements.get("invalid_module_previews") or {}
        is_single_app_batch = required_files == ["frontend/src/App.tsx"]
        is_single_dashboard_batch = required_files == ["frontend/src/pages/Dashboard.tsx"]
        is_app_retry = is_single_app_batch and bool(invalid_core_previews)
        is_dashboard_retry = is_single_dashboard_batch and bool(invalid_core_previews)
        is_single_module_retry = (
            len(required_files) == 1
            and required_files[0].startswith("frontend/src/pages/")
            and bool(invalid_module_previews)
        )
        use_plaintext_single_file = bool(app_requirements.get("single_file_plaintext")) and len(required_files) == 1
        is_dashboard_plaintext = use_plaintext_single_file and required_files == ["frontend/src/pages/Dashboard.tsx"]
        retry_module_path = required_files[0] if is_single_module_retry else ""
        is_assets_module_retry = retry_module_path.endswith("AssetsPage.tsx")
        is_workflow_module_retry = retry_module_path.endswith("WorkflowPage.tsx")
        is_records_module_retry = retry_module_path.endswith("RecordsPage.tsx")
        is_analytics_module_retry = retry_module_path.endswith("AnalyticsPage.tsx")
        is_reports_module_retry = retry_module_path.endswith("ReportsPage.tsx")
        is_statistics_module_retry = retry_module_path.endswith("StatisticsPage.tsx")
        retry_module_page = (
            next(
                (
                    page
                    for page in list(app_requirements.get("module_pages", []))
                    if str((page or {}).get("file_path") or "").strip() == retry_module_path
                ),
                {},
            )
            if is_single_module_retry
            else {}
        )
        retry_module_title = str(retry_module_page.get("title") or "").strip()
        retry_module_route = str(retry_module_page.get("route") or "").strip()
        retry_module_primary_action = str(retry_module_page.get("primary_action") or "").strip()
        retry_module_filter_placeholder = str(retry_module_page.get("filter_placeholder") or "").strip()
        retry_module_page_variant = str(retry_module_page.get("page_variant") or "").strip()
        retry_module_table_headers = [
            str(item).strip()
            for item in list(retry_module_page.get("table_headers", []))[:5]
            if str(item).strip()
        ]
        retry_module_row_tokens = [
            str(cell).strip()
            for row in list(retry_module_page.get("rows", []))[:2]
            for cell in list(row)[:4]
            if str(cell).strip()
        ]
        retry_module_focus_parts = [
            item
            for item in [
                f"标题 `{retry_module_title}`" if retry_module_title else "",
                f"主操作 `{retry_module_primary_action}`" if retry_module_primary_action else "",
                f"筛选提示 `{retry_module_filter_placeholder}`" if retry_module_filter_placeholder else "",
                f"路由 `{retry_module_route}`" if retry_module_route else "",
                f"page_variant={retry_module_page_variant}" if retry_module_page_variant else "",
            ]
            if item
        ]
        retry_module_focus_summary = "、".join(retry_module_focus_parts[:5])
        retry_module_sample_tokens = [*retry_module_table_headers, *retry_module_row_tokens]
        retry_module_sample_summary = "、".join(retry_module_sample_tokens[:10])
        retry_module_anchor_tokens = []
        for token in [
            retry_module_title,
            retry_module_primary_action,
            *retry_module_table_headers[:3],
            *retry_module_row_tokens[:4],
        ]:
            token = str(token).strip()
            if token and token not in retry_module_anchor_tokens:
                retry_module_anchor_tokens.append(token)
        retry_module_anchor_summary = "、".join(retry_module_anchor_tokens[:8])
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
17. 除登录页、首页、系统设置等硬性页面外，不要把不同项目都做成同一套通用后台模板；必须根据当前 `raw_user_request`、`scene`、`industry_scope`、`core_entities`、`focus_terms`、`module_pages`、`project_dna` 生成专属布局与文案。
18. 若 `module_pages` 中提供了 `page_variant`，生成页面时必须体现该变体的版面特征和信息组织方式，而不是统一复用同一块页面骨架。
19. 不得把多个模块都写成仅更换标题的“数据管理/流程管理/报表中心”套板页面；按钮、卡片标题、表格结构、说明板块必须与当前模块主题一致。
20. 如果 `app_type` 为 `desktop_client`，界面应体现桌面客户端工作台特征，例如标题栏、工具区、分栏工作区、较高的信息密度，而不是普通网页后台。
21. 不同产品的 UI 视觉风格必须重新设计，禁止所有项目都使用同一组导航色、同一组卡片层级和同一块内容骨架。
22. 模块内容区不要使用“上边界一条高饱和蓝色粗边框”的效果，应采用常规完整边框或轻阴影边框。
23. 必须吸收 `project_dna`、`preset_key`、`topic_label`、`differentiation_hint` 中提供的项目专属线索；即便同属一个行业，也要重构模块布局、卡片语义、分析区块、表格字段和首页叙事。
24. 第三方前端依赖只允许使用当前基础环境已覆盖的包：`react`、`react-dom`、`react-router-dom`、`antd`、`@ant-design/icons`、`@ant-design/pro-components`、`axios`、`dayjs`、`echarts`、`echarts-for-react`；不要引入其他 npm 包或需要额外安装的新依赖。
25. 不要默认输出“左侧深色竖向导航 + 右侧内容区”的通用后台框架，除非当前产品的场景和信息架构明确要求这种布局；必须根据当前产品重新设计整体壳层。
26. 当前输入中的 `raw_user_request` 是唯一主题源，其他画像字段只用于补充结构约束；不要假设存在隐藏的固定 UI 套板、固定页面骨架或历史项目可复用壳层。仅当本轮不是单文件回补/单文件批次时，才需要完整生成 `App.tsx`、登录页、首页、模块页；如果本轮 `required_files` 只包含单个页面或单个 `App.tsx`，则只能输出该文件，不得补写其他页面。
27. `experience_blueprint` 与 `visual_profile` 只能作为风格灵感，不能当成固定模板强行套用；当这些画像提示与当前模块信息架构冲突时，应优先围绕当前产品与当前页面自主重构布局，但仍不得退回统一左侧竖栏后台。
28. 如果 `validation_hints`、`invalid_core_previews` 或 `invalid_module_previews` 出现在输入约束中，说明上一版页面未通过校验；这次必须逐条修正这些问题，并优先重写 `required_files` 中列出的对应页面，不得回避或沿用旧骨架。
29. 不得挪用任何历史任务的行业素材、模块标题、表格字段、卡片叙事或业务步骤；遇到“调度”“监控”“协同”等跨行业共性词时，必须优先以当前 `preset_key`、`scene`、`industry_scope` 和 `core_entities` 重新建模。
30. 如果 `module_pages` 中提供了 `rows`、`table_headers`、`filter_placeholder` 等任务样例数据，模块页必须直接复用这些真实业务样例组织表格、卡片和筛选区，不能另造 `mockData`、`testData`、“张三/李四/王五”或一眼可见的假数据。
31. `App.tsx` 必须从 `./pages/*` 导入并挂接真实模块页，不得在 `App.tsx` 内联定义 `ModuleShell`、占位页或只显示 0 值统计卡的伪页面。
32. 同一任务内的不同功能页面必须由你自主重新设计正文布局与功能模块组织方式；即便都属于模块页，也不能只换标题后继续复用同一套“三卡片 + 一张表 + 两列说明”的正文骨架。应根据每个页面的模块主题、数据字段、主操作和业务语境，主动拉开信息区块、主视觉、内容分区、重点卡片和操作区布局差异。
33. 你生成的是正式面向市场与真实用户的软件产品界面，不是给平台拥有者、研发团队、测试团队、交付团队或评审人员看的说明页、汇报页、任务简报页、演示摘要页。
34. 前端界面文案必须服务最终用户的业务操作，禁止出现任何“任务简报”“进入前摘要”“平台入口概览”“岗位工作台预览”“软件演示入口”“开发情况”“交付说明”“验收说明”“处理建议”“本次任务”“当前任务”等面向内部团队或项目交付的叙事。
35. 不得把产品页面写成项目汇报、开发说明、实施说明、验收说明、培训提纲、演示口径或版本介绍页；界面中的说明文字只能解释当前业务对象、当前操作、当前数据、当前状态和当前结果，不能解释开发过程、建设背景、团队分工或平台能力清单。
36. 登录页、首页和各模块页都必须像真实商用产品一样直接进入用户任务流：登录页只承载品牌识别与登录动作，首页只承载业务总览与工作入口，模块页只承载业务处理与结果查看；不得额外插入与用户任务无关的说明性大段文案。
37. 如果无法在当前约束下生成真实、成品化、面向最终用户的页面，就宁可返回失败，也不要输出模板页、说明页、汇报页、占位页或内部演示页。
38. 如果 `experience_blueprint.navigation_variant` 为 `indexed`，或 `visual_profile.chrome_treatment` 为 `indexed_topbar`，优先采用顶部索引导航、顶部切换条或顶部主导航等非侧栏结构；但允许你结合当前产品重新组织摘要栏、概览区和工作区，不必机械复刻画像描述。严禁退回 `Layout.Sider`、左侧深色竖向导航、`Menu mode="inline"`、`theme="dark"` 这类通用后台壳层。
39. 如果 `experience_blueprint.shell_layout_hint` 提供了“顶部索引区 + 右侧摘要栏 + 分析工作台”“顶部导航 + 内容画布”“分段导航 + 主工作区”之类方向，请把它理解为高层结构参考，而不是必须逐字照搬的固定母版；核心目标是让当前产品形成独立、成品化、可运行的页面结构。

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
        if is_single_app_batch:
            system_prompt += """
40. 当前仅允许重写 `frontend/src/App.tsx`，请把输出收敛为单文件、最小可运行、强约束实现；不要顺带生成任何其他页面、工具函数或额外壳层代码。
41. 本轮 `App.tsx` 回补的首要目标是通过壳层校验：必须保留真实路由挂接与 `APP_PROFILE` 引用，但应尽量减少 imports、状态和装饰性代码，避免长篇 JSX、重复菜单配置和大段静态说明。
42. 若当前任务要求顶部导航/索引壳层，优先使用 `div`、`header`、`nav`、`section`、`Card`、`Tabs`、`Segmented`、`Space` 等轻量结构组合；不要导入或使用 `Layout`、`Sider`、`Menu`、`Dropdown`、`Breadcrumb`、`theme="dark"`、`mode="inline"`。
43. 即便这是首轮 `App.tsx` 生成，也要优先采用精简路由壳与轻量导航，不要输出超长导航配置、复杂装饰层级或大段静态说明。
44. App.tsx 不要再写 `useMemo`、`useLocation`、`useNavigate`、`NavLink`、`Outlet`、`TabsProps`、`Tabs`，也不要导入 `Row, Col, Card, Button, Space` 这一整套整页装饰性组件；请压缩为更短的 `header/nav + Routes` 顶层路由壳。
45. 若上一版 `App.tsx` 预览中出现旧后台壳层、演示式文案、无效导入，或一上来就是 `import React, { useMemo } from 'react'` / `import { Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'` / `import { Tabs } from 'antd'` / `import type { TabsProps } from 'antd'` / `import { Row, Col, Card, Button, Space } from 'antd'` 这类重型顶层壳，那么这一轮必须整体替换该模式，而不是局部修补。
"""
        if is_single_dashboard_batch:
            system_prompt += """
45. 当前仅允许重写 `frontend/src/pages/Dashboard.tsx`，请把输出收敛为单文件、最小可运行、强约束首页；不要顺带生成 App.tsx、Login.tsx、其他模块页、类型文件或服务文件。
46. Dashboard.tsx 必须使用命名导入 `import { APP_PROFILE } from '../generated/appProfile';`，并直接读取 `APP_PROFILE.product_name` 与 `APP_PROFILE.dashboard_metrics`；禁止写成 `./generated/appProfile`、`../../generated/appProfile`、默认导入或其他错误路径；同时必须展示中文首页/工作台标题，不要写任务简报、岗位工作台预览、开发汇报、交付说明或其他平台侧叙事。
47. Dashboard.tsx 可以使用 `Card`、`Statistic`、`Progress`、`Tag`、`Button`、`Space` 等基础组件；如需列表/表格，优先直接使用原生 `<table>`，不要回到 antd `Table columns` 配置写法。如使用 `@ant-design/icons`，只允许 `AppstoreOutlined`、`AuditOutlined`、`BarChartOutlined`、`CalendarOutlined`、`CheckCircleOutlined`、`ClockCircleOutlined`、`ExclamationCircleOutlined`、`FileTextOutlined`、`PlusOutlined`、`RightOutlined`、`TeamOutlined`、`UserOutlined` 这些已验证可用的图标名，禁止 `BriefcaseOutlined` 或其他未验证导出名。
48. Dashboard.tsx 必须使用精确组件签名 `export default function Dashboard()`，并直接在源码中出现 `APP_PROFILE.product_name` 与 `APP_PROFILE.dashboard_metrics`；不要改成 `React.FC`、`HomeDashboard`、`OverviewPage` 或其他函数名。
49. Dashboard.tsx 必须压缩成短文件：首页只保留 1 个中文 H1（如“系统首页”或“工作台”）、2~4 个统计块、1 个轻量表格/列表即可；不要生成 `Row`/`Col` 大栅格、长图标映射、长篇说明文案或超长 JSX。
50. Dashboard.tsx 不要在组件外声明 `const items = [`、`const recentActivities = [`、`const activities = [`、`const columns = [`、`const dataSource = [`、`ColumnsType`、`const iconMap: Record<string, React.ReactNode>`、长数组、长映射、长图标字典或大型统计配置；请把 2~3 行轻量样例直接写在组件内部，避免再次生成过长首页壳。
51. Dashboard.tsx 不要再写 `const fallbackMetrics = [`、`const metricCards = [` 或其他本地兜底指标数组；请直接基于 `APP_PROFILE.dashboard_metrics` 渲染 2~4 个统计块，不要回退成通用演示数据。
52. Dashboard.tsx 不要导入 `Typography`、不要写 `const { Title } = Typography`，也不要把首页写成 `Title/Paragraph` 通用展示壳；请直接使用原生 `h1`、`p` 或最少量 `Card/Statistic` 组织首页。
53. Dashboard.tsx 不要再写 `const metrics = APP_PROFILE.dashboard_metrics`、`const metrics = APP_PROFILE.dashboard_metrics || []`、`const metrics = (APP_PROFILE as any).dashboard_metrics`，也不要返回 `<div style={{ padding: 24 }}>`、`<div style={{ margin: 24 }}>`、`<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`、`<div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>`、`<div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 24px' }}>` 或 `<div style={{ padding: '1.5rem 2rem' }}>` 这类通用轻壳；H1 必须是中文首页/工作台标题，不能直接把 `APP_PROFILE.product_name` 当成首页主标题，也不要回退成只有“工作台”标题 + 单个统计卡的白页，更不要写成“异常监控总览”或“冷链履约异常协同工作台”这类偏监控看板/领域口号的历史壳标题。
54. 如果上一版预览或报错中出现 `BriefcaseOutlined`、无效 `@ant-design/icons` 导入、未使用 `APP_PROFILE.dashboard_metrics`、只写了通用标题壳层、错误的 `APP_PROFILE` 相对路径，或一上来就是 `import React from 'react'; import { Row, Col, Card, Statistic, Table, Tag, Progress, Button } from 'antd';` / `import React from 'react'; import { Card, Statistic } from 'antd';` / `import { Card, Statistic, Tag } from 'antd';` + `ExclamationCircleOutlined` / `const iconMap: Record<string, React.ReactNode>` / `import { CheckCircleOutlined, ExclamationCircleOutlined, ClockCircleOutlined, TeamOutlined } from '@ant-design/icons'` / `import { TeamOutlined, CalendarOutlined, FileTextOutlined, UserOutlined } from '@ant-design/icons'` / `import { FileTextOutlined, UserOutlined, CalendarOutlined, CheckCircleOutlined } from '@ant-design/icons'` / `import { Card, Statistic } from 'antd'` + `CalendarOutlined + TeamOutlined` / `import { Card, Statistic } from 'antd'` + 3~4 个状态图标 / `import { APP_PROFILE } from './generated/appProfile'` / `const metrics = APP_PROFILE.dashboard_metrics ...` / `const metrics = APP_PROFILE.dashboard_metrics || []` / `const metrics = (APP_PROFILE as any).dashboard_metrics` / `metrics.map((item) =>` / `const fallbackMetrics = [` / `const items = [` / `const recentActivities = [` / `const columns = [` / `const { Title } = Typography` / `<div style={{ padding: 24 }}>` / `<div style={{ margin: 24 }}>` / `<div style={{ padding: '16px' }}>` / `<p style={{ color: '#555' }}>{APP_PROFILE.product_name}</p>` / `<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>` / `<div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>` / `<div style={{ padding: '24px', background: '#f8f5ef', minHeight: '100vh' }}>` / `<div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 24px' }}>` / `<div style={{ padding: '1.5rem 2rem' }}>` / `<div style={{ padding: '32px 40px', maxWidth: 1200, margin: '0 auto' }}>` / `<div style={{ padding: '24px 32px', background: '#f0fdf9' }}>` / `<h1>工作台</h1>` / `<h1>系统首页</h1>` + 紫色产品副标题 / `<h1>异常监控总览</h1>` / `<h1>冷链履约异常协同工作台</h1>` / `const recentEvents = [` / `{ code: 'E-001', type: '温度超标', status: '处理中', time: '2025-06-01 10:30' }` / `{ code: 'E-002', type: '运输延迟', status: '待处理', time: '2025-06-01 09:15' }` / `BarChartOutlined + ExclamationCircleOutlined + ClockCircleOutlined + FileTextOutlined` / `\"frontend/src/App.tsx\"` / `import { Routes, Route, Navigate, Link` 这类大体量首页壳或越界壳层，那么这一轮必须整体重写成更短的实现，不要局部打补丁；若需要表格，请直接改成原生 `<table>`，不要再写 antd `Table columns`。
"""
        if is_single_module_retry:
            system_prompt += """
45. 当前仅允许重写 `required_files` 中列出的单个模块页；禁止输出 `frontend/src/App.tsx`、`frontend/src/pages/Login.tsx`、`frontend/src/pages/Dashboard.tsx`、其他模块页、类型文件或服务文件。
46. 模块页无效重试时，请把输出收敛为单文件、最小可运行、强约束页面：保留真实业务标题、筛选入口、主操作和任务样例数据，但尽量减少 imports、局部状态、辅助函数、超长 mock 数组和重复 JSX。
47. 模块页回补时不得生成任何全局壳层、路由容器、导航条、侧边栏、`Layout`、`Menu`、`Tabs` 壳层或 `App.tsx` 风格代码；只生成当前页面组件本身。
48. 如果上一轮模块页预览或错误信息中出现 `frontend/src/App.tsx`、后台壳层、演示说明文案或越界文件，这些都属于必须彻底移除的无效噪音；本轮只能整体重写当前模块页，不得顺带修补壳层。
49. 如果 token 紧张，优先保证当前模块页通过校验：使用精简表格、卡片、分区和任务样例数据，避免长篇静态说明和大段重复结构。
50. 模块页回补优先使用 `section`、`div`、`Space`、`Card`、原生 `table`、轻量 `Tag`/`Button` 组合；不要默认使用 `Modal`、`Drawer`、`Form.List`、复杂 `Table columns render`、`useMemo`、`useCallback`、大段本地状态或批量操作逻辑。
51. 模块页回补时尽量不要声明额外的 TypeScript interface/type、`ColumnsType` 泛型、大型静态数组或复杂映射；优先把 2-4 行任务样例数据直接写进轻量 JSX 表格/列表，避免长 JSON。
"""
        if is_single_module_retry:
            system_prompt += """
52. 当前模块页位于 `frontend/src/pages/*.tsx`，因此必须使用命名导入 `import { APP_PROFILE } from '../generated/appProfile';` 并实际使用 `APP_PROFILE`；禁止写成 `../../generated/appProfile`、`import APP_PROFILE from '../generated/appProfile'`、默认导入或其他错误相对路径。如果只导入不使用、或完全不引用 `APP_PROFILE`，将视为失败。
53. 禁止声明 `const mockData`、`mockData:`、`testData`、`sampleData` 等通用占位数据名；请直接复用当前任务提供的真实样例数据，必要时可把 2-4 行样例直接内联到 JSX。
54. 当前模块页不得改写成“资产台账”“报表中心”“数据管理”“通用档案页”等历史模板主题；页面首屏必须直接体现当前模块真实业务主题。
"""
        if is_single_module_retry and retry_module_focus_summary:
            system_prompt += (
                "\n"
                f"55. 当前模块必须保留这些真实业务要素：{retry_module_focus_summary}。"
                " 页面标题、主按钮、筛选提示和正文语义必须与这些要素一致，不得替换成其他历史项目口径。\n"
            )
        if is_single_module_retry and retry_module_sample_summary:
            system_prompt += (
                f"56. 当前模块必须直接覆盖这些字段/样例中的大部分：{retry_module_sample_summary}。"
                " 若缺少这些真实 token，将视为未通过校验。\n"
            )
        if is_single_module_retry and retry_module_title:
            system_prompt += (
                f"57. 当前模块首屏主标题（H1、页面标题或最显著标题）必须逐字使用 `{retry_module_title}`，"
                " 不得改写成近义标题、历史标题或其他模块主题。\n"
            )
        if is_single_module_retry and retry_module_anchor_summary:
            system_prompt += (
                f"58. 当前模块正文至少逐字保留这些业务锚点中的 2 个以上：{retry_module_anchor_summary}。"
                " 若上一版写成了别的业务主题，这一轮必须整体重写，而不是局部改名。\n"
            )
        if is_single_module_retry and retry_module_page_variant == "workspace":
            system_prompt += (
                "59. 当前模块 page_variant=workspace：请压缩为“标题区 + 1 行摘要/状态条 + 1 个检索输入 + 1 个主按钮 + 1 张轻量表格”，"
                " 不要生成抽屉、侧栏、复杂卡片矩阵或长篇说明。\n"
            )
        if is_single_module_retry and retry_module_page_variant == "insight":
            system_prompt += (
                "60. 当前模块 page_variant=insight：请压缩为“标题区 + 2~3 个轻量业务摘要 + 1 个检索输入 + 1 张轻量表格/列表”，"
                " 不要生成 Steps、Timeline、复杂图表区、Tabs、弹窗或长数据映射。\n"
            )
        if use_plaintext_single_file:
            system_prompt += """
61. 当前回补启用了单文件纯文本协议：请直接输出目标文件的完整源码文本本身，不要再包裹 JSON、不要输出 `files` 字段、不要输出 Markdown 代码块、不要输出解释说明。
62. 第一行就必须是源码内容，最后一行也必须是源码内容；若返回 JSON 或额外解释，将视为失败。
"""
        if is_dashboard_plaintext:
            system_prompt += (
                "63. 当前目标文件是 `frontend/src/pages/Dashboard.tsx`，请直接输出完整 TSX 源码，"
                "不要返回 JSON 外壳；源码必须实际读取 `APP_PROFILE.product_name` 与 `APP_PROFILE.dashboard_metrics`，"
                "并且如使用 `@ant-design/icons`，只能使用已验证可用图标名，禁止 `BriefcaseOutlined`。\n"
            )
        if is_assets_module_retry:
            system_prompt += (
                "\n"
                "57. 当前回补页面是 `AssetsPage.tsx`。注意：文件名虽然是 AssetsPage，但业务主题必须完全以当前模块画像为准；"
                "不要默认写成资产台账、资产名称、资产类别、资产状态或固定资产管理页面。\n"
                "58. `AssetsPage.tsx` 请压缩成“1 个筛选输入 + 1 个主按钮 + 1 张轻量业务表/列表”；"
                " 直接复用当前模块标题、主操作、筛选提示和任务样例数据，不要输出弹窗、抽屉、批量操作条或复杂状态机。\n"
                "59. `AssetsPage.tsx` 不要使用 `React.FC`、`useState`、受控搜索状态或 `Input`、`Card`、`Typography`、`Tag` 等会把页面写重的组件；"
                " 请优先输出无 hooks 的普通函数组件，仅保留原生 `<input>`、`<button>`、`<table>` 或最少量 `Button`。\n"
                "60. 若你正想输出类似这类旧错误实现："
                " `import React, { useState } from 'react'`、`import { Input, Button, Card, Typography, Tag } from 'antd'`、"
                " `const AssetsPage: React.FC = ...`，那么这整种写法本轮一律判失败。\n"
                "61. 若你正想输出另一类最新错误实现："
                " `function AssetsPage() { const items = [{ id, topic, role, status, tag, updateTime }] ... }`，"
                " 并把主题写成“候选人管理”“人才档案库”“应聘者全旅程管理”或其他历史模块，而不是当前要求的模块标题，那么同样一律判失败；"
                " 页面主标题、主按钮和表格正文都必须逐字围绕当前模块标题组织，不能只复用通用字段名。\n"
                "62. 若你正想输出另一类最新错误实现：`import React from 'react'`、`import { Button } from 'antd'` + `import { APP_PROFILE } from '../generated/appProfile'`，"
                " 再配合通用 `<div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>` 轻壳，并把 H1 写成“面试管理”，那么同样一律判失败；"
                " AssetsPage 的 H1 必须逐字等于当前模块标题，且正文必须落下当前模块样例数据对应的真实业务表格或列表。\n"
                "63. 若你正想输出另一类最新错误实现：`import React from 'react'` + `import { APP_PROFILE } from '../generated/appProfile'`，"
                " 再配合 `<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>` 蓝色轻壳，"
                " 并把 H1 写成“面试流程管理”或把 `APP_PROFILE.productName` 当成正文说明，那么同样一律判失败；"
                " AssetsPage 必须改回当前模块标题逐字命中的真实业务页。\n"
            )
        if is_workflow_module_retry:
            system_prompt += (
                "\n"
                "54. 当前回补页面是 `WorkflowPage.tsx`。注意：文件名虽然是 WorkflowPage，但业务主题必须完全以当前模块画像为准；"
                "不要默认写成人才流程跟进、步骤条、时间轴、阶段推进或流程看板页面。\n"
                "55. `WorkflowPage.tsx` 请压缩成“1 个筛选条 + 少量业务摘要 + 1 张轻量业务表/列表”；"
                " 直接复用当前模块标题、主操作、筛选提示和任务样例数据，不要输出 Steps、Timeline、弹窗、侧栏、复杂标签映射或多层折叠区。\n"
                "56. `WorkflowPage.tsx` 不要使用 `Table` 组件、`ColumnsType`、`Row/Col` 栅格或长数据数组；"
                " 优先使用原生 `<table>` 或简单列表直接写 2-4 行当前模块样例记录。\n"
                "57. `WorkflowPage.tsx` 不要使用 `React.FC`、`useState`、`useMemo`、`useCallback`、受控搜索状态或任何本地交互状态；"
                " 请输出无 hooks 的普通函数组件，首选静态 `<input placeholder=...>` + 原生 `<table>`。\n"
                "58. `WorkflowPage.tsx` 不要再导入 `Input`、`Card`、`Space`、`Typography`、`Tag` 等会把页面写重的组件；"
                " 只允许保留 `Button` 或完全使用原生 HTML。`APP_PROFILE` 必须使用命名导入 `import { APP_PROFILE } from '../generated/appProfile';`。\n"
                "59. 若你正想输出类似这类旧错误实现："
                " `import React, { useState } from 'react'`、`import { Input, Button, Card, Tag, Space } from 'antd'`、"
                " `import APP_PROFILE from '../generated/appProfile'`、`const WorkflowPage: React.FC = ...`，"
                " 那么这整种写法本轮一律判失败；请整体改写成命名导入 APP_PROFILE 的无 hooks 原生轻量页面。\n"
                "60. 若你正想输出另一类最新错误实现："
                " `const platformName = APP_PROFILE.product_name || '...'` 加一个通用 `<div style=...>` 壳，"
                " 再把平台名当成页面主语、写成泛化产品概览页，或直接把 H1 写成“候选人管理”等历史主题，"
                " 那么同样一律判失败；WorkflowPage 的 H1 必须逐字等于当前模块标题，且正文必须出现当前模块样例数据中的业务锚点，不能只展示产品名。\n"
                "61. 若你正想输出最新这类轻壳错误实现：`import { Button } from 'antd'`，"
                " 再配合统一的蓝色 `background: '#f3f6fb'` / `color: '#1e3a8a'` / `color: '#2563eb'` 内联样式壳，"
                " 并只放一个主按钮或一段摘要文字，那么同样一律判失败；`WorkflowPage.tsx` 必须是当前模块的真实业务页，"
                " 至少要落下当前模块标题、筛选输入、业务摘要和 1 份原生表格或列表，不能停留在通用产品壳层。\n"
                "62. 若你正想输出另一类最新错误实现：`import React from 'react'` + `import { APP_PROFILE } from '../generated/appProfile'`，"
                " 再配合白底通用内联样式壳（如 `background: '#ffffff'`、`minHeight: '100vh'`、`color: '#111'` / `'#555'`），"
                " 并把 H1 写成“候选人管理”，那么同样一律判失败；这仍然只是通用轻壳页，不是当前模块的真实业务页。\n"
                "63. 若你正想输出另一类最新错误实现：`const WorkflowPage = () =>`，"
                " 再配合顶层 `<div style={{ padding: 24 }}>`、先显示 `APP_PROFILE.product_name`、"
                " 再把 H1 写成“候选人管理”的通用白页壳，那么同样一律判失败；"
                " WorkflowPage 必须改回当前模块标题逐字命中的真实业务页，不能再返回这种产品名 + 历史标题的简陋壳层。\n"
                "64. 若你正想输出另一类最新错误实现：`import React from 'react'` + `function WorkflowPage() { return ( <div style={{ padding: 24 }}> ... ) }`，"
                " 顶部先用灰色小字显示 `APP_PROFILE.product_name`，再在正文里放历史模块标题或泛化业务标题，"
                " 那么同样一律判失败；这仍然只是产品名面包屑 + 通用轻壳，不是当前模块真实业务页。\n"
            )
        if is_records_module_retry:
            system_prompt += """
57. 当前回补页面是 `RecordsPage.tsx`：请把页面压缩成“1 个检索输入 + 1 个新建按钮 + 1 张档案表”即可；不要输出详情抽屉、批量操作、复杂筛选面板、标签墙或多段说明卡。
58. `RecordsPage.tsx` 只需保留主体名称/统一代码/负责人/状态等核心字段，并直接写入 2-4 行任务样例数据。
59. `RecordsPage.tsx` 不要使用 `React.FC`、`useState`、受控搜索状态或 `Table`、`Input`、`Space`、`Typography`、`Tag` 等重型实现；请改为无 hooks 的普通函数组件，优先使用原生 `<input>` + 原生 `<table>`。
60. 若你正想输出类似这类旧错误实现：`import React, { useState } from 'react'`、`import { Table, Button, Input, Space, Typography, Tag } from 'antd'`、`const RecordsPage: React.FC = ...`，那么这整种写法本轮一律判失败。
61. 若你正想输出另一类最新错误实现：`import APP_PROFILE from '../generated/appProfile'`、`const productName = APP_PROFILE?.productName || '...'`、
    再把页面标题写成“招聘需求管理”“院校客户管理”“职位管理”“职位与需求管理”或其他历史主题，那么同样一律判失败；H1 必须逐字等于当前模块标题，不能把产品名或历史模块名当作页面标题。
62. 若你正想输出 `const data = [{ id, topic, role, status, tag, time }]`、`const data = [{ id, topic, role, status, tag, updateTime }]`、`MOD0-001` / `MOD0-002` 配合“重点事项”这类泛化样例数组，那么同样一律判失败；RecordsPage 必须改回当前模块真实表头和真实样例字段，不能复用通用招聘需求表壳。
63. 若你正想输出另一类最新错误实现：`import React from 'react';` + `import { APP_PROFILE } from '../generated/appProfile';`，再配合 `<div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>`、顶部 `display: 'flex' + justifyContent: 'space-between' + alignItems: 'center'` 的米色轻壳页，那么同样一律判失败；必须改回当前模块标题逐字命中的真实检索表页。
64. `StatisticsPage.tsx` 不要使用 `React.FC`、`Input`、`Button`、`Card`、`Row`、`Col`、`Typography`、`SearchOutlined`、`BarChartOutlined` 这一整套重型 antd 统计页实现；请改成无 hooks 的普通函数组件，优先使用原生 `<input>` + 少量摘要块 + 原生 `<table>`。
"""
        if is_analytics_module_retry:
            system_prompt += (
                "\n"
                "59. 当前回补页面是 `AnalyticsPage.tsx`。注意：页面主题必须完全以当前模块画像为准；不要写通用“分析中心”“数据分析台”或历史项目的分析口径。\n"
                "60. `AnalyticsPage.tsx` 请压缩成“1 个筛选条 + 2~3 个轻量业务摘要 + 1 张结果表/列表”；直接复用当前模块标题、主操作、筛选提示和任务样例数据，不要输出复杂图表区、Tabs、弹窗或长篇分析说明。\n"
                "61. `AnalyticsPage.tsx` 不要使用 `React.FC`、`useState`、`Typography`、`Input`、`Button`、`Space`、`Card`、`Tag`、`SearchOutlined`、`PlusOutlined` 这一整套重型 antd 分析页实现；请改成无 hooks 的普通函数组件，优先使用原生 `<input>` + 少量摘要块 + 原生 `<table>`。\n"
                "62. 若你正想输出类似这类最新错误实现：`import React from 'react'`、`import { Typography, Input, Button, Space, Card, Tag } from 'antd'`、`import { SearchOutlined, PlusOutlined } from '@ant-design/icons'`、`const { Title, Text } = Typography`、`const AnalyticsPage: React.FC = ...`，那么这整种写法本轮一律判失败；页面主标题、摘要标题和结果表都必须逐字围绕当前模块标题与样例数据组织。\n"
            )
        if is_reports_module_retry:
            system_prompt += (
                "\n"
                "59. 当前回补页面是 `ReportsPage.tsx`。注意：页面主题必须完全以当前模块画像为准；"
                "不要写通用“报表中心”“招聘报表中心”或历史项目的统计口径。\n"
                "60. `ReportsPage.tsx` 请压缩成“1 个筛选条 + 2~3 个摘要卡 + 1 张结果表/列表”；"
                " 直接复用当前模块标题、主操作、筛选提示和任务样例数据，不要输出图表库、Tabs、下载弹窗或长篇分析说明。\n"
                "61. `ReportsPage.tsx` 不要使用 `React.FC`、`useState`、受控搜索状态或 `Input`、`Table`、`Card`、`Row`、`Col`、"
                " `Statistic`、`Typography`、`Space`、`SearchOutlined`、`FileTextOutlined` 这一整套重型 antd 报表页实现；"
                " 请改成无 hooks 的普通函数组件，优先使用原生 `<input>` + 少量摘要块 + 原生 `<table>`。\n"
                "62. 若你正想输出类似这类最新错误实现："
                " `import React, { useState } from 'react'`、`import { Input, Button, Table, Card, Row, Col, Statistic, Typography, Space } from 'antd'`、"
                " `import { SearchOutlined, FileTextOutlined } from '@ant-design/icons'`、`const ReportsPage: React...`，"
                " 那么这整种写法本轮一律判失败；页面主标题、摘要标题和结果表都必须逐字围绕当前模块标题与样例数据组织，不能回到通用报表模板。\n"
                "63. 若你正想输出另一类最新错误实现：`<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`、"
                " 再配合 `fontFamily:` 和把 H1 写成“录用与Offer管理”这类历史主题，那么同样一律判失败；"
                " `ReportsPage.tsx` 必须改回当前模块标题逐字命中的轻量报表页。\n"
            )
        if is_statistics_module_retry:
            system_prompt += (
                "\n"
                "59. 当前回补页面是 `StatisticsPage.tsx`。注意：页面主题必须完全以当前模块画像为准；不要写通用“统计中心”“数据统计中心”或历史项目统计口径。\n"
                "60. `StatisticsPage.tsx` 请压缩成“1 个筛选条 + 2~3 个轻量摘要块 + 1 张结果表/列表”；直接复用当前模块标题、筛选提示和任务样例数据，不要输出复杂图表区、下载弹窗或长篇分析说明。\n"
                "61. `StatisticsPage.tsx` 不要使用 `React.FC`、`Input`、`Button`、`Card`、`Row`、`Col`、`Typography`、`SearchOutlined`、`BarChartOutlined` 这一整套重型 antd 统计页实现；请改成无 hooks 的普通函数组件，优先使用原生 `<input>` + 少量摘要块 + 原生 `<table>`。\n"
                "62. 若你正想输出类似这类最新错误实现： `import React from 'react'`、`import { Input, Button, Card, Row, Col, Typography } from 'antd'`、`import { SearchOutlined, BarChartOutlined } from '@ant-design/icons'`、`const { Title, Text } = Typography`、`const StatisticsPage: React.FC = ...`，那么这整种写法本轮一律判失败；页面主标题、摘要标题和结果表都必须逐字围绕当前模块标题与样例数据组织。\n"
                "63. 若你正想输出另一类最新错误实现：`<div style={{ padding: '24px 32px', background: '#f3f6fb' }}>`、"
                " 再配合 `fontFamily:` 的蓝色通用轻壳，那么同样一律判失败；`StatisticsPage.tsx` 必须改回当前模块标题逐字命中的轻量统计页。\n"
                "64. 若你正想输出 `const productName = APP_PROFILE.productName || '...'`、`<div style={{ padding: 24, fontFamily: 'system-ui, -apple-system, sans-serif' }}>`、"
                " 再把 H1 写成“统计分析”或其他通用统计标题，那么同样一律判失败；`StatisticsPage.tsx` 必须改回当前模块标题逐字命中的真实统计页。\n"
                "65. 若你正想输出 `function StatisticsPage() { const productName = APP_PROFILE.productName || '...'`、"
                " 再配合 `<h1 style={{ marginBottom: 8, fontSize: 24, fontWeight: 600 }}>统计分析</h1>` 这一整种 preview 级通用统计轻壳，那么同样一律判失败；必须整体改写。\n"
                "66. 若你正想输出 `const { productName } = APP_PROFILE;`、`<div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>`、"
                " 再把 H1 写成“统计分析”并把副标题写成 `{productName} - 分析中心`，那么同样一律判失败；不能再走居中通用统计壳。\n"
                "67. 若你正想输出 `import React from 'react';`、`style={styles.container}`、`style={styles.title}`、`style={styles.subtitle}`，"
                " 再把主标题写成“数据分析与看板”并直接展示 `APP_PROFILE.productName`，那么同样一律判失败；必须整体改写成当前模块标题逐字命中的真实统计页。\n"
            )

        user_prompt = (
            f"PRD:\n{prd}\n\n"
            f"开发任务书:\n{work_order}\n\n"
            f"应用约束:\n{json.dumps(app_requirements, ensure_ascii=False, indent=2)}\n\n"
            "请基于这些信息生成完整源码文件。"
        )
        if is_single_app_batch:
            user_prompt += (
                "\n\n补充要求：当前只允许输出 App.tsx。"
                " 请直接输出精简后的顶层路由壳文件，优先保证："
                " 1) 使用 APP_PROFILE；"
                " 2) 正确导入并挂接 Login、Dashboard 与任务要求的模块页；"
                " 3) 不出现左侧后台模板、汇报式文案或额外占位组件；"
                " 4) 不要写 `useMemo`、`useLocation`、`useNavigate`、`NavLink`、`Outlet`、`TabsProps`、`Tabs`，也不要导入 `Row, Col, Card, Button, Space` 这一整套重型壳层组件；"
                " 5) 控制 imports 和 JSX 体量，避免再次输出超长 JSON 字符串。"
            )
        if is_app_retry:
            user_prompt += (
                " 这次只修复 App.tsx，且属于 App.tsx 校验失败后的回补，必须整体替换旧壳层。"
                " 不要再回到 `useMemo/useLocation/useNavigate/NavLink/Tabs/TabsProps/Outlet` 或 `Row, Col, Card, Button, Space` 这一类重型顶层壳。"
            )
        if is_single_dashboard_batch:
            user_prompt += (
                "\n\n补充要求：当前只允许输出 Dashboard.tsx。"
                " 请直接输出精简后的首页/工作台文件，优先保证："
                " 1) 直接读取 APP_PROFILE.product_name 与 APP_PROFILE.dashboard_metrics；"
                " 2) 使用 `export default function Dashboard()` 和中文首页/工作台标题；"
                " 3) 控制在短文件范围内，只保留少量统计块 + 1 个轻量表格/列表，优先原生 `<table>`；"
                " 4) 不要写组件外的 `const items = [`、`const recentActivities = [`、`const activities = [`、`const columns = [`、`const dataSource = [`、`ColumnsType`、长数组、长映射或长图标字典；"
                " 5) 不要写 `const fallbackMetrics = [`、`const metricCards = [` 这类本地兜底指标数组；"
                " 6) 不要导入 `Typography`，不要写 `const { Title } = Typography`，改用原生 h1/p；"
                " 7) 不要写 `const metrics = APP_PROFILE.dashboard_metrics`、`const metrics = APP_PROFILE.dashboard_metrics || []`、`const metrics = (APP_PROFILE as any).dashboard_metrics`，"
                "也不要返回 `<div style={{ padding: 24 }}>`、`<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`、`<div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>` 或 `<div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 24px' }}>` 这类通用轻壳，"
                "更不要把 APP_PROFILE.product_name 当成 H1，或回退成只有“工作台”标题 + 单个统计卡的白页；Dashboard.tsx 只能使用 `import { APP_PROFILE } from '../generated/appProfile';`。"
                " 8) 不出现任务简报、平台汇报、交付说明或占位壳层；"
                " 9) 若使用 @ant-design/icons，只能使用已验证可用图标名，绝对不要导入 BriefcaseOutlined。"
            )
        if is_dashboard_retry:
            user_prompt += (
                " 这次是 Dashboard.tsx 校验失败后的回补；上一版已经出现过大体量首页壳/无效命中风险。"
                " 不要再导入 BriefcaseOutlined 或其他未验证导出名，也不要再写 `Row/Col` 大栅格、长 imports、长图标映射、`const metrics = ...`、`const metrics = APP_PROFILE.dashboard_metrics`、`const metrics = APP_PROFILE.dashboard_metrics || []`、`const metrics = (APP_PROFILE as any).dashboard_metrics`、`metrics.map((item) =>`、`const fallbackMetrics = [`、`const items = [`、`const recentActivities = [`、`const activities = [`、`const columns = [`、`const dataSource = [`、`const { Title } = Typography`、`const iconMap: Record<string, React.ReactNode>`、`import { CheckCircleOutlined, ExclamationCircleOutlined, ClockCircleOutlined, TeamOutlined } from '@ant-design/icons'`、`import { TeamOutlined, CalendarOutlined, FileTextOutlined, UserOutlined } from '@ant-design/icons'`、`import { FileTextOutlined, UserOutlined, CalendarOutlined, CheckCircleOutlined } from '@ant-design/icons'`、`import { APP_PROFILE } from './generated/appProfile'`、`import { Card, Statistic } from 'antd'` + 多个状态图标、`import { Card, Statistic, Tag } from 'antd'` + `ExclamationCircleOutlined`、`<div style={{ padding: 24 }}>`、`<div style={{ margin: 24 }}>`、`<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`、`<div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>`、`<div style={{ padding: '24px', background: '#f8f5ef', minHeight: '100vh' }}>`、`<div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 24px' }}>`、`<div style={{ padding: '1.5rem 2rem' }}>`、`<div style={{ padding: '32px 40px', maxWidth: 1200, margin: '0 auto' }}>`、`<div style={{ padding: '24px 32px', background: '#f0fdf9' }}>`、`<h1>异常监控总览</h1>`、`<h1>冷链履约异常协同工作台</h1>`、`const recentEvents = [`、`{ code: 'E-001', type: '温度超标', status: '处理中', time: '2025-06-01 10:30' }` 或 `{ code: 'E-002', type: '运输延迟', status: '待处理', time: '2025-06-01 09:15' }`、`BarChartOutlined + ExclamationCircleOutlined + ClockCircleOutlined + FileTextOutlined`、`\"frontend/src/App.tsx\"` 或 `import { Routes, Route, Navigate, Link` 这类组件外长配置/通用展示壳。"
                " 若需要表格，请直接使用原生 `<table>`，不要再使用 antd `Table columns` API。"
                " 直接输出短版 `export default function Dashboard()`，并确保源码里出现 `APP_PROFILE.product_name`、`APP_PROFILE.dashboard_metrics` 与中文首页标题；不要把 `APP_PROFILE.product_name` 直接写成 H1。"
            )
        if is_single_module_retry:
            user_prompt += (
                "\n\n补充要求：当前只允许输出这个模块页文件。"
                " 禁止输出 App.tsx、Login.tsx、Dashboard.tsx 或任何其他文件。"
                " 请直接输出精简后的单页实现，优先保证："
                " 1) 页面内容严格围绕当前 required_files 对应模块；"
                " 2) 直接复用任务提供的标题、筛选、主操作和样例数据；"
                " 3) 不出现后台壳层、路由容器、汇报式文案或越界文件；"
                " 4) 控制 imports、状态和 JSX 体量，避免再次输出超长 JSON 字符串。"
                " 允许使用最小业务页过关：一个筛选区、一个主操作、一个轻量表格/列表就够，不要补齐复杂弹窗和表单。"
                " 优先使用原生 table/简单 div 列表，尽量不要声明 interface、ColumnsType 或长数据数组。"
            )
        if is_single_module_retry and retry_module_focus_summary:
            user_prompt += f" 当前模块的真实业务要素是：{retry_module_focus_summary}。"
        if is_single_module_retry and retry_module_sample_summary:
            user_prompt += f" 必须直接复用这些字段或样例：{retry_module_sample_summary}。"
        if is_single_module_retry:
            user_prompt += " 必须使用命名导入 `import { APP_PROFILE } from '../generated/appProfile';` 并实际使用 APP_PROFILE；禁止默认导入以及 const mockData、mockData:、testData、sampleData。"
        if is_single_module_retry and retry_module_title:
            user_prompt += f" 页面主标题必须逐字等于“{retry_module_title}”，不要改写成其他近义标题。"
        if is_single_module_retry and retry_module_anchor_summary:
            user_prompt += f" 页面正文至少逐字出现这些锚点中的两个以上：{retry_module_anchor_summary}。"
        if use_plaintext_single_file:
            user_prompt += (
                "\n\n本轮返回协议已切换为单文件纯文本。"
                " 请只返回目标文件源码，不要返回 JSON，不要写 ```tsx 代码块，不要附加任何解释。"
            )
        if is_dashboard_plaintext:
            user_prompt += (
                " 当前文件是 Dashboard.tsx，请从第一行开始直接输出完整源码；"
                " 必须读取 APP_PROFILE.product_name 与 APP_PROFILE.dashboard_metrics，"
                " 且不要导入 BriefcaseOutlined。"
                " 组件名必须是 `export default function Dashboard()`；请保持文件精简，不要再写大体量 imports、Row/Col 栅格、长图标映射、`const metrics = ...`、`const metrics = APP_PROFILE.dashboard_metrics`、`const metrics = APP_PROFILE.dashboard_metrics || []`、`const metrics = (APP_PROFILE as any).dashboard_metrics`、`const fallbackMetrics = [`、`const items = [`、`const recentActivities = [`、`const activities = [`、`const columns = [`、`const dataSource = [`、`const { Title } = Typography`、`const iconMap: Record<string, React.ReactNode>`、`import { CheckCircleOutlined, ExclamationCircleOutlined, ClockCircleOutlined, TeamOutlined } from '@ant-design/icons'`、`import { TeamOutlined, CalendarOutlined, FileTextOutlined, UserOutlined } from '@ant-design/icons'`、`import { APP_PROFILE } from './generated/appProfile'`、`import { Card, Statistic } from 'antd'` + 多个状态图标、`import { Card, Statistic, Tag } from 'antd'` + `ExclamationCircleOutlined`、`<div style={{ padding: 24 }}>`、`<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`、`<div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>`、`<div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 24px' }}>`、`<div style={{ padding: '1.5rem 2rem' }}>`、`<div style={{ padding: '32px 40px', maxWidth: 1200, margin: '0 auto' }}>`、`<div style={{ padding: '24px 32px', background: '#f0fdf9' }}>`、`<h1>异常监控总览</h1>` 或 `<h1>冷链履约异常协同工作台</h1>` 这类组件外长配置/展示壳。"
                " 禁止返回 `frontend/src/App.tsx`、禁止返回 `\"frontend/src/App.tsx\"`、也不要输出 `import { Routes, Route, Navigate, Link` 这类 App 壳层路由代码。"
                " H1 必须是中文首页/工作台标题，不要把 `APP_PROFILE.product_name` 直接写成首页主标题。"
                " 如需表格，请直接输出原生 `<table>`，不要用 antd `Table columns`。"
            )
        if is_assets_module_retry:
            user_prompt += (
                " 当前是 AssetsPage.tsx 回补，但业务主题以当前模块画像为准；不要写资产台账、资产名称、资产类别或固定资产管理。"
                " 不要再返回 `import React, { useState } from 'react'`、`import { Input, Button, Card, Typography, Tag } from 'antd'`"
                " 或 `const AssetsPage: React.FC = ...` 这种旧重型实现。"
                " 也不要返回 `function AssetsPage() { const items = [{ id, topic, role, status, tag, updateTime }] ... }`"
                " 并把主题写成“候选人管理”“人才档案库”“应聘者全旅程管理”之类历史模块；页面主标题必须逐字使用当前模块标题。"
                " 也不要返回 `import React from 'react'` + `import { Button } from 'antd'` + `import { APP_PROFILE } from '../generated/appProfile'` + `<div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>`"
                " 再把 H1 写成“面试管理”的通用轻壳页。"
                " 也不要返回 `import React from 'react'` + `import { APP_PROFILE } from '../generated/appProfile'` + `<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`"
                " 再把 H1 写成“面试流程管理”或把 `APP_PROFILE.productName` 当成正文说明的蓝色轻壳页。"
            )
        if is_workflow_module_retry:
            user_prompt += (
                " 当前是 WorkflowPage.tsx 回补，但业务主题以当前模块画像为准；不要默认写成流程跟进、步骤条、时间轴或阶段推进页面。"
                " 请改成无 hooks 的普通函数组件，不要用 React.FC、useState、Input、Card、Space、Typography、Tag，"
                " 直接输出原生 input/table 的最小页面，并使用命名导入 APP_PROFILE。"
                " 不要再返回 `import React, { useState } from 'react'`、`import { Input, Button, Card, Tag, Space } from 'antd'`、"
                " `import APP_PROFILE from '../generated/appProfile'` 或 `const WorkflowPage: React.FC = ...` 这种旧错误实现。"
                " 也不要返回 `const platformName = APP_PROFILE.product_name || '...'` 配合通用 `<div style=...>` 壳页面；"
                " 也不要返回 `import { Button } from 'antd'` 再配合统一蓝色内联样式壳、只放一个按钮和一段摘要的通用轻壳页；"
                " 也不要返回 `import React from 'react'` + `import { APP_PROFILE } from '../generated/appProfile'` + 白底通用内联样式壳"
                "（如 `background: '#ffffff'`、`minHeight: '100vh'`、`color: '#111'` / `'#555'`）的轻壳页；"
                " 也不要返回 `const WorkflowPage = () =>` + `<div style={{ padding: 24 }}>` + 先显示 `APP_PROFILE.product_name`"
                " 再把 H1 写成“候选人管理”的通用白页壳；"
                " 也不要返回 `import React from 'react'` + `function WorkflowPage() { return ( <div style={{ padding: 24 }}> ... ) }`"
                " 并在顶部先用灰色小字显示 `APP_PROFILE.product_name`、正文再放历史模块标题的面包屑式轻壳；"
                " 也不要返回 `<div style={{ color: '#888', fontSize: 12 }}>{APP_PROFILE.product_name} / 候选人管理</div>`"
                " 这种产品名 / 历史主题的面包屑式轻壳；"
                " H1 必须逐字等于当前模块标题，不能把 APP_PROFILE.product_name 当成页面标题，也不能写成“候选人管理”之类历史主题。"
            )
        if is_records_module_retry:
            user_prompt += (
                " 当前是 RecordsPage.tsx 回补，请只保留档案检索、新建入口和档案表，不要写详情抽屉、批量操作或复杂筛选面板。"
                " 不要再返回 `import React, { useState } from 'react'`、`import { Table, Button, Input, Space, Typography, Tag } from 'antd'`"
                " 或 `const RecordsPage: React.FC = ...` 这种旧重型实现。"
                " 也不要返回 `import APP_PROFILE from '../generated/appProfile'`、`const productName = APP_PROFILE?.productName || '...'`"
                " 或标题写成“招聘需求管理”“院校客户管理”“职位管理”“职位与需求管理”的通用壳页；页面主标题必须逐字等于当前模块标题。"
                " 也不要返回 `const data = [{ id, topic, role, status, tag, time }]`、`const data = [{ id, topic, role, status, tag, updateTime }]`、`MOD0-001`/`MOD0-002`"
                " 加“重点事项”这种通用样例数组；表头和行数据必须逐字贴合当前模块提供的真实字段。"
                " 也不要返回 `import React from 'react';` + `import { APP_PROFILE } from '../generated/appProfile';`"
                " 再配合 `<div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>` 和顶部 `justifyContent: 'space-between'` 的米色轻壳页。"
            )
        if is_analytics_module_retry:
            user_prompt += (
                " 当前是 AnalyticsPage.tsx 回补，但业务主题以当前模块画像为准；不要写通用分析中心、数据分析台或其他历史项目标题。"
                " 不要再返回 `import React from 'react'`、`import { Typography, Input, Button, Space, Card, Tag } from 'antd'`、"
                " `import { SearchOutlined, PlusOutlined } from '@ant-design/icons'`、`const { Title, Text } = Typography`"
                " 或 `const AnalyticsPage: React.FC = ...` 这种通用重型分析页模板；"
                " 请改成无 hooks 的普通函数组件，使用原生 input + 少量摘要块 + 原生 table。"
            )
        if is_reports_module_retry:
            user_prompt += (
                " 当前是 ReportsPage.tsx 回补，但业务主题以当前模块画像为准；不要写通用报表中心、招聘报表中心或其他历史项目标题。"
                " 不要再返回 `import React, { useState } from 'react'`、`import { Input, Button, Table, Card, Row, Col, Statistic, Typography, Space } from 'antd'`、"
                " `import { SearchOutlined, FileTextOutlined } from '@ant-design/icons'` 或通用重型报表页模板；"
                " 请改成无 hooks 的普通函数组件，使用原生 input + 少量摘要块 + 原生 table。"
                " 也不要再返回 `<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`"
                " 配合 `fontFamily:` 并把 H1 写成“录用与Offer管理”的蓝色历史主题轻壳页。"
            )
        if is_statistics_module_retry:
            user_prompt += (
                " 当前是 StatisticsPage.tsx 回补，但业务主题以当前模块画像为准；不要写通用统计中心、数据统计中心或其他历史项目标题。"
                " 不要再返回 `import React from 'react'`、`import { Input, Button, Card, Row, Col, Typography } from 'antd'`、"
                " `import { SearchOutlined, BarChartOutlined } from '@ant-design/icons'`、`const { Title, Text } = Typography`"
                " 或 `const StatisticsPage: React.FC = ...` 这种通用重型统计页模板；"
                " 请改成无 hooks 的普通函数组件，使用原生 input + 少量摘要块 + 原生 table。"
                " 也不要再返回 `<div style={{ padding: '24px 32px', background: '#f3f6fb' }}>`"
                " 配合 `fontFamily:` 的蓝色通用轻壳页。"
                " 也不要再返回 `const productName = APP_PROFILE.productName || '...'` + `<div style={{ padding: 24, fontFamily: 'system-ui, -apple-system, sans-serif' }}>`"
                " 再把 H1 写成“统计分析”的通用统计轻壳页。"
                " 也不要再返回 `function StatisticsPage() { const productName = APP_PROFILE.productName || '...'`"
                " 并配合 `<h1 style={{ marginBottom: 8, fontSize: 24, fontWeight: 600 }}>统计分析</h1>` 的 preview 级通用统计壳。"
                " 也不要再返回 `const { productName } = APP_PROFILE;` + `<div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>`"
                " 并把副标题写成 `{productName} - 分析中心` 的居中统计壳。"
                " 也不要再返回 `import React from 'react'` + `style={styles.container}` + `style={styles.title}` + `style={styles.subtitle}`"
                " 并把主标题写成“数据分析与看板”的通用数据看板壳。"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        max_tokens_override = 12000
        temperature_override = 0.2
        if is_single_app_batch:
            max_tokens_override = 5200
            temperature_override = 0.1
        elif is_single_dashboard_batch:
            max_tokens_override = 3200
            temperature_override = 0.1
        elif is_single_module_retry:
            max_tokens_override = 2600 if (
                is_assets_module_retry
                or is_workflow_module_retry
                or is_records_module_retry
                or is_analytics_module_retry
                or is_reports_module_retry
                or is_statistics_module_retry
            ) else 3200
            temperature_override = 0.05 if (
                is_assets_module_retry
                or is_workflow_module_retry
                or is_records_module_retry
                or is_analytics_module_retry
                or is_reports_module_retry
                or is_statistics_module_retry
            ) else 0.1

        if use_plaintext_single_file:
            file_path = required_files[0]

            async def _request_single_file(*, model: str, extra_user_note: str = "") -> LLMResponse:
                request_messages = messages
                if extra_user_note:
                    request_messages = [
                        messages[0],
                        {"role": "user", "content": messages[1]["content"] + extra_user_note},
                    ]
                raw_resp = await self.chat_with_models(
                    request_messages,
                    response_format="text",
                    primary_model=model,
                    max_tokens_override=max_tokens_override,
                    temperature_override=temperature_override,
                )
                if not raw_resp.success:
                    return raw_resp

                content = self._extract_code_content(raw_resp.text)
                if content.lstrip().startswith("{"):
                    parsed, parse_error = self._parse_json_object_content(content)
                    files = parsed.get("files") if isinstance(parsed, dict) else None
                    if isinstance(files, dict) and isinstance(files.get(file_path), str):
                        content = str(files[file_path]).strip()
                    elif parse_error:
                        logger.warning(
                            "single-file plaintext mode received JSON-like content but could not recover: %s",
                            parse_error,
                        )

                return LLMResponse(
                    success=True,
                    text=content,
                    structured={"files": {file_path: content}},
                )

            async def _request_single_file_json_recovery(*, model: str, extra_user_note: str = "") -> LLMResponse:
                request_messages = messages
                recovery_note = (
                    "\n\n前两次单文件纯文本返回为空。"
                    " 这一次改为 JSON 对象协议，但最终只允许返回一个 files 对象，"
                    f" 且只能包含键 `{file_path}`。"
                    " 请务必返回完整 TSX 源码，不要返回空字符串、占位说明或其他文件。"
                )
                if extra_user_note:
                    recovery_note += extra_user_note
                request_messages = [
                    messages[0],
                    {"role": "user", "content": messages[1]["content"] + recovery_note},
                ]
                raw_resp = await self.chat_with_models(
                    request_messages,
                    response_format="json_object",
                    primary_model=model,
                    max_tokens_override=max_tokens_override,
                    temperature_override=temperature_override,
                )
                if not raw_resp.success:
                    return raw_resp

                files = raw_resp.structured.get("files") if isinstance(raw_resp.structured, dict) else None
                content = ""
                if isinstance(files, dict) and isinstance(files.get(file_path), str):
                    content = str(files[file_path]).strip()
                if not content:
                    parsed, _ = self._parse_json_object_content(raw_resp.text)
                    parsed_files = parsed.get("files") if isinstance(parsed, dict) else None
                    if isinstance(parsed_files, dict) and isinstance(parsed_files.get(file_path), str):
                        content = str(parsed_files[file_path]).strip()

                if not content:
                    return LLMResponse(success=False, error="empty code body")

                return LLMResponse(
                    success=True,
                    text=content,
                    structured={"files": {file_path: content}},
                )

            raw_resp = await _request_single_file(model=REASONING_MODEL)
            if not raw_resp.success:
                return raw_resp
            if raw_resp.text:
                return raw_resp

            logger.warning(
                "single-file plaintext mode returned empty content for %s with model=%s; retrying with %s",
                file_path,
                REASONING_MODEL,
                TEXT_MODEL,
            )
            fallback_resp = await _request_single_file(
                model=TEXT_MODEL,
                extra_user_note=(
                    "\n\n上一次返回为空。请这一次立即从第一行开始输出完整 TSX 源码，"
                    " 不要输出任何解释、空行、JSON 外壳或占位文字。"
                ),
            )
            if not fallback_resp.success:
                return fallback_resp
            if not fallback_resp.text:
                logger.warning(
                    "single-file plaintext mode still empty for %s with model=%s; retrying with structured json recovery via %s",
                    file_path,
                    TEXT_MODEL,
                    REASONING_MODEL,
                )
                return await _request_single_file_json_recovery(
                    model=REASONING_MODEL,
                    extra_user_note=(
                        " 只允许返回 `{\"files\": {\"目标文件路径\": \"完整源码\"}}` 这一层结构，"
                        " 不要省略 files，也不要返回空文件内容。"
                    ),
                )
            return fallback_resp

        return await self.chat_with_models(
            messages,
            response_format="json_object",
            primary_model=REASONING_MODEL,
            max_tokens_override=max_tokens_override,
            temperature_override=temperature_override,
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
8. `required_manual_modules` 是系统固定必选章节，你无需改动；你需要从 `optional_manual_modules` 备选池中挑选 4 到 7 个最适合当前产品的模块 key，填入 `selected_optional_modules`，让不同产品的说明书扩展章节可以有变化。
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
