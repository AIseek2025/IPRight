from __future__ import annotations

import asyncio
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
    build_codegen_batches,
    build_codegen_requirements,
    generate_task_app_code,
    hydrate_missing_files_from_template,
    normalize_generated_frontend_files,
    normalize_prd_summary_with_plan_seed,
    prepare_seed_application,
    repair_invalid_core_files,
)
from workers.stages.handlers import (
    _load_prd_summary,
    _merge_manual_llm_content,
    _derive_run_ports,
    run_plan_stage,
    run_build_stage,
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
from app.services.runtime import SandboxRuntime
from app.services.capture import PlaywrightCapture


class TestStageHandlers:
    """Unit tests for individual stage handler functions."""

    def test_plan_stage_returns_valid_result(self):
        from unittest.mock import AsyncMock, MagicMock
        import asyncio

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_factory = MagicMock()
        mock_session_scope = AsyncMock()
        mock_session_scope.__aenter__.return_value = mock_session
        mock_session_factory.return_value.return_value = mock_session_scope

        async def _run():
            ctx = StageContext(
                task_id=str(uuid.uuid4()),
                build_id=str(uuid.uuid4()),
                db_factory=mock_session_factory,
            )
            result = await run_plan_stage(ctx)
            return result

        result = asyncio.run(_run())
        assert isinstance(result, StageResult)
        assert result.success

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
        ]
        assert "frontend/src/pages/OrdersPage.tsx" in requirements["required_files"]
        assert "frontend/src/pages/CustomersPage.tsx" in requirements["required_files"]
        assert [page["title"] for page in requirements["module_pages"]] == ["订单管理", "客户管理"]
        assert requirements["app_type"] == "desktop_client"
        assert requirements["visual_profile"]["name"] == "graphite_client"
        assert batches[0]["name"] == "core"
        assert batches[1]["required_files"] == ["frontend/src/pages/OrdersPage.tsx"]
        assert batches[2]["required_files"] == ["frontend/src/pages/CustomersPage.tsx"]
        assert batches[0]["requirements"]["app_type"] == "desktop_client"
        assert batches[0]["requirements"]["experience_blueprint"]["name"] == "command_hub"
        assert batches[0]["requirements"]["visual_profile"]["name"] == "graphite_client"
        assert requirements["project_dna"]["architecture_style"] == "dispatch_flow"
        assert batches[0]["requirements"]["project_dna"]["module_signature"] == ["运单调度中心", "线路监控台"]
        assert batches[0]["requirements"]["topic_label"] == "智慧物流调度台"

    def test_plan_seed_normalization_resets_drifting_media_modules(self):
        plan_seed = {
            "preset_key": "media",
            "core_modules": ["短剧内容管理", "创作者与演员管理", "广告投放管理", "排期管理", "播放数据统计"],
            "required_pages": ["/login", "/dashboard", "/series", "/actors", "/campaigns", "/schedules", "/statistics"],
            "user_roles": ["超级管理员", "内容审核员", "运营编辑"],
        }
        prd_summary = {
            "app_type": "admin_web",
            "core_modules": ["剧集管理", "剧集审核", "演员管理", "排期管理", "数据统计"],
            "required_pages": ["/login", "/dashboard", "/series", "/series", "/actors", "/schedules", "/statistics"],
            "user_roles": ["超级管理员", "内容审核员", "运营编辑"],
        }

        normalized = normalize_prd_summary_with_plan_seed(prd_summary, plan_seed)

        assert normalized["core_modules"] == plan_seed["core_modules"]
        assert normalized["required_pages"] == plan_seed["required_pages"]

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

        assert invalid_paths == []
        assert "Routes" in repaired["frontend/src/App.tsx"]
        assert "指挥仪表盘" in repaired["frontend/src/pages/Dashboard.tsx"]
        assert "ipright_demo_auth" in repaired["frontend/src/pages/Login.tsx"]

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

    def test_prepare_seed_application_removes_seed_frontend_shell_files(self, tmp_path):
        app_root = tmp_path / "app"
        profile = {
            "product_name": "测试系统",
            "modules": [{"route": "/orders", "key": "orders"}],
        }

        prepare_seed_application(str(app_root), profile)

        assert not (app_root / "frontend/src/App.tsx").exists()
        assert not (app_root / "frontend/src/pages").exists()
        assert (app_root / "frontend/src/generated/appProfile.ts").exists()
        assert (app_root / "frontend/src/font.css").exists()
        assert (app_root / "frontend/src/App.css").exists()
        assert "import './font.css';" in (app_root / "frontend/src/main.tsx").read_text(encoding="utf-8")
        assert (app_root / "frontend/public/fonts/IPRightCJK.ttf").exists()

    def test_generate_task_app_code_fails_when_core_batch_fails(self, tmp_path, monkeypatch):
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
        assert error is not None
        assert "missing or invalid LLM-generated core frontend files" in error
        assert report["invalid_core_paths"] == [
            "frontend/src/App.tsx",
            "frontend/src/pages/Dashboard.tsx",
            "frontend/src/pages/Login.tsx",
        ]
        assert report["batches"][-1]["generated_paths"] == []
        assert report["batches"][-1]["error"]

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
                self.calls.append(required)
                if required == (
                    "frontend/src/App.tsx",
                    "frontend/src/pages/Login.tsx",
                    "frontend/src/pages/Dashboard.tsx",
                ):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "export default function App(){ return <div>APP_PROFILE.product_name</div>; }",
                        }
                    )
                if required == (
                    "frontend/src/pages/Login.tsx",
                    "frontend/src/pages/Dashboard.tsx",
                ):
                    return _Resp(
                        {
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { return <button onClick={onLogin}>登录</button>; }",
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
        assert ("frontend/src/App.tsx", "frontend/src/pages/Login.tsx", "frontend/src/pages/Dashboard.tsx") in llm.calls
        assert ("frontend/src/pages/Login.tsx", "frontend/src/pages/Dashboard.tsx") in llm.calls
        assert ("frontend/src/pages/Dashboard.tsx",) in llm.calls
        assert report["generated_file_count"] == 3

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
                if required == (
                    "frontend/src/App.tsx",
                    "frontend/src/pages/Login.tsx",
                    "frontend/src/pages/Dashboard.tsx",
                ):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "export default function App(){ return <div>调度工作台</div>; }",
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { return <button onClick={onLogin}>登录 用户名 密码</button>; }",
                            "frontend/src/pages/Dashboard.tsx": "export default function Dashboard(){ return <div>系统首页 调度工作台</div>; }",
                        }
                    )
                if required == (
                    "frontend/src/App.tsx",
                    "frontend/src/pages/Dashboard.tsx",
                ):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "import { Routes, Route } from 'react-router-dom'; import { APP_PROFILE } from './generated/appProfile'; export default function App(){ return <Routes><Route path='/dispatch' element={<div>{APP_PROFILE.product_name}</div>} /></Routes>; }",
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
        assert [call["required_files"] for call in llm.calls] == [
            ("frontend/src/App.tsx", "frontend/src/pages/Login.tsx", "frontend/src/pages/Dashboard.tsx"),
            ("frontend/src/App.tsx", "frontend/src/pages/Dashboard.tsx"),
        ]
        assert llm.calls[-1]["validation_hints"]
        retry_batch = next(batch for batch in report["batches"] if batch["batch"] == "core_invalid_retry")
        assert retry_batch["generated_paths"] == [
            "frontend/src/App.tsx",
            "frontend/src/pages/Dashboard.tsx",
        ]
        assert (app_root / "frontend/src/App.tsx").exists()
        assert (app_root / "frontend/src/pages/Login.tsx").exists()
        assert (app_root / "frontend/src/pages/Dashboard.tsx").exists()

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
        assert '"@ant-design/pro-components": "^2.8.6"' in updated
        assert '"dayjs": "^1.11.0"' in updated
        assert '"echarts": "^5.5.0"' in updated
        assert '"echarts-for-react": "^3.0.2"' in updated

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

    def test_render_font_css_prefers_horizontal_cjk_layout(self):
        css = _render_font_css()
        assert "@fontsource/noto-sans-sc/chinese-simplified.css" in css
        assert "min-width: 1360px" in css
        assert "writing-mode: horizontal-tb" in css
        assert "'Noto Sans SC'" in css
        assert "input, button, textarea, select" in css

    def test_render_frontend_app_uses_wider_horizontal_sidebar(self):
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
        assert "width: isDesktopClient ? 268 : 296" in app_code
        assert "minWidth: isDesktopClient ? 268 : 296" in app_code
        assert "writingMode: 'horizontal-tb'" in app_code
        assert "wordBreak: 'keep-all'" in app_code

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
