"""The worker continues the trace the jobs API put on the message."""

from __future__ import annotations

from typing import TYPE_CHECKING

import stack_inspect_db
from reference_worker.queue import enqueue
from reference_worker.worker import handle_job
from stack_inspect_core import new_span_id, new_trace_id, set_sink
from stack_inspect_core.context import TraceContext, use_context

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_worker_query_stays_on_the_api_trace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A job file is enough to carry the trace into the worker process's SQL."""
    monkeypatch.setenv("STACK_INSPECT", "1")
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.setenv("STACK_INSPECT_SERVICE", "worker")
    monkeypatch.setenv("WORKER_QUEUE", str(tmp_path))
    captured: list[dict[str, object]] = []
    set_sink(captured.append)
    stack_inspect_db.install()
    context = TraceContext(trace_id=new_trace_id(), span_id=new_span_id())
    with use_context(context):
        enqueue()
    assert handle_job() is True
    queries = [event for event in captured if event.get("kind") == "query"]
    assert queries
    assert queries[0]["traceId"] == context.trace_id
    assert queries[0]["service"] == "worker"
    set_sink(None)
