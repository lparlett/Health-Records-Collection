"""Encounter services: lookup and ingestion helpers."""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from services.providers import get_or_create_provider

__all__ = ["find_encounter_id", "insert_encounters"]


def _date_only(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    digits = ''.join(ch for ch in value if ch.isdigit())
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
    """Resolve an encounter row for downstream usage based on identifiers."""
    if provider_id is None and provider_name:
        provider_id = get_or_create_provider(conn, provider_name)
    cur = conn.cursor()

    def fetch(sql: str, params: tuple[Any, ...]) -> Optional[int]:
        row = cur.execute(sql, params).fetchone()
        if row:
            return row[0]
        return None

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

    encounter_day = _date_only(encounter_date)

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


def insert_encounters(conn: sqlite3.Connection, patient_id: int, encounters: list[dict]) -> None:
    """Upsert encounter metadata, merging new details when duplicates appear."""
    if not encounters:
        return
    cur = conn.cursor()
    for enc in encounters:
        provider_name = enc.get("provider")
        provider_id = None
        if provider_name:
            provider_id = get_or_create_provider(conn, provider_name)

        encounter_date = enc.get("start") or enc.get("end")
        source_encounter_id = enc.get("source_id")
        encounter_type = enc.get("type")
        notes = enc.get("notes")
        if not notes:
            fallback_parts = [
                enc.get("location"),
                enc.get("status"),
                enc.get("mood"),
                enc.get("code"),
            ]
            fallback = " | ".join(part for part in fallback_parts if part)
            notes = fallback or None
        if not (encounter_date or source_encounter_id):
            continue

        existing = cur.execute(
            """
            SELECT id, encounter_type, notes
              FROM encounter
             WHERE patient_id = ?
               AND COALESCE(encounter_date, '') = COALESCE(?, '')
               AND COALESCE(provider_id, -1) = COALESCE(?, -1)
               AND COALESCE(source_encounter_id, '') = COALESCE(?, '')
            """,
            (patient_id, encounter_date, provider_id, source_encounter_id),
        ).fetchone()

        if existing:
            encounter_db_id, existing_type, existing_notes = existing
            updates: list[str] = []
            params: list[Any] = []
            if encounter_type and (existing_type or "") != encounter_type:
                updates.append("encounter_type = ?")
                params.append(encounter_type)
            if notes and (existing_notes or "") != notes:
                updates.append("notes = ?")
                params.append(notes)
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
                notes
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id,
                encounter_date,
                provider_id,
                source_encounter_id,
                encounter_type,
                notes,
            ),
        )
    conn.commit()
