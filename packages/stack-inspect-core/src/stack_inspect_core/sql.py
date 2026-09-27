"""Normalise SQL so repeated queries share a fingerprint.

Parameter values are never retained. Only the statement shape is.
"""

from __future__ import annotations

import hashlib
import re

_WHITESPACE = re.compile(r"\s+")
_STRINGS = re.compile(r"'(?:''|[^'])*'")
_NUMBERS = re.compile(r"(?<!\$)\b\d+(?:\.\d+)?\b")
_FINGERPRINT_LENGTH = 16


def normalise_sql(statement: str) -> str:
    """Return ``statement`` with literals replaced and whitespace collapsed.

    Dollar placeholders such as ``$1`` are kept, so a parametrised query stays
    stable without recording the bound values.
    """
    without_strings = _STRINGS.sub("?", statement)
    without_numbers = _NUMBERS.sub("?", without_strings)
    return _WHITESPACE.sub(" ", without_numbers).strip().lower()


def fingerprint_sql(statement: str) -> str:
    """Return a short hash of the normalised statement."""
    digest = hashlib.sha256(normalise_sql(statement).encode("utf-8")).hexdigest()
    return digest[:_FINGERPRINT_LENGTH]
