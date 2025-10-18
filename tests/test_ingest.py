from __future__ import annotations

from pathlib import Path
import zipfile

import logging
from unittest import mock

import ingest


def test_ingest_archive_records_data_source(
    tmp_path, schema_conn, monkeypatch
) -> None:
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

    archive_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("IHE_XDM/Lauren1/DOC0001.XML", xml_content)
        zf.writestr("IHE_XDM/Lauren1/METADATA.XML", metadata_xml)

    parsed_dir = tmp_path / "parsed"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    monkeypatch.setattr(ingest, "PARSED_DIR", parsed_dir)
    monkeypatch.setattr(ingest, "RAW_DIR", raw_dir)
    monkeypatch.setattr(ingest, "DB_PATH", Path(tmp_path / "db" / "health_records.db"))

    ingest.ingest_archive(schema_conn, archive_path)

    ds_row = schema_conn.execute(
        """
        SELECT
            id,
            original_filename,
            source_archive,
            document_created,
            repository_unique_id,
            document_hash,
            document_size,
            author_institution,
            attachment_id
          FROM data_source
        """
    ).fetchone()
    assert ds_row is not None
    (
        data_source_id,
        original_filename,
        source_archive,
        document_created,
        repository_unique_id,
        document_hash,
        document_size,
        author_institution,
        ds_attachment_id,
    ) = ds_row
    assert original_filename == "DOC0001.XML"
    assert source_archive == "sample.zip"
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
