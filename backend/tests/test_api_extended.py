from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

os.environ["IPRIGHT_DATABASE_URL"] = "sqlite+aiosqlite:///./test_api.db"
os.environ["IPRIGHT_DB_TYPE"] = "sqlite"
os.environ["IPRIGHT_AUTO_DISPATCH_TASKS"] = "false"

from app.main import app
from app.core.config import settings
from app.core.database import Base, _get_engine
from app.models.db import Artifact, Build, Export, Screenshot, Task, TaskEvent
from app.services import TaskService

settings.AUTO_DISPATCH_TASKS = False


@pytest_asyncio.fixture(scope="module")
async def _init_db():
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def async_client(_init_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

@pytest.mark.asyncio
class TestTaskLifecycle:
    async def test_create_and_get(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "生命周期测试"})
        assert resp.status_code == 201
        task_id = resp.json()["data"]["task_id"]

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}")
        assert resp2.status_code == 200
        assert resp2.json()["data"]["keyword"] == "生命周期测试"
        assert resp2.json()["data"]["status"] == "queued"

    async def test_create_task_creates_active_build(self, async_client):
        resp = await async_client.post(
            "/api/v1/tasks",
            json={"keyword": "构建派发测试", "product_name": "构建派发系统"},
        )
        assert resp.status_code == 201
        task_id = resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            assert task.active_build_id is not None
            assert task.status == "queued"
            assert task.current_stage == "queued"

            builds = (
                await session.execute(
                    select(Build).where(Build.task_id == task.id).order_by(Build.build_no.asc())
                )
            ).scalars().all()

            assert len(builds) == 1
            assert builds[0].build_no == 1
            assert builds[0].trigger_type == "create"
            assert builds[0].status == "queued"
            assert str(builds[0].id) == str(task.active_build_id)

    async def test_create_and_cancel(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "取消测试"})
        task_id = resp.json()["data"]["task_id"]

        resp2 = await async_client.post(f"/api/v1/tasks/{task_id}/cancel")
        assert resp2.status_code == 200

        resp3 = await async_client.get(f"/api/v1/tasks/{task_id}")
        assert resp3.json()["data"]["status"] == "cancelled"

    async def test_create_and_retry(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "重试测试"})
        task_id = resp.json()["data"]["task_id"]

        resp2 = await async_client.post(f"/api/v1/tasks/{task_id}/retry", json={})
        assert resp2.status_code == 409

        resp3 = await async_client.post(f"/api/v1/tasks/{task_id}/retry", json={"from_stage": "capturing"})
        assert resp3.status_code == 409

    async def test_retry_creates_new_build_and_switches_active_build(self, async_client):
        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "二次构建测试"})
        assert create_resp.status_code == 201
        task_id = create_resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            first_build = (
                await session.execute(
                    select(Build).where(Build.task_id == task.id).order_by(Build.build_no.asc())
                )
            ).scalars().first()
            assert first_build is not None
            first_build.status = "completed"
            first_build.current_stage = "completed"
            await session.commit()

        retry_resp = await async_client.post(
            f"/api/v1/tasks/{task_id}/retry",
            json={"from_stage": "capturing"},
        )
        assert retry_resp.status_code == 200

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            assert task.active_build_id is not None

            builds = (
                await session.execute(
                    select(Build).where(Build.task_id == task.id).order_by(Build.build_no.asc())
                )
            ).scalars().all()

            assert len(builds) == 2
            assert [build.build_no for build in builds] == [1, 2]
            assert [build.trigger_type for build in builds] == ["create", "retry"]
            assert str(builds[-1].id) == str(task.active_build_id)
            assert builds[-1].current_stage == "capture"

    async def test_retry_from_stage_name_resumes_from_previous_top_level_status(self, async_client):
        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "阶段名重试测试"})
        assert create_resp.status_code == 201
        task_id = create_resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            first_build = (
                await session.execute(
                    select(Build).where(Build.task_id == task.id).order_by(Build.build_no.asc())
                )
            ).scalars().first()
            assert first_build is not None
            first_build.status = "completed"
            first_build.current_stage = "completed"
            await session.commit()

        retry_resp = await async_client.post(
            f"/api/v1/tasks/{task_id}/retry",
            json={"from_stage": "compose_manual"},
        )
        assert retry_resp.status_code == 200

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            assert task.status == "capturing"
            assert task.current_stage == "capturing"
            latest_build = (
                await session.execute(
                    select(Build).where(Build.task_id == task.id).order_by(Build.build_no.desc()).limit(1)
                )
            ).scalars().first()
            assert latest_build is not None
            assert latest_build.current_stage == "compose_manual"

    async def test_retry_rejects_when_active_build_is_running(self, async_client):
        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "重试抢占测试"})
        assert create_resp.status_code == 201
        task_id = create_resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            first_build = (
                await session.execute(
                    select(Build).where(Build.task_id == task.id).order_by(Build.build_no.asc())
                )
            ).scalars().first()
            assert first_build is not None
            first_build.status = "running"
            first_build.current_stage = "compose_code_book"
            await session.commit()

        retry_resp = await async_client.post(f"/api/v1/tasks/{task_id}/retry", json={})
        assert retry_resp.status_code == 409
        payload = retry_resp.json()
        detail = payload["detail"] if "detail" in payload else payload
        assert detail["code"] == "BUILD_ALREADY_RUNNING"

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            builds = (
                await session.execute(
                    select(Build).where(Build.task_id == task.id).order_by(Build.build_no.asc())
                )
            ).scalars().all()
            assert len(builds) == 1
            assert builds[0].status == "running"
            assert builds[0].current_stage == "compose_code_book"
            assert str(builds[0].id) == str(task.active_build_id)

    async def test_retry_releases_stale_running_build_and_creates_new_build(self, async_client):
        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "过期运行构建释放测试"})
        assert create_resp.status_code == 201
        task_id = create_resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            first_build = (
                await session.execute(
                    select(Build).where(Build.task_id == task.id).order_by(Build.build_no.asc())
                )
            ).scalars().first()
            assert first_build is not None
            first_build.status = "running"
            first_build.current_stage = "verify_run"
            first_build.started_at = datetime.utcnow() - timedelta(hours=12)
            task.active_build_id = first_build.id
            await session.commit()

        retry_resp = await async_client.post(f"/api/v1/tasks/{task_id}/retry", json={"from_stage": "build"})
        assert retry_resp.status_code == 200

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            builds = (
                await session.execute(
                    select(Build).where(Build.task_id == task.id).order_by(Build.build_no.asc())
                )
            ).scalars().all()
            assert len(builds) == 2
            assert builds[0].status == "aborted"
            assert builds[0].current_stage == "aborted"
            assert "Automatically aborted stale" in (builds[0].failure_reason or "")
            assert builds[1].status == "queued"
            assert builds[1].build_no == 2
            assert str(task.active_build_id) == str(builds[1].id)

    async def test_get_task_reconciles_stale_running_build_to_failed(self, async_client):
        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "过期状态对齐测试"})
        assert create_resp.status_code == 201
        task_id = create_resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            build = (
                await session.execute(
                    select(Build).where(Build.task_id == task.id).order_by(Build.build_no.asc()).limit(1)
                )
            ).scalars().first()
            assert build is not None
            build.status = "running"
            build.current_stage = "build"
            build.started_at = datetime.utcnow() - timedelta(hours=12)
            task.status = "building"
            task.current_stage = "building"
            task.active_build_id = build.id
            await session.commit()

        detail_resp = await async_client.get(f"/api/v1/tasks/{task_id}")
        assert detail_resp.status_code == 200
        assert detail_resp.json()["data"]["status"] == "failed"
        assert detail_resp.json()["data"]["current_stage"] == "failed"
        assert detail_resp.json()["data"]["active_build_id"] is None

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            build = (
                await session.execute(
                    select(Build).where(Build.task_id == uuid.UUID(task_id)).order_by(Build.build_no.asc()).limit(1)
                )
            ).scalars().first()
            assert task is not None
            assert build is not None
            assert task.status == "failed"
            assert task.current_stage == "failed"
            assert task.active_build_id is None
            assert build.status == "aborted"
            assert build.current_stage == "aborted"
            assert "Automatically aborted stale" in (build.failure_reason or "")

    async def test_list_tasks_reconciles_orphaned_building_task_to_failed(self, async_client):
        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "孤儿任务状态对齐测试"})
        assert create_resp.status_code == 201
        task_id = create_resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            build = (
                await session.execute(
                    select(Build).where(Build.task_id == task.id).order_by(Build.build_no.asc()).limit(1)
                )
            ).scalars().first()
            assert build is not None
            build.status = "aborted"
            build.current_stage = "aborted"
            build.failure_reason = "Automatically aborted stale queued/running build after timeout"
            build.finished_at = datetime.utcnow()
            task.status = "building"
            task.current_stage = "building"
            task.active_build_id = None
            await session.commit()

        list_resp = await async_client.get("/api/v1/tasks?page=1&page_size=100")
        assert list_resp.status_code == 200
        items = list_resp.json()["data"]["items"]
        item = next(entry for entry in items if entry["id"] == task_id)
        assert item["status"] == "failed"
        assert item["current_stage"] == "failed"

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            assert task.status == "failed"
            assert task.current_stage == "failed"
            assert task.active_build_id is None

    async def test_task_service_marks_build_completed(self, async_client):
        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "构建完成态测试"})
        assert create_resp.status_code == 201
        task_id = create_resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            build = (
                await session.execute(
                    select(Build).where(Build.task_id == task.id).order_by(Build.build_no.asc())
                )
            ).scalars().first()
            assert build is not None

            service = TaskService(session)
            await service.mark_build_running(build, "verify_run")
            await service.mark_build_completed(build)
            await session.commit()

        async with get_session_factory()() as session:
            build = (
                await session.execute(
                    select(Build).where(Build.task_id == uuid.UUID(task_id)).order_by(Build.build_no.asc())
                )
            ).scalars().first()
            assert build is not None
            assert build.status == "completed"
            assert build.current_stage == "completed"
            assert build.finished_at is not None

    async def test_task_service_log_event_visible_in_dashboard_timeline(self, async_client):
        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "进度日志测试"})
        assert create_resp.status_code == 201
        task_id = create_resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            service = TaskService(session)
            await service.log_event(
                task_id=task.id,
                build_id=task.active_build_id,
                event_type="stage_progress",
                title="应用代码已生成",
                detail="已完成核心页面与运行清单写入",
                payload_json={"generated_file_count": 9},
            )
            await session.commit()

        async with get_session_factory()() as session:
            events = (
                await session.execute(
                    select(TaskEvent)
                    .where(TaskEvent.task_id == uuid.UUID(task_id))
                    .order_by(TaskEvent.created_at.desc())
                )
            ).scalars().all()
            assert any(event.title == "应用代码已生成" for event in events)

        dashboard_resp = await async_client.get(f"/api/v1/tasks/{task_id}/dashboard")
        assert dashboard_resp.status_code == 200
        timeline = dashboard_resp.json()["data"]["timeline"]
        assert any(item["title"] == "应用代码已生成" for item in timeline)

    async def test_get_dashboard(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "dashboard测试"})
        task_id = resp.json()["data"]["task_id"]

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/dashboard")
        assert resp2.status_code == 200
        data = resp2.json()["data"]
        assert "task" in data
        assert "timeline" in data
        assert "exports" in data

    async def test_get_timeline(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "timeline测试"})
        task_id = resp.json()["data"]["task_id"]

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/timeline")
        assert resp2.status_code == 200
        assert len(resp2.json()["data"]["items"]) >= 1

    async def test_get_artifacts_empty(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "artifact测试"})
        task_id = resp.json()["data"]["task_id"]

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/artifacts")
        assert resp2.status_code == 200
        assert resp2.json()["data"]["items"] == []

    async def test_get_exports_empty(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "export测试"})
        task_id = resp.json()["data"]["task_id"]

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/exports")
        assert resp2.status_code == 200
        assert resp2.json()["data"]["items"] == []

    async def test_get_screenshots_empty(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "screenshot测试"})
        task_id = resp.json()["data"]["task_id"]

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/screenshots")
        assert resp2.status_code == 200
        assert resp2.json()["data"]["items"] == []

    async def test_get_artifacts_respects_limit(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "artifact_limit测试"})
        task_id = resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            for idx in range(5):
                session.add(
                    Artifact(
                        task_id=task.id,
                        artifact_type="test",
                        artifact_name=f"artifact_{idx}",
                    )
                )
            await session.commit()

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/artifacts?limit=3")
        assert resp2.status_code == 200
        items = resp2.json()["data"]["items"]
        assert len(items) == 3
        assert items[0]["artifact_name"] == "artifact_4"

    async def test_get_artifacts_defaults_to_active_build(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "artifact_build_filter测试"})
        task_id = resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            old_build = Build(task_id=task.id, build_no=2, status="completed")
            new_build = Build(task_id=task.id, build_no=3, status="running")
            session.add_all([old_build, new_build])
            await session.flush()
            task.active_build_id = new_build.id
            session.add_all(
                [
                    Artifact(task_id=task.id, build_id=old_build.id, artifact_type="test", artifact_name="old_artifact"),
                    Artifact(task_id=task.id, build_id=new_build.id, artifact_type="test", artifact_name="new_artifact"),
                ]
            )
            await session.commit()

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/artifacts")
        assert resp2.status_code == 200
        items = resp2.json()["data"]["items"]
        assert [item["artifact_name"] for item in items] == ["new_artifact"]

        resp3 = await async_client.get(f"/api/v1/tasks/{task_id}/artifacts?build_id={old_build.id}")
        assert resp3.status_code == 200
        assert [item["artifact_name"] for item in resp3.json()["data"]["items"]] == ["old_artifact"]

    async def test_get_screenshots_respects_limit_and_keeps_oldest_first(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "screenshot_limit测试"})
        task_id = resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            for idx in range(5):
                session.add(
                    Screenshot(
                        task_id=task.id,
                        scenario_id=f"scene_{idx}",
                        page_title=f"页面{idx}",
                        route=f"/route/{idx}",
                    )
                )
            await session.commit()

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/screenshots?limit=3")
        assert resp2.status_code == 200
        items = resp2.json()["data"]["items"]
        assert len(items) == 3
        assert [item["scenario_id"] for item in items] == ["scene_2", "scene_3", "scene_4"]

    async def test_get_screenshots_defaults_to_active_build(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "screenshot_build_filter测试"})
        task_id = resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            old_build = Build(task_id=task.id, build_no=2, status="completed")
            new_build = Build(task_id=task.id, build_no=3, status="running")
            session.add_all([old_build, new_build])
            await session.flush()
            task.active_build_id = new_build.id
            session.add_all(
                [
                    Screenshot(task_id=task.id, build_id=old_build.id, scenario_id="old_scene", page_title="旧页面", route="/old"),
                    Screenshot(task_id=task.id, build_id=new_build.id, scenario_id="new_scene", page_title="新页面", route="/new"),
                ]
            )
            await session.commit()

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/screenshots")
        assert resp2.status_code == 200
        items = resp2.json()["data"]["items"]
        assert [item["scenario_id"] for item in items] == ["new_scene"]

        resp3 = await async_client.get(f"/api/v1/tasks/{task_id}/screenshots?build_id={old_build.id}")
        assert resp3.status_code == 200
        assert [item["scenario_id"] for item in resp3.json()["data"]["items"]] == ["old_scene"]

    async def test_get_exports_returns_build_no_and_latest_first(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "export_build_order测试"})
        task_id = resp.json()["data"]["task_id"]

        from app.core.database import get_session_factory

        async with get_session_factory()() as session:
            task = await session.get(Task, uuid.UUID(task_id))
            assert task is not None
            old_build = Build(task_id=task.id, build_no=2, status="completed", finished_at=datetime.utcnow() - timedelta(hours=1))
            new_build = Build(task_id=task.id, build_no=3, status="completed", finished_at=datetime.utcnow())
            session.add_all([old_build, new_build])
            await session.flush()
            session.add_all(
                [
                    Export(
                        task_id=task.id,
                        build_id=old_build.id,
                        export_type="manual_docx",
                        file_name="software_manual.docx",
                        status="ready",
                        download_url="/api/v1/exports/old/download",
                    ),
                    Export(
                        task_id=task.id,
                        build_id=new_build.id,
                        export_type="manual_docx",
                        file_name="software_manual.docx",
                        status="ready",
                        download_url="/api/v1/exports/new/download",
                    ),
                ]
            )
            await session.commit()

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/exports")
        assert resp2.status_code == 200
        items = resp2.json()["data"]["items"]
        assert [item["build_no"] for item in items] == [3, 2]
        assert items[0]["download_url"] == "/api/v1/exports/new/download"
        assert items[0]["is_latest"] is True
        assert items[1]["is_latest"] is False
        assert items[0]["build_finished_at"] is not None

        dashboard_resp = await async_client.get(f"/api/v1/tasks/{task_id}/dashboard")
        assert dashboard_resp.status_code == 200
        dashboard_exports = dashboard_resp.json()["data"]["exports"]
        assert [item["build_no"] for item in dashboard_exports] == [3, 2]
        assert dashboard_exports[0]["is_latest"] is True

    async def test_pagination(self, async_client):
        for i in range(5):
            await async_client.post("/api/v1/tasks", json={"keyword": f"分页测试_{i}"})

        resp = await async_client.get("/api/v1/tasks?page=1&page_size=3")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) <= 3
        assert data["page"] == 1
        assert data["page_size"] == 3

    async def test_filter_by_status(self, async_client):
        resp = await async_client.get("/api/v1/tasks?status=queued")
        assert resp.status_code == 200

        resp = await async_client.get("/api/v1/tasks?status=completed")
        assert resp.status_code == 200

    async def test_search_by_keyword(self, async_client):
        await async_client.post("/api/v1/tasks", json={"keyword": "unique_search_term_xyz"})
        resp = await async_client.get("/api/v1/tasks?keyword=unique_search_term_xyz")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1


@pytest.mark.asyncio
class TestSSEStream:
    @pytest.mark.skip(reason="SSE stream requires longer timeout handling")
    async def test_stream_endpoint(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "stream测试"})
        task_id = resp.json()["data"]["task_id"]

        async with async_client.stream("GET", f"/api/v1/tasks/{task_id}/stream") as resp2:
            assert resp2.status_code == 200
