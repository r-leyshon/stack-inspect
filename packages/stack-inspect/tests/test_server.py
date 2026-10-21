"""The collector answers CORS for the browser adapter and still refuses remote hosts."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from stack_inspect.server import create_app
from stack_inspect.store import EventLog

if TYPE_CHECKING:
    from pathlib import Path


def test_collector_answers_cors_for_a_browser_origin(tmp_path: Path) -> None:
    """A page on localhost may post to 127.0.0.1, and a preflight gets allow headers."""
    client = TestClient(create_app(EventLog(tmp_path / "events.db")), client=("127.0.0.1", 50000))
    preflight = client.options(
        "/v1/events",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert preflight.status_code == HTTPStatus.OK
    assert preflight.headers.get("access-control-allow-origin") == "*"
    assert "POST" in (preflight.headers.get("access-control-allow-methods") or "")

    posted = client.post(
        "/v1/events",
        headers={"Origin": "http://localhost:3000"},
        json={
            "id": "e1",
            "traceId": "trace",
            "nodeKey": "browser:interaction:click",
            "kind": "interaction",
            "layer": "browser",
            "phase": "instant",
            "name": "click",
            "ts": 1,
        },
    )
    assert posted.status_code == HTTPStatus.OK
    assert posted.headers.get("access-control-allow-origin") == "*"
    assert posted.json()["accepted"] == 1


def test_collector_still_refuses_a_remote_client(tmp_path: Path) -> None:
    """Loopback remains the security boundary after CORS is enabled."""
    remote = TestClient(create_app(EventLog(tmp_path / "events.db")), client=("10.0.0.1", 9))
    response = remote.get("/health")
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()["error"] == "loopback only"
