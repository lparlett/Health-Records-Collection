from __future__ import annotations

# Purpose: Orchestrate ingestion of CCD archives into the project SQLite datastore.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Main ingestion workflow for CCD archives."""

import logging
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path
from typing import Any, Iterable

from lxml import etree
from db.schema import ensure_schema
from parsers import (
    parse_conditions,
    parse_encounters,
    parse_immunizations,
    parse_labs,
    parse_medications,
    parse_patient,
    parse_procedures,
    parse_progress_notes,
    parse_vitals,
)
from services.conditions import insert_conditions
from services.encounters import insert_encounters
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


def unzip_raw_files(zip_file: Path, destination: Path) -> None:
    """Unpack a CCD archive when the destination folder is empty.

    Args:
        zip_file: Source ZIP archive containing CCD documents.
        destination: Directory where the archive contents should be extracted.
    """
    if destination.exists() and any(destination.iterdir()):
        logger.info(
            "Skipping extraction for %s; destination %s is already populated.",
            zip_file.name,
            destination,
        )
        return

    destination.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_file, "r") as zip_ref:
            zip_ref.extractall(destination)
        logger.info("Extracted %s into %s.", zip_file.name, destination)
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
    medications = parse_medications(tree, CCD_NAMESPACE)
    labs = parse_labs(tree, CCD_NAMESPACE)
    conditions = parse_conditions(tree, CCD_NAMESPACE)
    procedures = parse_procedures(tree, CCD_NAMESPACE)
    progress_notes = parse_progress_notes(tree, CCD_NAMESPACE)
    vitals = parse_vitals(tree, CCD_NAMESPACE)
    immunizations = parse_immunizations(tree, CCD_NAMESPACE)

    return {
        "patient": patient,
        "encounters": encounters,
        "medications": medications,
        "labs": labs,
        "conditions": conditions,
        "procedures": procedures,
        "progress_notes": progress_notes,
        "vitals": vitals,
        "immunizations": immunizations,
    }


def ingest_archive(conn: sqlite3.Connection, archive_path: Path) -> None:
    """Ingest a single CCD archive into the database.

    Args:
        conn: Open SQLite connection.
        archive_path: ZIP archive to ingest.
    """
    destination = PARSED_DIR / archive_path.stem
    unzip_raw_files(archive_path, destination)

    for xml_file in destination.rglob("*.xml"):
        parsed = parse_ccd(xml_file)
        if not parsed:
            continue

        patient_data = parsed.get("patient")
        if not isinstance(patient_data, dict):
            logger.warning("Skipping %s due to missing patient section.", xml_file.name)
            continue

        given = str(patient_data.get("given", "")).strip()
        family = str(patient_data.get("family", "")).strip()
        if not (given or family):
            logger.warning("Skipping %s due to incomplete patient identity.", xml_file.name)
            continue

        pid = insert_patient(conn, patient_data, archive_path.name)
        insert_encounters(conn, pid, _as_record_list(parsed.get("encounters")))
        insert_conditions(conn, pid, _as_record_list(parsed.get("conditions")))
        insert_procedures(conn, pid, _as_record_list(parsed.get("procedures")))
        insert_medications(conn, pid, _as_record_list(parsed.get("medications")))
        insert_labs(conn, pid, _as_record_list(parsed.get("labs")))
        insert_vitals(conn, pid, _as_record_list(parsed.get("vitals")))
        insert_immunizations(conn, pid, _as_record_list(parsed.get("immunizations")))
        insert_progress_notes(conn, pid, _as_record_list(parsed.get("progress_notes")))
        conn.commit()
        logger.info("Ingested %s for patient %s %s.", xml_file.name, given, family)


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


def main() -> None:
    """CLI entry point for ingesting CCD archives."""
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO)

    with closing(init_db()) as conn:
        for archive_path in RAW_DIR.glob("*.zip"):
            ingest_archive(conn, archive_path)


if __name__ == "__main__":
    main()
