Feature: Query cache invalidation
  Libraries that already track subscriptions contribute read and invalidated edges.

  Background:
    Given the reference app is running with stack-inspect enabled

  @m8
  Scenario: Invalidating a query shows what it affected
    When I trigger the "Load cached results" action
    And I trigger the "Invalidate results" action
    Then stack-inspect shows an invalidation of "results" affecting "ResultsPanel"
