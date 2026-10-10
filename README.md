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

`make stack-values` launches that same stack with `STACK_INSPECT_VALUES=1` and `NEXT_PUBLIC_STACK_INSPECT_VALUES=1`, so SQL arguments, a short row preview, request parameters and the React state value that changed are recorded.

Then open the app at <http://127.0.0.1:3000> and the graph at <http://127.0.0.1:9477>. The collector binds to loopback only. The page fills in as you use the app: each click is a trace, the timeline shows which layer did the work, and the graph keeps the links it has seen. **Export**, beside **Reset**, downloads a Markdown or JSON report of the story on screen. Dashed lines are read from the application source when the collector is started with `--root`, and they appear only where both ends have already been recorded. The reference stack passes `--root` for the example apps, so the scan never reads stack-inspect itself. For another app, start the collector with `--root` pointed at that app (or set `STACK_INSPECT_ROOTS`). With no roots, the collector does not guess a directory, and the graph says that roots are required.

A second app at <http://127.0.0.1:8010> is a jobs API plus a worker process. **Run a job** queues work on the API and a separate process continues that trace, so the graph shows a jobs lane and a worker lane.

## Use it in an application

The setup page is [`docs/setup.md`](docs/setup.md): what to install, which environment variables the server and the browser each need, and the FastAPI, database, Next.js and React calls. The adapters do nothing unless `STACK_INSPECT=1`, and the page also needs `NEXT_PUBLIC_STACK_INSPECT=1`. They refuse to start in production.

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
