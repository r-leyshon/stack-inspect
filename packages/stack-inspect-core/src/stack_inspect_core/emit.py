"""Send one event to the local collector, failing open."""

from __future__ import annotations

import http.client
import json
import logging
import os
import socket
import urllib.request
from collections.abc import Callable

from stack_inspect_core.guard import enabled
from stack_inspect_core.redact import redact_attributes

_LOG = logging.getLogger("stack_inspect")
_DEFAULT_URL = "http://127.0.0.1:9477/v1/events"
_TIMEOUT_SECONDS = 0.4

Sink = Callable[[dict[str, object]], None]
_sink: Sink | None = None


def set_sink(sink: Sink | None) -> None:
    """Replace the network poster, for tests. Pass ``None`` to restore it."""
    global _sink  # noqa: PLW0603 # tests swap the process-wide sink
    _sink = sink


def emit(event: dict[str, object]) -> None:
    """Record ``event`` if stack-inspect is enabled. Never raises."""
    if not enabled():
        return
    payload = dict(event)
    service = os.environ.get("STACK_INSPECT_SERVICE", "").strip()
    if service and not payload.get("service"):
        payload["service"] = service[:80]
    attributes = payload.get("attributes")
    if isinstance(attributes, dict):
        payload["attributes"] = redact_attributes(attributes)
    try:
        if _sink is not None:
            _sink(payload)
            return
        _post(payload)
    except Exception:  # noqa: BLE001 # the collector is optional; a failed post must not break the app
        _LOG.debug("stack-inspect dropped an event", exc_info=True)


def _post(payload: dict[str, object]) -> None:
    """POST ``payload`` to the collector as plain text, so the browser needs no preflight."""
    socket_path = os.environ.get("STACK_INSPECT_SOCKET", "").strip()
    body = json.dumps(payload).encode("utf-8")
    if socket_path:
        _post_socket(socket_path, body)
        return
    url = os.environ.get("STACK_INSPECT_URL", _DEFAULT_URL).rstrip("/")
    if not url.endswith("/v1/events"):
        url = f"{url}/v1/events"
    request = urllib.request.Request(  # noqa: S310 # URL is the local collector, not user input
        url,
        data=body,
        headers={"content-type": "text/plain"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS):  # noqa: S310
        return


class _UnixConnection(http.client.HTTPConnection):
    """An HTTP connection whose transport is a Unix socket, not TCP."""

    def __init__(self, path: str) -> None:
        super().__init__("localhost", timeout=_TIMEOUT_SECONDS)
        self._unix_path = path

    def connect(self) -> None:
        """Connect to the collector socket."""
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self._unix_path)


def _post_socket(path: str, body: bytes) -> None:
    """POST ``body`` to the collector listening on ``path``."""
    connection = _UnixConnection(path)
    try:
        connection.request("POST", "/v1/events", body=body, headers={"content-type": "text/plain"})
        response = connection.getresponse()
        response.read()
    finally:
        connection.close()
