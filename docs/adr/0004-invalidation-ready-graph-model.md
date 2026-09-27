# 4. Keep the graph model ready for invalidation edges

- **Status:** Proposed
- **Date:** 2026-09-27

## Context

The near-term goal is the execution graph: what ran, inside what, for how long. The long-term goal is the invalidation graph: why each thing ran, meaning which changed value made it stale (see the [vision](../vision.md)).

If the first version stores only parent/child timing relationships, adding invalidation later means redesigning the data model and throwing away existing recordings.

## Decision

From the first version, the model includes the pieces the invalidation graph will need, even while nothing produces them:

1. **The event log is the source of truth.** Graphs are always derived from it.
2. **Stable node identities** (`nodeKey`), so reads and invalidations can be tracked across interactions.
3. **An optional `causeIds` field** on every event.
4. **`read` and `invalidated` edge kinds** in the schema.
5. **Provenance on every edge** (`observed`, `inferred` or `declared`), so edges from library adapters, inference and optional annotations can coexist with directly observed ones.

## Consequences

- A little unused schema in the early milestones.
- Recordings made with the execution graph can be reprocessed when invalidation inference arrives.
- Adapters that can cheaply capture causes early (for example, which state setter triggered a React render) should do so, even before the UI uses them.
