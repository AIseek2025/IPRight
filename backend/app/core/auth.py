from __future__ import annotations

import logging
import os
import secrets

from fastapi import Request, status
from fastapi.security import HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer(auto_error=False)


def _load_token(env_name: str, role: str) -> str:
    """Load a token from the environment.

    If the env var is unset and the app is in DEBUG mode, fall back to a
    process-local random token (logged loudly so developers know to set one).
    In non-debug mode an unset token leaves the value empty, which causes the
    middleware to reject every request to the protected scope (fail-closed).
    """
    value = os.environ.get(env_name, "").strip()
    if value:
        return value

    debug = os.environ.get("IPRIGHT_DEBUG", "false").lower() in ("1", "true", "yes")
    if debug:
        generated = secrets.token_urlsafe(24)
        logger.warning(
            "%s is unset; generated ephemeral %s token for DEBUG run. "
            "Set %s in the environment to use a stable value.",
            env_name,
            role,
            env_name,
        )
        return generated

    logger.warning(
        "%s is not configured. %s endpoints will reject all requests until it is set.",
        env_name,
        role.capitalize(),
    )
    return ""


API_TOKEN = _load_token("IPRIGHT_API_TOKEN", "api")
ADMIN_TOKEN = _load_token("IPRIGHT_ADMIN_TOKEN", "admin")


class AuthMiddleware(BaseHTTPMiddleware):
    """Token-based auth middleware for IPRight API.

    Two scopes:

    * ``/api/v1/admin/*`` requires ``ADMIN_TOKEN`` (Bearer header).
    * Every other ``/api/v1/*`` route requires ``API_TOKEN`` (Bearer header
      *or*, for the SSE endpoint, a ``?token=`` query string because the
      browser ``EventSource`` API cannot set custom headers).

    Public exemptions: health/readiness probes, OpenAPI docs, the public
    download links (``/api/v1/exports/<id>/download`` and
    ``/api/v1/tasks/<id>/bundle/download``) which are intentionally a
    pre-shared URL surface, and the OPTIONS pre-flight that the browser
    sends before authenticated requests.
    """

    PUBLIC_PATHS = {
        "/health",
        "/healthz",
        "/readyz",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/favicon.ico",
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        # CORS pre-flight always passes; the CORS middleware handles headers.
        if method == "OPTIONS":
            return await call_next(request)

        if path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Pre-shared download URLs are intentionally unauthenticated.
        if path.startswith("/api/v1/exports") and path.endswith("/download"):
            return await call_next(request)
        if path.startswith("/api/v1/tasks/") and path.endswith("/bundle/download"):
            return await call_next(request)

        if path.startswith("/api/v1/admin"):
            return await self._enforce_token(
                request,
                call_next,
                expected=ADMIN_TOKEN,
                role="admin",
                allow_query=False,
            )

        if path.startswith("/api/v1/"):
            # SSE: EventSource cannot set custom headers, so we accept
            # ?token=... for that single endpoint. We restrict the query
            # token to the SSE stream path to avoid leaking tokens into
            # generic access logs.
            allow_query = path.endswith("/stream")
            return await self._enforce_token(
                request,
                call_next,
                expected=API_TOKEN,
                role="api",
                allow_query=allow_query,
            )

        return await call_next(request)

    async def _enforce_token(
        self,
        request: Request,
        call_next,
        *,
        expected: str,
        role: str,
        allow_query: bool,
    ):
        token = self._extract_token(request, allow_query=allow_query)
        if not token:
            return self._unauthorized(f"Missing {role} token")
        if not expected or not secrets.compare_digest(token, expected):
            return self._unauthorized(f"Invalid {role} token")
        return await call_next(request)

    @staticmethod
    def _extract_token(request: Request, *, allow_query: bool) -> str:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[len("Bearer "):].strip()
        if allow_query:
            value = request.query_params.get("token", "")
            return value.strip()
        return ""

    def _unauthorized(self, msg: str):
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"code": "UNAUTHORIZED", "message": msg},
        )
