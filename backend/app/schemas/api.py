from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator


class ORMBaseModel(BaseModel):
    """Base model that coerces UUID fields to strings."""
    model_config = {"from_attributes": True}

    @field_validator("id", "task_id", "build_id", "artifact_id", "active_build_id",
                     "image_artifact_id", "created_by", mode="before", check_fields=False)
    @classmethod
    def coerce_uuid(cls, v: Any) -> Any:
        if isinstance(v, UUID):
            return str(v)
        return v


class TaskCreateRequest(BaseModel):
    keyword: str
    product_name: Optional[str] = None
    version: str = "V1.0"
    industry: Optional[str] = None
    notes: Optional[str] = None


class TaskCreateResponse(BaseModel):
    task_id: str
    status: str


class TaskListItem(ORMBaseModel):
    id: str
    keyword: str
    product_name: str
    version: str
    status: str
    current_stage: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    items: list
    total: int
    page: int
    page_size: int


class TaskDetailResponse(ORMBaseModel):
    id: str
    keyword: str
    product_name: str
    version: str
    industry: Optional[str]
    notes: Optional[str]
    status: str
    current_stage: Optional[str]
    active_build_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class TaskDashboardResponse(BaseModel):
    task: TaskDetailResponse
    timeline: list
    exports: list
    prd_summary: Optional[str]
    screenshot_previews: list

    model_config = {"from_attributes": True}


class ArtifactItem(ORMBaseModel):
    id: str
    artifact_type: str
    artifact_name: str
    mime_type: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactListResponse(BaseModel):
    items: list


class StageRunItem(ORMBaseModel):
    id: str
    stage_name: str
    status: str
    attempt_no: int
    started_at: datetime
    finished_at: Optional[datetime]
    failure_reason: Optional[str]

    model_config = {"from_attributes": True}


class BuildDetailResponse(ORMBaseModel):
    id: str
    build_no: int
    status: str
    current_stage: Optional[str]
    trigger_type: str
    failure_reason: Optional[str]
    started_at: datetime
    finished_at: Optional[datetime]
    stage_runs: list

    model_config = {"from_attributes": True}


class ExportItem(ORMBaseModel):
    id: str
    export_type: str
    file_name: str
    status: str
    download_url: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ExportListResponse(BaseModel):
    items: list


class EventItem(ORMBaseModel):
    id: str
    event_type: str
    title: str
    detail: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    items: list


class TaskRetryRequest(BaseModel):
    from_stage: Optional[str] = None


class ApiResponse(BaseModel):
    code: str = "OK"
    message: str = "success"
    data: Any = None


class ScreenshotItem(ORMBaseModel):
    id: str
    scenario_id: str
    page_title: str
    route: str
    caption: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ScreenshotListResponse(BaseModel):
    items: list
