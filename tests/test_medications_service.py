from __future__ import annotations
import sqlite3

from health_records_collection.services.medications import insert_medications
from health_records_collection.tests import helpers


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Medication", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestMedicationsService(helpers.SchemaTestCase):
    """Test suite for medications service."""

    def test_insert_medications_sets_data_source(self) -> None:
        """Test that insert_medications sets data_source_id."""
        patient_id = _seed_patient(self.schema_conn)
        duplicates = insert_medications(
            self.schema_conn,
            patient_id,
            [
                {
                    "name": "Lisinopril",
                    "dose": "10 mg",
                    "route": "oral",
                    "frequency": "daily",
                    "start": "2024-01-01",
                    "status": "active",
                    "data_source_id": self.data_source_id,
                }
            ],
        )
        self.assertEqual(duplicates, 0)
        row = self.schema_conn.execute(
            "SELECT data_source_id FROM medication WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertEqual(row, (self.data_source_id,))

    def test_insert_medications_updates_existing(self) -> None:
        """Test that insert_medications updates existing records."""
        patient_id = _seed_patient(self.schema_conn)
        new_source = self.schema_conn.execute(
            """
            INSERT INTO data_source (original_filename, ingested_at, file_sha256)
            VALUES (?, ?, ?)
            """,
            ("medication.xml", "2025-10-12T00:00:05Z", "hash-med"),
        ).lastrowid
        self.schema_conn.commit()

        payload = {
            "name": "Lisinopril",
            "dose": "10 mg",
            "route": "oral",
            "frequency": "daily",
            "start": "2024-01-01",
            "status": "active",
            "data_source_id": None,
        }
        insert_medications(self.schema_conn, patient_id, [payload])

        payload["data_source_id"] = new_source
        duplicates = insert_medications(self.schema_conn, patient_id, [payload])
        self.assertEqual(duplicates, 1)

        row = self.schema_conn.execute(
            """
            SELECT data_source_id
              FROM medication
             WHERE patient_id = ?
               AND name = ?
            """,
            (patient_id, "Lisinopril"),
        ).fetchone()
        self.assertEqual(row, (new_source,))
