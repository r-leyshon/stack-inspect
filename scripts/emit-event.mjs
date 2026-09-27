const collector = process.env.STACK_INSPECT_URL ?? "http://127.0.0.1:9477";
const name = process.argv[2];
const traceId = process.argv[3];

const response = await fetch(`${collector}/v1/events`, {
  method: "POST",
  headers: { "content-type": "text/plain" },
  body: JSON.stringify({
    id: crypto.randomUUID().replaceAll("-", ""),
    traceId,
    nodeKey: `next:function-call:${name}`,
    kind: "function-call",
    layer: "next",
    phase: "instant",
    name,
    ts: Date.now(),
  }),
});

if (!response.ok) {
  process.exitCode = 1;
}
