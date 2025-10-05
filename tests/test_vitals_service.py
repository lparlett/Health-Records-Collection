import sqlite3
from pathlib import Path

from services.providers import get_or_create_provider
from services.vitals import insert_vitals


def _setup_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON;")
    schema_sql = Path("schema.sql").read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    return conn


def test_insert_vitals_links_to_existing_encounter():
    conn = _setup_connection()
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Test", "Patient"),
    )
    patient_id = cur.lastrowid

    provider_id = get_or_create_provider(conn, "Example Clinic")
    cur.execute(
        """
        INSERT INTO encounter (
            patient_id,
            encounter_date,
            provider_id,
            source_encounter_id,
            encounter_type,
            notes
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            patient_id,
            "20240101120000",
            provider_id,
            "ENC-1",
            "Office visit",
            None,
        ),
    )
    conn.commit()

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
        }
    ]

    insert_vitals(conn, patient_id, vital_payload)

    count = conn.execute("SELECT COUNT(*) FROM vital").fetchone()[0]
    assert count == 1

    row = conn.execute(
        "SELECT vital_type, value, unit, date, encounter_id FROM vital"
    ).fetchone()

    assert row == ("Body height", "170", "cm", "20240101120000", 1)
