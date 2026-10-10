"""MCP read tools slice the same log the UI projects, and /mcp stays on loopback."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from stack_inspect.mcp_server import (
    get_finding,
    get_graph,
    get_node_neighbourhood,
    get_report,
    list_findings,
    list_stories,
)
from stack_inspect.server import create_app
from stack_inspect.store import EventLog

if TYPE_CHECKING:
    from pathlib import Path

    from stack_inspect.model import GraphEvent


def _event(event_id: str, **overrides: object) -> GraphEvent:
    raw: dict[str, object] = {
        "id": event_id,
        "traceId": "trace-jobs",
        "nodeKey": "db:query:notes",
        "kind": "query",
        "layer": "db",
        "phase": "instant",
        "name": "select count(*) from notes",
        "ts": 1_700_000_000_000,
        "service": "worker",
        "attributes": {},
    }
    raw.update(overrides)
    event: GraphEvent = {
        "id": str(raw["id"]),
        "traceId": str(raw["traceId"]),
        "nodeKey": str(raw["nodeKey"]),
        "kind": str(raw["kind"]),
        "layer": str(raw["layer"]),
        "phase": str(raw["phase"]),
        "name": str(raw["name"]),
        "ts": raw["ts"] if isinstance(raw["ts"], int | float) else 0,
        "service": str(raw["service"]),
        "attributes": raw["attributes"] if isinstance(raw["attributes"], dict) else {},
    }
    parent = raw.get("parentId")
    if isinstance(parent, str):
        event["parentId"] = parent
    return event


def _story() -> list[GraphEvent]:
    request = _event(
        "request",
        nodeKey="api:request:POST /jobs",
        kind="request",
        layer="api",
        name="POST /jobs",
        service="jobs",
    )
    queries = [_event(f"query-{index}", parentId="request", ts=1_700_000_000_000 + index) for index in range(1, 4)]
    return [request, *queries]


def test_list_findings_cites_the_story_and_the_page() -> None:
    """A repeated query is returned in analysis order, with a link that opens it."""
    findings = list_findings(_story())["findings"]
    assert isinstance(findings, list)
    finding = findings[0]
    assert isinstance(finding, dict)
    assert finding["code"] == "repeated-query"
    assert finding["traceId"] == "trace-jobs"
    assert finding["nodeKeys"] == ["db:query:notes"]
    link = finding["link"]
    assert isinstance(link, str)
    assert link.startswith("http://127.0.0.1:9477/?")
    assert "trace=trace-jobs" in link
    assert "finding=repeated-query" in link
    assert "db%3Aquery%3Anotes" in link or "db:query:notes" in link


def test_get_finding_returns_one_match() -> None:
    """The code and the trace id together pick the finding."""
    body = get_finding(_story(), code="repeated-query", trace_id="trace-jobs")
    finding = body["finding"]
    assert isinstance(finding, dict)
    assert finding["code"] == "repeated-query"
    assert get_finding(_story(), code="missing", trace_id="trace-jobs")["note"] == (
        "No finding with that code in this trace."
    )


def test_get_report_leaves_out_assets_and_raw_events() -> None:
    """The default report matches the UI export: no asset noise and no event dump."""
    events = [
        *_story(),
        _event(
            "asset",
            nodeKey="next:request:webpack",
            layer="next",
            kind="request",
            name="GET /_next/static/chunks/webpack.js",
            service="",
            ts=1_700_000_001_100,
        ),
    ]
    text = get_report(events, trace_id="trace-jobs")
    assert text.startswith("# stack-inspect report")
    assert "select count(*) from notes" in text
    assert "webpack" not in text
    assert "## Events" not in text


def test_list_stories_names_the_trace() -> None:
    """A story summary carries the id, the start, the names and the layers."""
    stories = list_stories(_story())["stories"]
    assert isinstance(stories, list)
    story = stories[0]
    assert isinstance(story, dict)
    assert story["traceId"] == "trace-jobs"
    assert story["started"] == _story()[0]["ts"]
    assert "POST /jobs" in story["names"]
    assert story["layers"] == ["api", "db"]


def test_get_graph_filters_a_story_and_stops_at_the_limit() -> None:
    """A name filter returns that node, and an unfiltered story over the limit does not."""
    events = _story()
    narrowed = get_graph(events, trace_id="trace-jobs", name="notes")
    nodes = narrowed["nodes"]
    assert isinstance(nodes, list)
    assert [node["name"] for node in nodes if isinstance(node, dict)] == ["select count(*) from notes"]
    wide = [
        _event(
            f"n-{index}",
            nodeKey=f"api:request:/item/{index}",
            kind="request",
            layer="api",
            name=f"GET /item/{index}",
        )
        for index in range(81)
    ]
    capped = get_graph(wide, trace_id="trace-jobs")
    assert capped["nodeCount"] == len(wide)
    assert "nodes" not in capped
    assert capped["note"] == "This reply is over the limit. Narrow the question with a layer or a name."


def test_neighbourhood_includes_the_edge_and_the_finding() -> None:
    """The node, the edge that touches it, and the finding that names it come back together."""
    body = get_node_neighbourhood(_story(), node_key="db:query:notes")
    node = body["node"]
    assert isinstance(node, dict)
    assert node["nodeKey"] == "db:query:notes"
    edges = body["edges"]
    assert isinstance(edges, list)
    assert edges[0]["from"] == "api:request:POST /jobs"
    assert edges[0]["to"] == "db:query:notes"
    findings = body["findings"]
    assert isinstance(findings, list)
    assert findings[0]["code"] == "repeated-query"


def test_mcp_route_refuses_a_remote_client(tmp_path: Path) -> None:
    """The MCP route is on the collector, and a non-loopback client is still refused."""
    app = create_app(EventLog(tmp_path / "events.db"))
    mounted = [route for route in app.routes if getattr(route, "path", None) == "/mcp"]
    assert len(mounted) == 1
    remote = TestClient(app, client=("10.0.0.1", 9))
    response = remote.get("/mcp")
    assert response.status_code == HTTPStatus.FORBIDDEN
    assert response.json()["error"] == "loopback only"
