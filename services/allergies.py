# Purpose: Persist allergy and intolerance records into the SQLite datastore.
# Author: Codex + Lauren
# Date: 2025-10-19
# Related tests: tests/test_allergies_service.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Allergy ingestion helpers."""

from __future__ import annotations

import sqlite3
from typing import Mapping, Sequence, Tuple, TypedDict

from health_records_collection.db.utils import update_single_field
from health_records_collection.services.common import (
    clean_str,
    coerce_int,
    ensure_mapping_sequence,
)
from health_records_collection.services.encounters import (
    EncounterLookup,
    find_encounter_id,
)
from health_records_collection.services.providers import get_or_create_provider

__all__ = ["insert_allergies"]


class AllergyData(TypedDict, total=False):
    """Type-safe allergy field dictionary."""

    substance: str | None
    substance_code: str | None
    substance_system: str | None
    substance_display: str | None
    status: str | None
    onset_date: str | None
    severity: str | None
    reaction: str | None
    reaction_code: str | None
    reaction_code_system: str | None
    notes: str | None
    criticality: str | None
    noted_date: str | None
    source_id: str | None
    provider_name: str | None
    ds_id: int | None
    patient_id: int
    encounter_id: int | None
    provider_id: int | None


def _normalise_substance(entry: Mapping[str, object]) -> tuple[str | None, str | None]:
    """Return the preferred substance display value and code."""
    substance = clean_str(
        entry.get("substance")
        or entry.get("substance_code_display")
        or entry.get("substance_code")
    )
    substance_code = clean_str(entry.get("substance_code"))
    if not substance and substance_code:
        substance = substance_code
    return (substance, substance_code)


def _extract_allergy_fields(entry: Mapping[str, object]) -> AllergyData:
    """Extract and clean all allergy fields from an entry."""
    substance, substance_code = _normalise_substance(entry)

    return {
        "substance": substance,
        "substance_code": substance_code,
        "status": clean_str(entry.get("status")),
        "onset_date": clean_str(entry.get("onset")),
        "severity": clean_str(entry.get("severity")),
        "reaction": clean_str(entry.get("reaction")),
        "reaction_code": clean_str(entry.get("reaction_code")),
        "reaction_code_system": clean_str(entry.get("reaction_code_system")),
        "notes": clean_str(entry.get("notes")),
        "criticality": clean_str(entry.get("criticality")),
        "noted_date": clean_str(entry.get("noted_date")),
        "source_id": clean_str(entry.get("source_allergy_id")),
        "provider_name": clean_str(entry.get("provider")),
        "ds_id": coerce_int(entry.get("data_source_id")),
        "substance_system": clean_str(entry.get("substance_code_system")),
        "substance_display": clean_str(entry.get("substance_code_display")),
    }  # type: ignore


def _resolve_encounter(
    conn: sqlite3.Connection,
    patient_id: int,
    allergy_data: AllergyData,
    encounter_start: str | None,
    encounter_end: str | None,
) -> int | None:
    """Resolve encounter ID with fallback logic."""
    provider_name = allergy_data.get("provider_name")
    provider_id = allergy_data.get("provider_id")
    onset_date = allergy_data.get("onset_date")

    # Try encounter start date or onset date
    lookup = EncounterLookup(
        patient_id=patient_id,
        encounter_date=encounter_start or onset_date,
        provider_name=provider_name,
        provider_id=provider_id,
    )
    encounter_id = find_encounter_id(conn, lookup)

    # Fall back to encounter end date if needed
    if encounter_id is None and encounter_end:
        lookup = EncounterLookup(
            patient_id=patient_id,
            encounter_date=encounter_end,
            provider_name=provider_name,
            provider_id=provider_id,
        )
        encounter_id = find_encounter_id(conn, lookup)

    return encounter_id


def _build_allergy_payload(allergy_data: AllergyData) -> tuple:
    """Build the payload tuple for insert or update."""
    return (
        allergy_data.get("patient_id"),
        allergy_data.get("encounter_id"),
        allergy_data.get("provider_id"),
        allergy_data.get("substance"),
        allergy_data.get("substance_code"),
        allergy_data.get("substance_system"),
        allergy_data.get("substance_display"),
        allergy_data.get("reaction"),
        allergy_data.get("reaction_code"),
        allergy_data.get("reaction_code_system"),
        allergy_data.get("severity"),
        allergy_data.get("criticality"),
        allergy_data.get("status"),
        allergy_data.get("onset_date"),
        allergy_data.get("noted_date"),
        allergy_data.get("source_id"),
        allergy_data.get("notes"),
        allergy_data.get("ds_id"),
    )


def _find_existing_allergy(
    cur: sqlite3.Cursor,
    patient_id: int,
    allergy_data: AllergyData,
) -> tuple | None:
    """Find existing allergy record in database."""
    return cur.execute(
        """
        SELECT
            id,
            severity,
            reaction,
            notes,
            provider_id,
            encounter_id,
            data_source_id,
            reaction_code,
            reaction_code_system,
            criticality,
            status,
            noted_date,
            source_allergy_id
          FROM allergy
         WHERE patient_id = ?
           AND COALESCE(substance_code, '') = COALESCE(?, '')
           AND COALESCE(substance, '') = COALESCE(?, '')
           AND COALESCE(onset_date, '') = COALESCE(?, '')
           AND COALESCE(status, '') = COALESCE(?, '')
        """,
        (
            patient_id,
            allergy_data.get("substance_code") or "",
            allergy_data.get("substance") or "",
            allergy_data.get("onset_date") or "",
            allergy_data.get("status") or "",
        ),
    ).fetchone()


def _build_update_queries(
    allergy_data: AllergyData,
    existing: tuple,
) -> tuple[list[str], list[object]]:
    """Build update SQL and parameters for changed fields."""
    (
        _,
        existing_severity,
        existing_reaction,
        existing_notes,
        existing_provider,
        existing_encounter,
        existing_ds_id,
        existing_reaction_code,
        existing_reaction_system,
        existing_criticality,
        existing_status,
        existing_noted_date,
        existing_source_id,
    ) = existing

    updates: list[str] = []
    params: list[object] = []

    # Simple field updates
    column_updates = [
        ("severity", allergy_data.get("severity"), existing_severity),
        ("reaction", allergy_data.get("reaction"), existing_reaction),
        ("notes", allergy_data.get("notes"), existing_notes),
        (
            "criticality",
            allergy_data.get("criticality"),
            existing_criticality,
        ),
        ("status", allergy_data.get("status"), existing_status),
        ("noted_date", allergy_data.get("noted_date"), existing_noted_date),
        ("source_allergy_id", allergy_data.get("source_id"), existing_source_id),
    ]
    for column, new_value, old_value in column_updates:
        if new_value and (old_value or "") != new_value:
            updates.append(f"{column} = ?")
            params.append(new_value)

    # Coded field updates
    coded_updates = [
        (
            "reaction_code",
            allergy_data.get("reaction_code"),
            existing_reaction_code,
        ),
        (
            "reaction_code_system",
            allergy_data.get("reaction_code_system"),
            existing_reaction_system,
        ),
    ]
    for column, new_value, old_value in coded_updates:
        if new_value and (old_value or "") != new_value:
            updates.append(f"{column} = ?")
            params.append(new_value)

    # ID field updates
    provider_id = allergy_data.get("provider_id")
    if provider_id and (existing_provider or 0) != provider_id:
        updates.append("provider_id = ?")
        params.append(provider_id)

    encounter_id = allergy_data.get("encounter_id")
    if encounter_id and (existing_encounter or 0) != encounter_id:
        updates.append("encounter_id = ?")
        params.append(encounter_id)

    ds_id = allergy_data.get("ds_id")
    if ds_id is not None and (existing_ds_id or 0) != ds_id:
        updates.append("data_source_id = ?")
        params.append(ds_id)

    return updates, params


def _execute_allergy_update(
    cur: sqlite3.Cursor,
    updates: list[str],
    params: list[object],
    allergy_id: int,
) -> bool:
    """Execute update query for changed fields. Returns True if updated."""
    if not updates:
        return False

    # Single field update
    if len(updates) == 1:
        update_field = updates[0].split()[0]
        update_single_field(cur, "allergy", update_field, params[0], allergy_id)
    # Multiple fields update
    else:
        query = f"UPDATE allergy SET {', '.join(updates)} WHERE id = ?"  # nosec B608
        cur.execute(query, params + [allergy_id])

    return True


def insert_allergies(
    conn: sqlite3.Connection,
    patient_id: int,
    allergies: Sequence[Mapping[str, object]],
) -> Tuple[int, int]:
    """Insert or update allergy observations for a patient.

    Args:
        conn: Active SQLite connection.
        patient_id: Identifier for the owning patient.
        allergies: Parsed allergy dictionaries.

    Returns:
        Tuple[int, int]: (inserted_count, updated_count)
    """
    mapping_iter = list(ensure_mapping_sequence(allergies))
    if not mapping_iter:
        return (0, 0)

    inserted = 0
    updated = 0
    cur = conn.cursor()

    for entry in mapping_iter:
        # Extract all fields into a type-safe dict
        allergy_data: AllergyData = _extract_allergy_fields(entry)

        if not (allergy_data.get("substance") or allergy_data.get("substance_code")):
            continue

        # Enrich with patient context
        allergy_data["patient_id"] = patient_id  # type: ignore

        # Resolve provider
        provider_name = allergy_data.get("provider_name")
        if provider_name:
            prov_id = get_or_create_provider(conn, provider_name)
            allergy_data["provider_id"] = prov_id  # type: ignore

        # Resolve encounter with fallback
        encounter_id = _resolve_encounter(
            conn,
            patient_id,
            allergy_data,
            clean_str(entry.get("encounter_start")),
            clean_str(entry.get("encounter_end")),
        )
        if encounter_id:
            allergy_data["encounter_id"] = encounter_id  # type: ignore

        # Build payload tuple
        payload = _build_allergy_payload(allergy_data)

        # Find existing record
        existing = _find_existing_allergy(
            cur,
            patient_id,
            allergy_data,
        )

        if existing:
            # Build updates for changed fields
            updates, params = _build_update_queries(allergy_data, existing)

            allergy_id = existing[0]
            if _execute_allergy_update(cur, updates, params, allergy_id):
                updated += 1
            continue

        # Insert new record
        cur.execute(
            """
            INSERT INTO allergy (
                patient_id,
                encounter_id,
                provider_id,
                substance,
                substance_code,
                substance_code_system,
                substance_code_display,
                reaction,
                reaction_code,
                reaction_code_system,
                severity,
                criticality,
                status,
                onset_date,
                noted_date,
                source_allergy_id,
                notes,
                data_source_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        inserted += 1

    conn.commit()
    return (inserted, updated)
