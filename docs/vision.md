# Vision

## The problem

Shiny's `reactlog` let you operate an app and then see exactly what ran, in what order, and why. It needed no instrumentation in application code: Shiny owns the reactive runtime, so the dependency graph falls out of how Shiny works.

Our stack has no equivalent:

- **Frontend:** Next.js (React), running in the browser and on the server.
- **Backend:** FastAPI (Python, ASGI).
- **Database:** PostgreSQL.
- **Transport:** plain HTTP, plus middleware (including CORS), server-sent events (SSE) and bidirectional streaming (WebSockets).

Each layer has its own profiler or debugger, and OpenTelemetry can join requests across layers. Nothing shows a single, automatically discovered picture of what a user interaction caused across the whole stack. In particular, nothing makes middleware behaviour and CORS failures easy to see, even though they're a frequent source of lost time.

## What stack-inspect is

A **development-only** tool that watches a running app and builds a live graph of what executed across the browser, Next.js, FastAPI and PostgreSQL. It flags work that is slow, repeated, cancelled or apparently unnecessary.

Like `reactlog`, it trades performance for insight. It's for finessing an app before deployment, never for production.

## The ladder of ambition

There are three levels of graph, each harder than the last.

| Level | What it answers | Difficulty |
| :-- | :-- | :-- |
| 1. Execution graph | *What* ran, inside what, for how long | Moderate |
| 2. Observed dependency graph | What *tends* to run together, learned over many interactions | Moderate to hard |
| 3. Invalidation graph | *Why* each thing ran: which changed value made it stale | Hard |

The execution graph only needs to **observe** events at boundaries: renders, requests, function calls, queries, stream messages. The invalidation graph also needs to know **which values each piece of code read**. In Shiny every read goes through the runtime, so this is free. In our stack reads are ordinary variable access, spread across two languages and several processes, so each read has to be intercepted or inferred.

### Near-term goal: the execution graph

> Show the observed execution graph for a user interaction across React, Next.js, FastAPI and PostgreSQL, including middleware and streams, and flag repeated, slow, cancelled and apparently unnecessary work.

### Long-term goal: the full invalidation graph

The long-term aim is a true cross-stack invalidation graph: for any computation, render, request or query, stack-inspect can say which changed value caused it to run, and what else that change invalidated. This is `reactlog`'s model, extended across process and language boundaries.

We don't build this first, but every design decision should keep it reachable. See [ADR 0004](adr/0004-invalidation-ready-graph-model.md).

## Guiding principles

1. **Observe boundaries, don't annotate code.** Discovery is automatic. Annotations are optional and only add domain names.
2. **Development only, by construction.** The tool must be impossible to enable accidentally in production. See [ADR 0006](adr/0006-development-only-guarantee.md).
3. **Evidence, not claims.** Every edge records how it was learned (observed, inferred or declared) and how often it's been seen. The tool never presents runtime evidence as proof of a universal dependency.
4. **Local first.** Telemetry stays on the developer's machine. No hosted backend is required.
5. **Keep the raw record.** The event log is the source of truth, and graphs are derived from it, so better inference can be reapplied to old recordings.
6. **Safe to install in a locked-down estate.** The adapters must pass the same vulnerability gates as the work repositories that install them, so they carry almost no dependencies of their own. See the [security posture](security-posture.md).

## Non-goals

- Production monitoring, sampling or alerting. Use OpenTelemetry and a hosted observability backend for that.
- Perfect dependency inference for arbitrary code.
- Supporting stacks other than the one above, at least initially.
