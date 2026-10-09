/**
 * Source of the DevTools hook injected before React starts.
 * It records which function components rendered in each commit.
 */
import { valuesEnabled } from "@stack-inspect/core";

const recordValues = valuesEnabled();

export const devtoolsHookSource = `
(function () {
  if (window.__REACT_DEVTOOLS_GLOBAL_HOOK__) return;
  var recordValues = ${recordValues ? "true" : "false"};
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
  function walk(fiber, found, ancestorState) {
    if (!fiber) return;
    var type = fiber.type;
    var name = type && (type.displayName || type.name);
    var nextAncestor = ancestorState;
    if (typeof type === "function" && name && fiber.alternate) {
      var props = propsChanged(fiber);
      var state = stateChanged(fiber);
      found.push({
        name: name,
        unchanged: !props && !state,
        stateChanged: state,
        effectRestarted: effectRestarted(fiber),
        causeName: state ? name : ancestorState || "",
        state: state ? changedState(fiber) : "",
      });
      if (state) nextAncestor = name;
    }
    walk(fiber.child, found, nextAncestor);
    walk(fiber.sibling, found, ancestorState);
  }
  globalThis.__siCommits = [];
  globalThis.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    supportsFiber: true,
    renderers: new Map(),
    inject: function (renderer) {
      var id = this.renderers.size + 1;
      this.renderers.set(id, renderer);
      return id;
    },
    onScheduleFiberRoot: function () {},
    onCommitFiberRoot: function (_id, root) {
      try {
        var found = [];
        var fiber = root && (root.current || root);
        walk(fiber, found, "");
        globalThis.__siCommits.push(found);
      } catch (error) {
        console.error("stack-inspect react hook", error);
      }
    },
    onCommitFiberUnmount: function () {},
  };
})();
`;
