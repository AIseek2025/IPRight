from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.db import Build, StageRun
from app.schemas.api import BuildDetailResponse, StageRunItem

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/builds")
async def list_builds(
    task_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    builds_q = await db.execute(
        select(Build).where(Build.task_id == task_id).order_by(Build.created_at.desc())
    )
    builds = builds_q.scalars().all()
    items = [
        BuildDetailResponse(
            id=str(b.id),
            build_no=b.build_no,
            status=b.status,
            current_stage=b.current_stage,
            trigger_type=b.trigger_type,
            failure_reason=b.failure_reason,
            started_at=b.started_at,
            finished_at=b.finished_at,
            stage_runs=[],
        ).model_dump()
        for b in builds
    ]
    return {"code": "OK", "message": "success", "data": items}


@router.get("/builds/{build_id}")
async def get_build(build_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    build = await db.get(Build, build_id)
    if not build:
        raise HTTPException(status_code=404, detail={"code": "BUILD_NOT_FOUND", "message": "build does not exist"})

    stages_q = await db.execute(
        select(StageRun).where(StageRun.build_id == build_id).order_by(StageRun.started_at.asc())
    )
    stages = stages_q.scalars().all()

    return {"code": "OK", "message": "success", "data": BuildDetailResponse(
        id=str(build.id),
        build_no=build.build_no,
        status=build.status,
        current_stage=build.current_stage,
        trigger_type=build.trigger_type,
        failure_reason=build.failure_reason,
        started_at=build.started_at,
        finished_at=build.finished_at,
        stage_runs=[StageRunItem.model_validate(s) for s in stages],
    ).model_dump()}
