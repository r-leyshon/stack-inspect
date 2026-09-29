"""Jobs API. It records the request, then hands the trace to the worker process."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import stack_inspect_fastapi
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from reference_worker.queue import enqueue

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Name this process before it records anything."""
    os.environ.setdefault("STACK_INSPECT_SERVICE", "jobs")
    yield


app = FastAPI(title="stack-inspect worker example", lifespan=lifespan)
stack_inspect_fastapi.install(app)

_PAGE = """<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="utf-8" />
  <title>Worker example</title>
</head>
<body>
  <h1>Worker example</h1>
  <p>This is a second app. The button asks this process to queue a job.
  A separate worker process picks it up and continues the same trace.
  The graph at <a href="http://127.0.0.1:9477">http://127.0.0.1:9477</a>
  then shows a jobs lane and a worker lane.</p>
  <button id="run" type="button">Run a job</button>
  <p id="status"></p>
  <script>
    document.getElementById("run").addEventListener("click", async () => {
      const status = document.getElementById("status");
      status.textContent = "Queued…";
      const response = await fetch("/jobs", { method: "POST" });
      status.textContent = response.ok ? "The worker has the job." : "The jobs API did not accept it.";
    });
  </script>
</body>
</html>
"""


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the jobs API is up."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    """Serve the single button that queues a job."""
    return _PAGE


@app.post("/jobs")
def create_job() -> dict[str, str]:
    """Queue one job. The active trace is copied into the message."""
    enqueue()
    return {"status": "queued"}
