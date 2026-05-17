from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from sqlalchemy import select

from app.core.database import get_session_factory
from app.models.db import Artifact, Build, Screenshot, Task
from workers.stages.runtime_support import execute_capture_flow


def test_execute_capture_flow_only_persists_successful_images(tmp_path, monkeypatch):
    task_id = str(uuid.uuid4())
    build_id = str(uuid.uuid4())
    workspace_root = tmp_path / "workspace"
    artifacts_root = tmp_path / "artifacts"
    screenshots_root = artifacts_root / "screenshots"
    screenshots_root.mkdir(parents=True, exist_ok=True)
    success_image = screenshots_root / "dashboard.png"
    success_image.write_bytes(b"fake-png")

    class _FakeRuntime:
        def __init__(self, _workspace_root: str):
            self.workspace_root = _workspace_root

        async def start_services(self, _manifest: dict) -> None:
            return None

        def stop_all(self) -> None:
            return None

    class _FakeCapture:
        def __init__(self, *args, **kwargs):
            pass

        async def capture_scenarios(self, _capture_manifest: dict, _demo_accounts: list[dict]):
            return [
                SimpleNamespace(
                    scenario_id="dashboard",
                    page_title="系统首页",
                    route="/dashboard",
                    image_path=str(success_image),
                    success=True,
                    caption="图: 系统首页",
                    elements=["首页"],
                    error=None,
                ),
                SimpleNamespace(
                    scenario_id="signoffs",
                    page_title="签收回单中心",
                    route="/signoffs",
                    image_path="",
                    success=False,
                    caption="",
                    elements=[],
                    error="blank page",
                ),
            ]

    async def _fake_sleep(_seconds: float) -> None:
        return None

    async def _fake_create_artifact(
        db_factory,
        task_id: str,
        build_id: str,
        artifact_type: str,
        artifact_name: str,
        local_path: str | None = None,
        metadata: dict | None = None,
    ):
        async with db_factory()() as db:
            artifact = Artifact(
                task_id=uuid.UUID(task_id),
                build_id=uuid.UUID(build_id),
                artifact_type=artifact_type,
                artifact_name=artifact_name,
                local_path=local_path,
                metadata_json=metadata,
            )
            db.add(artifact)
            await db.commit()
            return artifact

    monkeypatch.setattr("app.services.runtime.SandboxRuntime", _FakeRuntime)
    monkeypatch.setattr("app.services.capture.PlaywrightCapture", _FakeCapture)

    async def _run():
        session_factory = get_session_factory()
        async with session_factory() as session:
            task = Task(
                id=uuid.UUID(task_id),
                keyword="截图记录一致性测试",
                product_name="截图记录一致性测试",
                version="V1.0",
                status="running",
                current_stage="capture",
            )
            build = Build(
                id=uuid.UUID(build_id),
                task_id=task.id,
                build_no=1,
                status="running",
                current_stage="capture",
            )
            session.add_all([task, build])
            await session.commit()

        total, success_count = await execute_capture_flow(
            task_id=task_id,
            build_id=build_id,
            workspace_root=str(workspace_root),
            artifacts_root=str(artifacts_root),
            screenshots_root=str(screenshots_root),
            run_manifest={"ports": {"frontend": 3000}},
            app_manifest={"demo_accounts": [{"username": "admin"}]},
            capture_manifest={"scenarios": []},
            create_artifact=_fake_create_artifact,
            db_factory=get_session_factory,
            sleep_fn=_fake_sleep,
        )

        async with session_factory() as session:
            screenshots = (
                await session.execute(
                    select(Screenshot)
                    .where(Screenshot.task_id == uuid.UUID(task_id))
                    .order_by(Screenshot.created_at.asc())
                )
            ).scalars().all()
            artifacts = (
                await session.execute(
                    select(Artifact)
                    .where(Artifact.task_id == uuid.UUID(task_id))
                    .order_by(Artifact.created_at.asc())
                )
            ).scalars().all()

        return total, success_count, screenshots, artifacts

    total, success_count, screenshots, artifacts = asyncio.run(_run())

    assert total == 2
    assert success_count == 1
    assert len(screenshots) == 1
    assert screenshots[0].scenario_id == "dashboard"
    assert screenshots[0].image_artifact_id is not None
    assert len([item for item in artifacts if item.artifact_type == "screenshot_image"]) == 1
    assert len([item for item in artifacts if item.artifact_type == "screenshot_manifest"]) == 1

    manifest = json.loads((artifacts_root / "screenshot_manifest.json").read_text(encoding="utf-8"))
    assert len(manifest) == 2
    assert manifest[0]["success"] is True
    assert manifest[1]["success"] is False
