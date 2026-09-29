# stack-inspect-db

Records SQL statements issued through asyncpg or SQLAlchemy. Parameter values are never stored: each query is kept as a normalised fingerprint. For asyncpg, the trace id is also attached as a SQL comment so database logs can be matched to the request.

```python
import stack_inspect_db

stack_inspect_db.install()
```

`asyncpg` and `SQLAlchemy` are not dependencies of this package. Each is patched only when the application has already imported it. Does nothing unless `STACK_INSPECT=1`.
