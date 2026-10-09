"""The downloadable report matches the log and leaves secrets out."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient
from stack_inspect.server import create_app
from stack_inspect.store import EventLog

if TYPE_CHECKING:
    from pathlib import Path


def _event(event_id: str, **overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": event_id,
        "traceId": "trace-jobs",
        "nodeKey": "api:request:POST /jobs",
        "kind": "request",
        "layer": "api",
        "phase": "instant",
        "name": "POST /jobs",
        "ts": 1_700_000_000_000,
        "service": "jobs",
        "attributes": {},
    }
    base.update(overrides)
    return base


def test_markdown_report_leads_with_findings_and_shared_story(tmp_path: Path) -> None:
    """A jobs request and a worker query are one story, and a secret is absent."""
    log = EventLog(tmp_path / "events.db")
    log.append(_event("request"))
    for index in range(2):
        log.append(
            _event(
                f"query-{index}",
                parentId="request",
                nodeKey="db:query:notes",
                kind="query",
                layer="db",
                name="select count(*) from notes",
                service="worker",
                ts=1_700_000_000_500 + index,
                attributes={"token": "secret-value", "fingerprint": "abc"},
            ),
        )
    log.append(
        _event(
            "asset",
            traceId="trace-jobs",
            nodeKey="next:request:webpack",
            layer="next",
            name="GET /_next/static/chunks/webpack.js",
            service="",
            ts=1_700_000_001_100,
        ),
    )
    client = TestClient(create_app(log), client=("127.0.0.1", 50000))
    page = client.get("/v1/report")
    assert page.is_success
    text = page.text
    assert text.startswith("# stack-inspect report")
    assert "Services: jobs, worker." in text
    assert "These processes share this story: jobs, worker." in text
    assert "select count(*) from notes" in text
    assert "secret-value" not in text
    assert "webpack" not in text
    assert "1 asset request" in text
    assert "## Events" not in text
    assert "seen 2 times" in text


def test_report_can_include_events_as_json(tmp_path: Path) -> None:
    """JSON is the same report, and the event list is opt-in."""
    log = EventLog(tmp_path / "events.db")
    log.append(_event("request"))
    client = TestClient(create_app(log), client=("127.0.0.1", 50000))
    body = client.get("/v1/report", params={"format": "json", "events": 1, "trace": "trace-jobs"}).json()
    assert body["services"] == ["jobs"]
    assert body["stories"][0]["traceId"] == "trace-jobs"
    assert body["events"][0]["name"] == "POST /jobs"
    assert "attachment" in client.get("/v1/report", params={"format": "json"}).headers["content-disposition"]


def test_report_names_values_when_they_were_recorded(tmp_path: Path) -> None:
    """A report that contains parameter values says so, and prints them in the story."""
    log = EventLog(tmp_path / "events.db")
    log.append(
        _event(
            "query",
            nodeKey="db:query:items",
            kind="query",
            layer="db",
            name="select name from items where id = $1",
            attributes={"parameters": ["synthetic-id"], "statement": "select name from items where id = $1"},
        ),
    )
    client = TestClient(create_app(log), client=("127.0.0.1", 50000))
    text = client.get("/v1/report").text
    assert "synthetic-id" in text
    assert "because recording them was turned on" in text
    assert "Request bodies, cookies, tokens" in text
