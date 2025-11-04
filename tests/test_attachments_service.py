from __future__ import annotations

import hashlib
import sqlite3
import unittest
from pathlib import Path

from health_records_collection.db.schema import ensure_schema
from health_records_collection.services.attachments import upsert_attachment
from health_records_collection.services.data_sources import link_attachment


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Attachment", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestAttachmentsService(unittest.TestCase):
    """Test suite for attachments service."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        
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

    
    def test_upsert_attachment_inserts_and_updates(self) -> None:
        """Test that upsert_attachment inserts and updates."""
        patient_id = _seed_patient(self.schema_conn)
        path = Path("data/parsed/test/DOC0001.XML")

        attachment_id = upsert_attachment(
            self.schema_conn,
            patient_id=patient_id,
            data_source_id=self.data_source_id,
            file_path=path,
            mime_type="text/xml",
            description="Initial import",
        )
        self.assertGreater(attachment_id, 0)

        # Update metadata
        updated_id = upsert_attachment(
            self.schema_conn,
            patient_id=patient_id,
            data_source_id=self.data_source_id,
            file_path=path,
            mime_type="application/xml",
            description="Updated description",
        )
        self.assertEqual(updated_id, attachment_id)

        row = self.schema_conn.execute(
            """
            SELECT data_source_id, mime_type, description
              FROM attachment
             WHERE id = ?
            """,
            (attachment_id,),
        ).fetchone()
        self.assertEqual(
            row, (self.data_source_id, "application/xml", "Updated description")
        )

    def test_link_attachment_sets_reference(self) -> None:
        """Test that link_attachment sets reference."""
        patient_id = _seed_patient(self.schema_conn)
        path = Path("data/parsed/test/DOC0002.XML")

        attachment_id = upsert_attachment(
            self.schema_conn,
            patient_id=patient_id,
            data_source_id=self.data_source_id,
            file_path=path,
            mime_type="text/xml",
            description="Linked attachment",
        )
        link_attachment(self.schema_conn, self.data_source_id, attachment_id)

        row = self.schema_conn.execute(
            "SELECT attachment_id FROM data_source WHERE id = ?",
            (self.data_source_id,),
        ).fetchone()
        self.assertEqual(row, (attachment_id,))
