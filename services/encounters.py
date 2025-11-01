# Purpose: Provide encounter lookup and persistence helpers for the SQLite datastore.
# Author: Codex + Lauren
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Encounter services: lookup and ingestion helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from health_records_collection.db.utils import update_single_field
from health_records_collection.services.common import clean_str, coerce_int
from health_records_collection.services.providers import get_or_create_provider

__all__ = ["find_encounter_id", "insert_encounters", "EncounterLookup"]


@dataclass
class EncounterLookup:
    """Parameters for encounter lookup operations."""

    patient_id: int
    encounter_date: Optional[str] = None
    provider_name: Optional[str] = None
    provider_id: Optional[int] = None


def _date_only(value: Optional[str]) -> Optional[str]:
    """Return the YYYYMMDD component of a date string if present."""
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) >= 8:
        return digits[:8]
    return None


def _fetch_encounter_id(
    cur: sqlite3.Cursor,
    sql: str,
    params: tuple[Any, ...],
) -> Optional[int]:
    """Execute a query and return the first column of the first row."""
    row = cur.execute(sql, params).fetchone()
    return row[0] if row else None


def _find_by_exact_date(
    cur: sqlite3.Cursor,
    lookup: EncounterLookup,
) -> Optional[int]:
    """Try to find encounter by exact date match."""
    if not lookup.encounter_date:
        return None

    sql = """
        SELECT id
          FROM encounter
         WHERE patient_id = ?
           AND COALESCE(encounter_date, '') = COALESCE(?, '')
    """
    params = [lookup.patient_id, lookup.encounter_date]

    if lookup.provider_id is not None:
        sql += " AND COALESCE(provider_id, -1) = COALESCE(?, -1)"
        params.append(lookup.provider_id)

    sql += " ORDER BY id DESC LIMIT 1"
    return _fetch_encounter_id(cur, sql, tuple(params))


def _find_by_day(
    cur: sqlite3.Cursor,
    lookup: EncounterLookup,
    encounter_day: str,
) -> Optional[int]:
    """Try to find encounter by day portion of date."""
    sql = """
        SELECT id
          FROM encounter
         WHERE patient_id = ?
           AND substr(COALESCE(encounter_date, ''), 1, 8) = ?
    """
    params = [lookup.patient_id, encounter_day]

    if lookup.provider_id is not None:
        sql += " AND COALESCE(provider_id, -1) = COALESCE(?, -1)"
        params.append(lookup.provider_id)

    sql += " ORDER BY encounter_date DESC, id DESC LIMIT 1"
    return _fetch_encounter_id(cur, sql, tuple(params))


def _find_by_provider(
    cur: sqlite3.Cursor,
    lookup: EncounterLookup,
) -> Optional[int]:
    """Find most recent encounter for patient and provider."""
    if lookup.provider_id is None:
        return None

    sql = """
        SELECT id
          FROM encounter
         WHERE patient_id = ?
           AND COALESCE(provider_id, -1) = COALESCE(?, -1)
         ORDER BY encounter_date DESC, id DESC
         LIMIT 1
    """
    return _fetch_encounter_id(cur, sql, (lookup.patient_id, lookup.provider_id))


def find_encounter_id(
    conn: sqlite3.Connection,
    lookup: EncounterLookup,
) -> Optional[int]:
    """Resolve an encounter row based on temporal and provider hints.

    Args:
        conn: Active SQLite connection.
        lookup: Encounter lookup parameters.

    Returns:
        Optional[int]: Matching encounter primary key if one is found.
    """
    # Resolve provider ID if needed
    if lookup.provider_id is None and lookup.provider_name:
        lookup.provider_id = get_or_create_provider(
            conn, clean_str(lookup.provider_name)
        )

    cur = conn.cursor()

    # Try exact date match
    match = _find_by_exact_date(cur, lookup)
    if match is not None:
        return match

    # Try day portion match
    encounter_day = _date_only(lookup.encounter_date or "")
    if encounter_day:
        match = _find_by_day(cur, lookup, encounter_day)
        if match is not None:
            return match

    # Try provider-only match
    return _find_by_provider(cur, lookup)


@dataclass
class EncounterData:
    """Container for parsed encounter data."""

    patient_id: int
    encounter_date: Optional[str] = None
    source_encounter_id: Optional[str] = None
    provider_name: Optional[str] = None
    provider_id: Optional[int] = None
    encounter_type: Optional[str] = None
    reason_for_visit: Optional[str] = None
    notes: Optional[str] = None
    data_source_id: Optional[int] = None
    organization_id: Optional[int] = None


def _parse_notes(enc: Mapping[str, object]) -> Optional[str]:
    """Extract and format notes from encounter data."""
    notes = clean_str(enc.get("notes"))
    if not notes:
        fallback_parts = [
            clean_str(enc.get("location")),
            clean_str(enc.get("status")),
            clean_str(enc.get("mood")),
            clean_str(enc.get("code")),
        ]
        fallback = " | ".join(part for part in fallback_parts if part)
        notes = fallback or None
    return notes


def _parse_encounter(
    conn: sqlite3.Connection,
    patient_id: int,
    enc: Mapping[str, object],
) -> Optional[EncounterData]:
    """Parse encounter data into structured format."""
    encounter_date = clean_str(enc.get("start")) or clean_str(enc.get("end"))
    source_encounter_id = clean_str(enc.get("source_id"))
    provider_name = clean_str(enc.get("provider"))
    provider_id = coerce_int(enc.get("provider_id"))

    # Early return if missing required fields
    if not (encounter_date and source_encounter_id):
        return None

    # Resolve provider if needed
    if provider_id is None and provider_name:
        provider_id = get_or_create_provider(conn, provider_name)

    # Get organization details
    organization_id = None
    org_name = enc.get("organization")
    if isinstance(org_name, str):
        organization_id = get_or_create_provider(
            conn, org_name, entity_type="organization"
        )

    return EncounterData(
        patient_id=patient_id,
        encounter_date=encounter_date,
        source_encounter_id=source_encounter_id,
        provider_name=provider_name,
        provider_id=provider_id,
        encounter_type=clean_str(enc.get("type")),
        reason_for_visit=clean_str(enc.get("reason_for_visit")),
        notes=_parse_notes(enc),
        data_source_id=coerce_int(enc.get("data_source_id")),
        organization_id=organization_id,
    )


def insert_encounters(
    conn: sqlite3.Connection,
    patient_id: int,
    encounters: Sequence[Mapping[str, object]],
) -> None:
    """Upsert encounter metadata, merging new information when duplicates appear.

    Args:
        conn: Active SQLite connection.
        patient_id: Identifier for the patient owning the encounter.
        encounters: Collection of parsed encounter dictionaries.
    """
    if not encounters:
        return

    cur = conn.cursor()
    for enc in encounters:
        encounter = _parse_encounter(conn, patient_id, enc)
        if not encounter:
            continue
        existing = _find_existing_encounter(cur, encounter)

        if existing:
            _update_encounter(cur, encounter, existing)
        else:
            _insert_encounter(cur, encounter)

    conn.commit()


def _find_existing_encounter(
    cur: sqlite3.Cursor,
    encounter: EncounterData,
) -> Optional[tuple[Any, ...]]:
    """Find existing encounter record if any."""
    return cur.execute(
        """
        SELECT id, encounter_type, notes, reason_for_visit, 
                data_source_id, provider_id, organization_id
          FROM encounter
         WHERE patient_id = ?
           AND encounter_date = ?
           AND COALESCE(provider_id, -1) = COALESCE(?, -1)
        """,
        (
            encounter.patient_id,
            encounter.encounter_date,
            encounter.provider_id,
        ),
    ).fetchone()


def _update_encounter(
    cur: sqlite3.Cursor,
    encounter: EncounterData,
    existing: tuple[Any, ...],
) -> None:
    """Update existing encounter with new data."""
    (
        encounter_db_id,
        existing_type,
        existing_notes,
        existing_reason,
        existing_data_source,
        existing_provider,
        existing_org,
    ) = existing

    # Build update params
    updates: list[str] = []
    params: list[Any] = []

    if encounter.encounter_type and (existing_type or "") != encounter.encounter_type:
        updates.append("encounter_type = ?")
        params.append(encounter.encounter_type)

    if encounter.notes and (existing_notes or "") != encounter.notes:
        updates.append("notes = ?")
        params.append(encounter.notes)

    if (
        encounter.reason_for_visit
        and (existing_reason or "") != encounter.reason_for_visit
    ):
        updates.append("reason_for_visit = ?")
        params.append(encounter.reason_for_visit)

    if (
        encounter.data_source_id is not None
        and (existing_data_source or 0) != encounter.data_source_id
    ):
        updates.append("data_source_id = ?")
        params.append(encounter.data_source_id)

    if (
        encounter.provider_id is not None
        and (existing_provider or 0) != encounter.provider_id
    ):
        updates.append("provider_id = ?")
        params.append(encounter.provider_id)

    if (
        encounter.organization_id is not None
        and (existing_org or 0) != encounter.organization_id
    ):
        updates.append("organization_id = ?")
        params.append(encounter.organization_id)

    if updates:
        params.append(encounter_db_id)
        _execute_update(cur, updates, params)


def _execute_update(
    cur: sqlite3.Cursor,
    updates: list[str],
    params: list[Any],
) -> None:
    """Execute the appropriate update query based on field count."""
    if len(updates) == 1:
        update_field = updates[0].split()[0]  # Extract field name from "field = ?"
        update_single_field(cur, "encounter", update_field, params[0], params[-1])
    else:
        query = f"UPDATE encounter SET {', '.join(updates)} WHERE id = ?"  # nosec B608
        cur.execute(query, params)


def _insert_encounter(cur: sqlite3.Cursor, encounter: EncounterData) -> None:
    """Insert a new encounter record."""
    cur.execute(
        """
        INSERT INTO encounter (
            patient_id,
            encounter_date,
            provider_id,
            organization_id,
            source_encounter_id,
            encounter_type,
            notes,
            reason_for_visit,
            data_source_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            encounter.patient_id,
            encounter.encounter_date,
            encounter.provider_id,
            encounter.organization_id,
            encounter.source_encounter_id,
            encounter.encounter_type,
            encounter.notes,
            encounter.reason_for_visit,
            encounter.data_source_id,
        ),
    )
