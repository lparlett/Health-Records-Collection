"""Tests for services.archives module.

Purpose: Validate archive registry helpers for ingestion deduplication.
Author: Codex + Lauren
Date: 2025-10-29
Tests: tests/test_archives_service.py
AI-assisted: This test module was generated with AI assistance.
"""

from __future__ import annotations
from health_records_collection.services import archives
from health_records_collection.tests import helpers


class TestArchivesService(helpers.SchemaTestCase):
    """Test suite for archives service."""

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
