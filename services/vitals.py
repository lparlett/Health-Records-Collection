"""Vital sign ingestion services."""
from __future__ import annotations

import sqlite3
from typing import Iterable, List, Optional

from db.utils import insert_records
from services.encounters import find_encounter_id

__all__ = ["insert_vitals"]


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    return " ".join(cleaned.split())


def _normalise_type(vital_type: Optional[str], code: Optional[str]) -> Optional[str]:
    label = _clean(vital_type)
    if label:
        return label
    return _clean(code)


def _filter_items(vitals: Iterable[dict]) -> List[dict]:
    filtered: List[dict] = []
    for vital in vitals:
        if _clean(vital.get("value")) is None:
            continue
        filtered.append(vital)
    return filtered


def insert_vitals(conn: sqlite3.Connection, patient_id: int, vitals: List[dict]) -> None:
    """Persist parsed vital signs into the database."""
    vitals = _filter_items(vitals)
    if not vitals:
        return

    columns = [
        "patient_id",
        "encounter_id",
        "vital_type",
        "value",
        "unit",
        "date",
    ]

    def build_row(vital: dict) -> tuple[object, ...]:
        measurement_date = (
            _clean(vital.get("date"))
            or _clean(vital.get("encounter_start"))
            or _clean(vital.get("encounter_end"))
        )
        provider_name = _clean(vital.get("provider"))
        encounter_source_id = _clean(vital.get("encounter_source_id"))
        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=measurement_date,
            provider_name=provider_name,
            source_encounter_id=encounter_source_id,
        )
        if encounter_id is None and vital.get("encounter_end"):
            fallback_date = _clean(vital.get("encounter_end"))
            if fallback_date and fallback_date != measurement_date:
                encounter_id = find_encounter_id(
                    conn,
                    patient_id,
                    encounter_date=fallback_date,
                    provider_name=provider_name,
                    source_encounter_id=encounter_source_id,
                )

        return (
            patient_id,
            encounter_id,
            _normalise_type(vital.get("vital_type"), vital.get("code")),
            _clean(vital.get("value")),
            _clean(vital.get("unit")),
            measurement_date,
        )

    insert_records(conn, "vital", columns, vitals, build_row)
