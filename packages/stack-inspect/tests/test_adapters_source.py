"""Source checks for browser and React adapters (no Vitest in the workspace yet)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_react_hook_records_mount_effect_and_unmount() -> None:
    """The injected DevTools hook pushes mounts, effect runs and unmount names."""
    source = (ROOT / "packages/react/src/hook.ts").read_text(encoding="utf-8")
    assert "mounted: mounted" in source
    assert "effectRan:" in source
    assert "__siUnmounts" in source
    assert "onCommitFiberUnmount" in source
    assert "installDevtoolsHook" in source
    assert "__stackInspectHookAttached" in source


def test_react_adapter_emits_mount_and_sets_active_cause() -> None:
    """Flush turns hook samples into mount/effect events and sets the page-local cause."""
    source = (ROOT / "packages/react/src/index.ts").read_text(encoding="utf-8")
    assert "browser:mount:" in source
    assert "browser:unmount:" in source
    assert "__stackInspectActiveCause" in source
    assert "setActiveEffectCause" in source
    assert "installDevtoolsHook" in source
    assert "__siFlushCommits" in source
    assert "mounted: true" in source
    # Do not treat every App* name as a framework internal.
    assert 'startsWith("AppRouter")' in source
    assert 'startsWith("App")' not in source


def test_react_hook_flushes_before_effects() -> None:
    """Flush from the commit hook so the active cause precedes passive effects."""
    source = (ROOT / "packages/react/src/hook.ts").read_text(encoding="utf-8")
    assert "__siFlushCommits" in source
    assert "flushNow" in source


def test_reference_app_installs_hook_before_hydration() -> None:
    """The reference app uses instrumentation-client so inject() can run."""
    source = (ROOT / "reference/web/instrumentation-client.ts").read_text(encoding="utf-8")
    assert "installDevtoolsHook" in source


def test_browser_fetch_attaches_active_effect_cause_ids() -> None:
    """Fetch records observed causeIds from the active effect when one is set."""
    source = (ROOT / "packages/browser/src/index.ts").read_text(encoding="utf-8")
    assert "activeEffectCauseIds" in source
    assert "causeIds" in source
    assert "__stackInspectActiveCause" in source
    assert "clearActiveEffectCause" in source
