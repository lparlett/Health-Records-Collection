from __future__ import annotations

from pathlib import Path
import zipfile

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

    archive_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(archive_path, "w") as zf:
        zf.writestr("document.xml", xml_content)

    parsed_dir = tmp_path / "parsed"
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    monkeypatch.setattr(ingest, "PARSED_DIR", parsed_dir)
    monkeypatch.setattr(ingest, "RAW_DIR", raw_dir)
    monkeypatch.setattr(ingest, "DB_PATH", Path(tmp_path / "db" / "health_records.db"))

    ingest.ingest_archive(schema_conn, archive_path)

    ds_row = schema_conn.execute(
        "SELECT id, original_filename, source_archive FROM data_source"
    ).fetchone()
    assert ds_row is not None
    data_source_id, original_filename, source_archive = ds_row
    assert original_filename == "document.xml"
    assert source_archive == "sample.zip"

    patient_row = schema_conn.execute(
        "SELECT data_source_id FROM patient"
    ).fetchone()
    assert patient_row == (data_source_id,)
