Feature: Streams
  Server-sent events and WebSockets are a stream of messages, not one long bar.

  Background:
    Given the reference app is running with stack-inspect enabled

  @m4
  Scenario: Each server-sent event appears under its stream
    When I trigger the "Open stream" action
    Then a stream for "/api/stream" has at least 3 messages

  @m4
  Scenario: A WebSocket message is linked to its stream
    When I trigger the "Open socket" action
    Then a stream for "/api/ws" has a message containing "hello"

  @m6
  Scenario: A stream that keeps reconnecting is flagged
    When I trigger the "Open stream" action 4 times
    Then stack-inspect flags "stream reconnecting repeatedly"
