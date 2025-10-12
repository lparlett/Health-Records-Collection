# Purpose: Persist vital sign observations into the SQLite datastore.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_vitals_service.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Vital sign ingestion services."""

from __future__ import annotations

import sqlite3
from typing import Iterable, Mapping, Sequence

from db.utils import insert_records
from services.common import clean_str, coerce_int
from services.encounters import find_encounter_id

__all__ = ["insert_vitals"]


def _normalise_type(vital_type: object, code: object) -> str | None:
    """Prefer the explicit vital label, falling back to the code."""
    label = clean_str(vital_type)
    if label:
        return label
    return clean_str(code)


def _filter_items(vitals: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """Return vitals that include a non-empty value."""
    filtered: list[Mapping[str, object]] = []
    for vital in vitals:
        if clean_str(vital.get("value")) is None:
            continue
        filtered.append(vital)
    return filtered


def insert_vitals(
    conn: sqlite3.Connection,
    patient_id: int,
    vitals: Sequence[Mapping[str, object]],
) -> None:
    """Persist parsed vital signs into the database.

    Args:
        conn: Active SQLite connection.
        patient_id: Identifier for the patient owning the vital observation.
        vitals: Sequence of parsed vital dictionaries.
    """
    filtered = _filter_items(vitals)
    if not filtered:
        return

    columns = [
        "patient_id",
        "encounter_id",
        "vital_type",
        "value",
        "unit",
        "date",
        "data_source_id",
    ]

    def build_row(vital: Mapping[str, object]) -> tuple[object, ...]:
        measurement_date = (
            clean_str(vital.get("date"))
            or clean_str(vital.get("encounter_start"))
            or clean_str(vital.get("encounter_end"))
        )
        provider_name = clean_str(vital.get("provider"))
        encounter_source_id = clean_str(vital.get("encounter_source_id"))
        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=measurement_date,
            provider_name=provider_name,
            source_encounter_id=encounter_source_id,
        )
        if encounter_id is None:
            fallback_date = clean_str(vital.get("encounter_end"))
            if fallback_date and fallback_date != measurement_date:
                encounter_id = find_encounter_id(
                    conn,
                    patient_id,
                    encounter_date=fallback_date,
                    provider_name=provider_name,
                    source_encounter_id=encounter_source_id,
                )

        ds_id = coerce_int(vital.get("data_source_id"))

        return (
            patient_id,
            encounter_id,
            _normalise_type(vital.get("vital_type"), vital.get("code")),
            clean_str(vital.get("value")),
            clean_str(vital.get("unit")),
            measurement_date,
            ds_id,
        )

    insert_records(conn, "vital", columns, [dict(v) for v in filtered], build_row)
