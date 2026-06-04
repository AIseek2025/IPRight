from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.tasks import router as tasks_router
from app.api.admin import router as admin_router
from app.api.exports import router as exports_router
from app.core.auth import AuthMiddleware
from app.core.config import settings
from app.core.logging_middleware import RequestLoggingMiddleware
from app.core.database import Base, _get_engine

logger = logging.getLogger("ipright")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")
    try:
        yield
    finally:
        try:
            await engine.dispose()
            logger.info("Database engine disposed")
        except Exception:
            logger.exception("Failed to dispose database engine on shutdown")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=_lifespan,
)


def _parse_cors_origins() -> list[str]:
    raw = os.environ.get("IPRIGHT_CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


_cors_origins = _parse_cors_origins()
_cors_allow_credentials = os.environ.get("IPRIGHT_CORS_ALLOW_CREDENTIALS", "false").lower() in (
    "1", "true", "yes",
)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(AuthMiddleware)
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=_cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    # Default: allow any origin but disallow credentials. Combining "*" with
    # allow_credentials=True is a CORS spec violation that browsers reject, so
    # we explicitly force credentials off in the wildcard case.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": "ERROR", "message": str(exc.detail)},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_ERROR", "message": "服务器内部错误"},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=400,
        content={"code": "BAD_REQUEST", "message": str(exc)},
    )


app.include_router(tasks_router)
app.include_router(admin_router)
app.include_router(exports_router)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
    }
