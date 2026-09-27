# 10. Security gates aligned with the JusticeAIUnit estate

- **Status:** Proposed
- **Date:** 2026-09-27

## Context

stack-inspect is open source but will be used in JusticeAIUnit work repositories. Those repositories block CI on known vulnerabilities through reusable workflows in `JusticeAIUnit/github-actions`. Reviewed on 2026-09-27, those gates block at:

- **high** and above for dependency review, OWASP Dependency-Check (CVSS 7 or more) and npm audit;
- **any severity** for pip-audit, including development dependency groups;
- **low** and above for zizmor.

This is stricter than "critical only".

Those reusable workflows are internal to JusticeAIUnit. A public repository under another owner can't call them, can't pull the private OWASP scanner image, and can't use the organisation's zizmor App credentials.

## Decision

- stack-inspect stays a public repository and **reproduces the work gates with public tooling, at identical thresholds**. The full mapping is in [security posture](../security-posture.md).
- The same pinning and update policy applies: actions pinned to a SHA, images pinned by tag and digest, committed lockfiles, and Renovate with a 14-day wait that security fixes skip.
- The same workflow hygiene applies: `permissions: {}`, `persist-credentials: false`, no `continue-on-error`, no `secrets: inherit`.
- Gates are never loosened. Accepting a specific advisory needs an explicit, commented, per-advisory ignore, for example `--ignore-vuln GHSA-…` with a reason and a date to revisit it.
- The mapping is reviewed whenever the work gates change.

## Consequences

- Anything that passes here should also pass when installed into a work repository.
- We maintain our own copies of the gate workflows, and they can drift from the work originals. The security posture document records the date of the last review.
- OWASP Dependency-Check without the work estate's pre-built NVD cache is slow, and needs an NVD API key and a cached data directory.
