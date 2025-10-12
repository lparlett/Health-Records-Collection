# Purpose: Persist medication administrations into the SQLite database.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Medication ingestion services."""

from __future__ import annotations

import sqlite3
from typing import Mapping, Sequence

from services.common import clean_str, coerce_int
from services.encounters import find_encounter_id

__all__ = ["insert_medications"]


def insert_medications(
    conn: sqlite3.Connection,
    patient_id: int,
    meds: Sequence[Mapping[str, object]],
) -> int:
    """Store medication administrations and align them with encounters.

    Args:
        conn: Active SQLite connection.
        patient_id: Identifier for the patient owning the administrations.
        meds: Collection of parsed medication entries.

    Returns:
        int: Number of duplicate entries detected during insertion.
    """
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
        "data_source_id",
    ]
    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT INTO medication ({', '.join(columns)}) VALUES ({placeholders})"

    cur = conn.cursor()
    duplicates = 0
    for med in meds:
        notes = clean_str(med.get("notes"))
        rxnorm = clean_str(med.get("rxnorm"))
        if rxnorm:
            if notes:
                notes = f"{notes} (RxNorm: {rxnorm})"
            else:
                notes = f"RxNorm: {rxnorm}"

        encounter_date = (
            clean_str(med.get("start"))
            or clean_str(med.get("end"))
            or clean_str(med.get("author_time"))
        )
        provider_name = clean_str(med.get("provider"))
        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=encounter_date,
            provider_name=provider_name,
        )

        name = clean_str(med.get("name"))
        dose = clean_str(med.get("dose"))
        route = clean_str(med.get("route"))
        frequency = clean_str(med.get("frequency"))
        start_date = clean_str(med.get("start_bucket")) or clean_str(med.get("start"))
        end_date = clean_str(med.get("end_bucket")) or clean_str(med.get("end"))
        status = clean_str(med.get("status"))
        ds_id = coerce_int(med.get("data_source_id"))

        row = (
            patient_id,
            encounter_id,
            name,
            dose,
            route,
            frequency,
            start_date,
            end_date,
            status,
            notes,
            ds_id,
        )
        try:
            cur.execute(sql, row)
        except sqlite3.IntegrityError:
            duplicates += 1
            if ds_id is not None:
                cur.execute(
                    """
                    UPDATE medication
                       SET data_source_id = COALESCE(data_source_id, ?)
                     WHERE patient_id = ?
                       AND COALESCE(encounter_id, -1) = COALESCE(?, -1)
                       AND COALESCE(name, '') = COALESCE(?, '')
                       AND COALESCE(dose, '') = COALESCE(?, '')
                       AND COALESCE(start_date, '') = COALESCE(?, '')
                    """,
                    (
                        ds_id,
                        patient_id,
                        encounter_id,
                        name or "",
                        dose or "",
                        start_date or "",
                    ),
                )

    conn.commit()
    return duplicates
