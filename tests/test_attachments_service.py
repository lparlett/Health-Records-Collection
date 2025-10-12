from __future__ import annotations

from pathlib import Path

import sqlite3

from services.attachments import upsert_attachment
from services.data_sources import link_attachment


def _seed_patient(conn: sqlite3.Connection) -> int:
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Attachment", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


def test_upsert_attachment_inserts_and_updates(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _seed_patient(schema_conn)
    path = Path("data/parsed/test/DOC0001.XML")

    attachment_id = upsert_attachment(
        schema_conn,
        patient_id=patient_id,
        data_source_id=data_source_id,
        file_path=path,
        mime_type="text/xml",
        description="Initial import",
    )
    assert attachment_id > 0

    # Update metadata
    updated_id = upsert_attachment(
        schema_conn,
        patient_id=patient_id,
        data_source_id=data_source_id,
        file_path=path,
        mime_type="application/xml",
        description="Updated description",
    )
    assert updated_id == attachment_id

    row = schema_conn.execute(
        """
        SELECT data_source_id, mime_type, description
          FROM attachment
         WHERE id = ?
        """,
        (attachment_id,),
    ).fetchone()
    assert row == (data_source_id, "application/xml", "Updated description")


def test_link_attachment_sets_reference(
    schema_conn: sqlite3.Connection,
    data_source_id: int,
) -> None:
    patient_id = _seed_patient(schema_conn)
    path = Path("data/parsed/test/DOC0002.XML")

    attachment_id = upsert_attachment(
        schema_conn,
        patient_id=patient_id,
        data_source_id=data_source_id,
        file_path=path,
        mime_type="text/xml",
        description="Linked attachment",
    )
    link_attachment(schema_conn, data_source_id, attachment_id)

    row = schema_conn.execute(
        "SELECT attachment_id FROM data_source WHERE id = ?",
        (data_source_id,),
    ).fetchone()
    assert row == (attachment_id,)
