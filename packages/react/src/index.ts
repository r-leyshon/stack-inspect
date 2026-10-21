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
  valuesEnabled,
} from "@stack-inspect/core";
import type React from "react";
import { installDevtoolsHook } from "./hook";

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

export { devtoolsHookSource, installDevtoolsHook } from "./hook";

/** Patch React. No effect unless stack-inspect is enabled. */
export function install(react: typeof React): void {
  void react;
  if (installed || !enabled() || typeof window === "undefined") {
    return;
  }
  installed = true;
  installDevtoolsHook();
  const page = window as Window & {
    __REACT_DEVTOOLS_GLOBAL_HOOK__?: { onCommitFiberRoot?: unknown };
    __siCommits?: unknown[];
    __siUnmounts?: unknown[];
    __siFlushCommits?: () => void;
  };
  if (!page.__siCommits) {
    page.__siCommits = [];
  }
  if (!page.__siUnmounts) {
    page.__siUnmounts = [];
  }
  // Hook calls this from onCommitFiberRoot before React runs effects.
  page.__siFlushCommits = flushCommits;
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
export function recordRender(
  name: string,
  unchanged: boolean,
  causeIds: string[] = [],
): void {
  emit(
    reactEvent(
      name,
      "render",
      `browser:render:${name}`,
      {
        unchanged,
        changedProps: unchanged ? [] : ["unknown"],
      },
      undefined,
      causeIds,
    ),
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
  name: string;
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

function hookReceivesCommits(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const hook = (
    window as Window & {
      __REACT_DEVTOOLS_GLOBAL_HOOK__?: { renderers?: { size?: number } };
    }
  ).__REACT_DEVTOOLS_GLOBAL_HOOK__;
  return (hook?.renderers?.size ?? 0) > 0;
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
  const commitHookLive = hookReceivesCommits();
  const present = new Set(found.map((item) => item.key));
  for (const [key, previous] of seenFibers) {
    if (present.has(key)) {
      continue;
    }
    seenFibers.delete(key);
    if (commitHookLive) {
      continue;
    }
    clearActiveEffectCause(previous.name);
    emit(
      reactEvent(previous.name, "unmount", `browser:unmount:${previous.name}`, {
        component: previous.name,
      }),
    );
  }
  const samples: SampleCause[] = [];
  for (const item of found) {
    const previous = seenFibers.get(item.key);
    seenFibers.set(item.key, {
      propsRef: item.propsRef,
      props: item.props,
      state: item.state,
      deps: item.deps,
      name: item.name,
    });
    if (!previous) {
      if (commitHookLive) {
        continue;
      }
      samples.push({
        key: item.key,
        name: item.name,
        stateChanged: false,
        depsChanged: item.deps !== "",
        rerendered: false,
        mounted: true,
        unchanged: true,
        state: "",
      });
      continue;
    }
    const propsChanged =
      JSON.stringify(item.props) !== JSON.stringify(previous.props);
    const stateChanged = item.state !== previous.state;
    const depsChanged = item.deps !== previous.deps;
    const rerendered = item.propsRef !== previous.propsRef || stateChanged;
    samples.push({
      key: item.key,
      name: item.name,
      stateChanged,
      depsChanged,
      rerendered,
      mounted: false,
      unchanged: !propsChanged && !stateChanged,
      state: stateChanged ? changedHookValues(previous.state, item.state) : "",
    });
  }
  const stateIds = new Map<string, string>();
  for (const sample of samples) {
    if (sample.stateChanged) {
      stateIds.set(sample.key, newEventId());
    }
  }
  for (const sample of samples) {
    const causeIds = causeIdsFor(sample.key, sample.stateChanged, stateIds);
    if (sample.mounted) {
      emit(
        reactEvent(sample.name, "mount", `browser:mount:${sample.name}`, {
          component: sample.name,
        }),
      );
      if (sample.depsChanged) {
        const effectId = newEventId();
        const nodeKey = `browser:effect:${sample.name}`;
        emit(
          reactEvent(
            sample.name,
            "effect",
            nodeKey,
            { component: sample.name, restarted: false },
            effectId,
            causeIds,
          ),
        );
        setActiveEffectCause(sample.name, effectId, nodeKey);
      }
      continue;
    }
    if (sample.stateChanged) {
      emit(
        reactEvent(
          sample.name,
          "state-update",
          `browser:state:${sample.name}`,
          stateAttributes(sample.state),
          stateIds.get(sample.key),
        ),
      );
    }
    if (sample.rerendered) {
      recordRender(sample.name, sample.unchanged, causeIds);
    }
    if (sample.depsChanged) {
      const effectId = newEventId();
      const nodeKey = `browser:effect:${sample.name}`;
      emit(
        reactEvent(
          sample.name,
          "effect",
          nodeKey,
          { component: sample.name, restarted: true },
          effectId,
          causeIds,
        ),
      );
      setActiveEffectCause(sample.name, effectId, nodeKey);
    }
  }
}

type SampleCause = {
  key: string;
  name: string;
  stateChanged: boolean;
  depsChanged: boolean;
  rerendered: boolean;
  mounted: boolean;
  unchanged: boolean;
  state: string;
};

function causeIdsFor(
  key: string,
  ownState: boolean,
  stateIds: Map<string, string>,
): string[] {
  if (ownState) {
    const own = stateIds.get(key);
    return own ? [own] : [];
  }
  let path = key;
  while (path.includes("/")) {
    path = path.slice(0, path.lastIndexOf("/"));
    const ancestor = stateIds.get(path);
    if (ancestor) {
      return [ancestor];
    }
  }
  return [];
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
  // Minified Next/React internals are one or two letters, sometimes with a digit.
  if (name.length <= 2 || /^[a-z]{1,2}\d*$/.test(name)) {
    return true;
  }
  return (
    name.startsWith("__next") ||
    name.startsWith("AppRouter") ||
    name.startsWith("Inner") ||
    name.startsWith("Outer") ||
    name.startsWith("ClientPage") ||
    name.startsWith("DevRoot") ||
    name.startsWith("HTTPAccess") ||
    name.startsWith("Redirect") ||
    name.startsWith("Replay") ||
    name.startsWith("ScrollAnd") ||
    name.startsWith("Segment") ||
    name.startsWith("Metadata") ||
    name.includes("Boundary") ||
    name.includes("Router") ||
    [
      "HotReload",
      "Script",
      "Head",
      "Root",
      "ServerRoot",
      "RuntimeStyles",
      "HistoryUpdater",
      "LoadingBoundary",
      "RenderFromTemplateContext",
      "QueryClientProvider",
      "AsyncMetadataOutlet",
      "Page",
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

type CommitRender = {
  name: string;
  mounted?: boolean;
  unchanged: boolean;
  stateChanged: boolean;
  effectRestarted: boolean;
  effectRan?: boolean;
  causeName?: string;
  state?: string;
};

const ACTIVE_CAUSE_MS = 250;

type ActiveCause = {
  componentName: string;
  effectEventId: string;
  nodeKey: string;
  until: number;
};

function setActiveEffectCause(
  componentName: string,
  effectEventId: string,
  nodeKey: string,
): void {
  if (typeof window === "undefined") {
    return;
  }
  const page = window as Window & { __stackInspectActiveCause?: ActiveCause };
  page.__stackInspectActiveCause = {
    componentName,
    effectEventId,
    nodeKey,
    until: Date.now() + ACTIVE_CAUSE_MS,
  };
}

function clearActiveEffectCause(componentName?: string): void {
  if (typeof window === "undefined") {
    return;
  }
  const page = window as Window & { __stackInspectActiveCause?: ActiveCause };
  if (!page.__stackInspectActiveCause) {
    return;
  }
  if (
    componentName &&
    page.__stackInspectActiveCause.componentName !== componentName
  ) {
    return;
  }
  delete page.__stackInspectActiveCause;
}

function flushCommits(): void {
  if (typeof window === "undefined") {
    return;
  }
  const page = window as Window & {
    __siCommits?: CommitRender[][];
    __siUnmounts?: { name: string }[];
  };
  const unmounts = page.__siUnmounts;
  if (unmounts?.length) {
    const pendingUnmounts = unmounts.splice(0, unmounts.length);
    for (const item of pendingUnmounts) {
      if (isFrameworkComponent(item.name)) {
        continue;
      }
      clearActiveEffectCause(item.name);
      emit(
        reactEvent(item.name, "unmount", `browser:unmount:${item.name}`, {
          component: item.name,
        }),
      );
    }
  }
  const commits = page.__siCommits;
  if (!commits?.length) {
    return;
  }
  const pending = commits.splice(0, commits.length);
  for (const commit of pending) {
    const useful = commit.filter(
      (render) => render.name && !isFrameworkComponent(render.name),
    );
    const stateIds = new Map<string, string>();
    const stateValues = new Map<string, string>();
    for (const render of useful) {
      if (render.stateChanged && !stateIds.has(render.name)) {
        stateIds.set(render.name, newEventId());
        if (render.state) {
          stateValues.set(render.name, render.state);
        }
      }
    }
    for (const [name, id] of stateIds) {
      emit(
        reactEvent(
          name,
          "state-update",
          `browser:state:${name}`,
          stateAttributes(stateValues.get(name)),
          id,
        ),
      );
    }
    for (const render of useful) {
      const causeId = render.stateChanged
        ? stateIds.get(render.name)
        : render.causeName
          ? stateIds.get(render.causeName)
          : undefined;
      const causeIds = causeId ? [causeId] : [];
      if (render.mounted) {
        emit(
          reactEvent(render.name, "mount", `browser:mount:${render.name}`, {
            component: render.name,
          }),
        );
      } else {
        recordRender(render.name, render.unchanged, causeIds);
      }
      if (render.effectRan || render.effectRestarted) {
        const effectId = newEventId();
        const nodeKey = `browser:effect:${render.name}`;
        emit(
          reactEvent(
            render.name,
            "effect",
            nodeKey,
            {
              component: render.name,
              restarted: Boolean(render.effectRestarted),
            },
            effectId,
            causeIds,
          ),
        );
        setActiveEffectCause(render.name, effectId, nodeKey);
      }
    }
  }
}

function recordStateValues(): boolean {
  if (typeof window !== "undefined") {
    const page = window as Window & { __stackInspectRecordValues?: boolean };
    if (page.__stackInspectRecordValues) {
      return true;
    }
  }
  return valuesEnabled();
}

function stateAttributes(
  raw: string | undefined,
): Record<string, unknown> | undefined {
  if (!recordStateValues() || !raw) {
    return undefined;
  }
  try {
    return { state: JSON.parse(raw) as unknown };
  } catch {
    return { state: raw.slice(0, 200) };
  }
}

function changedHookValues(previous: string, current: string): string {
  if (!recordStateValues()) {
    return "";
  }
  try {
    const prior = JSON.parse(previous) as unknown;
    const next = JSON.parse(current) as unknown;
    if (Array.isArray(prior) && Array.isArray(next)) {
      const changed = next.filter(
        (value, index) =>
          JSON.stringify(value) !== JSON.stringify(prior[index]),
      );
      return JSON.stringify(changed.length > 0 ? changed : next).slice(0, 200);
    }
    return JSON.stringify(next).slice(0, 200);
  } catch {
    return current.slice(0, 200);
  }
}

function reactEvent(
  name: string,
  kind: string,
  nodeKey: string,
  attributes?: Record<string, unknown>,
  id?: string,
  causeIds?: string[],
): GraphEvent {
  const traceId = readActiveTrace() ?? newTraceId();
  return {
    id: id ?? newEventId(),
    traceId,
    ...(causeIds && causeIds.length > 0 ? { causeIds } : {}),
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
