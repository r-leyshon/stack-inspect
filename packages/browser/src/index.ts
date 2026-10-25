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
/** Pathname + hash that bounds the current story. Query-string-only changes leave this alone. */
let storyKey = "";
/** True while a popstate (back/forward) is settling; those do not start a new story. */
let ignoreHashChange = false;

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
  installNavigationBoundary();
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
  const interactionId = newEventId();
  clearActiveEffectCause();
  if (pinned || !active || now - active.started > TRACE_WINDOW_MS) {
    pinned = false;
    active = {
      traceId: newTraceId(),
      spanId: newSpanId(),
      interactionId,
      started: now,
    };
    (
      window as Window & { __stackInspectTraceId?: string }
    ).__stackInspectTraceId = active.traceId;
  } else {
    active.interactionId = interactionId;
  }
  emit(
    browserEvent({
      id: interactionId,
      name,
      kind: "interaction",
      phase: "instant",
      nodeKey: `browser:interaction:${name}`,
    }),
  );
}

/**
 * Path or hash changes start a new story. Query-string-only changes and
 * back/forward (popstate) do not. The navigation event records ``fromTraceId``
 * so stories stay linked without inventing a causal edge.
 */
function installNavigationBoundary(): void {
  storyKey = storyUrlKey();
  wrapHistoryMethod("pushState");
  wrapHistoryMethod("replaceState");
  window.addEventListener("popstate", () => {
    ignoreHashChange = true;
    storyKey = storyUrlKey();
    queueMicrotask(() => {
      ignoreHashChange = false;
    });
  });
  window.addEventListener("hashchange", () => {
    if (ignoreHashChange) {
      return;
    }
    maybeSplitStory("hashchange");
  });
}

function wrapHistoryMethod(method: "pushState" | "replaceState"): void {
  const original = history[method].bind(history);
  history[method] = ((
    data: unknown,
    unused: string,
    url?: string | URL | null,
  ) => {
    const result = original(
      data,
      unused,
      url as string | URL | null | undefined,
    );
    maybeSplitStory(method);
    return result;
  }) as History["pushState"];
}

function storyUrlKey(): string {
  return `${window.location.pathname}${window.location.hash}`;
}

function maybeSplitStory(reason: string): void {
  const next = storyUrlKey();
  if (next === storyKey) {
    return;
  }
  const previousTraceId = active?.traceId;
  const previousKey = storyKey;
  storyKey = next;
  pinned = false;
  clearActiveEffectCause();
  const interactionId = newEventId();
  active = {
    traceId: newTraceId(),
    spanId: newSpanId(),
    interactionId,
    started: Date.now(),
  };
  (
    window as Window & { __stackInspectTraceId?: string }
  ).__stackInspectTraceId = active.traceId;
  emit(
    browserEvent({
      id: interactionId,
      name: `navigate ${next || "/"}`,
      kind: "interaction",
      phase: "instant",
      nodeKey: `browser:navigation:${next || "/"}`,
      attributes: {
        navigation: true,
        reason,
        href: window.location.href,
        fromPath: previousKey,
        ...(previousTraceId === undefined
          ? {}
          : { fromTraceId: previousTraceId }),
      },
    }),
  );
}

type ActiveCause = {
  componentName: string;
  effectEventId: string;
  nodeKey: string;
  until: number;
};

function clearActiveEffectCause(): void {
  delete (window as Window & { __stackInspectActiveCause?: ActiveCause })
    .__stackInspectActiveCause;
}

function activeEffectCauseIds(): string[] {
  const cause = (window as Window & { __stackInspectActiveCause?: ActiveCause })
    .__stackInspectActiveCause;
  if (!cause || Date.now() > cause.until) {
    return [];
  }
  return [cause.effectEventId];
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
    const spanId = newSpanId();
    const sentSpan = Boolean(trace) && !headers.has("traceparent");
    if (sentSpan && trace) {
      headers.set("traceparent", formatTraceparent(trace.traceId, spanId));
    }
    const id = newEventId();
    const path = pathOf(url);
    const method = (init?.method ?? "GET").toUpperCase();
    const causeIds = activeEffectCauseIds();
    emit(
      browserEvent({
        id,
        name: `${method} ${path}`,
        kind: "request",
        phase: "start",
        nodeKey: `browser:request:${path}`,
        parentId: trace?.interactionId,
        ...(causeIds.length > 0 ? { causeIds } : {}),
        attributes: {
          method,
          path,
          url,
          ...(sentSpan ? { spanId } : {}),
          ...(causeIds.length > 0
            ? {
                triggeredBy: (
                  window as Window & { __stackInspectActiveCause?: ActiveCause }
                ).__stackInspectActiveCause?.componentName,
              }
            : {}),
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
