from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.llm import LLMClient, LLMConfig, LLMResponse, PRD_MODEL, TEXT_MODEL, REASONING_MODEL, get_llm_client


class TestLLMConfig:
    def test_default_config(self):
        config = LLMConfig()
        assert config.provider == "deepseek"
        assert config.model == "deepseek-v4-pro"
        assert config.fallback_model == "deepseek-v4-pro"
        assert config.prd_model == "deepseek-v4-flash"
        assert config.code_model == "deepseek-v4-pro"
        assert config.doc_model == "deepseek-v4-pro"
        assert config.api_base == "https://api.deepseek.com/v1"

    def test_custom_config(self):
        config = LLMConfig(
            provider="openai",
            model="gpt-4",
            api_base="https://custom.api/v1",
        )
        assert config.model == "gpt-4"


class TestLLMResponse:
    def test_success_response(self):
        resp = LLMResponse(success=True, text="Hello")
        assert resp.success
        assert resp.text == "Hello"

    def test_error_response(self):
        resp = LLMResponse(success=False, error="Bad request")
        assert not resp.success
        assert resp.error == "Bad request"

    def test_structured_response(self):
        resp = LLMResponse(success=True, structured={"key": "value"})
        assert resp.structured["key"] == "value"


class TestLLMClient:
    def test_no_api_key_returns_error(self):
        os.environ.pop("DASHSCOPE_API_KEY", None)
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("LLM_API_KEY", None)

        import asyncio

        async def _run():
            client = LLMClient(LLMConfig(api_key=""))
            resp = await client.chat([{"role": "user", "content": "hi"}])
            assert not resp.success
            assert "No LLM API key" in resp.error

        asyncio.run(_run())

    def test_get_client_returns_llm_client_even_when_no_key(self):
        os.environ.pop("DASHSCOPE_API_KEY", None)
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("LLM_API_KEY", None)
        client = get_llm_client()
        assert isinstance(client, LLMClient)

    def test_text_and_reasoning_model_constants(self):
        assert PRD_MODEL == "deepseek-v4-flash"
        assert TEXT_MODEL == "deepseek-v4-pro"
        assert REASONING_MODEL == "deepseek-v4-pro"

    def test_config_loads_from_env(self):
        os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"
        try:
            config = LLMClient._load_config(LLMClient(LLMConfig(api_key="")))
            assert config.api_key == "sk-test-key"
        finally:
            del os.environ["DEEPSEEK_API_KEY"]

    def test_config_prefers_deepseek_api_base_and_strips_wrapper_chars(self):
        os.environ["DEEPSEEK_API_BASE"] = " `https://api.deepseek.com/v1` "
        try:
            config = LLMClient._load_config(LLMClient(LLMConfig(api_key="sk-test")))
            assert config.api_base == "https://api.deepseek.com/v1"
        finally:
            del os.environ["DEEPSEEK_API_BASE"]

    def test_parse_json_object_content_accepts_fenced_json(self):
        parsed, error = LLMClient._parse_json_object_content("""```json
{"files":{"frontend/src/App.tsx":"export default function App(){return null;}"}}
```""")
        assert not error
        assert parsed["files"]["frontend/src/App.tsx"].startswith("export default function App")

    def test_parse_json_object_content_reports_invalid_json(self):
        parsed, error = LLMClient._parse_json_object_content("not valid json")
        assert parsed == {}
        assert error

    def test_parse_json_object_content_repairs_raw_newlines_inside_strings(self):
        parsed, error = LLMClient._parse_json_object_content(
            '{"prd_markdown":"# 电力调度平台 V1.0 产品需求文档\n\n## 1. 产品概述\n电力调度平台用于调度中心。","prd_summary":{"app_type":"admin_web"}}'
        )
        assert not error
        assert parsed["prd_markdown"].startswith("# 电力调度平台 V1.0 产品需求文档")
        assert parsed["prd_summary"]["app_type"] == "admin_web"

    def test_generate_app_code_uses_json_object_mode(self, monkeypatch):
        captured = {}

        async def fake_chat_with_models(
            messages,
            response_format="text",
            *,
            primary_model,
            fallback_model="",
            parse_json_response=False,
            max_tokens_override=None,
            temperature_override=None,
        ):
            captured["messages"] = messages
            captured["response_format"] = response_format
            captured["parse_json_response"] = parse_json_response
            captured["max_tokens_override"] = max_tokens_override
            captured["temperature_override"] = temperature_override
            return LLMResponse(success=True, text='{"files":{"frontend/src/App.tsx":"ok"}}', structured={"files": {"frontend/src/App.tsx": "ok"}})

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code("prd", "work", {"required_files": []})
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert captured["parse_json_response"] is False
        assert captured["max_tokens_override"] == 16000
        assert captured["temperature_override"] == 0.75
        assert "直接按照 PRD 开发" in captured["messages"][0]["content"]
        assert "required_files" in captured["messages"][1]["content"]
        assert "target_interface_count" not in captured["messages"][1]["content"]
        assert "raw_user_request" not in captured["messages"][1]["content"]

    def test_generate_app_code_constrains_app_shell_batch(self, monkeypatch):
        captured = {}

        async def fake_chat_with_models(
            messages,
            response_format="text",
            *,
            primary_model,
            fallback_model="",
            parse_json_response=False,
            max_tokens_override=None,
            temperature_override=None,
        ):
            captured["messages"] = messages
            captured["response_format"] = response_format
            captured["max_tokens_override"] = max_tokens_override
            captured["temperature_override"] = temperature_override
            return LLMResponse(
                success=True,
                text='{"files":{"frontend/src/App.tsx":"ok"}}',
                structured={"files": {"frontend/src/App.tsx": "ok"}},
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {"required_files": ["frontend/src/App.tsx"]},
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert captured["max_tokens_override"] == 9000
        assert captured["temperature_override"] == 0.75
        assert "轻量路由壳文件" in captured["messages"][1]["content"]
        assert "不要在 `App.tsx` 内联任何页面实现" in captured["messages"][1]["content"]

    def test_chat_with_models_reports_missing_choices_response(self, monkeypatch):
        class _Response:
            status_code = 200
            text = '{"error":{"message":"upstream missing completion choices"}}'

            @staticmethod
            def json():
                return {"error": {"message": "upstream missing completion choices"}}

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, *args, **kwargs):
                return _Response()

        import asyncio
        import httpx

        monkeypatch.setattr(httpx, "AsyncClient", _Client)

        async def _run():
            client = LLMClient(LLMConfig(api_key="sk-test", api_base="https://api.deepseek.com/v1"))
            resp = await client.chat_with_models(
                [{"role": "user", "content": "hi"}],
                response_format="json_object",
                primary_model="deepseek-v4-pro",
            )
            assert not resp.success
            assert "missing choices" in resp.error
            assert "upstream missing completion choices" in resp.error

        asyncio.run(_run())

    def test_generate_prd_uses_raw_user_request_as_source_of_truth(self, monkeypatch):
        captured = {}

        async def fake_chat_with_models(
            messages,
            response_format="text",
            *,
            primary_model,
            fallback_model="",
            parse_json_response=False,
            max_tokens_override=None,
            temperature_override=None,
        ):
            captured["messages"] = messages
            captured["response_format"] = response_format
            return LLMResponse(
                success=True,
                text='{"prd_markdown":"# PRD","work_order_markdown":"# Work","prd_summary":{"app_type":"admin_web","core_modules":["模块A","模块B","模块C","模块D"],"required_pages":["/login","/dashboard","/a"],"user_roles":["管理员"],"scene":"场景","industry_scope":"行业","core_entities":["对象A"]}}',
                structured={},
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_prd(
                keyword="电力调度平台",
                product_name="电力调度平台",
                version="V1.0",
                industry="电网调度",
                notes="重点关注调度令",
                plan_seed={"raw_user_request": {"keyword": "电力调度平台"}},
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert "原始输入:" in captured["messages"][1]["content"]
        assert "重点关注调度令" in captured["messages"][1]["content"]
        assert "required_pages" in captured["messages"][0]["content"]
        assert "plan_seed" not in captured["messages"][1]["content"].lower()

    def test_generate_manual_content_uses_single_prd_and_screenshots_prompt(self, monkeypatch):
        calls = []

        async def fake_chat_with_models(
            messages,
            response_format="text",
            *,
            primary_model,
            fallback_model="",
            parse_json_response=False,
            max_tokens_override=None,
            temperature_override=None,
        ):
            calls.append(
                {
                    "system": messages[0]["content"],
                    "user": messages[1]["content"],
                    "response_format": response_format,
                    "max_tokens_override": max_tokens_override,
                }
            )
            return LLMResponse(
                success=True,
                structured={
                    "development_background": "背景",
                    "development_purpose": "目的",
                    "module_overrides": [{"title": "电网运行总览", "description": "模块描述"}],
                    "role_permissions": {"管理员": "查看全部"},
                    "page_overrides": [
                        {
                            "page_title": "电网运行总览",
                            "route": "/grid",
                            "caption": "图: 电网运行总览",
                            "description": "用于查看主网运行状态与关键指标。",
                            "steps": ["输入筛选条件", "查看运行结果"],
                            "highlights": ["运行状态", "关键指标"],
                        }
                    ],
                },
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_manual_content(
                product_name="电力调度平台",
                version="V1.0",
                profile={
                    "keyword": "电力调度平台",
                    "topic_label": "电力调度平台",
                    "scene": "电网调度",
                    "modules": [{"title": "电网运行总览", "route": "/grid"}],
                    "user_roles": ["管理员"],
                },
                prd_summary={"required_pages": ["/login", "/dashboard", "/grid"]},
                screenshots_meta=[
                    {"page_title": "电网运行总览", "route": "/grid", "elements": ["搜索", "导出"]},
                ],
            )
            assert resp.success
            assert resp.structured["development_background"] == "背景"
            assert resp.structured["page_overrides"][0]["page_title"] == "电网运行总览"
            assert resp.structured["page_overrides"][0]["steps"] == ["输入筛选条件", "查看运行结果"]

        asyncio.run(_run())
        assert calls[0]["response_format"] == "json_object"
        assert calls[0]["max_tokens_override"] == 7600
        assert '"screenshots"' in calls[0]["user"]
        assert '"prd_markdown"' in calls[0]["user"]
        assert "page_overrides" in calls[0]["system"]
        assert len(calls) == 1
        assert "根据产品 PRD 和产品截图信息" in calls[0]["system"]
        assert "不要引入平台模板" in calls[0]["system"]

    def test_generate_page_description_uses_copyright_enterprise_tone(self, monkeypatch):
        captured = {}

        async def fake_chat_with_models(
            messages,
            response_format="text",
            *,
            primary_model,
            fallback_model="",
            parse_json_response=False,
            max_tokens_override=None,
            temperature_override=None,
        ):
            captured["messages"] = messages
            captured["response_format"] = response_format
            return LLMResponse(
                success=True,
                structured={
                    "caption": "图1 实时监控与分级预警",
                    "description": "本功能用于展示预警规则、处理状态和时间信息。",
                    "steps": ["输入筛选条件", "查看处理结果"],
                },
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_page_description(
                "实时监控与分级预警筛选结果",
                "/warnings",
                ["实时监控与分级预警", "新增预警规则", "查询列表", "导出结果"],
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert "提交给版权局的软件著作权申请材料" in captured["messages"][0]["content"]
        assert "不要再使用“该截图展示了”" in captured["messages"][0]["content"]
        assert "以企业申报软件著作权的正式口吻撰写" in captured["messages"][0]["content"]
