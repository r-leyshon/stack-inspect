# 13. Service names, a string-map carrier, and a local socket

- **Status:** Proposed
- **Date:** 2026-09-27

## Context

A recording can leave the request that started it and continue in another process: a worker, a sidecar, or a browser worker writing to IndexedDB or the Origin Private File System. Those processes are not a fixed set, and the hop between them is not always HTTP.

Binding the collector to anything but loopback would let a container reach it, and would also let the rest of the machine reach it.

## Decision

- **Service name.** A process may set `STACK_INSPECT_SERVICE`. The name is copied onto each event. It is not an enumeration. The UI shows service lanes when one trace contains more than one name, and otherwise keeps the existing layer lanes.
- **Carrier.** `inject` writes the active W3C `traceparent` into a plain string map. `extract` reads it back. HTTP headers remain the carrier for HTTP. Any other hop is the application's map: queue properties, metadata, a job payload. stack-inspect does not ship an adapter for a particular queue or store.
- **Browser storage.** IndexedDB and the Origin Private File System are wrapped like `fetch`. The event records the store or path, the operation, and a byte count. Values and file bytes are not recorded. The storage install runs in a worker, because sync file access exists only there.
- **Socket.** The collector can also listen on a Unix socket (`--socket` or `STACK_INSPECT_SOCKET`). A container mounts that socket. The TCP listener stays on `127.0.0.1` and still refuses any other client. The socket file is mode `0600`.
- **SQLAlchemy** is an optional extra of the database adapter, beside asyncpg. It listens for statement execution. It records bound arguments only when `STACK_INSPECT_VALUES=1` ([ADR 0016](0016-optional-parameter-values.md)).

## Consequences

- An application continues a trace by copying a map it already owns. Nothing in the core names that application's queues.
- Two processes are distinguishable only when they set different service names.
- Containers reach the collector by a mounted socket, not by opening a port.
