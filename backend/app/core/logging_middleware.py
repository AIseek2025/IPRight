from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("ipright.api")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]
        start = time.time()
        response = await call_next(request)
        elapsed = time.time() - start
        logger.info(
            f"[{request_id}] {request.method} {request.url.path} "
            f"{response.status_code} {elapsed:.3f}s"
        )
        response.headers["X-Request-ID"] = request_id
        return response
