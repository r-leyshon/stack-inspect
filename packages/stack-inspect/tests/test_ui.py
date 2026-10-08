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
    assert 'id="transport"' in page.text
    assert 'id="restart"' in page.text
    assert 'aria-label="Restart"' in page.text
    assert 'class="transport-deck"' in page.text
    assert 'aria-label="Play"' in page.text
    assert 'class="transport-svg"' in page.text
    assert "glyph-play" in page.text
    assert "glyph-pause" in page.text
    assert 'id="ruler"' in page.text
    assert 'id="timecode"' in page.text
    assert 'id="view-sequence"' in page.text
    assert 'id="sequence"' in page.text
    assert 'aria-pressed="false">Sequence' in page.text
    assert "Sequence draws the same things in time order" in page.text
    assert "Only the drawing on screen is painted" in page.text
    assert 'id="names"' in page.text
    assert 'aria-pressed="false">Names' in page.text
    assert "hovering a dot still names" in page.text
    assert "grows each time" in page.text
    assert "1 consequence" in page.text
    assert "Drag the ruler or the playhead triangle" in page.text
    assert "jump to the start" in page.text
    assert "paint its nodes red" in page.text
    assert "#4a2424" in page.text
    assert "whole graph at that same moment" in page.text
    assert "including while a finding is open" in page.text
    assert 'data-help="live"' in page.text
    assert "hides the status" in page.text
    span = client.get("/v1/traces").json()["traces"][0]["spans"][0]
    assert span["layer"] == "api"
    assert span["name"] == "GET /items"
