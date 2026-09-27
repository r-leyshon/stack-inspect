/** Dependency-free helpers shared by the JavaScript adapters. */

const DEFAULT_URL = "http://127.0.0.1:9477";
const HEX = 16;
const TRACE_BYTES = 16;
const SPAN_BYTES = 8;

export type GraphEvent = {
  id: string;
  traceId: string;
  parentId?: string;
  causeIds?: string[];
  nodeKey: string;
  kind: string;
  layer: "browser" | "next" | "api" | "db";
  phase: "start" | "end" | "instant";
  name: string;
  ts: number;
  attributes?: Record<string, unknown>;
};

export type TraceContext = {
  traceId: string;
  spanId: string;
  parentEventId?: string;
};

/** True when this process has opted in and is not production. */
export function enabled(): boolean {
  const flag = readEnv("STACK_INSPECT") ?? readEnv("NEXT_PUBLIC_STACK_INSPECT");
  if (flag !== "1") {
    return false;
  }
  const nodeEnv = readEnv("NODE_ENV");
  const stackEnv = readEnv("STACK_INSPECT_ENV");
  if (nodeEnv === "production" || stackEnv === "production") {
    console.warn(
      "stack-inspect refused to start because this process is production",
    );
    return false;
  }
  return true;
}

/** Collector base URL, without a trailing slash. */
export function collectorUrl(): string {
  return (
    readEnv("STACK_INSPECT_URL") ??
    readEnv("NEXT_PUBLIC_STACK_INSPECT_URL") ??
    DEFAULT_URL
  ).replace(/\/$/, "");
}

/** Post one event. Never throws. Uses a simple content type so browsers skip the preflight. */
export function emit(event: GraphEvent): void {
  if (!enabled()) {
    return;
  }
  const url = `${collectorUrl()}/v1/events`;
  const body = JSON.stringify(event);
  try {
    if (typeof fetch === "function") {
      void fetch(url, {
        method: "POST",
        body,
        headers: { "content-type": "text/plain" },
        keepalive: true,
      }).catch(() => undefined);
      return;
    }
  } catch {
    // The collector is optional. Losing an event must not break the application.
  }
}

/** A new 32 character hex trace id. */
export function newTraceId(): string {
  return randomHex(TRACE_BYTES);
}

/** A new 16 character hex span id. */
export function newSpanId(): string {
  return randomHex(SPAN_BYTES);
}

/** A new event id. */
export function newEventId(): string {
  return randomHex(TRACE_BYTES);
}

/** Format a W3C traceparent header value. */
export function formatTraceparent(traceId: string, spanId: string): string {
  return `00-${traceId}-${spanId}-01`;
}

/** Parse a traceparent header, or return null. */
export function parseTraceparent(
  header: string,
): { traceId: string; spanId: string } | null {
  const parts = header.trim().split("-");
  if (parts.length !== 4 || parts[0] !== "00") {
    return null;
  }
  const traceId = parts[1] ?? "";
  const spanId = parts[2] ?? "";
  if (!/^[0-9a-f]{32}$/.test(traceId) || !/^[0-9a-f]{16}$/.test(spanId)) {
    return null;
  }
  return { traceId, spanId };
}

function randomHex(bytes: number): string {
  const buffer = new Uint8Array(bytes);
  if (crypto?.getRandomValues) {
    crypto.getRandomValues(buffer);
  } else {
    for (let index = 0; index < buffer.length; index += 1) {
      buffer[index] = Math.floor(Math.random() * 256);
    }
  }
  return Array.from(buffer, (value) =>
    value.toString(HEX).padStart(2, "0"),
  ).join("");
}

function readEnv(name: string): string | undefined {
  // Direct property access so Next.js can inline NEXT_PUBLIC_ values into the browser bundle.
  // A dynamic process.env[name] lookup stays empty in the client.
  if (name === "NEXT_PUBLIC_STACK_INSPECT") {
    return process.env.NEXT_PUBLIC_STACK_INSPECT;
  }
  if (name === "NEXT_PUBLIC_STACK_INSPECT_URL") {
    return process.env.NEXT_PUBLIC_STACK_INSPECT_URL;
  }
  if (name === "STACK_INSPECT") {
    return process.env.STACK_INSPECT ?? process.env.NEXT_PUBLIC_STACK_INSPECT;
  }
  if (name === "STACK_INSPECT_URL") {
    return (
      process.env.STACK_INSPECT_URL ?? process.env.NEXT_PUBLIC_STACK_INSPECT_URL
    );
  }
  if (name === "NODE_ENV") {
    return process.env.NODE_ENV;
  }
  if (name === "STACK_INSPECT_ENV") {
    return process.env.STACK_INSPECT_ENV;
  }
  return process.env[name];
}
