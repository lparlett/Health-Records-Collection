from __future__ import annotations

import hashlib
import shutil
import sqlite3
import tempfile
from pathlib import Path

from health_records_collection.services.data_sources import (
    link_attachment,
    upsert_data_source,
)
from health_records_collection.tests import helpers


def _create_archive(conn: sqlite3.Connection, name: str) -> int:
    """Helper to create an archive for testing."""
    hash_value = hashlib.sha256(name.encode("utf-8")).hexdigest()
    conn.execute(
        """
        INSERT INTO ingested_archive (
            archive_name,
            archive_sha256,
            first_ingested_at,
            last_ingested_at,
            ingest_count
        ) VALUES (?, ?, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z', 1)
        """,
        (name, hash_value),
    )
    archive_id = int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    conn.commit()
    return archive_id


def _assert_single_row(conn: sqlite3.Connection, expected_archive: str) -> None:
    """Helper to assert single data_source row."""
    row = conn.execute(
        """
        SELECT ds.original_filename,
               ia.archive_name,
               ds.ingested_at,
               ds.source_archive_id
          FROM data_source ds
          LEFT JOIN ingested_archive ia ON ds.source_archive_id = ia.id
        """
    ).fetchone()
    if row is None:
        raise AssertionError("Expected single data_source row but got None")
    filename, archive, ingested_at, archive_id = row
    if filename != "document.xml":
        raise AssertionError(f"Expected filename 'document.xml' but got '{filename}'")
    if archive != expected_archive:
        raise AssertionError(
            f"Expected archive '{expected_archive}' but got '{archive}'"
        )
    if not ingested_at.endswith("Z"):
        raise AssertionError(
            f"Expected ingested_at to end with 'Z' but got '{ingested_at}'"
        )
    if archive_id is None:
        raise AssertionError("Expected archive_id to be not None")


class TestDataSourcesService(helpers.SchemaTestCase):
    """Test suite for data sources service."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        super().setUp()
        self.tmp_path = Path(tempfile.mkdtemp())
        self.data_source_id: int | None = None

    def tearDown(self) -> None:
        """Clean up after testing."""
        super().tearDown()
        shutil.rmtree(self.tmp_path, ignore_errors=True)

    def test_upsert_data_source_inserts_and_updates(self) -> None:
        """Test that upsert_data_source inserts and updates."""
        doc_path = self.tmp_path / "document.xml"
        doc_path.write_text("test payload", encoding="utf-8")

        archive_id_1 = _create_archive(self.schema_conn, "batch-01.zip")
        first_id = upsert_data_source(
            self.schema_conn, doc_path, archive_id=archive_id_1
        )
        self.assertIsInstance(first_id, int)
        self.assertGreater(first_id, 0)
        _assert_single_row(self.schema_conn, "batch-01.zip")

        archive_id_2 = _create_archive(self.schema_conn, "batch-02.zip")
        second_id = upsert_data_source(
            self.schema_conn, doc_path, archive_id=archive_id_2
        )
        self.assertEqual(second_id, first_id)
        _assert_single_row(self.schema_conn, "batch-02.zip")

    def test_upsert_data_source_creates_unique_rows(self) -> None:
        """Test that upsert_data_source creates unique rows for different files."""
        doc_a = self.tmp_path / "a.xml"
        doc_a.write_text("content-a", encoding="utf-8")
        doc_b = self.tmp_path / "b.xml"
        doc_b.write_text("content-b", encoding="utf-8")

        archive_id = _create_archive(self.schema_conn, "archive.zip")
        id_a = upsert_data_source(self.schema_conn, doc_a, archive_id=archive_id)
        id_b = upsert_data_source(self.schema_conn, doc_b, archive_id=archive_id)

        self.assertNotEqual(id_a, id_b)
        count = self.schema_conn.execute("SELECT COUNT(*) FROM data_source").fetchone()[
            0
        ]
        self.assertEqual(count, 2)

    def test_upsert_data_source_raises_on_missing_file(self) -> None:
        """Test that upsert_data_source raises on missing file."""
        missing_path = self.tmp_path / "missing.xml"
        with self.assertRaises(OSError):
            upsert_data_source(self.schema_conn, missing_path)

    def test_upsert_data_source_applies_metadata(self) -> None:
        """Test that upsert_data_source applies metadata."""
        doc_path = self.tmp_path / "document.xml"
        doc_path.write_text("payload", encoding="utf-8")

        metadata = {
            "document_created": "2025-01-01T12:00:00Z",
            "repository_unique_id": "urn:test:repo",
            "document_hash": "metadata-hash",
            "document_size": 1024,
            "author_institution": "Unit Test Clinic",
        }

        archive_id = _create_archive(self.schema_conn, "archive.zip")

        upsert_data_source(
            self.schema_conn,
            doc_path,
            archive_id=archive_id,
            metadata=metadata,
        )

        row = self.schema_conn.execute(
            """
            SELECT
                document_created,
                repository_unique_id,
                document_hash,
                document_size,
                author_institution
              FROM data_source
            """
        ).fetchone()
        self.assertEqual(
            row,
            (
                "2025-01-01T12:00:00Z",
                "urn:test:repo",
                "metadata-hash",
                1024,
                "Unit Test Clinic",
            ),
        )

    def test_link_attachment_updates_data_source(self) -> None:
        """Test that link_attachment updates data_source."""
        doc_path = self.tmp_path / "link.xml"
        doc_path.write_text("link", encoding="utf-8")
        archive_id = _create_archive(self.schema_conn, "archive.zip")
        self.data_source_id = upsert_data_source(
            self.schema_conn, doc_path, archive_id=archive_id
        )

        self.schema_conn.execute(
            "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
            ("Link", "Patient"),
        )
        patient_id = int(
            self.schema_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        )
        self.schema_conn.execute(
            """
            INSERT INTO attachment (
                patient_id,
                file_path,
                mime_type,
                description,
                data_source_id
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (patient_id, "link.xml", "text/xml", "Link", self.data_source_id),
        )
        attachment_id = int(
            self.schema_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        )
        self.schema_conn.commit()

        link_attachment(self.schema_conn, self.data_source_id, attachment_id)

        row = self.schema_conn.execute(
            "SELECT attachment_id FROM data_source WHERE id = ?",
            (self.data_source_id,),
        ).fetchone()
        self.assertEqual(row, (attachment_id,))
