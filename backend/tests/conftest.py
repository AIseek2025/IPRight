"""Shared pytest configuration for IPRight backend tests.

The most important behavior here is to give every TestClient / AsyncClient
test a stable ``IPRIGHT_API_TOKEN`` (and ``IPRIGHT_ADMIN_TOKEN``) before any
``app.core.auth`` import happens, then automatically attach the
``Authorization: Bearer ...`` header to outbound HTTP calls. Without this,
the new fail-closed auth middleware would 401 every existing test.
"""

from __future__ import annotations

import os
from typing import Iterator

import pytest

# These must be set BEFORE the ``app.core.auth`` module is first imported,
# which is why we rely on a top-level conftest.py rather than a fixture.
os.environ.setdefault("IPRIGHT_API_TOKEN", "test-api-token")
os.environ.setdefault("IPRIGHT_ADMIN_TOKEN", "test-admin-token")


@pytest.fixture(scope="session")
def api_token() -> str:
    return os.environ["IPRIGHT_API_TOKEN"]


@pytest.fixture(scope="session")
def admin_token() -> str:
    return os.environ["IPRIGHT_ADMIN_TOKEN"]


@pytest.fixture(autouse=True)
def _inject_default_auth_header(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Patch ``httpx.AsyncClient`` so all test requests carry the API token.

    Tests that need to verify the unauthenticated path can pass an explicit
    ``Authorization`` header (it wins over the default), or use the
    ``unauthenticated_client`` fixture below.
    """
    import httpx

    original_request = httpx.AsyncClient.request

    async def patched(self, method, url, *args, **kwargs):  # type: ignore[no-redef]
        headers = kwargs.pop("headers", None) or {}
        if not any(k.lower() == "authorization" for k in headers):
            headers = {**headers, "Authorization": f"Bearer {os.environ['IPRIGHT_API_TOKEN']}"}
        kwargs["headers"] = headers
        return await original_request(self, method, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "request", patched)
    yield


@pytest.fixture
def unauthenticated_request_kwargs() -> dict:
    """Helper for tests that need to call an endpoint *without* the token."""
    return {"headers": {"Authorization": ""}}
