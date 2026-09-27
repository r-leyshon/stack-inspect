"""HTTP API and the single-page UI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from stack_inspect.model import validate_event
from stack_inspect.projector import Span, project
from stack_inspect.rules import analyse

if TYPE_CHECKING:
    from starlette.middleware.base import RequestResponseEndpoint

    from stack_inspect.store import EventLog

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost"})


def create_app(log: EventLog) -> FastAPI:  # noqa: C901 # route registration is a flat list, not nested logic
    """Return the collector application bound to ``log``."""
    app = FastAPI(title="stack-inspect", docs_url=None, redoc_url=None)

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
        """Remove every stored event. Test runs call this between scenarios."""
        log.clear()
        return {"status": "cleared"}

    @app.get("/v1/events")
    def list_events() -> dict[str, object]:
        """Return the raw event log."""
        events = log.all_events()
        return {"events": events}

    @app.get("/v1/graph")
    def graph() -> dict[str, object]:
        """Return nodes and accumulated edges."""
        projected = project(log.all_events())
        return {
            "nodes": [
                {
                    "nodeKey": node.node_key,
                    "kind": node.kind,
                    "layer": node.layer,
                    "name": node.name,
                    "count": node.count,
                }
                for node in projected.nodes.values()
            ],
            "edges": [
                {
                    "from": edge.origin,
                    "to": edge.target,
                    "kind": edge.kind,
                    "source": edge.source,
                    "count": edge.count,
                    "firstSeen": edge.first_seen,
                    "lastSeen": edge.last_seen,
                }
                for edge in projected.edges
            ],
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

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        """Serve the timeline, dependency graph and findings."""
        return _UI_PATH.read_text(encoding="utf-8")

    return app


def _trace_summary(trace_id: str, spans: list[Span]) -> dict[str, object]:
    """Return one trace, with each span placed so the timeline can draw it."""
    ordered = sorted(spans, key=lambda span: span.start)
    return {
        "traceId": trace_id,
        "started": ordered[0].start if ordered else 0,
        "names": [span.name for span in ordered],
        "layers": sorted({span.layer for span in ordered}),
        "spans": [
            {
                "name": span.name,
                "layer": span.layer,
                "kind": span.kind,
                "nodeKey": span.node_key,
                "start": span.start,
                "end": span.end if span.end is not None else span.start,
            }
            for span in ordered
        ],
    }


def default_log_path() -> Path:
    """Return the log path, under the system temp directory."""
    return Path.home() / ".stack-inspect" / "events.db"


_UI_PATH = Path(__file__).with_name("ui.html")
