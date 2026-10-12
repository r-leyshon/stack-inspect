"""The release assets keep the collector out of an application install."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "build_release.py"
_spec = importlib.util.spec_from_file_location("build_release", _SCRIPT)
assert _spec is not None
assert _spec.loader is not None
_release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_release)


def test_wheel_project_has_no_base_dependencies() -> None:
    """FastAPI, uvicorn and the MCP SDK are the serve extra, not the base install."""
    project = _release.python_project("1.0.0")
    assert "dependencies = []" in project
    assert 'serve = ["fastapi>=0.115", "mcp>=1.10", "uvicorn>=0.34"]' in project


def test_npm_manifest_has_no_install_script() -> None:
    """The tarball exports compiled subpaths and does not run a script on install."""
    manifest = _release.npm_manifest("1.0.0")
    assert manifest["name"] == "stack-inspect"
    assert "scripts" not in manifest
    exports = manifest["exports"]
    assert isinstance(exports, dict)
    assert set(exports) == {"./browser", "./react", "./next", "./next/middleware"}


def test_compiled_imports_stay_inside_the_tarball() -> None:
    """Workspace specifiers become relative files, with the extension Node expects."""
    source = 'import { emit } from "@stack-inspect/core";\nexport { hook } from "./hook";\n'
    rewritten = _release.rewrite_specifiers(source)
    assert "@stack-inspect/core" not in rewritten
    assert 'from "../core/index.js"' in rewritten
    assert 'from "./hook.js"' in rewritten
