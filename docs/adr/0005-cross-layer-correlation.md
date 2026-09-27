# 5. Link events across layers with W3C trace context

- **Status:** Proposed
- **Date:** 2026-09-27

## Context

Events from the browser, Next.js, FastAPI and PostgreSQL must be joined into one trace per interaction. This must work without changes to application code.

## Decision

- **Within a process**, use the runtime's context mechanism: `AsyncLocalStorage` in Node and `contextvars` in Python. These follow async work automatically, including tasks spawned inside a request.
- **Across HTTP**, the browser and Next.js adapters add a W3C `traceparent` header to outgoing requests. The Next.js and FastAPI adapters read it from incoming ones.
- **Into PostgreSQL**, the database adapter appends the trace context to each query as a SQL comment (sqlcommenter style), so database-side logs can be matched to requests.
- **Where headers can't be set** (browser `EventSource` and `WebSocket`), trace context goes in a query parameter, and for WebSockets also in a per-message envelope ([ADR 0007](0007-stream-model.md)).
- **CORS preflights** carry no trace context. They're matched to the request that triggered them by URL and timing ([ADR 0008](0008-middleware-and-cors-observation.md)).

## Consequences

- We use a standard format, so existing OpenTelemetry instrumentation can interoperate.
- Adding `traceparent` to cross-origin browser requests makes them "non-simple", which **triggers a CORS preflight that wouldn't otherwise happen**. The FastAPI adapter must allow the header in development, and the UI must mark preflights caused by stack-inspect itself so they aren't mistaken for application behaviour.
- SQL comments defeat prepared-statement caching in some drivers. This is acceptable in development.
