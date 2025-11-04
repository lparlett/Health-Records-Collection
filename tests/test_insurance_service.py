from __future__ import annotations

import sqlite3
import unittest

import pytest

from health_records_collection.services.insurance import upsert_insurance


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Insurance", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestInsuranceService(unittest.TestCase):
    """Test suite for insurance service."""

    @pytest.mark.usefixtures("schema_conn")
    def test_upsert_insurance_handles_insert_and_update(
        self,
        schema_conn: sqlite3.Connection,
        data_source_id: int,
    ) -> None:
        """Test that upsert_insurance handles both insert and update."""
        patient_id = _seed_patient(schema_conn)
        payload = {
            "payer_name": "Example Insurance",
            "plan_name": "Gold PPO",
            "coverage_type": "PPO",
            "member_id": "MEM123",
            "group_number": "GRP42",
            "status": "active",
            "payer_identifier": "758",
            "data_source_id": data_source_id,
        }

        inserted, updated = upsert_insurance(schema_conn, patient_id, [payload])
        self.assertEqual(inserted, 1)
        self.assertEqual(updated, 0)

        row = schema_conn.execute(
            """
            SELECT payer_name, plan_name, coverage_type, status, payer_identifier, data_source_id
              FROM insurance
             WHERE patient_id = ?
            """,
            (patient_id,),
        ).fetchone()
        self.assertEqual(
            row,
            (
                "Example Insurance",
                "Gold PPO",
                "PPO",
                "active",
                "758",
                data_source_id,
            ),
        )

        new_source = schema_conn.execute(
            """
            INSERT INTO data_source (original_filename, ingested_at, file_sha256)
            VALUES (?, ?, ?)
            """,
            ("insurance.xml", "2025-10-19T00:00:00Z", "hash-insurance"),
        ).lastrowid
        schema_conn.commit()

        update_payload = {
            **payload,
            "status": "inactive",
            "notes": "Coverage ended",
            "payer_identifier": "99999",
            "data_source_id": int(new_source) if new_source is not None else None,
        }
        inserted_again, updated_again = upsert_insurance(
            schema_conn,
            patient_id,
            [update_payload],
        )
        self.assertEqual(inserted_again, 0)
        self.assertEqual(updated_again, 1)

        updated_row = schema_conn.execute(
            """
            SELECT status, notes, payer_identifier, data_source_id
              FROM insurance
             WHERE patient_id = ?
            """,
            (patient_id,),
        ).fetchone()
        self.assertEqual(
            updated_row,
            (
                "inactive",
                "Coverage ended",
                "99999",
                int(new_source) if new_source is not None else None,
            ),
        )

        count = schema_conn.execute(
            "SELECT COUNT(*) FROM insurance WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()[0]
        self.assertEqual(count, 1)
