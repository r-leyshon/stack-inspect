"""The FastAPI adapter against a real Starlette stack."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import stack_inspect_fastapi
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from httpx import ASGITransport, AsyncClient
from stack_inspect_core import set_sink

if TYPE_CHECKING:
    from collections.abc import Iterator

_SERVER_ERROR = 500
_CLIENT_ERROR = 400


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, object]]]:
    """Collect events in memory and enable the adapter."""
    monkeypatch.setenv("STACK_INSPECT", "1")
    monkeypatch.delenv("NODE_ENV", raising=False)
    events: list[dict[str, object]] = []
    set_sink(events.append)
    yield events
    set_sink(None)


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/crash")
    async def crash() -> dict[str, str]:
        message = "planted crash"
        raise RuntimeError(message)

    @app.get("/api/items")
    async def items() -> dict[str, bool]:
        return {"ok": True}

    stack_inspect_fastapi.install(app)
    return app


@pytest.mark.anyio
async def test_server_error_is_visible_without_cors_headers(
    captured: list[dict[str, object]],
) -> None:
    """An unhandled error is recorded as 500 with no allow-origin header."""
    transport = ASGITransport(app=_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/crash", headers={"origin": "http://localhost:3000"})
    assert response.status_code == _SERVER_ERROR
    ends = [event for event in captured if event.get("phase") == "end" and event.get("kind") == "request"]
    assert ends
    attributes = ends[-1]["attributes"]
    assert isinstance(attributes, dict)
    assert attributes["status"] == _SERVER_ERROR
    assert not attributes["accessControlAllowOrigin"]


@pytest.mark.anyio
async def test_rejected_preflight_records_the_header(
    captured: list[dict[str, object]],
) -> None:
    """A preflight for a disallowed header is recorded with that header's name."""
    transport = ASGITransport(app=_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/items",
            headers={
                "origin": "http://localhost:3000",
                "access-control-request-method": "GET",
                "access-control-request-headers": "X-Custom-Header",
            },
        )
    assert response.status_code >= _CLIENT_ERROR
    options = [
        event
        for event in captured
        if isinstance(event.get("attributes"), dict)
        and event.get("attributes", {}).get("method") == "OPTIONS"  # type: ignore[union-attr]
        and event.get("phase") == "end"
    ]
    assert options
    attributes = options[-1]["attributes"]
    assert isinstance(attributes, dict)
    assert "X-Custom-Header" in str(attributes["requestedHeaders"])


def test_install_is_a_no_op_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without the opt-in flag the application is left untouched."""
    monkeypatch.delenv("STACK_INSPECT", raising=False)
    app = FastAPI()
    stack_inspect_fastapi.install(app)
    assert not hasattr(app, "_stack_inspect_installed")
