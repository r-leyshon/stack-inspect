"""The collector page is the interactive graph, and traces carry layout data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from stack_inspect.server import create_app
from stack_inspect.store import EventLog

if TYPE_CHECKING:
    from pathlib import Path


def test_page_draws_the_graph_and_traces_carry_layers(tmp_path: Path) -> None:
    """The UI is a graph canvas, and each trace span names its layer."""
    log = EventLog(tmp_path / "events.db")
    log.append(
        {
            "id": "e1",
            "traceId": "trace",
            "nodeKey": "api:request:GET /items",
            "kind": "request",
            "layer": "api",
            "phase": "instant",
            "name": "GET /items",
            "ts": 1,
            "attributes": {},
        },
    )
    client = TestClient(create_app(log), client=("127.0.0.1", 50000))
    page = client.get("/")
    assert page.is_success
    assert 'id="graph"' in page.text
    assert "hides the status" in page.text
    span = client.get("/v1/traces").json()["traces"][0]["spans"][0]
    assert span["layer"] == "api"
    assert span["name"] == "GET /items"
