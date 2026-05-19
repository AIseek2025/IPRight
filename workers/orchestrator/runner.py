from __future__ import annotations

import contextlib
import fcntl
import json
import logging
import os
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
    TOPLEVEL_TO_STAGE,
    TopLevelStatus,
)
from app.models.db import Build, StageRun, Task, TaskEvent
from app.services import TaskService
from workers.orchestrator.async_runner import run_async

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
    with _acquire_build_lock(build_id) as acquired:
        if not acquired:
            logger.warning("Build %s is already running in another worker; skipping duplicate dispatch", build_id)
            return
        # Submit the async pipeline to the per-process shared event loop so we
        # neither create a fresh loop per task (which throws away the
        # SQLAlchemy engine + connection pool) nor block ``asyncio.run`` from
        # being re-entered by sub-handlers.
        run_async(_async_run_pipeline(task_id, build_id))


@contextlib.contextmanager
def _acquire_build_lock(build_id: uuid.UUID):
    lock_path = f"/tmp/ipright-build-{build_id}.lock"
    os.makedirs("/tmp", exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            lock_file.write(str(build_id))
            lock_file.flush()
            yield True
        except BlockingIOError:
            yield False
        finally:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


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

        if task.active_build_id != build.id:
            logger.info(
                "Build %s is no longer active for task %s (active=%s); aborting dispatch",
                build.id,
                task_id,
                task.active_build_id,
            )
            if build.status in {StageStatus.QUEUED.value, StageStatus.RUNNING.value}:
                build.status = "aborted"
                build.current_stage = "aborted"
                build.failure_reason = "Superseded by a newer active build"
                await db.commit()
            return

        current_status = TopLevelStatus(task.status)

        while current_status in STAGE_TRANSITIONS:
            await db.refresh(task)
            await db.refresh(build)
            if task.active_build_id != build.id:
                logger.info(
                    "Build %s lost active ownership for task %s before stage transition (active=%s); aborting",
                    build.id,
                    task_id,
                    task.active_build_id,
                )
                if build.status in {StageStatus.QUEUED.value, StageStatus.RUNNING.value}:
                    build.status = "aborted"
                    build.current_stage = "aborted"
                    build.failure_reason = "Superseded by a newer active build"
                    await db.commit()
                return

            next_status = STAGE_TRANSITIONS[current_status]
            stage_name = TOPLEVEL_TO_STAGE.get(next_status)

            if stage_name and stage_name in STAGE_HANDLERS:
                logger.info(f"Running stage {stage_name.value} for task {task_id}")
                sr = await service.create_stage_run(build, stage_name.value)
                task.status = next_status.value
                task.current_stage = next_status.value
                await service.mark_build_running(build, stage_name.value)
                await service.log_event(
                    task_id=task.id,
                    build_id=build.id,
                    event_type="stage_started",
                    title=f"{stage_name.value} 阶段开始",
                    detail=f"任务进入 {stage_name.value}，正在执行 {next_status.value}",
                    payload_json={
                        "stage_name": stage_name.value,
                        "attempt_no": sr.attempt_no,
                        "status": next_status.value,
                    },
                )
                await db.commit()

                try:
                    context = StageContext(
                        task_id=str(task_id),
                        build_id=str(build_id),
                        db_factory=get_session_factory,
                    )
                    result = await STAGE_HANDLERS[stage_name](context)
                    if result.success:
                        await service.complete_stage_run(sr)
                        await service.log_event(
                            task_id=task.id,
                            build_id=build.id,
                            event_type="stage_succeeded",
                            title=f"{stage_name.value} 阶段完成",
                            detail=f"{stage_name.value} 已完成，准备进入下一阶段",
                            payload_json={
                                "stage_name": stage_name.value,
                                "attempt_no": sr.attempt_no,
                                "metadata": result.metadata or {},
                            },
                        )
                    else:
                        await service.fail_stage_run(sr, result.error or "unknown error")
                        await service.mark_build_failed(build, result.error or "unknown error")
                        await service.log_event(
                            task_id=task.id,
                            build_id=build.id,
                            event_type="stage_failed",
                            title=f"{stage_name.value} 阶段失败",
                            detail=result.error or "unknown error",
                            payload_json={
                                "stage_name": stage_name.value,
                                "attempt_no": sr.attempt_no,
                            },
                        )
                        await service.mark_failed(task, result.error or "unknown error")
                        await db.commit()
                        return
                except Exception as e:
                    logger.exception(f"Stage {stage_name.value} failed")
                    await service.fail_stage_run(sr, str(e))
                    await service.mark_build_failed(build, str(e))
                    await service.log_event(
                        task_id=task.id,
                        build_id=build.id,
                        event_type="stage_failed",
                        title=f"{stage_name.value} 阶段异常",
                        detail=str(e),
                        payload_json={
                            "stage_name": stage_name.value,
                            "attempt_no": sr.attempt_no,
                        },
                    )
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
