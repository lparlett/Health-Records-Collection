from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.data_sources import link_attachment, upsert_data_source


def _assert_single_row(conn: sqlite3.Connection, expected_archive: str) -> None:
    row = conn.execute(
        "SELECT original_filename, source_archive, ingested_at FROM data_source"
    ).fetchone()
    assert row is not None
    filename, archive, ingested_at = row
    assert filename == "document.xml"
    assert archive == expected_archive
    assert ingested_at.endswith("Z")


def test_upsert_data_source_inserts_and_updates(
    tmp_path: Path, schema_conn: sqlite3.Connection
) -> None:
    doc_path = tmp_path / "document.xml"
    doc_path.write_text("test payload", encoding="utf-8")

    first_id = upsert_data_source(
        schema_conn, doc_path, source_archive="batch-01.zip"
    )
    assert isinstance(first_id, int) and first_id > 0
    _assert_single_row(schema_conn, "batch-01.zip")

    second_id = upsert_data_source(
        schema_conn, doc_path, source_archive="batch-02.zip"
    )
    assert second_id == first_id
    _assert_single_row(schema_conn, "batch-02.zip")


def test_upsert_data_source_creates_unique_rows(
    tmp_path: Path, schema_conn: sqlite3.Connection
) -> None:
    doc_a = tmp_path / "a.xml"
    doc_a.write_text("content-a", encoding="utf-8")
    doc_b = tmp_path / "b.xml"
    doc_b.write_text("content-b", encoding="utf-8")

    id_a = upsert_data_source(schema_conn, doc_a, source_archive="archive.zip")
    id_b = upsert_data_source(schema_conn, doc_b, source_archive="archive.zip")

    assert id_a != id_b
    count = schema_conn.execute(
        "SELECT COUNT(*) FROM data_source"
    ).fetchone()[0]
    assert count == 2


def test_upsert_data_source_raises_on_missing_file(
    tmp_path: Path, schema_conn: sqlite3.Connection
) -> None:
    missing_path = tmp_path / "missing.xml"
    with pytest.raises(OSError):
        upsert_data_source(schema_conn, missing_path)


def test_upsert_data_source_applies_metadata(
    tmp_path: Path, schema_conn: sqlite3.Connection
) -> None:
    doc_path = tmp_path / "document.xml"
    doc_path.write_text("payload", encoding="utf-8")

    metadata = {
        "document_created": "2025-01-01T12:00:00Z",
        "repository_unique_id": "urn:test:repo",
        "document_hash": "metadata-hash",
        "document_size": 1024,
        "author_institution": "Unit Test Clinic",
    }

    upsert_data_source(
        schema_conn,
        doc_path,
        source_archive="archive.zip",
        metadata=metadata,
    )

    row = schema_conn.execute(
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
    assert row == (
        "2025-01-01T12:00:00Z",
        "urn:test:repo",
        "metadata-hash",
        1024,
        "Unit Test Clinic",
    )


def test_link_attachment_updates_data_source(
    tmp_path: Path, schema_conn: sqlite3.Connection
) -> None:
    doc_path = tmp_path / "link.xml"
    doc_path.write_text("link", encoding="utf-8")
    data_source_id = upsert_data_source(
        schema_conn, doc_path, source_archive="archive.zip"
    )

    schema_conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Link", "Patient"),
    )
    patient_id = int(schema_conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    schema_conn.execute(
        """
        INSERT INTO attachment (patient_id, file_path, mime_type, description, data_source_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (patient_id, "link.xml", "text/xml", "Link", data_source_id),
    )
    attachment_id = int(schema_conn.execute("SELECT last_insert_rowid()").fetchone()[0])
    schema_conn.commit()

    link_attachment(schema_conn, data_source_id, attachment_id)

    row = schema_conn.execute(
        "SELECT attachment_id FROM data_source WHERE id = ?",
        (data_source_id,),
    ).fetchone()
    assert row == (attachment_id,)
