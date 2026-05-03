from __future__ import annotations

import mimetypes
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.db import Export

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])


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


@router.get("/{export_id}/download")
async def download_export(export_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    export = await db.get(Export, export_id)
    if not export:
        raise HTTPException(status_code=404, detail={"code": "EXPORT_NOT_FOUND", "message": "export does not exist"})
    if export.status != "ready":
        raise HTTPException(status_code=409, detail={"code": "EXPORT_NOT_READY", "message": "export not ready yet"})

    storage_root = settings.WORKSPACE_ROOT
    file_path = f"{storage_root}/tasks/{export.task_id}/builds/{export.build_id}/exports/{export.file_name}"

    if os.path.exists(file_path):
        media_type = mimetypes.guess_type(export.file_name)[0] or "application/octet-stream"
        return FileResponse(file_path, filename=export.file_name, media_type=media_type)

    return StreamingResponse(iter([b""]), status_code=204)
