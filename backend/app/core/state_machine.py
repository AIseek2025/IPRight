from __future__ import annotations

import enum


class TopLevelStatus(str, enum.Enum):
    QUEUED = "queued"
    PLANNING = "planning"
    CODING = "coding"
    BUILDING = "building"
    RUNNING = "running"
    CAPTURING = "capturing"
    WRITING_MANUAL = "writing_manual"
    WRITING_CODE_BOOK = "writing_code_book"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_REVIEW = "needs_review"


class StageName(str, enum.Enum):
    PLAN = "plan"
    BUILD = "build"
    VERIFY_RUN = "verify_run"
    CAPTURE = "capture"
    COMPOSE_MANUAL = "compose_manual"
    COMPOSE_CODE_BOOK = "compose_code_book"
    PUBLISH = "publish"


class StageStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ArtifactType(str, enum.Enum):
    PRODUCT_PRD = "product_prd"
    DEVELOPMENT_WORK_ORDER = "development_work_order"
    APP_MANIFEST = "app_manifest"
    RUN_MANIFEST = "run_manifest"
    CAPTURE_MANIFEST = "capture_manifest"
    CODE_INDEX_MANIFEST = "code_index_manifest"
    RUNTIME_STATUS = "runtime_status"
    HEALTH_REPORT = "health_report"
    SCREENSHOT_MANIFEST = "screenshot_manifest"
    SCREENSHOT_IMAGE = "screenshot_image"
    SOFTWARE_MANUAL_DOCX = "software_manual_docx"
    SOURCE_CODE_BOOK_DOCX = "source_code_book_docx"
    LAUNCH_LOG = "launch_log"


class ExportType(str, enum.Enum):
    MANUAL_DOCX = "manual_docx"
    SOURCE_CODE_DOCX = "source_code_docx"


class ExportStatus(str, enum.Enum):
    PREPARING = "preparing"
    READY = "ready"
    EXPIRED = "expired"


class TriggerType(str, enum.Enum):
    CREATE = "create"
    RETRY = "retry"
    STAGE_RERUN = "stage_rerun"


class FailureCategory(str, enum.Enum):
    PLANNING_CONTRACT_ERROR = "planning_contract_error"
    CODING_CONTRACT_ERROR = "coding_contract_error"
    DEPENDENCY_INSTALL_FAILED = "dependency_install_failed"
    BUILD_FAILED = "build_failed"
    RUNTIME_BOOT_FAILED = "runtime_boot_failed"
    HEALTH_CHECK_FAILED = "health_check_failed"
    LOGIN_FAILED = "login_failed"
    CAPTURE_FAILED = "capture_failed"
    MANUAL_RENDER_FAILED = "manual_render_failed"
    CODE_BOOK_RENDER_FAILED = "code_book_render_failed"
    PUBLISH_FAILED = "publish_failed"


STAGE_TRANSITIONS: dict[TopLevelStatus, TopLevelStatus] = {
    TopLevelStatus.QUEUED: TopLevelStatus.PLANNING,
    TopLevelStatus.PLANNING: TopLevelStatus.CODING,
    TopLevelStatus.CODING: TopLevelStatus.BUILDING,
    TopLevelStatus.BUILDING: TopLevelStatus.RUNNING,
    TopLevelStatus.RUNNING: TopLevelStatus.CAPTURING,
    TopLevelStatus.CAPTURING: TopLevelStatus.WRITING_MANUAL,
    TopLevelStatus.WRITING_MANUAL: TopLevelStatus.WRITING_CODE_BOOK,
    TopLevelStatus.WRITING_CODE_BOOK: TopLevelStatus.PUBLISHING,
    TopLevelStatus.PUBLISHING: TopLevelStatus.COMPLETED,
}

TOPLEVEL_TO_STAGE: dict[TopLevelStatus, StageName | None] = {
    TopLevelStatus.PLANNING: StageName.PLAN,
    TopLevelStatus.CODING: None,
    TopLevelStatus.BUILDING: StageName.BUILD,
    TopLevelStatus.RUNNING: StageName.VERIFY_RUN,
    TopLevelStatus.CAPTURING: StageName.CAPTURE,
    TopLevelStatus.WRITING_MANUAL: StageName.COMPOSE_MANUAL,
    TopLevelStatus.WRITING_CODE_BOOK: StageName.COMPOSE_CODE_BOOK,
    TopLevelStatus.PUBLISHING: StageName.PUBLISH,
}

RETRYABLE_STAGES: set[StageName] = {
    StageName.PLAN,
    StageName.BUILD,
    StageName.VERIFY_RUN,
    StageName.CAPTURE,
    StageName.COMPOSE_MANUAL,
    StageName.COMPOSE_CODE_BOOK,
    StageName.PUBLISH,
}
