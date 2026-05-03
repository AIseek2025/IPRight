from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.state_machine import StageName, StageStatus, TopLevelStatus
from workers.orchestrator.runner import (
    StageContext,
    StageResult,
    _status_to_stage,
    STAGE_HANDLERS,
)
from workers.stages.handlers import (
    run_plan_stage,
    run_build_stage,
    run_compose_manual_stage,
    run_compose_code_book_stage,
)


class TestStageHandlers:
    """Unit tests for individual stage handler functions."""

    def test_plan_stage_returns_valid_result(self):
        from unittest.mock import AsyncMock, MagicMock
        import asyncio

        mock_session = AsyncMock()
        mock_session_factory = MagicMock()
        mock_session_scope = AsyncMock()
        mock_session_scope.__aenter__.return_value = mock_session
        mock_session_factory.return_value.return_value = mock_session_scope

        async def _run():
            ctx = StageContext(
                task_id=str(uuid.uuid4()),
                build_id=str(uuid.uuid4()),
                db_factory=mock_session_factory,
            )
            result = await run_plan_stage(ctx)
            return result

        result = asyncio.run(_run())
        assert isinstance(result, StageResult)
        assert result.success

    @pytest.mark.skip(reason="Requires full DB mock for artifact creation")
    def test_build_stage_returns_valid_result(self):
        pass

    def test_status_to_stage_mapping(self):
        assert _status_to_stage(TopLevelStatus.PLANNING) == StageName.PLAN
        assert _status_to_stage(TopLevelStatus.CODING) is None
        assert _status_to_stage(TopLevelStatus.BUILDING) == StageName.BUILD
        assert _status_to_stage(TopLevelStatus.RUNNING) == StageName.VERIFY_RUN
        assert _status_to_stage(TopLevelStatus.CAPTURING) == StageName.CAPTURE
        assert _status_to_stage(TopLevelStatus.WRITING_MANUAL) == StageName.COMPOSE_MANUAL
        assert _status_to_stage(TopLevelStatus.WRITING_CODE_BOOK) == StageName.COMPOSE_CODE_BOOK
        assert _status_to_stage(TopLevelStatus.PUBLISHING) == StageName.PUBLISH
        assert _status_to_stage(TopLevelStatus.QUEUED) is None
        assert _status_to_stage(TopLevelStatus.COMPLETED) is None

    def test_all_stages_registered(self):
        required = {
            StageName.PLAN, StageName.BUILD, StageName.VERIFY_RUN,
            StageName.CAPTURE, StageName.COMPOSE_MANUAL,
            StageName.COMPOSE_CODE_BOOK, StageName.PUBLISH,
        }
        registered = set(STAGE_HANDLERS.keys())
        assert required.issubset(registered), f"Missing stages: {required - registered}"


class TestStageContextAndResult:
    def test_stage_context_creation(self):
        ctx = StageContext(
            task_id="t1",
            build_id="b1",
            db_factory=lambda: None,
        )
        assert ctx.task_id == "t1"
        assert ctx.build_id == "b1"

    def test_stage_result_success(self):
        result = StageResult(success=True)
        assert result.success
        assert result.error is None

    def test_stage_result_failure(self):
        result = StageResult(success=False, error="test error")
        assert not result.success
        assert result.error == "test error"

    def test_stage_result_with_artifacts(self):
        result = StageResult(
            success=True,
            artifacts=[{"type": "prd", "name": "test_prd.md"}],
            metadata={"key": "value"},
        )
        assert len(result.artifacts) == 1
        assert result.metadata["key"] == "value"
