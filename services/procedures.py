# Purpose: Persist procedure records and associated codes in the SQLite datastore.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Procedure ingestion services."""

from __future__ import annotations

import sqlite3
from typing import Mapping, Sequence, TypedDict

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

__all__ = ["insert_procedures"]


def _extract_procedure_fields(
    conn: sqlite3.Connection, proc: Mapping[str, object]
) -> ProcedureData:
    """Extract and clean procedure fields from raw data.

    Args:
        conn: Active SQLite connection.
        proc: Raw procedure mapping.

    Returns:
        ProcedureData: Type-safe procedure data dictionary.
    """
    provider_name = clean_str(proc.get("provider"))
    provider_id = (
        get_or_create_provider(conn, provider_name) if provider_name else None
    )

    # Extract primary code info
    raw_codes = proc.get("codes")
    codes: list[Mapping[str, object]] = []
    if isinstance(raw_codes, Sequence) and not isinstance(raw_codes, (str, bytes)):
        codes = list(ensure_mapping_sequence(raw_codes))
    primary = codes[0] if codes else {}

    code_value = clean_str(primary.get("code"))
    code_system = clean_str(primary.get("system"))
    code_display = clean_str(primary.get("display"))

    name = clean_str(proc.get("name")) or code_display or code_value
    status = clean_str(proc.get("status"))
    date = clean_str(proc.get("date")) or clean_str(proc.get("author_time"))
    notes = clean_str(proc.get("notes"))
    ds_id = coerce_int(proc.get("data_source_id"))

    return ProcedureData(
        name=name,
        code_value=code_value,
        code_system=code_system,
        code_display=code_display,
        status=status,
        date=date,
        notes=notes,
        ds_id=ds_id,
        provider_id=provider_id,
    )


def _resolve_encounter(
    conn: sqlite3.Connection,
    patient_id: int,
    proc_data: ProcedureData,
    provider_name: str | None,
) -> int | None:
    """Resolve encounter ID from procedure data.

    Args:
        conn: Active SQLite connection.
        patient_id: Patient identifier.
        proc_data: Extracted procedure data.
        provider_name: Provider name for lookup.

    Returns:
        int | None: Encounter ID if found, None otherwise.
    """
    lookup = EncounterLookup(
        patient_id=patient_id,
        encounter_date=proc_data.get("date"),
        provider_name=provider_name,
        provider_id=proc_data.get("provider_id"),
    )
    return find_encounter_id(conn, lookup)


def _find_existing_procedure(
    cur: sqlite3.Cursor,
    patient_id: int,
    name: str | None,
    code_value: str | None,
    date: str | None,
) -> tuple[int, str | None, str | None, int | None, int | None, int | None] | None:
    """Find existing procedure matching key fields.

    Args:
        cur: Database cursor.
        patient_id: Patient identifier.
        name: Procedure name.
        code_value: Procedure code.
        date: Procedure date.

    Returns:
        Tuple with procedure details if found, None otherwise.
    """
    return cur.execute(
        """
        SELECT id, status, notes, provider_id, encounter_id, data_source_id
          FROM procedure
         WHERE patient_id = ?
           AND COALESCE(name, '') = COALESCE(?, '')
           AND COALESCE(code, '') = COALESCE(?, '')
           AND COALESCE(date, '') = COALESCE(?, '')
        """,
        (patient_id, name or "", code_value or "", date or ""),
    ).fetchone()


def _build_procedure_updates(
    proc_data: ProcedureData,
    existing: tuple[int, str | None, str | None, int | None, int | None, int | None],
) -> tuple[list[str], list[object]]:
    """Build UPDATE query components for changed fields.

    Args:
        proc_data: New procedure data.
        existing: Existing procedure record tuple.

    Returns:
        Tuple[list[str], list[object]]: (update_clauses, params)
    """
    (
        _,
        existing_status,
        existing_notes,
        existing_provider_id,
        existing_encounter_id,
        existing_data_source,
    ) = existing

    updates: list[str] = []
    params: list[object] = []

    status = proc_data.get("status")
    if status and (existing_status or "") != status:
        updates.append("status = ?")
        params.append(status)

    notes = proc_data.get("notes")
    if notes and (existing_notes or "") != notes:
        updates.append("notes = ?")
        params.append(notes)

    provider_id = proc_data.get("provider_id")
    if provider_id and (existing_provider_id or 0) != provider_id:
        updates.append("provider_id = ?")
        params.append(provider_id)

    encounter_id = proc_data.get("encounter_id")
    if encounter_id and (existing_encounter_id or 0) != encounter_id:
        updates.append("encounter_id = ?")
        params.append(encounter_id)

    ds_id = proc_data.get("ds_id")
    if ds_id is not None and (existing_data_source or 0) != ds_id:
        updates.append("data_source_id = ?")
        params.append(ds_id)

    return (updates, params)


def _execute_procedure_update(
    cur: sqlite3.Cursor,
    updates: list[str],
    params: list[object],
    procedure_id: int,
) -> bool:
    """Execute UPDATE query for procedure record.

    Args:
        cur: Database cursor.
        updates: List of update clauses.
        params: List of parameter values.
        procedure_id: Procedure ID to update.

    Returns:
        bool: True if updates were applied.
    """
    if not updates:
        return False

    if len(updates) == 1:
        update_field = updates[0].split()[0]
        update_single_field(cur, "procedure", update_field, params[0], procedure_id)
    else:
        query = f"UPDATE procedure SET {', '.join(updates)} WHERE id = ?" # nosec B608
        cur.execute(query, params + [procedure_id])

    return True


def _insert_procedure_record(
    cur: sqlite3.Cursor,
    patient_id: int,
    proc_data: ProcedureData,
    encounter_id: int | None,
) -> int:
    """Insert new procedure record.

    Args:
        cur: Database cursor.
        patient_id: Patient identifier.
        proc_data: Extracted procedure data.
        encounter_id: Associated encounter ID.

    Returns:
        int: ID of inserted procedure record.
    """
    cur.execute(
        """
        INSERT INTO procedure (
            patient_id,
            encounter_id,
            provider_id,
            name,
            code,
            code_system,
            code_display,
            status,
            date,
            notes,
            data_source_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            patient_id,
            encounter_id,
            proc_data.get("provider_id"),
            proc_data.get("name"),
            proc_data.get("code_value"),
            proc_data.get("code_system"),
            proc_data.get("code_display"),
            proc_data.get("status"),
            proc_data.get("date"),
            proc_data.get("notes"),
            proc_data.get("ds_id"),
        ),
    )
    return int(cur.lastrowid or 0)


def _insert_procedure_codes(
    cur: sqlite3.Cursor,
    procedure_id: int,
    codes: Sequence[Mapping[str, object]],
) -> None:
    """Insert procedure code entries.

    Args:
        cur: Database cursor.
        procedure_id: ID of procedure record.
        codes: Sequence of code mappings.
    """
    for code in codes:
        code_val = clean_str(code.get("code"))
        if not code_val:
            continue
        code_system_val = clean_str(code.get("system"))
        display_val = clean_str(code.get("display"))
        cur.execute(
            """
            INSERT OR IGNORE INTO procedure_code (
                procedure_id,
                code,
                code_system,
                display_name
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                procedure_id,
                code_val,
                code_system_val,
                display_val,
            ),
        )


class ProcedureData(TypedDict, total=False):
    """Type-safe procedure data dictionary."""

    name: str | None
    code_value: str | None
    code_system: str | None
    code_display: str | None
    status: str | None
    date: str | None
    notes: str | None
    ds_id: int | None
    provider_id: int | None
    encounter_id: int | None


def insert_procedures(
    conn: sqlite3.Connection,
    patient_id: int,
    procedures: Sequence[Mapping[str, object]],
) -> None:
    """Persist clinical procedures with provider, encounter, and code metadata.

    Args:
        conn: Active SQLite connection.
        patient_id: Identifier for the patient receiving the procedures.
        procedures: Sequence of parsed procedure entries.
    """
    if not procedures:
        return

    cur = conn.cursor()
    for proc in procedures:
        # Extract and clean procedure fields
        proc_data = _extract_procedure_fields(conn, proc)

        # Skip if no meaningful name
        if not proc_data.get("name"):
            continue

        # Get provider name for encounter lookup
        provider_name = clean_str(proc.get("provider"))

        # Resolve encounter ID
        encounter_id = _resolve_encounter(
            conn, patient_id, proc_data, provider_name
        )
        proc_data["encounter_id"] = encounter_id

        # Check for existing procedure
        existing = _find_existing_procedure(
            cur,
            patient_id,
            proc_data.get("name"),
            proc_data.get("code_value"),
            proc_data.get("date"),
        )

        if existing:
            # Update existing record
            updates, params = _build_procedure_updates(proc_data, existing)
            procedure_id = existing[0]
            _execute_procedure_update(cur, updates, params, procedure_id)
        else:
            # Insert new record
            procedure_id = _insert_procedure_record(
                cur, patient_id, proc_data, encounter_id
            )

        # Extract codes and insert them
        raw_codes = proc.get("codes")
        codes: list[Mapping[str, object]] = []
        if isinstance(raw_codes, Sequence) and not isinstance(raw_codes, (str, bytes)):
            codes = list(ensure_mapping_sequence(raw_codes))

        _insert_procedure_codes(cur, procedure_id, codes)

    conn.commit()
