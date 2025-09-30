"""Lab ingestion services."""
from __future__ import annotations

import sqlite3
from typing import List

from db.utils import insert_records
from services.encounters import find_encounter_id
from services.providers import get_or_create_provider

__all__ = ["insert_labs"]


def insert_labs(conn: sqlite3.Connection, patient_id: int, labs: List[dict]) -> None:
    """Persist lab results and link them to encounters and providers when able."""
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
    ]

    def build_row(result: dict) -> tuple:
        ordering_provider_name = result.get("ordering_provider")
        performing_org_name = result.get("performing_org")
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
            encounter_date=result.get("encounter_start") or result.get("date"),
            provider_name=ordering_provider_name,
            provider_id=ordering_provider_id,
            source_encounter_id=result.get("encounter_source_id"),
        )
        if encounter_id is None:
            encounter_id = find_encounter_id(
                conn,
                patient_id,
                encounter_date=result.get("encounter_end") or result.get("date"),
                provider_name=performing_org_name,
                provider_id=performing_org_id,
                source_encounter_id=result.get("encounter_source_id"),
            )
        return (
            patient_id,
            encounter_id,
            result.get("loinc"),
            result.get("test_name"),
            result.get("value"),
            result.get("unit"),
            result.get("reference_range"),
            result.get("abnormal_flag"),
            result.get("date"),
            ordering_provider_id,
            performing_org_id,
        )

    insert_records(conn, "lab_result", columns, labs, build_row)
