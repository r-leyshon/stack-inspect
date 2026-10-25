# Agentic layer

**Status:** The read tools are implemented ([ADR 0019](adr/0019-mcp-on-the-collector.md)). Findings carry span timing, method and idempotent flags where they apply, and `siblings` in the same story. Graph nodes expose `runs` alongside `count`. Mount and unmount events, and observed effect→fetch `causeIds`, are recorded when the React and browser adapters are installed. Playwright journeys, playhead control and invalidation questions are not.

While `stack-inspect serve` is running, a client attaches to `http://127.0.0.1:9477/mcp`. The tools are `list_findings`, `get_finding`, `get_report`, `list_stories`, `get_graph` and `get_node_neighbourhood`. Each finding includes a link, `http://127.0.0.1:9477/?trace=…&finding=…`, and the page opens that story and that finding. `get_finding` also returns the finding-neighbourhood graph slice. Duplicate and repeated findings say how many times the work ran and over how long. Unchanged re-renders are one ranked summary per story (`offenders`). A graph over the limit returns only `nodeCount` and `edgeCount` until narrowed; each node’s `runs` / `count` is how many times that key ran in the story. The tools do not clear the log, move the playhead, scan source, or turn value recording on.

## North star

Treat the collector as a **local evidence plane** for coding agents: structured, redacted, addressable context about what an interaction actually did. The agent talks about findings, node keys, edges, stories and a playhead moment. It does not scrape the graph canvas.

stack-inspect stays the source of truth. Claude, Cursor, Copilot or any other client attaches to the same projected model the UI already uses.

## Why MCP

An MCP server on the collector is the flexible front door. One server, many agents. Users point their preferred client at it. Cursor, Claude Desktop and a custom Claude Code config all speak the same protocol.

| Shape | Role |
| :-- | :-- |
| **MCP server** (`127.0.0.1` only) | Agent-agnostic. Same development-only bind as the collector ([ADR 0006](adr/0006-development-only-guarantee.md)). |
| **Tools** | Imperative questions: list findings, explain a finding, graph at a moment, neighbourhood of a node, diff two playheads. |
| **Resources** | Pullable snapshots, for example `stack-inspect://session/latest/report.md`, `…/findings.json`, `…/graph@cursor`. |
| **Prompts** (optional) | Packaged workflows: triage duplicated work, explain a CORS finding, turn a finding into a regression scenario. |

The HTTP surface is already most of this façade:

- `GET /v1/graph` — projected nodes and edges, including declared edges when both ends were observed.
- `GET /v1/findings` — analysis findings with `code`, `title`, `traceId`, `detail`, `at`, `nodeKeys`, optional timing and method fields, and `siblings` in the same story.
- `GET /v1/traces` — one summary per story, for the timeline.
- `GET /v1/report` — Markdown by default, JSON when asked. Already a good LLM context blob.
- `POST /v1/declared` — returns the source snapshot. Named roots are already read at startup; this reads them again.

MCP wraps those with clearer schemas, so an agent does not have to guess query parameters. Anything that cannot speak MCP still gets the stable JSON and Markdown report. A thin `stack-inspect ask` style CLI, or an "attach context" button that copies a finding-scoped bundle, covers the rest. Do not bake one vendor's agent SDK in as the only path.

## Conversation shapes

1. **Triage.** "What is the worst finding right now?" Ranked findings with node keys, counts, timestamps, and a deep link that opens the finding and playhead in the UI.
2. **Moment.** The agent binds to the playhead, a story, or a selected node. "Why is this node red?" and "What caused this query?" are answered from `causeIds`, edges and the finding, not from a guess.
3. **Diff.** "What changed after my fix?" Two recordings, or two cursors on one recording. Delta on findings, duplicated edges and span counts.
4. **Fix proposal.** Finding, then hypothesis, then a suggested code change that cites `finding` codes, node keys and event ids. The agent edits the repo. stack-inspect only supplies the proof.
5. **Narrated trace.** "Walk me through the last click." Browser, Next.js, API, SQL, with the arrangement's compressed gaps called out. The reactlog moment, in prose.

## Playwright and findings

A closed loop, with the browser driver and the evidence store kept apart:

```text
Agent or script
  → Playwright journey (Gherkin step or generated test)
  → the app emits events into the collector
  → rules produce findings
  → MCP tools return findings and a sliced graph
  → the agent proposes a fix or opens a pull request
  → the journey runs again, and the findings should shrink or change
```

Playwright drives the **app under test**. MCP talks to the **collector**. Driving the graph UI for evidence is brittle; query the API instead.

Variants worth keeping:

- **Planted-bug check.** The reference app already aims for "every planted problem raises a finding" ([roadmap](roadmap.md) M6). The journey asserts finding titles or codes, not only the DOM.
- **Journey from a finding.** "Record a journey that reproduces this duplicated request." The agent writes Playwright from the finding's `nodeKeys` and the story's timestamps.
- **Repeated runs.** Run a journey several times and summarise repeated, cancelled and CORS findings across runs.
- **Acceptance stays human.** The feature file stays in the developer's language ([testing](testing.md)). The agent fills the glue that asserts `GET /v1/findings`.

If a `run_journey` tool ever exists, prefer a sibling package that emits into the collector. Owning the browser lifecycle inside the collector is a large extra product.

## Starter tools

Read-only first. That matches redaction by default and local-first ([vision](vision.md)).

- `list_findings` / `get_finding`
- `get_report` — the Markdown the collector already renders
- `get_graph` — filters for story, cursor, layer and node key
- `get_story` / `list_stories` — arrangement clips
- `get_node_neighbourhood` — the ego graph around a finding
- `compare_sessions` — later

Session control, still local and still gated:

- `clear_recording` / `export_session`
- `set_cursor` / `select_finding` — so a human watching the UI sees what the agent is talking about
- `run_declared_scan` — wraps `POST /v1/declared`

## Where it sits

The agent layer sits in the collector process, not inside the adapters. Adapters stay thin ([ADR 0011](adr/0011-minimal-runtime-dependencies.md)).

```text
adapters → event log → projector and rules → UI
                              ↓
                         MCP / agent API
                              ↓
                    Cursor, Claude, or another client
```

Agents inherit the same redacted views as the UI. Request bodies, cookies and tokens stay out. SQL arguments, a short row preview, request parameters and the React state value that changed stay out unless `STACK_INSPECT_VALUES=1` ([ADR 0016](adr/0016-optional-parameter-values.md)).

The graph model should already be ready for later questions. `causeIds`, `read` and `invalidated` stay in the schema ([ADR 0004](adr/0004-invalidation-ready-graph-model.md)), so an MCP tool can grow those fields without a new protocol.

## Later product modes

- **Pair debugger.** The human clicks around. The agent watches a live findings stream and speaks only when something new fires.
- **Review buddy.** Before a pull request, smoke journeys run and the report is pasted into the description or the review prompt.
- **Invalidation tutor.** Once reads and invalidations fill in, "why did this re-render?" becomes the main question. Design the tools so those fields can appear without a schema break.
- **Finding to ticket.** A structured export: title, evidence, a reproduction-journey stub, and a severity.

## Risks

- **Context size.** A full graph will not fit a prompt. Tools return slices: a finding's neighbourhood, one story, or a cursor window. Opening a finding should prefer that neighbourhood over a whole-story dump ([ADR 0020](adr/0020-story-boundaries-and-finding-noise.md)). Same-code render noise is one ranked summary per story, not one finding per component.
- **Secrets.** Agents ask for more context. Do not widen redaction for "better answers" without an explicit opt-in. Keep MCP on localhost only.
- **Invented causality.** Answers cite a finding code, node key or event id. The tool does not invent edges, and it does not present an observed edge as a universal dependency ([vision](vision.md), evidence not claims).
- **Silent edits.** Start with explain, suggest, and re-verify. Automatic patches come after the loop is trustworthy.
- **Browser ownership.** A journey runner inside stack-inspect takes on Playwright's lifecycle. Leave that outside unless a later ADR says otherwise.

## A pragmatic ladder

1. **Bundle for agents.** Done. `?trace=` and `?finding=` open that story and that finding.
2. **MCP read tools** wrapping graph, findings and report. Done. See the status above.
3. **Playwright journeys that assert findings** in the reference app. The Gherkin suite already covers the planted problems, including a fetch caused by `useEffect`.
4. **A short agent-loop note** in the docs: attach MCP, run a journey, triage findings, patch, re-run.
5. **Live subscribe and UI sync.** The agent sets the playhead or highlights a finding while the human watches.
6. **Invalidation-aware questions** once Horizon 3 has something to say.

## First demo worth aiming at

`list_findings` and `get_report` are available over MCP, and a finding link opens that story in the UI. The reference Gherkin suite plants duplicate fetch, effect→fetch and the other findings; an agent-driven loop that calls MCP after a journey is still the next step.
