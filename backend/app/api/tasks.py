from __future__ import annotations

import asyncio
import logging
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.state_machine import StageStatus
from app.core.database import get_db
from app.models.db import Artifact, Build, Export, Screenshot, StageRun, Task, TaskEvent
from app.services import TaskService, normalize_retry_stage
from app.schemas.api import (
    ArtifactItem,
    ArtifactListResponse,
    EventItem,
    EventListResponse,
    ExportItem,
    ExportListResponse,
    ScreenshotItem,
    ScreenshotListResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskDashboardResponse,
    TaskDetailResponse,
    TaskListItem,
    TaskListResponse,
    TaskRetryRequest,
)

router = APIRouter(prefix="/api/v1", tags=["tasks"])
logger = logging.getLogger(__name__)

_BUNDLE_EXCLUDED_DIR_NAMES = {
    "downloads",
    "node_modules",
    "dist",
    ".vite",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "runtime_logs",
}
_BUNDLE_EXCLUDED_SUFFIXES = {".pyc"}


def _task_root(task_id: uuid.UUID) -> Path:
    return Path(settings.WORKSPACE_ROOT) / "tasks" / str(task_id)


async def _resolve_effective_build_id(
    db: AsyncSession,
    task: Task,
    requested_build_id: Optional[uuid.UUID] = None,
) -> Optional[uuid.UUID]:
    if requested_build_id:
        return requested_build_id
    if task.active_build_id:
        return task.active_build_id

    latest_build_q = await db.execute(
        select(Build.id).where(Build.task_id == task.id).order_by(Build.started_at.desc()).limit(1)
    )
    return latest_build_q.scalar_one_or_none()


def _slugify_name(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "ipright"


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.resolve(strict=False).relative_to(parent.resolve(strict=False))
        return True
    except ValueError:
        return False


def _safe_task_artifact_path(task_id: uuid.UUID, local_path: str) -> Path | None:
    """Resolve an artifact file path and ensure it stays inside the task workspace."""
    if not local_path:
        return None
    task_root = _task_root(task_id).resolve()
    raw_candidate = Path(local_path).expanduser()
    if raw_candidate.is_symlink():
        logger.warning("Rejecting symlink artifact path: %s", raw_candidate)
        return None
    candidate = raw_candidate.resolve(strict=False)
    if not candidate.is_file():
        return None
    if not _is_within(candidate, task_root):
        logger.warning("Rejecting artifact path outside task workspace: %s", candidate)
        return None
    return candidate


def _bundle_target(task: Task) -> tuple[Path, str, Path]:
    task_root = _task_root(task.id)
    downloads_dir = task_root / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify_name(task.product_name)
    version = _slugify_name(task.version or "V1.0")
    bundle_name = f"{slug}_{version}_{str(task.id)[:8]}_full_delivery.zip"
    bundle_path = downloads_dir / bundle_name
    root_prefix = Path(bundle_name.replace(".zip", ""))
    return bundle_path, bundle_name, root_prefix


def _screenshot_image_url(request: Request, task_id: uuid.UUID, screenshot_id: uuid.UUID | str | None) -> Optional[str]:
    if not screenshot_id:
        return None
    return str(request.url_for("download_task_screenshot_image", task_id=str(task_id), screenshot_id=str(screenshot_id)))


def _should_skip_bundle_path(task_root: Path, file_path: Path) -> bool:
    try:
        relative_parts = file_path.resolve().relative_to(task_root.resolve()).parts
    except ValueError:
        return True
    if any(part in _BUNDLE_EXCLUDED_DIR_NAMES for part in relative_parts[:-1]):
        return True
    return file_path.suffix in _BUNDLE_EXCLUDED_SUFFIXES


def _build_bundle(task: Task) -> tuple[Path, str, Path, int]:
    task_root = _task_root(task.id)
    task_root_resolved = task_root.resolve()
    bundle_path, bundle_name, root_prefix = _bundle_target(task)
    added_files = 0

    def _safe_add(zf: zipfile.ZipFile, file_path: Path) -> None:
        nonlocal added_files
        # Reject symlinks to avoid escaping the task workspace into other
        # users' data or sensitive host files.
        if file_path.is_symlink():
            logger.warning("Skipping symlink in bundle: %s", file_path)
            return
        if _should_skip_bundle_path(task_root, file_path):
            return
        try:
            relative = file_path.resolve().relative_to(task_root_resolved)
        except ValueError:
            logger.warning("Skipping path outside task workspace: %s", file_path)
            return
        arcname = root_prefix / relative
        zf.write(file_path, arcname.as_posix())
        added_files += 1

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        if task_root.exists():
            for child in sorted(task_root.iterdir(), key=lambda p: p.name):
                if child.name == "downloads":
                    continue
                if child.is_symlink():
                    logger.warning("Skipping symlink at task root: %s", child)
                    continue
                if child.is_dir():
                    for file_path in sorted(child.rglob("*")):
                        if file_path.is_dir():
                            continue
                        _safe_add(zf, file_path)
                elif child.is_file():
                    _safe_add(zf, child)

    return bundle_path, bundle_name, root_prefix, added_files


async def _hydrate_bundle_from_artifacts(
    db: AsyncSession,
    task: Task,
    *,
    bundle_path: Path,
    root_prefix: Path,
    effective_build_id: Optional[uuid.UUID],
) -> int:
    artifacts_stmt = select(Artifact).where(Artifact.task_id == task.id)
    if effective_build_id:
        artifacts_stmt = artifacts_stmt.where(
            or_(Artifact.build_id == effective_build_id, Artifact.build_id.is_(None))
        )
    artifacts_q = await db.execute(
        artifacts_stmt.order_by(Artifact.created_at.asc(), Artifact.artifact_name.asc())
    )
    artifacts = artifacts_q.scalars().all()

    added_files = 0
    seen_paths: set[Path] = set()
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for artifact in artifacts:
            if not artifact.local_path:
                continue
            file_path = _safe_task_artifact_path(task.id, artifact.local_path)
            if file_path is None or file_path in seen_paths:
                continue
            seen_paths.add(file_path)
            safe_name = artifact.artifact_name or f"{artifact.artifact_type}.bin"
            arcname = root_prefix / "recovered" / artifact.artifact_type / safe_name
            zf.write(file_path, arcname.as_posix())
            added_files += 1
    return added_files


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(body: TaskCreateRequest, db: AsyncSession = Depends(get_db)) -> dict:
    service = TaskService(db)
    task = Task(
        id=uuid.uuid4(),
        keyword=body.keyword,
        product_name=body.product_name or body.keyword,
        version=body.version,
        industry=body.industry,
        notes=body.notes,
        status="queued",
    )
    db.add(task)
    await db.flush()

    build = await service.start_build(task, trigger_type="create")

    event = TaskEvent(
        task_id=task.id,
        event_type="task_created",
        title=f"任务创建: {task.product_name}",
        detail=f"关键词: {body.keyword}",
    )
    db.add(event)

    await db.commit()

    if settings.AUTO_DISPATCH_TASKS:
        try:
            from workers.celery_app import orchestrate_task

            orchestrate_task.delay(str(task.id), str(build.id))
        except Exception as exc:
            logger.exception("Failed to dispatch task %s build %s", task.id, build.id)
            async with db.begin():
                fresh_task = await db.get(Task, task.id)
                if fresh_task:
                    fresh_task.status = "failed"
                    fresh_task.current_stage = "planning"
                db.add(TaskEvent(
                    task_id=task.id,
                    build_id=build.id,
                    event_type="task_dispatch_failed",
                    title="任务派发失败",
                    detail=str(exc),
                ))

    return {"code": "OK", "message": "success", "data": TaskCreateResponse(
        task_id=str(task.id), status=task.status
    ).model_dump()}


@router.get("/tasks")
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    keyword: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    query = select(Task)
    count_query = select(func.count(Task.id))

    if status_filter:
        query = query.where(Task.status == status_filter)
        count_query = count_query.where(Task.status == status_filter)
    if keyword:
        query = query.where(Task.keyword.ilike(f"%{keyword}%"))
        count_query = count_query.where(Task.keyword.ilike(f"%{keyword}%"))

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Task.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    tasks = (await db.execute(query)).scalars().all()

    items = [TaskListItem.model_validate({**t.__dict__, "id": str(t.id)}) for t in tasks]
    return {"code": "OK", "message": "success", "data": TaskListResponse(
        items=items, total=total, page=page, page_size=page_size
    ).model_dump()}


@router.get("/tasks/{task_id}")
async def get_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task does not exist"})
    return {"code": "OK", "message": "success", "data": TaskDetailResponse.model_validate(task).model_dump()}


@router.get("/tasks/{task_id}/dashboard")
async def get_task_dashboard(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task does not exist"})

    effective_build_id = await _resolve_effective_build_id(db, task)

    events_q = await db.execute(
        select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at.desc()).limit(20)
    )
    events = events_q.scalars().all()

    exports_q = await db.execute(select(Export).where(Export.task_id == task_id))
    exports = exports_q.scalars().all()

    screenshots_stmt = select(Screenshot).where(Screenshot.task_id == task_id)
    if effective_build_id:
        screenshots_stmt = screenshots_stmt.where(
            or_(Screenshot.build_id == effective_build_id, Screenshot.build_id.is_(None))
        )
    screenshots_q = await db.execute(screenshots_stmt.order_by(Screenshot.created_at.desc()).limit(6))
    screenshots = screenshots_q.scalars().all()

    dashboard = TaskDashboardResponse(
        task=TaskDetailResponse.model_validate(task),
        timeline=[EventItem.model_validate(e) for e in events],
        exports=[ExportItem.model_validate(e) for e in exports],
        prd_summary=None,
        screenshot_previews=[s.scenario_id for s in screenshots],
    )
    return {"code": "OK", "message": "success", "data": dashboard.model_dump()}


@router.get("/tasks/{task_id}/timeline")
async def get_task_timeline(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task does not exist"})
    events_q = await db.execute(
        select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at.asc())
    )
    events = events_q.scalars().all()
    items = [EventItem.model_validate(e) for e in events]
    return {"code": "OK", "message": "success", "data": EventListResponse(items=items).model_dump()}


@router.get("/tasks/{task_id}/artifacts")
async def get_task_artifacts(
    task_id: uuid.UUID,
    build_id: Optional[uuid.UUID] = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> dict:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task does not exist"})

    effective_build_id = await _resolve_effective_build_id(db, task, build_id)
    artifacts_stmt = select(Artifact).where(Artifact.task_id == task_id)
    if effective_build_id:
        artifacts_stmt = artifacts_stmt.where(
            or_(Artifact.build_id == effective_build_id, Artifact.build_id.is_(None))
        )
    artifacts_q = await db.execute(
        artifacts_stmt.order_by(Artifact.created_at.desc(), Artifact.artifact_name.desc()).limit(limit)
    )
    artifacts = artifacts_q.scalars().all()
    items = [ArtifactItem.model_validate(a) for a in artifacts]
    return {"code": "OK", "message": "success", "data": ArtifactListResponse(items=items).model_dump()}


@router.get("/tasks/{task_id}/exports")
async def get_task_exports(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    exports_q = await db.execute(select(Export).where(Export.task_id == task_id))
    exports = exports_q.scalars().all()
    items = [ExportItem.model_validate(e) for e in exports]
    return {"code": "OK", "message": "success", "data": ExportListResponse(items=items).model_dump()}


@router.get("/tasks/{task_id}/bundle/download")
async def download_task_bundle(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task does not exist"})

    effective_build_id = await _resolve_effective_build_id(db, task)
    bundle_path, bundle_name, root_prefix = _bundle_target(task)
    if bundle_path.is_file() and bundle_path.stat().st_size > 0:
        try:
            with zipfile.ZipFile(bundle_path, "r") as zf:
                if zf.namelist():
                    return FileResponse(
                        path=bundle_path,
                        filename=bundle_name,
                        media_type="application/zip",
                    )
        except zipfile.BadZipFile:
            logger.warning("Ignoring corrupt cached bundle for task %s: %s", task.id, bundle_path)

    bundle_path, bundle_name, root_prefix, added_files = _build_bundle(task)
    if added_files == 0:
        added_files = await _hydrate_bundle_from_artifacts(
            db,
            task,
            bundle_path=bundle_path,
            root_prefix=root_prefix,
            effective_build_id=effective_build_id,
        )
    if not bundle_path.exists() or added_files == 0:
        raise HTTPException(
            status_code=404,
            detail={"code": "TASK_BUNDLE_NOT_FOUND", "message": "bundle generation failed"},
        )

    return FileResponse(
        path=bundle_path,
        filename=bundle_name,
        media_type="application/zip",
    )


@router.get("/tasks/{task_id}/screenshots")
async def get_task_screenshots(
    task_id: uuid.UUID,
    request: Request,
    build_id: Optional[uuid.UUID] = Query(default=None),
    limit: int = Query(24, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> dict:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task does not exist"})

    effective_build_id = await _resolve_effective_build_id(db, task, build_id)
    screenshots_stmt = select(Screenshot).where(Screenshot.task_id == task_id)
    if effective_build_id:
        screenshots_stmt = screenshots_stmt.where(
            or_(Screenshot.build_id == effective_build_id, Screenshot.build_id.is_(None))
        )
    screenshots_q = await db.execute(
        screenshots_stmt.order_by(Screenshot.created_at.desc(), Screenshot.scenario_id.desc()).limit(limit)
    )
    screenshots = list(reversed(screenshots_q.scalars().all()))
    items = []
    for screenshot in screenshots:
        item = ScreenshotItem.model_validate(screenshot)
        item.image_url = _screenshot_image_url(request, task_id, screenshot.id) if request else None
        items.append(item)
    return {"code": "OK", "message": "success", "data": ScreenshotListResponse(items=items).model_dump()}


@router.get("/tasks/{task_id}/screenshots/{screenshot_id}/image", name="download_task_screenshot_image")
async def download_task_screenshot_image(
    task_id: uuid.UUID,
    screenshot_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    screenshot = await db.get(Screenshot, screenshot_id)
    if not screenshot or screenshot.task_id != task_id:
        raise HTTPException(status_code=404, detail={"code": "SCREENSHOT_NOT_FOUND", "message": "screenshot does not exist"})
    if not screenshot.image_artifact_id:
        raise HTTPException(status_code=404, detail={"code": "SCREENSHOT_IMAGE_MISSING", "message": "screenshot image does not exist"})

    artifact = await db.get(Artifact, screenshot.image_artifact_id)
    if not artifact or not artifact.local_path:
        raise HTTPException(status_code=404, detail={"code": "SCREENSHOT_IMAGE_MISSING", "message": "screenshot image does not exist"})

    file_path = _safe_task_artifact_path(task_id, artifact.local_path)
    if file_path is None:
        raise HTTPException(status_code=404, detail={"code": "SCREENSHOT_IMAGE_MISSING", "message": "screenshot image file not found"})

    return FileResponse(path=file_path, filename=artifact.artifact_name or file_path.name, media_type=artifact.mime_type or "image/png")


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: uuid.UUID, body: TaskRetryRequest, db: AsyncSession = Depends(get_db)) -> dict:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task does not exist"})

    retry_stage = normalize_retry_stage(body.from_stage)
    if body.from_stage and retry_stage is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_RETRY_STAGE",
                "message": f"unsupported retry stage: {body.from_stage}",
            },
        )

    active_build = task.active_build_id
    if active_build:
        active_build_obj = await db.get(Build, active_build)
        if active_build_obj and active_build_obj.status in {StageStatus.QUEUED.value, StageStatus.RUNNING.value}:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "BUILD_ALREADY_RUNNING",
                    "message": "当前已有运行中的构建，请等待完成后再重试",
                },
            )

    service = TaskService(db)
    build = await service.start_build(task, trigger_type="retry", from_stage=retry_stage)

    event = TaskEvent(
        task_id=task.id,
        build_id=build.id,
        event_type="task_retry",
        title="任务重试",
        detail=f"从阶段 {retry_stage.value} 重试" if retry_stage else "全局重试",
    )
    db.add(event)
    await db.commit()

    if settings.AUTO_DISPATCH_TASKS:
        try:
            from workers.celery_app import orchestrate_task

            orchestrate_task.delay(str(task.id), str(build.id))
        except Exception as exc:
            logger.exception("Failed to redispatch task %s build %s", task.id, build.id)
            async with db.begin():
                now = datetime.now(timezone.utc)
                fresh_task = await db.get(Task, task.id)
                fresh_build = await db.get(Build, build.id)
                if fresh_build:
                    fresh_build.status = StageStatus.FAILED.value
                    fresh_build.current_stage = StageStatus.FAILED.value
                    fresh_build.failure_reason = str(exc)
                    fresh_build.finished_at = now
                if fresh_task:
                    fresh_task.status = "failed"
                    fresh_task.current_stage = retry_stage.value if retry_stage else "planning"
                    fresh_task.updated_at = now
                    if fresh_task.active_build_id == build.id:
                        fresh_task.active_build_id = None
                db.add(TaskEvent(
                    task_id=task.id,
                    build_id=build.id,
                    event_type="task_retry_dispatch_failed",
                    title="任务重试派发失败",
                    detail=f"{type(exc).__name__}: {exc}",
                ))

    return {"code": "OK", "message": "重试已触发", "data": {"task_id": str(task_id)}}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task does not exist"})

    active_build_id = task.active_build_id
    now = datetime.now(timezone.utc)
    builds = (
        await db.execute(
            select(Build).where(
                Build.task_id == task.id,
                Build.status.in_([StageStatus.QUEUED.value, StageStatus.RUNNING.value]),
            )
        )
    ).scalars().all()
    for active_build in builds:
        active_build.status = "cancelled"
        active_build.failure_reason = "task cancelled by user"
        active_build.finished_at = now

        stage_runs = (
            await db.execute(
                select(StageRun).where(StageRun.build_id == active_build.id)
            )
        ).scalars().all()
        for stage_run in stage_runs:
            if stage_run.status in {StageStatus.QUEUED.value, StageStatus.RUNNING.value}:
                stage_run.status = "cancelled"
                stage_run.failure_reason = "task cancelled by user"
                stage_run.finished_at = now

    task.status = "cancelled"
    task.active_build_id = None
    task.updated_at = now
    event = TaskEvent(
        task_id=task.id,
        build_id=active_build_id,
        event_type="task_cancelled",
        title="任务已取消",
    )
    db.add(event)
    await db.commit()

    return {"code": "OK", "message": "任务已取消", "data": {"task_id": str(task_id)}}


@router.get("/tasks/{task_id}/stream")
async def stream_task_status(task_id: uuid.UUID):
    """SSE endpoint for real-time task status updates."""
    import json

    from app.core.database import get_session_factory

    async def event_stream():
        last_status = None
        last_stage = None
        seen_event_ids: set[str] = set()
        factory = get_session_factory()
        for _ in range(300):
            # Use an independent short-lived session per poll so we never read
            # from a stale identity-mapped cache, which would prevent the SSE
            # client from observing real-time status transitions.
            async with factory() as session:
                task = await session.get(Task, task_id)
                if task is None:
                    data = json.dumps(
                        {"task_id": str(task_id), "error": "TASK_NOT_FOUND"},
                        ensure_ascii=False,
                    )
                    yield f"event: error\ndata: {data}\n\n"
                    return
                current_status = task.status
                current_stage = task.current_stage
                events_q = await session.execute(
                    select(TaskEvent)
                    .where(TaskEvent.task_id == task_id)
                    .order_by(TaskEvent.created_at.desc())
                    .limit(20)
                )
                recent_events = list(reversed(events_q.scalars().all()))

            if current_status != last_status or current_stage != last_stage:
                last_status = current_status
                last_stage = current_stage
                data = json.dumps(
                    {
                        "task_id": str(task_id),
                        "status": current_status,
                        "current_stage": current_stage,
                    },
                    ensure_ascii=False,
                )
                yield f"event: status\ndata: {data}\n\n"

            for event in recent_events:
                event_id = str(event.id)
                if event_id in seen_event_ids:
                    continue
                seen_event_ids.add(event_id)
                payload = json.dumps(
                    {
                        "id": event_id,
                        "event_type": event.event_type,
                        "title": event.title,
                        "detail": event.detail,
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                    },
                    ensure_ascii=False,
                )
                yield f"event: task_event\ndata: {payload}\n\n"

            if current_status in ("completed", "failed", "cancelled"):
                break

            await asyncio.sleep(2)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
