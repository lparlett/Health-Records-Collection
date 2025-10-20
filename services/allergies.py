# Purpose: Persist allergy and intolerance records into the SQLite datastore.
# Author: Codex + Lauren
# Date: 2025-10-19
# Related tests: tests/test_allergies_service.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Allergy ingestion helpers."""

from __future__ import annotations

import sqlite3
from typing import Mapping, Sequence, Tuple

from services.common import clean_str, coerce_int, ensure_mapping_sequence
from services.encounters import find_encounter_id
from services.providers import get_or_create_provider

__all__ = ["insert_allergies"]


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
        substance, substance_code = _normalise_substance(entry)
        if not (substance or substance_code):
            continue

        status = clean_str(entry.get("status"))
        onset_date = clean_str(entry.get("onset"))
        severity = clean_str(entry.get("severity"))
        reaction = clean_str(entry.get("reaction"))
        reaction_code = clean_str(entry.get("reaction_code"))
        reaction_code_system = clean_str(entry.get("reaction_code_system"))
        notes = clean_str(entry.get("notes"))
        criticality = clean_str(entry.get("criticality"))
        noted_date = clean_str(entry.get("noted_date"))
        source_id = clean_str(entry.get("source_allergy_id"))

        provider_name = clean_str(entry.get("provider"))
        provider_id = get_or_create_provider(conn, provider_name) if provider_name else None

        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=clean_str(entry.get("encounter_start")) or onset_date,
            provider_name=provider_name,
            provider_id=provider_id,
            source_encounter_id=clean_str(entry.get("encounter_source_id")),
        )
        if encounter_id is None and clean_str(entry.get("encounter_end")):
            encounter_id = find_encounter_id(
                conn,
                patient_id,
                encounter_date=clean_str(entry.get("encounter_end")),
                provider_name=provider_name,
                provider_id=provider_id,
                source_encounter_id=clean_str(entry.get("encounter_source_id")),
            )

        ds_id = coerce_int(entry.get("data_source_id"))
        substance_system = clean_str(entry.get("substance_code_system"))
        substance_display = clean_str(entry.get("substance_code_display"))

        existing = cur.execute(
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
                substance_code or "",
                substance or "",
                onset_date or "",
                status or "",
            ),
        ).fetchone()

        payload = (
            patient_id,
            encounter_id,
            provider_id,
            substance,
            substance_code,
            substance_system,
            substance_display,
            reaction,
            reaction_code,
            reaction_code_system,
            severity,
            criticality,
            status,
            onset_date,
            noted_date,
            source_id,
            notes,
            ds_id,
        )

        if existing:
            (
                allergy_id,
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

            column_updates = [
                ("severity", severity, existing_severity),
                ("reaction", reaction, existing_reaction),
                ("notes", notes, existing_notes),
                ("criticality", criticality, existing_criticality),
                ("status", status, existing_status),
                ("noted_date", noted_date, existing_noted_date),
                ("source_allergy_id", source_id, existing_source_id),
            ]
            for column, new_value, old_value in column_updates:
                if new_value and (old_value or "") != new_value:
                    updates.append(f"{column} = ?")
                    params.append(new_value)

            coded_updates = [
                ("reaction_code", reaction_code, existing_reaction_code),
                ("reaction_code_system", reaction_code_system, existing_reaction_system),
            ]
            for column, new_value, old_value in coded_updates:
                if new_value and (old_value or "") != new_value:
                    updates.append(f"{column} = ?")
                    params.append(new_value)

            if provider_id and (existing_provider or 0) != provider_id:
                updates.append("provider_id = ?")
                params.append(provider_id)
            if encounter_id and (existing_encounter or 0) != encounter_id:
                updates.append("encounter_id = ?")
                params.append(encounter_id)
            if ds_id is not None and (existing_ds_id or 0) != ds_id:
                updates.append("data_source_id = ?")
                params.append(ds_id)

            if updates:
                params.append(allergy_id)
                cur.execute(
                    f"UPDATE allergy SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
                updated += 1
            continue

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

