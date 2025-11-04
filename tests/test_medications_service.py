from __future__ import annotations

import sqlite3
import unittest

import pytest

from health_records_collection.services.medications import insert_medications


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Medication", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestMedicationsService(unittest.TestCase):
    """Test suite for medications service."""

    @pytest.mark.usefixtures("schema_conn")
    def test_insert_medications_sets_data_source(
        self,
        schema_conn: sqlite3.Connection,
        data_source_id: int,
    ) -> None:
        """Test that insert_medications sets data_source_id."""
        patient_id = _seed_patient(schema_conn)
        duplicates = insert_medications(
            schema_conn,
            patient_id,
            [
                {
                    "name": "Lisinopril",
                    "dose": "10 mg",
                    "route": "oral",
                    "frequency": "daily",
                    "start": "2024-01-01",
                    "status": "active",
                    "data_source_id": data_source_id,
                }
            ],
        )
        self.assertEqual(duplicates, 0)
        row = schema_conn.execute(
            "SELECT data_source_id FROM medication WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertEqual(row, (data_source_id,))

    @pytest.mark.usefixtures("schema_conn")
    def test_insert_medications_updates_existing(
        self,
        schema_conn: sqlite3.Connection,
        data_source_id: int,
    ) -> None:
        """Test that insert_medications updates existing records."""
        patient_id = _seed_patient(schema_conn)
        new_source = schema_conn.execute(
            """
            INSERT INTO data_source (original_filename, ingested_at, file_sha256)
            VALUES (?, ?, ?)
            """,
            ("medication.xml", "2025-10-12T00:00:05Z", "hash-med"),
        ).lastrowid
        schema_conn.commit()

        payload = {
            "name": "Lisinopril",
            "dose": "10 mg",
            "route": "oral",
            "frequency": "daily",
            "start": "2024-01-01",
            "status": "active",
            "data_source_id": None,
        }
        insert_medications(schema_conn, patient_id, [payload])

        payload["data_source_id"] = new_source
        duplicates = insert_medications(schema_conn, patient_id, [payload])
        self.assertEqual(duplicates, 1)

        row = schema_conn.execute(
            """
            SELECT data_source_id
              FROM medication
             WHERE patient_id = ?
               AND name = ?
            """,
            (patient_id, "Lisinopril"),
        ).fetchone()
        self.assertEqual(row, (new_source,))
