from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.llm import LLMClient, LLMConfig, LLMResponse, get_llm_client


class TestLLMConfig:
    def test_default_config(self):
        config = LLMConfig()
        assert config.provider == "deepseek"
        assert config.model == "deepseek-v4-pro"
        assert config.fallback_model == "deepseek-v4-flash"
        assert config.api_base == "https://api.deepseek.com"

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

    def test_get_client_returns_template_when_no_key(self):
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("LLM_API_KEY", None)

        from app.services.llm import TemplateLLMClient
        client = get_llm_client()
        assert isinstance(client, TemplateLLMClient)

    def test_template_generate_prd(self):
        from app.services.llm import TemplateLLMClient
        import asyncio

        async def _run():
            client = TemplateLLMClient()
            resp = await client.generate_prd("测试", "测试系统", "V1.0", "物流")
            assert resp.success
            assert "测试系统" in resp.text
            assert "core_modules" in resp.structured.get("prd_summary", {})

        asyncio.run(_run())

    def test_config_loads_from_env(self):
        os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"
        try:
            config = LLMClient._load_config(LLMClient(LLMConfig(api_key="")))
            assert config.api_key == "sk-test-key"
        finally:
            del os.environ["DEEPSEEK_API_KEY"]
