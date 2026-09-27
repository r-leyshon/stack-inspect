import {
  emit,
  newEventId,
  newTraceId,
  parseTraceparent,
} from "@stack-inspect/core";

const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";

export async function GET(request: Request): Promise<Response> {
  const traceparent = request.headers.get("traceparent");
  const traceId =
    (traceparent && parseTraceparent(traceparent)?.traceId) || newTraceId();
  emit({
    id: newEventId(),
    traceId,
    nodeKey: "next:request:/api/dashboard",
    kind: "request",
    layer: "next",
    phase: "instant",
    name: "GET /api/dashboard",
    ts: Date.now(),
    attributes: { method: "GET", path: "/api/dashboard" },
  });
  const headers = new Headers();
  if (traceparent) {
    headers.set("traceparent", traceparent);
  }
  const response = await fetch(`${apiUrl}/api/dashboard`, { headers });
  return Response.json(await response.json());
}
