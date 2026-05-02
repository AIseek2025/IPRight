from __future__ import annotations

from app.schemas.api import (
    TaskCreateRequest,
    TaskCreateResponse,
    TaskListItem,
    TaskListResponse,
    TaskRetryRequest,
)


def test_task_create_request():
    req = TaskCreateRequest(keyword="test", version="V1.0")
    assert req.keyword == "test"
    assert req.version == "V1.0"
    assert req.product_name is None


def test_task_create_response():
    resp = TaskCreateResponse(task_id="abc-123", status="queued")
    assert resp.task_id == "abc-123"
    assert resp.status == "queued"


def test_task_retry_request():
    req = TaskRetryRequest(from_stage="capturing")
    assert req.from_stage == "capturing"


def test_task_retry_request_default():
    req = TaskRetryRequest()
    assert req.from_stage is None


def test_task_list_item():
    from datetime import datetime
    now = datetime.utcnow()
    item = TaskListItem(
        id="x", keyword="test", product_name="Test", version="V1.0",
        status="queued", current_stage=None, created_at=now, updated_at=now,
    )
    data = item.model_dump()
    assert data["id"] == "x"
    assert data["status"] == "queued"
