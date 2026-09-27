# stack-inspect-db

Records SQL statements issued through asyncpg. Parameter values are never stored: each query is kept as a normalised fingerprint, with the trace id attached as a SQL comment so database logs can be matched to the request.

```python
import stack_inspect_db

stack_inspect_db.install()
```

`asyncpg` is not a dependency of this package. It is patched only when the application has already imported it. Does nothing unless `STACK_INSPECT=1`.
