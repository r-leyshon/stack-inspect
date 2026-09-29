"""Start PostgreSQL, the collector, the reference API and the reference web app.

Playwright keeps this process in the foreground. Children are stopped when it exits.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
import urllib.request
from http import HTTPStatus
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLL_SECONDS = 0.5
READY_ATTEMPTS = 120


def main() -> None:
    """Boot the stack and wait until the process is signalled."""
    env = os.environ.copy()
    env["STACK_INSPECT"] = "1"
    env["WEB_ORIGIN"] = "http://127.0.0.1:3000"
    database = ROOT / ".e2e-events.db"
    database.unlink(missing_ok=True)
    _run(["docker", "compose", "-f", "reference/compose.yaml", "up", "-d", "--wait"])
    children = [
        _popen(["uv", "run", "stack-inspect", "serve", "--db", str(database)], env),
        _popen(
            ["uv", "run", "uvicorn", "reference_api.app:app", "--host", "127.0.0.1", "--port", "8000"],
            env,
        ),
        _popen(["npm", "run", "dev", "--workspace", "stack-inspect-reference-web"], env),
        _popen(
            ["uv", "run", "uvicorn", "reference_worker.api:app", "--host", "127.0.0.1", "--port", "8010"],
            {**env, "STACK_INSPECT_SERVICE": "jobs"},
        ),
        _popen(
            ["uv", "run", "python", "-m", "reference_worker.worker"],
            {**env, "STACK_INSPECT_SERVICE": "worker"},
        ),
    ]

    def stop(*_args: object) -> None:
        for child in children:
            child.terminate()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    wait_until("http://127.0.0.1:9477/health")
    wait_until("http://127.0.0.1:8000/health")
    wait_until("http://127.0.0.1:3000")
    wait_until("http://127.0.0.1:8010/health")
    while True:
        if any(child.poll() is not None for child in children):
            stop()
        time.sleep(POLL_SECONDS)


def _run(argv: list[str]) -> None:
    """Run a fixed local command and wait for it."""
    subprocess.run(argv, cwd=ROOT, check=True)  # noqa: S603 # argv is a fixed list, no user input


def _popen(argv: list[str], env: dict[str, str]) -> subprocess.Popen[bytes]:
    """Start a fixed local command and return the process."""
    return subprocess.Popen(argv, cwd=ROOT, env=env)  # noqa: S603 # argv is a fixed list, no user input


def wait_until(url: str) -> None:
    """Block until ``url`` responds."""
    for _attempt in range(READY_ATTEMPTS):
        try:
            with urllib.request.urlopen(url, timeout=1) as response:  # noqa: S310 # local health URL
                if response.status < HTTPStatus.INTERNAL_SERVER_ERROR:
                    return
        except OSError:
            time.sleep(POLL_SECONDS)
    message = f"timed out waiting for {url}"
    raise RuntimeError(message)


if __name__ == "__main__":
    main()
