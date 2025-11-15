# Purpose: Persist condition/problem list records in the SQLite datastore.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Condition ingestion services."""

from __future__ import annotations

import sqlite3
from typing import Mapping, Sequence, TypedDict

from health_records_collection.db.utils import execute_update
from health_records_collection.services.common import (
    clean_str,
    coerce_int,
    ensure_mapping_sequence,
    STANDARD_RECORD_UPDATE_SPECS,
    build_updates_from_specs,
    insert_code_mappings,
)
from health_records_collection.services.encounters import (
    EncounterLookup,
    find_encounter_id,
)
from health_records_collection.services.providers import get_or_create_provider

__all__ = ["insert_conditions"]


def _extract_condition_codes(
    cond: Mapping[str, object],
) -> list[Mapping[str, object]]:
    """Extract and validate codes from a condition entry."""
    raw_codes = cond.get("codes")
    codes: list[Mapping[str, object]] = []
    if isinstance(raw_codes, Sequence) and not isinstance(raw_codes, (str, bytes)):
        codes = list(ensure_mapping_sequence(raw_codes))
    return codes


def _extract_primary_code(
    codes: list[Mapping[str, object]],
) -> tuple[str | None, str | None, str | None]:
    """Extract primary code information from codes list."""
    primary_code = codes[0] if codes else {}
    code_value = clean_str(primary_code.get("code"))
    code_system = clean_str(primary_code.get("system"))
    code_display = clean_str(primary_code.get("display"))
    return code_value, code_system, code_display


def _extract_condition_fields(
    cond: Mapping[str, object],
    codes: list[Mapping[str, object]],
    code_value: str | None,
    code_system: str | None,
    code_display: str | None,
) -> ConditionData:
    """Extract and clean all condition fields from an entry."""
    name = clean_str(cond.get("name")) or code_display or code_value

    return {
        "name": name,
        "code_value": code_value,
        "code_system": code_system,
        "code_display": code_display,
        "onset_date": clean_str(cond.get("start")),
        "status": clean_str(cond.get("status")),
        "notes": clean_str(cond.get("notes")),
        "ds_id": coerce_int(cond.get("data_source_id")),
        "codes": codes,
    }  # type: ignore


def _resolve_condition_encounter(
    conn: sqlite3.Connection,
    patient_id: int,
    cond: Mapping[str, object],
    provider_name: str | None,
    provider_id: int | None,
) -> int | None:
    """Resolve encounter ID with fallback logic."""
    # Try primary date sources
    lookup = EncounterLookup(
        patient_id=patient_id,
        encounter_date=clean_str(cond.get("encounter_start"))
        or clean_str(cond.get("start"))
        or clean_str(cond.get("author_time")),
        provider_name=provider_name,
        provider_id=provider_id,
    )
    encounter_id = find_encounter_id(conn, lookup)

    # Fall back to encounter end date if needed
    if encounter_id is None and cond.get("encounter_end"):
        lookup = EncounterLookup(
            patient_id=patient_id,
            encounter_date=clean_str(cond.get("encounter_end")),
            provider_name=provider_name,
            provider_id=provider_id,
        )
        encounter_id = find_encounter_id(conn, lookup)

    return encounter_id


def _find_existing_condition(
    cur: sqlite3.Cursor,
    patient_id: int,
    condition_data: ConditionData,
) -> tuple | None:
    """Find existing condition record in database."""
    return cur.execute(
        """
        SELECT id, status, notes, provider_id, encounter_id, data_source_id
          FROM condition
         WHERE patient_id = ?
           AND COALESCE(name, '') = COALESCE(?, '')
           AND COALESCE(code, '') = COALESCE(?, '')
           AND COALESCE(onset_date, '') = COALESCE(?, '')
        """,
        (
            patient_id,
            condition_data.get("name") or "",
            condition_data.get("code_value") or "",
            condition_data.get("onset_date") or "",
        ),
    ).fetchone()


def _insert_new_condition(
    cur: sqlite3.Cursor,
    condition_data: ConditionData,
) -> int:
    """Insert a new condition record and return its ID."""
    cur.execute(
        """
        INSERT INTO condition (
            patient_id,
            name,
            onset_date,
            status,
            notes,
            provider_id,
            encounter_id,
            code,
            code_system,
            code_display,
            data_source_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            condition_data.get("patient_id"),
            condition_data.get("name"),
            condition_data.get("onset_date"),
            condition_data.get("status"),
            condition_data.get("notes"),
            condition_data.get("provider_id"),
            condition_data.get("encounter_id"),
            condition_data.get("code_value"),
            condition_data.get("code_system"),
            condition_data.get("code_display"),
            condition_data.get("ds_id"),
        ),
    )
    condition_id = cur.lastrowid
    if condition_id is None:
        raise sqlite3.DatabaseError("Failed to insert condition; lastrowid is None.")
    return int(condition_id)


class ConditionData(TypedDict, total=False):
    """Type-safe condition field dictionary."""

    name: str | None
    code_value: str | None
    code_system: str | None
    code_display: str | None
    onset_date: str | None
    status: str | None
    notes: str | None
    ds_id: int | None
    patient_id: int
    provider_id: int | None
    encounter_id: int | None
    codes: list[Mapping[str, object]]


def insert_conditions(
    conn: sqlite3.Connection,
    patient_id: int,
    conditions: Sequence[Mapping[str, object]],
) -> None:
    """Upsert condition entries and associated codes.

    Args:
        conn: Active SQLite connection.
        patient_id: Identifier for the patient owning the conditions.
        conditions: Sequence of parsed condition dictionaries.
    """
    if not conditions:
        return

    cur = conn.cursor()
    for cond in conditions:
        # Extract and validate codes
        codes = _extract_condition_codes(cond)
        code_value, code_system, code_display = _extract_primary_code(codes)

        # Extract all condition fields into type-safe dict
        condition_data: ConditionData = _extract_condition_fields(
            cond,
            codes,
            code_value,
            code_system,
            code_display,
        )

        if not condition_data.get("name"):
            continue

        # Enrich with patient context
        condition_data["patient_id"] = patient_id  # type: ignore

        # Resolve provider
        provider_name = clean_str(cond.get("provider"))
        if provider_name:
            prov_id = get_or_create_provider(conn, provider_name)
            condition_data["provider_id"] = prov_id  # type: ignore

        # Resolve encounter with fallback
        encounter_id = _resolve_condition_encounter(
            conn,
            patient_id,
            cond,
            provider_name,
            condition_data.get("provider_id"),
        )
        if encounter_id:
            condition_data["encounter_id"] = encounter_id  # type: ignore

        # Find existing record
        existing = _find_existing_condition(cur, patient_id, condition_data)

        if existing:
            # Build updates for changed fields
            updates, params = build_updates_from_specs(
                condition_data, existing, STANDARD_RECORD_UPDATE_SPECS
            )
            condition_id = existing[0]
            if execute_update(cur, "condition", updates, params, condition_id):
                pass  # Updated successfully
        else:
            # Insert new record
            condition_id = _insert_new_condition(cur, condition_data)

        # Process additional codes for the condition
        insert_code_mappings(
            cur,
            table="condition_code",
            ref_id=condition_id,
            codes=codes,
        )

    conn.commit()
