# stack-inspect-db

Records SQL statements issued through asyncpg or SQLAlchemy. Each query is kept as a normalised fingerprint. Parameter values, and a short preview of rows asyncpg already returned, are stored only when `STACK_INSPECT_VALUES=1`. The SQLAlchemy cursor is left unread. For asyncpg, the trace id is also attached as a SQL comment so database logs can be matched to the request.

```python
import stack_inspect_db

stack_inspect_db.install()
```

`asyncpg` and `SQLAlchemy` are not dependencies of this package. Each is patched only when the application has already imported it. Does nothing unless `STACK_INSPECT=1`.
