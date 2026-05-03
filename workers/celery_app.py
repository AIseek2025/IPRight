from __future__ import annotations

import uuid

from celery import Celery

from app.core.config import settings
from workers.stages import handlers as _stage_handlers  # noqa: F401

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
    worker_prefetch_multiplier=1,
)


@celery_app.task(name="orchestrate_task", bind=True, max_retries=3)
def orchestrate_task(self, task_id: str, build_id: str):
    from workers.orchestrator.runner import run_full_pipeline

    run_full_pipeline(uuid.UUID(task_id), uuid.UUID(build_id))
