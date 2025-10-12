from __future__ import annotations

from services.providers import get_or_create_provider
from services.vitals import insert_vitals


def test_insert_vitals_links_to_existing_encounter(schema_conn, data_source_id):
    schema_conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Test", "Patient"),
    )
    patient_id = int(
        schema_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    )

    provider_id = get_or_create_provider(schema_conn, "Example Clinic")
    schema_conn.execute(
        """
        INSERT INTO encounter (
            patient_id,
            encounter_date,
            provider_id,
            source_encounter_id,
            encounter_type,
            notes,
            data_source_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            patient_id,
            "20240101120000",
            provider_id,
            "ENC-1",
            "Office visit",
            None,
            data_source_id,
        ),
    )
    schema_conn.commit()

    vital_payload = [
        {
            "code": "8302-2",
            "vital_type": "Body height",
            "value": "170",
            "unit": "cm",
            "status": "completed",
            "date": "20240101120000",
            "encounter_start": "20240101120000",
            "encounter_end": None,
            "encounter_source_id": "ENC-1",
            "provider": "Example Clinic",
            "data_source_id": data_source_id,
        }
    ]

    insert_vitals(schema_conn, patient_id, vital_payload)

    count = schema_conn.execute("SELECT COUNT(*) FROM vital").fetchone()[0]
    assert count == 1

    row = schema_conn.execute(
        "SELECT vital_type, value, unit, date, encounter_id, data_source_id FROM vital"
    ).fetchone()

    assert row == ("Body height", "170", "cm", "20240101120000", 1, data_source_id)
