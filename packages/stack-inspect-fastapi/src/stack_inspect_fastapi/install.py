"""Wrap an ASGI app so each request becomes events."""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any
from urllib.parse import parse_qs

from stack_inspect_core import (
    current_context,
    emit,
    enabled,
    format_traceparent,
    new_event_id,
    new_span_id,
    new_trace_id,
    parse_traceparent,
    push_context,
    reset_context,
)
from stack_inspect_core.context import TraceContext

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_SSE_CONTENT_TYPE = b"text/event-stream"
_HEADER_STATUS_OK_MIN = 200


def install(app: Any) -> None:  # noqa: ANN401 # the app is whatever ASGI framework the caller uses
    """Record requests for ``app``. No effect unless stack-inspect is enabled.

    Call this after the application's middleware has been added. The wrapper
    sits outside Starlette's ``ServerErrorMiddleware``, so a 500 that skipped
    the CORS middleware is still visible.
    """
    if not enabled():
        return
    if getattr(app, "_stack_inspect_installed", False):
        return
    _wrap_user_middleware(app)
    # Python looks up ``__call__`` on the class, so replacing the instance
    # attribute does nothing. Wrap the built middleware stack instead. That
    # also sits outside ServerErrorMiddleware, which is what strips CORS
    # headers from an unhandled 500.
    original_build = app.build_middleware_stack

    def build_middleware_stack() -> ASGIApp:
        return _Outermost(original_build())

    app.build_middleware_stack = build_middleware_stack
    app.middleware_stack = None
    app._stack_inspect_installed = True  # noqa: SLF001 # marker on the caller's app object


class _Outermost:
    """Sees the response that actually leaves the server."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") == "lifespan":
            await self._app(scope, receive, send)
            return
        await _observe(self._app, scope, receive, send)


def _wrap_user_middleware(app: Any) -> None:  # noqa: ANN401
    """Wrap each user middleware layer so its name and order are recorded."""
    user_middleware = getattr(app, "user_middleware", None)
    if not user_middleware:
        return
    try:
        from starlette.middleware import Middleware  # noqa: PLC0415 # provided by the host app, not by this package
    except ImportError:
        return
    wrapped = []
    for index, middleware in enumerate(user_middleware):
        name = getattr(middleware.cls, "__name__", "middleware")
        wrapped.append(
            Middleware(
                _Layer,
                inner_cls=middleware.cls,
                inner_args=middleware.args,
                inner_kwargs=middleware.kwargs,
                layer_name=name,
                layer_index=index,
            ),
        )
    app.user_middleware = wrapped


class _Layer:
    """One named layer of the user middleware stack."""

    def __init__(  # noqa: PLR0913 # the layer needs the wrapped class plus the name shown in the graph
        self,
        app: ASGIApp,
        *,
        inner_cls: type,
        inner_args: tuple[object, ...],
        inner_kwargs: dict[str, object],
        layer_name: str,
        layer_index: int,
    ) -> None:
        self._inner = inner_cls(app, *inner_args, **inner_kwargs)
        self._layer_name = layer_name
        self._layer_index = layer_index

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self._inner(scope, receive, send)
            return
        context = current_context()
        event_id = new_event_id()
        emit(
            _event(
                event_id=event_id,
                name=self._layer_name,
                kind="middleware",
                phase="start",
                node_key=f"api:middleware:{self._layer_name}",
                parent_id=context.parent_event_id if context else None,
                attributes={"index": self._layer_index, "path": _path(scope)},
            ),
        )

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                emit(
                    _event(
                        event_id=new_event_id(),
                        name=self._layer_name,
                        kind="middleware",
                        phase="end",
                        node_key=f"api:middleware:{self._layer_name}",
                        parent_id=event_id,
                        attributes={
                            "status": message["status"],
                            "index": self._layer_index,
                            "path": _path(scope),
                        },
                    ),
                )
            await send(message)

        await self._inner(scope, receive, send_wrapper)


async def _observe(app: ASGIApp, scope: Scope, receive: Receive, send: Send) -> None:
    kind = scope.get("type")
    if kind == "websocket":
        await _observe_websocket(app, scope, receive, send)
        return
    if kind != "http":
        await app(scope, receive, send)
        return
    await _observe_http(app, scope, receive, send)


async def _observe_http(app: ASGIApp, scope: Scope, receive: Receive, send: Send) -> None:
    headers = _headers(scope)
    incoming = parse_traceparent(headers.get("traceparent", "")) or _trace_from_query(scope)
    if incoming is None:
        trace_id, parent_span = new_trace_id(), None
    else:
        trace_id, parent_span = incoming
    span_id = new_span_id()
    event_id = new_event_id()
    method = str(scope.get("method", "GET"))
    path = _path(scope)
    context = TraceContext(trace_id=trace_id, span_id=span_id, parent_event_id=event_id)
    token = push_context(context)
    started = time.time()
    attributes: dict[str, object] = {
        "method": method,
        "path": path,
        "spanId": span_id,
        "traceparent": format_traceparent(trace_id, span_id),
    }
    if parent_span is not None:
        attributes["parentSpanId"] = parent_span
    origin = headers.get("origin")
    if origin:
        attributes["crossOrigin"] = True
        attributes["origin"] = origin
    if method.upper() == "OPTIONS":
        attributes["requestedHeaders"] = headers.get("access-control-request-headers", "")
        attributes["requestedMethod"] = headers.get("access-control-request-method", "")
    emit(
        _event(
            event_id=event_id,
            name=f"{method} {path}",
            kind="request",
            phase="start",
            node_key=f"api:request:{method} {path}",
            attributes=attributes,
        ),
    )
    state: dict[str, object] = {"status": 0, "sse": False, "buffer": b""}

    async def send_wrapper(message: Message) -> None:
        if message["type"] == "http.response.start":
            status = int(message["status"])
            state["status"] = status
            response_headers = _message_headers(message)
            allow_origin = response_headers.get("access-control-allow-origin", "")
            content_type = response_headers.get("content-type", "")
            end_attributes = dict(attributes)
            end_attributes["status"] = status
            end_attributes["accessControlAllowOrigin"] = allow_origin
            end_attributes["allowedHeaders"] = response_headers.get(
                "access-control-allow-headers",
                "",
            )
            if _SSE_CONTENT_TYPE.decode() in content_type:
                state["sse"] = True
                _emit_stream(context, path, _stream_event_name(context.trace_id, path))
            emit(
                _event(
                    event_id=new_event_id(),
                    name=f"{method} {path}",
                    kind="request",
                    phase="end",
                    node_key=f"api:request:{method} {path}",
                    parent_id=event_id,
                    attributes=end_attributes,
                ),
            )
        elif message["type"] == "http.response.body" and state["sse"]:
            _emit_sse_chunks(context, path, state, bytes(message.get("body") or b""))
        await send(message)

    try:
        await app(scope, receive, send_wrapper)
    finally:
        reset_context(token)
        _ = started


def _emit_stream(context: TraceContext, path: str, event_name: str) -> str:
    event_id = new_event_id()
    emit(
        _event(
            event_id=event_id,
            name=path,
            kind="stream",
            phase="instant",
            node_key=f"api:stream:{path}",
            parent_id=context.parent_event_id,
            attributes={"event": event_name, "path": path},
        ),
    )
    return event_id


def _emit_sse_chunks(context: TraceContext, path: str, state: dict[str, object], chunk: bytes) -> None:
    held = state["buffer"]
    buffer = (held if isinstance(held, bytes) else b"") + chunk
    while b"\n\n" in buffer:
        raw, buffer = buffer.split(b"\n\n", 1)
        text = raw.decode("utf-8", errors="replace")
        data = ""
        for line in text.split("\n"):
            if line.startswith("data:"):
                data = line.removeprefix("data:").strip()
        previous = state.get("sequence", 0)
        sequence = (previous if isinstance(previous, int) else 0) + 1
        state["sequence"] = sequence
        emit(
            _event(
                event_id=new_event_id(),
                name=data or "message",
                kind="stream-message",
                phase="instant",
                node_key=f"api:stream-message:{path}",
                parent_id=context.parent_event_id,
                attributes={
                    "direction": "server",
                    "sequence": sequence,
                    "path": path,
                    "size": len(raw),
                },
            ),
        )
    state["buffer"] = buffer


async def _observe_websocket(app: ASGIApp, scope: Scope, receive: Receive, send: Send) -> None:
    path = _path(scope)
    query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
    trace_header = ""
    values = query.get("stack_inspect_traceparent")
    if values:
        trace_header = values[0]
    incoming = parse_traceparent(trace_header)
    trace_id = incoming[0] if incoming else new_trace_id()
    span_id = new_span_id()
    event_id = new_event_id()
    context = TraceContext(trace_id=trace_id, span_id=span_id, parent_event_id=event_id)
    token = push_context(context)
    sequence = {"client": 0, "server": 0}
    emit(
        _event(
            event_id=event_id,
            name=path,
            kind="stream",
            phase="start",
            node_key=f"api:stream:{path}",
            attributes={"event": "open", "path": path, "protocol": "websocket"},
        ),
    )

    async def receive_wrapper() -> Message:
        message = await receive()
        if message["type"] == "websocket.receive" and message.get("text") is not None:
            text, envelope_trace = _unwrap(str(message["text"]))
            message = dict(message)
            message["text"] = text
            sequence["client"] += 1
            emit(
                _event(
                    event_id=new_event_id(),
                    name=text,
                    kind="stream-message",
                    phase="instant",
                    node_key=f"api:stream-message:{path}",
                    parent_id=event_id,
                    attributes={
                        "direction": "client",
                        "sequence": sequence["client"],
                        "path": path,
                        "traceparent": envelope_trace,
                    },
                ),
            )
        return message

    async def send_wrapper(message: Message) -> None:
        if message["type"] == "websocket.send" and message.get("text") is not None:
            sequence["server"] += 1
            emit(
                _event(
                    event_id=new_event_id(),
                    name=str(message["text"]),
                    kind="stream-message",
                    phase="instant",
                    node_key=f"api:stream-message:{path}",
                    parent_id=event_id,
                    attributes={
                        "direction": "server",
                        "sequence": sequence["server"],
                        "path": path,
                    },
                ),
            )
        if message["type"] == "websocket.close":
            emit(
                _event(
                    event_id=new_event_id(),
                    name=path,
                    kind="stream",
                    phase="end",
                    node_key=f"api:stream:{path}",
                    parent_id=event_id,
                    attributes={"event": "close", "code": message.get("code")},
                ),
            )
        await send(message)

    try:
        await app(scope, receive_wrapper, send_wrapper)
    finally:
        reset_context(token)


def _unwrap(text: str) -> tuple[str, str]:
    """Return the application payload and any per-message traceparent."""
    if not text.startswith("{"):
        return text, ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text, ""
    if not isinstance(parsed, dict) or "__stackInspect" not in parsed:
        return text, ""
    envelope = parsed["__stackInspect"]
    payload = parsed.get("payload", "")
    traceparent = ""
    if isinstance(envelope, dict):
        raw = envelope.get("traceparent", "")
        traceparent = raw if isinstance(raw, str) else ""
    return str(payload), traceparent


_STREAM_OPENS: dict[tuple[str, str], int] = {}


def _trace_from_query(scope: Scope) -> tuple[str, str] | None:
    """EventSource cannot set headers, so the browser puts the trace in the query."""
    raw = scope.get("query_string", b"")
    if isinstance(raw, bytes):
        raw = raw.decode("latin-1")
    values = parse_qs(str(raw)).get("stack_inspect_traceparent")
    if not values:
        return None
    return parse_traceparent(values[0])


def _stream_event_name(trace_id: str, path: str) -> str:
    """The second and later connection for a path in one trace is a reconnect."""
    key = (trace_id, path)
    count = _STREAM_OPENS.get(key, 0) + 1
    _STREAM_OPENS[key] = count
    return "reconnect" if count > 1 else "open"


def _headers(scope: Scope) -> dict[str, str]:
    raw = scope.get("headers") or []
    return {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in raw}


def _message_headers(message: Message) -> dict[str, str]:
    raw = message.get("headers") or []
    return {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in raw}


def _path(scope: Scope) -> str:
    return str(scope.get("path", "/"))


def _event(  # noqa: PLR0913 # each event field is explicit so a caller cannot omit one silently
    *,
    event_id: str,
    name: str,
    kind: str,
    phase: str,
    node_key: str,
    attributes: dict[str, object],
    parent_id: str | None = None,
) -> dict[str, object]:
    context = current_context()
    trace_id = context.trace_id if context else new_trace_id()
    payload: dict[str, object] = {
        "id": event_id,
        "traceId": trace_id,
        "nodeKey": node_key,
        "kind": kind,
        "layer": "api",
        "phase": phase,
        "name": name,
        "ts": time.time() * 1000,
        "attributes": attributes,
    }
    if parent_id:
        payload["parentId"] = parent_id
    return payload
