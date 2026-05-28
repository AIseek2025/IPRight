from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.state_machine import StageName, StageStatus, TOPLEVEL_TO_STAGE, TopLevelStatus
from workers.orchestrator.runner import (
    StageContext,
    StageResult,
    STAGE_HANDLERS,
)
from workers.stages.build_support import (
    _synthesize_app_tsx,
    _synthesize_support_runtime_files,
    build_codegen_batches,
    build_codegen_requirements,
    generate_task_app_code,
    hydrate_missing_files_from_template,
    normalize_generated_frontend_files,
    normalize_prd_summary_with_plan_seed,
    prepare_seed_application,
    repair_invalid_core_files,
    repair_invalid_support_files,
    repair_invalid_module_pages,
)
from workers.stages.generated_frontend import _ensure_frontend_dependencies, sync_frontend_dependencies
from workers.stages.generated_frontend import _render_login_page
from workers.stages.handlers import (
    _load_prd_summary,
    _merge_manual_llm_content,
    _derive_run_ports,
    run_plan_stage,
    run_build_stage,
    run_capture_stage,
    run_compose_manual_stage,
    run_compose_code_book_stage,
)
from workers.stages.delivery_support import load_screenshots_meta
from workers.stages.generated_backend import write_generated_backend_files
from workers.stages.generated_frontend import (
    _ensure_backend_dependencies,
    _ensure_frontend_dependencies,
    _render_font_css,
    _render_frontend_app,
    _render_login_page,
    _render_module_page,
)
from workers.stages.runtime_support import _collect_missing_essential_titles
from app.services.runtime import SandboxRuntime
from app.services.capture import PlaywrightCapture
from app.services.document.manual import OPTIONAL_MANUAL_MODULES


class TestStageHandlers:
    """Unit tests for individual stage handler functions."""

    def test_plan_stage_returns_valid_result(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock
        import asyncio
        from app.core.config import settings
        from app.services.llm import LLMResponse

        task_id = str(uuid.uuid4())

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.get = AsyncMock(
            return_value=SimpleNamespace(
                id=uuid.UUID(task_id),
                keyword="电力调度平台",
                product_name="电力调度平台",
                version="V1.0",
                industry="电网调度",
                notes="围绕真实电网调度业务设计",
            )
        )
        mock_session_factory = MagicMock()
        mock_session_scope = AsyncMock()
        mock_session_scope.__aenter__.return_value = mock_session
        mock_session_factory.return_value.return_value = mock_session_scope

        class FakeLLM:
            async def generate_prd(self, **kwargs):
                return LLMResponse(
                    success=True,
                    structured={
                        "prd_markdown": "# PRD",
                        "work_order_markdown": "# Work Order",
                        "prd_summary": {
                            "app_type": "admin_web",
                            "core_modules": ["电网运行总览", "负荷调度中心", "发电计划协同", "输变线路监测"],
                            "required_pages": ["/login", "/dashboard", "/grid-overview", "/load-dispatch"],
                            "user_roles": ["管理员", "调度长", "值班调度员"],
                            "scene": "电网运行监视、负荷调度与检修协同",
                            "industry_scope": "电网调度",
                            "core_entities": ["电网线路", "变电站", "调度指令"],
                        },
                    },
                )

        from app.services import llm as llm_module

        async def _run():
            ctx = StageContext(
                task_id=task_id,
                build_id=str(uuid.uuid4()),
                db_factory=mock_session_factory,
            )
            result = await run_plan_stage(ctx)
            return result

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(settings, "WORKSPACE_ROOT", str(Path.cwd() / ".tmp_test_workspace"))
            mp.setattr(llm_module, "get_llm_client", lambda: FakeLLM())
            result = asyncio.run(_run())
            assert isinstance(result, StageResult)
            assert result.success

    def test_plan_stage_fails_without_template_fallback_when_llm_unavailable(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, MagicMock
        import asyncio
        from app.core.config import settings
        from app.services.llm import LLMResponse

        task_id = str(uuid.uuid4())
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.get = AsyncMock(
            return_value=SimpleNamespace(
                id=uuid.UUID(task_id),
                keyword="电力调度平台",
                product_name="电力调度平台",
                version="V1.0",
                industry="电网调度",
                notes=None,
            )
        )
        mock_session_factory = MagicMock()
        mock_session_scope = AsyncMock()
        mock_session_scope.__aenter__.return_value = mock_session
        mock_session_factory.return_value.return_value = mock_session_scope

        class BrokenLLM:
            async def generate_prd(self, **kwargs):
                return LLMResponse(success=False, error="llm offline")

        from app.services import llm as llm_module

        async def _run():
            ctx = StageContext(
                task_id=task_id,
                build_id=str(uuid.uuid4()),
                db_factory=mock_session_factory,
            )
            return await run_plan_stage(ctx)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(settings, "WORKSPACE_ROOT", str(Path.cwd() / ".tmp_test_workspace"))
            mp.setattr(llm_module, "get_llm_client", lambda: BrokenLLM())
            result = asyncio.run(_run())

        assert result.success is False
        assert "PRD generation unavailable" in result.error

    def test_load_prd_summary_reads_saved_summary(self, tmp_path, monkeypatch):
        from app.core.config import settings

        task_id = str(uuid.uuid4())
        summary_path = tmp_path / "tasks" / task_id / "workspace" / "prd" / "product_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text('{"core_modules": ["模块A"], "app_type": "admin_web"}', encoding="utf-8")

        monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))

        summary = _load_prd_summary(task_id)
        assert summary["core_modules"] == ["模块A"]
        assert summary["app_type"] == "admin_web"

    def test_merge_manual_llm_content_updates_profile_modules_and_screenshots(self):
        profile = {
            "modules": [
                {
                    "title": "采购管理",
                    "description": "原描述",
                    "highlights": ["原要点"],
                    "primary_action": "原动作",
                }
            ]
        }
        screenshots = [{"page_title": "采购管理", "route": "/purchases", "caption": "旧图注"}]
        llm_content = {
            "development_background": "新的开发背景",
            "technical_feature_bullets": ["特点一", "特点二"],
            "role_permissions": {"管理员": "可查看全部模块"},
            "selected_optional_modules": [
                OPTIONAL_MANUAL_MODULES[0]["key"],
                OPTIONAL_MANUAL_MODULES[3]["key"],
                "invalid_optional_key",
            ],
            "module_overrides": [
                {
                    "title": "采购管理",
                    "description": "新的模块描述",
                    "highlights": ["新要点A", "新要点B"],
                    "primary_action": "新建采购事项",
                }
            ],
            "page_overrides": [
                {
                    "page_title": "采购管理",
                    "caption": "图1 采购管理首页",
                    "description": "新的页面描述",
                    "steps": ["步骤1", "步骤2"],
                }
            ],
        }

        merged = _merge_manual_llm_content(profile, llm_content, screenshots)

        assert merged["development_background"] == "新的开发背景"
        assert merged["technical_feature_bullets"] == ["特点一", "特点二"]
        assert merged["role_permissions"]["管理员"] == "可查看全部模块"
        assert merged["selected_optional_modules"] == [
            OPTIONAL_MANUAL_MODULES[0]["key"],
            OPTIONAL_MANUAL_MODULES[3]["key"],
        ]
        assert merged["modules"][0]["description"] == "新的模块描述"
        assert merged["modules"][0]["primary_action"] == "新建采购事项"
        assert screenshots[0]["caption"] == "图1 采购管理首页"
        assert screenshots[0]["description"] == "新的页面描述"
        assert screenshots[0]["steps"] == ["步骤1", "步骤2"]

    def test_load_screenshots_meta_falls_back_to_artifacts_manifest(self, tmp_path):
        task_id = str(uuid.uuid4())
        artifacts_root = tmp_path / "tasks" / task_id / "artifacts"
        screenshots_root = artifacts_root / "screenshots"
        screenshots_root.mkdir(parents=True, exist_ok=True)
        (screenshots_root / "login-page.png").write_bytes(b"fake-png")
        (artifacts_root / "screenshot_manifest.json").write_text(
            '[{"page_title":"登录页","caption":"图1 登录页","route":"/login","elements":["登录"],"image_file":"login-page.png"}]',
            encoding="utf-8",
        )

        screenshots = load_screenshots_meta(
            task_id,
            lambda _: str(artifacts_root),
            lambda _: str(screenshots_root),
            lambda _name: None,
        )

        assert len(screenshots) == 1
        assert screenshots[0]["page_title"] == "登录页"
        assert screenshots[0]["image_path"] == str(screenshots_root / "login-page.png")

    @pytest.mark.skip(reason="Requires full DB mock for artifact creation")
    def test_build_stage_returns_valid_result(self):
        pass

    def test_status_to_stage_mapping(self):
        assert TOPLEVEL_TO_STAGE[TopLevelStatus.PLANNING] == StageName.PLAN
        assert TOPLEVEL_TO_STAGE[TopLevelStatus.CODING] is None
        assert TOPLEVEL_TO_STAGE[TopLevelStatus.BUILDING] == StageName.BUILD
        assert TOPLEVEL_TO_STAGE[TopLevelStatus.RUNNING] == StageName.VERIFY_RUN
        assert TOPLEVEL_TO_STAGE[TopLevelStatus.CAPTURING] == StageName.CAPTURE
        assert TOPLEVEL_TO_STAGE[TopLevelStatus.WRITING_MANUAL] == StageName.COMPOSE_MANUAL
        assert TOPLEVEL_TO_STAGE[TopLevelStatus.WRITING_CODE_BOOK] == StageName.COMPOSE_CODE_BOOK
        assert TOPLEVEL_TO_STAGE[TopLevelStatus.PUBLISHING] == StageName.PUBLISH
        assert TOPLEVEL_TO_STAGE.get(TopLevelStatus.QUEUED) is None
        assert TOPLEVEL_TO_STAGE.get(TopLevelStatus.COMPLETED) is None

    def test_all_stages_registered(self):
        required = {
            StageName.PLAN, StageName.BUILD, StageName.VERIFY_RUN,
            StageName.CAPTURE, StageName.COMPOSE_MANUAL,
            StageName.COMPOSE_CODE_BOOK, StageName.PUBLISH,
        }
        registered = set(STAGE_HANDLERS.keys())
        assert required.issubset(registered), f"Missing stages: {required - registered}"

    def test_generated_backend_writer_outputs_app_files(self, tmp_path):
        backend_root = tmp_path / "backend"
        backend_root.mkdir()
        written: dict[str, str] = {}

        def write_text(path: str, content: str) -> None:
            path_obj = Path(path)
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            path_obj.write_text(content, encoding="utf-8")
            written[path_obj.name] = content

        profile = {
            "product_name": "测试系统",
            "version": "V1.0",
            "scene": "测试场景",
            "industry_scope": "测试行业",
            "user_roles": ["管理员"],
            "modules": [],
            "dashboard_metrics": [],
            "support_environment": ["Linux"],
            "development_tools": ["Python"],
            "programming_language": "Python",
        }

        write_generated_backend_files(str(backend_root), profile, write_text)

        expected_files = {"app_profile.py", "main.py", "routes.py", "models.py", "services.py"}
        assert expected_files.issubset(written.keys())
        assert "APP_PROFILE" in written["main.py"]
        assert "summarize_profile" in written["services.py"]

    def test_codegen_batches_split_core_and_module_pages(self):
        profile = {
            "product_name": "测试系统",
            "short_name": "测试端",
            "app_type": "desktop_client",
            "scene": "测试场景",
            "industry_scope": "测试行业",
            "software_category": "行业管理软件",
            "user_roles": ["管理员"],
            "focus_terms": ["终端", "工作区"],
            "core_entities": ["终端任务", "工作区"],
            "preset_key": "logistics",
            "topic_label": "智慧物流调度台",
            "experience_blueprint": {"name": "command_hub"},
            "visual_profile": {"name": "graphite_client", "accent": "#2563eb"},
            "project_dna": {"architecture_style": "dispatch_flow", "module_signature": ["运单调度中心", "线路监控台"]},
            "differentiation_hint": "围绕物流调度、运单节点和车队协同重建页面内容",
            "modules": [
                {
                    "route": "/orders",
                    "title": "订单管理",
                    "key": "orders",
                    "description": "处理订单信息",
                    "primary_action": "新增订单",
                },
                {
                    "route": "/customers",
                    "title": "客户管理",
                    "key": "customers",
                    "description": "维护客户资料",
                    "primary_action": "新增客户",
                },
            ],
        }

        requirements = build_codegen_requirements(profile)
        batches = build_codegen_batches(requirements)

        assert requirements["core_required_files"] == [
            "frontend/src/App.tsx",
            "frontend/src/pages/Login.tsx",
            "frontend/src/pages/Dashboard.tsx",
            "frontend/src/services/api.ts",
            "frontend/src/types/constants.ts",
            "frontend/src/types/models.ts",
        ]
        assert "frontend/src/pages/OrdersPage.tsx" in requirements["required_files"]
        assert "frontend/src/pages/CustomersPage.tsx" in requirements["required_files"]
        assert [page["title"] for page in requirements["module_pages"]] == ["订单管理", "客户管理"]
        assert requirements["app_type"] == "desktop_client"
        assert requirements["visual_profile"]["name"] == "graphite_client"
        assert batches[0]["name"] == "core"
        assert batches[0]["required_files"] == ["frontend/src/App.tsx"]
        assert batches[1]["name"] == "core:Login"
        assert batches[1]["required_files"] == ["frontend/src/pages/Login.tsx"]
        assert batches[2]["name"] == "core:Dashboard"
        assert batches[2]["required_files"] == ["frontend/src/pages/Dashboard.tsx"]
        assert batches[3]["name"] == "support"
        assert batches[3]["required_files"] == [
            "frontend/src/services/api.ts",
            "frontend/src/types/constants.ts",
            "frontend/src/types/models.ts",
        ]
        assert batches[4]["required_files"] == ["frontend/src/pages/OrdersPage.tsx"]
        assert batches[5]["required_files"] == ["frontend/src/pages/CustomersPage.tsx"]
        assert batches[0]["requirements"]["app_type"] == "desktop_client"
        assert batches[0]["requirements"]["experience_blueprint"]["name"] == "command_hub"
        assert batches[0]["requirements"]["visual_profile"]["name"] == "graphite_client"
        assert requirements["project_dna"]["architecture_style"] == "dispatch_flow"
        assert batches[0]["requirements"]["project_dna"]["module_signature"] == ["运单调度中心", "线路监控台"]
        assert batches[0]["requirements"]["topic_label"] == "智慧物流调度台"

    def test_plan_seed_normalization_preserves_llm_modules_and_routes(self):
        plan_seed = {
            "preset_key": "media",
            "core_modules": ["短剧内容管理", "创作者与演员管理", "广告投放管理", "排期管理", "播放数据统计"],
            "required_pages": ["/login", "/dashboard", "/series", "/actors", "/campaigns", "/schedules", "/statistics"],
            "user_roles": ["超级管理员", "内容审核员", "运营编辑"],
            "core_entities": ["剧集", "演员"],
            "raw_user_request": {"keyword": "短剧平台", "product_name": "短剧平台"},
            "scene": "内容编排与投放协同",
            "industry_scope": "内容平台",
        }
        prd_summary = {
            "app_type": "admin_web",
            "core_modules": ["剧集管理", "剧集审核", "演员管理", "排期管理", "数据统计"],
            "required_pages": ["/login", "/dashboard", "/series", "/series", "/actors", "/schedules", "/statistics"],
            "user_roles": ["超级管理员", "内容审核员", "运营编辑"],
            "scene": "短剧内容编排与审核",
            "industry_scope": "短剧内容平台",
            "core_entities": ["剧集", "评论", "演员"],
        }

        normalized = normalize_prd_summary_with_plan_seed(prd_summary, plan_seed)

        assert normalized["core_modules"] == prd_summary["core_modules"]
        assert normalized["required_pages"] == ["/login", "/dashboard", "/series", "/actors", "/schedules", "/statistics"]
        assert normalized["scene"] == "短剧内容编排与审核"
        assert normalized["industry_scope"] == "短剧内容平台"
        assert normalized["raw_user_request"] == plan_seed["raw_user_request"]
        assert normalized["source_of_truth"] == "raw_user_request"

    def test_plan_seed_normalization_only_fills_missing_fields(self):
        plan_seed = {
            "preset_key": "power_dispatch",
            "core_modules": ["电网运行总览", "负荷调度中心", "发电计划协同", "输变线路监测", "检修工作票中心"],
            "required_pages": ["/login", "/dashboard", "/grid-overview", "/load-dispatch", "/generation-plans", "/transmission-lines", "/work-tickets"],
            "user_roles": ["管理员", "调度长", "值班调度员"],
            "core_entities": ["电网线路", "变电站"],
            "raw_user_request": {"keyword": "电力调度平台", "product_name": "电力调度平台"},
            "scene": "电网运行监视、负荷调度、检修协同与故障处置",
            "industry_scope": "电网调度",
        }
        prd_summary = {
            "app_type": "",
            "core_modules": [],
            "required_pages": [],
            "user_roles": [],
        }

        normalized = normalize_prd_summary_with_plan_seed(prd_summary, plan_seed)

        assert normalized["core_modules"] == plan_seed["core_modules"]
        assert normalized["required_pages"] == plan_seed["required_pages"]
        assert normalized["user_roles"] == plan_seed["user_roles"]
        assert normalized["core_entities"] == plan_seed["core_entities"]
        assert normalized["scene"] == plan_seed["scene"]
        assert normalized["industry_scope"] == plan_seed["industry_scope"]

    def test_hydrate_missing_files_from_template_skips_llm_required_frontend_pages(self, tmp_path):
        app_root = tmp_path / "app"
        page_path = app_root / "frontend/src/pages/CategoriesPage.tsx"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text("export default function CategoriesPage() { return null; }\n", encoding="utf-8")

        hydrated = hydrate_missing_files_from_template(
            str(app_root),
            generated_files={},
            required_files=["frontend/src/pages/CategoriesPage.tsx"],
        )

        assert hydrated == {}

    def test_repair_invalid_core_files_reports_invalid_outputs_without_template_restore(self, tmp_path):
        app_root = tmp_path / "app"
        repaired, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": "const PlaceholderPage = () => <div>模块开发中</div>;",
                "frontend/src/pages/Dashboard.tsx": "export default function Dashboard(){ return <div>工作台</div>; }",
                "frontend/src/pages/Login.tsx": "export default function Login(){ return <div>登录</div>; }",
            },
            profile={
                "modules": [
                    {"route": "/series", "key": "series"},
                ]
            },
        )

        assert sorted(invalid_paths) == [
            "frontend/src/App.tsx",
            "frontend/src/pages/Dashboard.tsx",
            "frontend/src/pages/Login.tsx",
        ]
        assert repaired["frontend/src/App.tsx"] == "const PlaceholderPage = () => <div>模块开发中</div>;"
        assert repaired["frontend/src/pages/Dashboard.tsx"] == "export default function Dashboard(){ return <div>工作台</div>; }"
        assert repaired["frontend/src/pages/Login.tsx"] == "export default function Login(){ return <div>登录</div>; }"

    def test_repair_invalid_core_files_accepts_alternate_valid_llm_outputs(self, tmp_path):
        app_root = tmp_path / "app"
        repaired, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { Route, Routes } from 'react-router-dom';
import { APP_PROFILE } from './generated/appProfile';
import DispatchPage from './pages/DispatchPage';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login onLogin={() => undefined} />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/dispatch" element={<DispatchPage title={APP_PROFILE.product_name} />} />
    </Routes>
  );
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function Dashboard() {
  return <section>指挥仪表盘 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}</section>;
}
""",
                "frontend/src/pages/Login.tsx": """
export default function Login({ onLogin }: { onLogin: () => void }) {
  const handleSubmit = () => {
    localStorage.setItem('ipright_demo_auth', '1');
    onLogin();
  };
  return <button onClick={handleSubmit}>登录并输入用户名密码</button>;
}
""",
            },
            profile={
                "modules": [
                    {"route": "/dispatch", "key": "dispatch"},
                ]
            },
        )

        assert invalid_paths == []
        assert "Routes" in repaired["frontend/src/App.tsx"]
        assert "指挥仪表盘" in repaired["frontend/src/pages/Dashboard.tsx"]
        assert "ipright_demo_auth" in repaired["frontend/src/pages/Login.tsx"]

    def test_repair_invalid_core_files_rejects_unknown_page_imports(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { Route, Routes } from 'react-router-dom';
import { APP_PROFILE } from './generated/appProfile';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import AlarmsPage from './pages/AlarmsPage';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login onLogin={() => undefined} />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/dispatch" element={<AlarmsPage title={APP_PROFILE.product_name} />} />
    </Routes>
  );
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function Dashboard() {
  return <section>指挥仪表盘 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}</section>;
}
""",
                "frontend/src/pages/Login.tsx": """
export default function Login() {
  const handleSubmit = () => localStorage.setItem('ipright_demo_auth', '1');
  return <button onClick={handleSubmit}>登录并输入用户名密码</button>;
}
""",
            },
            profile={
                "modules": [
                    {"route": "/dispatch", "key": "dispatch"},
                ]
            },
        )

        assert "frontend/src/App.tsx" in invalid_paths

    def test_repair_invalid_core_files_accepts_dashboard_with_real_widgets_without_fixed_title(self, tmp_path):
        app_root = tmp_path / "app"
        repaired, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { Card, Statistic, Table } from 'antd';
import ReactECharts from 'echarts-for-react';
import { APP_PROFILE } from '../generated/appProfile';

const Dashboard: React.FC = () => {
  const { product_name, dashboard_metrics } = APP_PROFILE;
  return (
    <div>
      <h1>{product_name}</h1>
      <Card><Statistic title={dashboard_metrics[0]?.title} value={dashboard_metrics[0]?.value} /></Card>
      <ReactECharts option={{}} />
      <Table dataSource={[]} columns={[]} />
    </div>
  );
};

export default Dashboard;
""",
                "frontend/src/pages/Login.tsx": """
export default function Login() {
  const handleSubmit = () => localStorage.setItem('ipright_demo_auth', '1');
  return <button onClick={handleSubmit}>登录并输入用户名密码</button>;
}
""",
            },
            profile={"modules": []},
        )

        assert invalid_paths == []
        assert "ReactECharts" in repaired["frontend/src/pages/Dashboard.tsx"]

    def test_repair_invalid_core_files_rejects_inline_module_shell_app(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { Routes, Route } from 'react-router-dom';
import { APP_PROFILE } from './generated/appProfile';
const ModuleShell = ({ title }) => <div>{title}</div>;
const RecordsPage = () => <ModuleShell title="授信主体管理" />;
export default function App() {
  return <Routes><Route path="/credit-subjects" element={<RecordsPage />} /></Routes>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function Dashboard() {
  return <section>系统首页 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}</section>;
}
""",
                "frontend/src/pages/Login.tsx": """
export default function Login({ onLogin }) {
  return <button onClick={onLogin}>登录 用户名 密码</button>;
}
""",
            },
            profile={
                "modules": [
                    {"route": "/credit-subjects", "key": "credit-subjects"},
                ]
            },
        )

        assert "frontend/src/App.tsx" in invalid_paths

    def test_repair_invalid_module_pages_reports_invalid_outputs_without_template_rewrite(self):
        generated_files = {
            "frontend/src/pages/WorkflowPage.tsx": """
import React from 'react';
const mockData = [{ id: 'AN-001', owner: '张风控' }];
export default function WorkflowPage() {
  return <div>风险指标体系与模型管理</div>;
}
""",
        }
        profile = {
            "modules": [
                {
                    "title": "风险指标体系与模型管理",
                    "key": "workflow",
                    "route": "/workflow",
                    "primary_action": "新增预警规则",
                    "filter_placeholder": "搜索分析主题 / 负责人 / 风险维度",
                    "table_headers": ["分析编号", "分析主题", "统计维度", "负责人"],
                    "rows": [
                        ["AN-202605-017", "新能源债券组合压力测试", "市场风险", "风险分析师"],
                    ],
                    "highlights": ["支持指标版本管理", "支持风险结论留痕"],
                    "description": "用于管理风险模型与分析结论。",
                    "page_variant": "insight",
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/WorkflowPage.tsx"]
        workflow_text = repaired["frontend/src/pages/WorkflowPage.tsx"]
        assert "mockData" in workflow_text
        assert "新能源债券组合压力测试" not in workflow_text

    def test_repair_invalid_module_pages_normalizes_wrong_app_profile_import(self):
        generated_files = {
            "frontend/src/pages/WorkflowPage.tsx": """
import { APP_PROFILE } from '../../generated/appProfile';

export default function WorkflowPage() {
  return <div>风险指标体系与模型管理 {APP_PROFILE.product_name} 分析编号 负责人</div>;
}
""",
        }
        profile = {
            "modules": [
                {
                    "title": "风险指标体系与模型管理",
                    "key": "workflow",
                    "route": "/workflow",
                    "table_headers": ["分析编号", "分析主题", "统计维度", "负责人"],
                    "rows": [
                        ["AN-202605-017", "新能源债券组合压力测试", "市场风险", "风险分析师"],
                    ],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == []
        workflow_text = repaired["frontend/src/pages/WorkflowPage.tsx"]
        assert "../generated/appProfile" in workflow_text
        assert "../../generated/appProfile" not in workflow_text

    def test_prepare_seed_application_removes_seed_frontend_shell_files(self, tmp_path):
        app_root = tmp_path / "app"
        profile = {
            "product_name": "测试系统",
            "modules": [{"route": "/orders", "key": "orders"}],
        }

        prepare_seed_application(str(app_root), profile)

        assert not (app_root / "frontend/src/App.tsx").exists()
        assert not (app_root / "frontend/src/pages").exists()
        assert not (app_root / "frontend/src/services/api.ts").exists()
        assert not (app_root / "frontend/src/types/constants.ts").exists()
        assert not (app_root / "frontend/src/types/models.ts").exists()
        assert (app_root / "frontend/src/generated/appProfile.ts").exists()
        assert (app_root / "frontend/src/font.css").exists()
        assert (app_root / "frontend/src/App.css").exists()
        assert "import './font.css';" in (app_root / "frontend/src/main.tsx").read_text(encoding="utf-8")
        assert (app_root / "frontend/public/fonts/IPRightCJK.ttf").exists()

    def test_demo_seed_frontend_sources_do_not_use_python_docstrings(self):
        seed_files = [
            PROJECT_ROOT / "examples/demo_app/frontend/src/hooks/useAppState.ts",
            PROJECT_ROOT / "examples/demo_app/frontend/src/types/constants.ts",
        ]

        for path in seed_files:
            text = path.read_text(encoding="utf-8")
            assert not text.lstrip().startswith('"""'), str(path)

    def test_generate_task_app_code_self_heals_core_and_support_when_llm_fails(self, tmp_path, monkeypatch):
        import workers.stages.build_support as build_support

        app_root = tmp_path / "app"
        prd_root = tmp_path / "prd"
        prd_root.mkdir(parents=True, exist_ok=True)
        (prd_root / "product_prd.md").write_text("# PRD\n", encoding="utf-8")
        (prd_root / "development_work_order.md").write_text("# Work Order\n", encoding="utf-8")

        profile = {
            "product_name": "测试系统",
            "scene": "测试场景",
            "industry_scope": "测试行业",
            "user_roles": ["管理员"],
            "modules": [],
            "focus_terms": [],
            "core_entities": [],
            "experience_blueprint": {},
            "dashboard_metrics": [],
            "version": "V1.0",
        }
        prepare_seed_application(str(app_root), profile)

        class _Resp:
            success = False
            structured = None
            error = "unknown error"

        class _LLM:
            async def generate_app_code(self, *_args, **_kwargs):
                return _Resp()

        monkeypatch.setattr(build_support, "get_llm_client", lambda: _LLM(), raising=False)
        monkeypatch.setattr("app.services.llm.get_llm_client", lambda: _LLM())

        async def _run():
            return await generate_task_app_code(str(app_root), str(prd_root), profile)

        report, error = asyncio.run(_run())
        assert report is not None
        assert error is None
        assert report["repaired_core_paths"] == [
            "frontend/src/App.tsx",
            "frontend/src/pages/Dashboard.tsx",
            "frontend/src/pages/Login.tsx",
        ]
        assert report["repaired_support_paths"] == [
            "frontend/src/services/api.ts",
            "frontend/src/types/constants.ts",
            "frontend/src/types/models.ts",
        ]
        assert report["template_ui_fallback_used"] is True
        assert (app_root / "frontend/src/App.tsx").exists()
        assert (app_root / "frontend/src/pages/Login.tsx").exists()
        assert (app_root / "frontend/src/pages/Dashboard.tsx").exists()
        assert (app_root / "frontend/src/services/api.ts").exists()

    def test_generate_task_app_code_retries_missing_core_files(self, tmp_path, monkeypatch):
        import workers.stages.build_support as build_support

        app_root = tmp_path / "app"
        prd_root = tmp_path / "prd"
        prd_root.mkdir(parents=True, exist_ok=True)
        (prd_root / "product_prd.md").write_text("# PRD\n", encoding="utf-8")
        (prd_root / "development_work_order.md").write_text("# Work Order\n", encoding="utf-8")

        profile = {
            "product_name": "测试系统",
            "scene": "测试场景",
            "industry_scope": "测试行业",
            "user_roles": ["管理员"],
            "modules": [],
            "focus_terms": [],
            "core_entities": [],
            "experience_blueprint": {},
            "dashboard_metrics": [],
            "version": "V1.0",
        }
        prepare_seed_application(str(app_root), profile)

        class _Resp:
            def __init__(self, files):
                self.success = True
                self.structured = {"files": files}
                self.error = None

        class _LLM:
            def __init__(self):
                self.calls = []

            async def generate_app_code(self, _prd, _wo, requirements):
                required = tuple(requirements["required_files"])
                self.calls.append(
                    {
                        "required_files": required,
                        "invalid_module_previews": dict(requirements.get("invalid_module_previews", {})),
                    }
                )
                if required == ("frontend/src/App.tsx",):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "export default function App(){ return <div>APP_PROFILE.product_name</div>; }",
                        }
                    )
                if required == ("frontend/src/pages/Login.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { return <button onClick={onLogin}>登录</button>; }",
                        }
                    )
                if required == ("frontend/src/pages/Dashboard.tsx",):
                    return _Resp({})
                if required == (
                    "frontend/src/services/api.ts",
                    "frontend/src/types/constants.ts",
                    "frontend/src/types/models.ts",
                ):
                    return _Resp(
                        {
                            "frontend/src/services/api.ts": "export async function request(){ return {}; } export const api = { login: async () => ({ success: true }) };",
                            "frontend/src/types/constants.ts": "export const APP_NAME = '测试系统'; export const APP_VERSION = 'V1.0';",
                            "frontend/src/types/models.ts": "export interface LoginResponse { success: boolean; token?: string; role?: string; }",
                        }
                    )
                if required == ("frontend/src/pages/Login.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }: { onLogin: () => void }) { return <button onClick={onLogin}>登录 用户名 密码</button>; }",
                        }
                    )
                if required == ("frontend/src/pages/Dashboard.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <div>系统首页 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}</div>; }",
                        }
                    )
                return _Resp({})

        llm = _LLM()
        monkeypatch.setattr(build_support, "get_llm_client", lambda: llm, raising=False)
        monkeypatch.setattr("app.services.llm.get_llm_client", lambda: llm)

        async def _run():
            return await generate_task_app_code(str(app_root), str(prd_root), profile)

        report, error = asyncio.run(_run())
        assert error is None
        assert report is not None
        required_calls = [call["required_files"] for call in llm.calls]
        assert ("frontend/src/App.tsx",) in required_calls
        assert ("frontend/src/pages/Login.tsx",) in required_calls
        assert ("frontend/src/pages/Dashboard.tsx",) in required_calls
        assert (
            "frontend/src/services/api.ts",
            "frontend/src/types/constants.ts",
            "frontend/src/types/models.ts",
        ) in required_calls
        assert required_calls.count(("frontend/src/pages/Login.tsx",)) >= 2
        assert required_calls.count(("frontend/src/pages/Dashboard.tsx",)) >= 2
        assert report["generated_file_count"] == 6

    def test_generate_task_app_code_retries_invalid_core_files(self, tmp_path, monkeypatch):
        import workers.stages.build_support as build_support

        app_root = tmp_path / "app"
        prd_root = tmp_path / "prd"
        prd_root.mkdir(parents=True, exist_ok=True)
        (prd_root / "product_prd.md").write_text("# PRD\n", encoding="utf-8")
        (prd_root / "development_work_order.md").write_text("# Work Order\n", encoding="utf-8")

        profile = {
            "product_name": "测试系统",
            "scene": "测试场景",
            "industry_scope": "测试行业",
            "user_roles": ["管理员"],
            "modules": [],
            "focus_terms": [],
            "core_entities": [],
            "experience_blueprint": {},
            "dashboard_metrics": [],
            "version": "V1.0",
        }
        prepare_seed_application(str(app_root), profile)

        class _Resp:
            def __init__(self, files):
                self.success = True
                self.structured = {"files": files}
                self.error = None

        class _LLM:
            def __init__(self):
                self.calls = []

            async def generate_app_code(self, _prd, _wo, requirements):
                self.calls.append(
                    {
                        "required_files": tuple(requirements["required_files"]),
                        "validation_hints": list(requirements.get("validation_hints", [])),
                    }
                )
                required = tuple(requirements["required_files"])
                if required == ("frontend/src/App.tsx",):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "export default function App(){ return <div>调度工作台</div>; }",
                        }
                    )
                if required == ("frontend/src/pages/Login.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { return <button onClick={onLogin}>登录 用户名 密码</button>; }",
                        }
                    )
                if required == ("frontend/src/pages/Dashboard.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Dashboard.tsx": "export default function Dashboard(){ return <div>系统首页 调度工作台</div>; }",
                        }
                    )
                if required == (
                    "frontend/src/services/api.ts",
                    "frontend/src/types/constants.ts",
                    "frontend/src/types/models.ts",
                ):
                    return _Resp(
                        {
                            "frontend/src/services/api.ts": "export async function request(){ return {}; } export const api = { login: async () => ({ success: true }) };",
                            "frontend/src/types/constants.ts": "export const APP_NAME = '测试系统'; export const APP_VERSION = 'V1.0';",
                            "frontend/src/types/models.ts": "export interface LoginResponse { success: boolean; token?: string; role?: string; }",
                        }
                    )
                if required == ("frontend/src/App.tsx",):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "import { Routes, Route } from 'react-router-dom'; import { APP_PROFILE } from './generated/appProfile'; export default function App(){ return <Routes><Route path='/dispatch' element={<div>{APP_PROFILE.product_name}</div>} /></Routes>; }",
                        }
                    )
                if required == ("frontend/src/pages/Login.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }: { onLogin: () => void }) { return <button onClick={onLogin}>登录 用户名 密码</button>; }",
                        }
                    )
                if required == ("frontend/src/pages/Dashboard.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <section>系统首页 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}</section>; }",
                        }
                    )
                return _Resp({})

        llm = _LLM()
        monkeypatch.setattr(build_support, "get_llm_client", lambda: llm, raising=False)
        monkeypatch.setattr("app.services.llm.get_llm_client", lambda: llm)

        async def _run():
            return await generate_task_app_code(str(app_root), str(prd_root), profile)

        report, error = asyncio.run(_run())
        assert error is None
        assert report is not None
        assert [call["required_files"] for call in llm.calls[:4]] == [
            ("frontend/src/App.tsx",),
            ("frontend/src/pages/Login.tsx",),
            ("frontend/src/pages/Dashboard.tsx",),
            (
                "frontend/src/services/api.ts",
                "frontend/src/types/constants.ts",
                "frontend/src/types/models.ts",
            ),
        ]
        retry_calls = [call for call in llm.calls[4:] if call["validation_hints"]]
        assert retry_calls
        assert all(len(call["required_files"]) == 1 for call in retry_calls)
        assert ("frontend/src/App.tsx",) in [call["required_files"] for call in retry_calls]
        assert ("frontend/src/pages/Dashboard.tsx",) in [call["required_files"] for call in retry_calls]
        retry_batches = [batch for batch in report["batches"] if batch["batch"] == "core_invalid_retry"]
        assert retry_batches
        assert all(len(batch["required_files"]) == 1 for batch in retry_batches)
        assert ["frontend/src/App.tsx"] in [batch["required_files"] for batch in retry_batches]
        assert ["frontend/src/pages/Dashboard.tsx"] in [batch["required_files"] for batch in retry_batches]
        assert (app_root / "frontend/src/App.tsx").exists()
        assert (app_root / "frontend/src/pages/Login.tsx").exists()
        assert (app_root / "frontend/src/pages/Dashboard.tsx").exists()

    def test_generate_task_app_code_structurally_repairs_persistently_invalid_app(self, tmp_path, monkeypatch):
        import workers.stages.build_support as build_support

        app_root = tmp_path / "app"
        prd_root = tmp_path / "prd"
        prd_root.mkdir(parents=True, exist_ok=True)
        (prd_root / "product_prd.md").write_text("# PRD\n", encoding="utf-8")
        (prd_root / "development_work_order.md").write_text("# Work Order\n", encoding="utf-8")

        profile = {
            "product_name": "供应链金融平台",
            "scene": "核心企业信用监控",
            "industry_scope": "供应链金融",
            "user_roles": ["管理员", "风控经理"],
            "modules": [
                {
                    "title": "授信主体",
                    "key": "credit-subjects",
                    "route": "/credit-subjects",
                    "description": "查看核心企业授信主体档案",
                }
            ],
            "focus_terms": [],
            "core_entities": [],
            "experience_blueprint": {},
            "dashboard_metrics": [],
            "version": "V3.0",
        }
        prepare_seed_application(str(app_root), profile)

        class _Resp:
            def __init__(self, files):
                self.success = True
                self.structured = {"files": files}
                self.error = None

        class _LLM:
            async def generate_app_code(self, _prd, _wo, requirements):
                required = tuple(requirements["required_files"])
                if required == (
                    "frontend/src/App.tsx",
                    "frontend/src/pages/Login.tsx",
                    "frontend/src/pages/Dashboard.tsx",
                ):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "import React from 'react'; export default function App(){ return <div>坏壳层</div>; }",
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { return <button onClick={onLogin}>登录 用户名 密码</button>; }",
                            "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <div>系统首页 {APP_PROFILE.product_name} Statistic Card</div>; }",
                        }
                    )
                if required == (
                    "frontend/src/services/api.ts",
                    "frontend/src/types/constants.ts",
                    "frontend/src/types/models.ts",
                ):
                    return _Resp(
                        {
                            "frontend/src/services/api.ts": "export async function request(){ return { success: true }; } export const api = { login: async () => ({ success: true, data: { token: 'demo-token', user: { name: 'admin', role: '管理员' } } }) };",
                            "frontend/src/types/constants.ts": "export const APP_NAME = '供应链金融平台'; export const APP_VERSION = 'V3.0';",
                            "frontend/src/types/models.ts": "export interface LoginResponse { token: string; user: { name: string; role: string; }; }",
                        }
                    )
                if required == ("frontend/src/pages/CreditSubjectsPage.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/CreditSubjectsPage.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function CreditSubjectsPage(){ return <section><h1>授信主体</h1><div>{APP_PROFILE.product_name}</div></section>; }",
                        }
                    )
                if required == ("frontend/src/pages/Login.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }: { onLogin: () => void }) { return <button onClick={onLogin}>登录 用户名 密码</button>; }",
                        }
                    )
                if required == ("frontend/src/pages/Dashboard.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <div>系统首页 {APP_PROFILE.product_name} Card</div>; }",
                        }
                    )
                if required == ("frontend/src/App.tsx",):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "export default function App(){ return <div>继续无效</div>; }",
                        }
                    )
                return _Resp({})

        llm = _LLM()
        monkeypatch.setattr(build_support, "get_llm_client", lambda: llm, raising=False)
        monkeypatch.setattr("app.services.llm.get_llm_client", lambda: llm)

        async def _run():
            return await generate_task_app_code(str(app_root), str(prd_root), profile)

        report, error = asyncio.run(_run())
        assert error is None
        assert report["repaired_core_paths"] == ["frontend/src/App.tsx"]
        fallback_batch = next(batch for batch in report["batches"] if batch["batch"] == "core_structural_fallback")
        assert fallback_batch["generated_paths"] == ["frontend/src/App.tsx"]
        app_text = (app_root / "frontend/src/App.tsx").read_text(encoding="utf-8")
        assert "APP_PROFILE" in app_text
        assert "/credit-subjects" in app_text
        assert "CreditSubjectsPage" in app_text

    def test_generate_task_app_code_retries_invalid_module_pages(self, tmp_path, monkeypatch):
        import workers.stages.build_support as build_support

        app_root = tmp_path / "app"
        prd_root = tmp_path / "prd"
        prd_root.mkdir(parents=True, exist_ok=True)
        (prd_root / "product_prd.md").write_text("# PRD\n", encoding="utf-8")
        (prd_root / "development_work_order.md").write_text("# Work Order\n", encoding="utf-8")

        profile = {
            "product_name": "风险监测平台",
            "scene": "围绕债券组合风控监测和预警处置进行分析",
            "industry_scope": "金融风控",
            "user_roles": ["管理员", "风险分析师"],
            "modules": [
                {
                    "title": "风险指标体系与模型管理",
                    "key": "workflow",
                    "route": "/workflow",
                    "primary_action": "新增预警规则",
                    "filter_placeholder": "搜索分析主题 / 负责人 / 风险维度",
                    "table_headers": ["分析编号", "分析主题", "统计维度", "负责人"],
                    "rows": [
                        ["AN-202605-017", "新能源债券组合压力测试", "市场风险", "风险分析师"],
                    ],
                    "highlights": ["支持指标版本管理", "支持风险结论留痕"],
                    "description": "用于管理风险模型与分析结论。",
                    "page_variant": "insight",
                }
            ],
            "focus_terms": [],
            "core_entities": [],
            "experience_blueprint": {},
            "dashboard_metrics": [],
            "version": "V1.0",
        }
        prepare_seed_application(str(app_root), profile)

        class _Resp:
            def __init__(self, files):
                self.success = True
                self.structured = {"files": files}
                self.error = None

        class _LLM:
            def __init__(self):
                self.calls = []

            async def generate_app_code(self, _prd, _wo, requirements):
                self.calls.append(
                    {
                        "required_files": tuple(requirements["required_files"]),
                        "validation_hints": list(requirements.get("validation_hints", [])),
                        "invalid_module_previews": dict(requirements.get("invalid_module_previews", {})),
                    }
                )
                required = tuple(requirements["required_files"])
                if required == (
                    "frontend/src/App.tsx",
                    "frontend/src/pages/Login.tsx",
                    "frontend/src/pages/Dashboard.tsx",
                ):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "import { Routes, Route } from 'react-router-dom'; import Login from './pages/Login'; import Dashboard from './pages/Dashboard'; import WorkflowPage from './pages/WorkflowPage'; import { APP_PROFILE } from './generated/appProfile'; export default function App(){ return <Routes><Route path='/login' element={<Login onLogin={() => undefined} />} /><Route path='/dashboard' element={<Dashboard />} /><Route path='/workflow' element={<WorkflowPage title={APP_PROFILE.product_name} />} /></Routes>; }",
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { return <button onClick={onLogin}>登录 用户名 密码</button>; }",
                            "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <div>系统首页 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}</div>; }",
                        }
                    )
                if required == (
                    "frontend/src/services/api.ts",
                    "frontend/src/types/constants.ts",
                    "frontend/src/types/models.ts",
                ):
                    return _Resp(
                        {
                            "frontend/src/services/api.ts": "export async function request(){ return { success: true }; } export const api = { login: async () => ({ success: true }) };",
                            "frontend/src/types/constants.ts": "export const APP_NAME = '风险监测平台'; export const APP_VERSION = 'V1.0';",
                            "frontend/src/types/models.ts": "export interface LoginResponse { success: boolean; token?: string; }",
                        }
                    )
                if required == ("frontend/src/pages/WorkflowPage.tsx",):
                    if not requirements.get("invalid_module_previews"):
                        return _Resp(
                            {
                                "frontend/src/pages/WorkflowPage.tsx": "const mockData = [{ id: '1' }]; export default function WorkflowPage(){ return <div>风险指标体系与模型管理</div>; }",
                            }
                        )
                    return _Resp(
                        {
                            "frontend/src/pages/WorkflowPage.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function WorkflowPage(){ return <section><header>风险指标体系与模型管理 {APP_PROFILE.product_name}</header><button>新增预警规则</button><div>搜索分析主题 / 负责人 / 风险维度</div><table><thead><tr><th>分析编号</th><th>分析主题</th><th>统计维度</th><th>负责人</th></tr></thead><tbody><tr><td>AN-202605-017</td><td>新能源债券组合压力测试</td><td>市场风险</td><td>风险分析师</td></tr></tbody></table></section>; }",
                        }
                    )
                return _Resp({})

        llm = _LLM()
        monkeypatch.setattr(build_support, "get_llm_client", lambda: llm, raising=False)
        monkeypatch.setattr("app.services.llm.get_llm_client", lambda: llm)

        async def _run():
            return await generate_task_app_code(str(app_root), str(prd_root), profile)

        report, error = asyncio.run(_run())
        assert error is None
        assert report is not None
        retry_call = next(call for call in llm.calls if call["invalid_module_previews"])
        assert retry_call["required_files"] == ("frontend/src/pages/WorkflowPage.tsx",)
        assert retry_call["validation_hints"]
        assert "frontend/src/pages/WorkflowPage.tsx" in retry_call["invalid_module_previews"]
        retry_batch = next(batch for batch in report["batches"] if batch["batch"] == "module_invalid_retry")
        assert retry_batch["generated_paths"] == ["frontend/src/pages/WorkflowPage.tsx"]
        page_text = (app_root / "frontend/src/pages/WorkflowPage.tsx").read_text(encoding="utf-8")
        assert "新能源债券组合压力测试" in page_text
        assert "mockData" not in page_text

    def test_generate_task_app_code_falls_back_to_structural_module_pages_when_retries_stay_invalid(self, tmp_path, monkeypatch):
        import workers.stages.build_support as build_support

        app_root = tmp_path / "app"
        prd_root = tmp_path / "prd"
        prd_root.mkdir(parents=True, exist_ok=True)
        (prd_root / "product_prd.md").write_text("# PRD\n", encoding="utf-8")
        (prd_root / "development_work_order.md").write_text("# Work Order\n", encoding="utf-8")

        profile = {
            "product_name": "冷链履约协同平台",
            "scene": "围绕冷链履约监控和异常处置进行协同",
            "industry_scope": "物流供应链",
            "user_roles": ["调度主管", "库存专员"],
            "modules": [
                {
                    "title": "履约分析与报表",
                    "key": "statistics",
                    "route": "/statistics",
                    "primary_action": "导出统计报表",
                    "filter_placeholder": "搜索履约单号 / 客户 / 节点",
                    "table_headers": ["履约单号", "客户", "节点", "状态"],
                    "rows": [
                        ["FUL-001", "华东生鲜", "在途监控", "正常"],
                    ],
                    "highlights": ["展示冷链履约波动趋势", "支持异常节点复盘"],
                    "description": "用于查看履约统计和异常分析。",
                    "page_variant": "insight",
                }
            ],
            "focus_terms": [],
            "core_entities": [],
            "experience_blueprint": {},
            "dashboard_metrics": [],
            "version": "V1.0",
        }
        prepare_seed_application(str(app_root), profile)

        class _Resp:
            def __init__(self, files):
                self.success = True
                self.structured = {"files": files}
                self.error = None

        class _LLM:
            async def generate_app_code(self, _prd, _wo, requirements):
                required = tuple(requirements["required_files"])
                if required == (
                    "frontend/src/App.tsx",
                    "frontend/src/pages/Login.tsx",
                    "frontend/src/pages/Dashboard.tsx",
                ):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "import { Routes, Route } from 'react-router-dom'; import Login from './pages/Login'; import Dashboard from './pages/Dashboard'; import StatisticsPage from './pages/StatisticsPage'; export default function App(){ return <Routes><Route path='/login' element={<Login onLogin={() => undefined} />} /><Route path='/dashboard' element={<Dashboard />} /><Route path='/statistics' element={<StatisticsPage />} /></Routes>; }",
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { return <button onClick={onLogin}>登录 用户名 密码</button>; }",
                            "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <div>系统首页 {APP_PROFILE.product_name} 调度总览</div>; }",
                        }
                    )
                if required == (
                    "frontend/src/services/api.ts",
                    "frontend/src/types/constants.ts",
                    "frontend/src/types/models.ts",
                ):
                    return _Resp(
                        {
                            "frontend/src/services/api.ts": "export async function request(){ return { success: true }; } export const api = { login: async () => ({ success: true }) };",
                            "frontend/src/types/constants.ts": "export const APP_NAME = '冷链履约协同平台'; export const APP_VERSION = 'V1.0';",
                            "frontend/src/types/models.ts": "export interface LoginResponse { success: boolean; token?: string; }",
                        }
                    )
                if required == ("frontend/src/pages/StatisticsPage.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/StatisticsPage.tsx": "const mockData = [{ id: '1' }]; export default function StatisticsPage(){ return <div>冷链监控看板</div>; }",
                        }
                    )
                return _Resp({})

        llm = _LLM()
        monkeypatch.setattr(build_support, "get_llm_client", lambda: llm, raising=False)
        monkeypatch.setattr("app.services.llm.get_llm_client", lambda: llm)

        async def _run():
            return await generate_task_app_code(str(app_root), str(prd_root), profile)

        report, error = asyncio.run(_run())
        assert error is None
        assert report["repaired_module_paths"] == ["frontend/src/pages/StatisticsPage.tsx"]
        fallback_batch = next(batch for batch in report["batches"] if batch["batch"] == "module_structural_fallback")
        assert fallback_batch["generated_paths"] == ["frontend/src/pages/StatisticsPage.tsx"]
        page_text = (app_root / "frontend/src/pages/StatisticsPage.tsx").read_text(encoding="utf-8")
        assert "APP_PROFILE" in page_text
        assert "导出统计报表" in page_text
        assert "FUL-001" in page_text
        assert "mockData" not in page_text

    def test_generate_task_app_code_shards_invalid_module_page_retries(self, tmp_path, monkeypatch):
        import workers.stages.build_support as build_support

        app_root = tmp_path / "app"
        prd_root = tmp_path / "prd"
        prd_root.mkdir(parents=True, exist_ok=True)
        (prd_root / "product_prd.md").write_text("# PRD\n", encoding="utf-8")
        (prd_root / "development_work_order.md").write_text("# Work Order\n", encoding="utf-8")

        profile = {
            "product_name": "冷链履约协同平台",
            "scene": "围绕跨境冷链采购、库存和预警联动进行协同",
            "industry_scope": "物流供应链",
            "user_roles": ["采购专员", "库存主管"],
            "modules": [
                {
                    "title": "采购协同",
                    "key": "purchases",
                    "route": "/purchases",
                    "primary_action": "发起采购协同",
                    "filter_placeholder": "搜索采购单 / 供应商 / 港口",
                    "table_headers": ["采购单号", "供应商", "港口", "状态"],
                    "rows": [["PO-001", "海丰冷链", "洋山港", "待提货"]],
                    "highlights": ["记录跨境提货状态"],
                    "description": "管理采购与提货协同。",
                    "page_variant": "records",
                },
                {
                    "title": "库存监控",
                    "key": "inventory",
                    "route": "/inventory",
                    "primary_action": "登记温区批次",
                    "filter_placeholder": "搜索批次 / 仓库 / 箱号",
                    "table_headers": ["批次号", "仓库", "温区", "可用量"],
                    "rows": [["LOT-009", "前海保税仓", "-18C", "128箱"]],
                    "highlights": ["展示温区占用趋势"],
                    "description": "监控库存温区与批次。",
                    "page_variant": "insight",
                },
                {
                    "title": "异常预警",
                    "key": "alerts",
                    "route": "/alerts",
                    "primary_action": "登记异常处置",
                    "filter_placeholder": "搜索预警编号 / 异常类型",
                    "table_headers": ["预警编号", "异常类型", "责任人", "状态"],
                    "rows": [["AL-301", "温控波动", "李调度", "处理中"]],
                    "highlights": ["串联异常处置时序"],
                    "description": "跟踪履约异常与处置。",
                    "page_variant": "timeline",
                },
            ],
            "focus_terms": [],
            "core_entities": [],
            "experience_blueprint": {},
            "dashboard_metrics": [],
            "version": "V1.0",
        }
        prepare_seed_application(str(app_root), profile)

        class _Resp:
            def __init__(self, files):
                self.success = True
                self.structured = {"files": files}
                self.error = None

        class _LLM:
            def __init__(self):
                self.calls = []

            async def generate_app_code(self, _prd, _wo, requirements):
                required = tuple(requirements["required_files"])
                self.calls.append(
                    {
                        "required_files": required,
                        "invalid_module_previews": dict(requirements.get("invalid_module_previews", {})),
                    }
                )
                if required == (
                    "frontend/src/App.tsx",
                    "frontend/src/pages/Login.tsx",
                    "frontend/src/pages/Dashboard.tsx",
                ):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "import { Routes, Route } from 'react-router-dom'; import Login from './pages/Login'; import Dashboard from './pages/Dashboard'; import PurchasesPage from './pages/PurchasesPage'; import InventoryPage from './pages/InventoryPage'; import AlertsPage from './pages/AlertsPage'; export default function App(){ return <Routes><Route path='/login' element={<Login onLogin={() => undefined} />} /><Route path='/dashboard' element={<Dashboard />} /><Route path='/purchases' element={<PurchasesPage />} /><Route path='/inventory' element={<InventoryPage />} /><Route path='/alerts' element={<AlertsPage />} /></Routes>; }",
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { return <button onClick={onLogin}>登录 用户名 密码</button>; }",
                            "frontend/src/pages/Dashboard.tsx": "export default function Dashboard(){ return <div>系统首页</div>; }",
                        }
                    )
                if required == (
                    "frontend/src/services/api.ts",
                    "frontend/src/types/constants.ts",
                    "frontend/src/types/models.ts",
                ):
                    return _Resp(
                        {
                            "frontend/src/services/api.ts": "export async function request(){ return { success: true }; } export const api = { login: async () => ({ success: true }) };",
                            "frontend/src/types/constants.ts": "export const APP_NAME = '冷链履约协同平台'; export const APP_VERSION = 'V1.0';",
                            "frontend/src/types/models.ts": "export interface LoginResponse { success: boolean; token?: string; }",
                        }
                    )
                if not requirements.get("invalid_module_previews"):
                    files = {
                        path: f"const mockData = [{{ id: '{idx}' }}]; export default function Page(){{ return <div>{path}</div>; }}"
                        for idx, path in enumerate(required, start=1)
                    }
                    return _Resp(files)

                files = {}
                for path in required:
                    if path.endswith("PurchasesPage.tsx"):
                        files[path] = "import { APP_PROFILE } from '../generated/appProfile'; export default function PurchasesPage(){ return <section><h1>采购协同</h1><div>{APP_PROFILE.product_name}</div><button>发起采购协同</button><table><tbody><tr><td>PO-001</td><td>海丰冷链</td><td>洋山港</td><td>待提货</td></tr></tbody></table></section>; }"
                    elif path.endswith("InventoryPage.tsx"):
                        files[path] = "import { APP_PROFILE } from '../generated/appProfile'; export default function InventoryPage(){ return <section><h1>库存监控</h1><div>{APP_PROFILE.product_name}</div><button>登记温区批次</button><table><tbody><tr><td>LOT-009</td><td>前海保税仓</td><td>-18C</td><td>128箱</td></tr></tbody></table></section>; }"
                    elif path.endswith("AlertsPage.tsx"):
                        files[path] = "import { APP_PROFILE } from '../generated/appProfile'; export default function AlertsPage(){ return <section><h1>异常预警</h1><div>{APP_PROFILE.product_name}</div><button>登记异常处置</button><table><tbody><tr><td>AL-301</td><td>温控波动</td><td>李调度</td><td>处理中</td></tr></tbody></table></section>; }"
                return _Resp(files)

        llm = _LLM()
        monkeypatch.setattr(build_support, "get_llm_client", lambda: llm, raising=False)
        monkeypatch.setattr("app.services.llm.get_llm_client", lambda: llm)

        async def _run():
            return await generate_task_app_code(str(app_root), str(prd_root), profile)

        report, error = asyncio.run(_run())
        assert error is None
        retry_calls = [
            call["required_files"]
            for call in llm.calls
            if call["invalid_module_previews"]
        ]
        assert retry_calls == [
            ("frontend/src/pages/PurchasesPage.tsx", "frontend/src/pages/InventoryPage.tsx"),
            ("frontend/src/pages/AlertsPage.tsx",),
        ]
        retry_batches = [batch for batch in report["batches"] if batch["batch"] == "module_invalid_retry"]
        assert [batch["required_files"] for batch in retry_batches] == [
            ["frontend/src/pages/PurchasesPage.tsx", "frontend/src/pages/InventoryPage.tsx"],
            ["frontend/src/pages/AlertsPage.tsx"],
        ]
        assert "mockData" not in (app_root / "frontend/src/pages/PurchasesPage.tsx").read_text(encoding="utf-8")
        assert "mockData" not in (app_root / "frontend/src/pages/InventoryPage.tsx").read_text(encoding="utf-8")
        assert "mockData" not in (app_root / "frontend/src/pages/AlertsPage.tsx").read_text(encoding="utf-8")

    def test_runtime_captures_early_exit_logs(self, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
        runtime = SandboxRuntime(str(workspace))

        async def _run():
            return await runtime.start_services({
                "start_commands": [
                    "/usr/bin/env python3 -c \"import sys; sys.stderr.write('boom\\\\n'); raise SystemExit(3)\""
                ]
            })

        services = asyncio.run(_run())
        assert services[0]["status"] == "exited"
        assert services[0]["returncode"] == 3
        assert services[0]["log_path"].endswith("service_1.log")
        assert "boom" in services[0]["log_tail"]

    def test_ensure_frontend_dependencies_adds_ui_runtime_packages(self, tmp_path):
        frontend_root = tmp_path / "frontend"
        frontend_root.mkdir(parents=True, exist_ok=True)
        package_json = frontend_root / "package.json"
        package_json.write_text(
            '{"dependencies":{"react":"^18.3.0"}}',
            encoding="utf-8",
        )

        _ensure_frontend_dependencies(str(frontend_root))

        updated = package_json.read_text(encoding="utf-8")
        assert '"axios": "^1.6.0"' in updated
        assert '"@fontsource/noto-sans-sc": "latest"' in updated
        assert '"antd": "^5.15.0"' in updated
        assert '"@ant-design/icons": "^5.3.0"' in updated
        assert '"dayjs": "^1.11.0"' in updated

    def test_sync_frontend_dependencies_only_keeps_used_optional_packages(self, tmp_path):
        frontend_root = tmp_path / "frontend"
        src_root = frontend_root / "src"
        src_root.mkdir(parents=True, exist_ok=True)
        package_json = frontend_root / "package.json"
        package_json.write_text(
            json.dumps(
                {
                    "dependencies": {
                        "react": "^18.3.0",
                        "@ant-design/pro-components": "^2.8.6",
                        "echarts": "^5.5.0",
                        "echarts-for-react": "^3.0.2",
                    }
                }
            ),
            encoding="utf-8",
        )
        (src_root / "Dashboard.tsx").write_text(
            "import ReactECharts from 'echarts-for-react';\nexport default function Dashboard(){ return <div />; }\n",
            encoding="utf-8",
        )

        sync_frontend_dependencies(str(frontend_root))

        updated = package_json.read_text(encoding="utf-8")
        assert '"echarts": "^5.5.0"' in updated
        assert '"echarts-for-react": "^3.0.2"' in updated
        assert '"@ant-design/pro-components"' not in updated

    def test_ensure_backend_dependencies_adds_pyjwt(self, tmp_path):
        backend_root = tmp_path / "backend"
        backend_root.mkdir(parents=True, exist_ok=True)
        requirements = backend_root / "requirements.txt"
        requirements.write_text("fastapi>=0.100\nuvicorn[standard]>=0.20\n", encoding="utf-8")

        _ensure_backend_dependencies(str(backend_root))

        updated = requirements.read_text(encoding="utf-8")
        assert "PyJWT>=2.8" in updated

    def test_normalize_generated_frontend_files_rewrites_llm_font_stacks(self):
        generated = {
            "frontend/src/pages/PurchasesPage.tsx": """
const styles = {
  container: {
    fontFamily: 'Microsoft YaHei', 'PingFang SC', 'Helvetica Neue', Arial, sans-serif',
  },
};
const css = `
  .panel {
    font-family: "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
  }
  code {
    font-family: monospace;
  }
`;
""",
            "backend/app/main.py": "print('ok')\n",
        }

        normalized = normalize_generated_frontend_files(generated)

        page_code = normalized["frontend/src/pages/PurchasesPage.tsx"]
        assert "'IPRight CJK'" in page_code
        assert '"IPRight CJK"' in page_code
        assert "font-family: monospace;" in page_code
        assert normalized["backend/app/main.py"] == "print('ok')\n"

    def test_runtime_backend_health_requires_2xx(self, monkeypatch, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
        runtime = SandboxRuntime(str(workspace))

        class _Resp:
            def __init__(self, status_code: int):
                self.status_code = status_code

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url: str):
                return _Resp(404)

        monkeypatch.setattr("app.services.runtime.httpx.AsyncClient", _Client)

        async def _run():
            return await runtime.run_health_checks(
                {
                    "health_checks": ["http://127.0.0.1:23180/health"],
                    "ports": {"backend": 23180},
                },
                timeout=3,
                services=[],
            )

        report = asyncio.run(_run())
        assert not report.success
        assert not report.backend_ok
        assert report.errors == ["Health check failed for http://127.0.0.1:23180/health"]

    def test_runtime_frontend_ok_only_when_check_passes(self, monkeypatch, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
        runtime = SandboxRuntime(str(workspace))

        class _Resp:
            def __init__(self, status_code: int):
                self.status_code = status_code

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url: str):
                return _Resp(404)

        monkeypatch.setattr("app.services.runtime.httpx.AsyncClient", _Client)

        async def _run():
            return await runtime.run_health_checks(
                {
                    "health_checks": ["http://127.0.0.1:23100/"],
                    "ports": {"frontend": 23100},
                },
                timeout=3,
                services=[],
            )

        report = asyncio.run(_run())
        assert not report.success
        assert not report.frontend_ok
        assert report.errors == ["Health check failed for http://127.0.0.1:23100/"]

    def test_runtime_start_services_releases_declared_ports_first(self, monkeypatch, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
        runtime = SandboxRuntime(str(workspace))
        released_ports: list[int] = []

        monkeypatch.setattr(
            "app.services.runtime._release_port",
            lambda port, grace=0.8: released_ports.append(port) or [],
        )

        class _Proc:
            def __init__(self):
                self.pid = 4321
                self.returncode = None

            def poll(self):
                return None

            def terminate(self):
                self.returncode = 0

        monkeypatch.setattr("app.services.runtime.subprocess.Popen", lambda *args, **kwargs: _Proc())

        async def _run():
            return await runtime.start_services(
                {
                    "ports": {"frontend": 23100, "backend": 23101},
                    "start_commands": ["echo frontend", "echo backend"],
                }
            )

        services = asyncio.run(_run())
        assert released_ports == [23100, 23101]
        assert len(services) == 2
        assert services[0]["status"] == "started"

    def test_runtime_login_page_requires_2xx_or_3xx(self, monkeypatch, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
        runtime = SandboxRuntime(str(workspace))

        class _Resp:
            def __init__(self, status_code: int):
                self.status_code = status_code

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url: str):
                return _Resp(404)

        monkeypatch.setattr("app.services.runtime.httpx.AsyncClient", _Client)

        assert asyncio.run(runtime.check_login_page("http://127.0.0.1:23100")) is False

    def test_runtime_frontend_marker_check_requires_current_task_identity(self, monkeypatch, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
        runtime = SandboxRuntime(str(workspace))

        class _Resp:
            def __init__(self, status_code: int, text: str):
                self.status_code = status_code
                self.text = text

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url: str):
                return _Resp(200, "<html><body>供应链管理软件 V1.0 登录入口</body></html>")

        monkeypatch.setattr("app.services.runtime.httpx.AsyncClient", _Client)

        ok, error = asyncio.run(
            runtime.check_frontend_markers("http://127.0.0.1:23100", ["供应链管理软件", "V1.0"])
        )
        assert ok is True
        assert error == ""

        ok, error = asyncio.run(
            runtime.check_frontend_markers("http://127.0.0.1:23100", ["投资风险平台"])
        )
        assert ok is False
        assert "Frontend marker mismatch" in error

    def test_runtime_frontend_marker_check_falls_back_to_workspace_sources(self, monkeypatch, tmp_path):
        workspace = tmp_path / "workspace"
        (workspace / "artifacts").mkdir(parents=True, exist_ok=True)
        profile_file = workspace / "app" / "frontend" / "src" / "generated" / "appProfile.ts"
        profile_file.parent.mkdir(parents=True, exist_ok=True)
        profile_file.write_text("export const APP_PROFILE = { product_name: '供应链核心企业金融数据分析与监控平台 V2.0', version: 'V2.0' }", encoding="utf-8")
        runtime = SandboxRuntime(str(workspace))

        class _Resp:
            def __init__(self, status_code: int, text: str):
                self.status_code = status_code
                self.text = text

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url: str):
                return _Resp(200, "<html><body><div id='root'></div></body></html>")

        monkeypatch.setattr("app.services.runtime.httpx.AsyncClient", _Client)

        ok, error = asyncio.run(
            runtime.check_frontend_markers(
                "http://127.0.0.1:23100",
                ["供应链核心企业金融数据分析与监控平台 V2.0", "V2.0"],
            )
        )
        assert ok is True
        assert error == ""

    def test_derive_run_ports_are_stable_and_task_build_specific(self):
        first = _derive_run_ports("task-a", "build-1")
        second = _derive_run_ports("task-a", "build-1")
        third = _derive_run_ports("task-a", "build-2")

        assert first == second
        assert first != third
        assert first["backend"] == first["frontend"] + 1
        assert 24000 <= first["frontend"] <= 43998

    def test_capture_login_page_expected_markers_include_login_form_traits(self):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")
        markers = capture._expected_markers("登录页", "/login")
        assert "登录" in markers
        assert "用户名" in markers
        assert "密码" in markers
        assert "平台入口概览" in markers

    def test_capture_dashboard_expected_markers_allow_variant_titles(self):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")
        markers = capture._expected_markers("系统首页", "/dashboard")
        assert "系统首页" in markers
        assert "调度总览" in markers
        assert "工作台" in markers

    def test_capture_statistics_expected_markers_allow_route_level_aliases(self):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")
        markers = capture._expected_markers("冷链监控看板", "/statistics")
        assert "冷链监控看板" in markers
        assert "统计" in markers
        assert "分析" in markers
        assert "报表" in markers

    def test_capture_meaningful_content_accepts_statistics_page_with_variant_title(self):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")
        ok = capture._is_meaningful_content_info(
            {
                "readyState": "complete",
                "textLength": 128,
                "blocks": 5,
                "headings": ["履约分析与报表"],
                "inputs": 1,
                "buttons": 2,
                "mainTextLength": 92,
                "mainBlocks": 4,
                "mainHeadings": ["履约分析与报表"],
                "mainInputs": 1,
                "mainButtons": 2,
                "height": 980,
                "hasExpectedTitle": False,
                "hasExpectedMarker": True,
                "hasMainExpectedTitle": False,
                "hasMainExpectedMarker": True,
                "hasLoginSignals": False,
            },
            route="/statistics",
            expected_markers=["冷链监控看板", "统计", "分析", "报表"],
        )
        assert ok is True

    def test_capture_meaningful_content_accepts_login_form_without_exact_title(self):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")
        ok = capture._is_meaningful_content_info(
            {
                "readyState": "complete",
                "textLength": 22,
                "blocks": 1,
                "headings": ["物流调度管理后台"],
                "inputs": 2,
                "buttons": 1,
                "mainTextLength": 22,
                "mainBlocks": 1,
                "mainHeadings": ["物流调度管理后台"],
                "mainInputs": 2,
                "mainButtons": 1,
                "height": 640,
                "hasExpectedTitle": False,
                "hasExpectedMarker": True,
                "hasMainExpectedTitle": False,
                "hasMainExpectedMarker": True,
                "hasLoginSignals": True,
            },
            route="/login",
            expected_markers=["登录", "用户名", "密码"],
        )
        assert ok is True

    def test_capture_meaningful_content_accepts_rich_dashboard_without_fixed_heading(self):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")
        ok = capture._is_meaningful_content_info(
            {
                "readyState": "complete",
                "textLength": 96,
                "blocks": 3,
                "headings": ["物流调度管理后台 - 调度总览"],
                "inputs": 0,
                "buttons": 2,
                "mainTextLength": 96,
                "mainBlocks": 3,
                "mainHeadings": ["物流调度管理后台 - 调度总览"],
                "mainInputs": 0,
                "mainButtons": 2,
                "height": 960,
                "hasExpectedTitle": False,
                "hasExpectedMarker": True,
                "hasMainExpectedTitle": False,
                "hasMainExpectedMarker": True,
                "hasLoginSignals": False,
            },
            route="/dashboard",
            expected_markers=["系统首页"],
        )
        assert ok is True

    def test_capture_meaningful_content_rejects_login_like_page_for_protected_route(self):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")
        ok = capture._is_meaningful_content_info(
            {
                "readyState": "complete",
                "textLength": 220,
                "blocks": 6,
                "headings": ["物流调度管理后台", "运单调度中心"],
                "inputs": 2,
                "buttons": 4,
                "mainTextLength": 42,
                "mainBlocks": 2,
                "mainHeadings": ["物流调度管理后台"],
                "mainInputs": 2,
                "mainButtons": 1,
                "height": 980,
                "hasExpectedTitle": True,
                "hasExpectedMarker": True,
                "hasMainExpectedTitle": False,
                "hasMainExpectedMarker": False,
                "hasLoginSignals": True,
            },
            route="/dispatch",
            expected_markers=["运单调度中心"],
        )
        assert ok is False

    def test_capture_summarize_content_info_includes_probe_fields(self):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")
        summary = capture._summarize_content_info(
            {
                "readyState": "complete",
                "textLength": 28,
                "blocks": 2,
                "inputs": 2,
                "buttons": 1,
                "height": 640,
                "hasExpectedMarker": True,
                "hasExpectedTitle": False,
                "headings": ["物流调度管理后台", "调度总览"],
            }
        )
        assert "content_probe=ready=complete" in summary
        assert "text=28" in summary
        assert "headings=物流调度管理后台 | 调度总览" in summary

    def test_capture_cleanup_failed_capture_removes_partial_png(self, tmp_path):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir=str(tmp_path))
        image_path = tmp_path / "login-page.png"
        image_path.write_bytes(b"partial")
        capture._cleanup_failed_capture(str(image_path))
        assert image_path.exists() is False

    def test_capture_usable_login_screenshot_accepts_small_but_meaningful_image(self, tmp_path, monkeypatch):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir=str(tmp_path))
        image_path = tmp_path / "login-page.png"
        image_path.write_bytes(b"x" * 1200)

        async def _meaningful(*_args, **_kwargs):
            return True

        monkeypatch.setattr(capture, "_has_meaningful_content", _meaningful)

        ok = asyncio.run(
            capture._is_usable_capture(
                object(),
                str(image_path),
                route="/login",
                title="登录页",
                expected_markers=["登录", "用户名", "密码"],
            )
        )
        assert ok is True

    def test_capture_css_forces_cjk_font_stack_on_all_elements(self):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")
        payload: dict[str, str] = {}

        class _Page:
            async def emulate_media(self, media: str = "screen"):
                payload["media"] = media

            async def add_style_tag(self, *, content: str):
                payload["content"] = content

        asyncio.run(capture._ensure_capture_css(_Page()))
        assert payload["media"] == "screen"
        assert '"IPRight CJK", "Noto Sans SC", "Noto Sans CJK SC"' in payload["content"]
        assert "font-family: \"IPRight CJK\", \"Noto Sans SC\", \"Noto Sans CJK SC\"" in payload["content"]
        assert "!important" in payload["content"]

    def test_capture_input_selectors_cover_search_fallbacks(self):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")
        selectors = capture._input_selectors("搜索")
        assert 'input[name="搜索"]' in selectors
        assert 'input[placeholder*="搜索"]' in selectors
        assert 'input[type="search"]' in selectors
        assert '[role="searchbox"]' in selectors
        assert 'input[placeholder*="关键字"]' in selectors

    def test_capture_fill_input_field_falls_back_to_visible_text_input(self):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")

        class _Page:
            def __init__(self):
                self.fill_calls: list[str] = []
                self.evaluate_payload = None

            async def fill(self, selector: str, value: str, timeout: int = 0):
                self.fill_calls.append(selector)
                raise RuntimeError("no explicit selector matched")

            async def evaluate(self, script: str, payload: dict):
                self.evaluate_payload = payload
                return True

        page = _Page()
        ok = asyncio.run(capture._fill_input_field(page, "搜索", "供应链金融"))
        assert ok is True
        assert 'input[name="搜索"]' in page.fill_calls
        assert page.evaluate_payload == {"target": "搜索", "value": "供应链金融"}

    def test_capture_trigger_search_submit_clicks_query_buttons(self):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")

        class _Page:
            def __init__(self):
                self.clicked: list[str] = []

            async def click(self, selector: str, timeout: int = 0):
                self.clicked.append(selector)
                if selector != 'button:has-text("查询")':
                    raise RuntimeError("not found")

        page = _Page()
        asyncio.run(capture._trigger_search_submit(page, "搜索"))
        assert page.clicked[0] == 'button:has-text("查询")'

    def test_capture_execute_action_skips_optional_fill_input_warning(self, monkeypatch, caplog):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir="/tmp")

        class _Page:
            async def wait_for_timeout(self, ms: int):
                return None

        async def _never_fill(*args, **kwargs):
            return False

        async def _stabilize(*args, **kwargs):
            return None

        monkeypatch.setattr(capture, "_fill_input_field", _never_fill)
        monkeypatch.setattr(capture, "_stabilize_page", _stabilize)

        with caplog.at_level("WARNING"):
            asyncio.run(
                capture._execute_action(
                    _Page(),
                    {"action": "fill_input", "target": "搜索", "value": "量化平台", "optional": True},
                )
            )

        assert "Unable to locate input field for target: 搜索" not in caplog.text

    def test_render_font_css_prefers_horizontal_cjk_layout(self):
        css = _render_font_css()
        assert "@fontsource/noto-sans-sc/chinese-simplified.css" in css
        assert "min-width: 1360px" in css
        assert "writing-mode: horizontal-tb" in css
        assert "'Noto Sans SC'" in css
        assert "input, button, textarea, select" in css

    def test_render_frontend_app_defaults_to_top_tabs_shell(self):
        profile = {
            "product_name": "AI股票量化投资平台",
            "version": "V1.0",
            "short_name": "量化平台",
            "scene": "量化策略研究与交易管理",
            "nav_items": [
                {"path": "/dashboard", "label": "首页", "icon": "📊"},
                {"path": "/users", "label": "用户管理", "icon": "👥"},
            ],
            "modules": [
                {
                    "key": "users",
                    "title": "用户管理",
                    "route": "/users",
                    "description": "维护用户账号",
                    "primary_action": "新增角色账号",
                }
            ],
        }
        app_code = _render_frontend_app(profile)
        assert "chromeTreatment = String((visualProfile.chrome_treatment as string) || (isDesktopClient ? 'desktop_workbench' : 'top_tabs'))" in app_code
        assert "顶部导航工作台" in app_code
        assert "当前视图" in app_code
        assert "focusTerms" in app_code

    def test_render_login_page_has_nonempty_right_panel(self):
        page_code = _render_login_page()
        assert "平台入口概览" in page_code
        assert "previewModules" in page_code
        assert "loginVariant === 'workspace' ? '1.12fr 380px' : '420px 1fr'" in page_code
        assert "fontFamily: uiFont" in page_code

    def test_render_frontend_app_always_shows_login_when_not_authenticated(self):
        profile = {
            "product_name": "供应链管理软件",
            "version": "V1.0",
            "short_name": "供应链",
            "scene": "供应链协同管理",
            "nav_items": [{"path": "/dashboard", "label": "首页", "icon": "📊"}],
            "modules": [],
        }
        app_code = _render_frontend_app(profile)
        assert "if (!loggedIn) {" in app_code
        assert "location.pathname !== '/login'" not in app_code

    def test_render_frontend_app_adds_desktop_workbench_shell_for_client_products(self):
        profile = {
            "product_name": "园区设备巡检客户端",
            "version": "V1.0",
            "short_name": "巡检终端",
            "app_type": "desktop_client",
            "scene": "设备巡检与工作站协同",
            "visual_profile": {"nav_background": "#111827", "nav_text": "#fff", "shell_background": "#eef2f7"},
            "nav_items": [{"path": "/dashboard", "label": "首页", "icon": "📊"}],
            "modules": [],
        }
        app_code = _render_frontend_app(profile)
        assert "桌面客户端工作台" in app_code
        assert "当前模块" in app_code
        assert "刷新视图" in app_code
        assert "打开工作区" in app_code

    def test_render_module_page_uses_module_specific_copy_and_removes_tips(self):
        module = {
            "key": "users",
            "title": "用户管理",
            "route": "/users",
            "description": "用于维护账号、角色与授权范围。",
            "primary_action": "新增角色账号",
            "filter_placeholder": "搜索用户名 / 角色 / 状态",
            "table_headers": ["账号编号", "姓名", "角色", "负责范围", "状态", "最近更新"],
            "rows": [
                ["USR-101", "陈思远", "管理员", "用户管理", "启用", "2026-05-02"],
                ["USR-102", "周可欣", "审核员", "策略管理", "处理中", "2026-05-01"],
            ],
            "highlights": ["支持统一建档", "支持角色过滤", "支持授权留痕"],
        }
        page_code = _render_module_page(module)
        assert "用户管理" in page_code
        assert "用于维护账号、角色与授权范围。" in page_code
        assert "新增角色账号" in page_code
        assert "支持统一建档" in page_code
        assert "使用提示" not in page_code
        assert "页面摘要" not in page_code
        assert "业务处理说明" in page_code
        assert "moduleRowsSafe" in page_code
        assert "主数据范围" in page_code
        assert "数据样例" in page_code
        assert "routeBadge" in page_code
        assert "borderTop" not in page_code
        assert "fontFamily: uiFont" in page_code
        assert 'name="搜索"' in page_code
        assert "aria-label={modulePlaceholder}" in page_code
        assert 'type="search"' in page_code

    def test_render_module_page_is_typescript_safe(self):
        module = {
            "key": "alerts",
            "title": "预警中心",
            "route": "/alerts",
            "description": "用于汇总风险告警、处置状态与最新留痕。",
            "primary_action": "新增预警规则",
            "filter_placeholder": "搜索告警编号 / 责任人 / 状态",
            "table_headers": ["告警编号", "主题", "责任人", "状态"],
            "rows": [["ALT-101", "库存预警", "周可欣", "处理中"]],
            "highlights": ["支持状态追踪"],
            "page_variant": "workspace",
        }
        page_code = _render_module_page(module)
        assert "const pageVariant: string" in page_code
        assert "style={panelStyle}" in page_code
        assert "style={{panelStyle}}" not in page_code

    def test_repair_invalid_core_files_rejects_unsupported_profile_fields(self, tmp_path):
        profile = {
            "app_type": "web_admin",
            "experience_blueprint": {},
            "visual_profile": {},
            "modules": [
                {
                    "key": "records",
                    "title": "档案管理",
                    "route": "/records",
                }
            ],
        }
        generated_files = {
            "frontend/src/App.tsx": """
import { Routes, Route } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import RecordsPage from './pages/RecordsPage';
import { APP_PROFILE } from './generated/appProfile';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login onLogin={() => undefined} />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/records" element={<RecordsPage title={APP_PROFILE.navigation?.title || APP_PROFILE.name} />} />
    </Routes>
  );
}
""",
            "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';

export default function Dashboard() {
  return (
    <section>
      系统首页 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}
      {String(APP_PROFILE.dashboard_metrics.totalProjects)}
    </section>
  );
}
""",
            "frontend/src/pages/Login.tsx": """
export default function Login({ onLogin }: { onLogin: () => void }) {
  return <button onClick={onLogin}>登录 用户名 密码</button>;
}
""",
        }

        _, invalid_paths = repair_invalid_core_files(str(tmp_path), generated_files, profile)

        assert "frontend/src/App.tsx" in invalid_paths
        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_requires_typed_login_handler(self, tmp_path):
        profile = {
            "app_type": "web_admin",
            "experience_blueprint": {},
            "visual_profile": {},
            "modules": [],
        }
        generated_files = {
            "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() { return <div>{APP_PROFILE.product_name}</div>; }
""",
            "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function Dashboard() { return <div>系统首页 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}</div>; }
""",
            "frontend/src/pages/Login.tsx": """
export default function Login({ onLogin }) {
  localStorage.setItem('ipright_demo_auth', 'true');
  return <button onClick={onLogin}>登录 用户名 密码</button>;
}
""",
        }

        _, invalid_paths = repair_invalid_core_files(str(tmp_path), generated_files, profile)

        assert "frontend/src/pages/Login.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_app_login_callback_signature_mismatch(self, tmp_path):
        profile = {
            "app_type": "web_admin",
            "experience_blueprint": {},
            "visual_profile": {},
            "modules": [],
        }
        generated_files = {
            "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';

export default function App() {
  const handleLogin = (token: string) => token;
  return <Login onLogin={handleLogin} />;
}
""",
            "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function Dashboard() { return <div>系统首页 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}</div>; }
""",
            "frontend/src/pages/Login.tsx": """
export default function Login({ onLogin }: { onLogin: () => void }) {
  localStorage.setItem('ipright_demo_auth', 'true');
  return <button onClick={onLogin}>登录 用户名 密码</button>;
}
""",
        }

        _, invalid_paths = repair_invalid_core_files(str(tmp_path), generated_files, profile)

        assert "frontend/src/App.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_duplicate_page_imports_and_routes(self, tmp_path):
        profile = {
            "app_type": "web_admin",
            "experience_blueprint": {},
            "visual_profile": {},
            "modules": [
                {
                    "key": "statistics",
                    "route": "/statistics",
                    "title": "统计分析",
                }
            ],
        }
        generated_files = {
            "frontend/src/App.tsx": """
import { Routes, Route } from 'react-router-dom';
import { APP_PROFILE } from './generated/appProfile';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import StatisticsPage from './pages/StatisticsPage';
import SuppliersPage from './pages/SuppliersPage';
import StatisticsPage from './pages/StatisticsPage';

const handleLogin = () => {};

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login onLogin={handleLogin} />} />
      <Route path="/" element={<Dashboard />} />
      <Route path="/statistics" element={<StatisticsPage />} />
      <Route path="/statistics" element={<StatisticsPage />} />
      <Route path="/suppliers" element={<SuppliersPage />} />
      <Route path="/about" element={<div>{APP_PROFILE.product_name}</div>} />
    </Routes>
  );
}
""",
            "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function Dashboard() { return <div>系统首页 {APP_PROFILE.product_name} Card</div>; }
""",
            "frontend/src/pages/Login.tsx": """
export default function Login({ onLogin }: { onLogin: () => void }) {
  localStorage.setItem('ipright_demo_auth', 'true');
  return <button onClick={onLogin}>登录 用户名 密码</button>;
}
""",
        }

        _, invalid_paths = repair_invalid_core_files(str(tmp_path), generated_files, profile)

        assert "frontend/src/App.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_login_without_callback_signature_when_app_requires_onlogin(self, tmp_path):
        profile = {
            "app_type": "web_admin",
            "experience_blueprint": {},
            "visual_profile": {},
            "modules": [],
        }
        generated_files = {
            "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
const handleLogin = () => {};
export default function App() { return <div><Login onLogin={handleLogin} /><Dashboard />{APP_PROFILE.product_name}</div>; }
""",
            "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function Dashboard() { return <div>系统首页 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}</div>; }
""",
            "frontend/src/pages/Login.tsx": """
export default function Login() {
  const handleSubmit = () => localStorage.setItem('ipright_demo_auth', 'true');
  return <button onClick={handleSubmit}>登录 用户名 密码</button>;
}
""",
        }

        _, invalid_paths = repair_invalid_core_files(str(tmp_path), generated_files, profile)

        assert "frontend/src/pages/Login.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_metric_hallucinations(self, tmp_path):
        profile = {
            "app_type": "web_admin",
            "experience_blueprint": {},
            "visual_profile": {},
            "modules": [],
        }
        generated_files = {
            "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
export default function App() { return <div>{APP_PROFILE.product_name}<Login onLogin={handleLogin} /><Dashboard /></div>; }
const handleLogin = () => {};
""",
            "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function Dashboard() {
  return <div>系统首页 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.totalCases} <ScheduleOutlined /></div>;
}
""",
            "frontend/src/pages/Login.tsx": """
export default function Login({ onLogin }: { onLogin: () => void }) {
  localStorage.setItem('ipright_demo_auth', 'true');
  return <button onClick={onLogin}>登录 用户名 密码</button>;
}
""",
        }

        _, invalid_paths = repair_invalid_core_files(str(tmp_path), generated_files, profile)

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_metric_icon_access(self, tmp_path):
        profile = {
            "app_type": "web_admin",
            "experience_blueprint": {},
            "visual_profile": {},
            "modules": [],
        }
        generated_files = {
            "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
const handleLogin = () => {};
export default function App() { return <div><Login onLogin={handleLogin} /><Dashboard /></div>; }
""",
            "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function Dashboard() {
  return <div>系统首页 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.map((metric) => <span>{metric.icon}</span>)}</div>;
}
""",
            "frontend/src/pages/Login.tsx": """
export default function Login({ onLogin }: { onLogin: () => void }) {
  localStorage.setItem('ipright_demo_auth', 'true');
  return <button onClick={onLogin}>登录 用户名 密码</button>;
}
""",
        }

        _, invalid_paths = repair_invalid_core_files(str(tmp_path), generated_files, profile)

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_metrics_state_shape_mismatch(self, tmp_path):
        profile = {
            "app_type": "web_admin",
            "experience_blueprint": {},
            "visual_profile": {},
            "modules": [],
        }
        generated_files = {
            "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
const handleLogin = () => {};
export default function App() { return <div><Login onLogin={handleLogin} /><Dashboard /></div>; }
""",
            "frontend/src/pages/Dashboard.tsx": """
import React, { useEffect, useState } from 'react';
import { APP_PROFILE } from '../generated/appProfile';
export default function Dashboard() {
  const [metrics, setMetrics] = useState({
    anomalyTotal: 128,
    pendingTasks: 35,
    closureRate: 87.5,
    avgProcessHours: 4.2,
  });
  useEffect(() => {
    if (APP_PROFILE?.dashboard_metrics) {
      setMetrics(APP_PROFILE.dashboard_metrics);
    }
  }, []);
  return <div>系统首页 {APP_PROFILE.product_name}</div>;
}
""",
            "frontend/src/pages/Login.tsx": """
export default function Login({ onLogin }: { onLogin: () => void }) {
  localStorage.setItem('ipright_demo_auth', 'true');
  return <button onClick={onLogin}>登录 用户名 密码</button>;
}
""",
        }

        _, invalid_paths = repair_invalid_core_files(str(tmp_path), generated_files, profile)

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_echarts_subpath_imports_and_metric_object_access(self, tmp_path):
        profile = {
            "app_type": "web_admin",
            "experience_blueprint": {},
            "visual_profile": {},
            "modules": [],
        }
        generated_files = {
            "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
const handleLogin = () => {};
export default function App() { return <div><Login onLogin={handleLogin} /><Dashboard /></div>; }
""",
            "frontend/src/pages/Dashboard.tsx": """
import React from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { APP_PROFILE } from '../generated/appProfile';
echarts.use([LineChart, GridComponent, CanvasRenderer]);
export default function Dashboard() {
  const metrics = APP_PROFILE?.dashboard_metrics ?? {
    todayAlerts: 12,
    processing: 5,
    overdueWarnings: 3,
    closed: 8,
  };
  return <div>系统首页 {APP_PROFILE.product_name} {metrics.todayAlerts} <ReactEChartsCore option={{}} /></div>;
}
""",
            "frontend/src/pages/Login.tsx": """
export default function Login({ onLogin }: { onLogin: () => void }) {
  localStorage.setItem('ipright_demo_auth', 'true');
  return <button onClick={onLogin}>登录 用户名 密码</button>;
}
""",
        }

        _, invalid_paths = repair_invalid_core_files(str(tmp_path), generated_files, profile)

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_metric_object_access_variants(self, tmp_path):
        profile = {
            "app_type": "web_admin",
            "experience_blueprint": {},
            "visual_profile": {},
            "modules": [],
        }
        generated_files = {
            "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
const handleLogin = () => {};
export default function App() { return <div><Login onLogin={handleLogin} /><Dashboard /></div>; }
""",
            "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
import { Card, Statistic } from 'antd';
export default function Dashboard() {
  const metrics = APP_PROFILE.dashboard_metrics || {
    openIncidents: 42,
    inProgress: 18,
    resolvedToday: 7,
    escalation: 3,
  };
  return (
    <Card title={`系统首页 ${APP_PROFILE.product_name}`}>
      <Statistic title="待处理异常" value={metrics.openIncidents} />
      <Statistic title="处理中" value={metrics.inProgress} />
      <Statistic title="今日已关闭" value={metrics.resolvedToday} />
      <Statistic title="升级处理" value={metrics.escalation} />
    </Card>
  );
}
""",
            "frontend/src/pages/Login.tsx": """
export default function Login({ onLogin }: { onLogin: () => void }) {
  localStorage.setItem('ipright_demo_auth', 'true');
  return <button onClick={onLogin}>登录 用户名 密码</button>;
}
""",
        }

        _, invalid_paths = repair_invalid_core_files(str(tmp_path), generated_files, profile)

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_render_login_page_types_login_variant_as_string(self):
        page = _render_login_page({"experience_blueprint": {"login_variant": "workspace"}})

        assert "const loginVariant: string =" in page

    def test_repair_invalid_support_files_falls_back_from_import_meta_env(self):
        profile = {"product_name": "测试平台", "version": "V1.0"}
        generated_files = {
            "frontend/src/services/api.ts": """
const baseUrl = import.meta.env.VITE_API_URL;
export const api = { login: async () => ({ token: 'x' }) };
""",
            "frontend/src/types/constants.ts": "export const APP_NAME = '测试平台';",
            "frontend/src/types/models.ts": "export interface DemoUser { name: string; role: string; }",
        }

        _, invalid_paths = repair_invalid_support_files(
            generated_files,
            profile,
            [
                "frontend/src/services/api.ts",
                "frontend/src/types/constants.ts",
                "frontend/src/types/models.ts",
            ],
        )

        assert "frontend/src/services/api.ts" in invalid_paths
        assert "frontend/src/types/constants.ts" in invalid_paths
        assert "frontend/src/types/models.ts" in invalid_paths

    def test_synthesize_support_runtime_files_overwrites_invalid_existing_files(self):
        profile = {"product_name": "测试平台", "version": "V1.0"}
        generated_files = {
            "frontend/src/services/api.ts": "const baseUrl = import.meta.env.VITE_API_URL;",
            "frontend/src/types/constants.ts": "export const APP_NAME = '坏文件';",
            "frontend/src/types/models.ts": "export interface UserData { id: number; }",
        }

        synthesized, repaired_paths = _synthesize_support_runtime_files(
            generated_files,
            profile,
            list(generated_files.keys()),
            overwrite_existing=True,
        )

        assert sorted(repaired_paths) == sorted(generated_files.keys())
        assert "import.meta.env" not in synthesized["frontend/src/services/api.ts"]
        assert "DEMO_USERNAME" in synthesized["frontend/src/types/constants.ts"]
        assert "COLORS" in synthesized["frontend/src/types/constants.ts"]
        assert "export interface DemoUser" in synthesized["frontend/src/types/models.ts"]

    def test_repair_invalid_module_pages_rejects_profile_aliases_and_unsafe_visual_profile(self):
        profile = {
            "modules": [
                {
                    "key": "records",
                    "title": "档案管理",
                    "route": "/records",
                    "table_headers": ["编号", "名称", "状态"],
                    "rows": [["REC-1", "北辰项目", "处理中"]],
                    "highlights": ["支持统一建档"],
                }
            ]
        }
        generated_files = {
            "frontend/src/pages/RecordsPage.tsx": """
import { APP_PROFILE } from '../generated/appProfile';

export default function RecordsPage() {
  return (
    <div style={{ color: APP_PROFILE.visual_profile.panel_background }}>
      {APP_PROFILE.productName}
      {APP_PROFILE.visualConfig?.accent}
      <Statistic title="数量" value={1} />
      档案管理 编号 北辰项目
    </div>
  );
}
""",
        }

        _, invalid_paths = repair_invalid_module_pages(generated_files, profile)

        assert "frontend/src/pages/RecordsPage.tsx" in invalid_paths

    def test_repair_invalid_module_pages_allows_statistics_page_name_without_antd_statistic(self):
        profile = {
            "modules": [
                {
                    "key": "statistics",
                    "title": "统计分析",
                    "route": "/statistics",
                    "table_headers": ["指标", "数值", "趋势"],
                    "rows": [["转化率", "18%", "上升"]],
                    "highlights": ["支持按维度查看趋势"],
                }
            ]
        }
        generated_files = {
            "frontend/src/pages/StatisticsPage.tsx": _render_module_page(profile["modules"][0]),
        }

        _, invalid_paths = repair_invalid_module_pages(generated_files, profile)

        assert "frontend/src/pages/StatisticsPage.tsx" not in invalid_paths

    def test_repair_invalid_module_pages_rejects_app_profile_title_access(self):
        profile = {
            "modules": [
                {
                    "key": "statistics",
                    "title": "统计分析",
                    "route": "/statistics",
                    "table_headers": ["指标", "数值", "趋势"],
                    "rows": [["转化率", "18%", "上升"]],
                    "highlights": ["支持按维度查看趋势"],
                }
            ]
        }
        generated_files = {
            "frontend/src/pages/StatisticsPage.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function StatisticsPage() {
  return <div>统计分析 指标 转化率 {APP_PROFILE.title}</div>;
}
""",
        }

        _, invalid_paths = repair_invalid_module_pages(generated_files, profile)

        assert "frontend/src/pages/StatisticsPage.tsx" in invalid_paths

    def test_repair_invalid_module_pages_rejects_theme_alias_and_shared_model_imports(self):
        profile = {
            "modules": [
                {
                    "key": "orders",
                    "title": "订单管理",
                    "route": "/orders",
                    "table_headers": ["订单号", "客户", "状态"],
                    "rows": [["ORD-1", "华东客户", "处理中"]],
                    "highlights": ["支持履约跟踪"],
                }
            ]
        }
        generated_files = {
            "frontend/src/pages/OrdersPage.tsx": """
import type { Supplier } from '../types/models';
import { APP_PROFILE } from '../generated/appProfile';

export default function OrdersPage() {
  return (
    <div style={{ background: APP_PROFILE.theme.background }}>
      <h1>订单管理</h1>
      <div>订单号 客户 状态</div>
      <div>ORD-1 华东客户 处理中</div>
    </div>
  );
}
""",
        }

        _, invalid_paths = repair_invalid_module_pages(generated_files, profile)

        assert "frontend/src/pages/OrdersPage.tsx" in invalid_paths

    def test_repair_invalid_module_pages_rejects_app_profile_description_access(self):

        profile = {
            "modules": [
                {
                    "key": "inventory",
                    "title": "履约节点监控",
                    "title": "履约节点监控",
                    "route": "/inventory",
                    "table_headers": ["履约单号", "阶段", "责任人"],
                    "rows": [["INV-01", "在途", "陈楠"]],
                    "highlights": ["支持节点追踪"],
                }
            ]
        }
        generated_files = {
            "frontend/src/pages/InventoryPage.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function InventoryPage() {
  return <div>履约节点监控 履约单号 INV-01 {APP_PROFILE.description}</div>;
}
""",
        }

        _, invalid_paths = repair_invalid_module_pages(generated_files, profile)

        assert "frontend/src/pages/InventoryPage.tsx" in invalid_paths

    def test_repair_invalid_module_pages_rejects_editable_table_columns(self):
        profile = {
            "modules": [
                {
                    "key": "alerts",
                    "title": "异常预警",
                    "route": "/alerts",
                    "table_headers": ["配置项", "当前值", "适用范围"],
                    "rows": [["温控阈值", "-18C", "仓储"]],
                    "highlights": ["支持异常预警配置"],
                }
            ]
        }
        generated_files = {
            "frontend/src/pages/AlertsPage.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function AlertsPage() {
  const columns = [{ title: '当前值', dataIndex: 'currentValue', editable: true }];
  return <div>异常预警 配置项 温控阈值 {APP_PROFILE.product_name} {String(columns.length)}</div>;
}
""",
        }

        _, invalid_paths = repair_invalid_module_pages(generated_files, profile)

        assert "frontend/src/pages/AlertsPage.tsx" in invalid_paths

    def test_build_frontend_profile_source_allows_extended_module_fields(self):
        from app.services.project_profile import build_frontend_profile_source

        source = build_frontend_profile_source({"modules": []})

        assert "steps?: string[];" in source
        assert "business_value?: string;" in source
        assert "page_variant?: string;" in source


class TestStageContextAndResult:
    def test_stage_context_creation(self):
        ctx = StageContext(
            task_id="t1",
            build_id="b1",
            db_factory=lambda: None,
        )
        assert ctx.task_id == "t1"
        assert ctx.build_id == "b1"

    def test_stage_result_success(self):
        result = StageResult(success=True)
        assert result.success
        assert result.error is None

    def test_stage_result_failure(self):
        result = StageResult(success=False, error="test error")
        assert not result.success
        assert result.error == "test error"

    def test_stage_result_with_artifacts(self):
        result = StageResult(
            success=True,
            artifacts=[{"type": "prd", "name": "test_prd.md"}],
            metadata={"key": "value"},
        )
        assert len(result.artifacts) == 1
        assert result.metadata["key"] == "value"


def test_run_build_stage_writes_codegen_report_on_codegen_failure(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from app.core.config import settings

    task_id = str(uuid.uuid4())
    build_id = str(uuid.uuid4())
    prd_dir = tmp_path / "tasks" / task_id / "workspace" / "prd"
    prd_dir.mkdir(parents=True, exist_ok=True)
    (prd_dir / "product_summary.json").write_text("{}", encoding="utf-8")

    class _Task:
        keyword = "物流调度管理后台"
        product_name = "物流调度管理后台"
        version = "V1.0"
        industry = "物流"

    mock_session = AsyncMock()
    mock_session.get.return_value = _Task()
    mock_session.add = MagicMock()
    mock_session_factory = MagicMock()
    mock_session_scope = AsyncMock()
    mock_session_scope.__aenter__.return_value = mock_session
    mock_session_factory.return_value.return_value = mock_session_scope

    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "workers.stages.handlers.build_task_profile",
        lambda **_kwargs: {
            "app_type": "admin_web",
            "modules": [],
            "screenshot_scenarios": [],
            "scene": "调度",
            "software_category": "物流软件",
            "industry_scope": "物流",
        },
    )
    monkeypatch.setattr("workers.stages.handlers.prepare_seed_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "workers.stages.handlers.generate_task_app_code",
        AsyncMock(
            return_value=(
                {
                    "required_files": ["frontend/src/App.tsx"],
                    "generated_paths": [],
                    "invalid_core_paths": ["frontend/src/App.tsx"],
                    "invalid_core_previews": {"frontend/src/App.tsx": "export default function App() {}"},
                    "batches": [],
                },
                "App code generation failed: missing or invalid LLM-generated core frontend files: frontend/src/App.tsx",
            )
        ),
    )

    async def _run():
        ctx = StageContext(task_id=task_id, build_id=build_id, db_factory=mock_session_factory)
        return await run_build_stage(ctx)

    result = asyncio.run(_run())
    assert result.success is False
    report_path = tmp_path / "tasks" / task_id / "workspace" / "manifests" / "app_codegen_report.json"
    assert report_path.exists()
    report = report_path.read_text(encoding="utf-8")
    assert "invalid_core_paths" in report
    assert "frontend/src/App.tsx" in report


def test_run_build_stage_run_manifest_requires_typescript_build(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from app.core.config import settings

    task_id = str(uuid.uuid4())
    build_id = str(uuid.uuid4())
    prd_dir = tmp_path / "tasks" / task_id / "workspace" / "prd"
    prd_dir.mkdir(parents=True, exist_ok=True)
    (prd_dir / "product_summary.json").write_text("{}", encoding="utf-8")

    class _Task:
        keyword = "冷链履约协同平台"
        product_name = "冷链履约协同平台"
        version = "V1.0"
        industry = "物流"

    mock_session = AsyncMock()
    mock_session.get.return_value = _Task()
    mock_session.add = MagicMock()
    mock_session_factory = MagicMock()
    mock_session_scope = AsyncMock()
    mock_session_scope.__aenter__.return_value = mock_session
    mock_session_factory.return_value.return_value = mock_session_scope

    class _ValidationResult:
        valid = True
        errors: list[str] = []

    monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "workers.stages.handlers.build_task_profile",
        lambda **_kwargs: {
            "app_type": "admin_web",
            "modules": [],
            "screenshot_scenarios": [],
            "scene": "履约协同",
            "software_category": "物流软件",
            "industry_scope": "物流",
        },
    )
    monkeypatch.setattr("workers.stages.handlers.prepare_seed_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "workers.stages.handlers.generate_task_app_code",
        AsyncMock(return_value=({"generated_file_count": 0, "repaired_core_paths": [], "repaired_support_paths": []}, None)),
    )
    monkeypatch.setattr("workers.stages.handlers._log_task_progress", AsyncMock())
    monkeypatch.setattr("workers.stages.handlers._create_artifact", AsyncMock())
    monkeypatch.setattr(
        "workers.stages.handlers.validator.validate_all",
        lambda _payload: {
            "app_manifest": _ValidationResult(),
            "run_manifest": _ValidationResult(),
            "capture_manifest": _ValidationResult(),
            "code_index_manifest": _ValidationResult(),
        },
    )
    monkeypatch.setattr("workers.stages.handlers.validator.is_all_valid", lambda _validation: True)

    async def _run():
        ctx = StageContext(task_id=task_id, build_id=build_id, db_factory=mock_session_factory)
        return await run_build_stage(ctx)

    result = asyncio.run(_run())
    assert result.success is True
    run_manifest_path = tmp_path / "tasks" / task_id / "workspace" / "manifests" / "run_manifest.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    assert "node node_modules/typescript/bin/tsc -b" in run_manifest["install_commands"][0]


def test_generate_task_app_code_reports_batch_progress(tmp_path, monkeypatch):
    import workers.stages.build_support as build_support

    app_root = tmp_path / "app"
    prd_root = tmp_path / "prd"
    prd_root.mkdir(parents=True, exist_ok=True)
    (prd_root / "product_prd.md").write_text("# PRD\n", encoding="utf-8")
    (prd_root / "development_work_order.md").write_text("# Work Order\n", encoding="utf-8")

    profile = {
        "product_name": "盲盒平台",
        "scene": "门店扫码抽取盲盒并完成订单履约",
        "industry_scope": "零售",
        "user_roles": ["总部运营", "门店管理员"],
        "modules": [],
        "focus_terms": [],
        "core_entities": [],
        "experience_blueprint": {},
        "dashboard_metrics": [],
        "version": "V1.0",
    }
    prepare_seed_application(str(app_root), profile)

    class _Resp:
        def __init__(self, files):
            self.success = True
            self.structured = {"files": files}
            self.error = None

    class _LLM:
        async def generate_app_code(self, _prd, _wo, requirements):
            required = tuple(requirements["required_files"])
            if required == (
                "frontend/src/App.tsx",
                "frontend/src/pages/Login.tsx",
                "frontend/src/pages/Dashboard.tsx",
            ):
                return _Resp(
                    {
                        "frontend/src/App.tsx": "import { Routes, Route } from 'react-router-dom'; export default function App(){ return <Routes><Route path='/' element={<div>盲盒平台</div>} /></Routes>; }",
                        "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { return <button onClick={onLogin}>登录</button>; }",
                        "frontend/src/pages/Dashboard.tsx": "export default function Dashboard(){ return <div>系统首页</div>; }",
                    }
                )
            if required == (
                "frontend/src/services/api.ts",
                "frontend/src/types/constants.ts",
                "frontend/src/types/models.ts",
            ):
                return _Resp(
                    {
                        "frontend/src/services/api.ts": "export async function request(){ return {}; }",
                        "frontend/src/types/constants.ts": "export const APP_NAME = '盲盒平台';",
                        "frontend/src/types/models.ts": "export interface Demo { id: string }",
                    }
                )
            return _Resp({})

    llm = _LLM()
    monkeypatch.setattr(build_support, "get_llm_client", lambda: llm, raising=False)
    monkeypatch.setattr("app.services.llm.get_llm_client", lambda: llm)

    progress_events = []

    async def _record_progress(event):
        progress_events.append(event)

    async def _run():
        return await generate_task_app_code(str(app_root), str(prd_root), profile, progress_callback=_record_progress)

    report, error = asyncio.run(_run())
    assert error is None
    assert report is not None
    phases = [event["phase"] for event in progress_events]
    assert "batch_started" in phases
    assert "attempt_started" in phases
    assert "attempt_completed" in phases
    assert any(event["batch"] == "core" and event["phase"] == "batch_started" for event in progress_events)


def test_stage_started_event_is_committed_before_stage_handler_runs():
    from unittest.mock import AsyncMock, MagicMock
    from app.models.db import Build, Task
    from app.services import TaskService
    from workers.orchestrator import runner as runner_module

    task_id = uuid.uuid4()
    build_id = uuid.uuid4()
    task = Task(
        id=task_id,
        keyword="盲盒平台",
        product_name="盲盒平台",
        version="V1.0",
        status=TopLevelStatus.QUEUED.value,
        current_stage=TopLevelStatus.QUEUED.value,
        active_build_id=build_id,
    )
    build = Build(
        id=build_id,
        task_id=task_id,
        build_no=1,
        status=StageStatus.QUEUED.value,
        trigger_type="create",
        current_stage="plan",
    )

    task_events = []
    committed_events = []
    commit_log = []
    stage_assertions = {"called": False}

    original_create_stage_run = TaskService.create_stage_run
    original_mark_build_running = TaskService.mark_build_running
    original_log_event = TaskService.log_event
    original_complete_stage_run = TaskService.complete_stage_run
    original_mark_build_completed = TaskService.mark_build_completed
    original_mark_completed = TaskService.mark_completed

    class FakeSession:
        async def get(self, model, pk):
            if model is Task and pk == task_id:
                return task
            if model is Build and pk == build_id:
                return build
            return None

        async def refresh(self, _obj):
            return None

        async def commit(self):
            commit_log.append(
                [
                    (event.event_type, event.title, event.detail)
                    for event in task_events
                ]
            )
            committed_events[:] = list(task_events)

        async def flush(self):
            return None

        async def execute(self, *_args, **_kwargs):
            raise AssertionError("execute should not be called in this test")

        def add(self, obj):
            if isinstance(obj, type("X", (), {})):
                pass

    fake_session = FakeSession()

    class FakeFactory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def fake_create_stage_run(self, build_obj, stage_name):
        return type("SR", (), {"attempt_no": 1, "status": StageStatus.RUNNING.value, "stage_name": stage_name})()

    async def fake_mark_build_running(self, build_obj, stage_name):
        build_obj.status = StageStatus.RUNNING.value
        build_obj.current_stage = stage_name

    async def fake_log_event(self, **kwargs):
        event = type(
            "LoggedEvent",
            (),
            {
                "event_type": kwargs["event_type"],
                "title": kwargs["title"],
                "detail": kwargs.get("detail"),
                "payload_json": kwargs.get("payload_json"),
            },
        )()
        task_events.append(event)
        return event

    async def fake_complete_stage_run(self, _sr):
        return None

    async def fake_mark_build_completed(self, build_obj):
        build_obj.status = TopLevelStatus.COMPLETED.value
        build_obj.current_stage = TopLevelStatus.COMPLETED.value

    async def fake_mark_completed(self, task_obj):
        task_obj.status = TopLevelStatus.COMPLETED.value
        task_obj.current_stage = TopLevelStatus.COMPLETED.value

    async def fake_stage_handler(_ctx):
        stage_assertions["called"] = True
        assert any(event[0] == "stage_started" and event[1] == "plan 阶段开始" for event in committed_events)
        assert task.status == TopLevelStatus.PLANNING.value
        assert build.status == StageStatus.RUNNING.value
        return StageResult(success=True, metadata={})

    stage_name = StageName.PLAN
    previous_handler = runner_module.STAGE_HANDLERS[stage_name]

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(runner_module, "get_session_factory", lambda: FakeFactory())
        mp.setattr(TaskService, "create_stage_run", fake_create_stage_run)
        mp.setattr(TaskService, "mark_build_running", fake_mark_build_running)
        mp.setattr(TaskService, "log_event", fake_log_event)
        mp.setattr(TaskService, "complete_stage_run", fake_complete_stage_run)
        mp.setattr(TaskService, "mark_build_completed", fake_mark_build_completed)
        mp.setattr(TaskService, "mark_completed", fake_mark_completed)
        runner_module.STAGE_HANDLERS[stage_name] = fake_stage_handler
        try:
            asyncio.run(runner_module._async_run_pipeline(task_id, build_id))
        finally:
            runner_module.STAGE_HANDLERS[stage_name] = previous_handler
            TaskService.create_stage_run = original_create_stage_run
            TaskService.mark_build_running = original_mark_build_running
            TaskService.log_event = original_log_event
            TaskService.complete_stage_run = original_complete_stage_run
            TaskService.mark_build_completed = original_mark_build_completed
            TaskService.mark_completed = original_mark_completed

    assert stage_assertions["called"] is True
    assert any(any(event[0] == "stage_started" for event in batch) for batch in commit_log)


def test_run_capture_stage_fails_when_essential_pages_are_missing(tmp_path, monkeypatch):
    async def _fake_execute_capture_flow(**_kwargs):
        return 10, 1, ["系统首页", "授信主体管理"]

    async def _fake_log_task_progress(*_args, **_kwargs):
        return None

    monkeypatch.setattr("workers.stages.handlers._load_manifest", lambda _task_id, name: {"scenarios": []} if name == "capture_manifest" else {})
    monkeypatch.setattr("workers.stages.handlers.reset_screenshots_dir", lambda _task_id: str(tmp_path / "screenshots"))
    monkeypatch.setattr("workers.stages.handlers.workspace_path", lambda _task_id: str(tmp_path / "workspace"))
    monkeypatch.setattr("workers.stages.handlers.artifacts_dir", lambda _task_id: str(tmp_path / "artifacts"))
    monkeypatch.setattr("workers.stages.handlers.execute_capture_flow", _fake_execute_capture_flow)
    monkeypatch.setattr("workers.stages.handlers._log_task_progress", _fake_log_task_progress)

    async def _run():
        ctx = StageContext(task_id="task-1", build_id="build-1", db_factory=lambda: None)
        return await run_capture_stage(ctx)

    result = asyncio.run(_run())
    assert result.success is False
    assert result.error == "核心页面截图失败: 系统首页、授信主体管理"
    assert result.metadata["missing_essential_titles"] == ["系统首页", "授信主体管理"]


def test_collect_missing_essential_titles_marks_failed_or_missing_core_pages():
    class Result:
        def __init__(self, scenario_id: str, success: bool, image_path: str):
            self.scenario_id = scenario_id
            self.success = success
            self.image_path = image_path

    capture_manifest = {
        "scenarios": [
            {"id": "login-page", "title": "登录页", "route": "/login"},
            {"id": "dashboard", "title": "系统首页", "route": "/dashboard"},
            {"id": "records", "title": "授信主体管理", "route": "/records"},
            {"id": "records-filtered-1", "title": "授信主体管理筛选结果", "route": "/records"},
        ]
    }
    results = [
        Result("login-page", True, "/tmp/login-page.png"),
        Result("dashboard", False, ""),
    ]

    missing = _collect_missing_essential_titles(capture_manifest, results)

    assert missing == ["系统首页", "授信主体管理"]


def test_synthesize_app_tsx_keeps_valid_jsx_style_object_syntax():
    profile = {
        "product_name": "投资风险评估预警平台",
        "scene": "面向投资风险监控与预警处置的业务平台",
        "app_type": "admin_web",
        "modules": [
            {
                "key": "records",
                "route": "/records",
                "title": "多源数据接入与治理",
                "description": "用于承接多源数据治理与查询。",
            }
        ],
    }
    generated_files = {
        "frontend/src/pages/RecordsPage.tsx": "export default function RecordsPage(){ return <div>ok</div>; }"
    }

    content = _synthesize_app_tsx(profile, generated_files)

    assert "style={{ minHeight: '100vh'" in content
    assert "style={ minHeight: '100vh'" not in content
    assert "chromeTreatment = String((visualProfile.chrome_treatment as string) || (isDesktopClient ? 'desktop_workbench' : 'top_tabs'))" in content
    assert "if (!loggedIn) {" in content
    assert "<Login onLogin={handleLogin} />" in content
