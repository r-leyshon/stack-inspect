"""Unit tests for the dependency-free core."""

from __future__ import annotations

import socket
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from stack_inspect_core import (
    emit,
    enabled,
    extract,
    fingerprint_sql,
    format_traceparent,
    inject,
    new_span_id,
    new_trace_id,
    normalise_sql,
    parse_traceparent,
    plain_parameters,
    redact_attributes,
    set_sink,
    values_enabled,
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


def test_values_stay_off_unless_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bound values need both flags, and production still refuses them."""
    monkeypatch.setenv("STACK_INSPECT", "1")
    monkeypatch.delenv("STACK_INSPECT_VALUES", raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)
    assert values_enabled() is False
    monkeypatch.setenv("STACK_INSPECT_VALUES", "1")
    assert values_enabled() is True
    monkeypatch.setenv("NODE_ENV", "production")
    assert values_enabled() is False


def test_plain_parameters_keeps_positional_values_and_drops_secret_keys() -> None:
    """A list of arguments is kept, and a key named token is not."""
    assert plain_parameters(("synthetic", 2)) == ["synthetic", 2]
    assert plain_parameters({"id": 1, "token": "nope"}) == {"id": 1}


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


def test_inject_then_extract_continues_the_same_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    """A plain dict can carry a trace from one context into another. No HTTP is involved."""
    monkeypatch.setenv("STACK_INSPECT", "1")
    monkeypatch.delenv("NODE_ENV", raising=False)
    context = TraceContext(trace_id=new_trace_id(), span_id=new_span_id())
    with use_context(context):
        message = inject({"job": "work"})
    assert message["job"] == "work"
    continued = extract(message)
    assert continued is not None
    assert continued.trace_id == context.trace_id
    captured: list[dict[str, object]] = []
    set_sink(captured.append)
    with use_context(continued):
        emit({"id": "continued", "name": "handler", "traceId": continued.trace_id})
    assert captured[0]["traceId"] == context.trace_id
    set_sink(None)


def test_emit_stamps_the_service_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """The process service name is added when the event does not name one."""
    monkeypatch.setenv("STACK_INSPECT", "1")
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.setenv("STACK_INSPECT_SERVICE", "audio-worker")
    captured: list[dict[str, object]] = []
    set_sink(captured.append)
    emit({"id": "s", "name": "tick"})
    assert captured[0]["service"] == "audio-worker"
    set_sink(None)


def _body_is_short(data: bytes) -> bool:
    """Return whether the HTTP body has not all arrived yet."""
    if b"\r\n\r\n" not in data:
        return True
    header, rest = data.split(b"\r\n\r\n", 1)
    length = 0
    for line in header.decode().split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1])
    return len(rest) < length


def test_socket_post_reaches_a_unix_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    """Events can be posted through a Unix socket instead of loopback TCP."""
    directory = tempfile.mkdtemp(prefix="si", dir="/tmp")
    path = Path(directory) / "c.sock"
    received: list[bytes] = []

    def serve() -> None:
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        server.listen(1)
        server.settimeout(2)
        connection, _address = server.accept()
        connection.settimeout(1)
        data = b""
        try:
            while b"\r\n\r\n" not in data or _body_is_short(data):
                chunk = connection.recv(4096)
                if not chunk:
                    break
                data += chunk
        except TimeoutError:
            pass
        received.append(data)
        connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
        connection.close()
        server.close()

    thread = threading.Thread(target=serve)
    thread.start()
    for _attempt in range(50):
        if path.exists():
            break
        thread.join(0.05)
    monkeypatch.setenv("STACK_INSPECT", "1")
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.setenv("STACK_INSPECT_SOCKET", str(path))
    set_sink(None)
    emit({"id": "sock", "name": "via-socket"})
    thread.join(2)
    assert b"via-socket" in received[0]


def test_context_is_restored() -> None:
    """Leaving a context block restores the previous trace."""
    assert current_context() is None
    context = TraceContext(trace_id="aa", span_id="bb", parent_event_id=None)
    with use_context(context):
        assert current_context() == context
    assert current_context() is None
