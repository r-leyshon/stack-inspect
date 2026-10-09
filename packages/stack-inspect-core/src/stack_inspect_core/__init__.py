"""Dependency-free event emitter for stack-inspect adapters."""

from stack_inspect_core.carrier import extract, inject
from stack_inspect_core.context import (
    current_context,
    push_context,
    reset_context,
)
from stack_inspect_core.emit import emit, set_sink
from stack_inspect_core.guard import enabled, values_enabled
from stack_inspect_core.ids import (
    format_traceparent,
    new_event_id,
    new_span_id,
    new_trace_id,
    parse_traceparent,
)
from stack_inspect_core.redact import plain_parameters, redact_attributes
from stack_inspect_core.sql import fingerprint_sql, normalise_sql

__all__ = [
    "current_context",
    "emit",
    "enabled",
    "extract",
    "fingerprint_sql",
    "format_traceparent",
    "inject",
    "new_event_id",
    "new_span_id",
    "new_trace_id",
    "normalise_sql",
    "parse_traceparent",
    "plain_parameters",
    "push_context",
    "redact_attributes",
    "reset_context",
    "set_sink",
    "values_enabled",
]
