# Set up stack-inspect

Development only. The adapters do nothing unless you opt in, and they refuse to start when the process is production. The collector listens on `127.0.0.1` only.

## Install

The collector stays out of the application lockfile. The adapters are development dependencies. They do not install Next.js, React, FastAPI, asyncpg or SQLAlchemy. The application already has those.

A release is two files on one GitHub tag ([ADR 0018](adr/0018-github-release-assets.md)). The wheel's base has no server dependencies. The `serve` extra, used only by `uvx`, adds them. The current pin is `v1.2.1`.

```bash
uvx --from "stack-inspect[serve] @ https://github.com/r-leyshon/stack-inspect/releases/download/v1.2.1/stack_inspect-1.2.1-py3-none-any.whl" stack-inspect serve
uv add --dev https://github.com/r-leyshon/stack-inspect/releases/download/v1.2.1/stack_inspect-1.2.1-py3-none-any.whl
npm install --save-dev https://github.com/r-leyshon/stack-inspect/releases/download/v1.2.1/stack-inspect-1.2.1.tgz
```

Python imports stay `stack_inspect_fastapi`, `stack_inspect_db` and `stack_inspect_core`. The npm package exports `stack-inspect/browser`, `stack-inspect/react`, `stack-inspect/next` and `stack-inspect/next/middleware`. The snippets below use the workspace names in this repository (`@stack-inspect/browser` and the rest). The wheel's database adapter still patches a driver only after the application has imported it.

This checkout still runs the collector with `uv run stack-inspect serve`. A `v*` tag publishes the two files above.

The JavaScript packages in this repository ship TypeScript source, so this checkout lists them in `transpilePackages`. The release tarball ships compiled JavaScript, and a consumer of that tarball can omit the list.

```ts
const nextConfig = {
  transpilePackages: [
    "@stack-inspect/browser",
    "@stack-inspect/core",
    "@stack-inspect/next",
    "@stack-inspect/react",
  ],
};
```

A fetch scan of the web root needs the `typescript` package installed in that application. With no `typescript` package, that scan is skipped. The Python scan does not need it.

## Turn it on

Set these for the API, the Next.js server, and any worker. The browser bundle cannot see a server-only variable, so the page also needs the `NEXT_PUBLIC_` names.

| Variable | Where | Effect |
| :-- | :-- | :-- |
| `STACK_INSPECT=1` | Every process | Opt in. Without it, every `install` returns immediately. |
| `NEXT_PUBLIC_STACK_INSPECT=1` | The page | Same opt-in, visible in the browser bundle. |
| `STACK_INSPECT_VALUES=1` | API and Next.js server | Record SQL arguments, a short asyncpg row preview, path and query parameters, and the React state value that changed. |
| `NEXT_PUBLIC_STACK_INSPECT_VALUES=1` | The page | Same values flag for the browser bundle. |
| `STACK_INSPECT_SERVICE` | A process, when several share a trace | Name on the timeline, for example `api` or `worker`. |
| `STACK_INSPECT_URL` | A process whose collector is not the default | Collector origin. The default is `http://127.0.0.1:9477`. The page reads `NEXT_PUBLIC_STACK_INSPECT_URL`. |

Browser origin: if the app runs at `http://localhost:3000`, the browser treats `http://127.0.0.1:9477` as a different origin. The collector answers CORS, so the browser adapter can post to the default collector URL from either `localhost` or `127.0.0.1` without a proxy.

The Next.js and browser adapters skip instrumenting requests whose URL starts with that configured collector origin. If you point `NEXT_PUBLIC_STACK_INSPECT_URL` at a Next.js proxy path, set `STACK_INSPECT_URL` on the server to the same origin you actually post to, or the adapter will re-enter `emit` and overflow the stack.

Production is refused when `NODE_ENV` or `STACK_INSPECT_ENV` is `production`. Python also refuses `prod`, and refuses `ENVIRONMENT` set to `production` or `prod`. Bodies, cookies and tokens are never recorded. Keys named password, token, cookie, secret or authorization are removed from the values that the flag does record.

## Collector

```bash
uvx --from stack-inspect stack-inspect serve --root /path/to/web --root /path/to/api
```

Open <http://127.0.0.1:9477>. `--root` (or `STACK_INSPECT_ROOTS`, as a path separator list) is the application source. The collector reads those directories for dashed edges and refuses a root that contains stack-inspect. With no roots it does not guess a directory. A dashed edge is drawn only after both ends have already been recorded.

`STACK_INSPECT_SOCKET`, or `--socket`, is a Unix socket for a process that cannot use loopback TCP. The TCP listener still accepts only `127.0.0.1`.

## Attach a client

While `stack-inspect serve` is running, point Cursor, or any other MCP client, at `http://127.0.0.1:9477/mcp`. The tools read findings, the report and slices of the graph. They do not install adapters or start the collector. A finding reply includes a link that opens that finding in the page.

## FastAPI and the database

Call the database adapter before the pool or engine is created. Call the FastAPI adapter after the application's own middleware has been added.

```python
import stack_inspect_db
import stack_inspect_fastapi

stack_inspect_db.install()
stack_inspect_fastapi.install(app)
```

HTTP carries `traceparent` on its own. A queue, a job payload or any other map of strings continues a trace when the sender copies `inject()` into that map and the receiver calls `extract()`:

```python
from stack_inspect_core import extract, inject
from stack_inspect_core.context import use_context

message = inject({"task": "count-notes"})
found = extract(message)
if found is not None:
    with use_context(found):
        ...
```

## Next.js, the page and React

`instrumentation.ts`:

```ts
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { register } = await import("@stack-inspect/next");
    register();
  }
}
```

`middleware.ts`, around the middleware you already have:

```ts
import { withStackInspect } from "@stack-inspect/next/middleware";

export default withStackInspect((request) => NextResponse.next());
```

Install the DevTools hook before React hydrates. Prefer
`instrumentation-client.ts` (Next.js 15.3+). Do not rely on
`next/script` with `beforeInteractive` alone — Next queues that after
its async chunks, so React can load first and never call `inject()`.

```ts
// instrumentation-client.ts (app root)
import { installDevtoolsHook } from "@stack-inspect/react";

installDevtoolsHook();
```

Optional belt-and-braces inline script in the root layout `<head>`:

```tsx
import { devtoolsHookSource } from "@stack-inspect/react";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en-GB">
      <head>
        <script
          dangerouslySetInnerHTML={{ __html: devtoolsHookSource }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
```

A client component, once:

```tsx
"use client";

import { install as installBrowser } from "@stack-inspect/browser";
import { install as installReact } from "@stack-inspect/react";
import React from "react";

installBrowser();
installReact(React);
```

`installBrowser()` records clicks, `fetch`, XHR, EventSource, WebSocket, IndexedDB and the Origin Private File System. A worker calls `installStorage()` and `adoptTrace(traceparent)` when it was given a trace to continue. File contents and stored values are not recorded.

TanStack Query is optional. Pass the client and the component that reads it:

```ts
import { observeQueryClient } from "@stack-inspect/react";

observeQueryClient(queryClient, "ResultsPanel");
```

That records a cache read and an invalidation. It does not wrap component state. There is no call to add in application code for each state cell, parameter or query.
