# Purpose: Provide encounter lookup and persistence helpers for the SQLite datastore.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Encounter services: lookup and ingestion helpers."""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Optional, Sequence

from services.common import clean_str, coerce_int
from services.providers import get_or_create_provider

__all__ = ["find_encounter_id", "insert_encounters"]


def _date_only(value: Optional[str]) -> Optional[str]:
    """Return the YYYYMMDD component of a date string if present."""
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) >= 8:
        return digits[:8]
    return None


def find_encounter_id(
    conn: sqlite3.Connection,
    patient_id: int,
    encounter_date: Optional[str] = None,
    provider_name: Optional[str] = None,
    *,
    provider_id: Optional[int] = None,
    source_encounter_id: Optional[str] = None,
) -> Optional[int]:
    """Resolve an encounter row based on temporal and provider hints.

    Args:
        conn: Active SQLite connection.
        patient_id: Patient identifier.
        encounter_date: Date or timestamp from the source document.
        provider_name: Provider display name.
        provider_id: Optional existing provider identifier.
        source_encounter_id: Source-system encounter identifier.

    Returns:
        Optional[int]: Matching encounter primary key if one is found.
    """
    normalized_provider_name = clean_str(provider_name)
    if provider_id is None and normalized_provider_name:
        provider_id = get_or_create_provider(conn, normalized_provider_name)
    cur = conn.cursor()

    def fetch(sql: str, params: tuple[Any, ...]) -> Optional[int]:
        row = cur.execute(sql, params).fetchone()
        return row[0] if row else None

    def run_query(base_sql: str, base_params: list[Any], order_clause: str) -> Optional[int]:
        if provider_id is not None:
            params_with_provider = tuple(base_params + [provider_id])
            sql_with_provider = (
                base_sql
                + " AND COALESCE(provider_id, -1) = COALESCE(?, -1)"
                + order_clause
            )
            match = fetch(sql_with_provider, params_with_provider)
            if match is not None:
                return match
        return fetch(base_sql + order_clause, tuple(base_params))

    encounter_day = _date_only(encounter_date or "")

    if source_encounter_id:
        params: list[Any] = [patient_id, source_encounter_id]
        base_sql = (
            """
            SELECT id
              FROM encounter
             WHERE patient_id = ?
               AND COALESCE(source_encounter_id, '') = COALESCE(?, '')
            """
        )
        if encounter_date:
            base_sql += " AND COALESCE(encounter_date, '') = COALESCE(?, '')"
            params.append(encounter_date)
        match = run_query(base_sql, params, " ORDER BY encounter_date DESC, id DESC LIMIT 1")
        if match is not None:
            return match
        if encounter_day:
            params = [patient_id, source_encounter_id, encounter_day]
            base_sql = (
                """
                SELECT id
                  FROM encounter
                 WHERE patient_id = ?
                   AND COALESCE(source_encounter_id, '') = COALESCE(?, '')
                   AND substr(COALESCE(encounter_date, ''), 1, 8) = ?
                """
            )
            match = run_query(
                base_sql,
                params,
                " ORDER BY encounter_date DESC, id DESC LIMIT 1",
            )
            if match is not None:
                return match

    if encounter_date:
        params = [patient_id, encounter_date]
        base_sql = (
            """
            SELECT id
              FROM encounter
             WHERE patient_id = ?
               AND COALESCE(encounter_date, '') = COALESCE(?, '')
            """
        )
        match = run_query(base_sql, params, " ORDER BY id DESC LIMIT 1")
        if match is not None:
            return match

    if encounter_day:
        params = [patient_id, encounter_day]
        base_sql = (
            """
            SELECT id
              FROM encounter
             WHERE patient_id = ?
               AND substr(COALESCE(encounter_date, ''), 1, 8) = ?
            """
        )
        match = run_query(
            base_sql,
            params,
            " ORDER BY encounter_date DESC, id DESC LIMIT 1",
        )
        if match is not None:
            return match

    if provider_id is not None:
        base_sql = (
            """
            SELECT id
              FROM encounter
             WHERE patient_id = ?
            """
        )
        return run_query(base_sql, [patient_id], " ORDER BY encounter_date DESC, id DESC LIMIT 1")

    return None


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
        provider_name = clean_str(enc.get("provider"))
        provider_id = get_or_create_provider(conn, provider_name) if provider_name else None

        encounter_date = clean_str(enc.get("start")) or clean_str(enc.get("end"))
        source_encounter_id = clean_str(enc.get("source_id"))
        encounter_type = clean_str(enc.get("type"))
        reason_for_visit = clean_str(enc.get("reason_for_visit"))
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
        if not (encounter_date or source_encounter_id):
            continue

        ds_id = coerce_int(enc.get("data_source_id"))

        existing = cur.execute(
            """
            SELECT id, encounter_type, notes, reason_for_visit, data_source_id
              FROM encounter
             WHERE patient_id = ?
               AND COALESCE(encounter_date, '') = COALESCE(?, '')
               AND COALESCE(provider_id, -1) = COALESCE(?, -1)
               AND COALESCE(source_encounter_id, '') = COALESCE(?, '')
            """,
            (patient_id, encounter_date, provider_id, source_encounter_id),
        ).fetchone()

        if existing:
            (
                encounter_db_id,
                existing_type,
                existing_notes,
                existing_reason,
                existing_data_source,
            ) = existing
            updates: list[str] = []
            params: list[Any] = []
            if encounter_type and (existing_type or "") != encounter_type:
                updates.append("encounter_type = ?")
                params.append(encounter_type)
            if notes and (existing_notes or "") != notes:
                updates.append("notes = ?")
                params.append(notes)
            if reason_for_visit and (existing_reason or "") != reason_for_visit:
                updates.append("reason_for_visit = ?")
                params.append(reason_for_visit)
            if ds_id is not None and (existing_data_source or 0) != ds_id:
                updates.append("data_source_id = ?")
                params.append(ds_id)
            if updates:
                params.append(encounter_db_id)
                cur.execute(
                    "UPDATE encounter SET " + ", ".join(updates) + " WHERE id = ?",
                    params,
                )
            continue

        cur.execute(
            """
            INSERT INTO encounter (
                patient_id,
                encounter_date,
                provider_id,
                source_encounter_id,
                encounter_type,
                notes,
                reason_for_visit,
                data_source_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id,
                encounter_date,
                provider_id,
                source_encounter_id,
                encounter_type,
                notes,
                reason_for_visit,
                ds_id,
            ),
        )
    conn.commit()
