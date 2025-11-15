# pylint: disable=duplicate-code

from __future__ import annotations

from health_records_collection.services.providers import get_or_create_provider
from health_records_collection.services.vitals import insert_vitals
from health_records_collection.tests import helpers


class TestVitalsService(helpers.SchemaTestCase):
    """Test suite for vitals service."""

    def test_insert_vitals_links_to_existing_encounter(self) -> None:
        """Test that insert_vitals properly links vitals to existing encounters."""
        self.schema_conn.execute(
            "INSERT INTO patient (given_name, family_name) VALUES (?, ?)",
            ("Test", "Patient"),
        )
        patient_id = int(
            self.schema_conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        )

        provider_id = get_or_create_provider(self.schema_conn, "Example Clinic")
        self.schema_conn.execute(
            """
            INSERT INTO encounter (
                patient_id,
                encounter_date,
                provider_id,
                source_encounter_id,
                encounter_type,
                notes,
                data_source_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id,
                "20240101120000",
                provider_id,
                "ENC-1",
                "Office visit",
                None,
                self.data_source_id,
            ),
        )
        self.schema_conn.commit()

        vital_payload = [
            {
                "code": "8302-2",
                "vital_type": "Body height",
                "value": "170",
                "unit": "cm",
                "status": "completed",
                "date": "20240101120000",
                "encounter_start": "20240101120000",
                "encounter_end": None,
                "encounter_source_id": "ENC-1",
                "provider": "Example Clinic",
                "data_source_id": self.data_source_id,
            }
        ]

        insert_vitals(self.schema_conn, patient_id, vital_payload)

        count = self.schema_conn.execute("SELECT COUNT(*) FROM vital").fetchone()[0]
        self.assertEqual(count, 1)

        row = self.schema_conn.execute(
            """
            SELECT vital_type, value, unit, date, encounter_id, data_source_id
              FROM vital
            """
        ).fetchone()

        self.assertEqual(
            row, ("Body height", "170", "cm", "20240101120000", 1, self.data_source_id)
        )
