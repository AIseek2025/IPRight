from __future__ import annotations

import asyncio
import logging
import uuid

from celery import Celery
from celery.signals import worker_ready

from app.core.config import settings
from workers.stages import load_stage_handlers

load_stage_handlers()
logger = logging.getLogger(__name__)

celery_app = Celery(
    "ipright",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="orchestrate_task", bind=True, max_retries=3)
def orchestrate_task(self, task_id: str, build_id: str):
    from workers.orchestrator.runner import run_full_pipeline

    run_full_pipeline(uuid.UUID(task_id), uuid.UUID(build_id))


@worker_ready.connect
def recover_interrupted_builds_on_worker_start(**kwargs):
    from app.core.database import get_session_factory
    from app.services import TaskService

    async def _recover() -> list[str]:
        async with get_session_factory()() as session:
            service = TaskService(session)
            recovered = await service.recover_interrupted_running_builds(
                "Worker restarted while build was running; previous execution was interrupted"
            )
            await session.commit()
            return [str(task_id) for task_id in recovered]

    try:
        recovered_ids = asyncio.run(_recover())
        if recovered_ids:
            logger.warning("Recovered interrupted running builds for tasks: %s", ", ".join(recovered_ids))
    except Exception:  # pragma: no cover - startup diagnostics only
        logger.exception("Failed to recover interrupted running builds on worker startup")
