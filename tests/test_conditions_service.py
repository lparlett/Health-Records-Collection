from __future__ import annotations

import sqlite3
import unittest

import pytest

from health_records_collection.services.conditions import insert_conditions


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Condition", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestConditionsService(unittest.TestCase):
    """Test suite for conditions service."""

    @pytest.mark.usefixtures("schema_conn")
    def test_insert_conditions_sets_data_source(
        self,
        schema_conn: sqlite3.Connection,
        data_source_id: int,
    ) -> None:
        """Test that insert_conditions properly sets the data_source_id."""
        patient_id = _seed_patient(schema_conn)
        insert_conditions(
            schema_conn,
            patient_id,
            [
                {
                    "name": "Hypertension",
                    "start": "2024-01-01",
                    "status": "active",
                    "provider": "Example Clinician",
                    "data_source_id": data_source_id,
                }
            ],
        )

        row = schema_conn.execute(
            "SELECT data_source_id FROM condition WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], data_source_id)

    @pytest.mark.usefixtures("schema_conn")
    def test_insert_conditions_updates_existing_data_source(
        self,
        schema_conn: sqlite3.Connection,
        data_source_id: int,
    ) -> None:
        """Test that insert_conditions updates existing condition data sources."""
        patient_id = _seed_patient(schema_conn)

        new_source = schema_conn.execute(
            """
            INSERT INTO data_source (original_filename, ingested_at, file_sha256)
            VALUES (?, ?, ?)
            """,
            ("condition.xml", "2025-10-12T00:00:03Z", "hash-cond"),
        ).lastrowid
        schema_conn.commit()

        payload = {
            "name": "Hypertension",
            "start": "2024-01-01",
            "status": "active",
            "provider": "Example Clinician",
            "data_source_id": data_source_id,
        }
        count = schema_conn.execute("SELECT COUNT(*) FROM data_source").fetchone()
        self.assertIsNotNone(count)
        self.assertGreaterEqual(count[0], 1)

        insert_conditions(schema_conn, patient_id, [payload])

        payload["data_source_id"] = new_source
        insert_conditions(schema_conn, patient_id, [payload])

        row = schema_conn.execute(
            "SELECT data_source_id FROM condition WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], new_source)
