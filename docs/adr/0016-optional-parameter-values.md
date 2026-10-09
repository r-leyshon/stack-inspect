# 16. Optional recording of parameter values

- **Status:** Proposed
- **Date:** 2026-10-08

## Context

[ADR 0006](0006-development-only-guarantee.md) keeps request bodies, cookies, tokens and SQL parameter values out of the log unless someone explicitly turns that on. The adapters had no such switch: bound arguments were always dropped. A local run against synthetic data still could not show which value was passed.

[Spike 0002](../spikes/0002-backend-reads.md) found that seeing those values would not say which parameter became which placeholder. Two equal values are not a cause. That conclusion stands.

## Decision

- **Flag.** `STACK_INSPECT_VALUES=1` records parameter values. It does nothing unless `STACK_INSPECT=1`, and it is still refused in production.
- **What is included.** A query event gains its bound arguments, in order, or by name when the driver provides names, and a short preview of the rows the driver already returned. An API request gains its path parameters and its query-string parameters. A React state update gains the hook value that changed. `stack_inspect_traceparent` is the trace carrier and is not treated as an application parameter. Keys named password, token, cookie, secret or authorization are still removed. Long strings are shortened, and only a bounded number of values are kept. The browser reads `NEXT_PUBLIC_STACK_INSPECT_VALUES` as well as `STACK_INSPECT_VALUES`, because the page bundle cannot see a server-only variable.
- **What stays out.** Request bodies, cookies, authorization headers, and storage record contents stay out. The SQLAlchemy cursor is left unread, so that path records arguments and not rows. The node key stays the SQL fingerprint, the request path, or the component name. A full fiber dump stays out. Nothing in the reference stack or the end-to-end script sets the flag.
- **No inferred edge.** Matching a recorded value to a placeholder does not draw an edge. The changed React value is not a record of which state the component read.
- **Visible when on.** The status line says parameter values are being recorded. The Values control starts on. It draws the playhead run halfway along each line on the graph and on the sequence diagram, in the same label. A dot with no line shows that label beside it. Turn the control off to leave the lines clear. Hovering a dot still lists the runs up to the playhead. A report that contains them says they were included because recording was turned on.

## Consequences

- A person testing with synthetic data can turn the flag on and share the report. The default log stays free of those values.
- A positional SQL argument that happens to be a password is stored when the flag is on. The flag is the warning.
- M9 and M10 remain unbuilt. The flag shows values that were already in hand. It does not name which parameter became `$1`, and it does not name which state a component read.
