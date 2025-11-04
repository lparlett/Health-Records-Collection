from __future__ import annotations

import hashlib
import sqlite3
import unittest
from pathlib import Path

from health_records_collection.db.schema import ensure_schema
from health_records_collection.services.allergies import insert_allergies


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Allergy", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestAllergiesService(unittest.TestCase): 
    """Test suite for allergies service."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        
        # Create self.schema_conn for database testing
        self.schema_conn = sqlite3.connect(":memory:")
        self.schema_conn.execute("PRAGMA foreign_keys = ON;")
        schema_path = Path(__file__).parent.parent / "schema.sql"
        schema_sql = schema_path.read_text(encoding="utf-8")
        self.schema_conn.executescript(schema_sql)
        ensure_schema(self.schema_conn)
        
        # Create a self.data_source_id for tests
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
        archive_id = int(self.schema_conn.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0])
        
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
        self.data_source_id = int(
            self.schema_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        )
        self.schema_conn.commit()

    def tearDown(self) -> None:
        """Clean up after testing."""
        self.schema_conn.close()

    def test_insert_allergies_inserts_and_updates(self) -> None:
        """Test that insert_allergies properly inserts and updates allergy records."""
        patient_id = _seed_patient(self.schema_conn)

        payload = {
            "substance": "Peanuts",
            "substance_code": "256349002",
            "status": "active",
            "onset": "20241001",
            "reaction": "Hives",
            "severity": "Mild",
            "provider": "Dr Allergy Tester",
            "data_source_id": self.data_source_id,
            "source_allergy_id": "ALLERGY-1",
        }

        inserted, updated = insert_allergies(self.schema_conn, patient_id, [payload])
        self.assertEqual(inserted, 1)
        self.assertEqual(updated, 0)

        row = self.schema_conn.execute(
            """
            SELECT
                substance,
                substance_code,
                severity,
                reaction,
                provider_id,
                data_source_id
              FROM allergy
             WHERE patient_id = ?
            """,
            (patient_id,),
        ).fetchone()
        self.assertIsNotNone(row)
        substance, substance_code, severity, reaction, provider_id, stored_source = row
        self.assertEqual(substance, "Peanuts")
        self.assertEqual(substance_code, "256349002")
        self.assertEqual(severity, "Mild")
        self.assertEqual(reaction, "Hives")
        self.assertIsNotNone(provider_id)
        self.assertEqual(stored_source, self.data_source_id)

        new_source = self.schema_conn.execute(
            """
            INSERT INTO data_source (original_filename, ingested_at, file_sha256)
            VALUES (?, ?, ?)
            """,
            ("allergy.xml", "2025-10-19T00:00:00Z", "hash-allergy"),
        ).lastrowid
        self.schema_conn.commit()

        update_payload = {
            **payload,
            "severity": "Severe",
            "reaction": "Anaphylaxis",
            "criticality": "High",
            "notes": "Carry epinephrine autoinjector",
            "data_source_id": int(new_source) if new_source is not None else None,
        }

        inserted_again, updated_again = insert_allergies(
            self.schema_conn,
            patient_id,
            [update_payload],
        )
        self.assertEqual(inserted_again, 0)
        self.assertEqual(updated_again, 1)

        updated_row = self.schema_conn.execute(
            """
            SELECT severity, reaction, criticality, notes, data_source_id
              FROM allergy
             WHERE patient_id = ?
            """,
            (patient_id,),
        ).fetchone()
        self.assertEqual(
            updated_row,
            (
                "Severe",
                "Anaphylaxis",
                "High",
                "Carry epinephrine autoinjector",
                int(new_source) if new_source is not None else None,
            ),
        )

        count = self.schema_conn.execute(
            "SELECT COUNT(*) FROM allergy WHERE patient_id = ?",
            (patient_id,),
        ).fetchone()[0]
        self.assertEqual(count, 1)
