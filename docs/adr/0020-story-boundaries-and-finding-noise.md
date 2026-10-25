# 20. Story boundaries and finding noise at application scale

- **Status:** Accepted
- **Date:** 2026-10-25

## Context

A real Next.js application (Justice Transcribe) produces stories that overwhelm both the graph and the findings panel: one click can fold hundreds of events into a single `traceId` when the window merges navigations, and a single story can raise dozens of identical-title findings such as `unchanged-rerender`. Agents hitting MCP then receive a raw graph dump until the size limit, or a findings list that is mostly the same alert repeated.

Three separate problems look like one "the graph is too complex" complaint:

1. **Story boundaries.** Client-side route changes after a click stay in the same `traceId` window, so two product moments share one story.
2. **Visual density.** Self-loops and busy neighbourhoods look like duplicate edges; the projector already folds repeats into `count`.
3. **Finding noise.** Rules that emit one finding per span (notably unchanged re-renders) make the panel and `list_findings` unusable at scale. A finding-centric neighbourhood slice helps the graph view; it does not by itself make ninety-two same-title alerts actionable.

## Decision

### Navigation as a story boundary

When the browser adapter observes a navigation (History API or equivalent) that changes the document URL path or hash in a way that is not query-string-only, start a new `traceId` for subsequent events, and record an observed navigation event that *links* the previous story to the next. Do not invent a causal edge from the click to every render in the new route. Query-string-only changes, back/forward that restore a prior story, and worker traces without a document URL stay out of this split until they have their own evidence.

### Edge rendering, not edge model

Keep counted edges as they are. In the drawing, collapse self-loops into a labelled badge on the node (for example `×17`) and prefer neighbourhood slices over full-story force layouts when the visible set is large. Do not store seventeen parallel edge records for the same pair.

### Finding-neighbourhood default

The UI and MCP share one slice: opening a finding (or `get_finding` / `get_node_neighbourhood`) returns the ego graph around that finding's `nodeKeys`, not the whole story. `get_graph` without a neighbourhood still may hit the size limit and must say so; it must not dump until truncated without guidance.

### Coalesce same-code render noise

For `unchanged-rerender` within one story, emit **one summary finding**, not one finding per span:

- **Title** names the volume, for example "27 components re-rendered with no changed props or state".
- **Detail** ranks offenders by event count, for example "top offenders: Presence ×17, Dialog ×8, UserSettingsProvider ×5".
- **`count`** is the total unchanged-render events in the story.
- **`nodeKeys`** are the ranked offender keys (capped), so opening the finding still paints the right neighbourhood.
- **`firstAt` / `lastAt` / `durationMs`** cover the span window of those events.

Per-component unchanged-rerender findings are not listed at the top level. Drill-down (UI expansion or a structured `offenders` field on the summary) exposes the per-component breakdown when someone needs a specific key. The same coalescing pattern applies to any future same-code, same-title flood that is only useful as a ranked summary.

Other rules that already group by fingerprint or node (duplicate requests, repeated queries, restarted effects) keep their existing shape.

## Consequences

- Findings panels and `list_findings` stay short enough to read on a large application story.
- Agents get the same actionable line a human would: where the noise concentrated, not ninety-two identical titles.
- Story splits make JT-scale timelines closer to product moments; the navigation link preserves continuity without pretending the whole post-navigation tree was caused by the originating click.
- Implementation touches the browser adapter (navigation boundary), `rules.py` (coalesce), the UI findings panel and MCP payloads (offenders / neighbourhood default), and the architecture analysis-rules list. Acceptance coverage belongs in Gherkin once the reference app can plant a multi-offender unchanged-rerender story.
