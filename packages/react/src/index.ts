/**
 * Records React state updates, renders and effect runs by wrapping the
 * dispatcher React installs while rendering. Also records TanStack Query
 * invalidations when a QueryClient is passed to `observeQueryClient`.
 */
import {
  emit,
  enabled,
  type GraphEvent,
  newEventId,
  newTraceId,
} from "@stack-inspect/core";
import type React from "react";

type QueryClientLike = {
  getQueryCache: () => {
    subscribe: (listener: (event: QueryCacheEvent) => void) => () => void;
  };
};

type QueryCacheEvent = {
  type?: string;
  action?: { type?: string };
  query?: { queryKey?: readonly unknown[] };
};

let installed = false;

export { devtoolsHookSource } from "./hook";

/** Patch React. No effect unless stack-inspect is enabled. */
export function install(react: typeof React): void {
  void react;
  if (installed || !enabled() || typeof window === "undefined") {
    return;
  }
  installed = true;
  const page = window as Window & {
    __REACT_DEVTOOLS_GLOBAL_HOOK__?: { onCommitFiberRoot?: unknown };
    __siCommits?: unknown[];
  };
  if (!page.__REACT_DEVTOOLS_GLOBAL_HOOK__) {
    page.__siCommits = [];
  }
  flushCommits();
  watchFibers();
  setInterval(flushCommits, 50);
  // Sample after React has flushed the click. A timer is late enough; the
  // bubble phase is not, because React's own listener may run later.
  document.addEventListener(
    "click",
    () => {
      setTimeout(sampleFibers, 40);
    },
    true,
  );
}

/**
 * Record cache invalidations from a TanStack Query client.
 * `componentName` is the component that reads the query.
 */
export function observeQueryClient(
  client: QueryClientLike,
  componentName: string,
): void {
  if (!enabled() || typeof window === "undefined") {
    return;
  }
  client.getQueryCache().subscribe((event) => {
    const key = JSON.stringify(event.query?.queryKey ?? []);
    if (event.type === "observerAdded" || event.type === "updated") {
      emit(
        reactEvent(componentName, "render", `browser:render:${componentName}`, {
          reads: `browser:query:${key}`,
          queryKey: key,
        }),
      );
    }
    if (event.action?.type === "invalidate") {
      emit(
        reactEvent("invalidate", "state-update", `browser:query:${key}`, {
          invalidates: `browser:render:${componentName}`,
          queryKey: key,
        }),
      );
    }
  });
}

/** Record a commit-time render. */
export function recordRender(name: string, unchanged: boolean): void {
  emit(
    reactEvent(name, "render", `browser:render:${name}`, {
      unchanged,
      changedProps: unchanged ? [] : ["unknown"],
    }),
  );
}

type Fiber = {
  type?: unknown;
  memoizedProps?: Record<string, unknown> | null;
  memoizedState?: HookState | null;
  child?: Fiber | null;
  sibling?: Fiber | null;
  return?: Fiber | null;
};

type HookState = {
  memoizedState?: unknown;
  next?: HookState | null;
};

type Seen = {
  propsRef: object | null;
  props: Record<string, unknown>;
  state: string;
  deps: string;
};

const seenFibers = new Map<string, Seen>();

function watchFibers(): void {
  const attempt = () => {
    if (!fiberRoot(document.body)) {
      requestAnimationFrame(attempt);
      return;
    }
    sampleFibers();
  };
  requestAnimationFrame(attempt);
}

function sampleFibers(): void {
  try {
    sampleFibersUnsafe();
  } catch (error) {
    emit(
      reactEvent("fiber-walk", "error", "browser:error:fiber", {
        message: error instanceof Error ? error.message : "fiber walk failed",
      }),
    );
  }
}

function sampleFibersUnsafe(): void {
  const root = fiberRoot(document.body);
  if (!root) {
    return;
  }
  const found: {
    key: string;
    name: string;
    propsRef: object | null;
    props: Record<string, unknown>;
    state: string;
    deps: string;
  }[] = [];
  walkFibers(root, "root", found, new Set());
  for (const item of found) {
    const previous = seenFibers.get(item.key);
    seenFibers.set(item.key, {
      propsRef: item.propsRef,
      props: item.props,
      state: item.state,
      deps: item.deps,
    });
    if (!previous) {
      continue;
    }
    const propsChanged =
      JSON.stringify(item.props) !== JSON.stringify(previous.props);
    const stateChanged = item.state !== previous.state;
    const depsChanged = item.deps !== previous.deps;
    const rerendered = item.propsRef !== previous.propsRef || stateChanged;
    if (rerendered) {
      recordRender(item.name, !propsChanged && !stateChanged);
    }
    if (stateChanged) {
      emit(reactEvent(item.name, "state-update", `browser:state:${item.name}`));
    }
    if (depsChanged) {
      emit(reactEvent(item.name, "effect", `browser:effect:${item.name}`));
    }
  }
}

function fiberRoot(node: Node): Fiber | null {
  const host = node as Node & Record<string, Fiber | undefined>;
  const key = Object.keys(host).find((name) =>
    name.startsWith("__reactFiber$"),
  );
  if (!key) {
    return null;
  }
  let fiber = host[key] ?? null;
  while (fiber?.return) {
    fiber = fiber.return;
  }
  const container = fiber as Fiber & { stateNode?: { current?: Fiber } };
  return container.stateNode?.current ?? fiber;
}

function walkFibers(
  fiber: Fiber | null,
  path: string,
  found: {
    key: string;
    name: string;
    propsRef: object | null;
    props: Record<string, unknown>;
    state: string;
    deps: string;
  }[],
  visiting: Set<Fiber>,
): void {
  let child = fiber?.child ?? null;
  let index = 0;
  while (child) {
    if (visiting.has(child)) {
      child = child.sibling ?? null;
      index += 1;
      continue;
    }
    visiting.add(child);
    const name = fiberName(child);
    const nextPath = name ? `${path}/${name}#${index}` : path;
    if (name && !isFrameworkComponent(name)) {
      found.push({
        key: nextPath,
        name,
        propsRef: child.memoizedProps ?? null,
        props: plainProps(child.memoizedProps),
        state: hookState(child),
        deps: hookDeps(child),
      });
    }
    walkFibers(child, nextPath, found, visiting);
    child = child.sibling ?? null;
    index += 1;
  }
}

function isFrameworkComponent(name: string): boolean {
  return (
    name.startsWith("__next") ||
    name.startsWith("AppRouter") ||
    name.startsWith("Inner") ||
    name.includes("Boundary") ||
    name.includes("Router") ||
    [
      "HotReload",
      "Script",
      "Head",
      "Root",
      "ServerRoot",
      "SegmentViewNode",
      "SegmentTrieNode",
      "RuntimeStyles",
      "HistoryUpdater",
      "RedirectBoundary",
    ].includes(name)
  );
}

function fiberName(fiber: Fiber): string {
  const type = fiber.type;
  if (typeof type === "function") {
    return type.displayName || type.name || "";
  }
  return "";
}

function plainProps(
  props: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  const plain: Record<string, unknown> = {};
  if (!props) {
    return plain;
  }
  for (const [key, value] of Object.entries(props)) {
    if (key === "children" || typeof value === "function") {
      continue;
    }
    plain[key] = typeof value === "object" ? null : value;
  }
  return plain;
}

function hookState(fiber: Fiber): string {
  const values: unknown[] = [];
  let hook = fiber.memoizedState;
  while (hook) {
    const value = hook.memoizedState;
    if (!(value && typeof value === "object" && "deps" in value)) {
      values.push(value);
    }
    hook = hook.next;
  }
  try {
    return JSON.stringify(values);
  } catch {
    return "";
  }
}

function hookDeps(fiber: Fiber): string {
  const deps: unknown[] = [];
  let hook = fiber.memoizedState;
  while (hook) {
    const value = hook.memoizedState;
    if (
      value &&
      typeof value === "object" &&
      "deps" in value &&
      Array.isArray(value.deps)
    ) {
      deps.push(value.deps);
    }
    hook = hook.next;
  }
  try {
    return JSON.stringify(deps);
  } catch {
    return "";
  }
}

function flushCommits(): void {
  if (typeof window === "undefined") {
    return;
  }
  const commits = (
    window as Window & {
      __siCommits?: {
        name: string;
        unchanged: boolean;
        stateChanged: boolean;
        effectRestarted: boolean;
      }[][];
    }
  ).__siCommits;
  if (!commits?.length) {
    return;
  }
  const pending = commits.splice(0, commits.length);
  for (const commit of pending) {
    for (const render of commit) {
      recordRender(render.name, render.unchanged);
      if (render.stateChanged) {
        emit(
          reactEvent(
            render.name,
            "state-update",
            `browser:state:${render.name}`,
          ),
        );
      }
      if (render.effectRestarted) {
        emit(
          reactEvent(render.name, "effect", `browser:effect:${render.name}`),
        );
      }
    }
  }
}

function reactEvent(
  name: string,
  kind: string,
  nodeKey: string,
  attributes?: Record<string, unknown>,
): GraphEvent {
  const traceId = readActiveTrace() ?? newTraceId();
  return {
    id: newEventId(),
    traceId,
    nodeKey,
    kind,
    layer: "browser",
    phase: "instant",
    name,
    ts: Date.now(),
    attributes,
  };
}

function readActiveTrace(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  const holder = (window as Window & { __stackInspectTraceId?: string })
    .__stackInspectTraceId;
  return holder ?? null;
}
