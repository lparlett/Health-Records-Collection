from __future__ import annotations

# Purpose: Orchestrate ingestion of CCD archives into the project SQLite datastore.
# Author: Codex + Lauren
# Date: 2025-10-11
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Main ingestion workflow for CCD archives."""

import argparse
import logging
import mimetypes
import sqlite3
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterable
from typing import Any, Dict, Optional, Sequence

from lxml import etree
from db.schema import ensure_schema
from parsers import (
    parse_allergies,
    parse_conditions,
    parse_encounters,
    parse_immunizations,
    parse_insurance,
    parse_labs,
    parse_medications,
    parse_patient,
    parse_procedures,
    parse_progress_notes,
    parse_vitals,
)
from services.allergies import insert_allergies
from services.attachments import upsert_attachment
from services.common import clean_str
from services.conditions import insert_conditions
from services.data_sources import link_attachment, upsert_data_source
from services.encounters import insert_encounters
from services.insurance import upsert_insurance
from services.immunizations import insert_immunizations
from services.labs import insert_labs
from services.medications import insert_medications
from services.patient import insert_patient
from services.procedures import insert_procedures
from services.progress_notes import insert_progress_notes
from services.vitals import insert_vitals

logger = logging.getLogger(__name__)

RAW_DIR: Path = Path("data/raw")
PARSED_DIR: Path = Path("data/parsed")
DB_PATH: Path = Path("db/health_records.db")
SCHEMA_FILE: Path = Path("schema.sql")
CCD_NAMESPACE = {"hl7": "urn:hl7-org:v3"}

ParsedCCD = dict[str, Any]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the ingestion workflow."""
    parser = argparse.ArgumentParser(
        description="Ingest CCD archives into the SQLite datastore."
    )
    parser.add_argument(
        "--log-level",
        default="info",
        choices=("error", "warning", "info", "debug"),
        help=(
            "Logging verbosity. Use 'debug' for detailed troubleshooting output. "
            "Default is 'info', which avoids logging patient-identifying details."
        ),
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help=(
            "Optional file path to write logs. When omitted, logs emit to the console."
        ),
    )
    return parser.parse_args(argv)


def configure_logging(level_name: str, log_file: Path | None) -> None:
    """Configure logging outputs according to runtime preferences."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    handlers: list[logging.Handler] = []
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def init_db() -> sqlite3.Connection:
    """Initialise the SQLite connection and ensure schema alignment.

    Returns:
        sqlite3.Connection: Live connection ready for ingestion.

    Raises:
        sqlite3.Error: If the database connection cannot be established.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    if SCHEMA_FILE.exists():
        try:
            schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover
            logger.error("Failed to read schema file %s: %s", SCHEMA_FILE, exc)
            raise
        conn.executescript(schema_sql)

    ensure_schema(conn)
    return conn


def _xpath_elements(
    node: etree._Element | etree._ElementTree,
    expression: str,
    ns: dict[str, str],
) -> list[etree._Element]:
    """Return a list of element nodes extracted via XPath."""
    if isinstance(node, etree._ElementTree):
        node = node.getroot()
    if node is None or not hasattr(node, "xpath"):
        return []
    raw = node.xpath(expression, namespaces=ns)
    elements: list[etree._Element] = []
    if isinstance(raw, etree._Element):
        elements.append(raw)
    elif isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
        for item in raw:
            if isinstance(item, etree._Element):
                elements.append(item)
    return elements


def unzip_raw_files(zip_file: Path, destination: Path) -> None:
    """Unpack a CCD archive when the destination folder is empty.

    Args:
        zip_file: Source ZIP archive containing CCD documents.
        destination: Directory where the archive contents should be extracted.
    """
    if destination.exists() and any(destination.iterdir()):
        logger.info(
            "Skipping extraction for %s; destination already populated.",
            zip_file.name,
        )
        logger.debug("Destination %s is already populated.", destination)
        return

    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_file, "r") as zip_ref:
            zip_ref.extractall(destination)
        logger.info("Extracted %s.", zip_file.name)
        logger.debug("Extracted %s into %s.", zip_file.name, destination)
    except (zipfile.BadZipFile, OSError) as exc:
        logger.warning("Failed to extract %s: %s", zip_file, exc)


def parse_ccd(xml_file: Path) -> ParsedCCD:
    """Parse a CCD XML document into structured collections.

    Args:
        xml_file: Path to the CCD XML document.

    Returns:
        ParsedCCD: A dictionary with parsed patient and clinical sections.
    """
    try:
        tree = etree.parse(str(xml_file))
    except (OSError, etree.XMLSyntaxError) as exc:
        logger.warning("Skipping malformed XML %s: %s", xml_file.name, exc)
        return {}

    patient = parse_patient(tree, CCD_NAMESPACE)
    encounters = parse_encounters(tree, CCD_NAMESPACE)
    allergies = parse_allergies(tree, CCD_NAMESPACE)
    medications = parse_medications(tree, CCD_NAMESPACE)
    labs = parse_labs(tree, CCD_NAMESPACE)
    conditions = parse_conditions(tree, CCD_NAMESPACE)
    procedures = parse_procedures(tree, CCD_NAMESPACE)
    progress_notes = parse_progress_notes(tree, CCD_NAMESPACE)
    vitals = parse_vitals(tree, CCD_NAMESPACE)
    immunizations = parse_immunizations(tree, CCD_NAMESPACE)
    insurance = parse_insurance(tree, CCD_NAMESPACE)

    return {
        "patient": patient,
        "encounters": encounters,
        "allergies": allergies,
        "medications": medications,
        "labs": labs,
        "conditions": conditions,
        "procedures": procedures,
        "progress_notes": progress_notes,
        "vitals": vitals,
        "immunizations": immunizations,
        "insurance": insurance,
    }


def ingest_archive(conn: sqlite3.Connection, archive_path: Path) -> None:
    """Ingest a single CCD archive into the database.

    Args:
        conn: Open SQLite connection.
        archive_path: ZIP archive to ingest.
    """
    destination = PARSED_DIR / archive_path.stem
    unzip_raw_files(archive_path, destination)

    metadata_lookup = _load_metadata(destination)

    for xml_file in destination.rglob("*.xml"):
        if xml_file.name.lower() == "metadata.xml":
            logger.debug("Skipping metadata descriptor %s.", xml_file)
            continue
        parsed = parse_ccd(xml_file)
        if not parsed:
            continue

        patient_data = parsed.get("patient")
        if not isinstance(patient_data, dict):
            logger.warning("Skipping %s due to missing patient section.", xml_file.name)
            continue

        given = clean_str(patient_data.get("given"))
        family = clean_str(patient_data.get("family"))
        if not (given or family):
            logger.warning("Skipping %s due to incomplete patient identity.", xml_file.name)
            continue

        try:
            meta_key = str(xml_file.resolve()).lower()
            data_source_id = upsert_data_source(
                conn,
                xml_file,
                source_archive=archive_path.name,
                metadata=metadata_lookup.get(meta_key),
            )
        except (OSError, sqlite3.DatabaseError) as exc:
            logger.warning(
                "Skipping %s due to provenance capture error: %s",
                xml_file.name,
                exc,
            )
            continue

        record_metadata = {
            "data_source_id": data_source_id,
            "source_archive": archive_path.name,
            "source_document": xml_file.name,
        }
        patient_record = {**patient_data, **record_metadata}

        pid = insert_patient(conn, patient_record)
        attachment_id = _record_attachment(
            conn,
            patient_id=pid,
            data_source_id=data_source_id,
            file_path=xml_file,
        )
        if attachment_id is not None:
            try:
                link_attachment(conn, data_source_id, attachment_id)
            except sqlite3.DatabaseError as exc:
                logger.warning(
                    "Failed to link attachment %s to data source %s: %s",
                    attachment_id,
                    data_source_id,
                    exc,
                )
        insert_encounters(
            conn,
            pid,
            _annotate_records(_as_record_list(parsed.get("encounters")), record_metadata),
        )
        insert_conditions(
            conn,
            pid,
            _annotate_records(_as_record_list(parsed.get("conditions")), record_metadata),
        )
        insert_allergies(
            conn,
            pid,
            _annotate_records(_as_record_list(parsed.get("allergies")), record_metadata),
        )
        insert_procedures(
            conn,
            pid,
            _annotate_records(_as_record_list(parsed.get("procedures")), record_metadata),
        )
        insert_medications(
            conn,
            pid,
            _annotate_records(_as_record_list(parsed.get("medications")), record_metadata),
        )
        insert_labs(
            conn,
            pid,
            _annotate_records(_as_record_list(parsed.get("labs")), record_metadata),
        )
        insert_vitals(
            conn,
            pid,
            _annotate_records(_as_record_list(parsed.get("vitals")), record_metadata),
        )
        insert_immunizations(
            conn,
            pid,
            _annotate_records(_as_record_list(parsed.get("immunizations")), record_metadata),
        )
        insert_progress_notes(
            conn,
            pid,
            _annotate_records(_as_record_list(parsed.get("progress_notes")), record_metadata),
        )
        upsert_insurance(
            conn,
            pid,
            _annotate_records(_as_record_list(parsed.get("insurance")), record_metadata),
        )
        conn.commit()
        logger.info("Ingested %s.", xml_file.name)
        logger.debug(
            "Ingested %s for patient %s %s.",
            xml_file.name,
            given,
            family,
        )


def _load_metadata(root: Path) -> dict[str, dict[str, Any]]:
    """Return a mapping of document path -> metadata extracted from METADATA.XML."""
    metadata: dict[str, dict[str, Any]] = {}
    ns = {"rim": "urn:oasis:names:tc:ebxml-regrep:xsd:rim:3.0"}
    for metadata_path in root.rglob("METADATA.XML"):
        try:
            tree = etree.parse(str(metadata_path))
        except (OSError, etree.XMLSyntaxError) as exc:
            logger.warning("Unable to parse metadata %s: %s", metadata_path, exc)
            continue
        base_dir = metadata_path.parent.resolve()
        for extrinsic in _xpath_elements(tree, "//rim:ExtrinsicObject", ns):
            slots = _extract_slot_values(extrinsic, ns)
            uris = slots.get("URI") or []
            if not uris:
                continue

            meta_payload = {
                "document_created": _normalise_creation_time(_first(slots.get("creationTime"))),
                "repository_unique_id": _first(slots.get("repositoryUniqueId")),
                "document_hash": _first(slots.get("hash")),
                "document_size": _to_int(_first(slots.get("size"))),
                "author_institution": _extract_author_institution(extrinsic, ns),
            }

            for uri in uris:
                doc_path = (base_dir / uri).resolve()
                # copy to avoid sharing between documents
                metadata[str(doc_path).lower()] = {
                    key: value for key, value in meta_payload.items() if value is not None
                }
    return metadata


def _extract_slot_values(node: etree._Element, ns: dict[str, str]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for slot in _xpath_elements(node, "rim:Slot", ns):
        name = slot.get("name")
        if not name:
            continue
        entries = [
            (value.text or "").strip()
            for value in _xpath_elements(slot, "rim:ValueList/rim:Value", ns)
            if value.text and value.text.strip()
        ]
        if entries:
            values[name] = entries
    return values


def _extract_author_institution(node: etree._Element, ns: dict[str, str]) -> Optional[str]:
    for classification in _xpath_elements(node, "rim:Classification", ns):
        for slot in _xpath_elements(classification, "rim:Slot", ns):
            if slot.get("name") != "authorInstitution":
                continue
            entries = [
                (value.text or "").strip()
                for value in _xpath_elements(slot, "rim:ValueList/rim:Value", ns)
                if value.text and value.text.strip()
            ]
            if entries:
                return entries[0]
    return None


def _first(values: Optional[list[str]]) -> Optional[str]:
    if not values:
        return None
    return values[0]


def _to_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _normalise_creation_time(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        dt = datetime.strptime(raw, "%Y%m%d%H%M%S")
    except ValueError:
        return raw
    return dt.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")


def _record_attachment(
    conn: sqlite3.Connection,
    *,
    patient_id: int,
    data_source_id: int,
    file_path: Path,
) -> Optional[int]:
    """Persist attachment metadata for the raw document."""
    try:
        relative_path = _relative_attachment_path(file_path)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Unable to resolve attachment path for %s: %s", file_path, exc)
        relative_path = file_path

    mime_type, _ = mimetypes.guess_type(str(file_path))
    description = f"Raw CCD document ({file_path.name})"

    try:
        attachment_id = upsert_attachment(
            conn,
            patient_id=patient_id,
            data_source_id=data_source_id,
            file_path=relative_path,
            mime_type=mime_type or "application/xml",
            description=description,
        )
    except sqlite3.DatabaseError as exc:
        logger.warning("Failed to record attachment for %s: %s", file_path, exc)
        return None
    return attachment_id

def _relative_attachment_path(file_path: Path) -> Path:
    """Return a path suitable for storage (relative to repo root when possible)."""
    try:
        return file_path.relative_to(Path.cwd())
    except ValueError:
        return file_path


def _as_record_list(candidate: Any) -> list[dict[str, Any]]:
    """Coerce parser output to a list of record dictionaries.

    Args:
        candidate: Potentially iterable parser output.

    Returns:
        list[dict[str, Any]]: Sanitised list ready for database persistence.
    """
    if isinstance(candidate, list):
        return [item for item in candidate if isinstance(item, dict)]

    if isinstance(candidate, Iterable) and not isinstance(candidate, (bytes, str)):
        return [item for item in candidate if isinstance(item, dict)]

    return []


def _annotate_records(
    records: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attach ingestion metadata to each record."""
    if not records:
        return []
    return [{**record, **metadata} for record in records]


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entry point for ingesting CCD archives."""
    args = parse_args(argv)
    configure_logging(args.log_level, args.log_file)
    logger.debug(
        "Logging configured: level=%s, destination=%s",
        args.log_level,
        args.log_file or "stdout",
    )

    with closing(init_db()) as conn:
        for archive_path in RAW_DIR.glob("*.zip"):
            ingest_archive(conn, archive_path)


if __name__ == "__main__":
    main()
