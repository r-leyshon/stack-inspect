"""Continue a trace through any map of strings.

HTTP already carries ``traceparent`` as a header. A queue, a blob's metadata,
or a job payload can carry the same header as one entry in a plain dict.
``inject`` writes the active trace in. ``extract`` reads it back out. Neither
knows what the map is for.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from stack_inspect_core.context import TraceContext, current_context
from stack_inspect_core.ids import format_traceparent, parse_traceparent

if TYPE_CHECKING:
    from collections.abc import Mapping

CARRIER_KEY = "traceparent"


def inject(carrier: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return ``carrier`` with the active trace added, when there is one.

    The input map is not modified.
    """
    copied = dict(carrier or {})
    context = current_context()
    if context is None:
        return copied
    copied[CARRIER_KEY] = format_traceparent(context.trace_id, context.span_id)
    return copied


def extract(carrier: Mapping[str, str]) -> TraceContext | None:
    """Return the trace stored in ``carrier``, or ``None`` when it has none."""
    raw = carrier.get(CARRIER_KEY) or carrier.get("stack_inspect_traceparent")
    if not raw:
        return None
    parsed = parse_traceparent(raw)
    if parsed is None:
        return None
    trace_id, span_id = parsed
    return TraceContext(trace_id=trace_id, span_id=span_id)
