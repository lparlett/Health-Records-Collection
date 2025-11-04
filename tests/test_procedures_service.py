from __future__ import annotations
from pathlib import Path
import hashlib

import sqlite3
import unittest


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
