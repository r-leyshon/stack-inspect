# 3. Event schema and graph model

- **Status:** Proposed
- **Date:** 2026-09-27

## Context

Adapters in two languages and several processes must emit events the collector can merge into one graph. A plain trace tree can't express everything we need. For example, two components independently reading the same cache key is a dependency, not a parent/child relationship.

## Decision

We separate three concepts: **events** (the raw record), **nodes** (stable identities) and **edges** (relationships with evidence).

```ts
type Layer = "browser" | "next" | "api" | "db"

type NodeKind =
  | "interaction" | "state-update" | "render" | "effect"
  | "middleware" | "request" | "stream" | "stream-message"
  | "function-call" | "query" | "error"

type GraphEvent = {
  id: string              // unique per event
  traceId: string         // groups one interaction across layers
  parentId?: string       // enclosing event, if any
  causeIds?: string[]     // events that directly caused this one, when known
  nodeKey: string         // stable identity, e.g. "api:route:GET /results"
  kind: NodeKind
  layer: Layer
  phase: "start" | "end" | "instant"
  name: string
  ts: number              // epoch milliseconds, fractional
  attributes?: Record<string, unknown>
}

type EdgeKind =
  | "contained" | "caused" | "awaited" | "retried"
  | "duplicated" | "emitted" | "read" | "invalidated"

type GraphEdge = {
  from: string            // nodeKey
  to: string              // nodeKey
  kind: EdgeKind
  source: "observed" | "inferred" | "declared"
  count: number
  firstSeen: number
  lastSeen: number
}
```

Rules:

- Adapters only emit events. Nodes and edges are derived by the graph projector.
- Events are append-only and never edited.
- `nodeKey` must stay the same for the same logical thing across interactions and restarts. For example: component display name plus position in the tree, route template rather than concrete URL, normalised SQL fingerprint rather than query text.
- Attributes are redacted by default: no request bodies, cookies, tokens or SQL parameter values. Parameter values are recorded only when `STACK_INSPECT_VALUES=1` ([ADR 0016](0016-optional-parameter-values.md)).

## Consequences

- Graphs can be rebuilt from the event log with improved projection logic.
- Stable `nodeKey` generation is a real design problem for each adapter, especially for React components.
- The schema is richer than OpenTelemetry spans, so importing OpenTelemetry data needs a conversion step.
