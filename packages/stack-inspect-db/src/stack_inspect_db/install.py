"""Patch asyncpg so each query is recorded against the active trace."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, cast

from stack_inspect_core import (
    current_context,
    emit,
    enabled,
    fingerprint_sql,
    format_traceparent,
    new_event_id,
    normalise_sql,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_QUERY_METHODS = ("fetch", "fetchrow", "fetchval", "execute", "executemany")


def install() -> None:
    """Patch ``asyncpg.connect`` and ``asyncpg.create_pool`` when asyncpg is installed."""
    if not enabled():
        return
    try:
        import asyncpg  # noqa: PLC0415 # optional host dependency, imported only when the app has it
    except ImportError:
        return
    if getattr(asyncpg, "_stack_inspect_installed", False):
        return
    original_connect = asyncpg.connect
    original_pool = asyncpg.create_pool

    async def connect(*args: object, **kwargs: object) -> Any:  # noqa: ANN401
        connection = await original_connect(*args, **kwargs)
        return _TracedConnection(connection)

    async def create_pool(*args: object, **kwargs: object) -> Any:  # noqa: ANN401
        pool = await original_pool(*args, **kwargs)
        return _TracedPool(pool)

    asyncpg.connect = connect
    asyncpg.create_pool = create_pool
    setattr(asyncpg, "_stack_inspect_installed", True)  # noqa: B010 # asyncpg has no such attribute in its stubs


class _TracedPool:
    """A pool whose ``acquire`` yields traced connections."""

    def __init__(self, pool: Any) -> None:  # noqa: ANN401
        self._pool = pool

    def acquire(self, *args: object, **kwargs: object) -> _Acquire:
        """Return an async context manager that yields a traced connection."""
        return _Acquire(self._pool.acquire(*args, **kwargs))

    async def close(self) -> None:
        """Close the underlying pool."""
        await self._pool.close()

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        """Delegate everything else to the underlying pool."""
        return getattr(self._pool, name)


class _Acquire:
    """Wrap the context manager returned by ``Pool.acquire``."""

    def __init__(self, inner: Any) -> None:  # noqa: ANN401
        self._inner = inner

    async def __aenter__(self) -> _TracedConnection:
        """Acquire a connection and wrap it."""
        connection = await self._inner.__aenter__()
        return _TracedConnection(connection)

    async def __aexit__(self, *exc: object) -> None:
        """Release the connection."""
        await self._inner.__aexit__(*exc)


class _TracedConnection:
    """Delegate to a connection, recording each query method."""

    def __init__(self, connection: Any) -> None:  # noqa: ANN401
        self._connection = connection

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401
        """Return a recording wrapper for query methods, or the original attribute."""
        attribute = getattr(self._connection, name)
        if name in _QUERY_METHODS and callable(attribute):
            return _recording(cast("Callable[..., Awaitable[Any]]", attribute))
        return attribute


def _recording(method: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    async def wrapper(*args: object, **kwargs: object) -> Any:  # noqa: ANN401
        statement = args[0] if args and isinstance(args[0], str) else ""
        normalised = normalise_sql(statement) if statement else ""
        fingerprint = fingerprint_sql(statement) if statement else ""
        commented = _with_trace_comment(statement) if statement else statement
        call_args = (commented, *args[1:]) if statement else args
        event_id = new_event_id()
        context = current_context()
        started = time.time()
        emit(
            _query_event(
                event_id,
                phase="start",
                statement=normalised,
                fingerprint=fingerprint,
                parent_id=context.parent_event_id if context else None,
            ),
        )
        try:
            result = await method(*call_args, **kwargs)
        except Exception:
            emit(
                _query_event(
                    new_event_id(),
                    phase="end",
                    statement=normalised,
                    fingerprint=fingerprint,
                    parent_id=event_id,
                    attributes={"error": True},
                ),
            )
            raise
        row_count = len(result) if isinstance(result, list) else None
        emit(
            _query_event(
                new_event_id(),
                phase="end",
                statement=normalised,
                fingerprint=fingerprint,
                parent_id=event_id,
                attributes={"rowCount": row_count, "durationMs": (time.time() - started) * 1000},
            ),
        )
        return result

    return wrapper


def _with_trace_comment(statement: str) -> str:
    context = current_context()
    if context is None:
        return statement
    traceparent = format_traceparent(context.trace_id, context.span_id)
    return f"/*traceparent='{traceparent}'*/ {statement}"


def _query_event(  # noqa: PLR0913 # each event field is explicit so a caller cannot omit one silently
    event_id: str,
    *,
    phase: str,
    statement: str,
    fingerprint: str,
    parent_id: str | None,
    attributes: dict[str, object] | None = None,
) -> dict[str, object]:
    context = current_context()
    merged: dict[str, object] = {"fingerprint": fingerprint, "statement": statement}
    if attributes:
        merged.update(attributes)
    payload: dict[str, object] = {
        "id": event_id,
        "traceId": context.trace_id if context else "untraced",
        "nodeKey": f"db:query:{fingerprint}",
        "kind": "query",
        "layer": "db",
        "phase": phase,
        "name": statement or fingerprint,
        "ts": time.time() * 1000,
        "attributes": merged,
    }
    if parent_id:
        payload["parentId"] = parent_id
    return payload
