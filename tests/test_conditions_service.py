from __future__ import annotations
import sqlite3

from health_records_collection.services.conditions import insert_conditions
from health_records_collection.tests import helpers


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Condition", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestConditionsService(helpers.SchemaTestCase):
    """Test suite for conditions service."""

    def test_insert_conditions_sets_data_source(self) -> None:
        """Test that insert_conditions properly sets the data_source_id."""
        patient_id = _seed_patient(self.schema_conn)
        insert_conditions(
            self.schema_conn,
            patient_id,
            [
                {
                    "name": "Hypertension",
                    "start": "2024-01-01",
                    "status": "active",
                    "provider": "Example Clinician",
                    "data_source_id": self.data_source_id,
                }
            ],
        )

        row = self.schema_conn.execute(
            "SELECT data_source_id FROM condition WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], self.data_source_id)

    def test_insert_conditions_updates_existing_data_source(self) -> None:
        """Test that insert_conditions updates existing condition data sources."""
        patient_id = _seed_patient(self.schema_conn)

        new_source = self.schema_conn.execute(
            """
            INSERT INTO data_source (original_filename, ingested_at, file_sha256)
            VALUES (?, ?, ?)
            """,
            ("condition.xml", "2025-10-12T00:00:03Z", "hash-cond"),
        ).lastrowid
        self.schema_conn.commit()

        payload = {
            "name": "Hypertension",
            "start": "2024-01-01",
            "status": "active",
            "provider": "Example Clinician",
            "data_source_id": self.data_source_id,
        }
        count = self.schema_conn.execute("SELECT COUNT(*) FROM data_source").fetchone()
        self.assertIsNotNone(count)
        self.assertGreaterEqual(count[0], 1)

        insert_conditions(self.schema_conn, patient_id, [payload])

        payload["data_source_id"] = new_source
        insert_conditions(self.schema_conn, patient_id, [payload])

        row = self.schema_conn.execute(
            "SELECT data_source_id FROM condition WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], new_source)
