"""Event shape shared by the collector and the rules."""

from __future__ import annotations

from typing import NotRequired, TypedDict


class GraphEvent(TypedDict):
    """One recorded event. Optional keys are absent until an adapter sets them."""

    id: str
    traceId: str
    parentId: NotRequired[str]
    causeIds: NotRequired[list[str]]
    nodeKey: str
    kind: str
    layer: str
    phase: str
    name: str
    ts: float
    attributes: NotRequired[dict[str, object]]


REQUIRED_FIELDS = ("id", "traceId", "nodeKey", "kind", "layer", "phase", "name", "ts")
PHASES = frozenset({"start", "end", "instant"})
LAYERS = frozenset({"browser", "next", "api", "db"})


def validate_event(payload: object) -> GraphEvent | None:
    """Return ``payload`` when it is a well-formed event, otherwise ``None``."""
    if not isinstance(payload, dict):
        return None
    for field in REQUIRED_FIELDS:
        if field not in payload:
            return None
    phase = payload["phase"]
    layer = payload["layer"]
    timestamp = payload["ts"]
    if phase not in PHASES or layer not in LAYERS:
        return None
    if not isinstance(timestamp, (int, float)):
        return None
    event: GraphEvent = {
        "id": str(payload["id"]),
        "traceId": str(payload["traceId"]),
        "nodeKey": str(payload["nodeKey"]),
        "kind": str(payload["kind"]),
        "layer": str(payload["layer"]),
        "phase": str(phase),
        "name": str(payload["name"]),
        "ts": float(timestamp),
    }
    if "parentId" in payload and payload["parentId"] is not None:
        event["parentId"] = str(payload["parentId"])
    cause_ids = payload.get("causeIds")
    if isinstance(cause_ids, list):
        event["causeIds"] = [str(item) for item in cause_ids]
    attributes = payload.get("attributes")
    if isinstance(attributes, dict):
        event["attributes"] = attributes
    return event
