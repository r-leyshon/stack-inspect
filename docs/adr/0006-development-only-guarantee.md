# 6. Guarantee development-only use

- **Status:** Proposed
- **Date:** 2026-09-27

## Context

stack-inspect monkey-patches runtimes, records detailed internal behaviour, slows the app down and exposes a local collector. Like `reactlog`, it must never run in production. That has to be enforced, not just documented.

## Decision

- **Opt-in:** adapters do nothing unless explicitly enabled with `STACK_INSPECT=1`.
- **Refuse production:** adapters also refuse to start if `NODE_ENV=production` or a production Next.js build is detected, or if FastAPI isn't running in a development configuration. When they refuse, they log a clear warning.
- **Local only:** the collector binds to `127.0.0.1` and rejects connections from other hosts.
- **Separate packages:** adapters ship as development dependencies, so production builds don't include them.
- **Redaction by default:** no bodies, cookies, tokens or SQL parameter values are recorded unless explicitly enabled. That switch is `STACK_INSPECT_VALUES=1` ([ADR 0016](0016-optional-parameter-values.md)).

## Consequences

- Using stack-inspect against a remote staging environment isn't supported initially.
- Enabling it takes a deliberate extra step, which is intended.
