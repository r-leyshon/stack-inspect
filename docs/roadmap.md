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

These milestones are research. Each starts with a spike to test feasibility before committing to a design.

### M9: React read tracking
Record which state, context and props each component and effect actually read, and which of them had changed when it re-ran.

### M10: Backend read tracking
Track which request parameters flowed into which service calls and queries.

### M11: Dependencies across boundaries
Carry "this depends on that" information across HTTP and streams, so a frontend value can be linked to the backend work it causes.

### M12: Database writes to invalidations
Link PostgreSQL writes to the cached reads of the same data. Possible mechanisms include parsing query fingerprints for the tables they touch, `LISTEN`/`NOTIFY`, or logical decoding.

**Done when (the long-term goal):** for any render, request or query, stack-inspect can say which changed value caused it to run and what else that change invalidated.
