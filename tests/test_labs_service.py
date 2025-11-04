from __future__ import annotations
from pathlib import Path
import hashlib

import sqlite3
import unittest


from health_records_collection.services.labs import insert_labs


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Lab", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestLabsService(unittest.TestCase):
    """Test suite for labs service."""

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

    
    def test_insert_labs_sets_data_source(self) -> None:
        """Test that insert_labs sets data_source_id."""
        patient_id = _seed_patient(self.schema_conn)

        insert_labs(
            self.schema_conn,
            patient_id,
            [
                {
                    "test_name": "Complete Blood Count",
                    "loinc": "58410-2",
                    "value": "12.5",
                    "unit": "g/dL",
                    "date": "2024-02-01",
                    "data_source_id": self.data_source_id,
                }
            ],
        )

        row = self.schema_conn.execute(
            "SELECT data_source_id FROM lab_result WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()
        self.assertEqual(row, (self.data_source_id,))

    def test_insert_labs_deduplicates_by_date_and_loinc(self) -> None:
        """Test that insert_labs deduplicates by date and LOINC code."""
        patient_id = _seed_patient(self.schema_conn)

        labs = [
            {
                "test_name": "Glucose",
                "loinc": "2345-7",
                "value": "95",
                "unit": "mg/dL",
                "date": "2024-03-01",
            },
            {
                "test_name": "Glucose",
                "loinc": "2345-7",
                "value": "96",
                "unit": "mg/dL",
                "date": "2024-03-01",
            },
            {
                "test_name": "Glucose",
                "loinc": "2345-7",
                "value": "88",
                "unit": "mg/dL",
                "date": "2024-03-02",
            },
            {
                "test_name": "Hemoglobin",
                "loinc": "718-7",
                "value": "13.2",
                "unit": "g/dL",
                "date": "2024-03-01",
            },
        ]

        insert_labs(self.schema_conn, patient_id, labs)

        rows = self.schema_conn.execute(
            "SELECT loinc_code, date, result_value FROM lab_result WHERE patient_id = ?",
            (patient_id,),
        ).fetchall()

        self.assertEqual(len(rows), 3)
        observed_pairs = {(row[0], row[1]) for row in rows}
        expected_pairs = {
            ("2345-7", "2024-03-01"),
            ("2345-7", "2024-03-02"),
            ("718-7", "2024-03-01"),
        }
        self.assertEqual(observed_pairs, expected_pairs)
