# Purpose: Streamlit workflow for secure ZIP uploads and ingestion triggers.
# Author: Codex + Lauren
# Date: 2025-10-29
# Reviewed by: Lauren
# Review date: 2025-10-29
# Tests: Manual Streamlit verification; tests/test_upload_components.py
# AI-assisted: Portions of this module were generated with AI assistance.
"""Streamlit components enabling ZIP uploads that invoke the ingestion pipeline."""

from __future__ import annotations

import hashlib
import logging
import re
import shutil
import sqlite3
import unicodedata
from pathlib import Path
from typing import Callable, Dict, List, Optional

import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile
import zipfile

from health_records_collection.ingest import ingest_archive
from health_records_collection.services.archives import archive_was_ingested

logger = logging.getLogger(__name__)

RAW_ARCHIVE_DIR = Path("data/raw")
MAX_ARCHIVE_BYTES = 250 * 1024 * 1024  # 250 MB ceiling to discourage large uploads.


def render_upload_page(
    conn: sqlite3.Connection,
    *,
    rerun_callback: Optional[Callable[[], None]] = None,
) -> None:
    """Render the upload page and invoke ingestion when requested."""
    st.header("Upload CCD Archives")
    st.caption(
        "Add ZIP files containing CCD documents. "
        "Uploaded archives are ingested immediately."
    )

    with st.form("zip-upload-form"):
        uploaded_archives = st.file_uploader(
            "Select CCD ZIP archives",
            type=["zip"],
            accept_multiple_files=True,
            help=(
                "Only ZIP files are accepted. "
                "Archives are written to data/raw/ and ingested."
            ),
        )
        trigger_ingest = st.form_submit_button("Upload and ingest")

    if not trigger_ingest:
        return

    if not uploaded_archives:
        st.warning("No ZIP archives selected.")
        return

    RAW_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    successes: List[str] = []
    errors: List[str] = []

    with st.spinner("Ingesting uploaded archives..."):
        for archive in uploaded_archives:
            try:
                _validate_archive_size(archive.size, archive.name)
                _validate_archive_type(archive)
                archive_hash = _compute_uploaded_hash(archive)
                prior_ingest = archive_was_ingested(conn, archive_hash)
                if prior_ingest:
                    errors.append(_format_duplicate_message(archive.name, prior_ingest))
                    logger.info(
                        "Skipped duplicate archive %s (hash %s).",
                        archive.name,
                        archive_hash,
                    )
                    continue
                archive_path = _persist_archive(archive, RAW_ARCHIVE_DIR)
                ingest_archive(
                    conn,
                    archive_path,
                    archive_sha256=archive_hash,
                )
                successes.append(f"Ingested {archive_path.name}")
            except ValueError as exc:
                errors.append(str(exc))
                logger.warning("Validation failed for %s: %s", archive.name, exc)
            except Exception as exc:  # pragma: no cover - defensive
                errors.append(f"Ingestion failed for {archive.name}: {exc}")
                logger.exception(
                    "Unexpected error during ingestion for %s", archive.name
                )

    st.session_state["upload_feedback"] = {
        "success": successes,
        "errors": errors,
    }

    if rerun_callback:
        rerun_callback()


def _validate_archive_size(size_bytes: Optional[int], label: str) -> None:
    """Ensure archives are within acceptable bounds for ingestion."""
    if size_bytes is None:
        return
    if size_bytes > MAX_ARCHIVE_BYTES:
        raise ValueError(
            f"{label} is larger than the {MAX_ARCHIVE_BYTES // (1024 * 1024)} MB limit."
        )


def _validate_archive_type(archive: UploadedFile) -> None:
    """Confirm the uploaded file is a ZIP archive."""
    if not archive:
        raise ValueError("Missing archive payload.")
    try:
        archive.seek(0)
        with zipfile.ZipFile(archive) as candidate:
            candidate.namelist()
    except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, RuntimeError) as exc:
        raise ValueError(f"{archive.name} is not a valid ZIP archive.") from exc
    finally:
        archive.seek(0)


def _compute_uploaded_hash(archive: UploadedFile) -> str:
    """Return SHA-256 hash for an uploaded archive stream."""
    hasher = hashlib.sha256()
    archive.seek(0)
    for chunk in iter(lambda: archive.read(8192), b""):
        if not chunk:
            break
        hasher.update(chunk)
    archive.seek(0)
    return hasher.hexdigest()


def _format_duplicate_message(
    filename: str,
    registry_row: Dict[str, object],
) -> str:
    """Compose a human-readable duplicate notice."""
    last_ingested = registry_row.get("last_ingested_at") or registry_row.get(
        "first_ingested_at"
    )
    count = registry_row.get("ingest_count")
    suffix = ""
    if isinstance(count, int) and count > 1:
        suffix = f" ({count} previous ingests)"
    timestamp = last_ingested or "a prior run"
    return f"{filename} was previously ingested on {timestamp}{suffix} and was skipped."


def _persist_archive(archive: UploadedFile, destination: Path) -> Path:
    """Write the uploaded archive to disk with a sanitised, unique filename."""
    sanitized_name = _sanitize_filename(archive.name or "ccd_archive.zip")
    target_path = _deduplicate_name(destination, sanitized_name)

    archive.seek(0)
    with target_path.open("wb") as buffer:
        shutil.copyfileobj(archive, buffer)

    return target_path


def _sanitize_filename(candidate: str) -> str:
    """Return a filesystem-safe filename while keeping contextual cues."""
    base = Path(candidate).name
    normalized = unicodedata.normalize("NFKD", base)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_only = ascii_only.replace(" ", "_")
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", ascii_only)
    if not cleaned.lower().endswith(".zip"):
        cleaned = f"{cleaned}.zip"
    return cleaned or "ccd_archive.zip"


def _deduplicate_name(directory: Path, filename: str) -> Path:
    """Prevent overwriting by appending a counter when collisions occur."""
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        proposal = directory / f"{stem}_{counter}{suffix}"
        if not proposal.exists():
            return proposal
        counter += 1
