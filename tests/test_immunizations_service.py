from __future__ import annotations

from typing import Any, Dict, List

from services.immunizations import insert_immunizations


def _seed_patient(conn) -> int:
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Test", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_insert_immunizations_deduplicates_and_sets_provenance(
    schema_conn, data_source_id
) -> None:
    patient_id = _seed_patient(schema_conn)

    immunization_payload: List[Dict[str, Any]] = [
        {
            "vaccine_name": "Influenza vaccine",
            "date": "20240315",
            "cvx_codes": ["140", "140"],
            "lot_number": "LOT-ABC",
            "product_name": "Influenza Quadrivalent",
            "status": "completed",
            "data_source_id": data_source_id,
        },
        {
            "vaccine_name": "Influenza vaccine",
            "date": "20240315",
            "cvx_codes": ["140"],
            "lot_number": "LOT-ABC",
            "product_name": "Influenza Quadrivalent",
            "status": "completed",
            "data_source_id": data_source_id,
        },
        {
            "vaccine_name": "COVID-19 vaccine",
            "date": "20240210",
            "cvx_codes": ["91309"],
            "product_name": "COVID-19 Booster",
            "data_source_id": data_source_id,
        },
    ]

    insert_immunizations(schema_conn, patient_id, immunization_payload)
    insert_immunizations(schema_conn, patient_id, immunization_payload)  # idempotent check

    rows = list(
        schema_conn.execute(
            """
            SELECT vaccine_name, cvx_code, date_administered, lot_number, notes, data_source_id
              FROM immunization
             ORDER BY date_administered
            """
        )
    )

    assert len(rows) == 2

    flu_row = rows[1]
    assert flu_row[0] == "Influenza vaccine"
    assert flu_row[1] == "140"
    assert flu_row[2] == "20240315"
    assert flu_row[3] == "LOT-ABC"
    assert flu_row[4] == "Product: Influenza Quadrivalent"
    assert flu_row[5] == data_source_id

    covid_row = rows[0]
    assert covid_row[0] == "COVID-19 vaccine"
    assert covid_row[1] == "91309"
    assert covid_row[2] == "20240210"
    assert covid_row[3] is None
    assert covid_row[4] == "Product: COVID-19 Booster"
    assert covid_row[5] == data_source_id
