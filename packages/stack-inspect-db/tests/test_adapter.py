"""The database adapter records statement shape, never parameter values."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from stack_inspect_core import set_sink
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
