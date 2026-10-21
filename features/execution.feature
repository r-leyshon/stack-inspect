Feature: Execution graph
  The collector shows what one user action did across the browser, Next.js, FastAPI and PostgreSQL.

  Background:
    Given the reference app is running with stack-inspect enabled

  @m1
  Scenario: Events from Python and Node appear on one timeline
    When a Python process records an event named "api-step" in a fresh trace
    And a Node process records an event named "web-step" in that trace
    Then the timeline shows "api-step" and "web-step" in one trace

  @m2
  Scenario: A click is one trace from the browser to SQL
    When I trigger the "Load dashboard" action
    Then one trace contains a browser request, a Next.js request, a FastAPI request and a SQL query

  @m5
  Scenario: A click shows the state update, the render and the request it caused
    When I trigger the "Unchanged child" action
    Then the latest trace contains a state update, a render and names "QuietChild"

  @m7
  Scenario: Edges accumulate evidence across interactions
    When I trigger the "Load dashboard" action
    And I trigger the "Load dashboard" action
    Then the dependency edge into the SQL query has been observed at least 2 times

  @m7
  Scenario: A fetch inside useEffect names the effect as its cause
    When I trigger the "Effect fetch" action
    Then a browser request is caused by the EffectFetch effect
