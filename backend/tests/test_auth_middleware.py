from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

os.environ.setdefault("IPRIGHT_DATABASE_URL", "sqlite+aiosqlite:///./test_api.db")
os.environ.setdefault("IPRIGHT_DB_TYPE", "sqlite")
os.environ.setdefault("IPRIGHT_AUTO_DISPATCH_TASKS", "false")

from app.main import app  # noqa: E402
from app.core.database import Base, _get_engine  # noqa: E402


@pytest_asyncio.fixture(scope="module")
async def _init_db():
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def async_client(_init_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
class TestAuthMiddleware:
    async def test_health_is_public(self, async_client):
        resp = await async_client.get("/health", headers={"Authorization": ""})
        assert resp.status_code == 200

    async def test_docs_is_public(self, async_client):
        resp = await async_client.get("/openapi.json", headers={"Authorization": ""})
        assert resp.status_code == 200

    async def test_business_api_rejects_missing_token(self, async_client):
        resp = await async_client.get("/api/v1/tasks", headers={"Authorization": ""})
        assert resp.status_code == 401
        body = resp.json()
        assert body["code"] == "UNAUTHORIZED"

    async def test_business_api_rejects_wrong_token(self, async_client):
        resp = await async_client.get(
            "/api/v1/tasks",
            headers={"Authorization": "Bearer not-the-right-token"},
        )
        assert resp.status_code == 401

    async def test_business_api_accepts_valid_token(self, async_client):
        resp = await async_client.get("/api/v1/tasks")
        assert resp.status_code == 200

    async def test_admin_requires_admin_token(self, async_client):
        # API token is not enough for admin scope
        api_token = os.environ["IPRIGHT_API_TOKEN"]
        resp = await async_client.get(
            "/api/v1/admin/builds?task_id=00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {api_token}"},
        )
        assert resp.status_code == 401

        admin_token = os.environ["IPRIGHT_ADMIN_TOKEN"]
        resp2 = await async_client.get(
            "/api/v1/admin/builds?task_id=00000000-0000-0000-0000-000000000000",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # The handler returns 200 with an empty list when no builds exist; the
        # important thing is auth no longer rejects it.
        assert resp2.status_code == 200

    async def test_sse_accepts_query_token(self, async_client):
        api_token = os.environ["IPRIGHT_API_TOKEN"]
        resp = await async_client.get(
            f"/api/v1/tasks/00000000-0000-0000-0000-000000000000/stream?token={api_token}",
            headers={"Authorization": ""},
        )
        # The endpoint will emit an "event: error" frame for the missing
        # task and then close, but the auth middleware must let it through.
        assert resp.status_code == 200

    async def test_sse_rejects_missing_token(self, async_client):
        resp = await async_client.get(
            "/api/v1/tasks/00000000-0000-0000-0000-000000000000/stream",
            headers={"Authorization": ""},
        )
        assert resp.status_code == 401

    async def test_export_download_path_is_public(self, async_client):
        # Bogus export id; we only care that auth is bypassed (handler will
        # return its own 404).
        resp = await async_client.get(
            "/api/v1/exports/00000000-0000-0000-0000-000000000000/download",
            headers={"Authorization": ""},
        )
        assert resp.status_code != 401
