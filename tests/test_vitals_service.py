from __future__ import annotations
from pathlib import Path
import hashlib

import sqlite3
import unittest


from health_records_collection.services.providers import get_or_create_provider
from health_records_collection.services.vitals import insert_vitals


class TestVitalsService(unittest.TestCase):
    """Test suite for vitals service."""

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

    
    def test_insert_vitals_links_to_existing_encounter(self) -> None:
        """Test that insert_vitals properly links vitals to existing encounters."""
        self.schema_conn.execute(
            "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
            ("Test", "Patient"),
        )
        patient_id = int(
            self.schema_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        )

        provider_id = get_or_create_provider(self.schema_conn, "Example Clinic")
        self.schema_conn.execute(
            """
            INSERT INTO encounter (
                patient_id,
                encounter_date,
                provider_id,
                source_encounter_id,
                encounter_type,
                notes,
                data_source_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id,
                "20240101120000",
                provider_id,
                "ENC-1",
                "Office visit",
                None,
                self.data_source_id,
            ),
        )
        self.schema_conn.commit()

        vital_payload = [
            {
                "code": "8302-2",
                "vital_type": "Body height",
                "value": "170",
                "unit": "cm",
                "status": "completed",
                "date": "20240101120000",
                "encounter_start": "20240101120000",
                "encounter_end": None,
                "encounter_source_id": "ENC-1",
                "provider": "Example Clinic",
                "data_source_id": self.data_source_id,
            }
        ]

        insert_vitals(self.schema_conn, patient_id, vital_payload)

        count = self.schema_conn.execute("SELECT COUNT(*) FROM vital").fetchone()[0]
        self.assertEqual(count, 1)

        row = self.schema_conn.execute(
            "SELECT vital_type, value, unit, date, encounter_id, data_source_id FROM vital"
        ).fetchone()

        self.assertEqual(
            row, ("Body height", "170", "cm", "20240101120000", 1, self.data_source_id)
        )
