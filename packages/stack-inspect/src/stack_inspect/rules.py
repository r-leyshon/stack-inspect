"""Analysis rules over one interaction, and over the accumulated graph."""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING

from stack_inspect.projector import Span, project

if TYPE_CHECKING:
    from stack_inspect.model import GraphEvent

REPEATED_QUERY_MIN = 3
LARGE_SUBTREE_MIN = 8
EFFECT_RESTART_MIN = 2
RECONNECT_MIN = 2
DUPLICATE_MIN = 2
SEQUENTIAL_MIN = 2


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing the developer should look at."""

    code: str
    title: str
    trace_id: str
    detail: str
    at: float


def analyse(events: list[GraphEvent]) -> list[Finding]:
    """Return every finding present in ``events``."""
    grouped: dict[str, list[GraphEvent]] = {}
    for event in events:
        grouped.setdefault(event["traceId"], []).append(event)
    findings: list[Finding] = []
    for trace_id, trace_events in grouped.items():
        spans = project(trace_events).spans_by_trace.get(trace_id, [])
        findings.extend(_trace_findings(trace_id, spans))
    return findings


def _trace_findings(trace_id: str, spans: list[Span]) -> list[Finding]:
    found: list[Finding] = []
    found.extend(_repeated_queries(trace_id, spans))
    found.extend(_duplicate_requests(trace_id, spans))
    found.extend(_cors_masked_errors(trace_id, spans))
    found.extend(_rejected_preflights(trace_id, spans))
    found.extend(_unchanged_rerenders(trace_id, spans))
    found.extend(_large_subtrees(trace_id, spans))
    found.extend(_restarted_effects(trace_id, spans))
    found.extend(_stream_reconnects(trace_id, spans))
    found.extend(_sequential_queries(trace_id, spans))
    found.extend(_work_after_visible(trace_id, spans))
    return found


def _repeated_queries(trace_id: str, spans: list[Span]) -> list[Finding]:
    counts: dict[str, int] = {}
    for span in spans:
        if span.kind != "query":
            continue
        fingerprint = str(span.attributes.get("fingerprint", span.node_key))
        counts[fingerprint] = counts.get(fingerprint, 0) + 1
    findings: list[Finding] = []
    for fingerprint, count in counts.items():
        if count >= REPEATED_QUERY_MIN:
            findings.append(
                Finding(
                    code="repeated-query",
                    title="Same query executed repeatedly within one interaction",
                    trace_id=trace_id,
                    detail=f"Query fingerprint {fingerprint} ran {count} times",
                    at=_at(
                        [span for span in spans if span.kind == "query" and _fingerprint(span) == fingerprint],
                        REPEATED_QUERY_MIN,
                    ),
                ),
            )
    return findings


def _duplicate_requests(trace_id: str, spans: list[Span]) -> list[Finding]:
    grouped: dict[str, list[Span]] = {}
    for span in spans:
        if span.kind != "request":
            continue
        grouped.setdefault(_request_key(span), []).append(span)
    return [
        Finding(
            code="duplicate-request",
            title="Duplicate request",
            trace_id=trace_id,
            detail=f"{key} ran {len(group)} times",
            at=_at(group, DUPLICATE_MIN),
        )
        for key, group in grouped.items()
        if len(group) >= DUPLICATE_MIN
    ]


def _cors_masked_errors(trace_id: str, spans: list[Span]) -> list[Finding]:
    findings: list[Finding] = []
    for span in spans:
        status = _status(span)
        if status is None or status < _SERVER_ERROR:
            continue
        if not span.attributes.get("crossOrigin"):
            continue
        if span.attributes.get("accessControlAllowOrigin"):
            continue
        path = str(span.attributes.get("path", span.name))
        findings.append(
            Finding(
                code="cors-masked-server-error",
                title="Server error reported as a CORS failure",
                trace_id=trace_id,
                detail=f"{path} returned status {status} without CORS headers",
                at=span.start,
            ),
        )
    return findings


def _rejected_preflights(trace_id: str, spans: list[Span]) -> list[Finding]:
    findings: list[Finding] = []
    for span in spans:
        if str(span.attributes.get("method", "")).upper() != "OPTIONS":
            continue
        status = _status(span)
        requested = str(span.attributes.get("requestedHeaders", ""))
        allowed = str(span.attributes.get("allowedHeaders", ""))
        rejected = status is not None and status >= _CLIENT_ERROR
        header_missing = bool(requested) and requested.lower() not in allowed.lower()
        if not rejected and not header_missing:
            continue
        path = str(span.attributes.get("path", span.name))
        named = requested or "the requested method"
        findings.append(
            Finding(
                code="rejected-preflight",
                title="Rejected preflight",
                trace_id=trace_id,
                detail=f"Preflight for {path} rejected; disallowed header {named}",
                at=span.start,
            ),
        )
    return findings


def _unchanged_rerenders(trace_id: str, spans: list[Span]) -> list[Finding]:
    return [
        Finding(
            code="unchanged-rerender",
            title="Component re-rendered with no changed props or state",
            trace_id=trace_id,
            detail=f"{span.name} re-rendered with nothing relevant changed",
            at=span.start,
        )
        for span in spans
        if span.kind == "render" and span.attributes.get("unchanged") is True
    ]


def _large_subtrees(trace_id: str, spans: list[Span]) -> list[Finding]:
    renders = [span for span in spans if span.kind == "render"]
    updates = [span for span in spans if span.kind == "state-update"]
    if not updates or len(renders) < LARGE_SUBTREE_MIN:
        return []
    return [
        Finding(
            code="large-render-subtree",
            title="State update caused a large render subtree",
            trace_id=trace_id,
            detail=f"{updates[-1].name} was followed by {len(renders)} renders",
            at=_at(renders, LARGE_SUBTREE_MIN),
        ),
    ]


def _restarted_effects(trace_id: str, spans: list[Span]) -> list[Finding]:
    counts: dict[str, int] = {}
    for span in spans:
        if span.kind != "effect":
            continue
        counts[span.node_key] = counts.get(span.node_key, 0) + 1
    return [
        Finding(
            code="effect-restarted",
            title="Effect repeatedly cancelled and restarted",
            trace_id=trace_id,
            detail=f"{node_key} ran {count} times",
            at=_at([span for span in spans if span.kind == "effect" and span.node_key == node_key], EFFECT_RESTART_MIN),
        )
        for node_key, count in counts.items()
        if count >= EFFECT_RESTART_MIN
    ]


def _stream_reconnects(trace_id: str, spans: list[Span]) -> list[Finding]:
    reconnects = [span for span in spans if span.kind == "stream" and span.attributes.get("event") == "reconnect"]
    if len(reconnects) < RECONNECT_MIN:
        return []
    return [
        Finding(
            code="stream-reconnect",
            title="Stream reconnecting repeatedly",
            trace_id=trace_id,
            detail=f"The stream reconnected {len(reconnects)} times",
            at=_at(reconnects, RECONNECT_MIN),
        ),
    ]


def _sequential_queries(trace_id: str, spans: list[Span]) -> list[Finding]:
    queries = [span for span in spans if span.kind == "query" and span.end is not None]
    queries.sort(key=lambda span: span.start)
    sequential = 0
    for earlier, later in itertools.pairwise(queries):
        different = earlier.attributes.get("fingerprint") != later.attributes.get("fingerprint")
        if earlier.end is not None and later.start >= earlier.end and different:
            sequential += 1
    if sequential < SEQUENTIAL_MIN - 1 and len(queries) < SEQUENTIAL_MIN:
        return []
    if len(queries) < SEQUENTIAL_MIN:
        return []
    overlapping = any(
        earlier.end is not None and later.start < earlier.end for earlier, later in itertools.pairwise(queries)
    )
    if overlapping or sequential < 1:
        return []
    return [
        Finding(
            code="sequential-awaits",
            title="Sequential awaits with no observed dependency",
            trace_id=trace_id,
            detail=f"{len(queries)} queries ran one after another",
            at=queries[-1].start,
        ),
    ]


def _work_after_visible(trace_id: str, spans: list[Span]) -> list[Finding]:
    visible = [span.start for span in spans if span.attributes.get("userVisible") is True]
    if not visible:
        return []
    visible_at = min(visible)
    late = [span for span in spans if span.kind in {"request", "query"} and span.start > visible_at]
    if not late:
        return []
    return [
        Finding(
            code="work-after-visible",
            title="Work performed after the user-visible result was already available",
            trace_id=trace_id,
            detail=f"{len(late)} operation(s) started after the result was visible",
            at=min(span.start for span in late),
        ),
    ]


def _request_key(span: Span) -> str:
    method = str(span.attributes.get("method", "GET"))
    path = str(span.attributes.get("path", span.name))
    return f"{method} {path}"


def _fingerprint(span: Span) -> str:
    return str(span.attributes.get("fingerprint", span.node_key))


def _at(spans: list[Span], count: int) -> float:
    """Return when the ``count``-th span started. That is when the finding became true."""
    ordered = sorted(spans, key=lambda span: span.start)
    return ordered[min(count, len(ordered)) - 1].start


def _status(span: Span) -> int | None:
    raw = span.attributes.get("status")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        return int(raw)
    return None


_CLIENT_ERROR = 400
_SERVER_ERROR = 500
