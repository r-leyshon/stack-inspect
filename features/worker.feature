Feature: A worker process
  A second process continues the trace and shows up as its own lane.

  @worker
  Scenario: A queued job is the same trace in the worker
    When I open the worker example and run a job
    Then one trace contains the services "jobs" and "worker"

  @worker
  Scenario: Reading source joins the job to the worker query
    When I open the worker example and run a job
    And I read the source into the graph
    Then the graph has a declared edge from "api:request:POST /jobs" to a query
