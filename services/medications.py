"""Medication ingestion services."""
from __future__ import annotations

import sqlite3
from typing import List

from services.encounters import find_encounter_id

__all__ = ["insert_medications"]


def insert_medications(conn: sqlite3.Connection, patient_id: int, meds: List[dict]) -> int:
    """Store medication administrations and align them with encounters based on timing."""
    if not meds:
        return 0

    columns = [
        "patient_id",
        "encounter_id",
        "name",
        "dose",
        "route",
        "frequency",
        "start_date",
        "end_date",
        "status",
        "notes",
    ]
    placeholders = ', '.join(['?'] * len(columns))
    sql = f"INSERT INTO medication ({', '.join(columns)}) VALUES ({placeholders})"

    cur = conn.cursor()
    duplicates = 0
    for med in meds:
        notes = med.get("notes")
        rxnorm = med.get("rxnorm")
        if rxnorm:
            if notes:
                notes = f"{notes} (RxNorm: {rxnorm})"
            else:
                notes = f"RxNorm: {rxnorm}"

        encounter_date = med.get("start") or med.get("end") or med.get("author_time")
        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=encounter_date,
            provider_name=med.get("provider"),
        )

        row = (
            patient_id,
            encounter_id,
            med.get("name"),
            med.get("dose"),
            med.get("route"),
            med.get("frequency"),
            med.get("start_bucket") or med.get("start"),
            med.get("end_bucket") or med.get("end"),
            med.get("status"),
            notes,
        )
        try:
            cur.execute(sql, row)
        except sqlite3.IntegrityError:
            duplicates += 1

    conn.commit()
    return duplicates
