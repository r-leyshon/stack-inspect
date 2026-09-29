# stack-inspect

A development-only execution graph for a Next.js, FastAPI and PostgreSQL application. You use the app, and stack-inspect shows what that did: the render, the request, the middleware, the SQL, and the stream messages. It is the first milestone on the way to a cross-stack invalidation graph. See [`docs/vision.md`](docs/vision.md).

Version 1.0 records what ran and what tends to run together. It does not claim to know why every computation ran. That remains the long-term goal, and the event model already has room for it.

## Run the reference app

```bash
uv sync --all-groups
npm ci
npx playwright install chromium
docker compose -f reference/compose.yaml up -d
uv run python scripts/e2e_stack.py
```

Then open the app at <http://127.0.0.1:3000> and the graph at <http://127.0.0.1:9477>. The collector binds to loopback only. The page fills in as you use the app: each click is a trace, the timeline shows which layer did the work, and the graph keeps the links it has seen. **Export**, beside **Reset**, downloads a Markdown or JSON report of the story on screen.

A second app at <http://127.0.0.1:8010> is a jobs API plus a worker process. **Run a job** queues work on the API and a separate process continues that trace, so the graph shows a jobs lane and a worker lane.

## Use it in an application

Set `STACK_INSPECT=1` and run the collector (`uv run stack-inspect serve`). Then, in development only:

```python
import stack_inspect_db
import stack_inspect_fastapi

stack_inspect_db.install()
stack_inspect_fastapi.install(app)
```

```ts
import { register } from "@stack-inspect/next";
import { install as installBrowser } from "@stack-inspect/browser";
import { install as installReact, devtoolsHookSource } from "@stack-inspect/react";
```

The adapters do nothing unless `STACK_INSPECT=1`, and they refuse to start when `NODE_ENV` is `production`.

Name a process with `STACK_INSPECT_SERVICE` (for example `api` or `worker`) so the timeline can tell processes apart. To follow a trace through a queue or any other message, copy `inject()` into the map you already send, and `extract()` it where the message is received. `STACK_INSPECT_SOCKET` posts events through a Unix socket for processes that cannot use loopback TCP; the collector still refuses any other TCP client.

`install()` on the page also records IndexedDB and Origin Private File System calls: the store or path, the operation, and a byte count. Values and file contents are not recorded. A worker calls `installStorage()`, and `adoptTrace(traceparent)` when it was given a trace to continue.

## Tests

```bash
uv run pytest
uv run ruff check .
npx biome check .
npm run test:e2e
```

Acceptance tests are Gherkin feature files in `features/`, run by playwright-bdd against the reference app. Each planted problem (an N+1 query, a duplicate fetch, a CORS failure that is really a server error, a rejected preflight, streams, a needless re-render, a restarted effect, a query invalidation) has a scenario.

## Licence

MIT. See [`LICENSE`](LICENSE).
