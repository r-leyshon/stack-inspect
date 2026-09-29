"""Unit tests for graph projection and the analysis rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from stack_inspect.projector import project
from stack_inspect.rules import analyse

if TYPE_CHECKING:
    from stack_inspect.model import GraphEvent


def _event(**overrides: object) -> GraphEvent:
    base: GraphEvent = {
        "id": "e1",
        "traceId": "trace",
        "nodeKey": "api:request:GET /items",
        "kind": "request",
        "layer": "api",
        "phase": "start",
        "name": "GET /items",
        "ts": 1,
        "attributes": {},
    }
    for key, value in overrides.items():
        base[key] = value  # type: ignore[literal-required] # test helper assigns known event fields
    return base


def test_parent_becomes_a_contained_edge() -> None:
    """A child event produces a contained edge from its parent's node."""
    events = [
        _event(id="parent", nodeKey="api:request:GET /dash", name="GET /dash"),
        _event(
            id="child",
            parentId="parent",
            nodeKey="db:query:abc",
            kind="query",
            layer="db",
            name="select",
            ts=2,
        ),
    ]
    graph = project(events)
    assert any(
        edge.origin == "api:request:GET /dash" and edge.target == "db:query:abc" and edge.kind == "contained"
        for edge in graph.edges
    )


def test_invalidation_attribute_becomes_an_edge() -> None:
    """An event that names what it invalidates produces an invalidated edge."""
    events = [
        _event(
            id="inv",
            phase="instant",
            kind="state-update",
            layer="browser",
            nodeKey="browser:query:results",
            name="invalidate results",
            attributes={"invalidates": "browser:render:ResultsPanel"},
        ),
    ]
    graph = project(events)
    assert graph.edges[0].kind == "invalidated"
    assert graph.edges[0].target == "browser:render:ResultsPanel"


def test_edge_counts_accumulate() -> None:
    """The same relationship seen twice keeps a count of two."""
    events = [
        _event(id="p1", traceId="t1"),
        _event(id="c1", traceId="t1", parentId="p1", nodeKey="db:query:abc", kind="query", layer="db", ts=2),
        _event(id="p2", traceId="t2", ts=3),
        _event(id="c2", traceId="t2", parentId="p2", nodeKey="db:query:abc", kind="query", layer="db", ts=4),
    ]
    counts = [edge.count for edge in project(events).edges if edge.kind == "contained"]
    assert counts == [2]


def test_repeated_query_finding() -> None:
    """Three identical query fingerprints in one trace are an N+1 finding."""
    events = [
        _event(
            id=f"q{index}",
            kind="query",
            layer="db",
            nodeKey="db:query:same",
            name="select",
            ts=index,
            phase="instant",
            attributes={"fingerprint": "same"},
        )
        for index in range(1, 4)
    ]
    findings = analyse(events)
    match = next(finding for finding in findings if finding.code == "repeated-query")
    assert match.at == events[-1]["ts"]


def test_cors_masked_server_error() -> None:
    """A cross-origin 500 without an allow-origin header is flagged."""
    events = [
        _event(
            phase="instant",
            attributes={"status": 500, "crossOrigin": True, "path": "/api/crash"},
        ),
    ]
    findings = analyse(events)
    assert findings[0].code == "cors-masked-server-error"
    assert "/api/crash" in findings[0].detail


def test_rejected_preflight_names_the_header() -> None:
    """A failed preflight finding includes the header the server refused."""
    events = [
        _event(
            phase="instant",
            attributes={
                "method": "OPTIONS",
                "status": 400,
                "path": "/api/items",
                "requestedHeaders": "X-Custom-Header",
                "allowedHeaders": "content-type",
            },
        ),
    ]
    finding = analyse(events)[0]
    assert finding.code == "rejected-preflight"
    assert "X-Custom-Header" in finding.detail


def test_duplicate_request() -> None:
    """The same method and path twice in one trace is a duplicate."""
    events = [
        _event(id="a", ts=1, attributes={"method": "GET", "path": "/api/dashboard"}),
        _event(id="b", ts=2, phase="instant", attributes={"method": "GET", "path": "/api/dashboard"}),
    ]
    assert any(finding.code == "duplicate-request" for finding in analyse(events))


def test_sequential_queries() -> None:
    """Two different queries that do not overlap are flagged as sequential."""
    events = [
        _event(
            id="q1",
            kind="query",
            layer="db",
            nodeKey="db:query:one",
            name="one",
            ts=1,
            attributes={"fingerprint": "one"},
        ),
        _event(
            id="q1-end", phase="end", parentId="q1", ts=2, kind="query", layer="db", nodeKey="db:query:one", name="one"
        ),
        _event(
            id="q2",
            kind="query",
            layer="db",
            nodeKey="db:query:two",
            name="two",
            ts=3,
            attributes={"fingerprint": "two"},
        ),
        _event(
            id="q2-end", phase="end", parentId="q2", ts=4, kind="query", layer="db", nodeKey="db:query:two", name="two"
        ),
    ]
    assert any(finding.code == "sequential-awaits" for finding in analyse(events))


def test_work_after_visible() -> None:
    """A request that starts after the result was shown is flagged."""
    events = [
        _event(
            id="visible",
            phase="instant",
            kind="render",
            layer="browser",
            nodeKey="browser:render:Result",
            name="Result",
            ts=5,
            attributes={"userVisible": True},
        ),
        _event(id="late", kind="request", ts=6, attributes={"path": "/api/dashboard"}),
    ]
    assert any(finding.code == "work-after-visible" for finding in analyse(events))
