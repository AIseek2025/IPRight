from __future__ import annotations

from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

import os

security_scheme = HTTPBearer(auto_error=False)

API_TOKEN = os.environ.get("IPRIGHT_API_TOKEN", "ipright-dev-token-2026")
ADMIN_TOKEN = os.environ.get("IPRIGHT_ADMIN_TOKEN", "ipright-admin-token-2026")


class AuthMiddleware(BaseHTTPMiddleware):
    """Simple token-based auth middleware for IPRight API."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in ("/health", "/docs", "/openapi.json", "/redoc"):
            return await call_next(request)

        if path.startswith("/api/v1/admin"):
            auth = request.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                return self._unauthorized("Missing admin token")
            token = auth.replace("Bearer ", "")
            if token != ADMIN_TOKEN:
                return self._unauthorized("Invalid admin token")
        elif path.startswith("/api/v1/exports") and "/download" in path:
            return await call_next(request)

        return await call_next(request)

    def _unauthorized(self, msg: str):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"code": "UNAUTHORIZED", "message": msg},
        )
