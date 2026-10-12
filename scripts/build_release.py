"""Build the two GitHub Release assets described in ADR 0018.

The wheel is the distribution ``stack-inspect``. It contains the adapter modules and the
collector. FastAPI, uvicorn and the MCP SDK are a ``serve`` extra, so installing the wheel
into an application does not pull the collector's server into that lockfile.

The npm tarball is one package named ``stack-inspect`` with compiled JavaScript subpaths.
It has no install script.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_PYTHON_PACKAGES = (
    "packages/stack-inspect-core/src/stack_inspect_core",
    "packages/stack-inspect-fastapi/src/stack_inspect_fastapi",
    "packages/stack-inspect-db/src/stack_inspect_db",
    "packages/stack-inspect/src/stack_inspect",
)
_VERSION_FILES = (
    "packages/stack-inspect/pyproject.toml",
    "packages/stack-inspect-core/pyproject.toml",
    "packages/stack-inspect-fastapi/pyproject.toml",
    "packages/stack-inspect-db/pyproject.toml",
    "packages/core/package.json",
    "packages/browser/package.json",
    "packages/react/package.json",
    "packages/next/package.json",
)
_JS_SOURCES = {
    "packages/core/src": "core",
    "packages/browser/src": "browser",
    "packages/react/src": "react",
    "packages/next/src": "next",
}
_CORE_IMPORT = re.compile(r"""(?P<quote>["'])@stack-inspect/core(?P=quote)""")
_RELATIVE_IMPORT = re.compile(r"""(?P<prefix>from\s+)(?P<quote>["'])(?P<path>\./[^"']+?)(?P=quote)""")


def release_version() -> str:
    """Return the shared package version, or fail when the packages disagree."""
    found = {_read_version(ROOT / relative) for relative in _VERSION_FILES}
    if len(found) != 1:
        message = f"release versions disagree: {sorted(found)}"
        raise SystemExit(message)
    return found.pop()


def python_project(version: str) -> str:
    """Return the wheel project. The base install has no third-party dependencies."""
    return f"""[project]
name = "stack-inspect"
version = "{version}"
description = "Development-only execution graph for Next.js, FastAPI and PostgreSQL"
readme = "README.md"
requires-python = ">=3.12"
license = "MIT"
license-files = ["LICENSE"]
dependencies = []

[project.optional-dependencies]
serve = ["fastapi>=0.115", "mcp>=1.10", "uvicorn>=0.34"]
asyncpg = ["asyncpg>=0.30"]
sqlalchemy = ["sqlalchemy>=2"]

[project.scripts]
stack-inspect = "stack_inspect.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = [
  "src/stack_inspect",
  "src/stack_inspect_core",
  "src/stack_inspect_fastapi",
  "src/stack_inspect_db",
]

[tool.hatch.build.targets.wheel.force-include]
"src/stack_inspect/ui.html" = "stack_inspect/ui.html"
"src/stack_inspect/scan_fetch.mjs" = "stack_inspect/scan_fetch.mjs"
"""


def npm_manifest(version: str) -> dict[str, object]:
    """Return the tarball manifest. Compiled subpaths, and no install script."""
    return {
        "name": "stack-inspect",
        "version": version,
        "description": "Development-only execution graph for Next.js, FastAPI and PostgreSQL",
        "license": "MIT",
        "type": "module",
        "exports": {
            "./browser": _export("./dist/browser/index"),
            "./react": _export("./dist/react/index"),
            "./next": _export("./dist/next/index"),
            "./next/middleware": _export("./dist/next/middleware"),
        },
        "files": ["dist", "README.md", "LICENSE"],
        "peerDependencies": {"react": ">=18"},
    }


def rewrite_specifiers(source: str) -> str:
    """Point workspace imports at the compiled files inside this tarball."""
    rewritten = _CORE_IMPORT.sub(r"\g<quote>../core/index.js\g<quote>", source)

    def _with_extension(match: re.Match[str]) -> str:
        path = match.group("path")
        if path.endswith(".js"):
            return match.group(0)
        return f"{match.group('prefix')}{match.group('quote')}{path}.js{match.group('quote')}"

    return _RELATIVE_IMPORT.sub(_with_extension, rewritten)


def build(out: Path) -> None:
    """Write the wheel, the npm tarball and a CycloneDX SBOM into ``out``."""
    version = release_version()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "work"
    if work.exists():
        shutil.rmtree(work)
    wheel = _build_wheel(work / "python", version, out)
    tarball = _build_npm(work / "npm", version, out)
    _sbom(out / f"stack-inspect-{version}.cdx.json", version, wheel.name, tarball.name)
    shutil.rmtree(work)


def _read_version(path: Path) -> str:
    """Return the version field from a pyproject or package.json file."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".toml":
        project = tomllib.loads(text)
        version = project["project"]["version"]
    else:
        version = json.loads(text)["version"]
    if not isinstance(version, str):
        message = f"{path} has no string version"
        raise SystemExit(message)
    return version


def _export(stem: str) -> dict[str, str]:
    """Return one package export for the compiled file and its declaration."""
    return {"types": f"{stem}.d.ts", "default": f"{stem}.js"}


def _build_wheel(project: Path, version: str, out: Path) -> Path:
    """Assemble the combined project and build the wheel."""
    project.mkdir(parents=True)
    (project / "pyproject.toml").write_text(python_project(version), encoding="utf-8")
    shutil.copyfile(ROOT / "LICENSE", project / "LICENSE")
    (project / "README.md").write_text(_readme(version), encoding="utf-8")
    source = project / "src"
    for relative in _PYTHON_PACKAGES:
        origin = ROOT / relative
        shutil.copytree(origin, source / origin.name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    subprocess.run(  # noqa: S603 # the command is a fixed list, not a shell
        ["uv", "build", "--wheel", "--out-dir", str(out)],  # noqa: S607 # uv is the installed toolchain
        cwd=project,
        check=True,
    )
    wheels = list(out.glob(f"stack_inspect-{version}-py3-none-any.whl"))
    if len(wheels) != 1:
        message = f"expected one wheel for {version}, found {wheels}"
        raise SystemExit(message)
    return wheels[0]


def _build_npm(project: Path, version: str, out: Path) -> Path:
    """Compile the adapters and pack the tarball."""
    source = project / "src"
    for origin, name in _JS_SOURCES.items():
        shutil.copytree(ROOT / origin, source / name, ignore=shutil.ignore_patterns("*.json"))
    (project / "tsconfig.json").write_text(_tsconfig(), encoding="utf-8")
    subprocess.run(
        ["npx", "tsc", "-p", "tsconfig.json"],  # noqa: S607 # npx and tsc come from this checkout
        cwd=project,
        check=True,
    )
    for compiled in (project / "dist").rglob("*"):
        if compiled.suffix in {".js", ".d.ts"}:
            compiled.write_text(rewrite_specifiers(compiled.read_text(encoding="utf-8")), encoding="utf-8")
    (project / "package.json").write_text(json.dumps(npm_manifest(version), indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(ROOT / "LICENSE", project / "LICENSE")
    (project / "README.md").write_text(_readme(version), encoding="utf-8")
    subprocess.run(  # noqa: S603 # the command is a fixed list, not a shell
        ["npm", "pack", "--pack-destination", str(out)],  # noqa: S607 # npm is the installed toolchain
        cwd=project,
        check=True,
    )
    tarballs = list(out.glob(f"stack-inspect-{version}.tgz"))
    if len(tarballs) != 1:
        message = f"expected one tarball for {version}, found {tarballs}"
        raise SystemExit(message)
    return tarballs[0]


def _tsconfig() -> str:
    """Return a compiler project that typechecks the copied sources."""
    return json.dumps(
        {
            "compilerOptions": {
                "target": "ES2022",
                "module": "ES2022",
                "moduleResolution": "bundler",
                "declaration": True,
                "outDir": "dist",
                "rootDir": "src",
                "strict": True,
                "noCheck": True,
                "lib": ["ES2022", "DOM"],
                "skipLibCheck": True,
                "baseUrl": ".",
                "paths": {"@stack-inspect/core": ["src/core/index.ts"]},
            },
            "include": ["src"],
        },
        indent=2,
    )


def _readme(version: str) -> str:
    """Return the install note packed into both assets."""
    return f"""# stack-inspect {version}

Development-only execution graph for Next.js, FastAPI and PostgreSQL.

Install the adapters from the GitHub Release assets. The collector runs from the
wheel's `serve` extra and stays out of the application lockfile.

Python imports are `stack_inspect_core`, `stack_inspect_fastapi` and `stack_inspect_db`.
JavaScript imports are `stack-inspect/browser`, `stack-inspect/react`,
`stack-inspect/next` and `stack-inspect/next/middleware`.
"""


def _sbom(path: Path, version: str, wheel: str, tarball: str) -> None:
    """Write a CycloneDX inventory of the two release assets."""
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {"component": {"type": "application", "name": "stack-inspect", "version": version}},
        "components": [
            {"type": "library", "name": "stack-inspect", "version": version, "purl": f"pkg:generic/{wheel}"},
            {"type": "library", "name": "stack-inspect", "version": version, "purl": f"pkg:generic/{tarball}"},
        ],
    }
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    """Build the assets into ``dist/release``."""
    build(ROOT / "dist" / "release")


if __name__ == "__main__":
    main()
