Feature: CORS failures are explained
  Browsers hide the reason for a CORS failure from page JavaScript.
  stack-inspect shows the real cause.

  Background:
    Given the reference app is running with stack-inspect enabled

  @m3 @cors
  Scenario: A server error is reported to the browser as a CORS failure
    When I trigger the "Crashing endpoint" action
    Then the browser reports a CORS failure for "/api/crash"
    And stack-inspect shows the request to "/api/crash" returned status 500
    And stack-inspect flags "server error reported as a CORS failure"

  @m3 @cors
  Scenario: A preflight is rejected because a header isn't allowed
    When I trigger the "Custom header" action
    Then stack-inspect shows a rejected preflight for "/api/items"
    And the finding names the disallowed header "X-Custom-Header"
