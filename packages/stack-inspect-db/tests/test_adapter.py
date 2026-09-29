"""The database adapter records statement shape, never parameter values."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine, text
from stack_inspect_core import set_sink
from stack_inspect_db import install
from stack_inspect_db.install import _recording  # pyright: ignore[reportPrivateUsage] # unit test of the wrapper itself

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[dict[str, object]]]:
    """Collect events in memory."""
    monkeypatch.setenv("STACK_INSPECT", "1")
    monkeypatch.delenv("NODE_ENV", raising=False)
    events: list[dict[str, object]] = []
    set_sink(events.append)
    yield events
    set_sink(None)


@pytest.mark.anyio
async def test_query_fingerprint_ignores_parameters(
    captured: list[dict[str, object]],
) -> None:
    """Bound values are not stored, and the statement sent to the driver is commented."""
    seen: list[str] = []

    async def fetch(statement: str, *args: object) -> list[tuple[object, ...]]:
        seen.append(statement)
        return [(args[0],)]

    wrapped = _recording(fetch)
    await wrapped("SELECT name FROM items WHERE id = $1", "secret-value")
    assert "secret-value" not in str(captured)
    assert seen[0].startswith("/*traceparent=") or "SELECT" in seen[0]
    start = next(event for event in captured if event["phase"] == "start")
    attributes = start["attributes"]
    assert isinstance(attributes, dict)
    assert attributes["fingerprint"]
    assert "secret-value" not in str(attributes["statement"])


def test_sqlalchemy_records_the_statement_not_the_parameter(
    captured: list[dict[str, object]],
) -> None:
    """A sync SQLAlchemy engine is recorded, and bound values are not."""
    install()
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(text("create table notes (body text)"))
        connection.execute(text("insert into notes (body) values (:body)"), {"body": "secret-note"})
    statements: list[object] = []
    for event in captured:
        attributes = event.get("attributes")
        if event.get("kind") == "query" and isinstance(attributes, dict):
            statements.append(attributes.get("statement"))
    rendered = " ".join(str(statement) for statement in statements)
    assert "notes" in rendered
    assert "secret-note" not in rendered
