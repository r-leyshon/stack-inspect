# 1. Record architecture decisions

- **Status:** Accepted
- **Date:** 2026-09-27

## Context

stack-inspect will involve many choices whose reasoning won't be obvious later, especially choices made to keep the long-term invalidation graph reachable while building the simpler execution graph first.

## Decision

We record significant architectural decisions as Architecture Decision Records (ADRs), using Michael Nygard's format: context, decision, consequences.

- ADRs live in `docs/adr/`, numbered sequentially: `NNNN-short-title.md`.
- Each ADR has a status: Proposed, Accepted, Superseded or Deprecated.
- Accepted ADRs aren't rewritten. A changed decision gets a new ADR that supersedes the old one, and both are cross-linked.

## Consequences

- The reasoning behind the design survives beyond the conversations where it was decided.
- Writing an ADR adds a little overhead to each significant decision.
