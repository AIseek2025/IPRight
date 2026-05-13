"""Shared background asyncio runner for synchronous Celery tasks.

The orchestrator pipeline is implemented as ``async def`` functions because
they share infrastructure (``AsyncSession``, ``httpx.AsyncClient``, Playwright)
with the FastAPI side. Celery's default ``prefork`` worker pool, however, is
fundamentally synchronous, which used to force every task to call
``asyncio.run(...)``. That had three real costs:

1. Each task spun up a fresh event loop, which discarded the SQLAlchemy
   engine bound to the previous loop and re-created the connection pool.
2. ``asyncio.run`` cannot be re-entered, so any helper that wanted to "just
   await something" from a sync context had to plumb its own loop.
3. Long-lived shared state (e.g. ``httpx.AsyncClient`` keep-alive pools)
   could never be reused across tasks.

This module exposes a process-singleton background loop running in a daemon
thread. ``run_async`` submits a coroutine via
``asyncio.run_coroutine_threadsafe`` and blocks the caller (the Celery worker
thread) on the result. The lifecycle is best-effort — at process exit we
attempt to stop the loop, but Celery's hard kill paths are still respected.

Why a single shared loop instead of switching to ``gevent``/``eventlet``?
- Lower blast radius: no monkey-patching of stdlib sockets / SQLAlchemy
  drivers (``asyncpg`` notably does not work under gevent).
- Compatible with the existing ``concurrency=2`` prefork pool: each worker
  process gets its own background loop and they remain isolated.
- Easy to revert per call site by re-introducing ``asyncio.run`` if needed.

Risks intentionally left in place:
- Cancellation across the thread boundary is best-effort. ``run_async``
  exposes a ``timeout`` argument that surfaces ``concurrent.futures.TimeoutError``
  to the caller; we do not attempt to forcibly cancel the coroutine because
  Celery's ``soft_time_limit`` / ``time_limit`` are the canonical kill paths.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import threading
from concurrent.futures import Future
from typing import Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_lock = threading.Lock()
_atexit_registered = False


def _runner(loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    finally:
        try:
            pending = [t for t in asyncio.all_tasks(loop) if not t.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
        except Exception:  # pragma: no cover - best effort
            logger.exception("Failed to drain pending tasks during loop shutdown")
        finally:
            try:
                loop.close()
            except Exception:  # pragma: no cover
                pass


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop, _loop_thread, _atexit_registered
    with _lock:
        if _loop is not None and _loop.is_running():
            return _loop
        new_loop = asyncio.new_event_loop()
        thread = threading.Thread(
            target=_runner,
            args=(new_loop,),
            name="ipright-async-runner",
            daemon=True,
        )
        thread.start()
        _loop = new_loop
        _loop_thread = thread
        if not _atexit_registered:
            atexit.register(_shutdown)
            _atexit_registered = True
        logger.info("Started shared async runner loop in thread %s", thread.name)
        return _loop


def _shutdown() -> None:
    global _loop, _loop_thread
    loop, thread = _loop, _loop_thread
    if loop is None:
        return
    try:
        loop.call_soon_threadsafe(loop.stop)
    except Exception:  # pragma: no cover
        logger.exception("Failed to signal stop to async runner loop")
    if thread is not None and thread.is_alive():
        thread.join(timeout=5)
    _loop = None
    _loop_thread = None


def run_async(coro: Coroutine[None, None, T], *, timeout: float | None = None) -> T:
    """Submit ``coro`` to the shared loop and block on its result.

    ``timeout`` is forwarded to ``Future.result``; ``None`` means "wait
    forever" (the canonical Celery wrapper supplies its own task time limit).
    Exceptions raised inside the coroutine are re-raised to the caller.
    """
    loop = _ensure_loop()
    fut: Future[T] = asyncio.run_coroutine_threadsafe(coro, loop)
    return fut.result(timeout=timeout)


def shutdown_runner() -> None:
    """Public hook used by tests / supervised shutdown paths."""
    _shutdown()
