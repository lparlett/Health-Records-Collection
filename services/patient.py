"""Patient insertion service."""
from __future__ import annotations

from typing import Optional

import sqlite3

__all__ = ["insert_patient"]


def insert_patient(conn: sqlite3.Connection, patient: dict, source_file: str) -> int:
    """Insert or update a patient record, returning the database ID."""
    cur = conn.cursor()

    given_raw = patient.get("given") or ""
    family_raw = patient.get("family") or ""
    dob_raw = patient.get("dob") or ""
    gender_raw = patient.get("gender") or ""

    given = given_raw.strip()
    family = family_raw.strip()
    dob = dob_raw.strip()
    gender = gender_raw.strip()

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
    return cur.lastrowid
