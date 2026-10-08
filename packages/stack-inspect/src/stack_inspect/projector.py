"""Derive nodes and evidence-bearing edges from the event log."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from stack_inspect.model import GraphEvent

EdgeSource = Literal["observed", "inferred", "declared"]

DUPLICATE_EDGE_MIN = 2


@dataclass
class GraphNode:
    """A stable thing that many events can belong to."""

    node_key: str
    kind: str
    layer: str
    name: str
    service: str = ""
    count: int = 0


@dataclass
class GraphEdge:
    """A relationship between two nodes, with the evidence behind it."""

    origin: str
    target: str
    kind: str
    source: EdgeSource = "observed"
    count: int = 0
    followed: int = 0
    first_seen: float = 0
    last_seen: float = 0
    click_ids: set[str] = field(default_factory=set, compare=False, repr=False)


@dataclass
class Span:
    """A start event paired with its end, when the end has arrived."""

    event_id: str
    trace_id: str
    node_key: str
    kind: str
    name: str
    layer: str
    service: str
    start: float
    end: float | None = None
    parent_id: str | None = None
    attributes: dict[str, object] = field(default_factory=dict)


@dataclass
class ProjectedGraph:
    """Nodes, edges and per-trace spans derived from the log."""

    nodes: dict[str, GraphNode]
    edges: list[GraphEdge]
    spans_by_trace: dict[str, list[Span]]


def project(events: list[GraphEvent]) -> ProjectedGraph:
    """Build the graph described by ``events``."""
    nodes: dict[str, GraphNode] = {}
    edge_index: dict[tuple[str, str, str], GraphEdge] = {}
    spans: dict[str, Span] = {}
    spans_by_trace: dict[str, list[Span]] = {}

    for event in events:
        _accumulate_node(nodes, event)
        span = _accumulate_span(spans, spans_by_trace, event)
        if span is None:
            continue
        _edges_for_event(edge_index, spans, event, span)

    _link_span_causes(edge_index, events)
    _link_duplicates(edge_index, spans, spans_by_trace)
    return ProjectedGraph(nodes=nodes, edges=list(edge_index.values()), spans_by_trace=spans_by_trace)


def _service(event: GraphEvent) -> str:
    raw = event.get("service")
    return raw if isinstance(raw, str) else ""


def _accumulate_node(nodes: dict[str, GraphNode], event: GraphEvent) -> None:
    node = nodes.get(event["nodeKey"])
    if node is None:
        node = GraphNode(
            node_key=event["nodeKey"],
            kind=event["kind"],
            layer=event["layer"],
            name=event["name"],
            service=_service(event),
        )
        nodes[event["nodeKey"]] = node
    elif _service(event):
        node.service = _service(event)
    if event["phase"] in {"start", "instant"}:
        node.count += 1


def _accumulate_span(
    spans: dict[str, Span],
    spans_by_trace: dict[str, list[Span]],
    event: GraphEvent,
) -> Span | None:
    if event["phase"] == "end":
        target = spans.get(event["id"]) or spans.get(event.get("parentId", ""))
        if target is None:
            return None
        target.end = event["ts"]
        target.attributes.update(event.get("attributes") or {})
        return target
    span = Span(
        event_id=event["id"],
        trace_id=event["traceId"],
        node_key=event["nodeKey"],
        kind=event["kind"],
        name=event["name"],
        layer=event["layer"],
        service=_service(event),
        start=event["ts"],
        end=event["ts"] if event["phase"] == "instant" else None,
        parent_id=event.get("parentId"),
        attributes=dict(event.get("attributes") or {}),
    )
    spans[event["id"]] = span
    spans_by_trace.setdefault(event["traceId"], []).append(span)
    return span


def _edges_for_event(
    edge_index: dict[tuple[str, str, str], GraphEdge],
    spans: dict[str, Span],
    event: GraphEvent,
    span: Span,
) -> None:
    parent_id = event.get("parentId")
    if parent_id:
        parent = spans.get(parent_id)
        if parent is not None:
            kind = "emitted" if span.kind == "stream-message" else "contained"
            edge = _add_edge(edge_index, parent.node_key, span.node_key, kind, event["ts"])
            if parent.kind == "interaction":
                edge.click_ids.add(parent.event_id)
                edge.followed = len(edge.click_ids)
    for cause_id in event.get("causeIds") or []:
        cause = spans.get(cause_id)
        if cause is not None:
            _add_edge(edge_index, cause.node_key, span.node_key, "caused", event["ts"])
    invalidates = span.attributes.get("invalidates")
    if isinstance(invalidates, str):
        _add_edge(edge_index, span.node_key, invalidates, "invalidated", event["ts"])
    reads = span.attributes.get("reads")
    if isinstance(reads, str):
        _add_edge(edge_index, span.node_key, reads, "read", event["ts"])


def _link_span_causes(
    edge_index: dict[tuple[str, str, str], GraphEdge],
    events: list[GraphEvent],
) -> None:
    """Draw a caused edge where one hop recorded the span id the previous hop sent."""
    sent: dict[tuple[str, str], tuple[str, float]] = {}
    for event in events:
        if event["phase"] == "end":
            continue
        span_id = _attribute(event, "spanId")
        if span_id:
            sent[(event["traceId"], span_id)] = (event["nodeKey"], event["ts"])
    for event in events:
        if event["phase"] == "end":
            continue
        parent_span = _attribute(event, "parentSpanId")
        if not parent_span:
            continue
        origin = sent.get((event["traceId"], parent_span))
        if origin is None or origin[0] == event["nodeKey"]:
            continue
        _add_edge(edge_index, origin[0], event["nodeKey"], "caused", min(origin[1], event["ts"]))


def _attribute(event: GraphEvent, name: str) -> str:
    raw = (event.get("attributes") or {}).get(name)
    return raw if isinstance(raw, str) else ""


def _add_edge(
    edge_index: dict[tuple[str, str, str], GraphEdge],
    origin: str,
    target: str,
    kind: str,
    seen_at: float,
) -> GraphEdge:
    key = (origin, target, kind)
    edge = edge_index.get(key)
    if edge is None:
        edge = GraphEdge(
            origin=origin,
            target=target,
            kind=kind,
            count=1,
            first_seen=seen_at,
            last_seen=seen_at,
        )
        edge_index[key] = edge
        return edge
    edge.count += 1
    edge.last_seen = seen_at
    return edge


def _duplicate_group_key(span: Span) -> str | None:
    """Return a key that groups equivalent requests or queries inside one trace."""
    if span.kind == "request":
        method = str(span.attributes.get("method", "GET"))
        path = str(span.attributes.get("path", span.name))
        return f"request:{method} {path}"
    if span.kind == "query":
        fingerprint = str(span.attributes.get("fingerprint", span.node_key))
        return f"query:{fingerprint}"
    return None


def _link_duplicates(
    edge_index: dict[tuple[str, str, str], GraphEdge],
    spans: dict[str, Span],
    spans_by_trace: dict[str, list[Span]],
) -> None:
    """Record each extra request or query as a counted ``duplicated`` edge.

    The first occurrence stays the reference. Each later one draws from its
    parent when there is one, otherwise from the first occurrence's parent, so
    fifteen runs of the same work become one edge with a high count rather
    than fifteen nodes. A link that would start and end on the same node is
    skipped: the node's own count already carries that multiplicity.
    """
    for trace_spans in spans_by_trace.values():
        groups: dict[str, list[Span]] = {}
        for span in trace_spans:
            key = _duplicate_group_key(span)
            if key is None:
                continue
            groups.setdefault(key, []).append(span)
        for group in groups.values():
            if len(group) < DUPLICATE_EDGE_MIN:
                continue
            ordered = sorted(group, key=lambda item: item.start)
            first = ordered[0]
            first_parent = spans.get(first.parent_id) if first.parent_id else None
            for span in ordered[1:]:
                parent = spans.get(span.parent_id) if span.parent_id else None
                origin_span = parent or first_parent
                if origin_span is None:
                    continue
                if origin_span.node_key == span.node_key:
                    continue
                _add_edge(edge_index, origin_span.node_key, span.node_key, "duplicated", span.start)
