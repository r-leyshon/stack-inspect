# 11. Minimal dependencies in the adapter packages

- **Status:** Proposed
- **Date:** 2026-09-27

## Context

Work repositories will install stack-inspect's adapters from npm and PyPI as development dependencies. Their pipelines then audit our **entire published dependency tree**: pip-audit at any severity, and npm audit, OWASP Dependency-Check and dependency review at high and above. One advisory anywhere in that tree blocks their CI, and they then have to wait for us to release a fix.

Updates also reach work repositories slowly. Renovate waits 14 days before offering a routine update, and CI installs are held back until a package is at least 72 hours old.

## Decision

Split stack-inspect by where it gets installed:

| Part | Installed into the app's lockfile? | Dependency rule |
| :-- | :-- | :-- |
| Adapters (browser, React, Next.js, FastAPI, database) | **Yes** | Standard library first. Framework packages are peer or optional dependencies, with wide version ranges, never pinned by us. |
| Collector, graph projector and UI | **No.** Run with `uvx`/`npx` or a container. | Normal dependency hygiene, but kept out of consumers' lockfiles |

Additional rules:

- **Adding a runtime dependency to an adapter requires a new ADR** explaining why the standard library or a peer dependency can't do the job.
- Integrations with optional libraries, such as OpenTelemetry instrumentation ([ADR 0002](0002-local-collector.md)) or TanStack Query, are **optional extras**, never required dependencies.
- **No install scripts** in any npm package.
- Releases are published with **provenance**: PyPI Trusted Publishing with attestations, npm trusted publishing with provenance. An **SBOM** is attached to each release.
- Vulnerabilities in stack-inspect itself are published as **GitHub security advisories**, so a consumer's Renovate skips the 14-day wait for our fix.

## Consequences

- Adapters may re-implement small utilities rather than import them.
- The collector and UI can use richer dependencies without affecting consumers.
- The dependency surface a work repository takes on is small, easy to review, and unlikely to block its CI.
