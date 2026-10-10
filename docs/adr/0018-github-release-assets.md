# 18. Distribute from GitHub Release assets

- **Status:** Proposed
- **Date:** 2026-10-09
- **Supersedes:** the publishing paragraph of [ADR 0011](0011-minimal-runtime-dependencies.md)

## Context

stack-inspect has to be installed in two languages. The FastAPI and database adapters run inside the API process. The browser, React and Next.js adapters run inside the page and the Next.js server. Python and Node resolve dependencies separately. Node can no longer load a module from a URL at runtime, so the collector cannot hand those adapters to Next.js.

The collector is a separate process. Its FastAPI and uvicorn dependencies must stay out of the application lockfile ([ADR 0011](0011-minimal-runtime-dependencies.md)). The repository keeps that split as eight projects: four Python packages, four npm workspaces, and a private workspace root. That layout is not an install surface. Publishing eight packages to PyPI and npm is more release machinery than this project wants for a first public version. Installing from git URLs would force a restructure, because npm cannot install one workspace out of a repository, and a moved tag would change what an application resolves.

## Decision

- **One tag, two files.** Pushing a version tag builds two assets and attaches them to the GitHub Release. The repository layout stays as it is. The eight projects are combined at build time.
- **Python wheel.** `stack_inspect-<version>-py3-none-any.whl` is the distribution named `stack-inspect`. It contains the adapter modules `stack_inspect_core`, `stack_inspect_fastapi` and `stack_inspect_db`, and the collector. Application imports stay on those module names. FastAPI and uvicorn are a `serve` extra, not base dependencies. `uv add` of the wheel does not install the extra. `uvx --from` the wheel with the extra runs the collector in its own environment.
- **npm tarball.** `stack-inspect-<version>.tgz` is one package named `stack-inspect`. It exports `stack-inspect/browser`, `stack-inspect/react`, `stack-inspect/next` and `stack-inspect/next/middleware`. It ships compiled JavaScript, so a Next.js app does not need `transpilePackages`. It has no install or prepare script ([ADR 0011](0011-minimal-runtime-dependencies.md)).
- **How an application installs a release.**

  ```bash
  uvx --from "stack-inspect[serve] @ https://github.com/<owner>/stack-inspect/releases/download/v<version>/stack_inspect-<version>-py3-none-any.whl" stack-inspect serve
  uv add --dev https://github.com/<owner>/stack-inspect/releases/download/v<version>/stack_inspect-<version>-py3-none-any.whl
  npm install --save-dev https://github.com/<owner>/stack-inspect/releases/download/v<version>/stack-inspect-<version>.tgz
  ```

- **The release is the pin.** GitHub immutable releases, so the tag and the assets cannot be replaced after publication. Each asset gets a signed attestation a consumer can check. An SBOM is attached to the same release.
- **Indexes stay optional.** PyPI and npm are not required. The same two files can be uploaded later.

## Consequences

- Two installs remain, one for Python and one for Node. That is the minimum while the adapters live in the application's lockfiles.
- This checkout is unchanged: the workspace packages and the reference app keep their current names. The release build is what publishes `stack-inspect` and the JavaScript subpaths.
- A consumer of the tarball imports `stack-inspect/browser`, `stack-inspect/react` and `stack-inspect/next`, not the `@stack-inspect/*` workspace names.
- [ADR 0011](0011-minimal-runtime-dependencies.md) still rules the lockfile split, the empty adapter dependency tree, and the ban on npm install scripts. Its publishing paragraph no longer applies.
