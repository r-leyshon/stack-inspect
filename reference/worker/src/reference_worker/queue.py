"""A directory of JSON files. The API writes a job; the worker takes it."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from stack_inspect_core import extract, inject

if TYPE_CHECKING:
    from stack_inspect_core.context import TraceContext


def queue_dir() -> Path:
    """Return the directory both processes use, creating it if needed."""
    path = Path(os.environ.get("WORKER_QUEUE", ".worker-queue"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def enqueue() -> Path:
    """Write one job carrying the active trace. The dict is the whole message."""
    path = queue_dir() / f"{uuid4().hex}.json"
    path.write_text(json.dumps(inject({"task": "count-notes"})), encoding="utf-8")
    return path


def take() -> tuple[TraceContext | None, str] | None:
    """Remove one job from the queue and return its trace and task name."""
    jobs = sorted(queue_dir().glob("*.json"))
    if not jobs:
        return None
    path = jobs[0]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    finally:
        path.unlink(missing_ok=True)
    if not isinstance(payload, dict):
        return None
    carrier = {str(key): str(value) for key, value in payload.items()}
    return extract(carrier), carrier.get("task", "")
