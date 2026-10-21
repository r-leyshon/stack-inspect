/**
 * Records incoming Next.js requests and the outgoing fetch calls they make.
 * Call `register` from `instrumentation.ts`. Wrap middleware with `withStackInspect`.
 */
import { AsyncLocalStorage } from "node:async_hooks";
import http from "node:http";
import {
  collectorUrl,
  emit,
  enabled,
  formatTraceparent,
  type GraphEvent,
  newEventId,
  newSpanId,
  newTraceId,
  parseTraceparent,
  setSink,
} from "@stack-inspect/core";

type Store = { traceId: string; spanId: string; eventId: string };

type MiddlewareRequest = {
  headers: { get(name: string): string | null };
  nextUrl: { pathname: string };
};

type MiddlewareResponse =
  | {
      status: number;
      headers: { get(name: string): string | null };
    }
  | null
  | undefined
  | Response;

type Middleware = (
  request: MiddlewareRequest,
  event: unknown,
) => MiddlewareResponse | Promise<MiddlewareResponse>;

const storage = new AsyncLocalStorage<Store>();
let registered = false;

/** Patch the Node HTTP server and global fetch. Call from `instrumentation.ts`. */
export function register(): void {
  if (registered || !enabled()) {
    return;
  }
  registered = true;
  const socketPath = process.env.STACK_INSPECT_SOCKET;
  if (socketPath) {
    setSink((event) => postToSocket(socketPath, event));
  }
  patchIncoming();
  patchFetch();
}

function postToSocket(socketPath: string, event: GraphEvent): void {
  const body = JSON.stringify(event);
  const request = http.request({
    socketPath,
    path: "/v1/events",
    method: "POST",
    headers: {
      "content-type": "text/plain",
      "content-length": Buffer.byteLength(body),
    },
  });
  request.on("error", () => undefined);
  request.end(body);
}

/** Record whether middleware rewrote, redirected or continued. */
export function withStackInspect(middleware: Middleware): Middleware {
  return async (request, event) => {
    const response = await middleware(request, event);
    if (!enabled()) {
      return response;
    }
    const headers = response && "headers" in response ? response.headers : null;
    const rewrite = headers?.get("x-middleware-rewrite") ?? null;
    const location = headers?.get("location") ?? null;
    const decision = rewrite ? "rewrite" : location ? "redirect" : "next";
    const store = storage.getStore();
    emit({
      id: newEventId(),
      traceId: store?.traceId ?? traceIdFrom(request),
      parentId: store?.eventId,
      nodeKey: "next:middleware",
      kind: "middleware",
      layer: "next",
      phase: "instant",
      name: decision,
      ts: Date.now(),
      attributes: {
        path: request.nextUrl.pathname,
        decision,
        status: response && "status" in response ? response.status : 200,
      },
    });
    return response;
  };
}

function patchIncoming(): void {
  const server = http.Server.prototype;
  const originalEmit = server.emit;
  server.emit = function (event: string, ...args: unknown[]): boolean {
    if (event !== "request") {
      return originalEmit.apply(this, [event, ...args]);
    }
    const request = args[0] as http.IncomingMessage;
    const header = request.headers.traceparent;
    const parsed = typeof header === "string" ? parseTraceparent(header) : null;
    const store: Store = {
      traceId: parsed?.traceId ?? newTraceId(),
      spanId: newSpanId(),
      eventId: newEventId(),
    };
    const path = request.url?.split("?")[0] ?? "/";
    emit({
      id: store.eventId,
      traceId: store.traceId,
      nodeKey: `next:request:${path}`,
      kind: "request",
      layer: "next",
      phase: "start",
      name: `${request.method ?? "GET"} ${path}`,
      ts: Date.now(),
      attributes: {
        method: request.method ?? "GET",
        path,
        ...(parsed ? { parentSpanId: parsed.spanId } : {}),
      },
    });
    return storage.run(store, () => originalEmit.apply(this, [event, ...args]));
  };
}

function patchFetch(): void {
  const original = globalThis.fetch.bind(globalThis);
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = requestUrl(input);
    // Skip the collector itself — including a proxied or non-default URL.
    if (url.startsWith(collectorUrl())) {
      return original(input, init);
    }
    const store = storage.getStore();
    const headers = new Headers(init?.headers);
    const carried = headers.get("traceparent");
    const parsed = carried ? parseTraceparent(carried) : null;
    const traceId = parsed?.traceId ?? store?.traceId ?? newTraceId();
    const spanId = newSpanId();
    if (!carried) {
      headers.set("traceparent", formatTraceparent(traceId, spanId));
    }
    const id = newEventId();
    const path = safePath(url);
    const method = (init?.method ?? "GET").toUpperCase();
    emit({
      id,
      traceId,
      parentId: store?.eventId,
      nodeKey: `next:request:${path}`,
      kind: "request",
      layer: "next",
      phase: "start",
      name: `${method} ${path}`,
      ts: Date.now(),
      attributes: {
        method,
        path,
        ...(carried ? {} : { spanId }),
      },
    });
    const response = await original(input, { ...init, headers });
    emit({
      id: newEventId(),
      traceId,
      parentId: id,
      nodeKey: `next:request:${path}`,
      kind: "request",
      layer: "next",
      phase: "end",
      name: `${method} ${path}`,
      ts: Date.now(),
      attributes: { method, path, status: response.status },
    });
    return response;
  };
}

function traceIdFrom(request: MiddlewareRequest): string {
  const header = request.headers.get("traceparent");
  return (header && parseTraceparent(header)?.traceId) || newTraceId();
}

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") {
    return input;
  }
  if (input instanceof URL) {
    return input.toString();
  }
  return input.url;
}

function safePath(url: string): string {
  try {
    return new URL(url).pathname;
  } catch {
    return url;
  }
}
