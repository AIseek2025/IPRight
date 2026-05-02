from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.db import Artifact, Build, Export, Screenshot, Task, TaskEvent
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


@router.post("/tasks", status_code=status.HTTP_201_CREATED)
async def create_task(body: TaskCreateRequest, db: AsyncSession = Depends(get_db)) -> dict:
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

    event = TaskEvent(
        task_id=task.id,
        event_type="task_created",
        title=f"任务创建: {task.product_name}",
        detail=f"关键词: {body.keyword}",
    )
    db.add(event)

    await db.commit()

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

    event = TaskEvent(
        task_id=task.id,
        event_type="task_retry",
        title="任务重试",
        detail=f"从阶段 {body.from_stage} 重试" if body.from_stage else "全局重试",
    )
    db.add(event)
    await db.commit()

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
