# Spike: Backend read tracking

**Status:** Stopped at the call. Not an architecture decision. Do not build M10.

## Question

Can the collector say which request parameter flowed into which query?

## What was tried

The running reference app was read back from the collector. A query event carries `fingerprint` and `statement`. A statement such as `select name from items where id = $1` keeps the placeholder. The bound value is not on the event. The database adapter receives that value and drops it. An API request event carries `method`, `path`, and the span id it sent. It does not carry path parameters, query parameters, or a body.

The reference routes do not take a parameter. The value passed to `$1` is `row["id"]` from an earlier query in the same handler, not a field of the HTTP request.

Source reading already draws a dashed line when a SQL literal sits in a route's call cone. That line says the route's source contains the query. It does not say a parameter was read, and it does not follow a value through a variable.

## What we kept

The span id still joins the request to the query it caused. That is "this request ran this query". The statement text still shows where a placeholder sits. The dashed source line still appears when the SQL literal is visible in the route.

## What we will not claim

Nothing in the running process records that a named parameter became `$1`. The driver sees the bound arguments and the source sees the call, and neither one is a read set. Matching equal values would record the values, which stays off unless a person turns that on, and two queries can share a value without one causing the other. Wrapping every parameter so the app reports each read would pepper the application with instrumentation.

A later spike could try a narrower static claim: a placeholder argument that is a bare name, and that name is a parameter of the route. That would be a dashed claim about the source. The reference app does not have that shape, so it would not demonstrate it. That claim is not scheduled.

## Conclusion

M10 is not feasible with the adapters as they stand. The collector can say which request ran which query. It cannot say which parameter became which placeholder.

## Next step

Do not implement parameter-to-placeholder tracking, and do not wrap parameters in application code. Leave the span-id cause, the statement text, and the dashed source line as they are.

Bound values, and a short preview of the rows a query already returned, may be recorded, and only when `STACK_INSPECT_VALUES=1` ([ADR 0016](../adr/0016-optional-parameter-values.md)). That records what was passed and a few cells that came back. It does not draw an edge because two values are equal, and it does not say which parameter became which placeholder.

The next research gate was M11. That spike has since stopped: a cache key does not cross HTTP ([spike](0003-cross-boundary-dependencies.md)). The next research gate is M12. Do not start it until that spike is asked for.
