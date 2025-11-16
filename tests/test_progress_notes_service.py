from __future__ import annotations
import sqlite3

from health_records_collection.services.progress_notes import insert_progress_notes
from health_records_collection.tests import helpers


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Note", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestProgressNotesService(helpers.SchemaTestCase):
    """Test suite for progress notes service."""

    def test_insert_progress_notes_sets_data_source(self) -> None:
        """Test that insert_progress_notes sets data_source_id."""
        patient_id = _seed_patient(self.schema_conn)
        inserted, duplicates = insert_progress_notes(
            self.schema_conn,
            patient_id,
            [
                {
                    "title": "Progress Note",
                    "note_datetime": "2024-03-10T10:00:00",
                    "text": "Patient is recovering as expected.",
                    "provider": "Example Clinician",
                    "data_source_id": self.data_source_id,
                }
            ],
        )
        self.assertEqual(inserted, 1)
        self.assertEqual(duplicates, 0)

        row = self.schema_conn.execute(
            "SELECT data_source_id FROM progress_note WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertEqual(row, (self.data_source_id,))

    def test_insert_progress_notes_updates_duplicate_data_source(self) -> None:
        """Test that insert_progress_notes updates duplicate data source."""
        patient_id = _seed_patient(self.schema_conn)
        new_source = self.schema_conn.execute(
            """
            INSERT INTO data_source (original_filename, ingested_at, file_sha256)
            VALUES (?, ?, ?)
            """,
            ("note.xml", "2025-10-12T00:00:06Z", "hash-note"),
        ).lastrowid
        self.schema_conn.commit()

        payload = {
            "title": "Progress Note",
            "note_datetime": "2024-03-10T10:00:00",
            "text": "Patient is recovering as expected.",
            "provider": "Example Clinician",
            "data_source_id": None,
        }
        insert_progress_notes(self.schema_conn, patient_id, [payload])

        payload["data_source_id"] = new_source
        inserted, duplicates = insert_progress_notes(
            self.schema_conn, patient_id, [payload]
        )
        self.assertEqual(inserted, 0)
        self.assertEqual(duplicates, 1)

        row = self.schema_conn.execute(
            "SELECT data_source_id FROM progress_note WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertEqual(row, (new_source,))
