"""Patch asyncpg so each query is recorded against the active trace."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

from stack_inspect_core import (
    current_context,
    emit,
    enabled,
    fingerprint_sql,
    format_traceparent,
    new_event_id,
    normalise_sql,
    plain_parameters,
    values_enabled,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_QUERY_METHODS = ("fetch", "fetchrow", "fetchval", "execute", "executemany")
_MAX_PREVIEW_ROWS = 3
_MAX_PREVIEW_COLUMNS = 8


def install() -> None:
    """Record queries from asyncpg and SQLAlchemy, whichever the application uses."""
    if not enabled():
        return
    _install_asyncpg()
    _install_sqlalchemy()


def _install_asyncpg() -> None:
    """Patch ``asyncpg.connect`` and ``asyncpg.create_pool`` when asyncpg is installed."""
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
                attributes=_parameter_attributes(args[1:] if len(args) > 1 else None),
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
        end_attributes: dict[str, object] = {"rowCount": row_count, "durationMs": (time.time() - started) * 1000}
        preview = _row_preview(result)
        if preview:
            end_attributes.update(preview)
        emit(
            _query_event(
                new_event_id(),
                phase="end",
                statement=normalised,
                fingerprint=fingerprint,
                parent_id=event_id,
                attributes=end_attributes,
            ),
        )
        return result

    return wrapper


def _install_sqlalchemy() -> None:
    """Record statements executed through any SQLAlchemy engine.

    Bound values are stored only when ``STACK_INSPECT_VALUES=1``.
    The cursor is left unread, so a row preview is not taken here.
    """
    try:
        from sqlalchemy import event  # noqa: PLC0415 # optional host dependency
        from sqlalchemy.engine import Engine  # noqa: PLC0415 # optional host dependency
    except ImportError:
        return
    if getattr(Engine, "_stack_inspect_installed", False):
        return

    def after_execute(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        normalised = normalise_sql(statement)
        fingerprint = fingerprint_sql(statement)
        trace = current_context()
        emit(
            _query_event(
                new_event_id(),
                phase="instant",
                statement=normalised,
                fingerprint=fingerprint,
                parent_id=trace.parent_event_id if trace else None,
                attributes=_parameter_attributes(_sqlalchemy_parameters(_parameters, _context)),
            ),
        )

    event.listen(Engine, "after_cursor_execute", after_execute)
    setattr(Engine, "_stack_inspect_installed", True)  # noqa: B010 # SQLAlchemy's Engine has no such attribute in its stubs


def _sqlalchemy_parameters(parameters: object, context: object) -> object:
    """Prefer the named arguments SQLAlchemy compiled, otherwise the positional tuple."""
    named = getattr(context, "compiled_parameters", None)
    if isinstance(named, list) and any(isinstance(item, dict) and item for item in named):
        return named[0] if len(named) == 1 else named
    return parameters


def _row_preview(result: object) -> dict[str, object] | None:
    """Return a few cells from a result the driver already handed back."""
    if not values_enabled() or result is None or isinstance(result, str | bytes):
        return None
    if isinstance(result, list):
        rows = [row for item in result[:_MAX_PREVIEW_ROWS] if (row := _preview_row(item)) is not None]
        return {"rows": rows} if rows else None
    row = _preview_row(result)
    if row is not None:
        return {"rows": [row]}
    if isinstance(result, bool | int | float):
        return {"rows": [[result]]}
    return None


def _preview_row(item: object) -> object | None:
    if isinstance(item, Mapping):
        pairs = list(item.items())[:_MAX_PREVIEW_COLUMNS]
        if not pairs:
            return None
        return plain_parameters({str(key): value for key, value in pairs})
    if isinstance(item, list | tuple):
        return plain_parameters(tuple(item[:_MAX_PREVIEW_COLUMNS]))
    if item is None or isinstance(item, bool | int | float | str):
        return plain_parameters(item)
    return None


def _parameter_attributes(parameters: object) -> dict[str, object] | None:
    """Return bound arguments when value recording is on, otherwise nothing."""
    if not values_enabled() or parameters is None:
        return None
    shaped = plain_parameters(parameters)
    if shaped in ([], {}):
        return None
    return {"parameters": shaped}


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
