from __future__ import annotations

from pathlib import Path
import zipfile
import hashlib

import logging
from unittest import mock

import ingest


def _create_sample_archive(tmp_path: Path, filename: str = "sample.zip") -> Path:
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


def test_ingest_archive_records_data_source(
    tmp_path, schema_conn, monkeypatch
) -> None:
    archive_path = _create_sample_archive(tmp_path, "sample.zip")

    parsed_dir = tmp_path / "parsed"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    parsed_dir.mkdir()

    db_path = tmp_path / "db" / "health_records.db"

    def _fake_load_paths():
        return {
            "raw_dir": raw_dir,
            "parsed_dir": parsed_dir,
            "db_path": db_path,
        }

    monkeypatch.setattr(ingest.settings, "load_paths", _fake_load_paths)

    ingest.ingest_archive(schema_conn, archive_path)

    ds_row = schema_conn.execute(
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
    assert ds_row is not None
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
    assert original_filename == "DOC0001.XML"
    assert source_archive_name == "sample.zip"
    assert source_archive_id is not None
    assert source_archive_ingest_count == 1
    assert document_created == "2025-01-01T12:34:56Z"
    assert repository_unique_id == "urn:repository:123"
    assert document_hash == "abc123hash"
    assert document_size == 512
    assert author_institution == "Unit Test Hospital"

    patient_row = schema_conn.execute(
        "SELECT data_source_id FROM patient"
    ).fetchone()
    assert patient_row == (data_source_id,)

    patient_count = schema_conn.execute(
        "SELECT COUNT(*) FROM patient"
    ).fetchone()[0]
    assert patient_count == 1

    attachment_row = schema_conn.execute(
        """
        SELECT id, patient_id, file_path, data_source_id, mime_type
          FROM attachment
        """
    ).fetchone()
    assert attachment_row is not None
    attachment_id, attachment_patient_id, attachment_path, attachment_ds_id, attachment_mime = attachment_row
    assert attachment_patient_id == schema_conn.execute("SELECT id FROM patient").fetchone()[0]
    assert attachment_path.endswith("DOC0001.XML")
    assert attachment_ds_id == data_source_id
    assert attachment_mime in ("text/xml", "application/xml")
    assert ds_attachment_id == attachment_id

    attachment_count = schema_conn.execute(
        "SELECT COUNT(*) FROM attachment"
    ).fetchone()[0]
    assert attachment_count == 1

    registry_row = schema_conn.execute(
        """
        SELECT id, archive_name, archive_sha256, ingest_count
          FROM ingested_archive
        """
    ).fetchone()
    assert registry_row is not None
    archive_id, archive_name, archive_hash, ingest_count = registry_row
    assert archive_name == "sample.zip"
    assert ingest_count == 1
    expected_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    assert archive_hash == expected_hash
    assert archive_id == source_archive_id


def test_ingest_archive_skips_duplicate_hash(
    tmp_path, schema_conn, monkeypatch
) -> None:
    archive_path = _create_sample_archive(tmp_path, "duplicate.zip")

    parsed_dir = tmp_path / "parsed"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    parsed_dir.mkdir()

    db_path = tmp_path / "db" / "records.db"

    def _fake_load_paths():
        return {
            "raw_dir": raw_dir,
            "parsed_dir": parsed_dir,
            "db_path": db_path,
        }

    monkeypatch.setattr(ingest.settings, "load_paths", _fake_load_paths)

    ingest.ingest_archive(schema_conn, archive_path)

    ds_count, ingest_count = schema_conn.execute(
        "SELECT COUNT(*), MAX(ingest_count) FROM data_source CROSS JOIN ingested_archive"
    ).fetchone()
    assert ds_count == 1
    assert ingest_count == 1

    ingest.ingest_archive(schema_conn, archive_path)

    ds_count_after = schema_conn.execute("SELECT COUNT(*) FROM data_source").fetchone()[0]
    ingest_count_after = schema_conn.execute(
        "SELECT ingest_count FROM ingested_archive WHERE archive_name = ?",
        ("duplicate.zip",),
    ).fetchone()[0]
    assert ds_count_after == 1
    assert ingest_count_after == 1

def test_ingest_archive_persists_allergies_and_insurance(
    tmp_path,
    schema_conn,
    monkeypatch,
) -> None:
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

    archive_path = tmp_path / "sample_insurance.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("IHE_XDM/Alex/DOC0001.XML", xml_content)

    parsed_dir = tmp_path / "parsed"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    parsed_dir.mkdir()

    db_path = tmp_path / "db" / "health_records_ins.db"

    def _fake_load_paths():
        return {
            "raw_dir": raw_dir,
            "parsed_dir": parsed_dir,
            "db_path": db_path,
        }

    monkeypatch.setattr(ingest.settings, "load_paths", _fake_load_paths)

    ingest.ingest_archive(schema_conn, archive_path)

    allergy_row = schema_conn.execute(
        """
        SELECT substance_code, status
          FROM allergy
        """
    ).fetchone()
    assert allergy_row == ("70618", "active")

    insurance_row = schema_conn.execute(
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
    assert insurance_row == (
        "BCBS PPO",
        "758",
        "Plan: BCBS PPO",
        "1871VH",
        "WLU768M83547",
        "WLU768M83547",
        "Self",
        "20200101000000",
        "completed",
    )


def test_configure_logging_respects_cli_options(tmp_path, monkeypatch):
    """Ensure CLI logging configuration respects verbosity settings."""
    log_file = tmp_path / "ingest.log"

    # Force existing handlers to make sure configure_logging replaces them.
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    dummy_handler = logging.StreamHandler()
    dummy_handler.setLevel(logging.CRITICAL)
    root_logger.addHandler(dummy_handler)

    args = ingest.parse_args(
        ["--log-level", "debug", "--log-file", str(log_file)]
    )
    assert args.log_level == "debug"
    assert args.log_file == log_file

    ingest.configure_logging(args.log_level, args.log_file)

    logger = logging.getLogger("ingest")
    logger.debug("debug message")
    logger.info("info message")
    logger.warning("warning message")

    # Stream handler (stderr) is harder to capture reliably; ensure file logging works.
    assert log_file.exists()
    contents = log_file.read_text(encoding="utf-8")
    assert "debug message" in contents
    assert "info message" in contents
    assert "warning message" in contents
