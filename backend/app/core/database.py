from __future__ import annotations
import asyncio
import logging
import os

from typing import AsyncGenerator

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

logger = logging.getLogger(__name__)

_engine = None
_async_session_factory = None
_engine_pid = None
_engine_loop_id = None


def _current_loop_id():
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return None


def _dispose_engine_safely(engine) -> None:
    """Best-effort sync disposal for an existing engine.

    The engine being replaced may be bound to a loop that is no longer
    running (process fork, loop swap), so we cannot rely on awaiting its
    async ``dispose``. We schedule disposal where possible and otherwise
    drop the reference; SQLAlchemy will close pooled connections during GC.
    """
    if engine is None:
        return
    try:
        sync_engine = getattr(engine, "sync_engine", None)
        if sync_engine is not None:
            sync_engine.dispose()
    except Exception:
        logger.exception("Failed to dispose stale async engine sync side")


def _get_engine():
    global _engine, _async_session_factory, _engine_pid, _engine_loop_id
    current_pid = os.getpid()
    current_loop_id = _current_loop_id()

    if _engine is None or _engine_pid != current_pid or _engine_loop_id != current_loop_id:
        previous_engine = _engine
        db_url = settings.DATABASE_URL
        if "sqlite" in db_url:
            _engine = create_async_engine(db_url, echo=settings.DEBUG)
        else:
            _engine = create_async_engine(
                db_url,
                echo=settings.DEBUG,
                poolclass=pool.NullPool,
            )
        _async_session_factory = None
        _engine_pid = current_pid
        _engine_loop_id = current_loop_id
        if previous_engine is not None and previous_engine is not _engine:
            _dispose_engine_safely(previous_engine)
    return _engine


def get_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(_get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _async_session_factory


def get_sync_url() -> str:
    return settings.DATABASE_SYNC_URL


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.close()
