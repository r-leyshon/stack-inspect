/**
 * Patches fetch, XHR, EventSource and WebSocket in the page.
 * Call `install()` once from a client component.
 */
import {
  collectorUrl,
  emit,
  enabled,
  extract,
  formatTraceparent,
  type GraphEvent,
  newEventId,
  newSpanId,
  newTraceId,
  parseTraceparent,
} from "@stack-inspect/core";
import { installStorage as patchStorage, type StorageRecord } from "./storage";

const TRACE_WINDOW_MS = 8000;

type ActiveTrace = {
  traceId: string;
  spanId: string;
  interactionId: string;
  started: number;
};

let active: ActiveTrace | null = null;
let pinned = false;
let installed = false;

/** Start patching browser APIs. No effect unless stack-inspect is enabled. */
export function install(): void {
  if (installed || !enabled() || typeof window === "undefined") {
    return;
  }
  installed = true;
  patchFetch();
  patchEventSource();
  patchWebSocket();
  observeVisibleResults();
  installStorage();
  document.addEventListener(
    "click",
    (event) => {
      const target = event.target;
      if (!(target instanceof Element)) {
        return;
      }
      const button = target.closest("button");
      const name =
        button?.textContent?.trim() || target.textContent?.trim() || "click";
      startInteraction(name);
    },
    true,
  );
}

/**
 * Record IndexedDB and Origin Private File System calls in this realm.
 * Call this from a worker. `install()` already calls it on the page.
 */
export function installStorage(): void {
  if (!enabled()) {
    return;
  }
  patchStorage(recordStorage);
}

/**
 * Keep ``traceparent`` as this realm's trace until the next click.
 * A worker calls this with the carrier it was given. The 8-second click
 * window does not apply to a trace continued this way.
 */
export function adoptTrace(traceparent: string): void {
  const parsed = parseTraceparent(traceparent);
  if (!parsed) {
    return;
  }
  active = {
    traceId: parsed.traceId,
    spanId: parsed.spanId,
    interactionId: "",
    started: Date.now(),
  };
  pinned = true;
}

/** Run ``fn`` with the trace stored in ``carrier``, then restore the previous one. */
export function runWithCarrier<T>(
  carrier: Record<string, string>,
  fn: () => T,
): T {
  const parsed = extract(carrier);
  const previous = active;
  const previousPinned = pinned;
  if (parsed) {
    adoptTrace(formatTraceparent(parsed.traceId, parsed.spanId));
  }
  try {
    return fn();
  } finally {
    active = previous;
    pinned = previousPinned;
  }
}

/** The trace started by the most recent interaction, if it is still current. */
export function activeTrace(): ActiveTrace | null {
  if (!active) {
    return null;
  }
  if (!pinned && Date.now() - active.started > TRACE_WINDOW_MS) {
    return null;
  }
  return active;
}

function startInteraction(name: string): void {
  const now = Date.now();
  if (pinned || !active || now - active.started > TRACE_WINDOW_MS) {
    pinned = false;
    active = {
      traceId: newTraceId(),
      spanId: newSpanId(),
      interactionId: newEventId(),
      started: now,
    };
    (
      window as Window & { __stackInspectTraceId?: string }
    ).__stackInspectTraceId = active.traceId;
  }
  emit(
    browserEvent({
      id: newEventId(),
      name,
      kind: "interaction",
      phase: "instant",
      nodeKey: `browser:interaction:${name}`,
    }),
  );
}

function patchFetch(): void {
  const original = window.fetch.bind(window);
  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = resolveUrl(input);
    if (url.startsWith(collectorUrl())) {
      return original(input, init);
    }
    const trace = activeTrace();
    const headers = new Headers(
      init?.headers ?? (input instanceof Request ? input.headers : undefined),
    );
    if (trace && !headers.has("traceparent")) {
      headers.set("traceparent", formatTraceparent(trace.traceId, newSpanId()));
    }
    const id = newEventId();
    const path = pathOf(url);
    emit(
      browserEvent({
        id,
        name: `GET ${path}`,
        kind: "request",
        phase: "start",
        nodeKey: `browser:request:${path}`,
        parentId: trace?.interactionId,
        attributes: {
          method: (init?.method ?? "GET").toUpperCase(),
          path,
          url,
        },
      }),
    );
    try {
      const response = await original(input, { ...init, headers });
      emit(
        browserEvent({
          id: newEventId(),
          name: `${(init?.method ?? "GET").toUpperCase()} ${path}`,
          kind: "request",
          phase: "end",
          nodeKey: `browser:request:${path}`,
          parentId: id,
          attributes: {
            method: (init?.method ?? "GET").toUpperCase(),
            path,
            status: response.status,
          },
        }),
      );
      return response;
    } catch (error) {
      emit(
        browserEvent({
          id: newEventId(),
          name: `failed ${path}`,
          kind: "error",
          phase: "instant",
          nodeKey: `browser:error:${path}`,
          parentId: id,
          attributes: {
            path,
            message: error instanceof Error ? error.message : "failed",
          },
        }),
      );
      throw error;
    }
  };
}

function patchEventSource(): void {
  const Original = window.EventSource;
  const Patched = class extends Original {
    constructor(url: string | URL, configuration?: EventSourceInit) {
      const traced = withTraceQuery(String(url));
      super(traced, configuration);
      const path = pathOf(String(url));
      const trace = activeTrace();
      const count =
        ((window as Window & { __siStreams?: number }).__siStreams ?? 0) + 1;
      (window as Window & { __siStreams?: number }).__siStreams = count;
      emit(
        browserEvent({
          id: newEventId(),
          name: path,
          kind: "stream",
          phase: "instant",
          nodeKey: `browser:stream:${path}`,
          parentId: trace?.interactionId,
          attributes: {
            event: count > 1 ? "reconnect" : "open",
            path,
            protocol: "sse",
          },
        }),
      );
      this.addEventListener("message", (message) => {
        emit(
          browserEvent({
            id: newEventId(),
            name: message.data,
            kind: "stream-message",
            phase: "instant",
            nodeKey: `browser:stream-message:${path}`,
            parentId: trace?.interactionId,
            attributes: {
              direction: "server",
              path,
              sequence: Number(message.lastEventId || 0),
            },
          }),
        );
      });
    }
  };
  window.EventSource = Patched;
}

function patchWebSocket(): void {
  const Original = window.WebSocket;
  const Patched = class extends Original {
    private sequence = 0;

    constructor(url: string | URL, protocols?: string | string[]) {
      super(withTraceQuery(String(url)), protocols);
      const path = pathOf(String(url));
      const trace = activeTrace();
      emit(
        browserEvent({
          id: newEventId(),
          name: path,
          kind: "stream",
          phase: "start",
          nodeKey: `browser:stream:${path}`,
          parentId: trace?.interactionId,
          attributes: { event: "open", path, protocol: "websocket" },
        }),
      );
      const originalSend = this.send.bind(this);
      this.send = (data: string | ArrayBufferLike | Blob | ArrayBufferView) => {
        this.sequence += 1;
        if (typeof data === "string" && trace) {
          const envelope = JSON.stringify({
            __stackInspect: {
              traceparent: formatTraceparent(trace.traceId, newSpanId()),
              seq: this.sequence,
            },
            payload: data,
          });
          originalSend(envelope);
          return;
        }
        originalSend(data);
      };
    }
  };
  window.WebSocket = Patched as typeof WebSocket;
}

function observeVisibleResults(): void {
  const observer = new MutationObserver(() => {
    if (!document.querySelector("[data-user-visible]")) {
      return;
    }
    emit(
      browserEvent({
        id: newEventId(),
        name: "result visible",
        kind: "render",
        phase: "instant",
        nodeKey: "browser:render:visible",
        attributes: { userVisible: true },
      }),
    );
    observer.disconnect();
  });
  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
}

function withTraceQuery(url: string): string {
  const trace = activeTrace();
  if (!trace) {
    return url;
  }
  const parsed = new URL(url, window.location.origin);
  parsed.searchParams.set(
    "stack_inspect_traceparent",
    formatTraceparent(trace.traceId, trace.spanId),
  );
  return parsed.toString();
}

function resolveUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") {
    return new URL(input, window.location.origin).toString();
  }
  if (input instanceof URL) {
    return input.toString();
  }
  return input.url;
}

function pathOf(url: string): string {
  try {
    return new URL(url, window.location.origin).pathname;
  } catch {
    return url;
  }
}

const recordStorage: StorageRecord = (detail) => {
  const trace = activeTrace();
  emit(
    browserEvent({
      id: newEventId(),
      name: detail.name,
      kind: "storage",
      phase: "instant",
      nodeKey: `browser:storage:${detail.backend}:${detail.name}`,
      parentId: trace?.interactionId || undefined,
      attributes: {
        backend: detail.backend,
        operation: detail.operation,
        ...(detail.bytes === undefined ? {} : { bytes: detail.bytes }),
        ...(detail.key === undefined ? {} : { key: detail.key }),
      },
    }),
  );
};

function browserEvent(
  partial: Omit<GraphEvent, "traceId" | "layer" | "ts"> & { traceId?: string },
): GraphEvent {
  const trace = activeTrace();
  return {
    traceId: partial.traceId ?? trace?.traceId ?? newTraceId(),
    layer: "browser",
    ts: Date.now(),
    ...partial,
  };
}
