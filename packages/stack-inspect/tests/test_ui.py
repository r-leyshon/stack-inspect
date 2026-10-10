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
    assert 'id="view-latency"' in page.text
    assert 'id="latency"' in page.text
    assert 'aria-pressed="false">Sequence' in page.text
    assert 'aria-pressed="false">Latency' in page.text
    assert "median duration" in page.text
    assert 'data-help="view-graph"' in page.text
    assert 'data-help="view-sequence"' in page.text
    assert 'data-help="view-latency"' in page.text
    assert "one line per request" in page.text
    assert "later runs of that same request" in page.text
    assert "select that request" in page.text
    assert "in decades" in page.text
    assert "Sequence draws the same things in time order" in page.text
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
    assert "Parameter values are being recorded." in page.text
    assert "including while a finding is open" in page.text
    assert 'data-help="live"' in page.text
    assert "hides the status" in page.text
    span = client.get("/v1/traces").json()["traces"][0]["spans"][0]
    assert span["layer"] == "api"
    assert span["name"] == "GET /items"


def test_page_explains_where_recorded_values_appear(tmp_path: Path) -> None:
    """Values is one control, and both drawings put the caption halfway along the line."""
    client = TestClient(create_app(EventLog(tmp_path / "events.db")), client=("127.0.0.1", 50000))
    page = client.get("/")
    assert 'id="values" aria-pressed="true">Values' in page.text
    assert "halfway along each line" in page.text
    assert "halfway along each message" in page.text


def test_latency_chart_warns_that_times_include_the_tool(tmp_path: Path) -> None:
    """The latency view says the times include stack-inspect and are not production."""
    client = TestClient(create_app(EventLog(tmp_path / "events.db")), client=("127.0.0.1", 50000))
    page = client.get("/")
    assert '<details id="latency-note"' in page.text
    assert "Development times include stack-inspect" in page.text
    assert "The adapters do not start in production." in page.text


def test_page_rests_a_large_graph(tmp_path: Path) -> None:
    """A single story keeps the force layout longer than the whole session."""
    client = TestClient(create_app(EventLog(tmp_path / "events.db")), client=("127.0.0.1", 50000))
    page = client.get("/")
    assert "const FORCE_LIMIT = { trace: 250, all: 120 }" in page.text
    assert "sit in columns" in page.text
    assert "moves that dot only" in page.text


def test_page_opens_a_finding_from_the_query(tmp_path: Path) -> None:
    """A trace and finding in the query string stay selected until the person picks another."""
    client = TestClient(create_app(EventLog(tmp_path / "events.db")), client=("127.0.0.1", 50000))
    page = client.get("/")
    assert "new URLSearchParams(window.location.search)" in page.text
    assert "pinnedTrace" in page.text
    assert "pinnedFinding" in page.text


def test_traces_include_recorded_parameters(tmp_path: Path) -> None:
    """Opted-in parameter values travel with the span, and stay off the graph node."""
    log = EventLog(tmp_path / "events.db")
    log.append(
        {
            "id": "q1",
            "traceId": "trace",
            "nodeKey": "db:query:items",
            "kind": "query",
            "layer": "db",
            "phase": "instant",
            "name": "select name from items where id = $1",
            "ts": 1,
            "attributes": {
                "parameters": ["synthetic-id"],
                "rows": [{"name": "Widget"}],
                "state": [4],
                "statement": "select name from items where id = $1",
            },
        },
    )
    client = TestClient(create_app(log), client=("127.0.0.1", 50000))
    span = client.get("/v1/traces").json()["traces"][0]["spans"][0]
    assert span["parameters"] == ["synthetic-id"]
    assert span["rows"] == [{"name": "Widget"}]
    assert span["state"] == [4]
    node = client.get("/v1/graph").json()["nodes"][0]
    assert "parameters" not in node
    assert "synthetic-id" not in str(node)
