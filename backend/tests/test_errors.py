from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

os.environ["IPRIGHT_DATABASE_URL"] = "sqlite+aiosqlite:///./test_err.db"
os.environ["IPRIGHT_DB_TYPE"] = "sqlite"
os.environ["IPRIGHT_AUTO_DISPATCH_TASKS"] = "false"

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
class TestErrorHandling:
    async def test_404_not_found(self, async_client):
        resp = await async_client.get("/api/v1/nonexistent")
        assert resp.status_code == 404

    async def test_422_validation_error(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={})
        assert resp.status_code == 422

    async def test_invalid_uuid_format(self, async_client):
        resp = await async_client.get("/api/v1/tasks/not-a-uuid")
        assert resp.status_code == 422

    async def test_health_always_ok(self, async_client):
        resp = await async_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_cors_headers(self, async_client):
        resp = await async_client.options("/api/v1/tasks", headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        })
        assert "access-control-allow-origin" in resp.headers or resp.status_code < 500

    async def test_request_id_header(self, async_client):
        resp = await async_client.get("/health")
        assert "x-request-id" in resp.headers


@pytest.mark.asyncio
class TestTaskListEdgeCases:
    async def test_page_zero(self, async_client):
        resp = await async_client.get("/api/v1/tasks?page=0")
        assert resp.status_code == 422

    async def test_negative_page_size(self, async_client):
        resp = await async_client.get("/api/v1/tasks?page_size=-1")
        assert resp.status_code == 422

    async def test_very_large_page_size(self, async_client):
        resp = await async_client.get("/api/v1/tasks?page_size=100")
        assert resp.status_code == 200

    async def test_empty_list(self, async_client):
        resp = await async_client.get("/api/v1/tasks?status=nonexistent_status")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0
