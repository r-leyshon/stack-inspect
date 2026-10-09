# Roadmap

**Status at 1.0.0:** Foundations and Horizons 1 and 2 (F0, M0–M8) are implemented and covered by the Gherkin suite in `features/`, run against the reference app. Horizon 3 remains the long-term goal. The event model already carries `read` and `invalidated` edges; TanStack Query is the first thing that produces them.

Milestones are grouped by the three levels in the [vision](vision.md). Each has a "done when" line so progress is unambiguous. From M1 onwards, each "done when" line is written as a Gherkin feature file before the milestone is built, and the milestone is done when those scenarios pass ([testing](testing.md)). Horizons 2 and 3 are deliberately less detailed and will be refined as Horizon 1 teaches us more.

## Foundations

### F0: Repository setup
- Licence chosen and added.
- pre-commit configured with the full tool set and suppression settings ([code quality](code-quality.md)).
- CI workflows reproducing the work security gates at identical thresholds ([security posture](security-posture.md)).
- Renovate configured with the same wait period, pinning and grouping settings.
- Repository settings: Dependabot alerts, secret scanning with push protection, private vulnerability reporting, branch protection.
- Test harnesses: pytest, Vitest, and playwright-bdd with an empty `features/` directory.

**Done when:** an empty change passes every required check, and a deliberately planted vulnerable dependency, leaked secret, unpinned action and blanket `# noqa` are each rejected.

## Horizon 1: execution graph

### M0: Reference app
A small Next.js + FastAPI + PostgreSQL app that deliberately contains the problems stack-inspect should find: an N+1 query, a duplicate fetch, a needless re-render, a 500 error that shows up as a CORS failure, a rejected preflight, an SSE endpoint and a WebSocket endpoint.

**Done when:** each planted problem can be triggered from the UI on demand.

### M1: Collector, event log and timeline
The local collector, append-only event log and a minimal timeline UI. Events are emitted by hand from test scripts.

**Done when:** events sent from Node and Python appear on one timeline in the UI.

### M2: HTTP and database across layers
Browser, Next.js, FastAPI and database adapters, linked with `traceparent` and sqlcommenter.

**Done when:** one click in the reference app produces one connected trace running browser → Next.js → FastAPI → SQL, with no tracing calls in the app's code.

### M3: Middleware and CORS
Wrapping of the ASGI middleware stack, Next.js middleware/proxy capture, and the DevTools adapter for browser-side CORS reasons.

**Done when:** both planted CORS problems in the reference app are shown with their real cause, and the 500 masquerading as a CORS error is flagged as such.

### M4: Streams
SSE and WebSocket adapters: stream lifecycle, per-message events and the development-only message envelope.

**Done when:** each SSE and WebSocket message in the reference app appears as a linked event under its stream, and reconnects are visible.

### M5: React adapter
Renders, commits, state updates, changed props and effects, via the React DevTools global hook.

**Done when:** a click shows the state update, the renders it caused, and the fetch fired by the resulting effect, all in one trace.

### M6: Analysis rules
The rules listed in the [architecture](architecture.md#9-analysis-rules).

**Done when:** every planted problem in the reference app raises a finding without manual inspection.

## Horizon 2: observed dependency graph

### M7: Stable node identities and accumulated graph
Group events into stable nodes and accumulate edges with evidence (count, last seen, confidence) across interactions. Add the dependency view to the UI.

**Done when:** after operating the reference app for a few minutes, the dependency view shows which state, components, endpoints and queries tend to run together, with evidence counts.

### M8: Data-library adapters
Adapters for TanStack Query and SWR that record cache keys, observers and invalidations. These are the first real sources of `read` and `invalidated` edges.

**Done when:** invalidating a query key shows which components and requests were affected.

## Horizon 3: invalidation graph (long-term goal)

These milestones are research. Each starts with a spike to test feasibility before committing to a design. The span a request sends is now a `caused` edge to the next hop ([ADR 0015](adr/0015-span-id-is-a-cause.md)). React can name the state update that preceded a render, and cannot yet name the values read during that render ([spike](spikes/0001-react-reads.md)). A request can be joined to the query it ran, and does not say which parameter became which placeholder ([spike](spikes/0002-backend-reads.md)). A cache key stays in the browser, and the span id already carries the request ([spike](spikes/0003-cross-boundary-dependencies.md)). A statement names its table, and that does not say a write invalidated a cache ([spike](spikes/0004-database-writes.md)). M10, M11 and M12 are not to be built.

### M9: React read tracking
Record which state, context and props each component and effect actually read, and which of them had changed when it re-ran.

### M10: Backend read tracking
Stopped. The [spike](spikes/0002-backend-reads.md) found that a request can be joined to the query it ran, and that the placeholder stays in the statement, and that no parameter can be tied to that placeholder. Do not build this. Do not wrap parameters, and do not infer an edge from equal values. Bound values and a short preview of returned rows are recorded only when `STACK_INSPECT_VALUES=1` ([ADR 0016](adr/0016-optional-parameter-values.md)).

### M11: Dependencies across boundaries
Stopped. The [spike](spikes/0003-cross-boundary-dependencies.md) found that a cache key stays on the browser render, and that the span id already carries the request to the API and the query. Nothing copies one onto the other. Sharing a trace or a click is not a cause. Do not build this. Do not infer an edge from equal values.

### M12: Database writes to invalidations
Stopped. The [spike](spikes/0004-database-writes.md) found that the statement text already names the table, and that the only PostgreSQL writes are the untraced startup seed. The `["results"]` cache does not name that table, and the database has no `NOTIFY`, publication or logical decoding. Do not build this. Do not treat a shared table name as an invalidation. No further research gate is scheduled.

**Done when (the long-term goal):** for any render, request or query, stack-inspect can say which changed value caused it to run and what else that change invalidated.

## Not yet scheduled

### Agentic layer

A local MCP server over the collector, so a coding agent can ask about findings, the graph and a playhead moment, and so Playwright journeys can feed those findings back into the agent. Ideation only: [agent layer](agent-layer.md).
