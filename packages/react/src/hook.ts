/**
 * DevTools hook that records mounts, unmounts, renders and effect runs.
 * Install before React when possible; also patches a hook that already exists.
 */
import { valuesEnabled } from "@stack-inspect/core";

const recordValues = valuesEnabled();

/** Inline script body for optional early HTML injection. */
export const devtoolsHookSource = buildHookSource(recordValues);

/** Install or patch the DevTools hook in this realm. Safe to call more than once. */
export function installDevtoolsHook(): void {
  if (typeof window === "undefined") {
    return;
  }
  if (recordValues) {
    (
      window as Window & { __stackInspectRecordValues?: boolean }
    ).__stackInspectRecordValues = true;
  }
  // Trusted package source; Function avoids leaking locals into the hook scope.
  new Function(devtoolsHookSource)();
}

function buildHookSource(values: boolean): string {
  return `
(function () {
  if (globalThis.__stackInspectHookAttached) return;
  globalThis.__stackInspectHookAttached = true;
  var recordValues = ${values ? "true" : "false"} || globalThis.__stackInspectRecordValues === true;
  if (recordValues) globalThis.__stackInspectRecordValues = true;
  function stateChanged(fiber) {
    var previous = fiber.alternate;
    if (!previous) return false;
    var left = fiber.memoizedState;
    var right = previous.memoizedState;
    while (left && right) {
      if (!Object.is(left.memoizedState, right.memoizedState)) return true;
      left = left.next;
      right = right.next;
    }
    return false;
  }
  function propsChanged(fiber) {
    var previous = fiber.alternate;
    if (!previous) return true;
    var nextProps = fiber.memoizedProps || {};
    var prevProps = previous.memoizedProps || {};
    var key;
    for (key in nextProps) {
      if (key !== "children" && !Object.is(nextProps[key], prevProps[key])) return true;
    }
    for (key in prevProps) {
      if (key !== "children" && !Object.is(nextProps[key], prevProps[key])) return true;
    }
    return false;
  }
  function hasEffects(fiber) {
    var hook = fiber.memoizedState;
    while (hook) {
      var effect = hook.memoizedState;
      if (effect && typeof effect.create === "function") return true;
      hook = hook.next;
    }
    return false;
  }
  function effectRestarted(fiber) {
    var previous = fiber.alternate;
    if (!previous) return false;
    var hook = fiber.memoizedState;
    var prev = previous.memoizedState;
    while (hook && prev) {
      var effect = hook.memoizedState;
      var prevEffect = prev.memoizedState;
      if (effect && prevEffect && effect.deps && prevEffect.deps && typeof effect.create === "function") {
        if (effect.deps.length !== prevEffect.deps.length) return true;
        for (var index = 0; index < effect.deps.length; index += 1) {
          if (!Object.is(effect.deps[index], prevEffect.deps[index])) return true;
        }
      }
      hook = hook.next;
      prev = prev.next;
    }
    return false;
  }
  function clipValue(value, depth) {
    if (depth > 3) return "";
    if (value == null || typeof value === "number" || typeof value === "boolean") return value;
    if (typeof value === "string") return value.length > 80 ? value.slice(0, 79) + "…" : value;
    if (Array.isArray(value)) return value.slice(0, 8).map(function (item) { return clipValue(item, depth + 1); });
    if (typeof value === "object") {
      var out = {};
      var count = 0;
      var key;
      for (key in value) {
        if (count >= 8) break;
        var lower = String(key).toLowerCase();
        if (lower === "password" || lower === "passwd" || lower === "secret" || lower === "token" || lower === "cookie" || lower === "cookies" || lower === "authorization" || lower === "set-cookie") continue;
        out[key] = clipValue(value[key], depth + 1);
        count += 1;
      }
      return out;
    }
    return "";
  }
  function changedState(fiber) {
    if (!recordValues) return "";
    var previous = fiber.alternate;
    if (!previous) return "";
    var left = fiber.memoizedState;
    var right = previous.memoizedState;
    var changed = [];
    while (left && right) {
      var value = left.memoizedState;
      if (!Object.is(value, right.memoizedState) && !(value && typeof value === "object" && value.deps)) {
        changed.push(clipValue(value, 0));
      }
      left = left.next;
      right = right.next;
    }
    if (!changed.length) return "";
    try { return JSON.stringify(changed).slice(0, 200); } catch (error) { return ""; }
  }
  function fiberName(fiber) {
    var type = fiber && fiber.type;
    return type && (type.displayName || type.name) || "";
  }
  function walk(fiber, found, ancestorState) {
    if (!fiber) return;
    var type = fiber.type;
    var name = type && (type.displayName || type.name);
    var nextAncestor = ancestorState;
    if (typeof type === "function" && name) {
      var mounted = !fiber.alternate;
      if (mounted || fiber.alternate) {
        var props = mounted ? false : propsChanged(fiber);
        var state = mounted ? false : stateChanged(fiber);
        var restarted = !mounted && effectRestarted(fiber);
        found.push({
          name: name,
          mounted: mounted,
          unchanged: !mounted && !props && !state,
          stateChanged: state,
          effectRestarted: restarted,
          effectRan: mounted ? hasEffects(fiber) : restarted,
          causeName: state ? name : ancestorState || "",
          state: state ? changedState(fiber) : "",
        });
        if (state) nextAncestor = name;
      }
    }
    walk(fiber.child, found, nextAncestor);
    walk(fiber.sibling, found, ancestorState);
  }
  function flushNow() {
    var flush = globalThis.__siFlushCommits;
    if (typeof flush === "function") flush();
  }
  function onCommit(_id, root) {
    try {
      var found = [];
      var fiber = root && (root.current || root);
      walk(fiber, found, "");
      globalThis.__siCommits.push(found);
      // Flush before layout/passive effects so effect-driven fetch sees the cause.
      flushNow();
    } catch (error) {
      console.error("stack-inspect react hook", error);
    }
  }
  function onUnmount(_id, fiber) {
    try {
      var name = fiberName(fiber);
      if (name && typeof fiber.type === "function") {
        globalThis.__siUnmounts.push({ name: name });
        flushNow();
      }
    } catch (error) {
      console.error("stack-inspect react unmount", error);
    }
  }
  if (!globalThis.__siCommits) globalThis.__siCommits = [];
  if (!globalThis.__siUnmounts) globalThis.__siUnmounts = [];
  var existing = globalThis.__REACT_DEVTOOLS_GLOBAL_HOOK__;
  if (existing) {
    var prevCommit = existing.onCommitFiberRoot;
    var prevUnmount = existing.onCommitFiberUnmount;
    existing.supportsFiber = true;
    if (!existing.renderers) existing.renderers = new Map();
    if (typeof existing.inject !== "function") {
      existing.inject = function (renderer) {
        var id = this.renderers.size + 1;
        this.renderers.set(id, renderer);
        return id;
      };
    }
    existing.onCommitFiberRoot = function (id, root) {
      onCommit(id, root);
      if (typeof prevCommit === "function") prevCommit.apply(this, arguments);
    };
    existing.onCommitFiberUnmount = function (id, fiber) {
      onUnmount(id, fiber);
      if (typeof prevUnmount === "function") prevUnmount.apply(this, arguments);
    };
    return;
  }
  globalThis.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    supportsFiber: true,
    renderers: new Map(),
    inject: function (renderer) {
      var id = this.renderers.size + 1;
      this.renderers.set(id, renderer);
      return id;
    },
    onScheduleFiberRoot: function () {},
    onCommitFiberRoot: onCommit,
    onCommitFiberUnmount: onUnmount,
  };
})();
`;
}
