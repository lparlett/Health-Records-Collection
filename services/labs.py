# Purpose: Persist laboratory observations into the SQLite datastore.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Lab ingestion services."""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Sequence, Tuple

from services.common import clean_str, coerce_int
from services.encounters import find_encounter_id
from services.providers import get_or_create_provider

__all__ = ["insert_labs"]


def insert_labs(
    conn: sqlite3.Connection,
    patient_id: int,
    labs: Sequence[Mapping[str, object]],
) -> None:
    """Persist lab results and link them to encounters and providers.

    Args:
        conn: Active SQLite connection.
        patient_id: Identifier for the patient owning the results.
        labs: Sequence of parsed lab observations.
    """
    columns = [
        "patient_id",
        "encounter_id",
        "loinc_code",
        "test_name",
        "result_value",
        "unit",
        "reference_range",
        "abnormal_flag",
        "date",
        "ordering_provider_id",
        "performing_org_id",
        "data_source_id",
    ]

    def build_row(result: Mapping[str, object]) -> Tuple[Any, ...]:
        ordering_provider_name = clean_str(result.get("ordering_provider"))
        performing_org_name = clean_str(result.get("performing_org"))
        ordering_provider_id = (
            get_or_create_provider(conn, ordering_provider_name)
            if ordering_provider_name
            else None
        )
        performing_org_id = (
            get_or_create_provider(conn, performing_org_name, entity_type="organization")
            if performing_org_name
            else None
        )
        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=clean_str(result.get("encounter_start")) or clean_str(result.get("date")),
            provider_name=ordering_provider_name,
            provider_id=ordering_provider_id,
            source_encounter_id=clean_str(result.get("encounter_source_id")),
        )
        if encounter_id is None:
            encounter_id = find_encounter_id(
                conn,
                patient_id,
                encounter_date=clean_str(result.get("encounter_end")) or clean_str(result.get("date")),
                provider_name=performing_org_name,
                provider_id=performing_org_id,
                source_encounter_id=clean_str(result.get("encounter_source_id")),
            )
        ds_id = coerce_int(result.get("data_source_id"))
        return (
            patient_id,
            encounter_id,
            clean_str(result.get("loinc")),
            clean_str(result.get("test_name")),
            clean_str(result.get("value")),
            clean_str(result.get("unit")),
            clean_str(result.get("reference_range")),
            clean_str(result.get("abnormal_flag")),
            clean_str(result.get("date")),
            ordering_provider_id,
            performing_org_id,
            ds_id,
        )

    normalized_labs = [dict(lab) for lab in labs]

    def _key(date_value: Any, encounter_value: Any, loinc_value: Any) -> tuple[Any, Any, Any]:
        return (
            clean_str(date_value),
            coerce_int(encounter_value),
            clean_str(loinc_value),
        )

    existing_keys_query = """
        SELECT date, encounter_id, loinc_code
          FROM lab_result
         WHERE patient_id = ?
    """
    existing_keys = {
        _key(row[0], row[1], row[2])
        for row in conn.execute(existing_keys_query, (patient_id,))
    }

    rows_to_insert: list[Tuple[Any, ...]] = []
    pending_keys: set[tuple[Any, Any, Any]] = set()

    for lab_entry in normalized_labs:
        row = build_row(lab_entry)
        unique_key = _key(row[8], row[1], row[2])
        if unique_key in existing_keys or unique_key in pending_keys:
            continue
        pending_keys.add(unique_key)
        rows_to_insert.append(row)

    if not rows_to_insert:
        return

    placeholders = ", ".join(["?"] * len(columns))
    sql = f"INSERT INTO lab_result ({', '.join(columns)}) VALUES ({placeholders})"
    cur = conn.cursor()
    cur.executemany(sql, rows_to_insert)
    conn.commit()
