Feature: Analysis findings
  Repeated, slow, cancelled and apparently unnecessary work is flagged without manual inspection.

  Background:
    Given the reference app is running with stack-inspect enabled

  @m6
  Scenario: An N+1 query is flagged
    When I trigger the "N plus one" action
    Then stack-inspect flags "same query executed repeatedly"

  @m6
  Scenario: A duplicate request is flagged
    When I trigger the "Duplicate fetch" action
    Then stack-inspect flags "duplicate request"

  @m6
  Scenario: Sequential independent queries are flagged
    When I trigger the "Sequential awaits" action
    Then stack-inspect flags "sequential awaits"

  @m6
  Scenario: A render with nothing changed is flagged
    When I trigger the "Unchanged child" action
    Then stack-inspect flags "no changed props or state"

  @m6
  Scenario: A large render subtree is flagged
    When I trigger the "Fan out" action
    Then stack-inspect flags "large render subtree"

  @m6
  Scenario: An effect that keeps restarting is flagged
    When I trigger the "Restart effect" action 3 times
    Then stack-inspect flags "effect repeatedly cancelled"

  @m6
  Scenario: Work after the result was visible is flagged
    When I trigger the "Extra work" action
    Then stack-inspect flags "after the user-visible result"
