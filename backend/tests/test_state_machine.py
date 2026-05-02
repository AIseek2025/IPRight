from __future__ import annotations

import uuid

from app.core.state_machine import (
    STAGE_TRANSITIONS,
    TopLevelStatus,
    StageName,
    StageStatus,
    RETRYABLE_STAGES,
)


def test_status_enum_values():
    assert TopLevelStatus.QUEUED.value == "queued"
    assert TopLevelStatus.COMPLETED.value == "completed"
    assert TopLevelStatus.FAILED.value == "failed"
    assert len(TopLevelStatus) == 13


def test_transition_chain():
    expected = [
        TopLevelStatus.QUEUED,
        TopLevelStatus.PLANNING,
        TopLevelStatus.CODING,
        TopLevelStatus.BUILDING,
        TopLevelStatus.RUNNING,
        TopLevelStatus.CAPTURING,
        TopLevelStatus.WRITING_MANUAL,
        TopLevelStatus.WRITING_CODE_BOOK,
        TopLevelStatus.PUBLISHING,
    ]
    for s in expected:
        assert s in STAGE_TRANSITIONS
        assert STAGE_TRANSITIONS[s] is not None


def test_completed_is_terminal():
    assert TopLevelStatus.COMPLETED not in STAGE_TRANSITIONS
    assert TopLevelStatus.FAILED not in STAGE_TRANSITIONS
    assert TopLevelStatus.CANCELLED not in STAGE_TRANSITIONS


def test_retryable_stages():
    assert StageName.PLAN in RETRYABLE_STAGES
    assert StageName.BUILD in RETRYABLE_STAGES
    assert StageName.CAPTURE in RETRYABLE_STAGES


def test_stage_enum_values():
    assert StageName.PLAN.value == "plan"
    assert StageName.CAPTURE.value == "capture"
    assert StageName.PUBLISH.value == "publish"


def test_stage_status_enum():
    assert StageStatus.QUEUED.value == "queued"
    assert StageStatus.RUNNING.value == "running"
    assert StageStatus.SUCCEEDED.value == "succeeded"
    assert StageStatus.FAILED.value == "failed"
