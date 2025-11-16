from __future__ import annotations
import sqlite3

from health_records_collection.services.encounters import insert_encounters
from health_records_collection.tests import helpers


def _insert_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        """
        INSERT INTO patient (
            given_name,
            family_name
        ) VALUES (?, ?)
        """,
        ("Test", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestEncountersService(helpers.SchemaTestCase):
    """Test suite for encounters service."""

    def test_insert_encounters_persists_data_source(self) -> None:
        """Test that insert_encounters persists data_source_id."""
        patient_id = _insert_patient(self.schema_conn)

        insert_encounters(
            self.schema_conn,
            patient_id,
            [
                {
                    "start": "20240102",
                    "source_id": "enc-1",
                    "type": "AMB",
                    "notes": "Initial visit",
                    "provider": "Example Clinic",
                    "data_source_id": self.data_source_id,
                }
            ],
        )

        row = self.schema_conn.execute(
            "SELECT data_source_id FROM encounter WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertEqual(row, (self.data_source_id,))

    def test_insert_encounters_updates_duplicate_provenance(self) -> None:
        """Test that insert_encounters updates duplicate provenance."""
        patient_id = _insert_patient(self.schema_conn)
        new_source = self.schema_conn.execute(
            """
            INSERT INTO data_source (original_filename, ingested_at, file_sha256)
            VALUES (?, ?, ?)
            """,
            ("encounter-2.xml", "2025-10-12T00:00:02Z", "hash-enc-2"),
        ).lastrowid
        self.schema_conn.commit()

        payload = {
            "start": "20240102",
            "source_id": "enc-dup",
            "type": "AMB",
            "provider": "Example Clinic",
            "data_source_id": self.data_source_id,
        }
        insert_encounters(self.schema_conn, patient_id, [payload])

        payload["data_source_id"] = new_source
        insert_encounters(self.schema_conn, patient_id, [payload])

        row = self.schema_conn.execute(
            """
            SELECT data_source_id
              FROM encounter
             WHERE patient_id = ?
               AND source_encounter_id = ?
            """,
            (patient_id, "enc-dup"),
        ).fetchone()
        self.assertEqual(row, (new_source,))
