# Purpose: Persist procedure records and associated codes in the SQLite datastore.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Procedure ingestion services."""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Sequence

from services.common import clean_str, ensure_mapping_sequence
from services.encounters import find_encounter_id
from services.providers import get_or_create_provider

__all__ = ["insert_procedures"]


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
        provider_name = clean_str(proc.get("provider"))
        provider_id = get_or_create_provider(conn, provider_name) if provider_name else None

        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=clean_str(proc.get("date")) or clean_str(proc.get("author_time")),
            provider_name=provider_name,
            provider_id=provider_id,
            source_encounter_id=clean_str(proc.get("encounter_source_id")),
        )

        raw_codes = proc.get("codes")
        codes: list[Mapping[str, object]] = []
        if isinstance(raw_codes, Sequence) and not isinstance(raw_codes, (str, bytes)):
            codes = list(ensure_mapping_sequence(raw_codes))
        primary = codes[0] if codes else {}
        code_value = clean_str(primary.get("code"))
        code_system = clean_str(primary.get("system"))
        code_display = clean_str(primary.get("display"))
        name = clean_str(proc.get("name")) or code_display or code_value
        if not name:
            continue

        status = clean_str(proc.get("status"))
        date = clean_str(proc.get("date")) or clean_str(proc.get("author_time"))
        notes = clean_str(proc.get("notes"))

        existing = cur.execute(
            """
            SELECT id, status, notes, provider_id, encounter_id
              FROM procedure
             WHERE patient_id = ?
               AND COALESCE(name, '') = COALESCE(?, '')
               AND COALESCE(code, '') = COALESCE(?, '')
               AND COALESCE(date, '') = COALESCE(?, '')
            """,
            (patient_id, name or "", code_value or "", date or ""),
        ).fetchone()

        if existing:
            (
                procedure_id,
                existing_status,
                existing_notes,
                existing_provider_id,
                existing_encounter_id,
            ) = existing
            updates: list[str] = []
            params: list[Any] = []
            if status and (existing_status or "") != status:
                updates.append("status = ?")
                params.append(status)
            if notes and (existing_notes or "") != notes:
                updates.append("notes = ?")
                params.append(notes)
            if provider_id and (existing_provider_id or 0) != provider_id:
                updates.append("provider_id = ?")
                params.append(provider_id)
            if encounter_id and (existing_encounter_id or 0) != encounter_id:
                updates.append("encounter_id = ?")
                params.append(encounter_id)
            if updates:
                params.append(procedure_id)
                cur.execute(
                    f"UPDATE procedure SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
        else:
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
                    notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_id,
                    encounter_id,
                    provider_id,
                    name,
                    code_value,
                    code_system,
                    code_display,
                    status,
                    date,
                    notes,
                ),
            )
            procedure_id = cur.lastrowid

        for code in codes:
            code_val = clean_str(code.get("code"))
            if not code_val:
                continue
            code_system_val = clean_str(code.get("system"))
            display_val = clean_str(code.get("display"))
            cur.execute(
                """
                INSERT OR IGNORE INTO procedure_code (procedure_id, code, code_system, display_name)
                VALUES (?, ?, ?, ?)
                """,
                (
                    procedure_id,
                    code_val,
                    code_system_val,
                    display_val,
                ),
            )
    conn.commit()
