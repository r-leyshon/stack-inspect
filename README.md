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

Then open the app at <http://127.0.0.1:3000> and the graph at <http://127.0.0.1:9477>. The collector binds to loopback only.

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
