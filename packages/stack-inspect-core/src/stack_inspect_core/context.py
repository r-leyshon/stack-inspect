"""Per-task trace context, carried across ``await`` points."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator


@dataclass(frozen=True, slots=True)
class TraceContext:
    """The trace and span active in the current task."""

    trace_id: str
    span_id: str
    parent_event_id: str | None = None


_CURRENT: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "stack_inspect_context",
    default=None,
)


def current_context() -> TraceContext | None:
    """Return the active trace context, if any."""
    return _CURRENT.get()


def push_context(context: TraceContext) -> contextvars.Token[TraceContext | None]:
    """Make ``context`` active and return the token needed to restore the previous one."""
    return _CURRENT.set(context)


def reset_context(token: contextvars.Token[TraceContext | None]) -> None:
    """Restore the trace context captured by ``token``."""
    _CURRENT.reset(token)


@contextmanager
def use_context(context: TraceContext) -> Generator[TraceContext]:
    """Make ``context`` active for the duration of the ``with`` block."""
    token = push_context(context)
    try:
        yield context
    finally:
        reset_context(token)
