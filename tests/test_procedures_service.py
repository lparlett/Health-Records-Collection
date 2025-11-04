from __future__ import annotations

import sqlite3
import unittest

import pytest

from health_records_collection.services.procedures import insert_procedures


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Procedure", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestProceduresService(unittest.TestCase):
    """Test suite for procedures service."""

    @pytest.mark.usefixtures("schema_conn")
    def test_insert_procedures_sets_data_source(
        self,
        schema_conn: sqlite3.Connection,
        data_source_id: int,
    ) -> None:
        """Test that insert_procedures sets data_source_id."""
        patient_id = _seed_patient(schema_conn)

        insert_procedures(
            schema_conn,
            patient_id,
            [
                {
                    "name": "Appendectomy",
                    "date": "20240401",
                    "status": "completed",
                    "codes": [{"code": "44950", "system": "CPT"}],
                    "provider": "Example Surgeon",
                    "data_source_id": data_source_id,
                }
            ],
        )

        row = schema_conn.execute(
            "SELECT data_source_id FROM procedure WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertEqual(row, (data_source_id,))

    @pytest.mark.usefixtures("schema_conn")
    def test_insert_procedures_updates_duplicate_data_source(
        self,
        schema_conn: sqlite3.Connection,
        data_source_id: int,
    ) -> None:
        """Test that insert_procedures updates duplicate data source."""
        patient_id = _seed_patient(schema_conn)
        new_source = schema_conn.execute(
            """
            INSERT INTO data_source (original_filename, ingested_at, file_sha256)
            VALUES (?, ?, ?)
            """,
            ("procedure.xml", "2025-10-12T00:00:04Z", "hash-proc"),
        ).lastrowid
        schema_conn.commit()

        payload = {
            "name": "Appendectomy",
            "date": "20240401",
            "status": "completed",
            "codes": [{"code": "44950", "system": "CPT"}],
            "provider": "Example Surgeon",
            "data_source_id": data_source_id,
        }
        insert_procedures(schema_conn, patient_id, [payload])

        payload["data_source_id"] = new_source
        insert_procedures(schema_conn, patient_id, [payload])

        row = schema_conn.execute(
            "SELECT data_source_id FROM procedure WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertEqual(row, (new_source,))
