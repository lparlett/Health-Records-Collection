# Purpose: Orchestrate ingestion of CCD archives into the project SQLite datastore.
# Author: Codex + Lauren
# Date: 2025-10-11
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.
"""Main ingestion workflow for CCD archives."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import logging
import mimetypes
from pathlib import Path
import sqlite3
import zipfile
from typing import TYPE_CHECKING, Any, Callable, Optional, Sequence

import yaml  # type: ignore
from defusedxml.lxml import parse as safe_parse  # type: ignore
from defusedxml.common import DefusedXmlException as XMLSyntaxError
from lxml import etree  # type: ignore # nosec import_lxml
from lxml.etree import _Element, _ElementTree  # type: ignore # nosec import_lxml


from health_records_collection import settings
from health_records_collection.db.schema import ensure_schema
from health_records_collection.parsers import (
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
from health_records_collection.security import encryption
from health_records_collection.services.allergies import insert_allergies
from health_records_collection.services.archives import (
    archive_was_ingested,
    register_ingested_archive,
)
from health_records_collection.services.attachments import upsert_attachment
from health_records_collection.services.common import clean_str
from health_records_collection.services.conditions import insert_conditions
from health_records_collection.services.data_sources import (
    link_attachment,
    upsert_data_source,
)
from health_records_collection.services.encounters import insert_encounters
from health_records_collection.services.immunizations import insert_immunizations
from health_records_collection.services.insurance import upsert_insurance
from health_records_collection.services.labs import insert_labs
from health_records_collection.services.medications import insert_medications
from health_records_collection.services.patient import insert_patient
from health_records_collection.services.procedures import insert_procedures
from health_records_collection.services.progress_notes import insert_progress_notes
from health_records_collection.services.vitals import insert_vitals

if TYPE_CHECKING:
    # Use cleaner type aliases for type hints
    EtreeElement = _Element  # type: ignore
    EtreeElementTree = _ElementTree  # type: ignore
else:  # pragma: no cover - runtime-only fallback for typing
    EtreeElement = _Element  # type: ignore
    EtreeElementTree = _ElementTree  # type: ignore

logger = logging.getLogger(__name__)

SCHEMA_FILE: Path = Path("schema.sql")
CCD_NAMESPACE = {"hl7": "urn:hl7-org:v3"}

ParsedCCD = dict[str, Any]

SectionInserter = Callable[
    [sqlite3.Connection, int, Sequence[dict[str, Any]]],
    Any,
]
SECTION_INSERTORS: tuple[tuple[str, SectionInserter], ...] = (
    ("encounters", insert_encounters),
    ("conditions", insert_conditions),
    ("allergies", insert_allergies),
    ("procedures", insert_procedures),
    ("medications", insert_medications),
    ("labs", insert_labs),
    ("vitals", insert_vitals),
    ("immunizations", insert_immunizations),
    ("progress_notes", insert_progress_notes),
    ("insurance", upsert_insurance),
)


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
        OSError: If the schema file cannot be read.
    """
    paths = settings.load_paths()
    db_path = paths["db_path"]
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
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
    node: EtreeElement | EtreeElementTree,
    expression: str,
    ns: dict[str, str],
) -> list[EtreeElement]:
    """Return a list of element nodes extracted via XPath."""
    if isinstance(node, EtreeElementTree):
        node = node.getroot()
    if node is None or not hasattr(node, "xpath"):
        return []
    raw = node.xpath(expression, namespaces=ns)
    elements: list[EtreeElement] = []
    if isinstance(raw, EtreeElement):
        elements.append(raw)
    elif isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)):
        for item in raw:
            if isinstance(item, EtreeElement):
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
        tree = safe_parse(str(xml_file))  # safe_parse mitigates XML entity attacks.
    except (OSError, XMLSyntaxError) as exc:
        logger.warning("Skipping malformed XML %s: %s", xml_file.name, exc)
        return {}

    try:
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
    except RuntimeError as exc:
        logger.error(
            "Error parsing CCD sections from %s: %s. "
            "Document may have missing or malformed sections.",
            xml_file.name,
            exc,
        )
        return {}

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


def ingest_archive(
    conn: sqlite3.Connection,
    archive_path: Path,
    *,
    archive_sha256: Optional[str] = None,
) -> None:
    """Ingest a single CCD archive into the database.

    Args:
        conn: Open SQLite connection.
        archive_path: ZIP archive to ingest.
        archive_sha256: Optional precomputed archive hash to avoid re-hashing.
    """
    archive_sha256 = _resolve_archive_hash(archive_path, archive_sha256)
    if archive_sha256 is None:
        return
    if _archive_previously_ingested(conn, archive_sha256, archive_path):
        return

    paths = settings.load_paths()
    ingestion_settings = _load_ingestion_settings()

    destination = paths["parsed_dir"] / archive_path.stem
    unzip_raw_files(archive_path, destination)

    metadata_lookup = _load_metadata(destination)

    try:
        data_source_ids = _ingest_documents_from_archive(
            conn,
            archive_path,
            destination,
            metadata_lookup,
            archive_name=archive_path.name,
        )
    except (OSError, sqlite3.Error, XMLSyntaxError, etree.XMLSyntaxError):
        logger.exception("Ingestion failed for archive %s.", archive_path.name)
        raise

    _register_archive_sources(conn, archive_path.name, archive_sha256, data_source_ids)
    delete_archive_flag, delete_non_xml_flag = _determine_cleanup_flags(
        archive_path, paths, ingestion_settings
    )

    _finalise_ingestion_artifacts(
        archive_path,
        destination,
        delete_archive=delete_archive_flag,
        delete_non_xml=delete_non_xml_flag,
    )


def _resolve_archive_hash(
    archive_path: Path, archive_sha256: Optional[str]
) -> Optional[str]:
    """Return a SHA-256 hash for the archive, logging failures."""
    if archive_sha256:
        return archive_sha256
    try:
        return _compute_archive_sha256(archive_path)
    except OSError as exc:
        logger.warning("Unable to hash %s: %s", archive_path, exc)
        return None


def _archive_previously_ingested(
    conn: sqlite3.Connection, archive_sha256: str, archive_path: Path
) -> bool:
    """Return True when the provided archive hash was already ingested."""
    existing_archive = archive_was_ingested(conn, archive_sha256)
    if not existing_archive:
        return False
    logger.info(
        "Skipping %s; previously ingested on %s.",
        archive_path.name,
        existing_archive.get("last_ingested_at")
        or existing_archive.get("first_ingested_at"),
    )
    return True


def _load_ingestion_settings() -> dict[str, Any]:
    """Return merged ingestion settings from defaults and user config."""
    ingestion_settings: dict[str, Any] = {
        **getattr(settings, "DEFAULT_SETTINGS", {}).get("ingestion", {})
    }
    load_settings_fn = getattr(settings, "load_settings", None)
    if callable(load_settings_fn):
        try:
            loaded_settings = load_settings_fn()
        except (IOError, yaml.YAMLError):  # pragma: no cover - defensive fallback
            logger.debug("Falling back to default ingestion settings.", exc_info=True)
        else:
            if isinstance(loaded_settings, dict) and "ingestion" in loaded_settings:
                ingestion_settings = loaded_settings["ingestion"]
    return ingestion_settings


def _register_archive_sources(
    conn: sqlite3.Connection,
    archive_name: str,
    archive_sha256: str,
    data_source_ids: Sequence[int],
) -> int:
    """Create archive row and link related data sources."""
    archive_id = register_ingested_archive(conn, archive_name, archive_sha256)
    if data_source_ids:
        conn.executemany(
            "UPDATE data_source SET source_archive_id = ? WHERE id = ?",
            [(archive_id, ds_id) for ds_id in data_source_ids],
        )
        conn.commit()
    logger.debug(
        "Registered archive %s with hash %s (id=%s).",
        archive_name,
        archive_sha256,
        archive_id,
    )
    return archive_id


def _determine_cleanup_flags(
    archive_path: Path,
    paths: dict[str, Path],
    ingestion_settings: dict[str, Any],
) -> tuple[bool, bool]:
    """Return cleanup preferences derived from settings."""
    delete_archive_flag = bool(ingestion_settings.get("delete_uploaded_archives", True))
    delete_non_xml_flag = bool(
        ingestion_settings.get("delete_unencrypted_extracted_files", True)
    )
    if delete_archive_flag:
        try:
            if archive_path.resolve().parent != paths["raw_dir"].resolve():
                delete_archive_flag = False
        except OSError:
            delete_archive_flag = False
    return delete_archive_flag, delete_non_xml_flag


def _delete_non_xml_files(destination: Path) -> int:
    """Remove non-XML, non-encrypted files from an extracted archive directory."""
    if not destination.exists():
        return 0
    removed = 0
    for file_path in destination.rglob("*"):
        if not file_path.is_file():
            continue
        suffixes = [suffix.lower() for suffix in file_path.suffixes]
        if ".xml" in suffixes or ".enc" in suffixes:
            continue
        try:
            file_path.unlink()
            removed += 1
        except OSError as exc:
            logger.warning("Failed to delete %s: %s", file_path, exc)
    for directory in sorted(
        (path for path in destination.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()
        except OSError:
            continue
    return removed


def _finalise_ingestion_artifacts(
    archive_path: Path,
    extraction_root: Path,
    *,
    delete_archive: bool,
    delete_non_xml: bool,
) -> None:
    """Apply configured cleanup steps after a successful ingestion."""
    if delete_non_xml:
        removed = _delete_non_xml_files(extraction_root)
        if removed:
            logger.debug(
                "Removed %s non-XML file(s) from %s after ingestion.",
                removed,
                extraction_root,
            )
    if delete_archive and archive_path.exists():
        try:
            archive_path.unlink()
            logger.debug("Deleted ingested archive %s.", archive_path.name)
        except OSError as exc:
            logger.warning("Unable to delete archive %s: %s", archive_path, exc)


def _compute_archive_sha256(archive_path: Path) -> str:
    """Return the SHA-256 hash for the provided archive path."""
    hasher = hashlib.sha256()
    with archive_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _ingest_documents_from_archive(
    conn: sqlite3.Connection,
    archive_path: Path,
    destination: Path,
    metadata_lookup: dict[str, dict[str, Any]],
    *,
    archive_name: str,
) -> list[int]:
    """Process all CCD documents within a prepared archive directory."""
    logger.debug(
        "Scanning %s for CCD documents extracted from %s.",
        destination,
        archive_path,
    )
    data_source_ids: set[int] = set()
    for xml_file in _iter_ccd_documents(destination):
        data_source_id = _process_document(
            conn,
            xml_file,
            metadata_lookup,
            archive_name=archive_name,
        )
        if data_source_id is not None:
            data_source_ids.add(data_source_id)
    return list(data_source_ids)


def _iter_ccd_documents(destination: Path) -> Iterable[Path]:
    """Yield each CCD document path within the extracted archive."""
    for candidate in destination.rglob("*"):
        if not candidate.is_file():
            continue
        if candidate.suffix.lower() != ".xml":
            continue
        if candidate.name.lower() == "metadata.xml":
            logger.debug("Skipping metadata descriptor %s.", candidate)
            continue
        yield candidate


def _process_document(
    conn: sqlite3.Connection,
    xml_file: Path,
    metadata_lookup: dict[str, dict[str, Any]],
    *,
    archive_name: str,
) -> Optional[int]:
    """Ingest a single CCD document and return its data source ID."""
    parsed = parse_ccd(xml_file)
    if not parsed:
        return None

    patient_payload = _validate_patient_payload(parsed, xml_file)
    if patient_payload is None:
        return None
    patient_data, given, family = patient_payload

    data_source_id = _create_data_source_entry(conn, xml_file, metadata_lookup)
    if data_source_id is None:
        return None

    record_metadata = {
        "data_source_id": data_source_id,
        "source_archive": archive_name,
        "source_document": xml_file.name,
    }
    patient_record = {**patient_data, **record_metadata}

    patient_id = insert_patient(conn, patient_record)
    _link_attachment_to_data_source(conn, patient_id, data_source_id, xml_file)
    _persist_patient_sections(conn, patient_id, parsed, record_metadata)
    conn.commit()

    logger.info("Ingested %s.", xml_file.name)
    logger.debug("Ingested %s for patient %s %s.", xml_file.name, given, family)
    return data_source_id


def _validate_patient_payload(
    parsed: ParsedCCD, xml_file: Path
) -> Optional[tuple[dict[str, Any], Optional[str], Optional[str]]]:
    """Ensure the parsed document contains identifiable patient data."""
    patient_data = parsed.get("patient")
    if not isinstance(patient_data, dict):
        logger.warning("Skipping %s due to missing patient section.", xml_file.name)
        return None

    given = clean_str(patient_data.get("given"))
    family = clean_str(patient_data.get("family"))
    if not (given or family):
        logger.warning("Skipping %s due to incomplete patient identity.", xml_file.name)
        return None

    return patient_data, given, family


def _create_data_source_entry(
    conn: sqlite3.Connection,
    xml_file: Path,
    metadata_lookup: dict[str, dict[str, Any]],
) -> Optional[int]:
    """Persist provenance information for a CCD document."""
    try:
        meta_key = str(xml_file.resolve()).lower()
        return upsert_data_source(
            conn,
            xml_file,
            metadata=metadata_lookup.get(meta_key),
        )
    except (OSError, sqlite3.DatabaseError) as exc:
        logger.warning(
            "Skipping %s due to provenance capture error: %s",
            xml_file.name,
            exc,
        )
        return None


def _persist_patient_sections(
    conn: sqlite3.Connection,
    patient_id: int,
    parsed: ParsedCCD,
    metadata: dict[str, Any],
) -> None:
    """Insert or update all supported patient sections for a CCD document."""
    for section_name, inserter in SECTION_INSERTORS:
        records = _annotate_records(
            _as_record_list(parsed.get(section_name)),
            metadata,
        )
        if not records:
            continue
        inserter(conn, patient_id, records)


def _link_attachment_to_data_source(
    conn: sqlite3.Connection,
    patient_id: int,
    data_source_id: int,
    xml_file: Path,
) -> None:
    """Encrypt raw documents and associate them with their data sources."""
    attachment_id = _record_attachment(
        conn,
        patient_id=patient_id,
        data_source_id=data_source_id,
        file_path=xml_file,
    )
    if attachment_id is None:
        return
    try:
        link_attachment(conn, data_source_id, attachment_id)
    except sqlite3.DatabaseError as exc:
        logger.warning(
            "Failed to link attachment %s to data source %s: %s",
            attachment_id,
            data_source_id,
            exc,
        )


def _load_metadata(root: Path) -> dict[str, dict[str, Any]]:
    """Return a mapping of document path -> metadata extracted from METADATA.XML."""
    metadata: dict[str, dict[str, Any]] = {}
    ns = {"rim": "urn:oasis:names:tc:ebxml-regrep:xsd:rim:3.0"}
    for metadata_path in root.rglob("METADATA.XML"):
        try:
            tree = safe_parse(
                str(metadata_path)
            )  # Using defusedxml for secure XML parsing.
        except (OSError, XMLSyntaxError) as exc:
            logger.warning("Unable to parse metadata %s: %s", metadata_path, exc)
            continue
        base_dir = metadata_path.parent.resolve()
        for extrinsic in _xpath_elements(tree, "//rim:ExtrinsicObject", ns):
            slots = _extract_slot_values(extrinsic, ns)
            uris = slots.get("URI") or []
            if not uris:
                continue

            meta_payload = {
                "document_created": _normalise_creation_time(
                    _first(slots.get("creationTime"))
                ),
                "repository_unique_id": _first(slots.get("repositoryUniqueId")),
                "document_hash": _first(slots.get("hash")),
                "document_size": _to_int(_first(slots.get("size"))),
                "author_institution": _extract_author_institution(extrinsic, ns),
            }

            for uri in uris:
                doc_path = (base_dir / uri).resolve()
                # copy to avoid sharing between documents
                metadata[str(doc_path).lower()] = {
                    key: value
                    for key, value in meta_payload.items()
                    if value is not None
                }
    return metadata


def _extract_slot_values(
    node: etree._Element, ns: dict[str, str]
) -> dict[str, list[str]]:
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


def _extract_author_institution(
    node: etree._Element, ns: dict[str, str]
) -> Optional[str]:
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
    manager = encryption.get_encryption_manager()
    try:
        secure_path = manager.encrypt_file(file_path)
    except (OSError, RuntimeError, ValueError) as exc:  # pragma: no cover - defensive
        logger.warning("Unable to encrypt attachment %s: %s", file_path, exc)
        secure_path = file_path
    try:
        relative_path = _relative_attachment_path(secure_path)
    except ValueError as exc:  # pragma: no cover - defensive
        logger.warning("Unable to resolve attachment path for %s: %s", secure_path, exc)
        relative_path = secure_path

    mime_type, _ = mimetypes.guess_type(str(secure_path))
    description = f"Raw CCD document ({secure_path.name})"

    try:
        attachment_id = upsert_attachment(
            conn,
            patient_id=patient_id,
            data_source_id=data_source_id,
            file_path=relative_path,
            mime_type=mime_type or "application/octet-stream",
            description=description,
        )
    except sqlite3.DatabaseError as exc:
        logger.warning("Failed to record attachment for %s: %s", secure_path, exc)
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
        paths = settings.load_paths()
        raw_dir = paths["raw_dir"]
        for archive_path in raw_dir.glob("*.zip"):
            ingest_archive(conn, archive_path)


if __name__ == "__main__":
    main()
