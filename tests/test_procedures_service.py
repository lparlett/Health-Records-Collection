from __future__ import annotations
import sqlite3

from health_records_collection.services.procedures import insert_procedures
from health_records_collection.tests import helpers


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Procedure", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestProceduresService(helpers.SchemaTestCase):
    """Test suite for procedures service."""

    def test_insert_procedures_sets_data_source(self) -> None:
        """Test that insert_procedures sets data_source_id."""
        patient_id = _seed_patient(self.schema_conn)

        insert_procedures(
            self.schema_conn,
            patient_id,
            [
                {
                    "name": "Appendectomy",
                    "date": "20240401",
                    "status": "completed",
                    "codes": [{"code": "44950", "system": "CPT"}],
                    "provider": "Example Surgeon",
                    "data_source_id": self.data_source_id,
                }
            ],
        )

        row = self.schema_conn.execute(
            "SELECT data_source_id FROM procedure WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertEqual(row, (self.data_source_id,))

    def test_insert_procedures_updates_duplicate_data_source(self) -> None:
        """Test that insert_procedures updates duplicate data source."""
        patient_id = _seed_patient(self.schema_conn)
        new_source = self.schema_conn.execute(
            """
            INSERT INTO data_source (original_filename, ingested_at, file_sha256)
            VALUES (?, ?, ?)
            """,
            ("procedure.xml", "2025-10-12T00:00:04Z", "hash-proc"),
        ).lastrowid
        self.schema_conn.commit()

        payload = {
            "name": "Appendectomy",
            "date": "20240401",
            "status": "completed",
            "codes": [{"code": "44950", "system": "CPT"}],
            "provider": "Example Surgeon",
            "data_source_id": self.data_source_id,
        }
        insert_procedures(self.schema_conn, patient_id, [payload])

        payload["data_source_id"] = new_source
        insert_procedures(self.schema_conn, patient_id, [payload])

        row = self.schema_conn.execute(
            "SELECT data_source_id FROM procedure WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertEqual(row, (new_source,))
