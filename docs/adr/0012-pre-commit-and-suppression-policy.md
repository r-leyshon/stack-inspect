# 12. Pre-commit linting and inline-only suppression

- **Status:** Proposed
- **Date:** 2026-09-27

## Context

The codebase spans Python, TypeScript, GitHub Actions workflows, Dockerfiles and Markdown. We want fast, automatic feedback, adherence to Python's PEP standards, and consistent style. Much of the code will be written with coding agents, which tend to silence a failing lint rule, often with a blanket or configuration-level ignore, rather than fix the code.

## Decision

- **pre-commit** runs every linter and formatter, using the fastest available tool for each job: Ruff, Biome, Pyright, `tsc`, zizmor, actionlint, gitleaks, hadolint, typos, rumdl, taplo and `pre-commit-hooks`. Fast hooks run on commit, and slower type checks run on push. CI runs everything.
- **Ruff selects `ALL` rules** and uses the Google docstring convention. The configuration-level ignore list is minimal, and each entry carries a comment.
- **Suppressions are inline only**. Each names a specific rule and gives a reason on the same line. The tools are configured to reject blanket and unused suppressions (Ruff `PGH004`/`RUF100`; Pyright `enableTypeIgnoreComments = false` and `reportUnnecessaryTypeIgnoreComment`; Biome's required explanations).
- **Configuration-level ignores** are limited to formatter conflicts, mutually exclusive rule pairs and path-scoped conventions, each with a comment.
- The policy is written into [`AGENTS.md`](../../AGENTS.md) so coding agents always have it in context.

Details, including per-tool syntax, are in [code quality](../code-quality.md).

## Consequences

- Selecting `ALL` means Ruff upgrades can introduce new rules. Handle them by fixing code or with a justified inline suppression, never by pinning Ruff indefinitely.
- Strict typing takes more effort at the boundaries with untyped frameworks and React internals. Those boundaries are where justified inline suppressions are expected.
- Every suppression is visible and greppable, and appears in review.
