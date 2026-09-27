"""Identifiers and the W3C traceparent header."""

from __future__ import annotations

import uuid

_TRACEPARENT_FIELDS = 4
_TRACE_ID_HEX_LENGTH = 32
_SPAN_ID_HEX_LENGTH = 16
_VERSION = "00"


def new_event_id() -> str:
    """Return a new event id."""
    return uuid.uuid4().hex


def new_trace_id() -> str:
    """Return a 32 character hex trace id."""
    return uuid.uuid4().hex


def new_span_id() -> str:
    """Return a 16 character hex span id."""
    return uuid.uuid4().hex[:_SPAN_ID_HEX_LENGTH]


def format_traceparent(trace_id: str, span_id: str) -> str:
    """Return a W3C ``traceparent`` value for a trace and span."""
    return f"{_VERSION}-{trace_id}-{span_id}-01"


def parse_traceparent(header: str) -> tuple[str, str] | None:
    """Return ``(trace_id, span_id)`` from a ``traceparent`` header, or ``None``."""
    parts = header.strip().split("-")
    if len(parts) != _TRACEPARENT_FIELDS:
        return None
    version, trace_id, span_id, _flags = parts
    if version != _VERSION:
        return None
    if len(trace_id) != _TRACE_ID_HEX_LENGTH or len(span_id) != _SPAN_ID_HEX_LENGTH:
        return None
    try:
        int(trace_id, 16)
        int(span_id, 16)
    except ValueError:
        return None
    return trace_id, span_id
