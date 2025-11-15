# Purpose: Shared helper utilities for service-layer persistence.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Common helpers for service modules."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence


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


def _value_is_not_none(value: Any) -> bool:
    return value is not None


@dataclass(frozen=True)
class UpdateFieldSpec:
    """Specification for deriving UPDATE statements from record diffs."""

    data_key: str
    column_name: str
    existing_index: int
    fallback: Any
    predicate: Callable[[Any], bool] = bool


STANDARD_RECORD_UPDATE_SPECS: tuple[UpdateFieldSpec, ...] = (
    UpdateFieldSpec("status", "status", 1, ""),
    UpdateFieldSpec("notes", "notes", 2, ""),
    UpdateFieldSpec("provider_id", "provider_id", 3, 0),
    UpdateFieldSpec("encounter_id", "encounter_id", 4, 0),
    UpdateFieldSpec("ds_id", "data_source_id", 5, 0, _value_is_not_none),
)


def build_updates_from_specs(
    record: Mapping[str, Any],
    existing: Sequence[Any],
    specs: Sequence[UpdateFieldSpec],
) -> tuple[list[str], list[Any]]:
    """Return UPDATE fragments and params for fields defined in specs."""
    updates: list[str] = []
    params: list[Any] = []
    for spec in specs:
        new_value = record.get(spec.data_key)
        if not spec.predicate(new_value):
            continue
        existing_value = (
            existing[spec.existing_index]
            if spec.existing_index < len(existing)
            else None
        )
        comparable_existing = existing_value if existing_value else spec.fallback
        if comparable_existing == new_value:
            continue
        updates.append(f"{spec.column_name} = ?")
        params.append(new_value)
    return updates, params


ALLOWED_CODE_REFERENCES: dict[str, str] = {
    "condition_code": "condition_id",
    "procedure_code": "procedure_id",
}


def insert_code_mappings(
    cur: sqlite3.Cursor,
    *,
    table: str,
    ref_id: int,
    codes: Sequence[Mapping[str, Any]],
) -> None:
    """Insert code/system/display entries into the requested code table."""
    reference_column = ALLOWED_CODE_REFERENCES.get(table)
    if reference_column is None:
        raise ValueError(f"Unsupported code table '{table}'.")

    for code in ensure_mapping_sequence(codes):
        code_value = clean_str(code.get("code"))
        if not code_value:
            continue
        code_system_val = clean_str(code.get("system"))
        display_val = clean_str(code.get("display"))
        cur.execute(
            f"""
            INSERT OR IGNORE INTO {table} (
                {reference_column},
                code,
                code_system,
                display_name
            )
            VALUES (?, ?, ?, ?)
            """,
            (ref_id, code_value, code_system_val, display_val),
        )
