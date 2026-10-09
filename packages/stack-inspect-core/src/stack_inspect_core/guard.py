"""Decide whether adapters are allowed to record."""

from __future__ import annotations

import logging
import os

_LOG = logging.getLogger("stack_inspect")

_PRODUCTION_VALUES = frozenset({"production", "prod"})


def enabled() -> bool:
    """Return whether recording is allowed in this process.

    Recording is opt-in via ``STACK_INSPECT=1`` and is refused when the
    process looks like a production deployment.
    """
    if os.environ.get("STACK_INSPECT") != "1":
        return False
    if _is_production():
        _LOG.warning("stack-inspect refused to start because this process is production")
        return False
    return True


def values_enabled() -> bool:
    """Return whether bound parameter values may be recorded.

    This stays off unless ``STACK_INSPECT_VALUES=1`` and recording itself is
    allowed. Production is still refused.
    """
    return enabled() and os.environ.get("STACK_INSPECT_VALUES") == "1"


def _is_production() -> bool:
    """Return whether the current environment variables name production."""
    checked = (
        os.environ.get("NODE_ENV", ""),
        os.environ.get("STACK_INSPECT_ENV", ""),
        os.environ.get("ENVIRONMENT", ""),
    )
    return any(value.lower() in _PRODUCTION_VALUES for value in checked)
