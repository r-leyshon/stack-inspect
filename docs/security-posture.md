# Security posture

stack-inspect is open source, but it's intended for use in JusticeAIUnit work repositories. Those repositories block CI on known vulnerabilities, so stack-inspect's own CI applies **the same gates at the same thresholds**. Anything that passes here should also pass when it's installed into a work repository. The decision is recorded in [ADR 0010](adr/0010-security-gates-aligned-with-work.md).

The reference for "the same gates" is the `JusticeAIUnit/github-actions` repository, reviewed on 2026-09-27: `sca.yml`, `code-quality.yaml` with its `qc-python` and `qc-nodejs` actions, `snyk.yml`, and the Renovate preset `default.json`. Those workflows are internal to JusticeAIUnit, so a public repository can't call them. We reproduce their behaviour with public tooling instead.

## Gates

**Blocking** means the check fails CI. **Reporting** means findings go to the Security tab without failing CI, matching work.

The npm audit and pip-audit checks run on pull requests, on pushes to `main`, and every day at 07:00 UTC. GitHub runs the scheduled job from the default branch.

| Control | Work implementation | Work threshold | stack-inspect equivalent | Mode |
| :-- | :-- | :-- | :-- | :-- |
| Dependency review (pull requests only, new dependencies) | `actions/dependency-review-action` | **high** and above | Same action, `fail-on-severity: high` | Blocking |
| OWASP Dependency-Check | Private image with a pre-built NVD cache, `--failOnCVSS 7` | **CVSS 7 or more** | Official `owasp/dependency-check` image, `--failOnCVSS 7`, NVD API key as a secret, data directory cached between runs | Blocking |
| npm audit | `npm audit --audit-level=high` | **high** and above | Same | Blocking |
| pip-audit | `uv export --frozen [--all-groups]` piped to an isolated `uvx pip-audit` | **Any severity** (pip-audit has no threshold) | Same, always with `--all-groups` because we always run tests | Blocking |
| GitHub Actions security | zizmor, `min-severity: low`, plus online supply-chain audits | **low** and above | zizmor, `min-severity: low`. Online audits run with `GITHUB_TOKEN`, because every action we reference is public. | Blocking |
| Secret scanning | MoJ `devsecops-hooks` image (blocks on findings), plus TruffleHog (fails only on scan errors, findings uploaded as an artifact) | Findings | Same images, configured the same way and pinned by tag and digest, plus GitHub secret scanning and push protection (free on public repositories), plus gitleaks in pre-commit | Blocking |
| Supply-chain install guard | AikidoSec `safe-chain`, 72-hour minimum package age for installs in CI | Malware, or package too new | Same, checksum-verified | Blocking |
| Static analysis (SAST) | CodeQL with `security-extended` queries | n/a | Same, for `python`, `javascript-typescript` and `actions` | Reporting |
| OpenSSF Scorecard | `sca-openssf` | n/a | `ossf/scorecard-action`, results published | Reporting |
| SBOM | `sca-sbom` | n/a | CycloneDX SBOM generated at release and attached to it | Reporting |
| Snyk | Daily scheduled scan, reports to code scanning | n/a | Optional: Snyk is free for open source. Not needed for parity because it doesn't block at work. | Reporting |

### Thresholds are stricter than "criticals only"

The work gates block on **high** severity and above, not just critical. `pip-audit` blocks on **every** severity, and at work it audits development dependency groups too, whenever tests are enabled. We match that exactly, and never loosen it.

### Where OWASP Dependency-Check doesn't reach

OWASP Dependency-Check mainly covers the npm side. Its Python analysers are experimental and don't read `uv.lock`, so **pip-audit is the effective Python gate**, as it is at work.

## Pinning and update policy

The same pinning policy as the work estate:

- **GitHub Actions** are pinned to a full commit SHA, with the version in a trailing comment.
- **Container images** are pinned by tag **and** digest (`image:1.2.3@sha256:…`), using the multi-arch index digest.
- **Lockfiles** (`uv.lock`, `package-lock.json`) are committed, and CI installs from them with `uv sync --frozen` and `npm ci`.
- **npm development dependencies** are pinned to exact versions.
- **Renovate** runs through the free Mend Renovate GitHub App. We can't extend the internal `github>JusticeAIUnit/github-actions` preset, so the relevant settings are copied into our own `renovate.json`:
  - A 14-day `minimumReleaseAge`, with `minimumReleaseAgeBehaviour: timestamp-required`.
  - Security updates skip the wait. This needs Dependabot alerts enabled on the repository.
  - `helpers:pinGitHubActionDigests`, `:pinDevDependencies`, `:enablePreCommit` and `abandonments:recommended`.
  - Grouped updates per ecosystem, and weekly lockfile maintenance.

## Workflow hygiene

The same rules as work, and zizmor enforces most of them:

- Top-level `permissions: {}`, with explicit least-privilege permissions per job.
- `persist-credentials: false` on every checkout.
- No `continue-on-error`. Use `if: ${{ !cancelled() }}` on steps that must run after a failure.
- No `secrets: inherit`. Pass only the secrets a job uses.
- Suppress a zizmor finding only inline with `# zizmor: ignore[<audit>]` plus a reason, never by turning an audit off. See [code quality](code-quality.md).

## Being safe to install into work repositories

stack-inspect's adapters are installed as development dependencies in work repositories. Work pipelines then scan **our entire published dependency tree** at the thresholds above, and a single advisory anywhere in it blocks their CI. This drives several rules, recorded in [ADR 0011](adr/0011-minimal-runtime-dependencies.md):

- **Adapters have as few runtime dependencies as possible.** The standard library first. Framework packages (React, Next.js, Starlette/FastAPI, database drivers) are peer or optional dependencies, never pinned by us.
- **The collector and UI are distributed as a standalone tool**, run with `uvx`/`npx` or a container. Their heavier dependencies never enter a work lockfile.
- **No install scripts**: no `postinstall` or similar lifecycle scripts in any npm package.
- **Publishing with provenance**: two attested assets on a GitHub Release, with an SBOM on the same release ([ADR 0018](adr/0018-github-release-assets.md)). PyPI and npm stay optional.
- **Our own vulnerabilities are published as GitHub security advisories.** A consumer's Renovate only skips the 14-day wait when there's an advisory to match, so without one our fix would wait two weeks to reach work repositories.
- **Release timing:** routine releases take at least 14 days to reach work repositories because of the Renovate wait, plus 72 hours for the CI install guard. Plan fixes accordingly.

## Repository settings

Settings the security gates depend on:

- Dependabot alerts: enabled. Renovate's security fast-track needs them.
- Secret scanning and push protection: enabled.
- Private vulnerability reporting: enabled.
- Branch protection on `main` requiring every blocking check in the table above.
