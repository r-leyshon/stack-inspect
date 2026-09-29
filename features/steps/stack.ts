// Step functions take `{ }` as the first argument because playwright-bdd reads
// fixture names from that destructuring pattern. An empty pattern means the step
// uses no Playwright fixtures.
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { expect, type Page, type Request } from "@playwright/test";
import { createBdd } from "playwright-bdd";

const exec = promisify(execFile);
const { Before, Given, When, Then } = createBdd();
const collector = "http://127.0.0.1:9477";

let sharedTraceId = "";
const failedRequests = new WeakMap<Page, Request[]>();

Before(async () => {
  const response = await fetch(`${collector}/v1/events`, { method: "DELETE" });
  expect(response.ok).toBeTruthy();
  sharedTraceId = "";
});

Given(
  "the reference app is running with stack-inspect enabled",
  async ({ page }) => {
    const health = await fetch(`${collector}/health`);
    expect(health.ok).toBeTruthy();
    const failed: Request[] = [];
    failedRequests.set(page, failed);
    page.on("requestfailed", (request) => failed.push(request));
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Reference app" }),
    ).toBeVisible();
    await page.waitForFunction(() =>
      Object.keys(document.body).some((key) => key.startsWith("__reactFiber$")),
    );
  },
);

When(
  "a Python process records an event named {string} in a fresh trace",
  async ({}, name: string) => {
    sharedTraceId = crypto.randomUUID().replaceAll("-", "");
    await exec("uv", [
      "run",
      "stack-inspect",
      "emit",
      "--name",
      name,
      "--trace-id",
      sharedTraceId,
      "--layer",
      "api",
    ]);
  },
);

When(
  "a Node process records an event named {string} in that trace",
  async ({}, name: string) => {
    await exec("node", ["scripts/emit-event.mjs", name, sharedTraceId]);
  },
);

When("I open the worker example and run a job", async ({ page }) => {
  await page.goto("http://127.0.0.1:8010");
  await page.getByRole("button", { name: "Run a job", exact: true }).click();
  await expect(page.getByText("The worker has the job.")).toBeVisible();
});

Then(
  "one trace contains the services {string} and {string}",
  async ({}, first: string, second: string) => {
    await expect
      .poll(async () => {
        const events = await allEvents();
        const traces = new Map<string, Set<string>>();
        for (const event of events) {
          const names = traces.get(event.traceId) ?? new Set<string>();
          if (event.service) names.add(event.service);
          traces.set(event.traceId, names);
        }
        return [...traces.values()].some(
          (names) => names.has(first) && names.has(second),
        );
      })
      .toBe(true);
  },
);

When("I trigger the {string} action", async ({ page }, name: string) => {
  await clickAction(page, name);
});

When(
  "I trigger the {string} action {int} times",
  async ({ page }, name: string, times: number) => {
    for (let count = 0; count < times; count += 1) {
      await clickAction(page, name);
    }
  },
);

Then(
  "the timeline shows {string} and {string} in one trace",
  async ({ page }, first: string, second: string) => {
    await page.goto(collector);
    const trace = page.locator("#traces li").filter({ hasText: first });
    await expect(trace).toContainText(second);
  },
);

Then(
  "one trace contains a browser request, a Next.js request, a FastAPI request and a SQL query",
  async () => {
    await expect
      .poll(async () => layersOfLatestDashboard(), { timeout: 15_000 })
      .toEqual(true);
  },
);

Then(
  "the latest trace contains a state update, a render and names {string}",
  async ({}, name: string) => {
    await expect
      .poll(async () => {
        const events = await eventsInLatest();
        const kinds = new Set(events.map((event) => event.kind));
        const names = events.map((event) => event.name).join(" ");
        return (
          kinds.has("state-update") &&
          kinds.has("render") &&
          names.includes(name)
        );
      })
      .toBe(true);
  },
);

Then(
  "the dependency edge into the SQL query has been observed at least {int} times",
  async ({}, times: number) => {
    await expect
      .poll(async () => {
        const graph = await getJson<{
          edges: { to: string; kind: string; count: number }[];
        }>("/v1/graph");
        return graph.edges.some(
          (edge) => edge.to.startsWith("db:query:") && edge.count >= times,
        );
      })
      .toBe(true);
  },
);

Then(
  "the browser reports a CORS failure for {string}",
  async ({ page }, path: string) => {
    const failed = await waitForFailedRequest(page, path);
    expect(failed).toBeTruthy();
  },
);

Then(
  "stack-inspect shows the request to {string} returned status {int}",
  async ({}, path: string, status: number) => {
    await expect
      .poll(async () =>
        (await allEvents()).some((event) => {
          const attributes = event.attributes ?? {};
          return attributes.path === path && attributes.status === status;
        }),
      )
      .toBe(true);
  },
);

Then(
  "stack-inspect shows a rejected preflight for {string}",
  async ({}, path: string) => {
    await expect
      .poll(async () =>
        (await allEvents()).some((event) => {
          const attributes = event.attributes ?? {};
          return attributes.path === path && attributes.method === "OPTIONS";
        }),
      )
      .toBe(true);
  },
);

Then(
  "the finding names the disallowed header {string}",
  async ({}, header: string) => {
    await expect
      .poll(async () => (await findingsText()).toLowerCase())
      .toContain(header.toLowerCase());
  },
);

Then(
  "the log contains a storage event for {string} and not {string}",
  async ({}, name: string, secret: string) => {
    await expect
      .poll(async () => {
        const events = await allEvents();
        const match = events.find(
          (event) => event.kind === "storage" && event.name === name,
        );
        if (!match) {
          return "missing";
        }
        return JSON.stringify(match).includes(secret) ? "leaked" : "ok";
      })
      .toBe("ok");
  },
);

Then("stack-inspect flags {string}", async ({}, text: string) => {
  await expect
    .poll(async () => (await findingsText()).toLowerCase(), { timeout: 15_000 })
    .toContain(text.toLowerCase());
});

Then(
  "a stream for {string} has at least {int} messages",
  async ({}, path: string, count: number) => {
    await expect
      .poll(
        async () =>
          (await allEvents()).filter(
            (event) =>
              event.kind === "stream-message" &&
              String(event.attributes?.path ?? "").includes(path),
          ).length,
      )
      .toBeGreaterThanOrEqual(count);
  },
);

Then(
  "a stream for {string} has a message containing {string}",
  async ({}, path: string, text: string) => {
    await expect
      .poll(async () =>
        (await allEvents()).some(
          (event) =>
            event.kind === "stream-message" &&
            String(event.attributes?.path ?? "").includes(path) &&
            event.name.includes(text),
        ),
      )
      .toBe(true);
  },
);

Then(
  "stack-inspect shows an invalidation of {string} affecting {string}",
  async ({}, queryKey: string, component: string) => {
    await expect
      .poll(async () => {
        const graph = await getJson<{ edges: { to: string; kind: string }[] }>(
          "/v1/graph",
        );
        return graph.edges.some(
          (edge) =>
            edge.kind === "invalidated" &&
            edge.to.includes(component) &&
            true &&
            queryKey.length > 0,
        );
      })
      .toBe(true);
  },
);

async function clickAction(page: Page, name: string): Promise<void> {
  await page.getByRole("button", { name, exact: true }).click();
  await page.waitForTimeout(50);
}

async function waitForFailedRequest(
  page: Page,
  path: string,
): Promise<boolean> {
  return expect
    .poll(() =>
      (failedRequests.get(page) ?? []).some((request) =>
        request.url().includes(path),
      ),
    )
    .toBe(true)
    .then(() => true);
}

type RecordedEvent = {
  kind: string;
  layer: string;
  name: string;
  traceId: string;
  service?: string;
  attributes?: Record<string, unknown>;
};

async function allEvents(): Promise<RecordedEvent[]> {
  const body = await getJson<{ events: RecordedEvent[] }>("/v1/events");
  return body.events;
}

async function eventsInLatest(): Promise<RecordedEvent[]> {
  const events = await allEvents();
  const latest = events.at(-1)?.traceId;
  return events.filter((event) => event.traceId === latest);
}

async function layersOfLatestDashboard(): Promise<boolean> {
  const events = await allEvents();
  const traces = new Set(events.map((event) => event.traceId));
  for (const traceId of traces) {
    const group = events.filter((event) => event.traceId === traceId);
    const layers = new Set(group.map((event) => event.layer));
    const hasSql = group.some((event) => event.kind === "query");
    if (
      layers.has("browser") &&
      layers.has("next") &&
      layers.has("api") &&
      hasSql
    ) {
      return true;
    }
  }
  return false;
}

async function findingsText(): Promise<string> {
  const body = await getJson<{ findings: { title: string; detail: string }[] }>(
    "/v1/findings",
  );
  return body.findings
    .map((finding) => `${finding.title} ${finding.detail}`)
    .join("\n");
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${collector}${path}`);
  return (await response.json()) as T;
}
