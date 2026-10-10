"""HTTP API and the single-page UI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from stack_inspect.mcp_server import attach_mcp, bind, collector_lifespan, mcp_application
from stack_inspect.model import GraphEvent, validate_event
from stack_inspect.projector import Span, project
from stack_inspect.report import build_report, render_markdown
from stack_inspect.rules import analyse
from stack_inspect.source import SOURCE_LIMITS, DeclaredEdge, DeclaredStore, declared_for_graph

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint

    from stack_inspect.store import EventLog

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def create_app(log: EventLog, roots: list[Path] | None = None) -> FastAPI:  # noqa: C901 # route registration is a flat list, not nested logic
    """Return the collector application bound to ``log``. Named ``roots`` are read now."""
    app, source = _collector_app(log, roots)

    @app.middleware("http")
    async def loopback_only(request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Refuse anything that did not arrive from this machine."""
        if request.client is not None and request.client.host not in _LOOPBACK:
            return JSONResponse({"error": "loopback only"}, status_code=403)
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        """Report that the collector is up."""
        return {"status": "ok"}

    @app.post("/v1/events")
    async def post_event(request: Request) -> Response:
        """Append one event, or a JSON list of events."""
        payload = await request.json()
        items = payload if isinstance(payload, list) else [payload]
        accepted = 0
        for item in items:
            event = validate_event(item)
            if event is None:
                continue
            log.append(event)
            accepted += 1
        return JSONResponse({"accepted": accepted})

    @app.delete("/v1/events")
    def delete_events() -> dict[str, str]:
        """Remove every stored event and read named roots again. Test runs call this between scenarios."""
        log.clear()
        source.read()
        return {"status": "cleared"}

    @app.get("/v1/events")
    def list_events() -> dict[str, object]:
        """Return the raw event log."""
        events = log.all_events()
        return {"events": events}

    @app.post("/v1/declared")
    def read_source() -> dict[str, object]:
        """Read the configured application roots. This does not append to the event log."""
        snapshot = source.read()
        drawn = _declared_edges(log.all_events(), snapshot.edges)
        return {
            "edges": [_declared_payload(edge) for edge in snapshot.edges],
            "drawn": len(drawn),
            "note": snapshot.note,
            "limits": SOURCE_LIMITS,
            "typescript": snapshot.typescript,
            "refused": list(snapshot.refused),
        }

    @app.get("/v1/graph")
    def graph() -> dict[str, object]:
        """Return nodes and accumulated edges, including declared edges whose ends were observed."""
        snapshot = source.read()
        projected = project(log.all_events())
        observed = [
            {
                "from": edge.origin,
                "to": edge.target,
                "kind": edge.kind,
                "source": edge.source,
                "count": edge.count,
                "followed": edge.followed,
                "firstSeen": edge.first_seen,
                "lastSeen": edge.last_seen,
            }
            for edge in projected.edges
        ]
        declared = [
            _declared_payload(edge) | {"count": 1, "firstSeen": 0, "lastSeen": 0}
            for edge in _declared_edges(log.all_events(), snapshot.edges)
        ]
        return {
            "nodes": [
                {
                    "nodeKey": node.node_key,
                    "kind": node.kind,
                    "layer": node.layer,
                    "name": node.name,
                    "service": node.service,
                    "count": node.count,
                }
                for node in projected.nodes.values()
            ],
            "edges": observed + declared,
            "sourceNote": snapshot.note,
        }

    @app.get("/v1/findings")
    def findings() -> dict[str, object]:
        """Return the analysis findings for the current log."""
        return {
            "findings": [
                {
                    "code": finding.code,
                    "title": finding.title,
                    "traceId": finding.trace_id,
                    "detail": finding.detail,
                    "at": finding.at,
                    "nodeKeys": list(finding.node_keys),
                }
                for finding in analyse(log.all_events())
            ],
        }

    @app.get("/v1/traces")
    def traces() -> dict[str, object]:
        """Return one summary per trace, for the timeline."""
        projected = project(log.all_events())
        summaries = [_trace_summary(trace_id, spans) for trace_id, spans in projected.spans_by_trace.items()]
        summaries.sort(key=lambda summary: summary["started"] if isinstance(summary["started"], int | float) else 0)
        return {"traces": summaries}

    @app.get("/v1/report")
    def report(trace: str | None = None, assets: int = 0, events: int = 0, format: str = "md") -> Response:  # noqa: A002 # format matches the query parameter a client sends
        """Download a digest of the log. Markdown by default, JSON when asked."""
        body = build_report(
            log.all_events(),
            trace_id=trace or None,
            include_assets=assets == 1,
            include_events=events == 1,
            declared=source.read().edges,
        )
        if format == "json":
            return JSONResponse(
                body,
                headers={"content-disposition": 'attachment; filename="stack-inspect.json"'},
            )
        markdown = render_markdown(body)
        return Response(
            markdown,
            media_type="text/markdown; charset=utf-8",
            headers={"content-disposition": 'attachment; filename="stack-inspect.md"'},
        )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        """Serve the timeline, dependency graph and findings."""
        return _UI_PATH.read_text(encoding="utf-8")

    source.read()
    return app


def _collector_app(log: EventLog, roots: list[Path] | None) -> tuple[FastAPI, DeclaredStore]:
    """Return the application, with the read-only MCP route attached."""
    source = DeclaredStore(list(roots or []))
    bind(log, source)
    mcp_app = mcp_application()
    app = FastAPI(title="stack-inspect", docs_url=None, redoc_url=None, lifespan=collector_lifespan(mcp_app))
    attach_mcp(app, mcp_app)
    return app, source


def _declared_edges(events: list[GraphEvent], edges: tuple[DeclaredEdge, ...]) -> list[DeclaredEdge]:
    """Return declared edges that can be drawn on top of ``events``."""
    projected = project(events)
    observed = [(edge.origin, edge.target, edge.kind) for edge in projected.edges]
    return declared_for_graph(edges, projected.nodes, observed)


def _declared_payload(edge: DeclaredEdge) -> dict[str, object]:
    """Return the JSON shape of one declared edge."""
    return {
        "from": edge.origin,
        "to": edge.target,
        "kind": edge.kind,
        "source": "declared",
        "originAt": edge.origin_at,
        "targetAt": edge.target_at,
    }


def _trace_summary(trace_id: str, spans: list[Span]) -> dict[str, object]:
    """Return one trace, with each span placed so the timeline can draw it."""
    ordered = sorted(spans, key=lambda span: span.start)
    return {
        "traceId": trace_id,
        "started": ordered[0].start if ordered else 0,
        "names": [span.name for span in ordered],
        "layers": sorted({span.layer for span in ordered}),
        "spans": [_span_payload(span) for span in ordered],
    }


def _span_payload(span: Span) -> dict[str, object]:
    """Return one span, including opted-in parameter values when they were recorded."""
    body: dict[str, object] = {
        "name": span.name,
        "layer": span.layer,
        "service": span.service,
        "kind": span.kind,
        "nodeKey": span.node_key,
        "start": span.start,
        "end": span.end if span.end is not None else span.start,
    }
    for key in ("parameters", "query", "pathParams", "rows", "state"):
        if key in span.attributes:
            body[key] = span.attributes[key]
    return body


def default_log_path() -> Path:
    """Return the log path, under the system temp directory."""
    return Path.home() / ".stack-inspect" / "events.db"


_UI_PATH = Path(__file__).with_name("ui.html")
