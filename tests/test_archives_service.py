from __future__ import annotations
# Purpose: Validate archive registry helpers for ingestion deduplication.
from pathlib import Path
import hashlib
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: tests/test_archives_service.py
# AI-assisted: This test module was generated with AI assistance.
"""Tests for services.archives module."""


import sqlite3
import unittest
from typing import Dict


from health_records_collection.services import archives


class TestArchivesService(unittest.TestCase):
    """Test suite for archives service."""

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

    
    def test_archive_registration_inserts_new_row(self) -> None:
        """Test that first registration creates a new row with count = 1."""
        archive_hash = "abc123"
        archive_id = archives.register_ingested_archive(
            self.schema_conn, "first.zip", archive_hash
        )

        row = archives.archive_was_ingested(self.schema_conn, archive_hash)
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], archive_id)
        self.assertEqual(row["archive_name"], "first.zip")
        self.assertEqual(row["archive_sha256"], archive_hash)
        self.assertEqual(row["ingest_count"], 1)
        self.assertEqual(row["first_ingested_at"], row["last_ingested_at"])

    def test_archive_registration_updates_existing(self) -> None:
        """Test that repeated registration increments count and updates timestamps."""
        archive_hash = "def456"
        first_id = archives.register_ingested_archive(
            self.schema_conn, "initial.zip", archive_hash
        )
        first_row = archives.archive_was_ingested(self.schema_conn, archive_hash)
        self.assertIsNotNone(first_row)
        second_id = archives.register_ingested_archive(
            self.schema_conn, "updated-name.zip", archive_hash
        )

        second_row = archives.archive_was_ingested(self.schema_conn, archive_hash)
        self.assertIsNotNone(second_row)
        self.assertEqual(first_id, second_id)
        self.assertEqual(second_id, second_row["id"])
        self.assertEqual(second_row["archive_name"], "updated-name.zip")
        self.assertEqual(second_row["ingest_count"], 2)
        self.assertLessEqual(
            second_row["first_ingested_at"], second_row["last_ingested_at"]
        )
