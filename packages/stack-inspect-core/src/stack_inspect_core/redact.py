"""Drop values that must never be recorded."""

from __future__ import annotations

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
