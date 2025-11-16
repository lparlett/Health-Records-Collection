from __future__ import annotations

import sqlite3
from pathlib import Path

from health_records_collection.services.attachments import upsert_attachment
from health_records_collection.services.data_sources import link_attachment
from health_records_collection.tests import helpers


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Attachment", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestAttachmentsService(helpers.SchemaTestCase):
    """Test suite for attachments service."""

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
