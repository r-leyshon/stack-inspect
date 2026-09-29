Feature: Browser storage
  IndexedDB and the Origin Private File System are visible without their contents.

  Background:
    Given the reference app is running with stack-inspect enabled

  @m9
  Scenario: A local write records the store and not the value
    When I trigger the "Save locally" action
    Then the log contains a storage event for "notes" and not "secret-note"
