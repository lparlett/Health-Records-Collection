# Purpose: Manage patient persistence in the project SQLite database.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Patient insertion service."""
from __future__ import annotations

import sqlite3
from typing import Mapping

from health_records_collection.services.common import clean_str, coerce_int

__all__ = ["insert_patient"]


def insert_patient(
    conn: sqlite3.Connection,
    patient: Mapping[str, object],
) -> int:
    """Insert or update a patient record.

    Args:
        conn: Open SQLite connection with active transaction control.
        patient: Mapping of patient attributes parsed from CCD input.

    Returns:
        int: Primary key for the patient row.
    """
    cur = conn.cursor()

    given = clean_str(patient.get("given")) or ""
    family = clean_str(patient.get("family")) or ""
    dob = clean_str(patient.get("dob")) or ""
    gender = clean_str(patient.get("gender")) or ""
    ds_id = coerce_int(patient.get("data_source_id"))

    cur.execute(
        """
        SELECT id, gender, data_source_id
          FROM patient
         WHERE COALESCE(given_name, '') = ?
           AND COALESCE(family_name, '') = ?
           AND COALESCE(birth_date, '') = ?
        """,
        (given, family, dob),
    )
    row = cur.fetchone()
    if row:
        patient_id, existing_gender, existing_data_source = row
        updates: list[str] = []
        params: list[object] = []
        if gender and (existing_gender or "") != gender:
            updates.append("gender = ?")
            params.append(gender)
        if ds_id is not None and existing_data_source != ds_id:
            updates.append("data_source_id = ?")
            params.append(ds_id)
        if updates:
            # Use specific UPDATE statements for each case to avoid SQL injection risks
            if len(updates) == 2:  # Both gender and data_source_id need updating
                cur.execute(
                    """
                    UPDATE patient 
                    SET gender = ?,
                        data_source_id = ?
                    WHERE id = ?
                    """,
                    params,
                )
            elif "gender = ?" in updates:
                cur.execute(
                    """
                    UPDATE patient 
                    SET gender = ?
                    WHERE id = ?
                    """,
                    [params[0], params[-1]],
                )
            else:  # data_source_id needs updating
                cur.execute(
                    """
                    UPDATE patient 
                    SET data_source_id = ?
                    WHERE id = ?
                    """,
                    [params[0], params[-1]],
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
            data_source_id
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            given or None,
            family or None,
            dob or None,
            gender or None,
            ds_id,
        ),
    )
    conn.commit()
    last_row_id = cur.lastrowid
    if last_row_id is None:
        raise sqlite3.DatabaseError("Failed to insert patient row; lastrowid is None.")
    return int(last_row_id)
