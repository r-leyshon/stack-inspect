# 2. Local collector rather than an OpenTelemetry backend

- **Status:** Proposed
- **Date:** 2026-09-27

## Context

The obvious starting point is OpenTelemetry: instrument every layer, send spans to an OpenTelemetry Collector, and view them in Grafana Tempo or Jaeger. That gives a cross-stack trace waterfall quickly.

It falls short for stack-inspect because:

- OpenTelemetry spans model a tree of timed operations. Our model also needs instant events (state updates, stream messages), stable node identities and non-tree edges such as `read`, `invalidated` and `duplicated`.
- Trace backends are built for storing and searching many traces, not for a live, reactlog-style view of one developer's session.
- Running Tempo and Grafana locally is a lot of machinery for a development tool.

## Decision

stack-inspect runs its own **local collector** with its own event schema ([ADR 0003](0003-event-schema-and-graph-model.md)).

- Adapters send events to the collector over local HTTP or WebSocket.
- We **reuse OpenTelemetry pieces where they help**: the W3C `traceparent` format, and optionally existing OpenTelemetry instrumentation libraries as event sources, with their spans converted into our events. These libraries are optional extras, never required dependencies of the adapters ([ADR 0011](0011-minimal-runtime-dependencies.md)).
- We may add an OpenTelemetry export later, so recordings can also be viewed in standard tools.

## Consequences

- We control the data model, which the invalidation graph depends on.
- We maintain our own collector and UI instead of using off-the-shelf ones.
- Teams already using OpenTelemetry keep their existing setup. stack-inspect sits alongside it.
