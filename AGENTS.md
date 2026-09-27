# AGENTS.md

Guidance for coding agents working in this repository. Humans follow the same rules.

## What this project is

stack-inspect is a **development-only** tool that watches a running Next.js + FastAPI + PostgreSQL app and builds a live execution graph of what each user interaction caused. It's inspired by Shiny's `reactlog`. The long-term goal is a full cross-stack invalidation graph.

Read before making changes:

| Document | What's in it |
| :-- | :-- |
| [`docs/vision.md`](docs/vision.md) | Scope, long-term goal, non-goals |
| [`docs/architecture.md`](docs/architecture.md) | Components, graph model, middleware/CORS, streams |
| [`docs/roadmap.md`](docs/roadmap.md) | Milestones and their "done when" criteria |
| [`docs/adr/`](docs/adr/) | Why each decision was made |
| [`docs/testing.md`](docs/testing.md) | Unit, integration and Gherkin acceptance tests |
| [`docs/security-posture.md`](docs/security-posture.md) | Security gates and dependency rules |
| [`docs/code-quality.md`](docs/code-quality.md) | Linters, PEP compliance, suppression syntax |

## Non-negotiables

1. **Development only.** Never weaken the production guards ([ADR 0006](docs/adr/0006-development-only-guarantee.md)). The collector binds to `127.0.0.1` only.
2. **Keep the graph model ready for invalidation edges** ([ADR 0004](docs/adr/0004-invalidation-ready-graph-model.md)). The event log is append-only, node keys are stable, and `causeIds`, `read` and `invalidated` stay in the schema.
3. **Redact by default.** Never record request bodies, cookies, tokens or SQL parameter values unless the user explicitly enables it.

## Dependencies

The adapters are installed into work repositories, whose CI blocks on **high** and above for npm and OWASP, and on **any** severity for pip-audit ([ADR 0011](docs/adr/0011-minimal-runtime-dependencies.md)).

- **Don't add a runtime dependency to an adapter package.** Use the standard library, or declare the framework as a peer or optional dependency. If you believe a new dependency is unavoidable, stop and propose an ADR instead.
- Development dependencies are audited too. Prefer tools already in use.
- Commit lockfile changes (`uv.lock`, `package-lock.json`) together with the manifest change that caused them.
- No npm lifecycle or install scripts.
- Never add `--ignore-vuln`, audit exclusions or lowered thresholds without a reason and a date to revisit it, and flag the change in your summary.

## Linting and suppressions

pre-commit runs every linter and formatter. Run it before declaring work done:

```bash
pre-commit run --all-files
pre-commit run --all-files --hook-stage pre-push   # type checks
```

**Fix the code first.** Suppress only when the rule is genuinely wrong for that specific line.

When you must suppress:

- **Inline only.** Name the specific rule and give a reason on the same line.
- **Never** use bare suppressions: `# noqa`, `# type: ignore`, `@ts-ignore`, or a `biome-ignore` without a rule.
- **Never** add rules to configuration-level ignore lists or `per-file-ignores` to silence a warning. Those lists are limited to formatter conflicts, mutually exclusive rules and path-scoped conventions, and each entry carries a comment.
- **Never** bypass hooks with `--no-verify`, or disable a hook.
- List every new suppression in your summary and the pull request description.

| Tool | Correct form |
| :-- | :-- |
| Ruff | `# noqa: S603  # args are a fixed list, no user input` |
| Pyright | `# pyright: ignore[reportUnknownMemberType]  # untyped third-party API` |
| Biome | `// biome-ignore lint/suspicious/noExplicitAny: shape comes from React internals` |
| TypeScript | `// @ts-expect-error -- reason` (never `@ts-ignore`) |
| zizmor | `# zizmor: ignore[<audit>]  # reason` |
| hadolint | `# hadolint ignore=DL3008` on the line before, with a reason comment |

## Testing

- Write or update tests with every behaviour change. Bug fixes start with a failing test.
- Unit tests: pytest (Python) and Vitest (TypeScript). No network, database or browser in unit tests.
- Acceptance tests: Gherkin feature files in `features/`, run by playwright-bdd against the reference app. A milestone's "done when" criterion is written as a feature file before the milestone is built.

## GitHub Actions workflows

- Top-level `permissions: {}`, with least-privilege permissions per job.
- Pin third-party actions to a full commit SHA with a version comment. Pin container images by tag **and** digest.
- `persist-credentials: false` on checkout. No `continue-on-error`. No `secrets: inherit`.
- zizmor must pass at `low` severity.

## Conventions

- **British English** in code, comments and documentation.
- **Conventional commits**: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`.
- Record significant decisions as a new ADR in `docs/adr/` ([ADR 0001](docs/adr/0001-record-architecture-decisions.md)). Don't rewrite accepted ADRs. Supersede them with a new one.
- Keep documentation true: when behaviour changes, update the relevant doc in the same change.
