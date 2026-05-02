from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

os.environ["IPRIGHT_DATABASE_URL"] = "sqlite+aiosqlite:///./test_api.db"
os.environ["IPRIGHT_DB_TYPE"] = "sqlite"

from app.main import app
from app.core.database import Base, _get_engine


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
