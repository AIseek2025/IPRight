from __future__ import annotations

import logging
import mimetypes
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.db import Artifact, Export

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])

logger = logging.getLogger(__name__)

EXPORT_ARTIFACT_FALLBACKS = {
    "manual_docx": ("software_manual_docx",),
    "source_code_docx": ("source_code_book_docx",),
    "application_form_docx": ("application_form_docx",),
}


@router.get("/{export_id}")
async def get_export(export_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict:
    export = await db.get(Export, export_id)
    if not export:
        raise HTTPException(status_code=404, detail={"code": "EXPORT_NOT_FOUND", "message": "export does not exist"})
    return {"code": "OK", "message": "success", "data": {
        "id": str(export.id),
        "file_name": export.file_name,
        "export_type": export.export_type,
        "status": export.status,
        "download_url": export.download_url,
        "created_at": str(export.created_at),
    }}


def _safe_resolve_export_path(export: Export) -> Path:
    """Resolve the on-disk file path for an export and reject path traversal."""
    storage_root = Path(settings.WORKSPACE_ROOT).resolve()
    exports_dir = (
        storage_root
        / "tasks"
        / str(export.task_id)
        / "builds"
        / str(export.build_id)
        / "exports"
    ).resolve()

    file_name = export.file_name or ""
    if not file_name or "/" in file_name or "\\" in file_name or file_name in (".", ".."):
        raise HTTPException(
            status_code=400,
            detail={"code": "EXPORT_FILE_NAME_INVALID", "message": "invalid export file name"},
        )

    candidate = (exports_dir / file_name).resolve()
    try:
        candidate.relative_to(exports_dir)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail={"code": "EXPORT_PATH_INVALID", "message": "invalid export path"},
        )
    return candidate


async def _resolve_export_artifact_path(db: AsyncSession, export: Export) -> Path | None:
    artifact: Artifact | None = None
    if export.artifact_id:
        artifact = await db.get(Artifact, export.artifact_id)

    if artifact is None and export.build_id:
        artifact_types = EXPORT_ARTIFACT_FALLBACKS.get(export.export_type, ())
        if artifact_types:
            artifact_q = await db.execute(
                select(Artifact)
                .where(
                    Artifact.task_id == export.task_id,
                    Artifact.build_id == export.build_id,
                    Artifact.artifact_name == export.file_name,
                    Artifact.artifact_type.in_(artifact_types),
                )
                .order_by(Artifact.created_at.desc())
                .limit(1)
            )
            artifact = artifact_q.scalar_one_or_none()

    if not artifact or not artifact.local_path:
        return None

    storage_root = Path(settings.WORKSPACE_ROOT).resolve()
    task_root = (storage_root / "tasks" / str(export.task_id)).resolve()
    raw_candidate = Path(artifact.local_path).expanduser()
    if raw_candidate.is_symlink():
        logger.warning(
            "Rejecting export symlink artifact path: export=%s path=%s",
            export.id,
            raw_candidate,
        )
        return None
    candidate = raw_candidate.resolve(strict=False)
    if not candidate.is_file():
        return None
    try:
        candidate.relative_to(task_root)
    except ValueError:
        logger.warning(
            "Rejecting export artifact path outside task workspace: export=%s path=%s",
            export.id,
            candidate,
        )
        return None
    return candidate


@router.get("/{export_id}/download")
async def download_export(export_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    export = await db.get(Export, export_id)
    if not export:
        raise HTTPException(status_code=404, detail={"code": "EXPORT_NOT_FOUND", "message": "export does not exist"})
    if export.status != "ready":
        raise HTTPException(status_code=409, detail={"code": "EXPORT_NOT_READY", "message": "export not ready yet"})

    file_path = _safe_resolve_export_path(export)
    if not file_path.is_file():
        fallback_path = await _resolve_export_artifact_path(db, export)
        if fallback_path is not None:
            file_path = fallback_path

    if not file_path.is_file():
        logger.warning(
            "Export %s marked ready but file missing on disk: %s",
            export.id,
            file_path,
        )
        raise HTTPException(
            status_code=404,
            detail={"code": "EXPORT_FILE_MISSING", "message": "export file not found on disk"},
        )

    media_type = mimetypes.guess_type(export.file_name)[0] or "application/octet-stream"
    return FileResponse(str(file_path), filename=export.file_name, media_type=media_type)
