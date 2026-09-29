"""Declared edges are read from named roots and joined only where a run already has both ends."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import stack_inspect
from fastapi.testclient import TestClient
from stack_inspect.server import create_app
from stack_inspect.source import DeclaredStore, scan_roots
from stack_inspect.store import EventLog
from stack_inspect_core.sql import fingerprint_sql

if TYPE_CHECKING:
    from stack_inspect.model import GraphEvent

_NOTES = "select count(*) from notes"
_ROUTE = """\
from sqlalchemy import text

@app.get("/notes")
def notes():
    connection.execute(text("select count(*) from notes"))
"""
_DYNAMIC = """\
@app.get("/notes")
def notes(table):
    connection.execute(text(f"select count(*) from {table}"))
"""
_JOBS = """\
from example.queue import enqueue

@app.post("/jobs")
def create_job():
    enqueue()
"""
_QUEUE = """\
def enqueue():
    return None

def take():
    return None
"""
_WORKER = """\
from example.queue import take
from sqlalchemy import text

def handle_job():
    take()
    _count_notes()

def _count_notes():
    connection.execute(text("select count(*) from notes"))
"""
_FETCH = """\
export function postItems() {
  return fetch("/api/items", { method: "POST" });
}

export function dynamic(base: string, path: string) {
  return fetch(`${base}${path}`);
}
"""


def test_route_in_the_same_function_declares_a_query(tmp_path: Path) -> None:
    """A SQL literal in a route becomes a declared edge, and an f-string does not."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "direct.py").write_text(_ROUTE, encoding="utf-8")
    (app / "dynamic.py").write_text(_DYNAMIC, encoding="utf-8")
    edges = scan_roots([app]).edges
    assert len(edges) == 1
    assert edges[0].origin == "api:request:GET /notes"
    assert edges[0].target == f"db:query:{fingerprint_sql(_NOTES)}"
    assert edges[0].kind == "caused"
    assert edges[0].origin_at.startswith("direct.py:")


def test_queue_handoff_joins_the_route_to_the_worker_query(tmp_path: Path) -> None:
    """Enqueue and take from the same module declare the route that queues the job."""
    root = tmp_path / "app"
    package = root / "example"
    package.mkdir(parents=True)
    (package / "jobs.py").write_text(_JOBS, encoding="utf-8")
    (package / "queue.py").write_text(_QUEUE, encoding="utf-8")
    (package / "worker.py").write_text(_WORKER, encoding="utf-8")
    edges = scan_roots([root]).edges
    assert len(edges) == 1
    assert edges[0].origin == "api:request:POST /jobs"
    assert edges[0].target == f"db:query:{fingerprint_sql(_NOTES)}"
    assert edges[0].target_at.startswith("example/worker.py:")


def test_reference_worker_joins_the_job_to_its_queries() -> None:
    """The example worker is the case the button is for."""
    snapshot = scan_roots([_repo() / "reference" / "worker"])
    assert snapshot.refused == ()
    targets = {edge.target for edge in snapshot.edges if edge.origin == "api:request:POST /jobs"}
    create = "create table if not exists notes (id integer)"
    assert f"db:query:{fingerprint_sql(_NOTES)}" in targets
    assert f"db:query:{fingerprint_sql(create)}" in targets
    assert all("stack_inspect" not in edge.origin_at for edge in snapshot.edges)


def test_a_root_that_contains_the_collector_is_refused() -> None:
    """Reading source must not analyse stack-inspect itself."""
    snapshot = scan_roots([_package(), _repo()])
    assert snapshot.edges == ()
    assert str(_package()) in snapshot.note
    assert str(_repo()) in snapshot.note


def test_symlink_that_leaves_the_root_is_ignored(tmp_path: Path) -> None:
    """A link to source outside the root is not part of the application."""
    outside = tmp_path / "outside"
    inside = tmp_path / "app"
    outside.mkdir()
    inside.mkdir()
    (outside / "leak.py").write_text(_ROUTE, encoding="utf-8")
    (inside / "leak.py").symlink_to(outside / "leak.py")
    assert scan_roots([inside]).edges == ()


def test_unchanged_files_reuse_the_snapshot(tmp_path: Path) -> None:
    """A second request with the same bytes does not read the source again."""
    app = tmp_path / "app"
    app.mkdir()
    target = app / "direct.py"
    target.write_text(_ROUTE, encoding="utf-8")
    store = DeclaredStore([app])
    first = store.read()
    assert store.read() is first
    target.write_text(_DYNAMIC, encoding="utf-8")
    second = store.read()
    assert second is not first
    assert second.edges == ()


def test_no_roots_does_not_scan_the_working_directory() -> None:
    """An empty configuration explains itself and returns no edges."""
    snapshot = scan_roots([])
    assert snapshot.edges == ()
    assert snapshot.note.startswith("No source roots")


def test_fetch_of_a_literal_path_declares_a_route(tmp_path: Path) -> None:
    """TypeScript fetch joins a literal path, and a path built at runtime does not."""
    typescript = _repo() / "node_modules" / "typescript"
    if not typescript.is_dir():
        pytest.skip("typescript is not installed")
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    modules = tmp_path / "node_modules"
    modules.mkdir()
    (modules / "typescript").symlink_to(typescript, target_is_directory=True)
    (tmp_path / "page.ts").write_text(_FETCH, encoding="utf-8")
    snapshot = scan_roots([tmp_path])
    assert snapshot.typescript == "scanned"
    assert [edge.origin for edge in snapshot.edges] == ["browser:request:/api/items"]
    assert snapshot.edges[0].target == "api:request:POST /api/items"


def test_graph_draws_a_declared_edge_only_when_both_ends_were_observed(tmp_path: Path) -> None:
    """Reset clears the run and the reading. A missing end stays off the graph."""
    app = tmp_path / "app"
    app.mkdir()
    (app / "direct.py").write_text(_ROUTE, encoding="utf-8")
    log = EventLog(tmp_path / "events.db")
    client = TestClient(create_app(log, roots=[app]), client=("127.0.0.1", 50000))
    reading = client.post("/v1/declared")
    assert reading.is_success
    target = f"db:query:{fingerprint_sql(_NOTES)}"
    body = reading.json()
    assert body["drawn"] == 0
    assert body["edges"][0]["to"] == target
    assert body["limits"]
    assert client.get("/v1/graph").json()["edges"] == []

    log.append(_event("request"))
    assert client.get("/v1/graph").json()["edges"] == []
    log.append(_event("query", nodeKey=target, kind="query", layer="db", name=_NOTES))
    drawn = client.get("/v1/graph").json()["edges"]
    assert drawn[0]["source"] == "declared"
    assert drawn[0]["from"] == "api:request:GET /notes"
    assert drawn[0]["to"] == target

    report = client.get("/v1/report").text
    assert "read from source" in report
    assert _NOTES in report

    assert client.delete("/v1/events").is_success
    log.append(_event("request-again", nodeKey="api:request:GET /notes"))
    log.append(_event("query-again", nodeKey=target, kind="query", layer="db", name=_NOTES))
    assert client.get("/v1/graph").json()["edges"] == []
    again = client.post("/v1/declared")
    assert again.json()["edges"][0]["to"] == target
    redrawn = client.get("/v1/graph").json()["edges"]
    assert redrawn[0]["source"] == "declared"
    assert redrawn[0]["to"] == target


def test_page_offers_read_source(tmp_path: Path) -> None:
    """The button is on the page and does not explain itself in a popover."""
    client = TestClient(create_app(EventLog(tmp_path / "events.db")), client=("127.0.0.1", 50000))
    page = client.get("/")
    assert 'id="read-source"' in page.text
    assert "Read source" in page.text
    assert 'data-help="read-source"' not in page.text


def _event(event_id: str, **overrides: object) -> GraphEvent:
    base: GraphEvent = {
        "id": event_id,
        "traceId": "trace",
        "nodeKey": "api:request:GET /notes",
        "kind": "request",
        "layer": "api",
        "phase": "instant",
        "name": "GET /notes",
        "ts": 1,
        "attributes": {},
    }
    for key, value in overrides.items():
        base[key] = value  # type: ignore[literal-required] # test helper assigns known event fields
    return base


def _repo() -> Path:
    return Path(__file__).resolve().parents[3]


def _package() -> Path:
    """Return the installed collector package directory."""
    return Path(stack_inspect.__file__).resolve().parent
