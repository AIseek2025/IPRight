from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session_factory
from app.core.state_machine import (
    STAGE_TRANSITIONS,
    StageName,
    StageStatus,
    TopLevelStatus,
)
from app.models.db import Build, StageRun, Task, TaskEvent
from app.services import TaskService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

logger = logging.getLogger(__name__)

STAGE_HANDLERS: dict[StageName, Callable] = {}


def register_stage(stage: StageName):
    def decorator(fn: Callable):
        STAGE_HANDLERS[stage] = fn
        return fn
    return decorator


def run_full_pipeline(task_id: uuid.UUID, build_id: uuid.UUID) -> None:
    asyncio.run(_async_run_pipeline(task_id, build_id))


async def _async_run_pipeline(task_id: uuid.UUID, build_id: uuid.UUID) -> None:
    factory = get_session_factory()
    async with factory() as db:
        service = TaskService(db)

        task = await db.get(Task, task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return

        build = await db.get(Build, build_id)
        if not build:
            logger.error(f"Build {build_id} not found")
            return

        current_status = TopLevelStatus(task.status)

        while current_status in STAGE_TRANSITIONS:
            next_status = STAGE_TRANSITIONS[current_status]
            stage_name = _status_to_stage(next_status)

            if stage_name and stage_name in STAGE_HANDLERS:
                logger.info(f"Running stage {stage_name.value} for task {task_id}")
                sr = await service.create_stage_run(build, stage_name.value)
                task.status = next_status.value
                task.current_stage = next_status.value
                await service.mark_build_running(build, stage_name.value)
                await db.flush()

                try:
                    context = StageContext(
                        task_id=str(task_id),
                        build_id=str(build_id),
                        db_factory=get_session_factory,
                    )
                    result = await STAGE_HANDLERS[stage_name](context)
                    if result.success:
                        await service.complete_stage_run(sr)
                    else:
                        await service.fail_stage_run(sr, result.error or "unknown error")
                        await service.mark_build_failed(build, result.error or "unknown error")
                        await service.mark_failed(task, result.error or "unknown error")
                        await db.commit()
                        return
                except Exception as e:
                    logger.exception(f"Stage {stage_name.value} failed")
                    await service.fail_stage_run(sr, str(e))
                    await service.mark_build_failed(build, str(e))
                    await service.mark_failed(task, str(e))
                    await db.commit()
                    return

            current_status = next_status
            if current_status == TopLevelStatus.COMPLETED:
                await service.mark_build_completed(build)
                await service.mark_completed(task)
                await db.commit()
                return

            await db.commit()


def _status_to_stage(status: TopLevelStatus) -> StageName | None:
    mapping = {
        TopLevelStatus.PLANNING: StageName.PLAN,
        TopLevelStatus.CODING: None,
        TopLevelStatus.BUILDING: StageName.BUILD,
        TopLevelStatus.RUNNING: StageName.VERIFY_RUN,
        TopLevelStatus.CAPTURING: StageName.CAPTURE,
        TopLevelStatus.WRITING_MANUAL: StageName.COMPOSE_MANUAL,
        TopLevelStatus.WRITING_CODE_BOOK: StageName.COMPOSE_CODE_BOOK,
        TopLevelStatus.PUBLISHING: StageName.PUBLISH,
    }
    return mapping.get(status)


@dataclass
class StageContext:
    task_id: str
    build_id: str
    db_factory: Any


@dataclass
class StageResult:
    success: bool
    error: str | None = None
    artifacts: list[dict] | None = None
    metadata: dict | None = None
