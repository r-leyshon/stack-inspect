/**
 * Middleware helper. This file stays free of Node built-ins so Next.js can
 * bundle it for the middleware runtime.
 */
import {
  emit,
  enabled,
  newEventId,
  newTraceId,
  parseTraceparent,
} from "@stack-inspect/core";

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
    const header = request.headers.get("traceparent");
    const traceId =
      (header && parseTraceparent(header)?.traceId) || newTraceId();
    emit({
      id: newEventId(),
      traceId,
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
