# Purpose: Validate archive registry helpers for ingestion deduplication.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: tests/test_archives_service.py
# AI-assisted: This test module was generated with AI assistance.
"""Tests for services.archives module."""

from __future__ import annotations

import sqlite3
from typing import Dict

from services import archives


def test_archive_registration_inserts_new_row(schema_conn: sqlite3.Connection) -> None:
    """First registration should create a new row with count = 1."""
    archive_hash = "abc123"
    archive_id = archives.register_ingested_archive(schema_conn, "first.zip", archive_hash)

    row = archives.archive_was_ingested(schema_conn, archive_hash)
    assert row is not None
    assert row["id"] == archive_id
    assert row["archive_name"] == "first.zip"
    assert row["archive_sha256"] == archive_hash
    assert row["ingest_count"] == 1
    assert row["first_ingested_at"] == row["last_ingested_at"]


def test_archive_registration_updates_existing(schema_conn: sqlite3.Connection) -> None:
    """Repeated registration should increment count and update timestamps."""
    archive_hash = "def456"
    first_id = archives.register_ingested_archive(schema_conn, "initial.zip", archive_hash)
    first_row = archives.archive_was_ingested(schema_conn, archive_hash)
    assert first_row is not None
    second_id = archives.register_ingested_archive(schema_conn, "updated-name.zip", archive_hash)

    second_row = archives.archive_was_ingested(schema_conn, archive_hash)
    assert second_row is not None
    assert first_id == second_id == second_row["id"]
    assert second_row["archive_name"] == "updated-name.zip"
    assert second_row["ingest_count"] == 2
    assert second_row["first_ingested_at"] <= second_row["last_ingested_at"]
