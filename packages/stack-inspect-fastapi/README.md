# stack-inspect-fastapi

Records HTTP requests, the middleware stack, CORS preflights, server-sent events and WebSockets from a FastAPI or Starlette application. It has no dependency on FastAPI itself: the application you install it into already provides Starlette.

```python
import stack_inspect_fastapi

stack_inspect_fastapi.install(app)
```

Does nothing unless `STACK_INSPECT=1` and the process is not production. Path and query-string parameters are recorded only when `STACK_INSPECT_VALUES=1`. Request bodies, cookies and authorization headers are not.
