"""Condition ingestion services."""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from services.encounters import find_encounter_id
from services.providers import get_or_create_provider


__all__ = ["insert_conditions"]


def insert_conditions(conn: sqlite3.Connection, patient_id: int, conditions: List[dict]) -> None:
    """Upsert condition/problem list entries and codes linked to providers and encounters."""
    if not conditions:
        return
    cur = conn.cursor()
    for cond in conditions:
        provider_name = cond.get("provider")
        provider_id: Optional[int] = None
        if provider_name:
            provider_id = get_or_create_provider(conn, provider_name)
        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=(
                cond.get("encounter_start")
                or cond.get("start")
                or cond.get("author_time")
            ),
            provider_name=provider_name,
            provider_id=provider_id,
            source_encounter_id=cond.get("encounter_source_id"),
        )

        if encounter_id is None and cond.get("encounter_end"):
            encounter_id = find_encounter_id(
                conn,
                patient_id,
                encounter_date=cond.get("encounter_end"),
                provider_name=provider_name,
                provider_id=provider_id,
                source_encounter_id=cond.get("encounter_source_id"),
            )

        codes = cond.get("codes") or []
        primary_code = codes[0] if codes else {}
        code_value = (primary_code.get("code") or "").strip() or None
        code_system = (primary_code.get("system") or "").strip() or None
        code_display = (primary_code.get("display") or "").strip() or None

        name = (cond.get("name") or code_display or code_value or "").strip()
        if not name:
            continue

        onset_date = cond.get("start") or None
        status = cond.get("status") or None
        notes = cond.get("notes") or None

        existing = cur.execute(
            """
            SELECT id, status, notes, provider_id, encounter_id
              FROM condition
             WHERE patient_id = ?
               AND COALESCE(name, '') = COALESCE(?, '')
               AND COALESCE(code, '') = COALESCE(?, '')
               AND COALESCE(onset_date, '') = COALESCE(?, '')
            """,
            (patient_id, name, code_value or '', onset_date or ''),
        ).fetchone()

        if existing:
            (
                condition_id,
                existing_status,
                existing_notes,
                existing_provider_id,
                existing_encounter_id,
            ) = existing
            updates: List[str] = []
            params: List[Optional[str]] = []
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
                    code_display
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )
            condition_id = cur.lastrowid

        for code in codes:
            code_val = (code.get("code") or "").strip()
            if not code_val:
                continue
            code_system_val = (code.get("system") or "").strip()
            display_val = (code.get("display") or "").strip() or None
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
