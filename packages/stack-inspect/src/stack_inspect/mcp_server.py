"""Read-only MCP tools over the same projection the UI uses."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from starlette.routing import Route

from stack_inspect.projector import Span, project
from stack_inspect.report import build_report, render_markdown
from stack_inspect.rules import analyse, finding_dict
from stack_inspect.source import declared_for_graph

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable, Collection
    from contextlib import AbstractAsyncContextManager

    from fastapi import FastAPI
    from starlette.applications import Starlette

    from stack_inspect.model import GraphEvent
    from stack_inspect.projector import GraphEdge, GraphNode
    from stack_inspect.rules import Finding
    from stack_inspect.source import DeclaredEdge, DeclaredStore
    from stack_inspect.store import EventLog

_NODE_LIMIT = 80
_EDGE_LIMIT = 160
_NARROW = "This reply is over the limit. Narrow the question with a layer or a name."
_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

_log: EventLog | None = None
_source: DeclaredStore | None = None


def bind(log: EventLog, source: DeclaredStore) -> None:
    """Point the tools at the collector's log. ``create_app`` calls this once."""
    global _log, _source  # noqa: PLW0603 # one collector process, one log
    _log = log
    _source = source


def list_findings(events: list[GraphEvent]) -> dict[str, object]:
    """Return each finding, in analysis order, with a link that opens it."""
    findings = analyse(events)
    return {"findings": [_finding_payload(finding, findings) for finding in findings]}


def get_finding(
    events: list[GraphEvent],
    *,
    code: str,
    trace_id: str,
    declared: tuple[DeclaredEdge, ...] = (),
) -> dict[str, object]:
    """Return the finding with this code in this story, plus its neighbourhood slice."""
    findings = analyse(events)
    matches = [finding for finding in findings if finding.code == code and finding.trace_id == trace_id]
    if not matches:
        return {"note": "No finding with that code in this trace."}
    if len(matches) == 1:
        finding = matches[0]
        body: dict[str, object] = {"finding": _finding_payload(finding, findings)}
        neighbourhood = _finding_neighbourhood(events, finding, declared=declared)
        if neighbourhood is not None:
            body["neighbourhood"] = neighbourhood
        return body
    return {
        "findings": [_finding_payload(finding, findings) for finding in matches],
        "note": "Several findings share this code and trace. Each link opens one of them.",
    }


def get_report(
    events: list[GraphEvent],
    *,
    trace_id: str | None = None,
    declared: tuple[DeclaredEdge, ...] = (),
) -> str:
    """Return the Markdown report. Asset noise and the raw event list stay out."""
    body = build_report(
        events,
        trace_id=trace_id or None,
        include_assets=False,
        include_events=False,
        declared=declared,
    )
    return render_markdown(body)


def list_stories(events: list[GraphEvent]) -> dict[str, object]:
    """Return one summary per story: its id, when it started, names and layers."""
    projected = project(events)
    stories = [_story(trace_id, spans) for trace_id, spans in projected.spans_by_trace.items()]
    stories.sort(key=lambda story: story["started"] if isinstance(story["started"], int | float) else 0)
    return {"stories": stories}


def get_graph(
    events: list[GraphEvent],
    *,
    trace_id: str,
    layer: str | None = None,
    name: str | None = None,
    declared: tuple[DeclaredEdge, ...] = (),
) -> dict[str, object]:
    """Return nodes and edges for one story. A large story asks for a narrower question."""
    if not trace_id:
        return {"note": "Pass a traceId from list_stories."}
    story = [event for event in events if event["traceId"] == trace_id]
    if not story:
        return {"traceId": trace_id, "note": "That story is not in the log."}
    return _graph_slice(story, trace_id, layer, name, declared)


def get_node_neighbourhood(
    events: list[GraphEvent],
    *,
    node_key: str,
    declared: tuple[DeclaredEdge, ...] = (),
) -> dict[str, object]:
    """Return one node, the edges that touch it, and the findings that name it."""
    projected = project(events)
    node = projected.nodes.get(node_key)
    if node is None:
        return {"note": "That node is not in the log."}
    observed = [edge for edge in projected.edges if node_key in {edge.origin, edge.target}]
    drawn = _declared_edges(set(projected.nodes), observed, declared)
    incident = [edge for edge in drawn if node_key in {edge.origin, edge.target}]
    findings = analyse(events)
    named = [finding for finding in findings if node_key in finding.node_keys]
    body: dict[str, object] = {
        "node": _node_payload(node),
        "edgeCount": len(observed) + len(incident),
        "findings": [_finding_payload(finding, findings) for finding in named],
    }
    if len(observed) + len(incident) > _EDGE_LIMIT:
        body["note"] = "Too many edges touch this node. Ask for one story with get_graph."
        return body
    body["edges"] = [_edge_payload(edge) for edge in observed] + [_declared_payload(edge) for edge in incident]
    return body


def _finding_neighbourhood(
    events: list[GraphEvent],
    finding: Finding,
    *,
    declared: tuple[DeclaredEdge, ...] = (),
) -> dict[str, object] | None:
    """Return the ego graph around a finding's node keys (same slice the UI opens)."""
    if not finding.node_keys:
        return None
    story = [event for event in events if event["traceId"] == finding.trace_id]
    projected = project(story if story else events)
    seeds = {key for key in finding.node_keys if key in projected.nodes}
    if not seeds:
        return None
    keys = set(seeds)
    for edge in projected.edges:
        if edge.origin in seeds:
            keys.add(edge.target)
        if edge.target in seeds:
            keys.add(edge.origin)
    nodes = [projected.nodes[key] for key in keys if key in projected.nodes]
    observed = [edge for edge in projected.edges if edge.origin in keys and edge.target in keys]
    drawn = _declared_edges(keys, observed, declared)
    body: dict[str, object] = {
        "traceId": finding.trace_id,
        "nodeCount": len(nodes),
        "edgeCount": len(observed) + len(drawn),
        "nodeKeys": sorted(seeds),
    }
    if len(nodes) > _NODE_LIMIT or len(observed) + len(drawn) > _EDGE_LIMIT:
        body["note"] = _NARROW
        return body
    body["nodes"] = [_node_payload(node) for node in nodes]
    body["edges"] = [_edge_payload(edge) for edge in observed] + [_declared_payload(edge) for edge in drawn]
    return body


def mcp_application() -> Starlette:
    """Return the Streamable HTTP app served at ``/mcp``."""
    server = MCPServer(
        "stack-inspect",
        instructions=(
            "Read the stack-inspect collector. Findings, reports and graph slices come from the same "
            "projection as the UI. Cite code, nodeKey and traceId. Do not invent an edge. "
            "Node runs and count are how many times that nodeKey ran in the story. "
            "Duplicate and repeated findings include durationMs and siblings in the same trace. "
            "get_finding returns the finding-neighbourhood slice, not the whole story. "
            "Unchanged re-renders are one ranked summary per story with offenders. "
            "A graph over the limit returns only nodeCount and edgeCount until narrowed."
        ),
    )
    _register(server)
    return server.streamable_http_app(streamable_http_path="/", stateless_http=True, json_response=True)


def collector_lifespan(mcp_app: Starlette) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Return a lifespan that starts the MCP session manager."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
        async with mcp_app.router.lifespan_context(mcp_app):
            yield

    return lifespan


def attach_mcp(app: FastAPI, mcp_app: Starlette) -> None:
    """Serve MCP at ``/mcp`` on the collector application."""
    mcp_route = next(route for route in mcp_app.routes if isinstance(route, Route) and route.path == "/")
    app.routes.append(Route("/mcp", endpoint=mcp_route.endpoint))


def _register(server: MCPServer) -> None:
    """Register the read tools. They read the log bound by ``bind``."""

    @server.tool(name="list_findings", annotations=_READ_ONLY, structured_output=False)
    def list_findings_tool() -> dict[str, object]:
        """List findings with timing, method, idempotent, siblings in the same story, and a UI link."""
        return list_findings(_events())

    @server.tool(name="get_finding", annotations=_READ_ONLY, structured_output=False)
    def get_finding_tool(code: str, trace_id: str) -> dict[str, object]:
        """Return one finding by code and trace, with siblings and its neighbourhood slice."""
        return get_finding(_events(), code=code, trace_id=trace_id, declared=_declared())

    @server.tool(name="get_report", annotations=_READ_ONLY, structured_output=False)
    def get_report_tool(trace_id: str = "") -> str:
        """Return the Markdown report for the log, or for one story when a trace id is given."""
        return get_report(_events(), trace_id=trace_id or None, declared=_declared())

    @server.tool(name="list_stories", annotations=_READ_ONLY, structured_output=False)
    def list_stories_tool() -> dict[str, object]:
        """List stories. Each summary has its trace id, start time, names and layers."""
        return list_stories(_events())

    @server.tool(name="get_graph", annotations=_READ_ONLY, structured_output=False)
    def get_graph_tool(trace_id: str, layer: str = "", name: str = "") -> dict[str, object]:
        """Return nodes and edges for one story. Each node has runs and count. Over the limit, only counts."""
        return get_graph(_events(), trace_id=trace_id, layer=layer or None, name=name or None, declared=_declared())

    @server.tool(name="get_node_neighbourhood", annotations=_READ_ONLY, structured_output=False)
    def get_node_neighbourhood_tool(node_key: str) -> dict[str, object]:
        """Return one node (with runs), the edges that touch it, and the findings that name it."""
        return get_node_neighbourhood(_events(), node_key=node_key, declared=_declared())


def _events() -> list[GraphEvent]:
    """Return the bound log, or nothing when the tools are not mounted."""
    if _log is None:
        return []
    return _log.all_events()


def _declared() -> tuple[DeclaredEdge, ...]:
    """Return declared edges from the bound source, or none."""
    if _source is None:
        return ()
    return _source.read().edges


def _story(trace_id: str, spans: list[Span]) -> dict[str, object]:
    """Return the fields the timeline uses to name one story."""
    ordered = sorted(spans, key=lambda span: span.start)
    return {
        "traceId": trace_id,
        "started": ordered[0].start if ordered else 0,
        "names": [span.name for span in ordered],
        "layers": sorted({span.layer for span in ordered}),
    }


def _graph_slice(
    story: list[GraphEvent],
    trace_id: str,
    layer: str | None,
    name: str | None,
    declared: tuple[DeclaredEdge, ...],
) -> dict[str, object]:
    """Return one story's graph, or counts and a note when it is over the limit."""
    projected = project(story)
    nodes = _matching_nodes(list(projected.nodes.values()), layer, name)
    keys = {node.node_key for node in nodes}
    observed = [edge for edge in projected.edges if edge.origin in keys and edge.target in keys]
    drawn = _declared_edges(keys, observed, declared)
    body: dict[str, object] = {"traceId": trace_id, "nodeCount": len(nodes), "edgeCount": len(observed) + len(drawn)}
    if len(nodes) > _NODE_LIMIT or len(observed) + len(drawn) > _EDGE_LIMIT:
        body["note"] = _NARROW
        return body
    body["nodes"] = [_node_payload(node) for node in nodes]
    body["edges"] = [_edge_payload(edge) for edge in observed] + [_declared_payload(edge) for edge in drawn]
    return body


def _matching_nodes(nodes: list[GraphNode], layer: str | None, name: str | None) -> list[GraphNode]:
    """Keep nodes in ``layer`` whose name contains ``name``."""
    chosen = nodes
    if layer:
        chosen = [node for node in chosen if node.layer == layer]
    if name:
        needle = name.casefold()
        chosen = [node for node in chosen if needle in node.name.casefold()]
    return chosen


def _declared_edges(
    node_keys: Collection[str],
    observed: list[GraphEdge],
    declared: tuple[DeclaredEdge, ...],
) -> list[DeclaredEdge]:
    """Return declared edges that the graph can draw beside ``observed``."""
    seen = [(edge.origin, edge.target, edge.kind) for edge in observed]
    return declared_for_graph(declared, node_keys, seen)


def _finding_payload(finding: Finding, all_findings: list[Finding]) -> dict[str, object]:
    """Return one finding in the same shape as ``GET /v1/findings``, plus its UI link."""
    key = f"{finding.code}:{finding.trace_id}:{'|'.join(finding.node_keys)}:{finding.detail}"
    body = finding_dict(finding, all_findings=all_findings)
    body["link"] = _ui_link(finding.trace_id, key)
    return body


def _ui_link(trace_id: str, finding: str) -> str:
    """Return the collector page opened on this finding."""
    port = os.environ.get("STACK_INSPECT_PORT", "9477")
    return f"http://127.0.0.1:{port}/?{urlencode({'trace': trace_id, 'finding': finding})}"


def _node_payload(node: GraphNode) -> dict[str, object]:
    """Return one node in the same shape as ``GET /v1/graph``, with ``runs`` for agents."""
    return {
        "nodeKey": node.node_key,
        "kind": node.kind,
        "layer": node.layer,
        "name": node.name,
        "service": node.service,
        "count": node.count,
        "runs": node.count,
    }


def _edge_payload(edge: GraphEdge) -> dict[str, object]:
    """Return one observed edge in the same shape as ``GET /v1/graph``."""
    return {
        "from": edge.origin,
        "to": edge.target,
        "kind": edge.kind,
        "source": edge.source,
        "count": edge.count,
        "followed": edge.followed,
        "firstSeen": edge.first_seen,
        "lastSeen": edge.last_seen,
    }


def _declared_payload(edge: DeclaredEdge) -> dict[str, object]:
    """Return one declared edge in the same shape as ``GET /v1/graph``."""
    return {
        "from": edge.origin,
        "to": edge.target,
        "kind": edge.kind,
        "source": "declared",
        "count": 1,
        "firstSeen": 0,
        "lastSeen": 0,
        "originAt": edge.origin_at,
        "targetAt": edge.target_at,
    }
