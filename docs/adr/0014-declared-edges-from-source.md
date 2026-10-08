# 14. Declared edges from source

- **Status:** Proposed
- **Date:** 2026-09-29
- **Revised:** 2026-10-08

## Context

A shared trace is not an edge. The jobs API and the worker can appear in one story with nothing drawn between them, because the worker never learns the event id of the request that queued it. The source, though, names both sides: the route that calls `enqueue`, and the SQL reached from the function that calls `take`.

That relationship was not observed. It must not be written into the event log, which is a record of what ran. It must not be read unless the directories were named, and it must not be read from stack-inspect's own tree.

## Decision

- **Named roots are read with the collector.** The collector reads them as it starts, again when the recording is reset, and again when a source file's size or modification time changes. The same file hashes skip the parse. `POST /v1/declared` still returns that snapshot. The adapters never read source. With no roots, nothing is read, the working directory is not guessed, and the graph says that `--root` is required.
- **Beside the log.** The result is a snapshot of edges whose `source` is `declared` and whose kind is `caused`. It is kept in memory, replaced when the files change, and dropped when the collector process stops. Reset clears the recording and reads the roots again.
- **Both ends observed.** `GET /v1/graph` draws a declared edge only when the recording already contains both node keys. Code that never ran stays off the graph.
- **Explicit roots.** `stack-inspect serve --root` (or `STACK_INSPECT_ROOTS`) names the application directories. The request body cannot name a path. With no roots, the scan does not guess the working directory.
- **The collector is not a root.** A root that is the `stack_inspect` package, that contains it, or that sits inside it, is refused. The walk stays inside each accepted root, skips dependency directories, and does not follow a symlink that leaves the root.
- **What is stored.** Node keys, a SQL fingerprint from the same normaliser as the database adapter, and `file:line`. File bodies are not stored. A second request with the same file hashes returns the cached snapshot.
- **What can be seen.** In Python, a FastAPI route decorator and a SQL literal (`text("...")`, or a string passed to `execute`, `fetch`, `fetchval` or `fetchrow`) in that route's call cone. Also a queue handoff: a route whose call cone reaches `enqueue`, and SQL in the call cone of a function that calls `take`, when both names resolve to the same module inside the roots. In TypeScript, a `fetch` of a literal path, using the `typescript` package installed for that root. Dynamic routes, SQL built up in pieces, and ordinary variable reads are not seen.

## Consequences

- Reset clears the recording and reads the named roots again. A dashed line returns once both of its ends have run.
- A dashed line is a claim about the source, not proof from a run.
- An application with no configured roots has no declared edges. The page says that `--root` is required.
