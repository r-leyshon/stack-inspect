"""HTTP API and the single-page UI."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from stack_inspect.model import validate_event
from stack_inspect.projector import project
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
        events = log.all_events()
        projected = project(events)
        summaries: list[dict[str, object]] = []
        for trace_id, spans in projected.spans_by_trace.items():
            names = [span.name for span in spans]
            summaries.append(
                {
                    "traceId": trace_id,
                    "names": names,
                    "started": spans[0].start if spans else 0,
                },
            )
        return {"traces": summaries}

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        """Serve the timeline and dependency views."""
        return _PAGE

    return app


def default_log_path() -> Path:
    """Return the log path, under the system temp directory."""
    return Path.home() / ".stack-inspect" / "events.db"


_PAGE = """<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="utf-8" />
  <title>stack-inspect</title>
  <style>
    :root { color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }
    body { margin: 0; display: grid; grid-template-columns: 280px 1fr 320px; min-height: 100vh; }
    aside, main { padding: 1rem 1.25rem; }
    aside { border-right: 1px solid #8884; }
    h1 { font-size: 1.1rem; margin: 0 0 0.75rem; }
    h2 { font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.04em; margin: 1rem 0 0.4rem; }
    ul { list-style: none; padding: 0; margin: 0; }
    li { padding: 0.35rem 0.2rem; border-bottom: 1px solid #8883; font-size: 0.9rem; }
    .meta { color: #888; font-size: 0.75rem; }
    .finding { background: #a30a1; }
  </style>
</head>
<body>
  <aside>
    <h1>stack-inspect</h1>
    <h2>Traces</h2>
    <ul id="traces"></ul>
  </aside>
  <main>
    <h2>Timeline</h2>
    <ul id="timeline"></ul>
    <h2>Dependency graph</h2>
    <ul id="edges"></ul>
  </main>
  <aside>
    <h2>Findings</h2>
    <ul id="findings"></ul>
  </aside>
  <script>
    async function refresh() {
      const [traces, graph, findings] = await Promise.all([
        fetch("/v1/traces").then((response) => response.json()),
        fetch("/v1/graph").then((response) => response.json()),
        fetch("/v1/findings").then((response) => response.json()),
      ]);
      document.getElementById("traces").innerHTML = traces.traces.map((trace) =>
        `<li data-trace="${trace.traceId}">${trace.names.map((name) => `<div>${name}</div>`).join("")}</li>`
      ).join("");
      const selected = traces.traces[traces.traces.length - 1];
      document.getElementById("timeline").innerHTML = selected
        ? selected.names.map((name) => `<li>${name}</li>`).join("")
        : "";
      document.getElementById("edges").innerHTML = graph.edges.map((edge) =>
        `<li>${edge.from} → ${edge.to} <span class="meta">${edge.kind}, observed ${edge.count}</span></li>`
      ).join("");
      document.getElementById("findings").innerHTML = findings.findings.map((finding) =>
        `<li class="finding" data-code="${finding.code}">` +
        `<strong>${finding.title}</strong><div class="meta">${finding.detail}</div></li>`
      ).join("");
    }
    refresh();
    setInterval(refresh, 1000);
  </script>
</body>
</html>
"""
