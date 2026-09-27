# Code quality

Linting, formatting and type checking run through [pre-commit](https://pre-commit.com). Where a fast option exists (usually written in Rust or Go), we use it. CI runs the same hooks, so a clean local commit means a clean CI lint job. The decision is recorded in [ADR 0012](adr/0012-pre-commit-and-suppression-policy.md).

## Tools

| Area | Tool | Notes |
| :-- | :-- | :-- |
| Python lint | Ruff | `select = ["ALL"]`, with a short, commented ignore list (see below) |
| Python format | Ruff formatter | Black-compatible |
| Python types | Pyright, strict mode | Matches the work estate. Runs at the pre-push stage because it's slower. `reportMissingTypeStubs` and the `reportUnknown*` family are off: asyncpg and decoded JSON have no stubs, and those reports would otherwise flag every call into them. |
| Python packaging | `validate-pyproject`, `uv lock --check` | PEP 621 metadata is valid, and the lockfile matches `pyproject.toml` |
| TypeScript/JavaScript lint and format | Biome | Recommended rules plus stricter ones, and it formats JSON too. The work estate's templates also use Biome. |
| TypeScript types | `tsc --noEmit`, strict mode | Runs at the pre-push stage. The reference app stays on TypeScript below 7 until Next.js supports it (see below). |
| GitHub Actions | zizmor, actionlint | zizmor at `low` severity, matching the work gate |
| Secrets | gitleaks | Fast pre-commit check. CI also runs TruffleHog and MoJ `devsecops-hooks`. |
| Dockerfiles | hadolint | Matches the work estate |
| Shell | ShellCheck | Only if the repository contains shell scripts |
| Spelling | typos | Configured for British English (`en-gb`) |
| Markdown | rumdl | Rust implementation of the markdownlint rules |
| TOML | taplo | Formatting and validation |
| General | `pre-commit-hooks` | Trailing whitespace, end-of-file newline, YAML/TOML/JSON syntax, merge conflict markers, large files, private keys |

Fast hooks run on `pre-commit`. Slower hooks (Pyright, `tsc`) run on `pre-push`. CI runs every stage.

`prek`, a Rust reimplementation of pre-commit, reads the same `.pre-commit-config.yaml` and can be used locally for speed. CI uses pre-commit itself.

Hook versions are pinned to exact releases and kept up to date by Renovate (`:enablePreCommit`), with the same 14-day wait as every other dependency.

### TypeScript 7

The native TypeScript 7 compiler doesn't provide the compiler API that `next build` uses, so a Next.js app on TypeScript 7 passes `tsc` but fails its production build. The work estate hit exactly this. The reference app caps TypeScript below 7 until Next.js supports it. stack-inspect's own packages, which don't run `next build`, aren't bound by this.

## PEP compliance

| PEP | Enforced by |
| :-- | :-- |
| PEP 8 (style) | Ruff formatter, plus Ruff rule sets `E`, `W` and `N` (naming) |
| PEP 257 (docstrings) | Ruff `D` rules, with the Google convention |
| PEP 484 / 526 (type hints) | Pyright strict, plus Ruff `ANN` rules |
| PEP 561 (typed packages) | Each Python package ships a `py.typed` marker |
| PEP 621 (project metadata) | `validate-pyproject` |
| PEP 735 (dependency groups) | Development dependencies declared in `[dependency-groups]`, managed by uv |
| PEP 440 (versions) | Checked by the build backend at release |

## Suppression policy

This section applies to humans and agents alike. It's repeated in [`AGENTS.md`](../AGENTS.md) so coding agents always have it in context.

### Rules

1. **Fix the code first.** A suppression is for when the rule is wrong *for this specific line*, not for when fixing it is inconvenient.
2. **Suppress inline, name the rule, give a reason.** Every suppression names the specific rule code and gives a reason on the same line. Bare or blanket suppressions are forbidden, and the tools are configured to reject them.
3. **Never suppress in configuration to make a warning go away.** Configuration-level ignores are allowed only in three cases, and each needs a comment explaining why:
   - Rules that conflict with the formatter.
   - Pairs of mutually exclusive rules, where selecting `ALL` enables both and the tool doesn't resolve it automatically.
   - Conventions scoped to a path, such as `assert` in `tests/`.
4. **Never bypass the hooks.** No `git commit --no-verify`. No lowering of gate thresholds.
5. **List any new suppressions in the pull request description**, so a reviewer sees each one.

### Syntax per tool

| Tool | Correct form | Rejected by |
| :-- | :-- | :-- |
| Ruff | `# noqa: S603  # args are a fixed list, no user input` | `PGH004` (blanket `noqa`), `RUF100` (unused `noqa`) |
| Pyright | `# pyright: ignore[reportUnknownMemberType]  # untyped third-party API` | `enableTypeIgnoreComments = false` (bans bare `# type: ignore`), `reportUnnecessaryTypeIgnoreComment = "error"` |
| Biome | `// biome-ignore lint/suspicious/noExplicitAny: shape comes from React internals` | Biome requires the explanation, and reports unused suppressions |
| TypeScript | `// @ts-expect-error -- reason`, never `@ts-ignore` | Biome lint rules |
| zizmor | `# zizmor: ignore[<audit>]  # reason` | Unused ignores are reported |
| hadolint | `# hadolint ignore=DL3008` on the line before, with a reason comment | n/a |
| gitleaks | `# gitleaks:allow  # reason`, only for confirmed false positives such as test fixtures | n/a |

### Allowed configuration-level ignores

This is the starting set of ignores in the Ruff configuration. The Google docstring convention already disables the mutually exclusive `D` rules, so they aren't listed. Add a formatter-conflict ignore only if Ruff itself warns about the conflict. Anything else needs a pull request that argues for it.

```toml
[tool.ruff.lint]
select = ["ALL"]
ignore = [
  "COM812",  # conflicts with the Ruff formatter
  "CPY001",  # the MIT licence lives in LICENSE; repeating it in every file adds nothing
]

[tool.ruff.lint.per-file-ignores]
"**/tests/**" = [
  "S101",    # pytest uses bare assert
  "INP001",  # tests are modules, not a package; pytest loads them with importlib
]

[tool.ruff.lint.pydocstyle]
convention = "google"
```
