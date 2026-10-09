# 17. The graph layout rests, and a large picture sits in columns

- **Status:** Proposed
- **Date:** 2026-10-09

## Context

The collector draws the visible graph by pushing every dot against every other dot, on every frame, including after the dots have stopped moving. Captions, run counts and latency medians were also rebuilt from the whole log on every frame. That stays responsive for one story. It does not stay responsive for every node a larger application records in a session.

## Decision

- **Force layout while the picture is a diagram.** This trace pushes dots apart while 250 or fewer dots are visible. All activity does so while 120 or fewer are visible. The count is the visible dots, because the work is the pairs among them.
- **Columns after that.** Above those counts the dots sit in the four layer columns, ordered by when they were first seen. The picture is placed once when that set changes.
- **Rest.** Under either ceiling the simulation stops once the dots are still, and the canvas is left unpainted until the playhead, the filters, the camera or a new event changes the picture. Dragging a dot moves that dot only. A new visible set starts the simulation again.
- **One pass per change.** The playhead caption, the run count and the latency median for each dot are computed when the playhead or the log changes, then reused by both drawings.

## Consequences

- A settled story costs nothing while it sits on screen, with Values left on.
- All activity past 120 dots, and a single story past 250, reads as columns rather than a force diagram. Fit recentres that picture.
