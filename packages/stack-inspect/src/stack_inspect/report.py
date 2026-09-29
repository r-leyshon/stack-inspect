"""A digest of the log for later reading, or for pasting to a model."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from stack_inspect_core.redact import redact_attributes

from stack_inspect.projector import project
from stack_inspect.rules import analyse
from stack_inspect.source import SOURCE_LIMITS, declared_for_graph

if TYPE_CHECKING:
    from stack_inspect.model import GraphEvent
    from stack_inspect.projector import GraphEdge, GraphNode, ProjectedGraph, Span
    from stack_inspect.source import DeclaredEdge

_REPEATED_MIN = 2
_REDACTION = "Request bodies, cookies, tokens, SQL parameter values and storage record contents are not included."


def build_report(
    events: list[GraphEvent],
    *,
    trace_id: str | None = None,
    include_assets: bool = False,
    include_events: bool = False,
    declared: tuple[DeclaredEdge, ...] | None = None,
) -> dict[str, object]:
    """Return the report as data. Markdown is rendered from this same object."""
    chosen = [event for event in events if trace_id is None or event["traceId"] == trace_id]
    omitted_assets = [event for event in chosen if _is_asset(str(event["name"]))]
    visible = chosen if include_assets else [event for event in chosen if not _is_asset(str(event["name"]))]
    projected = project(visible)
    findings = [finding for finding in analyse(visible) if trace_id is None or finding.trace_id == trace_id]
    stories = _stories(projected.spans_by_trace)
    services = sorted({span.service for spans in projected.spans_by_trace.values() for span in spans if span.service})
    times = [event["ts"] for event in visible]
    report: dict[str, object] = {
        "title": "stack-inspect report",
        "from": _iso(min(times)) if times else None,
        "to": _iso(max(times)) if times else None,
        "services": services,
        "redaction": _REDACTION,
        "findings": [
            {
                "title": finding.title,
                "traceId": finding.trace_id,
                "detail": finding.detail,
            }
            for finding in findings
        ],
        "stories": stories,
        "repeated": _repeated(projected.edges, projected.nodes),
        "declared": _declared(declared or (), projected),
        "omitted": {"assets": 0 if include_assets else len(omitted_assets)},
    }
    if include_events:
        report["events"] = [
            {
                "id": event["id"],
                "traceId": event["traceId"],
                "service": event.get("service", ""),
                "layer": event["layer"],
                "kind": event["kind"],
                "name": event["name"],
                "ts": event["ts"],
                "attributes": redact_attributes(event.get("attributes")),
            }
            for event in visible
        ]
    return report


def render_markdown(report: dict[str, object]) -> str:
    """Render ``report`` as Markdown."""
    sections = [
        _header_markdown(report),
        _findings_markdown(report["findings"]),
        _stories_markdown(report["stories"]),
        _repeated_markdown(report["repeated"]),
        _declared_markdown(report["declared"]),
        _omitted_markdown(report["omitted"]),
    ]
    events = report.get("events")
    if isinstance(events, list):
        sections.append(_events_markdown(events))
    return "\n".join(sections)


def _header_markdown(report: dict[str, object]) -> str:
    services = report["services"]
    if isinstance(services, list) and services:
        service_line = ", ".join(str(service) for service in services)
    else:
        service_line = "none named"
    return "\n".join(
        [
            f"# {report['title']}",
            "",
            f"Recorded from {report['from'] or 'n/a'} to {report['to'] or 'n/a'}.",
            f"Services: {service_line}.",
            str(report["redaction"]),
            "",
        ],
    )


def _findings_markdown(findings: object) -> str:
    lines = ["## Findings", ""]
    if isinstance(findings, list) and findings:
        lines.extend(_finding_line(finding) for finding in findings if isinstance(finding, dict))
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def _finding_line(finding: dict[str, object]) -> str:
    title = _plain(finding.get("title"))
    trace = _short(finding.get("traceId"))
    detail = _plain(finding.get("detail"))
    return f"- **{title}** ({trace}): {detail}"


def _stories_markdown(stories: object) -> str:
    lines = ["## Stories", ""]
    if isinstance(stories, list) and stories:
        for story in stories:
            if isinstance(story, dict):
                lines.extend(_story_markdown(story))
    else:
        lines.extend(["None.", ""])
    return "\n".join(lines)


def _repeated_markdown(repeated: object) -> str:
    lines = ["## Repeated relationships", ""]
    if isinstance(repeated, list) and repeated:
        lines.extend(_edge_line(edge) for edge in repeated if isinstance(edge, dict))
    else:
        lines.append("No relationship was seen more than once.")
    lines.append("")
    return "\n".join(lines)


def _declared_markdown(declared: object) -> str:
    lines = ["## Read from source", ""]
    if isinstance(declared, list) and declared:
        lines.extend(_declared_line(edge) for edge in declared if isinstance(edge, dict))
        lines.extend(["", SOURCE_LIMITS])
    else:
        lines.append("None.")
    lines.append("")
    return "\n".join(lines)


def _declared_line(edge: dict[str, object]) -> str:
    kind = _plain(edge.get("kind"))
    origin = _plain(edge.get("from"))
    target = _plain(edge.get("to"))
    return f"- `{kind}` {origin} → {target}, read from source."


def _edge_line(edge: dict[str, object]) -> str:
    kind = _plain(edge.get("kind"))
    origin = _plain(edge.get("from"))
    target = _plain(edge.get("to"))
    return f"- `{kind}` {origin} → {target}, seen {edge.get('count')} times"


def _omitted_markdown(omitted: object) -> str:
    asset_count = omitted.get("assets", 0) if isinstance(omitted, dict) else 0
    return "\n".join(
        [
            "## Left out",
            "",
            f"- {asset_count} asset request(s) were omitted.",
            f"- {_REDACTION}",
            "",
        ],
    )


def _events_markdown(events: list[object]) -> str:
    lines = ["## Events", ""]
    lines.extend(_event_line(event) for event in events if isinstance(event, dict))
    lines.append("")
    return "\n".join(lines)


def _event_line(event: dict[str, object]) -> str:
    lane = _plain(event.get("service") or event.get("layer"))
    return f"- {_short(event.get('traceId'))} {lane} {_plain(event.get('kind'))} {_plain(event.get('name'))}"


def _stories(spans_by_trace: dict[str, list[Span]]) -> list[dict[str, object]]:
    stories: list[dict[str, object]] = []
    for trace_id, spans in spans_by_trace.items():
        ordered = sorted(spans, key=lambda span: span.start)
        if not ordered:
            continue
        services = sorted({span.service for span in ordered if span.service})
        stories.append(
            {
                "traceId": trace_id,
                "title": _title(ordered),
                "started": _iso(ordered[0].start),
                "services": services,
                "spans": [
                    {
                        "lane": span.service or span.layer,
                        "kind": span.kind,
                        "name": span.name,
                        "durationMs": _duration(span),
                    }
                    for span in ordered
                ],
            },
        )
    stories.sort(key=lambda story: str(story["started"]))
    return stories


def _declared(edges: tuple[DeclaredEdge, ...], projected: ProjectedGraph) -> list[dict[str, object]]:
    observed = [(edge.origin, edge.target, edge.kind) for edge in projected.edges]
    visible = declared_for_graph(edges, projected.nodes, observed)
    return [
        {
            "kind": edge.kind,
            "from": projected.nodes[edge.origin].name,
            "to": projected.nodes[edge.target].name,
            "at": edge.origin_at,
        }
        for edge in visible
    ]


def _repeated(edges: list[GraphEdge], nodes: dict[str, GraphNode]) -> list[dict[str, object]]:
    repeated: list[dict[str, object]] = []
    for edge in edges:
        if edge.count < _REPEATED_MIN:
            continue
        repeated.append(
            {
                "kind": edge.kind,
                "from": nodes[edge.origin].name if edge.origin in nodes else edge.origin,
                "to": nodes[edge.target].name if edge.target in nodes else edge.target,
                "count": edge.count,
            },
        )
    repeated.sort(key=lambda item: item["count"] if isinstance(item["count"], int) else 0, reverse=True)
    return repeated


def _title(spans: list[Span]) -> str:
    for span in spans:
        if span.kind == "interaction" and not _is_asset(span.name):
            return span.name
    for span in spans:
        if span.kind == "request" and not _is_asset(span.name):
            return span.name
    return spans[0].name


def _story_markdown(story: dict[str, object]) -> list[str]:
    services = story["services"]
    lines = [
        f"### {_plain(story.get('title'))}",
        "",
        f"Trace `{story.get('traceId')}`. Started {story.get('started')}.",
    ]
    if isinstance(services, list) and len(services) > 1:
        joined = ", ".join(str(service) for service in services)
        lines.append(
            f"These processes share this story: {joined}. A shared story is not, by itself, a line on the graph.",
        )
    lines.append("")
    spans = story["spans"]
    if isinstance(spans, list):
        for span in spans:
            if isinstance(span, dict):
                duration = span.get("durationMs")
                timing = "instant" if not isinstance(duration, int | float) or duration < 1 else f"{int(duration)} ms"
                lines.append(
                    f"- {_plain(span.get('lane'))} {_plain(span.get('kind'))} {_plain(span.get('name'))} ({timing})",
                )
    lines.append("")
    return lines


def _is_asset(name: str) -> bool:
    return "/_next/" in name or "webpack" in name or "hot-update" in name


def _duration(span: Span) -> float:
    if span.end is None:
        return 0
    return max(0, span.end - span.start)


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp / 1000, tz=UTC).isoformat()


def _short(value: object) -> str:
    text = str(value or "")
    return text[:8]


def _plain(value: object) -> str:
    return str(value or "").replace("\n", " ").replace("`", "'")
