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
    build_seed_copy_ignore,
    build_codegen_batches,
    build_codegen_requirements,
    generate_task_app_code,
    hydrate_missing_files_from_template,
    normalize_generated_frontend_files,
    normalize_prd_summary_with_plan_seed,
    prepare_seed_application,
    repair_invalid_core_files,
    repair_invalid_module_pages,
)
from workers.stages.generated_frontend import _ensure_frontend_dependencies, sync_frontend_dependencies
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
from workers.stages.delivery_support import _warm_bundle_download
from workers.stages.generated_backend import write_generated_backend_files
from workers.stages import delivery_support as delivery_support_module
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

    def test_merge_manual_llm_content_dedupes_repeated_sentences(self):
        profile = {"modules": [{"title": "采购管理"}]}
        screenshots = [{"page_title": "采购管理", "route": "/purchases"}]
        llm_content = {
            "development_background": "平台围绕采购审批展开。平台围绕采购审批展开。",
            "technical_feature_bullets": ["统一登录", "统一登录", "过程留痕"],
            "module_overrides": [
                {
                    "title": "采购管理",
                    "description": "采购管理页面用于处理采购事项。采购管理页面用于处理采购事项。",
                    "steps": ["进入页面查看列表。", "进入页面查看列表。", "完成后导出结果。"],
                }
            ],
            "page_overrides": [
                {
                    "page_title": "采购管理",
                    "description": "采购页面展示审批结果。采购页面展示审批结果。",
                }
            ],
        }

        merged = _merge_manual_llm_content(profile, llm_content, screenshots)

        assert merged["development_background"] == "平台围绕采购审批展开。"
        assert merged["technical_feature_bullets"] == ["统一登录", "过程留痕"]
        assert merged["modules"][0]["description"] == "采购管理页面用于处理采购事项。"
        assert merged["modules"][0]["steps"] == ["进入页面查看列表。", "完成后导出结果。"]
        assert screenshots[0]["description"] == "采购页面展示审批结果。"

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
        assert batches[1]["name"] == "core_login"
        assert batches[1]["required_files"] == ["frontend/src/pages/Login.tsx"]
        assert batches[2]["name"] == "core_dashboard"
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
  return (
    <section>
      <h1>指挥仪表盘</h1>
      <div>{APP_PROFILE.product_name}</div>
      <div>
        {APP_PROFILE.dashboard_metrics.map((item) => (
          <article key={item.title}>
            <strong>{item.title}</strong>
            <span>{item.value}</span>
          </article>
        ))}
      </div>
    </section>
  );
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

export default function Dashboard() {
  return (
    <div>
      <h1>系统概览</h1>
      <div>{APP_PROFILE.product_name}</div>
      <Card>
        <Statistic title="当前指标数" value={APP_PROFILE.dashboard_metrics.length} />
      </Card>
      <ReactECharts option={{ xAxis: { type: 'category', data: ['本周'] }, yAxis: { type: 'value' }, series: [{ type: 'bar', data: [APP_PROFILE.dashboard_metrics.length] }] }} />
      <Table
        dataSource={[{ key: '1', item: '指标同步', status: '完成' }]}
        columns={[{ title: '事项', dataIndex: 'item' }, { title: '状态', dataIndex: 'status' }]}
        pagination={false}
      />
    </div>
  );
}
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

    def test_repair_invalid_core_files_rejects_dashboard_with_unsupported_antd_icon_name(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { Card, Statistic } from 'antd';
import { BriefcaseOutlined } from '@ant-design/icons';
import { APP_PROFILE } from '../generated/appProfile';

export default function Dashboard() {
  return (
    <section>
      <h1>系统首页</h1>
      <Card>
        <Statistic title={APP_PROFILE.dashboard_metrics[0]?.label} value={APP_PROFILE.dashboard_metrics[0]?.value} prefix={<BriefcaseOutlined />} />
      </Card>
    </section>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_top_level_table_config(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
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
import { TeamOutlined } from '@ant-design/icons';
import { APP_PROFILE } from '../generated/appProfile';

const columns = [
  { title: '事项', dataIndex: 'title' },
  { title: '状态', dataIndex: 'status' },
];

export default function Dashboard() {
  return (
    <section>
      <h1>系统首页</h1>
      <Card>
        <Statistic title={APP_PROFILE.product_name} value={APP_PROFILE.dashboard_metrics.length} prefix={<TeamOutlined />} />
      </Card>
      <Table columns={columns} dataSource={[{ key: '1', title: '事项A', status: '进行中' }]} pagination={False} />
    </section>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_typography_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { Card, Statistic, Table, Typography } from 'antd';
import { TeamOutlined } from '@ant-design/icons';
import { APP_PROFILE } from '../generated/appProfile';

const { Title } = Typography;

export default function Dashboard() {
  return (
    <section>
      <Title level={2}>系统首页</Title>
      <Card>
        <Statistic title={APP_PROFILE.product_name} value={APP_PROFILE.dashboard_metrics.length} prefix={<TeamOutlined />} />
      </Card>
      <Table dataSource={[{ key: '1', title: '事项A' }]} pagination={false} />
    </section>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_fallback_metrics_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { Card, Statistic, Table, Tag } from 'antd';
import { TeamOutlined, FileTextOutlined, CheckCircleOutlined, ClockCircleOutlined } from '@ant-design/icons';
import { APP_PROFILE } from '../generated/appProfile';

export default function Dashboard() {
  const fallbackMetrics = [
    { label: '进行中职位', value: 12 },
    { label: '待审批事项', value: 8 },
  ];
  return (
    <section>
      <h1>系统首页</h1>
      <Card>
        <Statistic title={APP_PROFILE.product_name} value={APP_PROFILE.dashboard_metrics.length} prefix={<TeamOutlined />} />
      </Card>
      <Table dataSource={fallbackMetrics.map((item, index) => ({ key: String(index), ...item }))} pagination={false} />
    </section>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_flex_monitor_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import React from 'react';
import { Card, Statistic } from 'antd';
import { APP_PROFILE } from '../generated/appProfile';

export default function Dashboard() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '20px 24px' }}>
      <h1>异常监控总览</h1>
      <p>{APP_PROFILE.product_name}</p>
      <Card>
        <Statistic title="异常总数" value={APP_PROFILE.dashboard_metrics.length} />
      </Card>
    </div>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_domain_workbench_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { Card, Statistic, Tag } from 'antd';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { APP_PROFILE } from '../generated/appProfile';

export default function Dashboard() {
  return (
    <div style={{ padding: '1.5rem 2rem' }}>
      <h1>冷链履约异常协同工作台</h1>
      <p>{APP_PROFILE.product_name}</p>
      <Card>
        <Statistic title="异常事件" value={APP_PROFILE.dashboard_metrics.length} prefix={<ExclamationCircleOutlined />} />
      </Card>
      <Tag color="warning">待协同处理</Tag>
    </div>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_icon_map_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { Card, Statistic } from 'antd';
import { CheckCircleOutlined, ExclamationCircleOutlined, ClockCircleOutlined, TeamOutlined } from '@ant-design/icons';
import { APP_PROFILE } from '../generated/appProfile';

export default function Dashboard() {
  const iconMap: Record<string, React.ReactNode> = {
    check: <CheckCircleOutlined />,
    alert: <ExclamationCircleOutlined />,
    time: <ClockCircleOutlined />,
    team: <TeamOutlined />,
  };
  return (
    <section>
      <h1>工作台</h1>
      <Card>
        <Statistic title={APP_PROFILE.product_name} value={APP_PROFILE.dashboard_metrics.length} prefix={iconMap.alert} />
      </Card>
    </section>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_four_icon_stats_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { Card, Statistic } from 'antd';
import { TeamOutlined, CalendarOutlined, FileTextOutlined, UserOutlined } from '@ant-design/icons';
import { APP_PROFILE } from '../generated/appProfile';

export default function Dashboard() {
  return (
    <section>
      <h1>工作台</h1>
      <Card>
        <Statistic title="团队总数" value={8} prefix={<TeamOutlined />} />
      </Card>
      <Card>
        <Statistic title="今日安排" value={5} prefix={<CalendarOutlined />} />
      </Card>
      <Card>
        <Statistic title="文档数量" value={APP_PROFILE.dashboard_metrics.length} prefix={<FileTextOutlined />} />
      </Card>
      <Card>
        <Statistic title={APP_PROFILE.product_name} value={12} prefix={<UserOutlined />} />
      </Card>
    </section>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_beige_icon_stats_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
import { Card, Statistic } from 'antd';
import { FileTextOutlined, UserOutlined, CalendarOutlined, CheckCircleOutlined } from '@ant-design/icons';

export default function Dashboard() {
  return (
    <div style={{ background: '#f8f5ef', minHeight: '100vh', padding: '24px' }}>
      <h1>工作台</h1>
      <Card><Statistic title="文档总数" value={APP_PROFILE.dashboard_metrics.length} prefix={<FileTextOutlined />} /></Card>
      <Card><Statistic title="活跃用户" value={12} prefix={<UserOutlined />} /></Card>
      <Card><Statistic title="今日安排" value={6} prefix={<CalendarOutlined />} /></Card>
      <Card><Statistic title={APP_PROFILE.product_name} value={1} prefix={<CheckCircleOutlined />} /></Card>
    </div>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_margin_metrics_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
import { Card, Statistic } from 'antd';

export default function Dashboard() {
  const metrics = APP_PROFILE.dashboard_metrics;
  return (
    <div style={{ margin: 24 }}>
      <h1>工作台</h1>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 24 }}>
        {metrics.map((item) => (
          <Card key={item.title}>
            <Statistic title={item.title} value={item.value} />
          </Card>
        ))}
      </div>
      <p>{APP_PROFILE.product_name}</p>
    </div>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_metrics_alias_blue_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
import { Card, Statistic } from 'antd';

export default function Dashboard() {
  const metrics = APP_PROFILE.dashboard_metrics || [];
  return (
    <div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>
      <h1 style={{ marginBottom: 24 }}>{APP_PROFILE.product_name}</h1>
      <Card>
        <Statistic title="指标数量" value={metrics.length} />
      </Card>
    </div>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_any_metrics_plain_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { Card, Statistic } from 'antd';
import { APP_PROFILE } from '../generated/appProfile';

export default function Dashboard() {
  const metrics = (APP_PROFILE as any).dashboard_metrics;
  return (
    <div style={{ padding: 24 }}>
      <h1>工作台</h1>
      <Card>
        <Statistic title="指标数量" value={metrics?.length || 0} />
      </Card>
    </div>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_string_padding_light_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { Card, Statistic } from 'antd';
import { APP_PROFILE } from '../generated/appProfile';

export default function Dashboard() {
  return (
    <div style={{ background: '#f8f5ef', minHeight: '100vh', padding: '24px' }}>
      <h1>工作台</h1>
      <Card>
        <Statistic title={APP_PROFILE.product_name} value={APP_PROFILE.dashboard_metrics.length} />
      </Card>
    </div>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_calendar_team_plain_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { Card, Statistic } from 'antd';
import { CalendarOutlined, TeamOutlined } from '@ant-design/icons';
import { APP_PROFILE } from '../generated/appProfile';

export default function Dashboard() {
  return (
    <div style={{ padding: '16px' }}>
      <h1>工作台</h1>
      <p style={{ color: '#555' }}>{APP_PROFILE.product_name}</p>
      <div style={{ display: 'flex', gap: 12 }}>
        <Card>
          <Statistic title="待办事项" value={8} prefix={<CalendarOutlined />} />
        </Card>
        <Card>
          <Statistic title="团队成员" value={12} prefix={<TeamOutlined />} />
        </Card>
      </div>
    </div>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

    def test_repair_invalid_core_files_rejects_dashboard_with_wrong_app_profile_path(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import { APP_PROFILE } from './generated/appProfile';
export default function App() {
  return <div>{APP_PROFILE.product_name}</div>;
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { Card, Statistic } from 'antd';
import { APP_PROFILE } from './generated/appProfile';

export default function Dashboard() {
  return (
    <section>
      <h1>系统首页</h1>
      <Card>
        <Statistic title={APP_PROFILE.product_name} value={APP_PROFILE.dashboard_metrics.length} />
      </Card>
    </section>
  );
}
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

        assert "frontend/src/pages/Dashboard.tsx" in invalid_paths

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
  return <section><h1>系统首页</h1><div>{APP_PROFILE.product_name}</div><div>{APP_PROFILE.dashboard_metrics.map((item) => <article key={item.title}>{item.title}{item.value}</article>)}</div></section>;
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

    def test_repair_invalid_core_files_rejects_heavy_tabs_app_shell(self, tmp_path):
        app_root = tmp_path / "app"
        _, invalid_paths = repair_invalid_core_files(
            str(app_root),
            generated_files={
                "frontend/src/App.tsx": """
import React, { useMemo } from 'react';
import { Routes, Route, Navigate, useLocation, useNavigate, NavLink, Outlet } from 'react-router-dom';
import { Tabs, Row, Col, Card, Button, Space } from 'antd';
import type { TabsProps } from 'antd';
import { APP_PROFILE } from './generated/appProfile';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import WorkflowPage from './pages/WorkflowPage';

export default function App() {
  const items: TabsProps['items'] = useMemo(() => [], []);
  return (
    <Row>
      <Col span={24}>
        <Card>
          <Space>{APP_PROFILE.product_name}</Space>
          <Tabs items={items} />
          <Routes>
            <Route path="/login" element={<Login onLogin={() => undefined} />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/workflow" element={<WorkflowPage />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
          <Outlet />
        </Card>
      </Col>
    </Row>
  );
}
""",
                "frontend/src/pages/Dashboard.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function Dashboard() {
  return <section><h1>系统首页</h1><div>{APP_PROFILE.product_name}</div><div>{APP_PROFILE.dashboard_metrics.map((item) => <article key={item.title}>{item.title}{item.value}</article>)}</div></section>;
}
""",
                "frontend/src/pages/Login.tsx": """
export default function Login({ onLogin }) {
  return <button onClick={onLogin}>登录 用户名 密码</button>;
}
""",
                "frontend/src/pages/WorkflowPage.tsx": """
export default function WorkflowPage() {
  return <div>职位与候选人管理</div>;
}
""",
            },
            profile={
                "modules": [
                    {"route": "/workflow", "key": "workflow"},
                ],
                "experience_blueprint": {"navigation_variant": "indexed"},
                "visual_profile": {"chrome_treatment": "indexed_topbar"},
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

    def test_repair_invalid_module_pages_rejects_reporting_copy(self):
        generated_files = {
            "frontend/src/pages/WorkflowPage.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function WorkflowPage() {
  return <section>任务简报 平台入口概览 风险指标体系与模型管理 分析编号 新能源债券组合压力测试</section>;
}
""",
        }
        profile = {
            "modules": [
                {
                    "title": "风险指标体系与模型管理",
                    "key": "workflow",
                    "route": "/workflow",
                    "table_headers": ["分析编号", "分析主题"],
                    "rows": [["AN-202605-017", "新能源债券组合压力测试"]],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/WorkflowPage.tsx"]
        assert "任务简报" in repaired["frontend/src/pages/WorkflowPage.tsx"]

    def test_repair_invalid_module_pages_rejects_workflow_candidate_white_shell(self):
        generated_files = {
            "frontend/src/pages/WorkflowPage.tsx": """
import React from 'react';
import { APP_PROFILE } from '../generated/appProfile';

export default function WorkflowPage() {
  return (
    <div style={{ padding: 24, background: '#ffffff', minHeight: '100vh' }}>
      <div style={{ color: '#888', fontSize: 12 }}>{APP_PROFILE.product_name} / 候选人管理</div>
      <h1 style={{ margin: '8px 0 16px' }}>候选人管理</h1>
      <p style={{ color: '#555' }}>用于处理候选人流程。</p>
    </div>
  );
}
""",
        }
        profile = {
            "modules": [
                {
                    "title": "风险指标体系与模型管理",
                    "key": "workflow",
                    "route": "/workflow",
                    "table_headers": ["分析编号", "分析主题"],
                    "rows": [["AN-202605-017", "新能源债券组合压力测试"]],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/WorkflowPage.tsx"]
        assert "候选人管理" in repaired["frontend/src/pages/WorkflowPage.tsx"]

    def test_repair_invalid_module_pages_rejects_trailing_import_and_missing_default_export(self):
        generated_files = {
            "frontend/src/pages/WorkflowPage.tsx": """
function WorkflowPage() {
  return (
    <section>
      <h1>借阅归还管理</h1>
      <button>新建借阅归还管理事项</button>
      <table>
        <tbody>
          <tr><td>借阅编号</td><td>BR-001</td><td>图书馆</td></tr>
        </tbody>
      </table>
    </section>
  );
}

import { APP_PROFILE } from '../generated/appProfile';
""",
        }
        profile = {
            "modules": [
                {
                    "title": "借阅归还管理",
                    "key": "workflow",
                    "route": "/workflow",
                    "primary_action": "新建借阅归还管理事项",
                    "filter_placeholder": "搜索借阅编号 / 归还状态 / 经办人",
                    "table_headers": ["借阅编号", "借阅主题", "归还状态"],
                    "rows": [["BR-001", "图书借阅", "待归还"]],
                    "page_variant": "workflow",
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/WorkflowPage.tsx"]
        assert "import { APP_PROFILE } from '../generated/appProfile';" in repaired["frontend/src/pages/WorkflowPage.tsx"]
        assert "export default function WorkflowPage" not in repaired["frontend/src/pages/WorkflowPage.tsx"]

    def test_repair_invalid_module_pages_rejects_title_only_inventory_shell_without_two_business_anchors(self):
        generated_files = {
            "frontend/src/pages/InventoryPage.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function InventoryPage() {
  return (
    <section>
      <h1>库存监控</h1>
      <div>{APP_PROFILE.product_name}</div>
    </section>
  );
}
""",
        }
        profile = {
            "modules": [
                {
                    "title": "库存监控",
                    "key": "inventory",
                    "route": "/inventory",
                    "primary_action": "登记温区批次",
                    "filter_placeholder": "搜索批次号 / 仓库 / 温区",
                    "table_headers": ["批次号", "仓库", "温区", "库存箱数"],
                    "rows": [["LOT-009", "前海保税仓", "-18C", "128箱"]],
                    "highlights": ["追踪冷链温区波动", "盘点异常库存"],
                    "page_variant": "assets",
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/InventoryPage.tsx"]
        assert "库存监控" in repaired["frontend/src/pages/InventoryPage.tsx"]
        assert "LOT-009" not in repaired["frontend/src/pages/InventoryPage.tsx"]

    def test_repair_invalid_module_pages_rejects_truncated_typescript_source(self):
        generated_files = {
            "frontend/src/pages/StatisticsPage.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function StatisticsPage() {
  const allData = [
    { key: '1', analysisId: 'MOD0-301', topic: '统计报表周报', dimension: '融合招聘一体化软件', responsible: '周铭', conclusion: '融合招聘一体化软件趋势稳定', updateTime: '2026-05-02' },
    { key: '2', analysisId: 'MOD0-302', topic: '统计报表月报', dimension: '教育
""",
        }
        profile = {
            "modules": [
                {
                    "title": "统计报表",
                    "key": "statistics",
                    "route": "/statistics",
                    "table_headers": ["分析编号", "分析主题", "统计维度", "负责人"],
                    "rows": [["MOD0-301", "统计报表周报", "融合招聘一体化软件", "周铭"]],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/StatisticsPage.tsx"]
        assert "统计报表月报" in repaired["frontend/src/pages/StatisticsPage.tsx"]

    def test_repair_invalid_module_pages_rejects_wrong_app_profile_relative_path(self):
        generated_files = {
            "frontend/src/pages/AssetsPage.tsx": """
import { APP_PROFILE } from '../../generated/appProfile';
export default function AssetsPage() {
  return <section><h1>招聘流程引擎</h1><div>{APP_PROFILE.product_name}</div><table><tbody><tr><td>WF-001</td><td>初筛流转</td><td>招聘经理</td></tr></tbody></table></section>;
}
""",
        }
        profile = {
            "modules": [
                {
                    "title": "招聘流程引擎",
                    "key": "assets",
                    "route": "/assets",
                    "table_headers": ["流程编号", "流程主题", "负责人"],
                    "rows": [["WF-001", "初筛流转", "招聘经理"]],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/AssetsPage.tsx"]
        assert "../../generated/appProfile" in repaired["frontend/src/pages/AssetsPage.tsx"]

    def test_repair_invalid_module_pages_rejects_default_app_profile_import(self):
        generated_files = {
            "frontend/src/pages/RecordsPage.tsx": """
import APP_PROFILE from '../generated/appProfile';
export default function RecordsPage() {
  return <section><h1>职位与岗位管理</h1><div>{APP_PROFILE.product_name}</div><table><tbody><tr><td>REC-001</td><td>岗位编制调整</td><td>招聘主管</td></tr></tbody></table></section>;
}
""",
        }
        profile = {
            "modules": [
                {
                    "title": "职位与岗位管理",
                    "key": "records",
                    "route": "/records",
                    "table_headers": ["记录编号", "主题名称", "责任角色"],
                    "rows": [["REC-001", "岗位编制调整", "招聘主管"]],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/RecordsPage.tsx"]
        assert "import APP_PROFILE from '../generated/appProfile'" in repaired["frontend/src/pages/RecordsPage.tsx"]

    def test_repair_invalid_module_pages_rejects_records_beige_light_shell(self):
        generated_files = {
            "frontend/src/pages/RecordsPage.tsx": """
import React from 'react';
import { APP_PROFILE } from '../generated/appProfile';

export default function RecordsPage() {
  return (
    <div style={{ padding: 24, background: '#f8f5ef', minHeight: '100vh' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ margin: 0 }}>职位与岗位管理</h1>
        <span>{APP_PROFILE.product_name}</span>
      </div>
      <input placeholder="搜索职位与岗位管理相关的融合招聘一体化软件/教育" />
      <table>
        <tbody>
          <tr><td>记录编号</td><td>主题名称</td><td>责任角色</td><td>当前状态</td></tr>
          <tr><td>REC-001</td><td>岗位编制调整</td><td>招聘主管</td><td>处理中</td></tr>
        </tbody>
      </table>
    </div>
  );
}
""",
        }
        profile = {
            "modules": [
                {
                    "title": "职位与岗位管理",
                    "key": "records",
                    "route": "/records",
                    "table_headers": ["记录编号", "主题名称", "责任角色", "当前状态"],
                    "rows": [["REC-001", "岗位编制调整", "招聘主管", "处理中"]],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/RecordsPage.tsx"]
        assert "background: '#f8f5ef'" in repaired["frontend/src/pages/RecordsPage.tsx"]

    def test_repair_invalid_module_pages_rejects_records_generic_array_shell(self):
        generated_files = {
            "frontend/src/pages/RecordsPage.tsx": """
import { APP_PROFILE } from '../generated/appProfile';
export default function RecordsPage() {
  const records = [
    { id: 'REC-001', topic: '图书管理平台图书档案管理', role: '图书管理员', status: '处理中', tag: '图书档案管理', updateTime: '2026-05-02' },
    { id: 'REC-002', topic: '图书档案管理协同跟进', role: '图书馆主管', status: '待审核', tag: '图书管理平台', updateTime: '2026-05-03' },
  ];
  return <section><h1>图书档案管理</h1><div>{APP_PROFILE.product_name}</div></section>;
}
""",
        }
        profile = {
            "modules": [
                {
                    "title": "图书档案管理",
                    "key": "records",
                    "route": "/records",
                    "table_headers": ["档案编号", "图书名称", "馆藏位置", "借阅状态"],
                    "rows": [["BK-001", "操作系统导论", "A-01书架", "可借阅"]],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/RecordsPage.tsx"]
        assert "const records = [" in repaired["frontend/src/pages/RecordsPage.tsx"]

    def test_repair_invalid_module_pages_rejects_statistics_heavy_antd_shell(self):
        generated_files = {
            "frontend/src/pages/StatisticsPage.tsx": """
import React from 'react';
import { Input, Button, Card, Row, Col, Typography } from 'antd';
import { SearchOutlined, BarChartOutlined } from '@ant-design/icons';
import { APP_PROFILE } from '../generated/appProfile';

const { Title, Text } = Typography;

const StatisticsPage: React.FC = () => {
  return (
    <div>
      <Title>统计报表</Title>
      <Text>{APP_PROFILE.product_name}</Text>
      <Input prefix={<SearchOutlined />} placeholder="搜索统计报表相关主题" />
      <Button icon={<BarChartOutlined />}>生成统计分析</Button>
      <Row gutter={16}>
        <Col span={12}><Card>摘要一</Card></Col>
      </Row>
    </div>
  );
};

export default StatisticsPage;
""",
        }
        profile = {
            "modules": [
                {
                    "title": "统计报表",
                    "key": "statistics",
                    "route": "/statistics",
                    "table_headers": ["分析编号", "分析主题", "统计维度", "负责人"],
                    "rows": [["AN-001", "图书借阅统计", "借阅量", "管理员"]],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/StatisticsPage.tsx"]
        assert "StatisticsPage: React.FC" in repaired["frontend/src/pages/StatisticsPage.tsx"]

    def test_repair_invalid_module_pages_rejects_analytics_heavy_antd_shell(self):
        generated_files = {
            "frontend/src/pages/AnalyticsPage.tsx": """
import React from 'react';
import { Typography, Input, Button, Space, Card, Tag } from 'antd';
import { SearchOutlined, PlusOutlined } from '@ant-design/icons';
import { APP_PROFILE } from '../generated/appProfile';

const { Title, Text } = Typography;

const AnalyticsPage: React.FC = () => {
  return (
    <div>
      <Title>风险指标体系与模型管理</Title>
      <Text>{APP_PROFILE.product_name}</Text>
      <Space>
        <Input prefix={<SearchOutlined />} placeholder="搜索风险指标体系与模型管理相关主题" />
        <Button icon={<PlusOutlined />}>新增风险指标</Button>
      </Space>
      <Card>
        <Tag>监测中</Tag>
      </Card>
    </div>
  );
};

export default AnalyticsPage;
""",
        }
        profile = {
            "modules": [
                {
                    "title": "风险指标体系与模型管理",
                    "key": "analytics",
                    "route": "/analytics",
                    "table_headers": ["分析编号", "分析主题", "负责人"],
                    "rows": [["AN-202605-017", "新能源债券组合压力测试", "周铭"]],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/AnalyticsPage.tsx"]
        assert "AnalyticsPage: React.FC" in repaired["frontend/src/pages/AnalyticsPage.tsx"]

    def test_repair_invalid_module_pages_rejects_reports_blue_shell(self):
        generated_files = {
            "frontend/src/pages/ReportsPage.tsx": """
import React from 'react';
import { APP_PROFILE } from '../generated/appProfile';

export default function ReportsPage() {
  return (
    <div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh', fontFamily: 'Inter, sans-serif' }}>
      <h1>录用与Offer管理</h1>
      <p>{APP_PROFILE.product_name}</p>
      <table>
        <tbody>
          <tr><td>分析编号</td><td>分析主题</td><td>统计维度</td></tr>
          <tr><td>AN-001</td><td>校招转化分析</td><td>转化率</td></tr>
        </tbody>
      </table>
    </div>
  );
}
""",
        }
        profile = {
            "modules": [
                {
                    "title": "招聘成效分析",
                    "key": "reports",
                    "route": "/reports",
                    "table_headers": ["分析编号", "分析主题", "统计维度"],
                    "rows": [["AN-001", "校招转化分析", "转化率"]],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/ReportsPage.tsx"]
        assert "录用与Offer管理" in repaired["frontend/src/pages/ReportsPage.tsx"]

    def test_repair_invalid_module_pages_rejects_statistics_blue_shell(self):
        generated_files = {
            "frontend/src/pages/StatisticsPage.tsx": """
import React from 'react';
import { APP_PROFILE } from '../generated/appProfile';

export default function StatisticsPage() {
  return (
    <div style={{ padding: '24px 32px', background: '#f3f6fb', minHeight: '100vh', fontFamily: 'Inter, sans-serif' }}>
      <h1>统计报表</h1>
      <p>{APP_PROFILE.product_name}</p>
      <table>
        <tbody>
          <tr><td>分析编号</td><td>分析主题</td><td>统计维度</td></tr>
          <tr><td>AN-001</td><td>图书借阅统计</td><td>借阅量</td></tr>
        </tbody>
      </table>
    </div>
  );
}
""",
        }
        profile = {
            "modules": [
                {
                    "title": "统计报表",
                    "key": "statistics",
                    "route": "/statistics",
                    "table_headers": ["分析编号", "分析主题", "统计维度"],
                    "rows": [["AN-001", "图书借阅统计", "借阅量"]],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/StatisticsPage.tsx"]
        assert "padding: '24px 32px'" in repaired["frontend/src/pages/StatisticsPage.tsx"]

    def test_repair_invalid_module_pages_rejects_statistics_product_name_light_shell(self):
        generated_files = {
            "frontend/src/pages/StatisticsPage.tsx": """
import { APP_PROFILE } from '../generated/appProfile';

export default function StatisticsPage() {
  const productName = APP_PROFILE.productName || '图书管理平台';
  return (
    <div style={{ padding: 24, fontFamily: 'system-ui, -apple-system, sans-serif' }}>
      <h1>统计分析</h1>
      <p>{productName}</p>
      <table>
        <tbody>
          <tr><td>分析编号</td><td>分析主题</td><td>统计维度</td></tr>
          <tr><td>AN-001</td><td>图书借阅统计</td><td>借阅量</td></tr>
        </tbody>
      </table>
    </div>
  );
}
""",
        }
        profile = {
            "modules": [
                {
                    "title": "统计报表",
                    "key": "statistics",
                    "route": "/statistics",
                    "table_headers": ["分析编号", "分析主题", "统计维度"],
                    "rows": [["AN-001", "图书借阅统计", "借阅量"]],
                }
            ]
        }

        repaired, repaired_paths = repair_invalid_module_pages(generated_files, profile)

        assert repaired_paths == ["frontend/src/pages/StatisticsPage.tsx"]
        assert "APP_PROFILE.productName" in repaired["frontend/src/pages/StatisticsPage.tsx"]

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

    def test_build_seed_copy_ignore_skips_macos_metadata(self):
        ignored = build_seed_copy_ignore()(
            "/tmp/source",
            ["src", "._src", "__MACOSX", ".DS_Store", "node_modules", "main.tsx"],
        )

        assert "._src" in ignored
        assert "__MACOSX" in ignored
        assert ".DS_Store" in ignored
        assert "node_modules" in ignored
        assert "main.tsx" not in ignored

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
        assert error == (
            "App code generation failed: missing or invalid LLM-generated core frontend files: "
            "frontend/src/App.tsx, frontend/src/pages/Dashboard.tsx, frontend/src/pages/Login.tsx"
        )
        assert report["repaired_core_paths"] == []
        assert report["repaired_support_paths"] == [
            "frontend/src/services/api.ts",
            "frontend/src/types/constants.ts",
            "frontend/src/types/models.ts",
        ]
        assert report["template_ui_fallback_used"] is False
        assert (app_root / "frontend/src/App.tsx").exists() is False
        assert (app_root / "frontend/src/pages/Login.tsx").exists() is False
        assert (app_root / "frontend/src/pages/Dashboard.tsx").exists() is False
        assert (app_root / "frontend/src/services/api.ts").exists() is False

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
                    return _Resp(
                        {
                            "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <section><h1>系统首页</h1><div>{APP_PROFILE.product_name}</div><div>{APP_PROFILE.dashboard_metrics.map((item) => <article key={item.title}>{item.title}{item.value}</article>)}</div></section>; }",
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
                        "invalid_core_previews": dict(requirements.get("invalid_core_previews", {})),
                    }
                )
                required = tuple(requirements["required_files"])
                if required == ("frontend/src/App.tsx",):
                    if requirements.get("invalid_core_previews"):
                        return _Resp(
                            {
                                "frontend/src/App.tsx": "import { Routes, Route } from 'react-router-dom'; import { APP_PROFILE } from './generated/appProfile'; import Dashboard from './pages/Dashboard'; export default function App(){ return <Routes><Route path='/' element={<Dashboard />} /><Route path='/dispatch' element={<div>{APP_PROFILE.product_name}</div>} /></Routes>; }",
                            }
                        )
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
                    if requirements.get("invalid_core_previews"):
                        return _Resp(
                            {
                                "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <section><h1>系统首页</h1><div>{APP_PROFILE.product_name}</div><div>{APP_PROFILE.dashboard_metrics.map((item) => <article key={item.title}>{item.title}{item.value}</article>)}</div></section>; }",
                            }
                        )
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
            ("frontend/src/App.tsx",),
            ("frontend/src/pages/Login.tsx",),
            ("frontend/src/pages/Dashboard.tsx",),
            (
                "frontend/src/services/api.ts",
                "frontend/src/types/constants.ts",
                "frontend/src/types/models.ts",
            ),
            ("frontend/src/App.tsx",),
            ("frontend/src/pages/Dashboard.tsx",),
        ]
        retry_calls = [call for call in llm.calls if call["invalid_core_previews"]]
        assert [call["required_files"] for call in retry_calls] == [
            ("frontend/src/App.tsx",),
            ("frontend/src/pages/Dashboard.tsx",),
        ]
        assert all(call["validation_hints"] for call in retry_calls)
        dashboard_retry_call = next(
            call for call in retry_calls if call["required_files"] == ("frontend/src/pages/Dashboard.tsx",)
        )
        assert any("export default function Dashboard()" in hint for hint in dashboard_retry_call["validation_hints"])
        assert any("压缩成精简首页" in hint for hint in dashboard_retry_call["validation_hints"])
        assert any("不要在组件外声明 `const items = [`" in hint for hint in dashboard_retry_call["validation_hints"])
        assert any("`const fallbackMetrics = [`" in hint for hint in dashboard_retry_call["validation_hints"])
        assert any("`const recentActivities = [`" in hint for hint in dashboard_retry_call["validation_hints"])
        assert any("`const columns = [`" in hint for hint in dashboard_retry_call["validation_hints"])
        assert any("`const { Title } = Typography`" in hint for hint in dashboard_retry_call["validation_hints"])
        assert any("`const metrics = APP_PROFILE.dashboard_metrics || []`" in hint for hint in dashboard_retry_call["validation_hints"])
        assert any("#f3f6fb" in hint and "APP_PROFILE.product_name" in hint for hint in dashboard_retry_call["validation_hints"])
        assert any("CalendarOutlined + TeamOutlined" in hint and "padding: '16px'" in hint for hint in dashboard_retry_call["validation_hints"])
        assert any("<h1>工作台</h1>" in hint and "产品名副标题" in hint for hint in dashboard_retry_call["validation_hints"])
        assert any("原生 `<table>`" in hint for hint in dashboard_retry_call["validation_hints"])

        app_retry_call = next(
            call for call in retry_calls if call["required_files"] == ("frontend/src/App.tsx",)
        )
        assert any("`useMemo`" in hint and "`useLocation`" in hint and "`useNavigate`" in hint for hint in app_retry_call["validation_hints"])
        assert any("`Row, Col, Card, Button, Space`" in hint for hint in app_retry_call["validation_hints"])
        retry_batches = [batch for batch in report["batches"] if batch["batch"] == "core_invalid_retry"]
        assert [batch["required_files"] for batch in retry_batches] == [
            ["frontend/src/App.tsx"],
            ["frontend/src/pages/Dashboard.tsx"],
        ]
        assert [batch["generated_paths"] for batch in retry_batches] == [
            ["frontend/src/App.tsx"],
            ["frontend/src/pages/Dashboard.tsx"],
        ]
        assert (app_root / "frontend/src/App.tsx").exists()
        assert (app_root / "frontend/src/pages/Login.tsx").exists()
        assert (app_root / "frontend/src/pages/Dashboard.tsx").exists()

    def test_build_codegen_batches_marks_core_dashboard_as_plaintext_single_file(self):
        codegen_requirements = {
            "required_files": [
                "frontend/src/App.tsx",
                "frontend/src/pages/Login.tsx",
                "frontend/src/pages/Dashboard.tsx",
            ],
            "core_required_files": [
                "frontend/src/App.tsx",
                "frontend/src/pages/Login.tsx",
                "frontend/src/pages/Dashboard.tsx",
            ],
            "raw_user_request": {},
            "app_type": "admin_web",
            "preset_key": "",
            "product_name": "测试系统",
            "short_name": "测试",
            "topic_label": "测试系统",
            "scene": "测试场景",
            "industry_scope": "测试行业",
            "software_category": "",
            "user_roles": ["管理员"],
            "focus_terms": [],
            "core_entities": [],
            "experience_blueprint": {},
            "visual_profile": {},
            "project_dna": {},
            "differentiation_hint": "",
            "module_pages": [],
        }

        batches = build_codegen_batches(codegen_requirements)
        core_dashboard = next(batch for batch in batches if batch["name"] == "core_dashboard")

        assert core_dashboard["required_files"] == ["frontend/src/pages/Dashboard.tsx"]
        assert core_dashboard["requirements"]["single_file_plaintext"] is True

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
                if required == ("frontend/src/App.tsx",):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "import React from 'react'; export default function App(){ return <div>坏壳层</div>; }",
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
                            "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <section><h1>系统首页</h1><div>{APP_PROFILE.product_name}</div><div>{APP_PROFILE.dashboard_metrics.map((item) => <article key={item.title}>{item.title}{item.value}</article>)}</div></section>; }",
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
        assert error == (
            "App code generation failed: missing or invalid LLM-generated core frontend files: "
            "frontend/src/App.tsx"
        )
        assert report["repaired_core_paths"] == []
        assert all(batch["batch"] != "core_structural_fallback" for batch in report["batches"])
        assert (app_root / "frontend/src/App.tsx").exists() is False

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
                if required == ("frontend/src/App.tsx",):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "import { Routes, Route } from 'react-router-dom'; import Login from './pages/Login'; import Dashboard from './pages/Dashboard'; import WorkflowPage from './pages/WorkflowPage'; import { APP_PROFILE } from './generated/appProfile'; export default function App(){ return <Routes><Route path='/login' element={<Login onLogin={() => undefined} />} /><Route path='/dashboard' element={<Dashboard />} /><Route path='/workflow' element={<WorkflowPage title={APP_PROFILE.product_name} />} /></Routes>; }",
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
                            "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <section><h1>系统首页</h1><div>{APP_PROFILE.product_name}</div><div>{APP_PROFILE.dashboard_metrics.map((item) => <article key={item.title}>{item.title}{item.value}</article>)}</div></section>; }",
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
        assert any("React.FC" in hint and "APP_PROFILE from '../generated/appProfile'" in hint for hint in retry_call["validation_hints"])
        assert any("const platformName = APP_PROFILE.product_name" in hint for hint in retry_call["validation_hints"])
        assert any("#ffffff" in hint and "候选人管理" in hint for hint in retry_call["validation_hints"])
        assert any("const WorkflowPage = () =>" in hint and "padding: 24" in hint and "候选人管理" in hint for hint in retry_call["validation_hints"])
        assert "frontend/src/pages/WorkflowPage.tsx" in retry_call["invalid_module_previews"]
        retry_batch = next(batch for batch in report["batches"] if batch["batch"] == "module_invalid_retry")
        assert retry_batch["generated_paths"] == ["frontend/src/pages/WorkflowPage.tsx"]
        page_text = (app_root / "frontend/src/pages/WorkflowPage.tsx").read_text(encoding="utf-8")
        assert "新能源债券组合压力测试" in page_text
        assert "mockData" not in page_text

    def test_assets_retry_hints_include_padding24_button_negative_example(self):
        import workers.stages.build_support as build_support

        hints = build_support._build_module_validation_hints(
            {
                "modules": [
                    {
                        "key": "assets",
                        "route": "/assets",
                        "title": "材料资产管理",
                        "primary_action": "新建材料资产台账",
                        "filter_placeholder": "搜索材料资产编号",
                        "table_headers": ["资产编号", "材料名称", "保管部门", "当前状态"],
                        "rows": [["AST-001", "申报材料总表", "知识产权部", "处理中"]],
                        "page_variant": "records",
                    }
                ]
            },
            ["frontend/src/pages/AssetsPage.tsx"],
        )

        assert any("import React from 'react'" in hint for hint in hints)
        assert any("padding: 24, maxWidth: 1200, margin: '0 auto'" in hint for hint in hints)
        assert any("面试管理" in hint for hint in hints)
        assert any("background: '#f3f6fb'" in hint and "面试流程管理" in hint for hint in hints)
        assert any("APP_PROFILE.productName" in hint for hint in hints)

    def test_workflow_retry_hints_include_product_name_breadcrumb_negative_example(self):
        import workers.stages.build_support as build_support

        hints = build_support._build_module_validation_hints(
            {
                "modules": [
                    {
                        "key": "workflow",
                        "route": "/workflow",
                        "title": "录用与入职管理",
                        "primary_action": "发起录用与入职流程",
                        "filter_placeholder": "搜索候选人姓名 / 录用岗位 / 办理阶段",
                        "table_headers": ["录用编号", "候选人姓名", "录用岗位", "办理阶段"],
                        "rows": [["OFF-202605-015", "林晓", "初中数学教研岗", "Offer审批中"]],
                        "page_variant": "workflow",
                    }
                ]
            },
            ["frontend/src/pages/WorkflowPage.tsx"],
        )

        assert any("function WorkflowPage() { return (" in hint and "padding: 24" in hint for hint in hints)
        assert any("APP_PROFILE.product_name" in hint and "灰色小字" in hint for hint in hints)
        assert any("export default function WorkflowPage()" in hint for hint in hints)
        assert any("所有 import 必须放在文件顶部" in hint for hint in hints)
        assert any("至少命中 2 个当前模块业务锚点" in hint for hint in hints)

    def test_assets_retry_hints_include_reader_card_centered_shell_negative_example(self):
        import workers.stages.build_support as build_support

        hints = build_support._build_module_validation_hints(
            {
                "modules": [
                    {
                        "key": "assets",
                        "route": "/assets",
                        "title": "馆藏资产管理",
                        "primary_action": "新建馆藏资产台账",
                        "filter_placeholder": "搜索资产编号 / 馆藏位置 / 状态",
                        "table_headers": ["资产编号", "资产名称", "馆藏位置", "当前状态"],
                        "rows": [["AST-001", "馆藏图书一批", "A区书库", "在库"]],
                        "page_variant": "assets",
                    }
                ]
            },
            ["frontend/src/pages/AssetsPage.tsx"],
        )

        assert any("padding: '24px', maxWidth: '1200px', margin: '0 auto'" in hint for hint in hints)
        assert any("读者证管理" in hint for hint in hints)

    def test_records_retry_hints_include_records_array_negative_example(self):
        import workers.stages.build_support as build_support

        hints = build_support._build_module_validation_hints(
            {
                "modules": [
                    {
                        "key": "records",
                        "route": "/records",
                        "title": "图书档案管理",
                        "primary_action": "新建图书档案",
                        "filter_placeholder": "搜索档案编号 / 图书名称 / 馆藏位置",
                        "table_headers": ["档案编号", "图书名称", "馆藏位置", "借阅状态"],
                        "rows": [["BK-001", "操作系统导论", "A-01书架", "可借阅"]],
                        "page_variant": "records",
                    }
                ]
            },
            ["frontend/src/pages/RecordsPage.tsx"],
        )

        assert any("const records = [" in hint for hint in hints)
        assert any("REC-001/REC-002" in hint for hint in hints)
        assert any("图书档案管理协同跟进" in hint for hint in hints)

    def test_dashboard_retry_hints_include_recent_events_negative_example(self):
        import workers.stages.build_support as build_support

        hints = build_support._build_core_validation_hints(
            {"modules": []},
            ["frontend/src/pages/Dashboard.tsx"],
        )

        assert any("const recentEvents = [" in hint for hint in hints)
        assert any("温度超标 / 运输延迟 / 处理中 / 待处理" in hint for hint in hints)
        assert any("E-001" in hint and "2025-06-01 10:30" in hint for hint in hints)
        assert any("E-002" in hint and "2025-06-01 09:15" in hint for hint in hints)

    def test_statistics_retry_hints_include_exact_product_name_shell_negative_example(self):
        import workers.stages.build_support as build_support

        hints = build_support._build_module_validation_hints(
            {
                "modules": [
                    {
                        "key": "statistics",
                        "route": "/statistics",
                        "title": "统计报表",
                        "primary_action": "生成统计分析",
                        "filter_placeholder": "搜索统计报表相关主题",
                        "table_headers": ["分析编号", "分析主题", "统计维度", "负责人"],
                        "rows": [["AN-001", "图书借阅统计", "借阅量", "管理员"]],
                        "page_variant": "reports",
                    }
                ]
            },
            ["frontend/src/pages/StatisticsPage.tsx"],
        )

        assert any("function StatisticsPage() { const productName = APP_PROFILE.productName" in hint for hint in hints)
        assert any("fontWeight: 600" in hint and "统计分析" in hint for hint in hints)
        assert any("const { productName } = APP_PROFILE;" in hint for hint in hints)
        assert any("maxWidth: 1200" in hint and "分析中心" in hint for hint in hints)
        assert any("数据分析与看板" in hint and "style={styles.container}" in hint for hint in hints)

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
                if required == ("frontend/src/App.tsx",):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "import { Routes, Route } from 'react-router-dom'; import { APP_PROFILE } from './generated/appProfile'; import Login from './pages/Login'; import Dashboard from './pages/Dashboard'; import PurchasesPage from './pages/PurchasesPage'; import InventoryPage from './pages/InventoryPage'; import AlertsPage from './pages/AlertsPage'; export default function App(){ return <div>{APP_PROFILE.product_name}<Routes><Route path='/login' element={<Login onLogin={() => undefined} />} /><Route path='/dashboard' element={<Dashboard />} /><Route path='/purchases' element={<PurchasesPage />} /><Route path='/inventory' element={<InventoryPage />} /><Route path='/alerts' element={<AlertsPage />} /></Routes></div>; }",
                        }
                    )
                if required == ("frontend/src/pages/Login.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { const handleSubmit = () => { localStorage.setItem('ipright_demo_auth', 'true'); onLogin(); }; return <button onClick={handleSubmit}>登录 用户名 密码</button>; }",
                        }
                    )
                if required == ("frontend/src/pages/Dashboard.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <section><h1>系统首页</h1><div>{APP_PROFILE.product_name}</div><div>{APP_PROFILE.dashboard_metrics.map((item) => <article key={item.title}>{item.title}{item.value}</article>)}</div></section>; }",
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
            ("frontend/src/pages/PurchasesPage.tsx",),
            ("frontend/src/pages/InventoryPage.tsx",),
            ("frontend/src/pages/AlertsPage.tsx",),
        ]
        retry_batches = [batch for batch in report["batches"] if batch["batch"] == "module_invalid_retry"]
        assert [batch["required_files"] for batch in retry_batches] == [
            ["frontend/src/pages/PurchasesPage.tsx"],
            ["frontend/src/pages/InventoryPage.tsx"],
            ["frontend/src/pages/AlertsPage.tsx"],
        ]
        assert "mockData" not in (app_root / "frontend/src/pages/PurchasesPage.tsx").read_text(encoding="utf-8")
        assert "mockData" not in (app_root / "frontend/src/pages/InventoryPage.tsx").read_text(encoding="utf-8")
        assert "mockData" not in (app_root / "frontend/src/pages/AlertsPage.tsx").read_text(encoding="utf-8")

    def test_generate_task_app_code_ignores_unexpected_files_in_module_retry(self, tmp_path, monkeypatch):
        import workers.stages.build_support as build_support

        app_root = tmp_path / "app"
        prd_root = tmp_path / "prd"
        prd_root.mkdir(parents=True, exist_ok=True)
        (prd_root / "product_prd.md").write_text("# PRD\n", encoding="utf-8")
        (prd_root / "development_work_order.md").write_text("# Work Order\n", encoding="utf-8")

        profile = {
            "product_name": "招聘分析平台",
            "scene": "围绕招聘记录、流程跟进和画像评估进行分析",
            "industry_scope": "人力资源",
            "user_roles": ["招聘主管"],
            "modules": [
                {
                    "title": "流程跟进",
                    "key": "workflow",
                    "route": "/workflow",
                    "primary_action": "新增跟进记录",
                    "filter_placeholder": "搜索候选人 / 岗位 / 招聘顾问",
                    "table_headers": ["候选人", "岗位", "环节", "顾问"],
                    "rows": [["林晓", "算法工程师", "终面", "周顾问"]],
                    "highlights": ["聚焦流程节点协作"],
                    "description": "管理招聘流程推进。",
                    "page_variant": "workflow",
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
                            "frontend/src/App.tsx": "import { Routes, Route } from 'react-router-dom'; import { APP_PROFILE } from './generated/appProfile'; import Login from './pages/Login'; import Dashboard from './pages/Dashboard'; import WorkflowPage from './pages/WorkflowPage'; export default function App(){ return <div>{APP_PROFILE.product_name}<Routes><Route path='/login' element={<Login onLogin={() => undefined} />} /><Route path='/dashboard' element={<Dashboard />} /><Route path='/workflow' element={<WorkflowPage />} /></Routes></div>; }",
                        }
                    )
                if required == ("frontend/src/pages/Login.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { const handleSubmit = () => { localStorage.setItem('ipright_demo_auth', 'true'); onLogin(); }; return <button onClick={handleSubmit}>登录 用户名 密码</button>; }",
                        }
                    )
                if required == ("frontend/src/pages/Dashboard.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <section><h1>系统首页</h1><div>{APP_PROFILE.product_name}</div><div>{APP_PROFILE.dashboard_metrics.map((item) => <article key={item.title}>{item.title}{item.value}</article>)}</div></section>; }",
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
                            "frontend/src/types/constants.ts": "export const APP_NAME = '招聘分析平台'; export const APP_VERSION = 'V1.0';",
                            "frontend/src/types/models.ts": "export interface LoginResponse { success: boolean; token?: string; }",
                        }
                    )
                if required == ("frontend/src/pages/WorkflowPage.tsx",):
                    if not requirements.get("invalid_module_previews"):
                        return _Resp(
                            {
                                "frontend/src/pages/WorkflowPage.tsx": "const mockData = [{ id: '1' }]; export default function WorkflowPage(){ return <div>流程跟进</div>; }",
                            }
                        )
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "import { Layout } from 'antd'; export default function App(){ return <Layout />; }",
                            "frontend/src/pages/WorkflowPage.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function WorkflowPage(){ return <section><h1>流程跟进</h1><div>{APP_PROFILE.product_name}</div><button>新增跟进记录</button><table><tbody><tr><td>林晓</td><td>算法工程师</td><td>终面</td><td>周顾问</td></tr></tbody></table></section>; }",
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
        retry_batch = next(batch for batch in report["batches"] if batch["batch"] == "module_invalid_retry")
        assert retry_batch["required_files"] == ["frontend/src/pages/WorkflowPage.tsx"]
        assert retry_batch["generated_paths"] == ["frontend/src/pages/WorkflowPage.tsx"]
        assert "unexpected files returned: frontend/src/App.tsx" in (retry_batch["error"] or "")
        app_text = (app_root / "frontend/src/App.tsx").read_text(encoding="utf-8")
        assert "<Layout />" not in app_text
        workflow_text = (app_root / "frontend/src/pages/WorkflowPage.tsx").read_text(encoding="utf-8")
        assert "林晓" in workflow_text

    def test_generate_task_app_code_ignores_unexpected_files_in_main_page_batch(self, tmp_path, monkeypatch):
        import workers.stages.build_support as build_support

        app_root = tmp_path / "app"
        prd_root = tmp_path / "prd"
        prd_root.mkdir(parents=True, exist_ok=True)
        (prd_root / "product_prd.md").write_text("# PRD\n", encoding="utf-8")
        (prd_root / "development_work_order.md").write_text("# Work Order\n", encoding="utf-8")

        profile = {
            "product_name": "档案管理平台",
            "scene": "围绕主体档案、证照记录和经营信息进行归集",
            "industry_scope": "企业服务",
            "user_roles": ["档案专员"],
            "modules": [
                {
                    "title": "主体档案",
                    "key": "records",
                    "route": "/records",
                    "primary_action": "新建主体档案",
                    "filter_placeholder": "搜索主体名称 / 统一代码 / 负责人",
                    "table_headers": ["主体名称", "统一代码", "负责人", "状态"],
                    "rows": [["华衡科技", "91310000MA1K12345A", "顾宁", "有效"]],
                    "highlights": ["覆盖主体信息归集"],
                    "description": "管理主体档案。",
                    "page_variant": "records",
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
                required = tuple(requirements["required_files"])
                self.calls.append({"required_files": required})
                if required == ("frontend/src/App.tsx",):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "import { Routes, Route } from 'react-router-dom'; import { APP_PROFILE } from './generated/appProfile'; import Login from './pages/Login'; import Dashboard from './pages/Dashboard'; import RecordsPage from './pages/RecordsPage'; export default function App(){ return <div>{APP_PROFILE.product_name}<Routes><Route path='/login' element={<Login onLogin={() => undefined} />} /><Route path='/dashboard' element={<Dashboard />} /><Route path='/records' element={<RecordsPage />} /></Routes></div>; }",
                        }
                    )
                if required == ("frontend/src/pages/Login.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { const handleSubmit = () => { localStorage.setItem('ipright_demo_auth', 'true'); onLogin(); }; return <button onClick={handleSubmit}>登录 用户名 密码</button>; }",
                        }
                    )
                if required == ("frontend/src/pages/Dashboard.tsx",):
                    return _Resp(
                        {
                            "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <section><h1>系统首页</h1><div>{APP_PROFILE.product_name}</div><div>{APP_PROFILE.dashboard_metrics.map((item) => <article key={item.title}>{item.title}{item.value}</article>)}</div></section>; }",
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
                            "frontend/src/types/constants.ts": "export const APP_NAME = '档案管理平台'; export const APP_VERSION = 'V1.0';",
                            "frontend/src/types/models.ts": "export interface LoginResponse { success: boolean; token?: string; }",
                        }
                    )
                if required == ("frontend/src/pages/RecordsPage.tsx",):
                    return _Resp(
                        {
                            "frontend/src/App.tsx": "import { Layout } from 'antd'; export default function App(){ return <Layout />; }",
                            "frontend/src/pages/RecordsPage.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function RecordsPage(){ return <section><h1>主体档案</h1><div>{APP_PROFILE.product_name}</div><button>新建主体档案</button><table><tbody><tr><td>华衡科技</td><td>91310000MA1K12345A</td><td>顾宁</td><td>有效</td></tr></tbody></table></section>; }",
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
        page_batch = next(batch for batch in report["batches"] if batch["batch"] == "page:RecordsPage")
        assert page_batch["required_files"] == ["frontend/src/pages/RecordsPage.tsx"]
        assert page_batch["generated_paths"] == ["frontend/src/pages/RecordsPage.tsx"]
        assert "unexpected files returned: frontend/src/App.tsx" in (page_batch["error"] or "")
        app_text = (app_root / "frontend/src/App.tsx").read_text(encoding="utf-8")
        assert "<Layout />" not in app_text
        records_text = (app_root / "frontend/src/pages/RecordsPage.tsx").read_text(encoding="utf-8")
        assert "华衡科技" in records_text

    def test_records_retry_hints_include_generic_data_negative_example(self):
        import workers.stages.build_support as build_support

        hints = build_support._build_module_validation_hints(
            {
                "modules": [
                    {
                        "key": "records",
                        "route": "/records",
                        "title": "职位与岗位管理",
                        "primary_action": "新建职位与岗位管理事项",
                        "filter_placeholder": "搜索职位与岗位管理",
                        "table_headers": ["记录编号", "主题名称", "责任角色", "当前状态"],
                        "rows": [["MOD0-001", "融合招聘一体化软件职位与岗位管理", "超级管理员", "处理中"]],
                        "page_variant": "records",
                    }
                ]
            },
            ["frontend/src/pages/RecordsPage.tsx"],
        )

        assert any("招聘需求管理" in hint for hint in hints)
        assert any("const data = [{ id, topic, role, status, tag, updateTime }]" in hint for hint in hints)

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

    def test_sync_frontend_dependencies_ignores_appledouble_sidecar_files(self, tmp_path):
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
                    }
                }
            ),
            encoding="utf-8",
        )
        (src_root / "Dashboard.tsx").write_text(
            "export default function Dashboard(){ return <div />; }\n",
            encoding="utf-8",
        )
        (src_root / "._Dashboard.tsx").write_bytes(b"\x00\x01\x02\xa3binary")

        sync_frontend_dependencies(str(frontend_root))

        updated = package_json.read_text(encoding="utf-8")
        assert '"react": "^18.3.0"' in updated
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
        assert "平台入口概览" not in markers

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
            if required == ("frontend/src/App.tsx",):
                return _Resp(
                    {
                            "frontend/src/App.tsx": "import { Routes, Route } from 'react-router-dom'; import { APP_PROFILE } from './generated/appProfile'; import Login from './pages/Login'; import Dashboard from './pages/Dashboard'; export default function App(){ return <div>{APP_PROFILE.product_name}<Routes><Route path='/login' element={<Login onLogin={() => undefined} />} /><Route path='/' element={<Dashboard />} /></Routes></div>; }",
                    }
                )
            if required == ("frontend/src/pages/Login.tsx",):
                return _Resp(
                    {
                        "frontend/src/pages/Login.tsx": "export default function Login({ onLogin }) { const handleSubmit = () => { localStorage.setItem('ipright_demo_auth', 'true'); onLogin(); }; return <button onClick={handleSubmit}>登录 用户名 密码</button>; }",
                    }
                )
            if required == ("frontend/src/pages/Dashboard.tsx",):
                return _Resp(
                    {
                        "frontend/src/pages/Dashboard.tsx": "import { APP_PROFILE } from '../generated/appProfile'; export default function Dashboard(){ return <section><h1>系统首页</h1><div>{APP_PROFILE.product_name}</div><div>{APP_PROFILE.dashboard_metrics.map((item) => <article key={item.title}>{item.title}{item.value}</article>)}</div></section>; }",
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


def test_warm_bundle_download_hits_dynamic_bundle_endpoint(monkeypatch):
    calls = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self, _size=-1):
            return b""

    def fake_urlopen(request, timeout):
        calls["url"] = request.full_url
        calls["auth"] = request.headers.get("Authorization")
        calls["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("IPRIGHT_API_TOKEN", "api-token")
    monkeypatch.setattr(delivery_support_module.urllib_request, "urlopen", fake_urlopen)

    assert _warm_bundle_download("task-123") is True
    assert calls["url"] == "http://127.0.0.1:18000/api/v1/tasks/task-123/bundle/download"
    assert calls["auth"] == "Bearer api-token"
    assert calls["timeout"] == 120


def test_warm_bundle_download_skips_without_api_token(monkeypatch):
    monkeypatch.delenv("IPRIGHT_API_TOKEN", raising=False)
    assert _warm_bundle_download("task-123") is False
