from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))


class TestPipelineIntegration:
    """Integration tests for the full IPRight pipeline."""

    @pytest.fixture
    def task_dir(self, tmp_path):
        """Create a temporary task workspace."""
        td = tmp_path / "task_test"
        td.mkdir()
        for sub in ["prd", "manifests", "app", "artifacts/screenshots", "builds/build_001/exports"]:
            (td / sub).mkdir(parents=True, exist_ok=True)
        return td

    def test_full_document_generation(self, task_dir):
        """Test that the required Word documents can be generated from scratch."""
        from app.services.document.manual import SoftwareManualGenerator
        from app.services.document.codebook import SourceCodeBookGenerator

        # Generate manual
        manual_gen = SoftwareManualGenerator(product_name="TestApp", version="V1.0")
        manual_gen.generate_full(
            prd_summary={"core_modules": ["A", "B", "C"]},
            screenshots_meta=[
                {"page_title": "登录页", "caption": "图1 登录页", "image_path": ""},
                {"page_title": "首页", "caption": "图2 首页", "image_path": ""},
            ],
        )
        manual_path = task_dir / "builds" / "build_001" / "exports" / "software_manual.docx"
        manual_gen.save(str(manual_path))
        assert manual_path.exists()
        assert manual_path.stat().st_size > 1000

        # Generate source code book from example app
        demo_app = PROJECT_ROOT / "examples" / "demo_app"
        if (demo_app / "manifests" / "code_index_manifest.json").exists():
            code_index = json.loads((demo_app / "manifests" / "code_index_manifest.json").read_text())
            code_gen = SourceCodeBookGenerator(product_name="TestApp", version="V1.0")
            code_gen.generate(code_index, str(demo_app))
            code_path = task_dir / "builds" / "build_001" / "exports" / "source_code_book.docx"
            code_gen.save(str(code_path))
            assert code_path.exists()
            assert code_path.stat().st_size > 100

    def test_manifest_validation_chain(self, task_dir):
        """Test that all 4 manifests from demo_app pass validation."""
        from app.services.validator import ManifestValidator

        demo_app = PROJECT_ROOT / "examples" / "demo_app" / "manifests"
        if not demo_app.exists():
            pytest.skip("Demo app manifests not found")

        validator = ManifestValidator()
        manifests = {}
        for name in ["app_manifest", "run_manifest", "capture_manifest", "code_index_manifest"]:
            mf_path = demo_app / f"{name}.json"
            if mf_path.exists():
                manifests[name] = json.loads(mf_path.read_text(encoding="utf-8"))

        assert len(manifests) > 0
        results = validator.validate_all(manifests)
        assert validator.is_all_valid(results), f"Validation failed: {results}"

    def test_state_machine_full_chain(self):
        """Test the complete state machine transitions."""
        from app.core.state_machine import (
            STAGE_TRANSITIONS, TopLevelStatus
        )

        # Verify the complete chain from queued to completed
        chain = [
            TopLevelStatus.QUEUED,
            TopLevelStatus.PLANNING,
            TopLevelStatus.CODING,
            TopLevelStatus.BUILDING,
            TopLevelStatus.RUNNING,
            TopLevelStatus.CAPTURING,
            TopLevelStatus.WRITING_MANUAL,
            TopLevelStatus.WRITING_CODE_BOOK,
            TopLevelStatus.PUBLISHING,
            TopLevelStatus.COMPLETED,
        ]

        for i in range(len(chain) - 1):
            current = chain[i]
            expected_next = chain[i + 1]
            if current in STAGE_TRANSITIONS:
                assert STAGE_TRANSITIONS[current] == expected_next, \
                    f"Expected {current} -> {expected_next}, got {STAGE_TRANSITIONS.get(current)}"

    def test_e2e_workspace_structure(self, task_dir):
        """Verify the workspace directory structure matches the contract."""
        required_dirs = [
            task_dir / "prd",
            task_dir / "manifests",
            task_dir / "app",
            task_dir / "artifacts",
        ]
        for d in required_dirs:
            assert d.exists(), f"Required directory missing: {d}"

        # Test that we can write manifests
        manifest = {
            "product_name": "Test",
            "version": "V1.0",
            "app_type": "admin_web",
            "frontend_framework": "react_vite",
            "backend_framework": "fastapi",
            "entry_routes": ["/login"],
            "demo_accounts": [{"username": "admin", "password": "admin123"}],
        }
        manifest_path = task_dir / "manifests" / "app_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        assert manifest_path.exists()

        loaded = json.loads(manifest_path.read_text())
        assert loaded["product_name"] == "Test"
        assert len(loaded["demo_accounts"]) == 1

    def test_api_schemas_serialize(self):
        """Test API request/response schemas serialize correctly."""
        from app.schemas.api import (
            TaskCreateRequest, TaskCreateResponse, TaskDetailResponse,
            TaskListItem, ExportItem, EventItem
        )
        from datetime import datetime

        req = TaskCreateRequest(keyword="test", product_name="Test", version="V2.0", industry="物流")
        data = req.model_dump()
        assert data["keyword"] == "test"
        assert data["version"] == "V2.0"

        resp = TaskCreateResponse(task_id="abc-123", status="queued")
        assert resp.model_dump()["task_id"] == "abc-123"

        now = datetime.utcnow()
        item = TaskListItem(id="x", keyword="k", product_name="p", version="V1.0",
                            status="queued", current_stage=None, created_at=now, updated_at=now)
        assert item.model_dump()["status"] == "queued"
