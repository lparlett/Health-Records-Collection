from __future__ import annotations

import sqlite3
import unittest

import pytest

from health_records_collection.services.patient import insert_patient


class TestPatientService(unittest.TestCase):
    """Test suite for patient service."""

    @pytest.mark.usefixtures("schema_conn")
    def test_insert_patient_records_data_source(
        self,
        schema_conn: sqlite3.Connection,
        data_source_id: int,
    ) -> None:
        """Test that insert_patient records data_source_id."""
        payload = {
            "given": "Ada",
            "family": "Lovelace",
            "dob": "1815-12-10",
            "gender": "female",
            "data_source_id": data_source_id,
        }

        patient_id = insert_patient(schema_conn, payload)
        row = schema_conn.execute(
            "SELECT given_name, family_name, data_source_id FROM patient WHERE id = ?",
            (patient_id,),
        ).fetchone()

        self.assertEqual(row, ("Ada", "Lovelace", data_source_id))

    @pytest.mark.usefixtures("schema_conn")
    def test_insert_patient_updates_existing_data_source(
        self,
        schema_conn: sqlite3.Connection,
        data_source_id: int,
    ) -> None:
        """Test that insert_patient updates existing data source."""
        other_data_source = schema_conn.execute(
            """
            INSERT INTO data_source (original_filename, ingested_at, file_sha256)
            VALUES (?, ?, ?)
            """,
            ("other.xml", "2025-10-12T00:00:01Z", "hash-other"),
        ).lastrowid
        schema_conn.commit()

        payload = {
            "given": "Alan",
            "family": "Turing",
            "dob": "1912-06-23",
            "gender": "male",
            "data_source_id": data_source_id,
        }
        patient_id = insert_patient(schema_conn, payload)

        # Re-ingest with updated provenance
        payload["data_source_id"] = other_data_source
        insert_patient(schema_conn, payload)

        row = schema_conn.execute(
            "SELECT data_source_id FROM patient WHERE id = ?",
            (patient_id,),
        ).fetchone()
        self.assertEqual(row, (other_data_source,))
