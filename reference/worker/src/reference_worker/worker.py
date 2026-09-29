"""Worker process. It continues whatever trace the jobs API put on the message."""

from __future__ import annotations

import os
import signal
import time

import stack_inspect_db
from sqlalchemy import create_engine, text
from stack_inspect_core.context import use_context

from reference_worker.queue import take


def handle_job() -> bool:
    """Run one queued job inside the trace it carried. Return whether there was one."""
    job = take()
    if job is None:
        return False
    context, _task = job
    if context is None:
        _count_notes()
        return True
    with use_context(context):
        _count_notes()
    return True


def _count_notes() -> None:
    """Query a local engine so the database adapter records the worker's SQL."""
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.execute(text("create table if not exists notes (id integer)"))
        connection.execute(text("select count(*) from notes"))


def main() -> None:
    """Poll the queue until the process is asked to stop."""
    os.environ.setdefault("STACK_INSPECT", "1")
    os.environ.setdefault("STACK_INSPECT_SERVICE", "worker")
    stack_inspect_db.install()
    stopping = False

    def stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping:
        if not handle_job():
            time.sleep(0.2)


if __name__ == "__main__":
    main()
