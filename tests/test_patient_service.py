from __future__ import annotations
from pathlib import Path
import hashlib

import sqlite3
import unittest


from health_records_collection.services.patient import insert_patient


class TestPatientService(unittest.TestCase):
    """Test suite for patient service."""

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

    
    def test_insert_patient_records_data_source(self) -> None:
        """Test that insert_patient records data_source_id."""
        payload = {
            "given": "Ada",
            "family": "Lovelace",
            "dob": "1815-12-10",
            "gender": "female",
            "data_source_id": self.data_source_id,
        }

        patient_id = insert_patient(self.schema_conn, payload)
        row = self.schema_conn.execute(
            "SELECT given_name, family_name, data_source_id FROM patient WHERE id = ?",
            (patient_id,),
        ).fetchone()

        self.assertEqual(row, ("Ada", "Lovelace", self.data_source_id))

    def test_insert_patient_updates_existing_data_source(self) -> None:
        """Test that insert_patient updates existing data source."""
        other_data_source = self.schema_conn.execute(
            """
            INSERT INTO data_source (original_filename, ingested_at, file_sha256)
            VALUES (?, ?, ?)
            """,
            ("other.xml", "2025-10-12T00:00:01Z", "hash-other"),
        ).lastrowid
        self.schema_conn.commit()

        payload = {
            "given": "Alan",
            "family": "Turing",
            "dob": "1912-06-23",
            "gender": "male",
            "data_source_id": self.data_source_id,
        }
        patient_id = insert_patient(self.schema_conn, payload)

        # Re-ingest with updated provenance
        payload["data_source_id"] = other_data_source
        insert_patient(self.schema_conn, payload)

        row = self.schema_conn.execute(
            "SELECT data_source_id FROM patient WHERE id = ?",
            (patient_id,),
        ).fetchone()
        self.assertEqual(row, (other_data_source,))
