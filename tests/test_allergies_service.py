from __future__ import annotations

import sqlite3

from health_records_collection.services.allergies import insert_allergies
from health_records_collection.tests import helpers


def _seed_patient(conn: sqlite3.Connection) -> int:
    """Helper to insert a patient for testing."""
    conn.execute(
        "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
        ("Allergy", "Patient"),
    )
    return int(conn.execute("SELECT last_insert_rowid()").fetchone()[0])


class TestAllergiesService(helpers.SchemaTestCase):
    """Test suite for allergies service."""

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
