# Testing

stack-inspect is tested at three levels. The decision is recorded in [ADR 0009](adr/0009-testing-strategy.md).

| Level | Tools | What it proves |
| :-- | :-- | :-- |
| Unit | pytest (Python), Vitest (TypeScript) | Individual functions and classes behave correctly in isolation |
| Integration | pytest, Vitest, a real PostgreSQL in Docker | An adapter works against the real framework: an ASGI app, a Next.js handler, a database driver |
| Acceptance (BDD) | Gherkin feature files run by [playwright-bdd](https://github.com/vitalets/playwright-bdd) | The whole system does what a developer expects, driven through a real browser against the reference app |

## Unit tests

- **Python:** pytest. Async tests use the pytest plugin that ships with `anyio`, which FastAPI already depends on, so it adds no new dependency.
- **TypeScript:** Vitest. React adapter tests use React Testing Library with a DOM environment.
- Unit tests don't touch the network, a database or a browser. They use fakes for those boundaries.
- Write the test first where practical. Every bug fix starts with a failing test that reproduces the bug.

## Integration tests

Adapters are mostly glue around frameworks, so much of their behaviour can only be trusted against the real thing:

- **FastAPI adapter:** a real Starlette/FastAPI app with a real middleware stack, called in-process. This includes CORS preflights and the "500 without CORS headers" case.
- **Database adapter:** a real PostgreSQL in Docker, the same major version as the work estate.
- **Next.js adapter:** real route handlers and middleware/proxy running in the Next.js server.
- **Streams:** real SSE and WebSocket endpoints, with messages checked end to end.

## Acceptance tests (BDD)

### Why Gherkin with playwright-bdd

- **Gherkin** is the plain-language `Given / When / Then` format. Scenarios read as specifications a non-developer can follow.
- **playwright-bdd** turns feature files into Playwright tests. It drives a real browser, which the acceptance tests need anyway, and gives Chrome DevTools Protocol sessions in Chromium, which the CORS adapter depends on ([ADR 0008](adr/0008-middleware-and-cors-observation.md)).
- We run one BDD runner, not one per language, so each scenario is written once and exercises the whole stack.

### How it fits together

```text
features/*.feature ──▶ playwright-bdd ──▶ Playwright
                                              │
            ┌─────────────────────────────────┼─────────────────────────────┐
            ▼                                 ▼                             ▼
   Reference app in the browser     stack-inspect collector API     DevTools Protocol session
   (clicks, forms, streams)         (query recorded events/graph)   (browser-side failures)
```

The reference app from roadmap milestone M0 runs under Docker Compose with stack-inspect enabled. Step definitions operate the app through the browser, then assert against what stack-inspect recorded, by querying the collector.

### Milestones are specified as features

Each roadmap milestone's "done when" criterion is written as a feature file **before** the milestone is built. The milestone is done when its scenarios pass. For example, M3:

```gherkin
Feature: CORS failures are explained
  Browsers hide the reason for a CORS failure from page JavaScript.
  stack-inspect shows the real cause.

  Background:
    Given the reference app is running with stack-inspect enabled

  @m3 @cors
  Scenario: A server error is reported to the browser as a CORS failure
    When I trigger the "crashing endpoint" action
    Then the browser reports a CORS failure for "/api/crash"
    And stack-inspect shows the request to "/api/crash" returned status 500
    And stack-inspect flags "server error reported as a CORS failure"

  @m3 @cors
  Scenario: A preflight is rejected because a header isn't allowed
    When I trigger the "custom header" action
    Then stack-inspect shows a rejected preflight for "/api/items"
    And the finding names the disallowed header "X-Custom-Header"
```

### Conventions

- Feature files live in `features/`, one file per capability: `execution-graph.feature`, `cors.feature`, `streams.feature` and so on.
- Write scenarios in the developer's language, not the implementation's. Say "the browser reports a CORS failure", not "`Network.loadingFailed` has `corsErrorStatus`".
- One behaviour per scenario. Use `Background` for shared setup.
- Tag each scenario with its milestone (`@m3`) and capability (`@cors`). Unfinished scenarios are tagged `@wip` and are excluded from the required CI run.
- British English throughout.

## Coverage

Coverage is **collected and reported, not gated**, for now: coverage.py for Python and Vitest's V8 coverage for TypeScript. Reports appear in CI output. Adding a gate is a later decision, to be made once the codebase has a stable shape.

## In CI

- Unit and integration tests run on every pull request and are required checks.
- Acceptance tests run on every pull request against the reference app under Docker Compose. Scenarios tagged `@wip` are excluded.
- Test dependencies are development dependencies, so they're audited by the pip-audit and npm audit gates like everything else ([security posture](security-posture.md)). Keep them few.
