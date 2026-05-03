from __future__ import annotations
import asyncio
import os

from typing import AsyncGenerator

from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

_engine = None
_async_session_factory = None
_engine_pid = None
_engine_loop_id = None


def _current_loop_id():
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return None


def _get_engine():
    global _engine, _async_session_factory, _engine_pid, _engine_loop_id
    current_pid = os.getpid()
    current_loop_id = _current_loop_id()

    if _engine is None or _engine_pid != current_pid or _engine_loop_id != current_loop_id:
        db_url = settings.DATABASE_URL
        if "sqlite" in db_url:
            _engine = create_async_engine(db_url, echo=settings.DEBUG)
        else:
            # Celery tasks call asyncio.run() per execution, so pooled asyncpg
            # connections can become bound to a previous event loop.
            _engine = create_async_engine(
                db_url,
                echo=settings.DEBUG,
                poolclass=pool.NullPool,
            )
        _async_session_factory = None
        _engine_pid = current_pid
        _engine_loop_id = current_loop_id
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
