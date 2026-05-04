from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

os.environ["IPRIGHT_DATABASE_URL"] = "sqlite+aiosqlite:///./test_api.db"
os.environ["IPRIGHT_DB_TYPE"] = "sqlite"
os.environ["IPRIGHT_AUTO_DISPATCH_TASKS"] = "false"

from app.main import app
from app.core.database import Base, _get_engine, get_session_factory


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
class TestHealthEndpoint:
    async def test_health_check(self, async_client):
        resp = await async_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


@pytest.mark.asyncio
class TestTaskAPI:
    async def test_create_task_minimal(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={"keyword": "测试系统"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == "OK"
        assert "task_id" in data["data"]

    async def test_create_task_full(self, async_client):
        resp = await async_client.post("/api/v1/tasks", json={
            "keyword": "智慧仓储管理平台",
            "product_name": "仓储系统",
            "version": "V2.0",
            "industry": "物流",
            "notes": "测试",
        })
        assert resp.status_code == 201

    async def test_list_tasks(self, async_client):
        resp = await async_client.get("/api/v1/tasks?page=1&page_size=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data["data"]

    async def test_get_task_not_found(self, async_client):
        resp = await async_client.get("/api/v1/tasks/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    async def test_cancel_task_not_found(self, async_client):
        resp = await async_client.post("/api/v1/tasks/00000000-0000-0000-0000-000000000000/cancel")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestExportAPI:
    async def test_export_not_found(self, async_client):
        resp = await async_client.get("/api/v1/exports/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    async def test_download_not_found(self, async_client):
        resp = await async_client.get("/api/v1/exports/00000000-0000-0000-0000-000000000000/download")
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestTaskBundleAPI:
    async def test_task_bundle_not_found(self, async_client):
        resp = await async_client.get("/api/v1/tasks/00000000-0000-0000-0000-000000000000/bundle/download")
        assert resp.status_code == 404

    async def test_task_bundle_download(self, async_client, tmp_path, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))

        resp = await async_client.post("/api/v1/tasks", json={"keyword": "bundle测试", "product_name": "下载测试系统"})
        assert resp.status_code == 201
        task_id = resp.json()["data"]["task_id"]

        task_root = tmp_path / "tasks" / task_id
        (task_root / "workspace" / "prd").mkdir(parents=True, exist_ok=True)
        (task_root / "artifacts" / "screenshots").mkdir(parents=True, exist_ok=True)
        (task_root / "builds" / "build_001" / "exports").mkdir(parents=True, exist_ok=True)
        (task_root / "workspace" / "prd" / "product_prd.md").write_text("# PRD", encoding="utf-8")
        (task_root / "artifacts" / "screenshots" / "home.png").write_bytes(b"png-data")
        (task_root / "builds" / "build_001" / "exports" / "software_manual.docx").write_bytes(b"docx-data")

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/bundle/download")
        assert resp2.status_code == 200
        assert resp2.headers["content-type"] == "application/zip"

        bundle_path = tmp_path / "bundle.zip"
        bundle_path.write_bytes(resp2.content)
        with zipfile.ZipFile(bundle_path, "r") as zf:
            names = zf.namelist()
            assert any(name.endswith("/workspace/prd/product_prd.md") for name in names)
            assert any(name.endswith("/artifacts/screenshots/home.png") for name in names)
            assert any(name.endswith("/builds/build_001/exports/software_manual.docx") for name in names)
