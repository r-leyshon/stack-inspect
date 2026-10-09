# Spike: Dependencies across boundaries

**Status:** Stopped at the request. Not an architecture decision. Do not build M11.

## Question

Can a dependency cross HTTP, so a frontend cache key or value is linked to the backend work it causes, beyond the span-id edge that already says this request ran that request?

## What was tried

The running reference app was read back from the collector after Load cached results and Invalidate results. The log held 203 events.

The TanStack observer records a `read` edge from `browser:render:ResultsPanel` to `browser:query:["results"]`, and an `invalidated` edge back to that render. Those events carry `queryKey`. They carry no path, no span id and no parent.

The refetch records `browser:request:/api/dashboard` with a span id. That span id is the cause of `api:request:GET /api/dashboard`, which contains `select count(*) from items`. Those events carry the path and the span id. They carry no query key.

The cache-key events and the dashboard fetch share a trace because every click in that session fell inside the eight-second trace window. The same trace also holds the crash, the N+1, the stream and several other dashboard fetches. The render events have no parent. The fetch's parent is the Load cached results interaction.

Invalidate results emits the cache-key event and no fetch.

The source snapshot includes `browser:request:/api/dashboard` to `api:request:GET /api/dashboard`. The span id already draws that pair, so the declared copy stays off the graph. The scanner keeps the path and drops which function the fetch sat in. It does not read `queryKey`. The page's `useQuery` and the Next route both fetch that path, and the snapshot keeps one of those sites.

No stream event carries a query key.

## What we kept

The span-id `caused` edge from the browser request to the API request, and from the API request to the query. The `read` and `invalidated` edges between ResultsPanel and the cache key. The declared route-to-SQL edges.

## What we will not claim

Nothing on the wire copies the cache key onto the request, or the request path onto the cache. Sharing a trace is not a cause: this session's trace contains unrelated requests. Sharing a click is not a cause either. The observer event is not a child of the interaction, a second query in that click would meet the same fetch, and an invalidation meets no fetch at all.

Matching a recorded value to a JSON field or a bound parameter is the inference [spike 0002](0002-backend-reads.md) refused.

A later spike could try a narrower static claim: a literal `queryKey` whose `queryFn` fetches a literal path. The reference app has that shape. It would be a dashed claim about the source, of the same kind as [ADR 0014](../adr/0014-declared-edges-from-source.md), and it would say the function fetches that path. It would not say a value was read, and it would not say the cache depends on the rows. That claim is not scheduled.

## Conclusion

M11 is not feasible from the events as they stand. The collector can say which request ran which request, and which component reads which cache key. It cannot say that the cache key depends on the backend work.

## Next step

Do not join a cache key to a request because they share a trace, a click, or a value. Leave the span-id cause and the browser `read` and `invalidated` edges as they are.

The next research gate was M12. That spike has since stopped: a shared table name is not an invalidation of a cache ([spike](0004-database-writes.md)). No further research gate is scheduled.
