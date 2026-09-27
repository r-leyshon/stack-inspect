# 7. Model SSE and WebSockets as streams of messages

- **Status:** Proposed
- **Date:** 2026-09-27

## Context

The app uses server-sent events (SSE) and bidirectional streaming (WebSockets). These connections can stay open for minutes and carry many messages. Modelling each as a single timed request is useless: one long bar that hides everything interesting.

Two browser constraints apply:

- `EventSource` and `WebSocket` can't set custom request headers, so `traceparent` can't be sent the usual way.
- WebSocket messages have no headers at all.

## Decision

- A connection is a **`stream` node** with lifecycle events: opened, reconnected, closed and errored, including close codes.
- Each message is a **`stream-message` event** with direction (client to server, or server to client), connection ID, sequence number, size and type.
- **`emitted` edges** link the backend operation that produced a message to the message. **`caused` edges** link a received message to the work it triggered, such as a React state update or a backend handler.
- **Trace context at connect time** is passed as a development-only query parameter on the connection URL.
- **Trace context per message (WebSockets)** travels in a development-only envelope added by the browser adapter and removed by the FastAPI adapter before the application sees the message. Server-to-client messages are wrapped and unwrapped the same way.
- **SSE reconnects** that send `Last-Event-ID` are recorded as the same logical stream.
- If the app uses fetch-based SSE instead of `EventSource`, the normal `traceparent` header is used.

## Consequences

- The envelope changes message payloads in transit, so adapters on both ends must be active together. If only one end is instrumented, the adapters fall back to linking by connection ID and sequence number.
- Automatic instrumentation for FastAPI WebSockets and streaming responses is thin in existing tools, so these adapters are mostly custom work.
- High-frequency streams can flood the event log. Adapters need per-stream sampling or summarisation settings.
