from __future__ import annotations

from pathlib import Path
import tempfile
import sqlite3
import zipfile
import hashlib
import logging
import unittest
from unittest.mock import patch

from health_records_collection import ingest
from health_records_collection.db.schema import ensure_schema

def _create_sample_archive(tmp_path: Path, filename: str = "sample.zip") -> Path:
    """Helper to create a sample archive for testing."""
    xml_content = """
    <ClinicalDocument xmlns="urn:hl7-org:v3">
      <recordTarget>
        <patientRole>
          <patient>
            <name>
              <given>Jane</given>
              <family>Doe</family>
            </name>
          </patient>
        </patientRole>
      </recordTarget>
    </ClinicalDocument>
    """

    metadata_xml = """
    <SubmitObjectsRequest xmlns="urn:oasis:names:tc:ebxml-regrep:xsd:lcm:3.0">
      <RegistryObjectList xmlns:rim="urn:oasis:names:tc:ebxml-regrep:xsd:rim:3.0">
        <rim:ExtrinsicObject id="doc-1" objectType="urn:uuid:7edca82f-054d-47f2-a032-9b2a5b5186c1">
          <rim:Slot name="repositoryUniqueId">
            <rim:ValueList>
              <rim:Value>urn:repository:123</rim:Value>
            </rim:ValueList>
          </rim:Slot>
          <rim:Slot name="creationTime">
            <rim:ValueList>
              <rim:Value>20250101123456</rim:Value>
            </rim:ValueList>
          </rim:Slot>
          <rim:Slot name="URI">
            <rim:ValueList>
              <rim:Value>DOC0001.XML</rim:Value>
            </rim:ValueList>
          </rim:Slot>
          <rim:Slot name="hash">
            <rim:ValueList>
              <rim:Value>abc123hash</rim:Value>
            </rim:ValueList>
          </rim:Slot>
          <rim:Slot name="size">
            <rim:ValueList>
              <rim:Value>512</rim:Value>
            </rim:ValueList>
          </rim:Slot>
          <rim:Classification>
            <rim:Slot name="authorInstitution">
              <rim:ValueList>
                <rim:Value>Unit Test Hospital</rim:Value>
              </rim:ValueList>
            </rim:Slot>
          </rim:Classification>
        </rim:ExtrinsicObject>
      </RegistryObjectList>
    </SubmitObjectsRequest>
    """

    archive_path = tmp_path / filename
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("IHE_XDM/Lauren1/DOC0001.XML", xml_content)
        zf.writestr("IHE_XDM/Lauren1/METADATA.XML", metadata_xml)
    return archive_path


class TestIngest(unittest.TestCase):
    """Test suite for ingest module."""

    def setUp(self) -> None:
        """Set up temporary directory for ingest testing."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)
        
        # Create schema_conn for database testing
        self.schema_conn = sqlite3.connect(":memory:")
        self.schema_conn.execute("PRAGMA foreign_keys = ON;")
        schema_path = Path(__file__).parent.parent / "schema.sql"
        schema_sql = schema_path.read_text(encoding="utf-8")
        self.schema_conn.executescript(schema_sql)
        ensure_schema(self.schema_conn)

    def tearDown(self) -> None:
        """Clean up temporary directory and database connection after testing."""
        # Close all log handlers to release file locks before cleanup
        logger = logging.getLogger()
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
        
        # Close database connection
        if hasattr(self, 'schema_conn'):
            self.schema_conn.close()
        
        self.temp_dir.cleanup()

    def test_ingest_archive_records_data_source(self) -> None:
        """Test that ingest_archive records data_source."""
        archive_path = _create_sample_archive(self.tmp_path, "sample.zip")

        parsed_dir = self.tmp_path / "parsed"
        raw_dir = self.tmp_path / "raw"
        raw_dir.mkdir()
        parsed_dir.mkdir()

        db_path = self.tmp_path / "db" / "health_records.db"

        def _fake_load_paths():
            return {
                "raw_dir": raw_dir,
                "parsed_dir": parsed_dir,
                "db_path": db_path,
            }

        with patch.object(ingest.settings, "load_paths", _fake_load_paths):
            ingest.ingest_archive(self.schema_conn, archive_path)

        ds_row = self.schema_conn.execute(
            """
            SELECT
                ds.id,
                ds.original_filename,
                ds.source_archive_id,
                ia.archive_name,
                ia.ingest_count,
                ds.document_created,
                ds.repository_unique_id,
                ds.document_hash,
                ds.document_size,
                ds.author_institution,
                ds.attachment_id
              FROM data_source ds
              LEFT JOIN ingested_archive ia ON ds.source_archive_id = ia.id
            """
        ).fetchone()
        self.assertIsNotNone(ds_row)
        (
            data_source_id,
            original_filename,
            source_archive_id,
            source_archive_name,
            source_archive_ingest_count,
            document_created,
            repository_unique_id,
            document_hash,
            document_size,
            author_institution,
            ds_attachment_id,
        ) = ds_row
        self.assertEqual(original_filename, "DOC0001.XML")
        self.assertEqual(source_archive_name, "sample.zip")
        self.assertIsNotNone(source_archive_id)
        self.assertEqual(source_archive_ingest_count, 1)
        self.assertEqual(document_created, "2025-01-01T12:34:56Z")
        self.assertEqual(repository_unique_id, "urn:repository:123")
        self.assertEqual(document_hash, "abc123hash")
        self.assertEqual(document_size, 512)
        self.assertEqual(author_institution, "Unit Test Hospital")

        patient_row = self.schema_conn.execute(
            "SELECT data_source_id FROM patient"
        ).fetchone()
        self.assertEqual(patient_row, (data_source_id,))

        patient_count = self.schema_conn.execute(
          "SELECT COUNT(*) FROM patient"
        ).fetchone()[
            0
        ]
        self.assertEqual(patient_count, 1)

        attachment_row = self.schema_conn.execute(
            """
            SELECT id, patient_id, file_path, data_source_id, mime_type
              FROM attachment
            """
        ).fetchone()
        self.assertIsNotNone(attachment_row)
        (
            attachment_id,
            attachment_patient_id,
            attachment_path,
            attachment_ds_id,
            attachment_mime,
        ) = attachment_row
        self.assertEqual(
            attachment_patient_id,
            self.schema_conn.execute("SELECT id FROM patient").fetchone()[0],
        )
        self.assertTrue(attachment_path.endswith("DOC0001.XML.enc"))
        self.assertEqual(attachment_ds_id, data_source_id)
        self.assertIn(attachment_mime, ("application/octet-stream", "application/xml"))
        self.assertEqual(ds_attachment_id, attachment_id)

        attachment_count = self.schema_conn.execute(
            "SELECT COUNT(*) FROM attachment"
        ).fetchone()[0]
        self.assertEqual(attachment_count, 1)

        registry_row = self.schema_conn.execute(
            """
            SELECT id, archive_name, archive_sha256, ingest_count
              FROM ingested_archive
            """
        ).fetchone()
        self.assertIsNotNone(registry_row)
        archive_id, archive_name, archive_hash, ingest_count = registry_row
        self.assertEqual(archive_name, "sample.zip")
        self.assertEqual(ingest_count, 1)
        expected_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        self.assertEqual(archive_hash, expected_hash)
        self.assertEqual(archive_id, source_archive_id)

    def test_ingest_archive_skips_duplicate_hash(self) -> None:
        """Test that ingest_archive skips duplicate hash."""
        archive_path = _create_sample_archive(self.tmp_path, "duplicate.zip")

        parsed_dir = self.tmp_path / "parsed"
        raw_dir = self.tmp_path / "raw"
        raw_dir.mkdir()
        parsed_dir.mkdir()

        db_path = self.tmp_path / "db" / "records.db"

        def _fake_load_paths():
            return {
                "raw_dir": raw_dir,
                "parsed_dir": parsed_dir,
                "db_path": db_path,
            }

        with patch.object(ingest.settings, "load_paths", _fake_load_paths):
            ingest.ingest_archive(self.schema_conn, archive_path)

            ds_count, ingest_count = self.schema_conn.execute(
                "SELECT COUNT(*), MAX(ingest_count) FROM data_source "
                "CROSS JOIN ingested_archive"
            ).fetchone()
            self.assertEqual(ds_count, 1)
            self.assertEqual(ingest_count, 1)

            ingest.ingest_archive(self.schema_conn, archive_path)

            ds_count_after = self.schema_conn.execute(
                "SELECT COUNT(*) FROM data_source"
            ).fetchone()[0]
            ingest_count_after = self.schema_conn.execute(
                "SELECT ingest_count FROM ingested_archive WHERE archive_name = ?",
                ("duplicate.zip",),
            ).fetchone()[0]
            self.assertEqual(ds_count_after, 1)
            self.assertEqual(ingest_count_after, 1)

    def test_ingest_archive_persists_allergies_and_insurance(self) -> None:
        """Test that ingest_archive persists allergies and insurance."""
        xml_content = """
        <ClinicalDocument xmlns="urn:hl7-org:v3"
                          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
                          xmlns:sdtc="urn:hl7-org:sdtc">
          <recordTarget>
            <patientRole>
              <patient>
                <name>
                  <given>Alex</given>
                  <family>Smith</family>
                </name>
              </patient>
            </patientRole>
          </recordTarget>
          <component>
            <structuredBody>
              <component>
                <section>
                  <code code="48765-2"/>
                  <text>
                    <paragraph ID="allergyNote">Patient reported penicillin reaction.</paragraph>
                  </text>
                  <entry>
                    <act classCode="ACT" moodCode="EVN">
                      <entryRelationship typeCode="SUBJ">
                        <observation classCode="OBS" moodCode="EVN">
                          <templateId root="2.16.840.1.113883.10.20.22.4.8"/>
                          <statusCode code="active"/>
                          <effectiveTime value="20250105"/>
                          <value xsi:type="CD" code="70618" codeSystem="2.16.840.1.113883.6.88" displayName="Penicillin"/>
                          <text>
                            <reference value="#allergyNote"/>
                          </text>
                          <entryRelationship typeCode="SUBJ">
                            <observation classCode="OBS" moodCode="EVN">
                              <templateId root="2.16.840.1.113883.10.20.22.4.9"/>
                              <value xsi:type="CD" code="39579001" displayName="Anaphylaxis"/>
                            </observation>
                          </entryRelationship>
                          <author>
                            <assignedAuthor>
                              <assignedPerson>
                                <name>Dr Allergy Tester</name>
                              </assignedPerson>
                            </assignedAuthor>
                          </author>
                        </observation>
                      </entryRelationship>
                    </act>
                  </entry>
                </section>
              </component>
              <component>
                <section>
                  <code code="48768-6"/>
                  <text>
                    <list>
                      <item ID="coverage100">Plan: BCBS PPO</item>
                      <item ID="coverage100PlanName">BCBS PPO</item>
                      <item ID="coverage100relToSub">Self</item>
                    </list>
                  </text>
                  <entry>
                    <act classCode="ACT" moodCode="EVN">
                      <templateId root="2.16.840.1.113883.10.20.22.4.60"/>
                      <id root="1.2.840.114350.1.13.470.2.7.2.678671" extension="816442"/>
                      <code code="48768-6" displayName="Payment sources"/>
                      <statusCode code="completed"/>
                      <effectiveTime value="20240303"/>
                      <entryRelationship typeCode="COMP">
                        <act classCode="ACT" moodCode="EVN">
                          <templateId root="2.16.840.1.113883.10.20.22.4.61"/>
                          <id root="1.2.840.114350.1.13.470.2.7.3.678671.210" extension="1871VH"/>
                          <code code="612" codeSystem="2.16.840.1.113883.3.221.5"/>
                          <text>
                            <reference value="#coverage100"/>
                          </text>
                          <statusCode code="completed"/>
                          <performer typeCode="PRF">
                            <assignedEntity>
                              <id root="2.16.840.1.113883.6.300" extension="758"/>
                              <representedOrganization>
                                <name>BCBS PPO</name>
                              </representedOrganization>
                            </assignedEntity>
                          </performer>
                          <participant typeCode="COV">
                            <participantRole>
                              <id extension="WLU768M83547"/>
                              <code codeSystem="2.16.840.1.113883.5.111">
                                <originalText>Self<reference value="#coverage100relToSub"/></originalText>
                              </code>
                              <time>
                                <low value="20200101000000"/>
                                <high nullFlavor="NA"/>
                              </time>
                              <playingEntity>
                                <name nullFlavor="NI"/>
                                <sdtc:birthTime nullFlavor="UNK"/>
                              </playingEntity>
                            </participantRole>
                          </participant>
                          <entryRelationship typeCode="REFR">
                            <act classCode="ACT" moodCode="DEF">
                              <text>
                                <reference value="#coverage100PlanName"/>
                              </text>
                            </act>
                          </entryRelationship>
                        </act>
                      </entryRelationship>
                    </act>
                  </entry>
                </section>
              </component>
            </structuredBody>
          </component>
        </ClinicalDocument>
        """

        archive_path = self.tmp_path / "sample_insurance.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("IHE_XDM/Alex/DOC0001.XML", xml_content)

        parsed_dir = self.tmp_path / "parsed"
        raw_dir = self.tmp_path / "raw"
        raw_dir.mkdir()
        parsed_dir.mkdir()

        db_path = self.tmp_path / "db" / "health_records_ins.db"

        def _fake_load_paths():
            return {
                "raw_dir": raw_dir,
                "parsed_dir": parsed_dir,
                "db_path": db_path,
            }

        with patch.object(ingest.settings, "load_paths", _fake_load_paths):
            ingest.ingest_archive(self.schema_conn, archive_path)

            allergy_row = self.schema_conn.execute(
                """
                SELECT substance_code, status
                  FROM allergy
                """
            ).fetchone()
            self.assertEqual(allergy_row, ("70618", "active"))

            insurance_row = self.schema_conn.execute(
                """
                SELECT
                    payer_name,
                    payer_identifier,
                    plan_name,
                    group_number,
                    member_id,
                    subscriber_id,
                    relationship,
                    effective_date,
                    status
                  FROM insurance
                """
            ).fetchone()
            self.assertEqual(
                insurance_row,
                (
                    "BCBS PPO",
                    "758",
                    "Plan: BCBS PPO",
                    "1871VH",
                    "WLU768M83547",
                    "WLU768M83547",
                    "Self",
                    "20200101000000",
                    "completed",
                ),
            )

    def test_configure_logging_respects_cli_options(self) -> None:
        """Test that configure_logging respects CLI options."""
        log_file = self.tmp_path / "ingest.log"

        # Force existing handlers to make sure configure_logging replaces them.
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        dummy_handler = logging.StreamHandler()
        dummy_handler.setLevel(logging.CRITICAL)
        root_logger.addHandler(dummy_handler)

        args = ingest.parse_args(["--log-level", "debug", "--log-file", str(log_file)])
        self.assertEqual(args.log_level, "debug")
        self.assertEqual(args.log_file, log_file)

        ingest.configure_logging(args.log_level, args.log_file)

        logger = logging.getLogger("ingest")
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")

        # Stream handler (stderr) is harder to capture reliably;
        # ensure file logging works.
        self.assertTrue(log_file.exists())
        contents = log_file.read_text(encoding="utf-8")
        self.assertIn("debug message", contents)
        self.assertIn("info message", contents)
        self.assertIn("warning message", contents)
