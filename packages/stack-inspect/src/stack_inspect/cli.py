"""Command line entry point."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import uvicorn
from stack_inspect_core import emit, new_event_id, new_trace_id

from stack_inspect.server import create_app, default_log_path
from stack_inspect.store import EventLog

_DEFAULT_PORT = 9477
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1"})


def main(argv: list[str] | None = None) -> None:
    """Run the collector or emit a single event."""
    parser = argparse.ArgumentParser(prog="stack-inspect")
    subcommands = parser.add_subparsers(dest="command", required=True)

    serve = subcommands.add_parser("serve", help="run the local collector")
    serve.add_argument("--host", default=os.environ.get("STACK_INSPECT_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=_port_from_env())
    serve.add_argument("--db", type=Path, default=default_log_path())

    record = subcommands.add_parser("emit", help="send one event to a running collector")
    record.add_argument("--name", required=True)
    record.add_argument("--trace-id", required=True)
    record.add_argument("--layer", default="api")
    record.add_argument("--kind", default="function-call")

    args = parser.parse_args(argv)
    if args.command == "serve":
        _serve(args.host, args.port, args.db)
        return
    _emit(args.name, args.trace_id, args.layer, args.kind)


def _port_from_env() -> int:
    raw = os.environ.get("STACK_INSPECT_PORT", str(_DEFAULT_PORT))
    return int(raw)


def _serve(host: str, port: int, database: Path) -> None:
    if host not in _LOOPBACK_HOSTS:
        sys.exit(f"stack-inspect refuses to bind to {host}; use 127.0.0.1")
    database.parent.mkdir(parents=True, exist_ok=True)
    log = EventLog(database)
    app = create_app(log)
    uvicorn.run(app, host=host, port=port, log_level="info")


def _emit(name: str, trace_id: str, layer: str, kind: str) -> None:
    os.environ.setdefault("STACK_INSPECT", "1")
    emit(
        {
            "id": new_event_id(),
            "traceId": trace_id or new_trace_id(),
            "nodeKey": f"{layer}:{kind}:{name}",
            "kind": kind,
            "layer": layer,
            "phase": "instant",
            "name": name,
            "ts": _now_ms(),
        },
    )


def _now_ms() -> float:
    """Return the current time in milliseconds."""
    return time.time() * 1000
