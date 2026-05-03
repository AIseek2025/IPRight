from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.db import Artifact, Build, Export, Screenshot, Task, TaskEvent
from app.services import TaskService
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


def _task_root(task_id: uuid.UUID) -> Path:
    return Path(settings.WORKSPACE_ROOT) / "tasks" / str(task_id)


def _slugify_name(value: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "ipright"


def _build_bundle(task: Task) -> tuple[Path, str]:
    task_root = _task_root(task.id)
    if not task_root.exists():
        raise HTTPException(status_code=404, detail={"code": "TASK_WORKSPACE_NOT_FOUND", "message": "task workspace not found"})

    downloads_dir = task_root / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify_name(task.product_name)
    version = _slugify_name(task.version or "V1.0")
    bundle_name = f"{slug}_{version}_{str(task.id)[:8]}_full_delivery.zip"
    bundle_path = downloads_dir / bundle_name

    root_prefix = Path(bundle_name.replace(".zip", ""))

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for child in sorted(task_root.iterdir(), key=lambda p: p.name):
            if child.name == "downloads":
                continue
            if child.is_dir():
                for file_path in sorted(child.rglob("*")):
                    if file_path.is_dir():
                        continue
                    arcname = root_prefix / file_path.relative_to(task_root)
                    zf.write(file_path, arcname.as_posix())
            elif child.is_file():
                arcname = root_prefix / child.relative_to(task_root)
                zf.write(child, arcname.as_posix())

    return bundle_path, bundle_name


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

    events_q = await db.execute(
        select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at.desc()).limit(20)
    )
    events = events_q.scalars().all()

    exports_q = await db.execute(select(Export).where(Export.task_id == task_id))
    exports = exports_q.scalars().all()

    screenshots_q = await db.execute(
        select(Screenshot).where(Screenshot.task_id == task_id).limit(6)
    )
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
    events_q = await db.execute(
        select(TaskEvent).where(TaskEvent.task_id == task_id).order_by(TaskEvent.created_at.asc())
    )
    events = events_q.scalars().all()
    items = [EventItem.model_validate(e) for e in events]
    return {"code": "OK", "message": "success", "data": EventListResponse(items=items).model_dump()}


@router.get("/tasks/{task_id}/artifacts")
async def get_task_artifacts(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    artifacts_q = await db.execute(
        select(Artifact).where(Artifact.task_id == task_id).order_by(Artifact.created_at.desc())
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

    bundle_path, bundle_name = _build_bundle(task)
    if not bundle_path.exists():
        raise HTTPException(status_code=404, detail={"code": "TASK_BUNDLE_NOT_FOUND", "message": "bundle generation failed"})

    return FileResponse(
        path=bundle_path,
        filename=bundle_name,
        media_type="application/zip",
    )


@router.get("/tasks/{task_id}/screenshots")
async def get_task_screenshots(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    screenshots_q = await db.execute(
        select(Screenshot).where(Screenshot.task_id == task_id).order_by(Screenshot.created_at.asc())
    )
    screenshots = screenshots_q.scalars().all()
    items = [ScreenshotItem.model_validate(s) for s in screenshots]
    return {"code": "OK", "message": "success", "data": ScreenshotListResponse(items=items).model_dump()}


@router.post("/tasks/{task_id}/retry")
async def retry_task(task_id: uuid.UUID, body: TaskRetryRequest, db: AsyncSession = Depends(get_db)) -> dict:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task does not exist"})

    service = TaskService(db)
    build = await service.start_build(task, trigger_type="retry")

    event = TaskEvent(
        task_id=task.id,
        build_id=build.id,
        event_type="task_retry",
        title="任务重试",
        detail=f"从阶段 {body.from_stage} 重试" if body.from_stage else "全局重试",
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
                fresh_task = await db.get(Task, task.id)
                if fresh_task:
                    fresh_task.status = "failed"
                    fresh_task.current_stage = body.from_stage or "planning"
                db.add(TaskEvent(
                    task_id=task.id,
                    build_id=build.id,
                    event_type="task_retry_dispatch_failed",
                    title="任务重试派发失败",
                    detail=str(exc),
                ))

    return {"code": "OK", "message": "重试已触发", "data": {"task_id": str(task_id)}}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    task = await db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail={"code": "TASK_NOT_FOUND", "message": "task does not exist"})

    task.status = "cancelled"
    event = TaskEvent(
        task_id=task.id, event_type="task_cancelled", title="任务已取消"
    )
    db.add(event)
    await db.commit()

    return {"code": "OK", "message": "任务已取消", "data": {"task_id": str(task_id)}}


@router.get("/tasks/{task_id}/stream")
async def stream_task_status(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """SSE endpoint for real-time task status updates."""
    async def event_stream():
        last_status = None
        for _ in range(300):
            task = await db.get(Task, task_id)
            if task and task.status != last_status:
                import json
                last_status = task.status
                data = json.dumps({
                    "task_id": str(task.id),
                    "status": task.status,
                    "current_stage": task.current_stage,
                }, ensure_ascii=False)
                yield f"data: {data}\n\n"

            if task and task.status in ("completed", "failed", "cancelled"):
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
