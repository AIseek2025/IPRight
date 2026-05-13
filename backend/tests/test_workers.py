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
    hydrate_missing_files_from_template,
    normalize_prd_summary_with_plan_seed,
    repair_invalid_core_files,
)
from workers.stages.handlers import (
    _derive_run_ports,
    run_plan_stage,
    run_build_stage,
    run_compose_manual_stage,
    run_compose_code_book_stage,
)
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
            "scene": "测试场景",
            "industry_scope": "测试行业",
            "user_roles": ["管理员"],
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
        assert batches[0]["name"] == "core"
        assert batches[1]["required_files"] == ["frontend/src/pages/OrdersPage.tsx"]
        assert batches[2]["required_files"] == ["frontend/src/pages/CustomersPage.tsx"]

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

    def test_hydrate_missing_files_from_template_uses_existing_page_code(self, tmp_path):
        app_root = tmp_path / "app"
        page_path = app_root / "frontend/src/pages/CategoriesPage.tsx"
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text("export default function CategoriesPage() { return null; }\n", encoding="utf-8")

        hydrated = hydrate_missing_files_from_template(
            str(app_root),
            generated_files={},
            required_files=["frontend/src/pages/CategoriesPage.tsx"],
        )

        assert "frontend/src/pages/CategoriesPage.tsx" in hydrated
        assert "CategoriesPage" in hydrated["frontend/src/pages/CategoriesPage.tsx"]

    def test_repair_invalid_core_files_restores_template_app_and_dashboard(self, tmp_path):
        app_root = tmp_path / "app"
        frontend_root = app_root / "frontend/src/pages"
        frontend_root.mkdir(parents=True, exist_ok=True)
        (app_root / "frontend/src").mkdir(parents=True, exist_ok=True)

        (app_root / "frontend/src/App.tsx").write_text(
            "import { APP_PROFILE } from './generated/appProfile';\nimport SeriesPage from './pages/SeriesPage';\nexport default function App(){ return <div>{APP_PROFILE.product_name}<SeriesPage /></div>; }\n",
            encoding="utf-8",
        )
        (app_root / "frontend/src/pages/Dashboard.tsx").write_text(
            "import { APP_PROFILE } from '../generated/appProfile';\nexport default function Dashboard(){ return <div>系统首页 {APP_PROFILE.product_name} {APP_PROFILE.dashboard_metrics.length}</div>; }\n",
            encoding="utf-8",
        )
        (app_root / "frontend/src/pages/Login.tsx").write_text(
            "export default function Login({ onLogin }) { return <button onClick={onLogin}>登录</button>; }\n",
            encoding="utf-8",
        )

        repaired, repaired_paths = repair_invalid_core_files(
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

        assert sorted(repaired_paths) == [
            "frontend/src/App.tsx",
            "frontend/src/pages/Dashboard.tsx",
            "frontend/src/pages/Login.tsx",
        ]
        assert "APP_PROFILE.product_name" in repaired["frontend/src/App.tsx"]
        assert "系统首页" in repaired["frontend/src/pages/Dashboard.tsx"]
        assert "onLogin" in repaired["frontend/src/pages/Login.tsx"]

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

    def test_capture_cleanup_failed_capture_removes_partial_png(self, tmp_path):
        capture = PlaywrightCapture(base_url="http://127.0.0.1:3000", output_dir=str(tmp_path))
        image_path = tmp_path / "login-page.png"
        image_path.write_bytes(b"partial")
        capture._cleanup_failed_capture(str(image_path))
        assert image_path.exists() is False

    def test_render_font_css_prefers_horizontal_cjk_layout(self):
        css = _render_font_css()
        assert "@fontsource/noto-sans-sc/chinese-simplified.css" in css
        assert "min-width: 1360px" in css
        assert "writing-mode: horizontal-tb" in css
        assert "'Noto Sans SC'" in css

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
        assert "width: 296" in app_code
        assert "minWidth: 296" in app_code
        assert "writingMode: 'horizontal-tb'" in app_code
        assert "wordBreak: 'keep-all'" in app_code

    def test_render_login_page_has_nonempty_right_panel(self):
        page_code = _render_login_page()
        assert "平台入口概览" in page_code
        assert "previewModules" in page_code
        assert "loginVariant === 'workspace' ? '1.12fr 380px' : '420px 1fr'" in page_code

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
        assert "核心字段" in page_code
        assert "数据样例" in page_code
        assert "routeBadge" in page_code


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
