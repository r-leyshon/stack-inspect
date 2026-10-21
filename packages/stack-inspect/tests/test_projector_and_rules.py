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


def test_effect_cause_ids_link_a_fetch() -> None:
    """A request that names an effect event draws an observed caused edge."""
    events = [
        _event(
            id="effect-1",
            phase="instant",
            kind="effect",
            layer="browser",
            nodeKey="browser:effect:AudioUploader",
            name="AudioUploader",
            attributes={"component": "AudioUploader", "restarted": False},
        ),
        _event(
            id="fetch-1",
            phase="instant",
            kind="request",
            layer="browser",
            nodeKey="browser:request:/blob",
            name="GET /blob",
            causeIds=["effect-1"],
            ts=2,
            attributes={"method": "GET", "path": "/blob", "triggeredBy": "AudioUploader"},
        ),
    ]
    edges = [edge for edge in project(events).edges if edge.kind == "caused"]
    assert len(edges) == 1
    assert edges[0].origin == "browser:effect:AudioUploader"
    assert edges[0].target == "browser:request:/blob"


def test_cause_ids_become_a_caused_edge() -> None:
    """A render that names the state update which preceded it draws a caused edge."""
    events = [
        _event(
            id="state",
            phase="instant",
            kind="state-update",
            layer="browser",
            nodeKey="browser:state:Fanout",
            name="Fanout",
        ),
        _event(
            id="render",
            phase="instant",
            kind="render",
            layer="browser",
            nodeKey="browser:render:FanChild",
            name="FanChild",
            causeIds=["state"],
            ts=2,
        ),
    ]
    graph = project(events)
    assert any(
        edge.origin == "browser:state:Fanout" and edge.target == "browser:render:FanChild" and edge.kind == "caused"
        for edge in graph.edges
    )


def test_sent_span_id_causes_the_next_hop() -> None:
    """The span id a caller sent becomes a caused edge when the next hop records it."""
    events = [
        _event(
            id="browser",
            nodeKey="browser:request:/api/items",
            layer="browser",
            name="GET /api/items",
            attributes={"spanId": "abc123abc123abcd"},
        ),
        _event(
            id="api",
            nodeKey="api:request:GET /api/items",
            name="GET /api/items",
            ts=2,
            attributes={"parentSpanId": "abc123abc123abcd", "spanId": "ffffffffffffffff"},
        ),
        _event(
            id="api-end",
            phase="end",
            parentId="api",
            ts=3,
            attributes={"parentSpanId": "abc123abc123abcd"},
        ),
    ]
    caused = [edge for edge in project(events).edges if edge.kind == "caused"]
    assert len(caused) == 1
    assert caused[0].origin == "browser:request:/api/items"
    assert caused[0].target == "api:request:GET /api/items"
    assert caused[0].count == 1


def test_a_hop_does_not_cause_itself() -> None:
    """A request's own span id is not a cause of that same request."""
    events = [
        _event(attributes={"spanId": "abc123abc123abcd", "parentSpanId": "abc123abc123abcd"}),
    ]
    assert [edge for edge in project(events).edges if edge.kind == "caused"] == []


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


def test_a_click_counts_distinct_presses_not_extra_fetches() -> None:
    """Two presses that share one call count as two, and a double fetch inside one press still counts as one."""
    dashboard = {
        "nodeKey": "browser:request:/api/dashboard",
        "kind": "request",
        "layer": "browser",
        "name": "GET /api/dashboard",
    }
    stream = {
        "nodeKey": "browser:request:/api/stream",
        "kind": "request",
        "layer": "browser",
        "name": "GET /api/stream",
    }
    events = [
        _event(
            id="click-1",
            phase="instant",
            kind="interaction",
            layer="browser",
            nodeKey="browser:interaction:Load dashboard",
            name="Load dashboard",
        ),
        _event(id="fetch-1", parentId="click-1", ts=2, **dashboard),
        _event(id="fetch-1b", parentId="click-1", ts=3, **dashboard),
        _event(
            id="click-2",
            phase="instant",
            kind="interaction",
            layer="browser",
            nodeKey="browser:interaction:Load dashboard",
            name="Load dashboard",
            ts=4,
        ),
        _event(id="fetch-2", parentId="click-2", ts=5, **dashboard),
        _event(id="fetch-stream", parentId="click-2", ts=6, **stream),
    ]
    edges = {
        edge.target: edge
        for edge in project(events).edges
        if edge.origin == "browser:interaction:Load dashboard" and edge.kind == "contained"
    }
    presses = sum(event["kind"] == "interaction" for event in events)
    dashboard_fetches = sum(event["nodeKey"] == "browser:request:/api/dashboard" for event in events)
    dashboard = edges["browser:request:/api/dashboard"]
    stream_edge = edges["browser:request:/api/stream"]
    assert dashboard.count == dashboard_fetches
    assert dashboard.followed == presses
    assert stream_edge.followed == sum(
        event.get("parentId") == "click-2" and event["nodeKey"] == "browser:request:/api/stream" for event in events
    )


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
            ts=index * 1000,
            phase="instant",
            attributes={"fingerprint": "same"},
        )
        for index in range(1, 4)
    ]
    findings = analyse(events)
    match = next(finding for finding in findings if finding.code == "repeated-query")
    assert match.at == events[-1]["ts"]
    assert match.node_keys == ("db:query:same",)
    runs = 3
    span_ms = 2000
    assert match.count == runs
    assert match.duration_ms == span_ms
    assert "over 2.0s" in match.detail


def test_duplicated_edge_counts_extra_runs() -> None:
    """Extra runs of the same request become one duplicated edge with a count."""
    request = {
        "nodeKey": "api:request:GET /api/dashboard",
        "name": "GET /api/dashboard",
        "attributes": {"method": "GET", "path": "/api/dashboard"},
    }
    events = [
        _event(id="parent", nodeKey="browser:interaction:load", kind="interaction", layer="browser", name="load"),
        _event(id="a", parentId="parent", ts=2, **request),
        _event(id="b", parentId="parent", ts=3, phase="instant", **request),
        _event(id="c", parentId="parent", ts=4, phase="instant", **request),
    ]
    edges = [edge for edge in project(events).edges if edge.kind == "duplicated"]
    assert len(edges) == 1
    assert edges[0].origin == "browser:interaction:load"
    assert edges[0].target == "api:request:GET /api/dashboard"
    assert edges[0].count == len(events) - 2  # parent plus the first request are not extras


def test_duplicated_edge_skips_self_loops() -> None:
    """Repeated work on one node without a parent does not draw a loop."""
    events = [
        _event(
            id="a",
            ts=1,
            nodeKey="api:request:GET /api/dashboard",
            name="GET /api/dashboard",
            attributes={"method": "GET", "path": "/api/dashboard"},
        ),
        _event(
            id="b",
            ts=2,
            phase="instant",
            nodeKey="api:request:GET /api/dashboard",
            name="GET /api/dashboard",
            attributes={"method": "GET", "path": "/api/dashboard"},
        ),
    ]
    graph = project(events)
    assert graph.nodes["api:request:GET /api/dashboard"].count == len(events)
    assert not any(edge.kind == "duplicated" for edge in graph.edges)


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
        _event(
            id="a",
            ts=1,
            nodeKey="api:request:GET /api/dashboard",
            name="GET /api/dashboard",
            attributes={"method": "GET", "path": "/api/dashboard"},
        ),
        _event(
            id="b",
            ts=2,
            phase="instant",
            nodeKey="api:request:GET /api/dashboard",
            name="GET /api/dashboard",
            attributes={"method": "GET", "path": "/api/dashboard"},
        ),
    ]
    match = next(finding for finding in analyse(events) if finding.code == "duplicate-request")
    assert match.node_keys == ("api:request:GET /api/dashboard",)
    assert match.title == "Duplicate request"
    assert match.idempotent is True
    assert match.method == "GET"
    assert "over 1ms" in match.detail


def test_duplicate_non_idempotent_request() -> None:
    """A repeated POST is titled as non-idempotent and carries timing."""
    events = [
        _event(
            id="a",
            ts=1000,
            nodeKey="api:request:POST /tokens",
            name="POST /tokens",
            attributes={"method": "POST", "path": "/tokens"},
        ),
        _event(
            id="b",
            ts=4100,
            phase="instant",
            nodeKey="api:request:POST /tokens",
            name="POST /tokens",
            attributes={"method": "POST", "path": "/tokens"},
        ),
        _event(
            id="c",
            ts=4200,
            phase="instant",
            nodeKey="api:request:POST /tokens",
            name="POST /tokens",
            attributes={"method": "POST", "path": "/tokens"},
        ),
        _event(
            id="d",
            ts=4300,
            phase="instant",
            nodeKey="api:request:POST /tokens",
            name="POST /tokens",
            attributes={"method": "POST", "path": "/tokens"},
        ),
    ]
    match = next(finding for finding in analyse(events) if finding.code == "duplicate-request")
    assert match.title == "Duplicate non-idempotent request"
    assert match.idempotent is False
    assert match.method == "POST"
    runs = 4
    span_ms = 3300
    assert match.count == runs
    assert match.duration_ms == span_ms
    assert "POST /tokens ran 4 times over 3.3s" in match.detail


def test_duplicate_request_notes_a_double_mount() -> None:
    """When the same component mounted twice, the duplicate detail says so."""
    events = [
        _event(
            id="m1",
            ts=1,
            kind="mount",
            layer="browser",
            nodeKey="browser:mount:AudioUploader",
            name="AudioUploader",
        ),
        _event(
            id="m2",
            ts=2,
            kind="mount",
            layer="browser",
            nodeKey="browser:mount:AudioUploader",
            name="AudioUploader",
        ),
        _event(
            id="r1",
            ts=3,
            kind="render",
            layer="browser",
            nodeKey="browser:render:AudioUploader",
            name="AudioUploader",
        ),
        _event(
            id="a",
            ts=4,
            nodeKey="api:request:GET /blob",
            name="GET /blob",
            attributes={"method": "GET", "path": "/blob"},
        ),
        _event(
            id="b",
            ts=5,
            phase="instant",
            nodeKey="api:request:GET /blob",
            name="GET /blob",
            attributes={"method": "GET", "path": "/blob"},
        ),
    ]
    match = next(finding for finding in analyse(events) if finding.code == "duplicate-request")
    assert "AudioUploader mounted 2 times in this story" in match.detail


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
