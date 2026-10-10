# 19. MCP on the collector

- **Status:** Proposed
- **Date:** 2026-10-10

## Context

A coding agent needs the same evidence the UI shows: findings, a story, and the graph around a node. Scraping the canvas is brittle. The HTTP API already projects that evidence, and an agent should not have to guess query parameters or invent an edge.

The collector already binds to loopback only ([ADR 0006](0006-development-only-guarantee.md)). Adapters stay free of extra runtime dependencies ([ADR 0011](0011-minimal-runtime-dependencies.md)). The collector may take a dependency the adapters do not.

## Decision

- **Inside the collector.** `stack-inspect serve` mounts a Streamable HTTP MCP server at `/mcp` on the same `127.0.0.1` process. There is no second port and no stdio sidecar. The loopback check covers `/mcp`.
- **Read-only.** The tools are `list_findings`, `get_finding`, `get_report`, `list_stories`, `get_graph` and `get_node_neighbourhood`. They call the same projection, analysis and report as the HTTP API. They do not clear the log, move the playhead, scan source, or turn value recording on.
- **Slices.** A tool returns one story, one finding, or the edges that touch one node. A graph over the limit tells the caller to narrow the question. It does not paste the whole log into the reply.
- **Citations.** A finding reply includes its `code`, `traceId`, `nodeKeys`, and a link that opens that finding in the UI. The tool does not invent an edge and does not rank a new severity.
- **Dependency.** The `mcp` package is a dependency of the collector only.

## Consequences

- An MCP client attaches to `http://127.0.0.1:9477/mcp` while the collector is running.
- Installing adapters and starting the collector stay outside MCP. The server cannot bring itself up.
- Playwright journeys, playhead control and session compare stay unbuilt.
