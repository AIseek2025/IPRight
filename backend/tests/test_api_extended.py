from __future__ import annotations

import os
import sys
import uuid
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
from app.core.database import Base, _get_engine
from app.models.db import Build, Task
from app.services import TaskService


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
        assert resp2.status_code == 200

        resp3 = await async_client.post(f"/api/v1/tasks/{task_id}/retry", json={"from_stage": "capturing"})
        assert resp3.status_code == 200

    async def test_retry_creates_new_build_and_switches_active_build(self, async_client):
        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "二次构建测试"})
        assert create_resp.status_code == 201
        task_id = create_resp.json()["data"]["task_id"]

        retry_resp = await async_client.post(
            f"/api/v1/tasks/{task_id}/retry",
            json={"from_stage": "capturing"},
        )
        assert retry_resp.status_code == 200

        from app.core.database import get_session_factory

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
