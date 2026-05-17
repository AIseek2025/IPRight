from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.services.llm import LLMClient, LLMConfig, LLMResponse, TEXT_MODEL, REASONING_MODEL, get_llm_client


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

    def test_get_client_returns_llm_client_even_when_no_key(self):
        os.environ.pop("DEEPSEEK_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("LLM_API_KEY", None)
        client = get_llm_client()
        assert isinstance(client, LLMClient)

    def test_text_and_reasoning_model_constants(self):
        assert TEXT_MODEL == "deepseek-v4-flash"
        assert REASONING_MODEL == "deepseek-v4-pro"

    def test_config_loads_from_env(self):
        os.environ["DEEPSEEK_API_KEY"] = "sk-test-key"
        try:
            config = LLMClient._load_config(LLMClient(LLMConfig(api_key="")))
            assert config.api_key == "sk-test-key"
        finally:
            del os.environ["DEEPSEEK_API_KEY"]

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
        assert captured["max_tokens_override"] == 12000
        assert captured["temperature_override"] == 0.2
