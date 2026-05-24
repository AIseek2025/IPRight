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

    def test_parse_json_object_content_repairs_raw_newlines_inside_strings(self):
        parsed, error = LLMClient._parse_json_object_content(
            '{"prd_markdown":"# 电力调度平台 V1.0 产品需求文档\n\n## 1. 产品概述\n电力调度平台用于调度中心。","prd_summary":{"app_type":"admin_web"}}'
        )
        assert not error
        assert parsed["prd_markdown"].startswith("# 电力调度平台 V1.0 产品需求文档")
        assert parsed["prd_summary"]["app_type"] == "admin_web"

    def test_parse_json_object_content_repairs_trailing_commas_in_prd_payload(self):
        parsed, error = LLMClient._parse_json_object_content(
            '{\n'
            '  "prd_markdown": "# 冷链协同平台\\n\\n## 1. 概述",\n'
            '  "prd_summary": {"app_type": "admin_web", "core_modules": ["监控", "协同"],},\n'
            '  "work_order_markdown": "# Work",\n'
            '}\n'
        )
        assert not error
        assert parsed["prd_markdown"].startswith("# 冷链协同平台")
        assert parsed["prd_summary"]["app_type"] == "admin_web"
        assert parsed["work_order_markdown"] == "# Work"

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
        assert captured["max_tokens_override"] == 12000
        assert captured["temperature_override"] == 0.2
        assert "不得挪用任何历史任务的行业素材" in captured["messages"][0]["content"]
        assert "raw_user_request" in captured["messages"][0]["content"]

    def test_generate_app_code_uses_compact_mode_for_invalid_app_retry(self, monkeypatch):
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
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/App.tsx"],
                    "invalid_core_previews": {"frontend/src/App.tsx": "import { Layout, Menu } from 'antd';"},
                },
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert captured["parse_json_response"] is False
        assert captured["max_tokens_override"] == 5200
        assert captured["temperature_override"] == 0.1
        assert "当前仅允许重写 `frontend/src/App.tsx`" in captured["messages"][0]["content"]
        assert "不要导入或使用 `Layout`、`Sider`、`Menu`、`Dropdown`" in captured["messages"][0]["content"]
        assert "`useMemo`、`useLocation`、`useNavigate`、`NavLink`" in captured["messages"][0]["content"]
        assert "`Row, Col, Card, Button, Space`" in captured["messages"][0]["content"]
        assert "这次只修复 App.tsx" in captured["messages"][1]["content"]

    def test_generate_app_code_uses_compact_mode_for_initial_single_app_batch(self, monkeypatch):
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
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/App.tsx"],
                },
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert captured["parse_json_response"] is False
        assert captured["max_tokens_override"] == 5200
        assert captured["temperature_override"] == 0.1
        assert "当前仅允许重写 `frontend/src/App.tsx`" in captured["messages"][0]["content"]
        assert "即便这是首轮 `App.tsx` 生成" in captured["messages"][0]["content"]
        assert "`useMemo`、`useLocation`、`useNavigate`、`NavLink`" in captured["messages"][0]["content"]
        assert "当前只允许输出 App.tsx" in captured["messages"][1]["content"]

    def test_generate_app_code_uses_dashboard_icon_guard_for_invalid_retry(self, monkeypatch):
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
            return LLMResponse(
                success=True,
                text='{"files":{"frontend/src/pages/Dashboard.tsx":"ok"}}',
                structured={"files": {"frontend/src/pages/Dashboard.tsx": "ok"}},
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/pages/Dashboard.tsx"],
                    "invalid_core_previews": {
                        "frontend/src/pages/Dashboard.tsx": "import { BriefcaseOutlined } from '@ant-design/icons';",
                    },
                },
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert captured["parse_json_response"] is False
        assert captured["max_tokens_override"] == 3200
        assert captured["temperature_override"] == 0.1
        assert "当前仅允许重写 `frontend/src/pages/Dashboard.tsx`" in captured["messages"][0]["content"]
        assert "禁止 `BriefcaseOutlined`" in captured["messages"][0]["content"]
        assert "必须使用精确组件签名 `export default function Dashboard()`" in captured["messages"][0]["content"]
        assert "不要在组件外声明 `const items = [`" in captured["messages"][0]["content"]
        assert "`const columns = [`" in captured["messages"][0]["content"]
        assert "`const recentActivities = [`" in captured["messages"][0]["content"]
        assert "`const fallbackMetrics = [`" in captured["messages"][0]["content"]
        assert "`const iconMap: Record<string, React.ReactNode>`" in captured["messages"][0]["content"]
        assert "`const { Title } = Typography`" in captured["messages"][0]["content"]
        assert "`const metrics = APP_PROFILE.dashboard_metrics`" in captured["messages"][0]["content"]
        assert "`const metrics = APP_PROFILE.dashboard_metrics || []`" in captured["messages"][0]["content"]
        assert "`const metrics = (APP_PROFILE as any).dashboard_metrics`" in captured["messages"][0]["content"]
        assert "`metrics.map((item) =>`" in captured["messages"][0]["content"]
        assert "`import { CheckCircleOutlined, ExclamationCircleOutlined, ClockCircleOutlined, TeamOutlined } from '@ant-design/icons'`" in captured["messages"][0]["content"]
        assert "`import { TeamOutlined, CalendarOutlined, FileTextOutlined, UserOutlined } from '@ant-design/icons'`" in captured["messages"][0]["content"]
        assert "`import { FileTextOutlined, UserOutlined, CalendarOutlined, CheckCircleOutlined } from '@ant-design/icons'`" in captured["messages"][0]["content"]
        assert "`import { Card, Statistic } from 'antd'` + `CalendarOutlined + TeamOutlined`" in captured["messages"][0]["content"]
        assert "`import { APP_PROFILE } from './generated/appProfile'`" in captured["messages"][0]["content"]
        assert "`<div style={{ padding: '16px' }}>`" in captured["messages"][0]["content"]
        assert "`<p style={{ color: '#555' }}>{APP_PROFILE.product_name}</p>`" in captured["messages"][0]["content"]
        assert "`<h1>工作台</h1>`" in captured["messages"][0]["content"]
        assert "`<div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>`" in captured["messages"][0]["content"]
        assert "`<div style={{ padding: '24px', background: '#f8f5ef', minHeight: '100vh' }}>`" in captured["messages"][0]["content"]
        assert "`<div style={{ margin: 24 }}>`" in captured["messages"][0]["content"]
        assert "`<div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 24px' }}>`" in captured["messages"][0]["content"]
        assert "`<h1>异常监控总览</h1>`" in captured["messages"][0]["content"]
        assert "`<div style={{ padding: '1.5rem 2rem' }}>`" in captured["messages"][0]["content"]
        assert "`<h1>冷链履约异常协同工作台</h1>`" in captured["messages"][0]["content"]
        assert "`<div style={{ padding: 24 }}>`" in captured["messages"][0]["content"]
        assert "`<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`" in captured["messages"][0]["content"]
        assert "`const recentEvents = [`" in captured["messages"][0]["content"]
        assert "`{ code: 'E-001', type: '温度超标', status: '处理中', time: '2025-06-01 10:30' }`" in captured["messages"][0]["content"]
        assert "`<div style={{ padding: '32px 40px', maxWidth: 1200, margin: '0 auto' }}>`" in captured["messages"][0]["content"]
        assert "`<div style={{ padding: '24px 32px', background: '#f0fdf9' }}>`" in captured["messages"][0]["content"]
        assert "`BarChartOutlined + ExclamationCircleOutlined + ClockCircleOutlined + FileTextOutlined`" in captured["messages"][0]["content"]
        assert '"frontend/src/App.tsx"' in captured["messages"][0]["content"]
        assert "`import { Routes, Route, Navigate, Link`" in captured["messages"][0]["content"]
        assert "当前只允许输出 Dashboard.tsx" in captured["messages"][1]["content"]
        assert "不要再导入 BriefcaseOutlined" in captured["messages"][1]["content"]
        assert "直接输出短版 `export default function Dashboard()`" in captured["messages"][1]["content"]
        assert "`const metrics = ...`" in captured["messages"][1]["content"]
        assert "`const items = [`" in captured["messages"][1]["content"]
        assert "`const recentActivities = [`" in captured["messages"][1]["content"]
        assert "`const fallbackMetrics = [`" in captured["messages"][1]["content"]
        assert "`const iconMap: Record<string, React.ReactNode>`" in captured["messages"][1]["content"]
        assert "`const { Title } = Typography`" in captured["messages"][1]["content"]
        assert "`const metrics = APP_PROFILE.dashboard_metrics`" in captured["messages"][1]["content"]
        assert "`const metrics = APP_PROFILE.dashboard_metrics || []`" in captured["messages"][1]["content"]
        assert "`const metrics = (APP_PROFILE as any).dashboard_metrics`" in captured["messages"][1]["content"]
        assert "`metrics.map((item) =>`" in captured["messages"][1]["content"]
        assert "`import { CheckCircleOutlined, ExclamationCircleOutlined, ClockCircleOutlined, TeamOutlined } from '@ant-design/icons'`" in captured["messages"][1]["content"]
        assert "`import { TeamOutlined, CalendarOutlined, FileTextOutlined, UserOutlined } from '@ant-design/icons'`" in captured["messages"][1]["content"]
        assert "`import { FileTextOutlined, UserOutlined, CalendarOutlined, CheckCircleOutlined } from '@ant-design/icons'`" in captured["messages"][1]["content"]
        assert "`import { APP_PROFILE } from './generated/appProfile'`" in captured["messages"][1]["content"]
        assert "`<div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>`" in captured["messages"][1]["content"]
        assert "`<div style={{ padding: '24px', background: '#f8f5ef', minHeight: '100vh' }}>`" in captured["messages"][1]["content"]
        assert "`<div style={{ margin: 24 }}>`" in captured["messages"][1]["content"]
        assert "`<div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 24px' }}>`" in captured["messages"][1]["content"]
        assert "`<h1>异常监控总览</h1>`" in captured["messages"][1]["content"]
        assert "`<div style={{ padding: '1.5rem 2rem' }}>`" in captured["messages"][1]["content"]
        assert "`<h1>冷链履约异常协同工作台</h1>`" in captured["messages"][1]["content"]
        assert "`<div style={{ padding: 24 }}>`" in captured["messages"][1]["content"]
        assert "`<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`" in captured["messages"][1]["content"]
        assert "`const recentEvents = [`" in captured["messages"][1]["content"]
        assert "`{ code: 'E-002', type: '运输延迟', status: '待处理', time: '2025-06-01 09:15' }`" in captured["messages"][1]["content"]
        assert "`<div style={{ padding: '32px 40px', maxWidth: 1200, margin: '0 auto' }}>`" in captured["messages"][1]["content"]
        assert "`<div style={{ padding: '24px 32px', background: '#f0fdf9' }}>`" in captured["messages"][1]["content"]
        assert '"frontend/src/App.tsx"' in captured["messages"][1]["content"]
        assert "`import { Routes, Route, Navigate, Link`" in captured["messages"][1]["content"]
        assert "原生 `<table>`" in captured["messages"][1]["content"]

    def test_generate_app_code_uses_compact_mode_for_single_module_retry(self, monkeypatch):
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
            return LLMResponse(
                success=True,
                text='{"files":{"frontend/src/pages/WorkflowPage.tsx":"ok"}}',
                structured={"files": {"frontend/src/pages/WorkflowPage.tsx": "ok"}},
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/pages/WorkflowPage.tsx"],
                    "invalid_module_previews": {
                        "frontend/src/pages/WorkflowPage.tsx": "const mockData = [{ id: '1' }];",
                    },
                },
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert captured["parse_json_response"] is False
        assert captured["max_tokens_override"] == 2600
        assert captured["temperature_override"] == 0.05
        assert "仅当本轮不是单文件回补/单文件批次时" in captured["messages"][0]["content"]
        assert "禁止输出 `frontend/src/App.tsx`" in captured["messages"][0]["content"]
        assert "模块页回补时不得生成任何全局壳层" in captured["messages"][0]["content"]
        assert "当前回补页面是 `WorkflowPage.tsx`" in captured["messages"][0]["content"]
        assert "不要使用 `Table` 组件、`ColumnsType`" in captured["messages"][0]["content"]
        assert "当前只允许输出这个模块页文件" in captured["messages"][1]["content"]
        assert "不要默认写成流程跟进、步骤条、时间轴或阶段推进页面" in captured["messages"][1]["content"]

    def test_generate_app_code_uses_module_payload_for_assets_retry(self, monkeypatch):
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
            return LLMResponse(
                success=True,
                text='{"files":{"frontend/src/pages/AssetsPage.tsx":"ok"}}',
                structured={"files": {"frontend/src/pages/AssetsPage.tsx": "ok"}},
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/pages/AssetsPage.tsx"],
                    "module_pages": [
                        {
                            "file_path": "frontend/src/pages/AssetsPage.tsx",
                            "title": "人才档案库",
                            "route": "/assets",
                            "primary_action": "新建人才档案库事项",
                            "filter_placeholder": "搜索人才档案库相关的融合招聘一体化软件/教育",
                            "table_headers": ["记录编号", "主题名称", "责任角色", "当前状态"],
                            "rows": [
                                ["MOD0-001", "融合招聘一体化软件人才档案库", "系统管理员", "处理中"],
                                ["MOD0-002", "融合招聘一体化软件重点事项", "招聘主管", "待审核"],
                            ],
                            "page_variant": "records",
                        }
                    ],
                    "invalid_module_previews": {
                        "frontend/src/pages/AssetsPage.tsx": "const mockData = [{ id: '1' }];",
                    },
                },
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert captured["parse_json_response"] is False
        assert captured["max_tokens_override"] == 2600
        assert captured["temperature_override"] == 0.05
        assert "当前模块必须保留这些真实业务要素" in captured["messages"][0]["content"]
        assert "标题 `人才档案库`" in captured["messages"][0]["content"]
        assert "禁止声明 `const mockData`" in captured["messages"][0]["content"]
        assert "禁止写成 `../../generated/appProfile`" in captured["messages"][0]["content"]
        assert "import APP_PROFILE from '../generated/appProfile'" in captured["messages"][0]["content"]
        assert "不要默认写成资产台账" in captured["messages"][0]["content"]
        assert "const AssetsPage: React.FC = ..." in captured["messages"][0]["content"]
        assert "候选人管理" in captured["messages"][0]["content"]
        assert "const items = [{ id, topic, role, status, tag, updateTime }]" in captured["messages"][0]["content"]
        assert "import React from 'react'" in captured["messages"][0]["content"]
        assert "import { Button } from 'antd'" in captured["messages"][0]["content"]
        assert "<div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>" in captured["messages"][0]["content"]
        assert "面试管理" in captured["messages"][0]["content"]
        assert "background: '#f3f6fb'" in captured["messages"][0]["content"]
        assert "面试流程管理" in captured["messages"][0]["content"]
        assert "APP_PROFILE.productName" in captured["messages"][0]["content"]
        assert "必须使用命名导入 `import { APP_PROFILE } from '../generated/appProfile';`" in captured["messages"][1]["content"]
        assert "不要写资产台账、资产名称、资产类别" in captured["messages"][1]["content"]
        assert "const AssetsPage: React.FC = ..." in captured["messages"][1]["content"]
        assert "候选人管理" in captured["messages"][1]["content"]
        assert "import React from 'react'" in captured["messages"][1]["content"]
        assert "import { Button } from 'antd'" in captured["messages"][1]["content"]
        assert "<div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>" in captured["messages"][1]["content"]
        assert "面试管理" in captured["messages"][1]["content"]
        assert "background: '#f3f6fb'" in captured["messages"][1]["content"]
        assert "面试流程管理" in captured["messages"][1]["content"]
        assert "APP_PROFILE.productName" in captured["messages"][1]["content"]

    def test_generate_app_code_uses_module_payload_for_workflow_retry(self, monkeypatch):
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
            return LLMResponse(
                success=True,
                text='{"files":{"frontend/src/pages/WorkflowPage.tsx":"ok"}}',
                structured={"files": {"frontend/src/pages/WorkflowPage.tsx": "ok"}},
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/pages/WorkflowPage.tsx"],
                    "module_pages": [
                        {
                            "file_path": "frontend/src/pages/WorkflowPage.tsx",
                            "title": "人才库管理",
                            "route": "/workflow",
                            "primary_action": "新建人才库管理事项",
                            "filter_placeholder": "搜索人才库管理相关的融合招聘一体化软件/教育",
                            "table_headers": ["记录编号", "主题名称", "责任角色", "当前状态"],
                            "rows": [
                                ["MOD0-001", "融合招聘一体化软件人才库管理", "超级管理员", "处理中"],
                                ["MOD0-002", "融合招聘一体化软件重点事项", "招聘主管", "待审核"],
                            ],
                            "page_variant": "insight",
                        }
                    ],
                    "invalid_module_previews": {
                        "frontend/src/pages/WorkflowPage.tsx": "const mockData = [{ id: '1' }];",
                    },
                },
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert captured["parse_json_response"] is False
        assert captured["max_tokens_override"] == 2600
        assert captured["temperature_override"] == 0.05
        assert "标题 `人才库管理`" in captured["messages"][0]["content"]
        assert "不要默认写成人才流程跟进、步骤条、时间轴、阶段推进" in captured["messages"][0]["content"]
        assert "不要使用 `React.FC`、`useState`" in captured["messages"][0]["content"]
        assert "命名导入 `import { APP_PROFILE } from '../generated/appProfile';`" in captured["messages"][0]["content"]
        assert "禁止写成 `../../generated/appProfile`" in captured["messages"][0]["content"]
        assert "import APP_PROFILE from '../generated/appProfile'" in captured["messages"][0]["content"]
        assert "const platformName = APP_PROFILE.product_name || '...'" in captured["messages"][0]["content"]
        assert "import { Button } from 'antd'" in captured["messages"][0]["content"]
        assert "#f3f6fb" in captured["messages"][0]["content"]
        assert "import React from 'react'" in captured["messages"][0]["content"]
        assert "background: '#ffffff'" in captured["messages"][0]["content"]
        assert "const WorkflowPage = () =>" in captured["messages"][0]["content"]
        assert "<div style={{ padding: 24 }}>" in captured["messages"][0]["content"]
        assert "function WorkflowPage() { return ( <div style={{ padding: 24 }}> ... ) }" in captured["messages"][0]["content"]
        assert "灰色小字显示 `APP_PROFILE.product_name`" in captured["messages"][0]["content"]
        assert "候选人管理" in captured["messages"][0]["content"]
        assert "当前模块的真实业务要素是" in captured["messages"][1]["content"]
        assert "必须使用命名导入 `import { APP_PROFILE } from '../generated/appProfile';`" in captured["messages"][1]["content"]
        assert "不要默认写成流程跟进、步骤条、时间轴或阶段推进页面" in captured["messages"][1]["content"]
        assert "不要用 React.FC、useState、Input、Card、Space、Typography、Tag" in captured["messages"][1]["content"]
        assert "const WorkflowPage: React.FC = ..." in captured["messages"][1]["content"]
        assert "统一蓝色内联样式壳" in captured["messages"][1]["content"]
        assert "import React from 'react'" in captured["messages"][1]["content"]
        assert "background: '#ffffff'" in captured["messages"][1]["content"]
        assert "const WorkflowPage = () =>" in captured["messages"][1]["content"]
        assert "<div style={{ padding: 24 }}>" in captured["messages"][1]["content"]
        assert "function WorkflowPage() { return ( <div style={{ padding: 24 }}> ... ) }" in captured["messages"][1]["content"]
        assert "灰色小字显示 `APP_PROFILE.product_name`" in captured["messages"][1]["content"]
        assert "{APP_PROFILE.product_name} / 候选人管理" in captured["messages"][1]["content"]
        assert "候选人管理" in captured["messages"][1]["content"]
        assert "不能把 APP_PROFILE.product_name 当成页面标题" in captured["messages"][1]["content"]

    def test_generate_app_code_locks_exact_title_and_anchor_tokens_for_records_retry(self, monkeypatch):
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
            return LLMResponse(
                success=True,
                text='{"files":{"frontend/src/pages/RecordsPage.tsx":"ok"}}',
                structured={"files": {"frontend/src/pages/RecordsPage.tsx": "ok"}},
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/pages/RecordsPage.tsx"],
                    "module_pages": [
                        {
                            "file_path": "frontend/src/pages/RecordsPage.tsx",
                            "title": "职位与岗位管理",
                            "route": "/records",
                            "primary_action": "新建职位与岗位管理事项",
                            "filter_placeholder": "搜索职位与岗位管理相关的融合招聘一体化软件/教育",
                            "table_headers": ["记录编号", "主题名称", "责任角色", "当前状态"],
                            "rows": [
                                ["MOD0-001", "融合招聘一体化软件职位与岗位管理", "超级管理员", "处理中"],
                                ["MOD0-002", "融合招聘一体化软件重点事项", "招聘主管", "待审核"],
                            ],
                            "page_variant": "workspace",
                        }
                    ],
                    "invalid_module_previews": {
                        "frontend/src/pages/RecordsPage.tsx": "const mockData = [{ id: '1' }];",
                    },
                },
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert captured["max_tokens_override"] == 2600
        assert "当前模块首屏主标题（H1、页面标题或最显著标题）必须逐字使用 `职位与岗位管理`" in captured["messages"][0]["content"]
        assert "当前模块正文至少逐字保留这些业务锚点中的 2 个以上" in captured["messages"][0]["content"]
        assert "当前模块 page_variant=workspace" in captured["messages"][0]["content"]
        assert "const RecordsPage: React.FC = ..." in captured["messages"][0]["content"]
        assert "import APP_PROFILE from '../generated/appProfile'" in captured["messages"][0]["content"]
        assert "招聘需求管理" in captured["messages"][0]["content"]
        assert "const data = [{ id, topic, role, status, tag, time }]" in captured["messages"][0]["content"]
        assert "<div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>" in captured["messages"][0]["content"]
        assert "justifyContent: 'space-between'" in captured["messages"][0]["content"]
        assert "MOD0-001" in captured["messages"][1]["content"]
        assert "页面主标题必须逐字等于“职位与岗位管理”" in captured["messages"][1]["content"]
        assert "页面正文至少逐字出现这些锚点中的两个以上" in captured["messages"][1]["content"]
        assert "米色轻壳页" in captured["messages"][1]["content"]

    def test_generate_app_code_uses_compact_mode_for_analytics_retry(self, monkeypatch):
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
            return LLMResponse(
                success=True,
                text='{"files":{"frontend/src/pages/AnalyticsPage.tsx":"ok"}}',
                structured={"files": {"frontend/src/pages/AnalyticsPage.tsx": "ok"}},
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/pages/AnalyticsPage.tsx"],
                    "module_pages": [
                        {
                            "file_path": "frontend/src/pages/AnalyticsPage.tsx",
                            "title": "风险指标体系与模型管理",
                            "route": "/analytics",
                            "primary_action": "新增风险指标",
                            "filter_placeholder": "搜索风险指标体系与模型管理相关主题",
                            "table_headers": ["分析编号", "分析主题", "负责人"],
                            "rows": [
                                ["AN-202605-017", "新能源债券组合压力测试", "周铭"],
                                ["AN-202605-018", "授信敞口波动分析", "赵岚"],
                            ],
                            "page_variant": "insight",
                        }
                    ],
                    "invalid_module_previews": {
                        "frontend/src/pages/AnalyticsPage.tsx": "const AnalyticsPage: React.FC = ...",
                    },
                },
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert captured["parse_json_response"] is False
        assert captured["max_tokens_override"] == 2600
        assert captured["temperature_override"] == 0.05
        assert "当前回补页面是 `AnalyticsPage.tsx`" in captured["messages"][0]["content"]
        assert "不要写通用“分析中心”“数据分析台”" in captured["messages"][0]["content"]
        assert "import { Typography, Input, Button, Space, Card, Tag } from 'antd'" in captured["messages"][0]["content"]
        assert "SearchOutlined, PlusOutlined" in captured["messages"][0]["content"]
        assert "当前是 AnalyticsPage.tsx 回补" in captured["messages"][1]["content"]
        assert "通用重型分析页模板" in captured["messages"][1]["content"]
        assert "使用原生 input + 少量摘要块 + 原生 table" in captured["messages"][1]["content"]

    def test_generate_app_code_uses_compact_mode_for_reports_retry(self, monkeypatch):
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
            return LLMResponse(
                success=True,
                text='{"files":{"frontend/src/pages/ReportsPage.tsx":"ok"}}',
                structured={"files": {"frontend/src/pages/ReportsPage.tsx": "ok"}},
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/pages/ReportsPage.tsx"],
                    "module_pages": [
                        {
                            "file_path": "frontend/src/pages/ReportsPage.tsx",
                            "title": "招聘成效分析",
                            "route": "/reports",
                            "primary_action": "导出招聘成效分析",
                            "filter_placeholder": "搜索招聘成效分析相关主题",
                            "table_headers": ["分析编号", "分析主题", "统计维度", "负责人"],
                            "rows": [
                                ["AN-001", "校招转化分析", "转化率", "运营主管"],
                                ["AN-002", "岗位闭环分析", "完成率", "招聘经理"],
                            ],
                            "page_variant": "reports",
                        }
                    ],
                    "invalid_module_previews": {
                        "frontend/src/pages/ReportsPage.tsx": "const mockData = [{ id: '1' }];",
                    },
                },
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert captured["parse_json_response"] is False
        assert captured["max_tokens_override"] == 2600
        assert captured["temperature_override"] == 0.05
        assert "当前回补页面是 `ReportsPage.tsx`" in captured["messages"][0]["content"]
        assert "不要写通用“报表中心”“招聘报表中心”" in captured["messages"][0]["content"]
        assert "import { Input, Button, Table, Card, Row, Col, Statistic, Typography, Space } from 'antd'" in captured["messages"][0]["content"]
        assert "SearchOutlined, FileTextOutlined" in captured["messages"][0]["content"]
        assert "录用与Offer管理" in captured["messages"][0]["content"]
        assert "<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>" in captured["messages"][0]["content"]
        assert "当前是 ReportsPage.tsx 回补" in captured["messages"][1]["content"]
        assert "通用重型报表页模板" in captured["messages"][1]["content"]
        assert "使用原生 input + 少量摘要块 + 原生 table" in captured["messages"][1]["content"]
        assert "录用与Offer管理" in captured["messages"][1]["content"]
        assert "<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>" in captured["messages"][1]["content"]

    def test_generate_app_code_uses_compact_mode_for_statistics_retry(self, monkeypatch):
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
            return LLMResponse(
                success=True,
                text='{"files":{"frontend/src/pages/StatisticsPage.tsx":"ok"}}',
                structured={"files": {"frontend/src/pages/StatisticsPage.tsx": "ok"}},
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/pages/StatisticsPage.tsx"],
                    "module_pages": [
                        {
                            "file_path": "frontend/src/pages/StatisticsPage.tsx",
                            "title": "统计报表",
                            "route": "/statistics",
                            "primary_action": "生成统计分析",
                            "filter_placeholder": "搜索统计报表相关主题",
                            "table_headers": ["分析编号", "分析主题", "统计维度", "负责人"],
                            "rows": [
                                ["AN-001", "图书借阅统计", "借阅量", "管理员"],
                                ["AN-002", "库存周报", "库存变化", "馆长"],
                            ],
                            "page_variant": "reports",
                        }
                    ],
                    "invalid_module_previews": {
                        "frontend/src/pages/StatisticsPage.tsx": "const StatisticsPage: React.FC = ...",
                    },
                },
            )
            assert resp.success

        asyncio.run(_run())
        assert captured["response_format"] == "json_object"
        assert captured["parse_json_response"] is False
        assert captured["max_tokens_override"] == 2600
        assert captured["temperature_override"] == 0.05
        assert "当前回补页面是 `StatisticsPage.tsx`" in captured["messages"][0]["content"]
        assert "通用“统计中心”“数据统计中心”" in captured["messages"][0]["content"]
        assert "import { Input, Button, Card, Row, Col, Typography } from 'antd'" in captured["messages"][0]["content"]
        assert "SearchOutlined, BarChartOutlined" in captured["messages"][0]["content"]
        assert "<div style={{ padding: '24px 32px', background: '#f3f6fb' }}>" in captured["messages"][0]["content"]
        assert "const productName = APP_PROFILE.productName" in captured["messages"][0]["content"]
        assert "<div style={{ padding: 24, fontFamily: 'system-ui, -apple-system, sans-serif' }}>" in captured["messages"][0]["content"]
        assert "fontWeight: 600" in captured["messages"][0]["content"]
        assert "const { productName } = APP_PROFILE;" in captured["messages"][0]["content"]
        assert "{productName} - 分析中心" in captured["messages"][0]["content"]
        assert "数据分析与看板" in captured["messages"][0]["content"]
        assert "style={styles.container}" in captured["messages"][0]["content"]
        assert "当前是 StatisticsPage.tsx 回补" in captured["messages"][1]["content"]
        assert "通用重型统计页模板" in captured["messages"][1]["content"]
        assert "使用原生 input + 少量摘要块 + 原生 table" in captured["messages"][1]["content"]
        assert "<div style={{ padding: '24px 32px', background: '#f3f6fb' }}>" in captured["messages"][1]["content"]
        assert "const productName = APP_PROFILE.productName" in captured["messages"][1]["content"]
        assert "H1 写成“统计分析”" in captured["messages"][1]["content"]
        assert "fontWeight: 600" in captured["messages"][1]["content"]
        assert "const { productName } = APP_PROFILE;" in captured["messages"][1]["content"]
        assert "{productName} - 分析中心" in captured["messages"][1]["content"]
        assert "数据分析与看板" in captured["messages"][1]["content"]
        assert "style={styles.container}" in captured["messages"][1]["content"]

    def test_generate_app_code_supports_plaintext_single_file_retry(self, monkeypatch):
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
            return LLMResponse(
                success=True,
                text="export default function WorkflowPage(){ return <section>ok</section>; }",
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/pages/WorkflowPage.tsx"],
                    "invalid_module_previews": {
                        "frontend/src/pages/WorkflowPage.tsx": "const mockData = [{ id: '1' }];",
                    },
                    "single_file_plaintext": True,
                },
            )
            assert resp.success
            assert resp.structured == {
                "files": {
                    "frontend/src/pages/WorkflowPage.tsx": "export default function WorkflowPage(){ return <section>ok</section>; }"
                }
            }

        asyncio.run(_run())
        assert captured["response_format"] == "text"
        assert captured["parse_json_response"] is False
        assert captured["max_tokens_override"] == 2600
        assert captured["temperature_override"] == 0.05
        assert "单文件纯文本协议" in captured["messages"][0]["content"]
        assert "请只返回目标文件源码，不要返回 JSON" in captured["messages"][1]["content"]

    def test_generate_app_code_supports_plaintext_single_file_dashboard(self, monkeypatch):
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
            captured["primary_model"] = primary_model
            captured["parse_json_response"] = parse_json_response
            captured["max_tokens_override"] = max_tokens_override
            captured["temperature_override"] = temperature_override
            return LLMResponse(
                success=True,
                text="import { APP_PROFILE } from '../generated/appProfile';\nexport default function Dashboard(){ return <section>{APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}</section>; }",
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/pages/Dashboard.tsx"],
                    "single_file_plaintext": True,
                },
            )
            assert resp.success
            assert resp.structured == {
                "files": {
                    "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile';\nexport default function Dashboard(){ return <section>{APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}</section>; }"
                }
            }

        asyncio.run(_run())
        assert captured["response_format"] == "text"
        assert captured["primary_model"] == REASONING_MODEL
        assert captured["parse_json_response"] is False
        assert captured["max_tokens_override"] == 3200
        assert captured["temperature_override"] == 0.1
        assert "当前目标文件是 `frontend/src/pages/Dashboard.tsx`" in captured["messages"][0]["content"]
        assert "当前文件是 Dashboard.tsx，请从第一行开始直接输出完整源码" in captured["messages"][1]["content"]
        assert "必须使用精确组件签名 `export default function Dashboard()`" in captured["messages"][0]["content"]
        assert "组件名必须是 `export default function Dashboard()`" in captured["messages"][1]["content"]
        assert "不要在组件外声明 `const items = [`" in captured["messages"][0]["content"]
        assert "`const columns = [`" in captured["messages"][0]["content"]
        assert "`const recentActivities = [`" in captured["messages"][0]["content"]
        assert "`const fallbackMetrics = [`" in captured["messages"][0]["content"]
        assert "`const { Title } = Typography`" in captured["messages"][0]["content"]
        assert "`const metrics = APP_PROFILE.dashboard_metrics || []`" in captured["messages"][0]["content"]
        assert "`<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`" in captured["messages"][1]["content"]
        assert "原生 `<table>`" in captured["messages"][1]["content"]

    def test_generate_app_code_retries_plaintext_single_file_with_text_model_when_first_response_empty(self, monkeypatch):
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
                    "messages": messages,
                    "response_format": response_format,
                    "primary_model": primary_model,
                    "parse_json_response": parse_json_response,
                    "max_tokens_override": max_tokens_override,
                    "temperature_override": temperature_override,
                }
            )
            if len(calls) == 1:
                return LLMResponse(success=True, text="")
            return LLMResponse(
                success=True,
                text="export default function WorkflowPage(){ return <section>ok</section>; }",
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/pages/WorkflowPage.tsx"],
                    "invalid_module_previews": {
                        "frontend/src/pages/WorkflowPage.tsx": "const mockData = [{ id: '1' }];",
                    },
                    "single_file_plaintext": True,
                },
            )
            assert resp.success
            assert resp.structured == {
                "files": {
                    "frontend/src/pages/WorkflowPage.tsx": "export default function WorkflowPage(){ return <section>ok</section>; }"
                }
            }

        asyncio.run(_run())
        assert len(calls) == 2
        assert calls[0]["response_format"] == "text"
        assert calls[0]["primary_model"] == REASONING_MODEL
        assert calls[1]["response_format"] == "text"
        assert calls[1]["primary_model"] == TEXT_MODEL
        assert "上一次返回为空。请这一次立即从第一行开始输出完整 TSX 源码" in calls[1]["messages"][1]["content"]

    def test_generate_app_code_recovers_plaintext_single_file_with_json_when_both_text_attempts_empty(self, monkeypatch):
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
                    "messages": messages,
                    "response_format": response_format,
                    "primary_model": primary_model,
                    "parse_json_response": parse_json_response,
                    "max_tokens_override": max_tokens_override,
                    "temperature_override": temperature_override,
                }
            )
            if len(calls) < 3:
                return LLMResponse(success=True, text="")
            return LLMResponse(
                success=True,
                text='{"files":{"frontend/src/pages/Dashboard.tsx":"export default function Dashboard(){ return <section>json-ok</section>; }"}}',
                structured={
                    "files": {
                        "frontend/src/pages/Dashboard.tsx": "export default function Dashboard(){ return <section>json-ok</section>; }"
                    }
                },
            )

        client = LLMClient(LLMConfig(api_key="sk-test"))
        monkeypatch.setattr(client, "chat_with_models", fake_chat_with_models)

        import asyncio

        async def _run():
            resp = await client.generate_app_code(
                "prd",
                "work",
                {
                    "required_files": ["frontend/src/pages/Dashboard.tsx"],
                    "single_file_plaintext": True,
                },
            )
            assert resp.success
            assert resp.structured == {
                "files": {
                    "frontend/src/pages/Dashboard.tsx": "export default function Dashboard(){ return <section>json-ok</section>; }"
                }
            }

        asyncio.run(_run())
        assert len(calls) == 3
        assert calls[0]["response_format"] == "text"
        assert calls[0]["primary_model"] == REASONING_MODEL
        assert calls[1]["response_format"] == "text"
        assert calls[1]["primary_model"] == TEXT_MODEL
        assert calls[2]["response_format"] == "json_object"
        assert calls[2]["primary_model"] == REASONING_MODEL
        assert "前两次单文件纯文本返回为空" in calls[2]["messages"][1]["content"]
        assert "只允许返回 `{\"files\": {\"目标文件路径\": \"完整源码\"}}`" in calls[2]["messages"][1]["content"]

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
        assert "原始用户输入（唯一主题源）" in captured["messages"][1]["content"]
        assert "重点关注调度令" in captured["messages"][1]["content"]
        assert "platform" not in captured["messages"][1]["content"].lower()

    def test_generate_manual_content_splits_overview_and_page_overrides(self, monkeypatch):
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
            if "页面名称:" in messages[1]["content"]:
                return LLMResponse(
                    success=True,
                    structured={
                        "caption": "图: 电网运行总览",
                        "description": "用于查看主网运行状态与关键指标。",
                        "steps": ["输入筛选条件", "查看运行结果"],
                    },
                )
            return LLMResponse(
                success=True,
                structured={
                    "development_background": "背景",
                    "development_purpose": "目的",
                    "module_overrides": [{"title": "电网运行总览", "description": "模块描述"}],
                    "role_permissions": {"管理员": "查看全部"},
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
        assert calls[0]["max_tokens_override"] == 5200
        assert '"screenshots"' in calls[0]["user"]
        assert "page_overrides" not in calls[0]["system"]
        assert any("页面名称:" in call["user"] for call in calls[1:])
        assert "提交给版权局" in calls[0]["system"]
        assert "以企业身份撰写" in calls[0]["system"]
        assert "该截图展示了" in calls[0]["system"]

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
