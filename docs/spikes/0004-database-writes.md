# Spike: Database writes to invalidations

**Status:** Stopped at the table name. Not an architecture decision. Do not build M12.

## Question

Can a PostgreSQL write be linked to the cached read of the same data?

## What was tried

The running reference app was read back from the collector. The log held 203 events. The reference database was asked for its replication settings.

The only PostgreSQL writes are the API startup seed: `create table if not exists items`, `delete from items`, and five `insert into items (id, name) values ($1, $2)`. Those events are `untraced`. They share no trace with a later read.

The cached read is the TanStack key `["results"]`. Load cached results fetches `GET /api/dashboard`, which runs `select count(*) from items`. That statement is in the click's trace. The cache event carries `queryKey` and does not name `items`. Invalidate results marks `ResultsPanel` stale and writes nothing.

The worker's `notes` statements are SQLite, not PostgreSQL. They are a `create table` and a `select count(*)`, with no insert.

The statement text already contains the table name, so a parser could see that the insert and the select both mention `items`. The reference database has `wal_level` set to `replica`, no replication slot, no publication and no trigger. The application never issues `LISTEN` or `NOTIFY`.

## What we kept

The statement text on each query, including the table name. The seed writes as their own nodes. The `read` and `invalidated` edges between `ResultsPanel` and `browser:query:["results"]`, which come from the TanStack client and not from a write.

## What we will not claim

Two statements that mention `items` are not an invalidation. The seed runs before any click, in another trace, and nothing tells the `["results"]` cache that `items` changed. The cache key does not name the table, and [spike 0003](0003-cross-boundary-dependencies.md) found no join from that key to the query.

`LISTEN`/`NOTIFY` would have to be added to the application. Logical decoding would need `wal_level=logical`, a publication and a replication slot, none of which this database has. Either mechanism would still report a table change, not the cache key.

A later spike could draw an inferred edge between a write statement and a read statement that name the same table. The reference app can show that both mention `items`. It cannot show that the write invalidated a cache. That claim is not scheduled.

## Conclusion

M12 is not feasible from the events as they stand. The collector can see which statements mention a table. It cannot see that a write invalidated a cached read.

## Next step

Do not draw an `invalidated` edge because two statements mention the same table. Leave the statement text and the TanStack invalidation as they are.

No further research gate is scheduled. M9 stays as [spike 0001](0001-react-reads.md) left it.
