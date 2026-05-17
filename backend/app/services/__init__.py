from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state_machine import (
    STAGE_TRANSITIONS,
    StageStatus,
    TopLevelStatus,
)
from app.models.db import Build, StageRun, Task, TaskEvent


class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def transition(self, task: Task, target: TopLevelStatus) -> None:
        old_status = task.status
        task.status = target.value
        task.current_stage = target.value
        task.updated_at = datetime.utcnow()

        event = TaskEvent(
            task_id=task.id,
            event_type=f"status_{target.value}",
            title=f"阶段切换: {old_status} -> {target.value}",
            detail=f"任务 {task.product_name} 进入 {target.value} 阶段",
        )
        self.db.add(event)
        await self.db.flush()

    async def start_build(self, task: Task, trigger_type: str = "create") -> Build:
        stale_builds_q = await self.db.execute(
            select(Build).where(
                Build.task_id == task.id,
                Build.status.in_([StageStatus.QUEUED.value, StageStatus.RUNNING.value]),
            )
        )
        stale_builds = stale_builds_q.scalars().all()
        for stale_build in stale_builds:
            stale_build.status = "aborted"
            stale_build.current_stage = "aborted"
            stale_build.failure_reason = "Superseded by a newer build retry"
            stale_build.finished_at = datetime.utcnow()

        last_build_q = await self.db.execute(
            select(Build).where(Build.task_id == task.id).order_by(Build.build_no.desc()).limit(1)
        )
        last_build = last_build_q.scalar()
        build_no = (last_build.build_no + 1) if last_build else 1
        build_id = uuid.uuid4()

        build = Build(
            id=build_id,
            task_id=task.id,
            build_no=build_no,
            status="queued",
            trigger_type=trigger_type,
            current_stage="plan",
        )
        self.db.add(build)
        task.active_build_id = build_id
        task.status = TopLevelStatus.QUEUED.value
        task.current_stage = TopLevelStatus.QUEUED.value
        task.updated_at = datetime.utcnow()
        await self.db.flush()
        return build

    async def create_stage_run(self, build: Build, stage_name: str) -> StageRun:
        last_q = await self.db.execute(
            select(StageRun)
            .where(StageRun.build_id == build.id, StageRun.stage_name == stage_name)
            .order_by(StageRun.attempt_no.desc())
            .limit(1)
        )
        last = last_q.scalar()
        attempt_no = (last.attempt_no + 1) if last else 1

        sr = StageRun(
            build_id=build.id,
            stage_name=stage_name,
            status=StageStatus.RUNNING.value,
            attempt_no=attempt_no,
        )
        self.db.add(sr)
        await self.db.flush()
        return sr

    async def mark_build_running(self, build: Build, stage_name: str) -> None:
        build.status = StageStatus.RUNNING.value
        build.current_stage = stage_name
        await self.db.flush()

    async def complete_stage_run(self, stage_run: StageRun) -> None:
        stage_run.status = StageStatus.SUCCEEDED.value
        stage_run.finished_at = datetime.utcnow()
        await self.db.flush()

    async def fail_stage_run(self, stage_run: StageRun, reason: str) -> None:
        stage_run.status = StageStatus.FAILED.value
        stage_run.finished_at = datetime.utcnow()
        stage_run.failure_reason = reason
        await self.db.flush()

    async def mark_build_failed(self, build: Build, reason: str) -> None:
        build.status = TopLevelStatus.FAILED.value
        build.current_stage = TopLevelStatus.FAILED.value
        build.failure_reason = reason
        build.finished_at = datetime.utcnow()
        await self.db.flush()

    async def mark_build_completed(self, build: Build) -> None:
        build.status = TopLevelStatus.COMPLETED.value
        build.current_stage = TopLevelStatus.COMPLETED.value
        build.finished_at = datetime.utcnow()
        await self.db.flush()

    async def advance_task(self, task: Task) -> "Optional[TopLevelStatus]":
        current = TopLevelStatus(task.status)
        if current in STAGE_TRANSITIONS:
            next_status = STAGE_TRANSITIONS[current]
            await self.transition(task, next_status)
            return next_status
        return None

    async def mark_failed(self, task: Task, reason: str) -> None:
        task.status = TopLevelStatus.FAILED.value
        task.current_stage = TopLevelStatus.FAILED.value
        task.updated_at = datetime.utcnow()
        event = TaskEvent(
            task_id=task.id,
            event_type="task_failed",
            title=f"任务失败: {task.product_name}",
            detail=reason,
        )
        self.db.add(event)
        await self.db.flush()

    async def mark_completed(self, task: Task) -> None:
        task.status = TopLevelStatus.COMPLETED.value
        task.current_stage = TopLevelStatus.COMPLETED.value
        task.updated_at = datetime.utcnow()
        event = TaskEvent(
            task_id=task.id,
            event_type="task_completed",
            title=f"任务完成: {task.product_name}",
            detail="所有阶段已完成，导出文件可下载",
        )
        self.db.add(event)
        await self.db.flush()
