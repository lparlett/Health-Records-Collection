from __future__ import annotations
from pathlib import Path
import hashlib

import sqlite3
import unittest
from typing import Any, Dict, List


from health_records_collection.services.immunizations import insert_immunizations


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Test", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestImmunizationsService(unittest.TestCase):
    """Test suite for immunizations service."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        from health_records_collection.db.schema import ensure_schema
        
        # Create schema_conn for database testing
        self.schema_conn = sqlite3.connect(":memory:")
        self.schema_conn.execute("PRAGMA foreign_keys = ON;")
        schema_path = Path(__file__).parent.parent / "schema.sql"
        schema_sql = schema_path.read_text(encoding="utf-8")
        self.schema_conn.executescript(schema_sql)
        ensure_schema(self.schema_conn)
        
        # Create a data_source_id for tests
        archive_hash = hashlib.sha256(b"archive.zip").hexdigest()
        self.schema_conn.execute(
            """
            INSERT INTO ingested_archive (
                archive_name,
                archive_sha256,
                first_ingested_at,
                last_ingested_at,
                ingest_count
            ) VALUES (?, ?, '2025-10-12T00:00:00Z', '2025-10-12T00:00:00Z', 1)
            """,
            ("archive.zip", archive_hash),
        )
        archive_id = int(self.schema_conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        
        self.schema_conn.execute(
            """
            INSERT INTO data_source (
                original_filename,
                file_sha256,
                ingested_at,
                source_archive_id
            ) VALUES (?, ?, '2025-10-12T00:00:00Z', ?)
            """,
            ("test.xml", hashlib.sha256(b"test").hexdigest(), archive_id),
        )
        self.data_source_id = int(self.schema_conn.execute("SELECT last_insert_rowid()").fetchone()[0])
        self.schema_conn.commit()

    def tearDown(self) -> None:
        """Clean up after testing."""
        self.schema_conn.close()

    
    def test_insert_immunizations_deduplicates_and_sets_provenance(self) -> None:
        """Test that insert_immunizations deduplicates and sets provenance."""
        patient_id = _seed_patient(self.schema_conn)

        immunization_payload: List[Dict[str, Any]] = [
            {
                "vaccine_name": "Influenza vaccine",
                "date": "20240315",
                "cvx_codes": ["140", "140"],
                "lot_number": "LOT-ABC",
                "product_name": "Influenza Quadrivalent",
                "status": "completed",
                "data_source_id": self.data_source_id,
            },
            {
                "vaccine_name": "Influenza vaccine",
                "date": "20240315",
                "cvx_codes": ["140"],
                "lot_number": "LOT-ABC",
                "product_name": "Influenza Quadrivalent",
                "status": "completed",
                "data_source_id": self.data_source_id,
            },
            {
                "vaccine_name": "COVID-19 vaccine",
                "date": "20240210",
                "cvx_codes": ["91309"],
                "product_name": "COVID-19 Booster",
                "data_source_id": self.data_source_id,
            },
        ]

        insert_immunizations(self.schema_conn, patient_id, immunization_payload)
        insert_immunizations(
            self.schema_conn, patient_id, immunization_payload
        )  # idempotent check

        rows = list(
            self.schema_conn.execute(
                """
                SELECT vaccine_name, cvx_code, date_administered, lot_number, notes, data_source_id
                  FROM immunization
                 ORDER BY date_administered
                """
            )
        )

        self.assertEqual(len(rows), 2)

        flu_row = rows[1]
        self.assertEqual(flu_row[0], "Influenza vaccine")
        self.assertEqual(flu_row[1], "140")
        self.assertEqual(flu_row[2], "20240315")
        self.assertEqual(flu_row[3], "LOT-ABC")
        self.assertEqual(flu_row[4], "Product: Influenza Quadrivalent")
        self.assertEqual(flu_row[5], self.data_source_id)

        covid_row = rows[0]
        self.assertEqual(covid_row[0], "COVID-19 vaccine")
        self.assertEqual(covid_row[1], "91309")
        self.assertEqual(covid_row[2], "20240210")
        self.assertIsNone(covid_row[3])
        self.assertEqual(covid_row[4], "Product: COVID-19 Booster")
        self.assertEqual(covid_row[5], self.data_source_id)
