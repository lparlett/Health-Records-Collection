# Purpose: Persist procedure records and associated codes in the SQLite datastore.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Procedure ingestion services."""

from __future__ import annotations

import sqlite3
from typing import Mapping, Sequence, TypedDict, cast

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
    provider_id = get_or_create_provider(conn, provider_name) if provider_name else None

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
    row = cur.execute(
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
    return cast(
        "tuple[int, str | None, str | None, int | None, int | None, int | None] | None",
        row,
    )


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
        encounter_id = _resolve_encounter(conn, patient_id, proc_data, provider_name)
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
            updates, params = build_updates_from_specs(
                proc_data,
                existing,
                STANDARD_RECORD_UPDATE_SPECS,
            )
            procedure_id = existing[0]
            execute_update(cur, "procedure", updates, params, procedure_id)
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

        insert_code_mappings(
            cur,
            table="procedure_code",
            ref_id=procedure_id,
            codes=codes,
        )

    conn.commit()
