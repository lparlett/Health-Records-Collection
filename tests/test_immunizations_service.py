import sqlite3
from pathlib import Path
from typing import Any, Dict, List

from services.immunizations import insert_immunizations


def _setup_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    schema_sql = Path("schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    return conn


def test_insert_immunizations_deduplicates_and_formats() -> None:
    conn = _setup_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Test", "Patient"),
    )
    patient_id = cur.lastrowid
    assert isinstance(patient_id, int)

    immunization_payload: List[Dict[str, Any]] = [
        {
            "vaccine_name": "Influenza vaccine",
            "date": "20240315",
            "cvx_codes": ["140", "140"],
            "lot_number": "LOT-ABC",
            "product_name": "Influenza Quadrivalent",
            "status": "completed",
        },
        {
            "vaccine_name": "Influenza vaccine",
            "date": "20240315",
            "cvx_codes": ["140"],
            "lot_number": "LOT-ABC",
            "product_name": "Influenza Quadrivalent",
            "status": "completed",
        },
        {
            "vaccine_name": "COVID-19 vaccine",
            "date": "20240210",
            "cvx_codes": ["91309"],
            "product_name": "COVID-19 Booster",
        },
    ]

    insert_immunizations(conn, patient_id, immunization_payload)
    insert_immunizations(conn, patient_id, immunization_payload)  # idempotent check

    rows = list(
        conn.execute(
            "SELECT vaccine_name, cvx_code, date_administered, lot_number, notes FROM immunization ORDER BY date_administered"
        )
    )

    assert len(rows) == 2

    flu_row = rows[1]
    assert flu_row[0] == "Influenza vaccine"
    assert flu_row[1] == "140"
    assert flu_row[2] == "20240315"
    assert flu_row[3] == "LOT-ABC"
    assert flu_row[4] == "Product: Influenza Quadrivalent"

    covid_row = rows[0]
    assert covid_row[0] == "COVID-19 vaccine"
    assert covid_row[1] == "91309"
    assert covid_row[2] == "20240210"
    assert covid_row[3] is None
    assert covid_row[4] == "Product: COVID-19 Booster"
