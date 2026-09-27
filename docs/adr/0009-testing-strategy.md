# 9. Testing strategy: unit, integration and Gherkin acceptance tests

- **Status:** Proposed
- **Date:** 2026-09-27

## Context

stack-inspect spans two languages, several processes and a browser. Its most important behaviours, such as explaining a CORS failure or linking a click to a SQL query, only exist when the whole stack runs together. Unit tests alone can't prove them.

We also want each roadmap milestone to have an unambiguous, executable definition of done.

## Decision

- **Unit tests:** pytest for Python, Vitest for TypeScript.
- **Integration tests:** adapters tested against real frameworks, and a real PostgreSQL in Docker.
- **Acceptance tests:** Gherkin feature files run by **playwright-bdd**, driving a real browser against the reference app with stack-inspect enabled.
  - A single BDD runner for the whole system, rather than one per language.
  - Chosen over pytest-bdd, Cucumber.js and behave because the acceptance tests are browser-driven, and Playwright gives direct Chrome DevTools Protocol access, which the CORS adapter needs.
- **Each milestone's "done when" criterion is written as a feature file before the milestone is built.**
- **Coverage is reported, not gated**, until the codebase has a stable shape.

Details are in [testing](../testing.md).

## Consequences

- Acceptance tests need the reference app (roadmap M0) and Docker Compose in CI, which makes them slower than the unit tests.
- Test tooling is made of development dependencies, which the audit gates cover ([ADR 0010](0010-security-gates-aligned-with-work.md)). Keep the set small.
- Without a coverage gate, reviewers must watch for untested code.
