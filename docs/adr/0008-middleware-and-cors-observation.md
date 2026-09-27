# 8. Observe middleware and CORS from both server and browser

- **Status:** Proposed
- **Date:** 2026-09-27

## Context

CORS failures are frequent and slow to debug. They're hard to diagnose because:

- **The browser hides the reason from page JavaScript.** A blocked `fetch` rejects with a generic `TypeError`. The real reason appears only in the DevTools console.
- **Preflight `OPTIONS` requests are sent by the browser itself**, can't be seen from page JavaScript, and carry no trace context.
- **Server errors can look like CORS errors.** In Starlette/FastAPI, `ServerErrorMiddleware` sits outside `CORSMiddleware`, so an unhandled exception produces a 500 with no CORS headers, and the browser reports a CORS failure rather than the server error.
- **Middleware order matters** and is invisible at runtime.

## Decision

Observe from both sides and join the results.

**Server side:**

- The FastAPI adapter wraps every layer of the built ASGI middleware stack. It records entry and exit order, which layer produced the response, and the final response status and headers.
- Preflights are recorded as `middleware` nodes with `Origin`, `Access-Control-Request-Method`, `Access-Control-Request-Headers`, and the `Access-Control-Allow-*` headers returned.
- Every response to a cross-origin request records whether the CORS headers were present and whether they matched the request.
- The Next.js adapter records middleware/proxy decisions: pass-through, rewrite, redirect or early response.

**Browser side:**

- A DevTools adapter connects over the Chrome DevTools Protocol, for example to a browser launched by stack-inspect. It records `Network.loadingFailed` events, including `corsErrorStatus`, and CORS issues from the `Audits` domain.
- Browser-side failures are matched to server-side records by URL, method and timing.

**Analysis rules:**

- A 5xx response without CORS headers is flagged as "server error reported as a CORS failure".
- Rejected preflights are flagged, showing which requested method or header wasn't allowed.
- Preflights caused only by stack-inspect's own `traceparent` header are labelled as such ([ADR 0005](0005-cross-layer-correlation.md)).

## Consequences

- The browser-side reason requires a Chromium-based browser controlled over the DevTools Protocol. Without it, stack-inspect still shows the server side of the story.
- Wrapping every middleware layer adds overhead to every request. This is acceptable in development.
