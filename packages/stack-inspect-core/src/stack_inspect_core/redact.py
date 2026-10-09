"""Drop values that must never be recorded."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

_MAX_PARAMETER_TEXT = 200
_MAX_PARAMETERS = 32
_MAX_DEPTH = 4

_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "cookies",
        "password",
        "passwd",
        "secret",
        "set-cookie",
        "token",
    },
)


def redact_attributes(attributes: dict[str, object] | None) -> dict[str, object]:
    """Return a copy of ``attributes`` with sensitive keys removed.

    Nested dictionaries are redacted too. Lists and other values are kept as-is,
    so callers must not put secrets anywhere except a recognised key.
    """
    if not attributes:
        return {}
    cleaned: dict[str, object] = {}
    for key, value in attributes.items():
        if key.lower() in _SENSITIVE_KEYS:
            continue
        if isinstance(value, dict):
            cleaned[key] = redact_attributes(value)
        else:
            cleaned[key] = value
    return cleaned


def plain_parameters(value: object) -> object:
    """Return a JSON-safe copy of bound arguments, with secret keys removed."""
    return _plain(value, 0)


_UNSHAPED = object()


def _plain(value: object, depth: int) -> object:
    if depth > _MAX_DEPTH:
        return type(value).__name__
    scalar = _scalar(value)
    if scalar is not _UNSHAPED:
        return scalar
    if isinstance(value, Mapping):
        items = list(value.items())[:_MAX_PARAMETERS]
        return redact_attributes({str(key): _plain(item, depth + 1) for key, item in items})
    if isinstance(value, Sequence):
        return [_plain(item, depth + 1) for item in list(value)[:_MAX_PARAMETERS]]
    return type(value).__name__


def _scalar(value: object) -> object:
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        if len(value) <= _MAX_PARAMETER_TEXT:
            return value
        return f"{value[:_MAX_PARAMETER_TEXT]}…"
    if isinstance(value, bytes):
        return f"{len(value)} bytes"
    return _UNSHAPED
