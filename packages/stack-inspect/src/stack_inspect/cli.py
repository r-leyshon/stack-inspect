"""Command line entry point."""

from __future__ import annotations

import argparse
import os
import sys
import threading
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
    serve.add_argument(
        "--socket",
        type=Path,
        default=_socket_from_env(),
        help="also listen on this Unix socket, for processes that cannot use loopback TCP",
    )
    serve.add_argument(
        "--root",
        action="append",
        type=Path,
        default=None,
        help="application directory to read when asked; repeat for each app",
    )

    record = subcommands.add_parser("emit", help="send one event to a running collector")
    record.add_argument("--name", required=True)
    record.add_argument("--trace-id", required=True)
    record.add_argument("--layer", default="api")
    record.add_argument("--kind", default="function-call")

    args = parser.parse_args(argv)
    if args.command == "serve":
        _serve(args.host, args.port, args.db, args.socket, _roots(args.root))
        return
    _emit(args.name, args.trace_id, args.layer, args.kind)


def _port_from_env() -> int:
    raw = os.environ.get("STACK_INSPECT_PORT", str(_DEFAULT_PORT))
    return int(raw)


def _socket_from_env() -> Path | None:
    raw = os.environ.get("STACK_INSPECT_SOCKET", "").strip()
    return Path(raw) if raw else None


def _roots(chosen: list[Path] | None) -> list[Path]:
    """Use ``--root`` when it was passed, otherwise ``STACK_INSPECT_ROOTS``."""
    if chosen:
        return chosen
    raw = os.environ.get("STACK_INSPECT_ROOTS", "")
    return [Path(part) for part in raw.split(os.pathsep) if part.strip()]


def _serve(host: str, port: int, database: Path, socket_path: Path | None, roots: list[Path]) -> None:
    if host not in _LOOPBACK_HOSTS:
        sys.exit(f"stack-inspect refuses to bind to {host}; use 127.0.0.1")
    database.parent.mkdir(parents=True, exist_ok=True)
    log = EventLog(database)
    app = create_app(log, roots)
    if socket_path is not None:
        _listen_on_socket(app, socket_path)
    uvicorn.run(app, host=host, port=port, log_level="info")


def _listen_on_socket(app: object, socket_path: Path) -> None:
    """Listen on ``socket_path`` as well as the loopback port. TCP stays loopback-only."""
    if socket_path.exists():
        socket_path.unlink()
    socket_path.parent.mkdir(parents=True, exist_ok=True)

    def run() -> None:
        previous = os.umask(0o077)
        try:
            uvicorn.run(app, uds=str(socket_path), log_level="info")  # type: ignore[arg-type] # the same FastAPI app serves both listeners
        finally:
            os.umask(previous)

    threading.Thread(target=run, name="stack-inspect-socket", daemon=True).start()
    for _attempt in range(50):
        if socket_path.exists():
            socket_path.chmod(0o600)
            return
        time.sleep(0.05)


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
