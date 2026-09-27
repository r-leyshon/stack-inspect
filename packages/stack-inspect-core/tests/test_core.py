"""Unit tests for the dependency-free core."""

from __future__ import annotations

from typing import TYPE_CHECKING

from stack_inspect_core import (
    emit,
    enabled,
    fingerprint_sql,
    format_traceparent,
    new_span_id,
    new_trace_id,
    normalise_sql,
    parse_traceparent,
    redact_attributes,
    set_sink,
)
from stack_inspect_core.context import TraceContext, current_context, use_context

if TYPE_CHECKING:
    import pytest


def test_disabled_unless_opted_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Recording stays off until STACK_INSPECT=1."""
    monkeypatch.delenv("STACK_INSPECT", raising=False)
    assert enabled() is False


def test_refuses_production(monkeypatch: pytest.MonkeyPatch) -> None:
    """A production environment variable disables recording even when opted in."""
    monkeypatch.setenv("STACK_INSPECT", "1")
    monkeypatch.setenv("NODE_ENV", "production")
    assert enabled() is False


def test_traceparent_round_trip() -> None:
    """A formatted traceparent parses back to the same ids."""
    trace_id = new_trace_id()
    span_id = new_span_id()
    parsed = parse_traceparent(format_traceparent(trace_id, span_id))
    assert parsed == (trace_id, span_id)


def test_traceparent_rejects_garbage() -> None:
    """Malformed headers do not raise; they are ignored."""
    assert parse_traceparent("not-a-header") is None


def test_redacts_secrets() -> None:
    """Passwords, cookies and tokens are dropped, including nested ones."""
    cleaned = redact_attributes(
        {"password": "hunter2", "path": "/ok", "nested": {"cookie": "a=b", "left": 1}},
    )
    assert "password" not in cleaned
    assert cleaned["path"] == "/ok"
    nested = cleaned["nested"]
    assert isinstance(nested, dict)
    assert "cookie" not in nested
    assert nested["left"] == 1


def test_normalise_sql_drops_literals_and_keeps_placeholders() -> None:
    """Two calls with different parameter values share one fingerprint."""
    first = "SELECT name FROM items WHERE id = $1 AND note = 'a'"
    second = "select  name  from items where id = $1 and note = 'b'"
    assert fingerprint_sql(first) == fingerprint_sql(second)
    assert "$1" in normalise_sql(first)
    assert "'a'" not in normalise_sql(first)


def test_emit_uses_the_sink_only_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Events reach the sink when enabled, and carry no secrets."""
    captured: list[dict[str, object]] = []
    set_sink(captured.append)
    monkeypatch.setenv("STACK_INSPECT", "1")
    monkeypatch.delenv("NODE_ENV", raising=False)
    emit(
        {
            "id": "1",
            "name": "example",
            "attributes": {"token": "secret", "path": "/items"},
        },
    )
    assert captured[0]["name"] == "example"
    attributes = captured[0]["attributes"]
    assert isinstance(attributes, dict)
    assert "token" not in attributes
    set_sink(None)


def test_context_is_restored() -> None:
    """Leaving a context block restores the previous trace."""
    assert current_context() is None
    context = TraceContext(trace_id="aa", span_id="bb", parent_event_id=None)
    with use_context(context):
        assert current_context() == context
    assert current_context() is None
