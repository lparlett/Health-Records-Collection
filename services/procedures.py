"""Procedure ingestion services."""
from __future__ import annotations

import sqlite3
from typing import List, Optional

from services.encounters import find_encounter_id
from services.providers import get_or_create_provider

__all__ = ["insert_procedures"]


def insert_procedures(conn: sqlite3.Connection, patient_id: int, procedures: List[dict]) -> None:
    """Persist clinical procedures with provider, encounter, and multi-code metadata."""
    if not procedures:
        return
    cur = conn.cursor()
    for proc in procedures:
        provider_name = proc.get("provider")
        provider_id: Optional[int] = None
        if provider_name:
            provider_id = get_or_create_provider(conn, provider_name)
        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=proc.get("date") or proc.get("author_time"),
            provider_name=provider_name,
            provider_id=provider_id,
            source_encounter_id=proc.get("encounter_source_id"),
        )
        codes = proc.get("codes") or []
        primary = codes[0] if codes else {}
        code_value = (primary.get("code") or "").strip() or None
        code_system = (primary.get("system") or "").strip() or None
        code_display = (primary.get("display") or "").strip() or None
        name = (proc.get("name") or code_display or code_value or "").strip()
        if not name:
            continue
        status = proc.get("status") or None
        date = proc.get("date") or proc.get("author_time") or None
        notes = proc.get("notes") or None

        existing = cur.execute(
            """
            SELECT id, status, notes, provider_id, encounter_id
              FROM procedure
             WHERE patient_id = ?
               AND COALESCE(name, '') = COALESCE(?, '')
               AND COALESCE(code, '') = COALESCE(?, '')
               AND COALESCE(date, '') = COALESCE(?, '')
            """,
            (patient_id, name, code_value or '', date or ''),
        ).fetchone()

        if existing:
            (
                procedure_id,
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
            code_val = (code.get("code") or "").strip()
            if not code_val:
                continue
            code_system_val = (code.get("system") or "").strip() or None
            display_val = (code.get("display") or "").strip() or None
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
