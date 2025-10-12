# Purpose: Persist condition/problem list records in the SQLite datastore.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Condition ingestion services."""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Sequence

from services.common import clean_str, coerce_int, ensure_mapping_sequence
from services.encounters import find_encounter_id
from services.providers import get_or_create_provider

__all__ = ["insert_conditions"]


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
        provider_name = clean_str(cond.get("provider"))
        provider_id = get_or_create_provider(conn, provider_name) if provider_name else None

        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=clean_str(cond.get("encounter_start"))
            or clean_str(cond.get("start"))
            or clean_str(cond.get("author_time")),
            provider_name=provider_name,
            provider_id=provider_id,
            source_encounter_id=clean_str(cond.get("encounter_source_id")),
        )

        if encounter_id is None and cond.get("encounter_end"):
            encounter_id = find_encounter_id(
                conn,
                patient_id,
                encounter_date=clean_str(cond.get("encounter_end")),
                provider_name=provider_name,
                provider_id=provider_id,
                source_encounter_id=clean_str(cond.get("encounter_source_id")),
            )

        raw_codes = cond.get("codes")
        codes: list[Mapping[str, object]] = []
        if isinstance(raw_codes, Sequence) and not isinstance(raw_codes, (str, bytes)):
            codes = list(ensure_mapping_sequence(raw_codes))
        primary_code = codes[0] if codes else {}
        code_value = clean_str(primary_code.get("code"))
        code_system = clean_str(primary_code.get("system"))
        code_display = clean_str(primary_code.get("display"))

        name = clean_str(cond.get("name")) or code_display or code_value
        if not name:
            continue

        onset_date = clean_str(cond.get("start"))
        status = clean_str(cond.get("status"))
        notes = clean_str(cond.get("notes"))

        ds_id = coerce_int(cond.get("data_source_id"))

        existing = cur.execute(
            """
            SELECT id, status, notes, provider_id, encounter_id, data_source_id
              FROM condition
             WHERE patient_id = ?
               AND COALESCE(name, '') = COALESCE(?, '')
               AND COALESCE(code, '') = COALESCE(?, '')
               AND COALESCE(onset_date, '') = COALESCE(?, '')
            """,
            (patient_id, name or "", code_value or "", onset_date or ""),
        ).fetchone()

        if existing:
            (
                condition_id,
                existing_status,
                existing_notes,
                existing_provider_id,
                existing_encounter_id,
                existing_data_source,
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
            if ds_id is not None and (existing_data_source or 0) != ds_id:
                updates.append("data_source_id = ?")
                params.append(ds_id)
            if updates:
                params.append(condition_id)
                cur.execute(
                    f"UPDATE condition SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
        else:
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
                    patient_id,
                    name,
                    onset_date,
                    status,
                    notes,
                    provider_id,
                    encounter_id,
                    code_value,
                    code_system,
                    code_display,
                    ds_id,
                ),
            )
            condition_id = cur.lastrowid

        for code in codes:
            code_val = clean_str(code.get("code"))
            if not code_val:
                continue
            code_system_val = clean_str(code.get("system"))
            display_val = clean_str(code.get("display"))
            cur.execute(
                """
                INSERT OR IGNORE INTO condition_code (condition_id, code, code_system, display_name)
                VALUES (?, ?, ?, ?)
                """,
                (
                    condition_id,
                    code_val,
                    code_system_val,
                    display_val,
                ),
            )
    conn.commit()
