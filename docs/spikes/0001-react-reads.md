# Spike: React read tracking

**Status:** Stopped at the fiber. Not an architecture decision. M9 stays open.

## Question

On Unchanged child and Fan out, can the adapter name which state or props a component read during render, and which of those had changed?

## What was tried

The React adapter already walks the fiber tree after a commit. Each fiber exposes `memoizedState` and `memoizedProps` from after the render, plus the previous fiber on `alternate`. Comparing those answers two questions:

- Did this component's own hook state change?
- Did its props change?

It does not answer which of those values the function actually read. React does not record a read set. The values are simply what is left on the fiber when the commit finishes. A component can close over a value, ignore a prop, or read context, and the fiber looks the same.

## What we kept

Where the comparison is solid, the render names that state update in `causeIds`:

- Its own state changed in the same commit: the render and a restarted effect cause that state update.
- Its own state did not change, and an ancestor's state did: the render causes that ancestor's state update. This is how `QuietChild` and `FanChild` point at the parent update that carried them along.

The projector turns `causeIds` into a `caused` edge.

The value that changed may be stored on that state-update event when `STACK_INSPECT_VALUES=1` ([ADR 0016](../adr/0016-optional-parameter-values.md)). That is the new hook value, not a list of what the function read.

## What we will not claim

A `caused` edge here means "this state update was in the commit that produced this render". It does not mean the component read that state. Naming the read set needs a mechanism React does not give the DevTools hook: a compiler, a custom renderer, or a wrapper around every state cell. That is a later spike, not a small extension of the fiber walk.
