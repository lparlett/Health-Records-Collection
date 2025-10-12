# Purpose: Manage patient persistence in the project SQLite database.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Patient insertion service."""
from __future__ import annotations

import sqlite3
from typing import Mapping, Optional

from services.common import clean_str

__all__ = ["insert_patient"]


def insert_patient(
    conn: sqlite3.Connection,
    patient: Mapping[str, object],
    source_file: str,
) -> int:
    """Insert or update a patient record.

    Args:
        conn: Open SQLite connection with active transaction control.
        patient: Mapping of patient attributes parsed from CCD input.
        source_file: Artifact name that produced the patient information.

    Returns:
        int: Primary key for the patient row.
    """
    cur = conn.cursor()

    given = clean_str(patient.get("given")) or ""
    family = clean_str(patient.get("family")) or ""
    dob = clean_str(patient.get("dob")) or ""
    gender = clean_str(patient.get("gender")) or ""

    cur.execute(
        """
        SELECT id, gender, source_file
          FROM patient
         WHERE COALESCE(given_name, '') = ?
           AND COALESCE(family_name, '') = ?
           AND COALESCE(birth_date, '') = ?
        """,
        (given, family, dob),
    )
    row = cur.fetchone()
    if row:
        patient_id, existing_gender, existing_source = row
        updates: list[str] = []
        params: list[Optional[str]] = []
        if gender and (existing_gender or "") != gender:
            updates.append("gender = ?")
            params.append(gender)
        if source_file and (existing_source or "") != source_file:
            updates.append("source_file = ?")
            params.append(source_file)
        if updates:
            params.append(patient_id)
            cur.execute(
                f"UPDATE patient SET {', '.join(updates)} WHERE id = ?",
                params,
            )
            conn.commit()
        return patient_id

    cur.execute(
        """
        INSERT INTO patient (
            given_name,
            family_name,
            birth_date,
            gender,
            source_file
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            given or None,
            family or None,
            dob or None,
            gender or None,
            source_file,
        ),
    )
    conn.commit()
    last_row_id = cur.lastrowid
    if last_row_id is None:
        raise sqlite3.DatabaseError("Failed to insert patient row; lastrowid is None.")
    return int(last_row_id)
