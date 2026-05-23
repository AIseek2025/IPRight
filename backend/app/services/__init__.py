from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.state_machine import (
    STAGE_TRANSITIONS,
    StageName,
    StageStatus,
    TOPLEVEL_TO_STAGE,
    TopLevelStatus,
)
from app.models.db import Build, StageRun, Task, TaskEvent

STALE_BUILD_TIMEOUT = timedelta(hours=6)
ACTIVE_TASK_STATUSES = {
    TopLevelStatus.QUEUED.value,
    TopLevelStatus.PLANNING.value,
    TopLevelStatus.CODING.value,
    TopLevelStatus.BUILDING.value,
    TopLevelStatus.RUNNING.value,
    TopLevelStatus.CAPTURING.value,
    TopLevelStatus.WRITING_MANUAL.value,
    TopLevelStatus.WRITING_CODE_BOOK.value,
    TopLevelStatus.PUBLISHING.value,
}


class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_event(
        self,
        *,
        task_id: uuid.UUID,
        build_id: uuid.UUID | None = None,
        event_type: str,
        title: str,
        detail: str | None = None,
        payload_json: dict[str, Any] | None = None,
    ) -> TaskEvent:
        event = TaskEvent(
            task_id=task_id,
            build_id=build_id,
            event_type=event_type,
            title=title,
            detail=detail,
            payload_json=payload_json,
        )
        self.db.add(event)
        await self.db.flush()
        return event

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

    def _resolve_retry_entrypoint(self, from_stage: str | None) -> tuple[TopLevelStatus, str]:
        if not from_stage:
            return TopLevelStatus.QUEUED, "plan"

        target_stage: StageName | None = None
        try:
            target_stage = StageName(from_stage)
        except ValueError:
            try:
                target_status = TopLevelStatus(from_stage)
            except ValueError:
                return TopLevelStatus.QUEUED, "plan"
            target_stage = TOPLEVEL_TO_STAGE.get(target_status)

        if target_stage is None:
            return TopLevelStatus.QUEUED, "plan"

        stage_status = next(
            (status for status, stage in TOPLEVEL_TO_STAGE.items() if stage == target_stage),
            TopLevelStatus.PLANNING,
        )
        previous_status = next(
            (status for status, next_status in STAGE_TRANSITIONS.items() if next_status == stage_status),
            TopLevelStatus.QUEUED,
        )
        return previous_status, target_stage.value

    async def cleanup_stale_builds(
        self,
        *,
        task_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> list[Build]:
        now = now or datetime.utcnow()
        cutoff = now - STALE_BUILD_TIMEOUT
        query = select(Build).where(
            Build.status.in_([StageStatus.QUEUED.value, StageStatus.RUNNING.value]),
            Build.started_at.is_not(None),
            Build.started_at < cutoff,
        )
        if task_id is not None:
            query = query.where(Build.task_id == task_id)

        stale_builds = (await self.db.execute(query)).scalars().all()
        if not stale_builds:
            return []

        tasks = {
            build.task_id: await self.db.get(Task, build.task_id)
            for build in stale_builds
        }
        for stale_build in stale_builds:
            stale_build.status = "aborted"
            stale_build.current_stage = "aborted"
            stale_build.failure_reason = "Automatically aborted stale queued/running build after timeout"
            stale_build.finished_at = now
            task = tasks.get(stale_build.task_id)
            if task and task.active_build_id == stale_build.id:
                task.active_build_id = None
                if task.status in ACTIVE_TASK_STATUSES:
                    task.status = TopLevelStatus.FAILED.value
                    task.current_stage = TopLevelStatus.FAILED.value
                task.updated_at = now
        await self.db.flush()
        return stale_builds

    async def reconcile_task_state(self, task: Task) -> bool:
        if task.status not in ACTIVE_TASK_STATUSES:
            return False

        latest_build: Build | None = None
        if task.active_build_id:
            latest_build = await self.db.get(Build, task.active_build_id)
            if latest_build and latest_build.status in {StageStatus.QUEUED.value, StageStatus.RUNNING.value}:
                return False

        if latest_build is None:
            latest_build_q = await self.db.execute(
                select(Build)
                .where(Build.task_id == task.id)
                .order_by(Build.build_no.desc())
                .limit(1)
            )
            latest_build = latest_build_q.scalar_one_or_none()

        if latest_build is None:
            return False
        if latest_build.status in {StageStatus.QUEUED.value, StageStatus.RUNNING.value}:
            return False

        changed = False
        if latest_build.status == TopLevelStatus.COMPLETED.value:
            if task.status != TopLevelStatus.COMPLETED.value:
                task.status = TopLevelStatus.COMPLETED.value
                task.current_stage = TopLevelStatus.COMPLETED.value
                changed = True
        elif latest_build.status in {TopLevelStatus.FAILED.value, "aborted", StageStatus.CANCELLED.value}:
            if task.status != TopLevelStatus.FAILED.value or task.current_stage != TopLevelStatus.FAILED.value:
                task.status = TopLevelStatus.FAILED.value
                task.current_stage = TopLevelStatus.FAILED.value
                changed = True

        if task.active_build_id is not None and latest_build.status not in {
            StageStatus.QUEUED.value,
            StageStatus.RUNNING.value,
        }:
            task.active_build_id = None
            changed = True

        if changed:
            task.updated_at = datetime.utcnow()
            await self.db.flush()
        return changed

    async def start_build(self, task: Task, trigger_type: str = "create", from_stage: str | None = None) -> Build:
        await self.cleanup_stale_builds()
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
        resume_status, initial_stage = self._resolve_retry_entrypoint(from_stage if trigger_type == "retry" else None)

        build = Build(
            id=build_id,
            task_id=task.id,
            build_no=build_no,
            status="queued",
            trigger_type=trigger_type,
            current_stage=initial_stage,
        )
        self.db.add(build)
        task.active_build_id = build_id
        task.status = resume_status.value
        task.current_stage = resume_status.value
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
        await self.log_event(
            task_id=task.id,
            build_id=task.active_build_id,
            event_type="task_failed",
            title=f"任务失败: {task.product_name}",
            detail=reason,
        )

    async def mark_completed(self, task: Task) -> None:
        task.status = TopLevelStatus.COMPLETED.value
        task.current_stage = TopLevelStatus.COMPLETED.value
        task.updated_at = datetime.utcnow()
        await self.log_event(
            task_id=task.id,
            build_id=task.active_build_id,
            event_type="task_completed",
            title=f"任务完成: {task.product_name}",
            detail="所有阶段已完成，导出文件可下载",
        )
