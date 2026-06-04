from __future__ import annotations

import os
import sys
import uuid
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
from app.models.db import Artifact, Build, Export, Screenshot, Task


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

    async def test_download_export_falls_back_to_artifact_local_path(self, async_client, tmp_path, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path / "workspace_root"))

        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "导出回退测试", "product_name": "导出回退系统"})
        assert create_resp.status_code == 201
        task_id = uuid.UUID(create_resp.json()["data"]["task_id"])

        workspace_root = tmp_path / "workspace_root"
        artifact_file = workspace_root / "tasks" / str(task_id) / "artifacts" / "software_manual.docx"
        artifact_file.parent.mkdir(parents=True, exist_ok=True)
        artifact_file.write_bytes(b"docx-data")

        async with get_session_factory()() as session:
            task = await session.get(Task, task_id)
            assert task is not None
            build = Build(task_id=task.id, build_no=2, status="completed", trigger_type="retry")
            session.add(build)
            await session.flush()
            task.active_build_id = build.id

            artifact = Artifact(
                task_id=task.id,
                build_id=build.id,
                artifact_type="software_manual_docx",
                artifact_name="software_manual.docx",
                local_path=str(artifact_file),
            )
            session.add(artifact)
            await session.flush()

            export = Export(
                task_id=task.id,
                build_id=build.id,
                artifact_id=artifact.id,
                export_type="manual_docx",
                file_name="software_manual.docx",
                status="ready",
                download_url=f"/api/v1/exports/{uuid.uuid4()}/download",
            )
            session.add(export)
            await session.commit()
            export_id = export.id

        resp = await async_client.get(f"/api/v1/exports/{export_id}/download")
        assert resp.status_code == 200
        assert resp.content == b"docx-data"

    async def test_download_export_rejects_symlink_artifact_local_path(self, async_client, tmp_path, monkeypatch):
        from app.core.config import settings

        workspace_root = tmp_path / "workspace_root"
        monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(workspace_root))

        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "导出软链测试", "product_name": "导出软链系统"})
        assert create_resp.status_code == 201
        task_id = uuid.UUID(create_resp.json()["data"]["task_id"])

        task_dir = workspace_root / "tasks" / str(task_id)
        real_file = task_dir / "artifacts" / "real_manual.docx"
        symlink_file = task_dir / "artifacts" / "software_manual.docx"
        real_file.parent.mkdir(parents=True, exist_ok=True)
        real_file.write_bytes(b"docx-data")
        symlink_file.symlink_to(real_file)

        async with get_session_factory()() as session:
            task = await session.get(Task, task_id)
            assert task is not None
            build = Build(task_id=task.id, build_no=2, status="completed", trigger_type="retry")
            session.add(build)
            await session.flush()
            task.active_build_id = build.id

            artifact = Artifact(
                task_id=task.id,
                build_id=build.id,
                artifact_type="software_manual_docx",
                artifact_name="software_manual.docx",
                local_path=str(symlink_file),
            )
            session.add(artifact)
            await session.flush()

            export = Export(
                task_id=task.id,
                build_id=build.id,
                artifact_id=artifact.id,
                export_type="manual_docx",
                file_name="software_manual.docx",
                status="ready",
                download_url=f"/api/v1/exports/{uuid.uuid4()}/download",
            )
            session.add(export)
            await session.commit()
            export_id = export.id

        resp = await async_client.get(f"/api/v1/exports/{export_id}/download")
        assert resp.status_code == 404
        detail = resp.json()["detail"] if "detail" in resp.json() else resp.json()
        assert detail["code"] == "EXPORT_FILE_MISSING"


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

    async def test_task_bundle_skips_transient_large_directories(self, async_client, tmp_path, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))

        resp = await async_client.post("/api/v1/tasks", json={"keyword": "bundle瘦身测试", "product_name": "bundle瘦身系统"})
        assert resp.status_code == 201
        task_id = resp.json()["data"]["task_id"]

        task_root = tmp_path / "tasks" / task_id
        (task_root / "workspace" / "app" / "frontend" / "src").mkdir(parents=True, exist_ok=True)
        (task_root / "workspace" / "app" / "frontend" / "node_modules" / "pkg").mkdir(parents=True, exist_ok=True)
        (task_root / "workspace" / "app" / "frontend" / "dist").mkdir(parents=True, exist_ok=True)
        (task_root / "workspace" / "artifacts" / "runtime_logs").mkdir(parents=True, exist_ok=True)
        (task_root / "artifacts" / "screenshots").mkdir(parents=True, exist_ok=True)

        (task_root / "workspace" / "app" / "frontend" / "src" / "main.tsx").write_text("console.log('ok')", encoding="utf-8")
        (task_root / "workspace" / "app" / "frontend" / "node_modules" / "pkg" / "index.js").write_text("ignored", encoding="utf-8")
        (task_root / "workspace" / "app" / "frontend" / "dist" / "bundle.js").write_text("ignored", encoding="utf-8")
        (task_root / "workspace" / "artifacts" / "runtime_logs" / "frontend.log").write_text("ignored", encoding="utf-8")
        (task_root / "artifacts" / "screenshots" / "home.png").write_bytes(b"png-data")

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/bundle/download")
        assert resp2.status_code == 200

        bundle_path = tmp_path / "trimmed_bundle.zip"
        bundle_path.write_bytes(resp2.content)
        with zipfile.ZipFile(bundle_path, "r") as zf:
            names = zf.namelist()
            assert any(name.endswith("/workspace/app/frontend/src/main.tsx") for name in names)
            assert not any("/node_modules/" in name for name in names)
            assert not any("/dist/" in name for name in names)
            assert not any("/runtime_logs/" in name for name in names)

    async def test_task_bundle_falls_back_to_artifact_local_paths(self, async_client, tmp_path, monkeypatch):
        from app.core.config import settings

        workspace_root = tmp_path / "workspace_root"
        monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(workspace_root))

        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "bundle回退测试", "product_name": "bundle回退系统"})
        assert create_resp.status_code == 201
        task_id = uuid.UUID(create_resp.json()["data"]["task_id"])

        recovered_file = workspace_root / "tasks" / str(task_id) / "artifacts" / "software_manual.docx"
        recovered_file.parent.mkdir(parents=True, exist_ok=True)
        recovered_file.write_bytes(b"legacy-docx")

        async with get_session_factory()() as session:
            task = await session.get(Task, task_id)
            assert task is not None
            build = Build(task_id=task.id, build_no=2, status="completed", trigger_type="retry")
            session.add(build)
            await session.flush()
            task.active_build_id = build.id

            artifact = Artifact(
                task_id=task.id,
                build_id=build.id,
                artifact_type="software_manual_docx",
                artifact_name="software_manual.docx",
                local_path=str(recovered_file),
            )
            session.add(artifact)
            await session.commit()

        resp = await async_client.get(f"/api/v1/tasks/{task_id}/bundle/download")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

        bundle_path = tmp_path / "recovered_bundle.zip"
        bundle_path.write_bytes(resp.content)
        with zipfile.ZipFile(bundle_path, "r") as zf:
            names = zf.namelist()
            assert any(name.endswith("software_manual.docx") for name in names)

    async def test_task_bundle_rejects_symlink_artifact_local_path(self, async_client, tmp_path, monkeypatch):
        from app.core.config import settings

        workspace_root = tmp_path / "workspace_root"
        monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(workspace_root))

        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "bundle软链测试", "product_name": "bundle软链系统"})
        assert create_resp.status_code == 201
        task_id = uuid.UUID(create_resp.json()["data"]["task_id"])

        task_dir = workspace_root / "tasks" / str(task_id)
        real_file = task_dir / "artifacts" / "real_manual.docx"
        symlink_file = task_dir / "artifacts" / "software_manual.docx"
        real_file.parent.mkdir(parents=True, exist_ok=True)
        real_file.write_bytes(b"legacy-docx")
        symlink_file.symlink_to(real_file)

        async with get_session_factory()() as session:
            task = await session.get(Task, task_id)
            assert task is not None
            build = Build(task_id=task.id, build_no=2, status="completed", trigger_type="retry")
            session.add(build)
            await session.flush()
            task.active_build_id = build.id

            artifact = Artifact(
                task_id=task.id,
                build_id=build.id,
                artifact_type="software_manual_docx",
                artifact_name="software_manual.docx",
                local_path=str(symlink_file),
            )
            session.add(artifact)
            await session.commit()

        resp = await async_client.get(f"/api/v1/tasks/{task_id}/bundle/download")
        assert resp.status_code == 200

        bundle_path = tmp_path / "symlink_filtered_bundle.zip"
        bundle_path.write_bytes(resp.content)
        with zipfile.ZipFile(bundle_path, "r") as zf:
            names = zf.namelist()
            assert not any(name.endswith("software_manual.docx") for name in names)


@pytest.mark.asyncio
class TestTaskScreenshotAPI:
    async def test_task_screenshots_include_preview_url_and_image_download(self, async_client, tmp_path, monkeypatch):
        from app.core.config import settings

        workspace_root = tmp_path / "workspace_root"
        monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(workspace_root))

        create_resp = await async_client.post("/api/v1/tasks", json={"keyword": "截图预览测试", "product_name": "截图预览系统"})
        assert create_resp.status_code == 201
        task_id = uuid.UUID(create_resp.json()["data"]["task_id"])

        screenshot_file = workspace_root / "tasks" / str(task_id) / "artifacts" / "screenshots" / "dashboard.png"
        screenshot_file.parent.mkdir(parents=True, exist_ok=True)
        screenshot_file.write_bytes(b"png-data")

        async with get_session_factory()() as session:
            task = await session.get(Task, task_id)
            assert task is not None
            build = Build(task_id=task.id, build_no=2, status="completed", trigger_type="retry")
            session.add(build)
            await session.flush()
            task.active_build_id = build.id

            artifact = Artifact(
                task_id=task.id,
                build_id=build.id,
                artifact_type="screenshot_image",
                artifact_name="dashboard.png",
                local_path=str(screenshot_file),
                mime_type="image/png",
            )
            session.add(artifact)
            await session.flush()

            screenshot = Screenshot(
                task_id=task.id,
                build_id=build.id,
                scenario_id="dashboard",
                page_title="系统首页",
                route="/dashboard",
                image_artifact_id=artifact.id,
                caption="图: 系统首页",
            )
            session.add(screenshot)
            await session.commit()

        list_resp = await async_client.get(f"/api/v1/tasks/{task_id}/screenshots")
        assert list_resp.status_code == 200
        payload = list_resp.json()["data"]["items"]
        assert len(payload) == 1
        assert payload[0]["image_artifact_id"]
        assert payload[0]["image_url"].endswith(f"/api/v1/tasks/{task_id}/screenshots/{payload[0]['id']}/image")

        image_resp = await async_client.get(payload[0]["image_url"])
        assert image_resp.status_code == 200
        assert image_resp.content == b"png-data"

    async def test_task_bundle_reuses_existing_download(self, async_client, tmp_path, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "WORKSPACE_ROOT", str(tmp_path))

        resp = await async_client.post("/api/v1/tasks", json={"keyword": "bundle缓存测试", "product_name": "缓存下载系统"})
        assert resp.status_code == 201
        task_id = resp.json()["data"]["task_id"]

        task_root = tmp_path / "tasks" / task_id
        downloads_dir = task_root / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)
        existing_bundle = downloads_dir / f"缓存下载系统_V1_0_{task_id[:8]}_full_delivery.zip"
        with zipfile.ZipFile(existing_bundle, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("cached/readme.txt", "cached bundle")

        resp2 = await async_client.get(f"/api/v1/tasks/{task_id}/bundle/download")
        assert resp2.status_code == 200
        assert resp2.headers["content-type"] == "application/zip"

        bundle_path = tmp_path / "cached_bundle.zip"
        bundle_path.write_bytes(resp2.content)
        with zipfile.ZipFile(bundle_path, "r") as zf:
            assert zf.read("cached/readme.txt") == b"cached bundle"
