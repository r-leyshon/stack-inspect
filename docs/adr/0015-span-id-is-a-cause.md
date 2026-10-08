# 15. A sent span id is a cause

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

[ADR 0005](0005-cross-layer-correlation.md) joins the browser, Next.js and FastAPI into one trace with a W3C `traceparent` header. Sharing a trace does not draw an edge. A click, the browser fetch it started, and the API request in that same trace were three nodes with nothing between them.

The header already carries a span id. The receiver already stored it as `parentSpanId`. The sender threw the span id away, and the click event used a different id from the one its child events named as `parentId`.

## Decision

- The event id of a click is the `parentId` of the browser request, stream or storage call that follows it. A later click in the same trace window becomes the parent of what follows that click. The trace id stays put for the window.
- A hop that places a span id on an outgoing `traceparent` records that value as `spanId`. A hop that reads a `traceparent` records the incoming span id as `parentSpanId`.
- The projector draws one `caused` edge from the node that sent a span id to the node that received it, in the same trace. An end event does not add a second edge. A node does not cause itself.
- The edge is `observed`. Both sides recorded a span id that was actually on the wire.

## Consequences

- A browser fetch lines up with the Next.js or FastAPI request it called, and a click lines up with the browser call it started.
- CORS behaviour is unchanged. No new request header is added.
- This is still "this request ran because that request ran". It does not say which value was read. That remains [the React read spike](../spikes/0001-react-reads.md) and Horizon 3.
