# Purpose: Shared helper utilities for service-layer persistence.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Common helpers for service modules."""

from __future__ import annotations

from typing import Any, Iterable, Iterator, Mapping


def clean_str(value: Any) -> str | None:
    """Return a trimmed string for any input, or None when empty."""
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = value.strip()
    else:
        cleaned = str(value).strip()
    return cleaned or None


def coerce_int(value: Any) -> int | None:
    """Return an int for numeric inputs, otherwise None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def ensure_mapping_sequence(items: Iterable[Any]) -> Iterator[Mapping[str, Any]]:
    """Yield mapping entries from a potentially heterogeneous iterable."""
    for item in items:
        if isinstance(item, Mapping):
            yield item
