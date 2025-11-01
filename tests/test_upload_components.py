# Purpose: Validate Streamlit upload workflow for ingestion triggers and safeguards.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: pytest -k test_upload_components
# AI-assisted: This test module was generated with AI assistance.
"""Unit tests for frontend.upload_components."""

from __future__ import annotations

import io
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import pytest
import zipfile

from frontend import upload_components


@dataclass
class _DummyUploadedFile:
    """Test double implementing the UploadedFile interface subset."""

    name: str
    data: bytes
    declared_size: Optional[int] = None

    def __post_init__(self) -> None:
        self._buffer = io.BytesIO(self.data)
        if self.declared_size is None:
            self.declared_size = len(self.data)

    @property
    def size(self) -> Optional[int]:
        return self.declared_size

    def read(self, size: int | None = -1) -> bytes:
        return self._buffer.read(size if size is not None else -1)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._buffer.seek(offset, whence)

    def tell(self) -> int:
        return self._buffer.tell()


def _build_zip_bytes() -> bytes:
    """Return a minimal ZIP binary payload."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("sample.txt", "payload")
    buffer.seek(0)
    return buffer.read()


class _FormContext:
    """No-op context manager emulating streamlit.form."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _SpinnerContext:
    """No-op context manager emulating streamlit.spinner."""

    def __init__(self, _label: str) -> None:
        self.label = _label

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _StreamlitStub:
    """Minimal shim around the Streamlit API surface used by upload components."""

    def __init__(
        self,
        *,
        uploads: Iterable[_DummyUploadedFile],
        submit_result: bool,
    ) -> None:
        self._uploads = list(uploads)
        self._submit_result = submit_result
        self.session_state: dict[str, object] = {}
        self.success_messages: List[str] = []
        self.error_messages: List[str] = []
        self.warning_messages: List[str] = []

    def header(self, _label: str) -> None:
        return None

    def caption(self, _label: str) -> None:
        return None

    def form(self, _label: str) -> _FormContext:
        return _FormContext()

    def file_uploader(self, *_args, **_kwargs) -> List[_DummyUploadedFile]:
        return self._uploads

    def form_submit_button(self, *_args, **_kwargs) -> bool:
        return self._submit_result

    def spinner(self, label: str) -> _SpinnerContext:
        return _SpinnerContext(label)

    def warning(self, message: str) -> None:
        self.warning_messages.append(message)

    def success(self, message: str) -> None:
        self.success_messages.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)


def test_render_upload_page_ingests_archives(monkeypatch, tmp_path):
    """Ensure uploaded archives are persisted, ingested, and feedback recorded."""
    stub_file = _DummyUploadedFile("Patient Records!.zip", _build_zip_bytes())
    stubs = _StreamlitStub(uploads=[stub_file], submit_result=True)
    monkeypatch.setattr(upload_components, "st", stubs)
    monkeypatch.setattr(upload_components, "RAW_ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(
        upload_components, "archive_was_ingested", lambda conn, sha: None
    )

    ingested_paths: List[Path] = []
    received_hashes: List[str] = []

    def _fake_ingest(
        conn: sqlite3.Connection,
        archive_path: Path,
        *,
        archive_sha256: Optional[str] = None,
    ) -> None:
        ingested_paths.append(archive_path)
        received_hashes.append(archive_sha256 or "")

    monkeypatch.setattr(upload_components, "ingest_archive", _fake_ingest)

    rerun_called = {"flag": False}

    def _rerun() -> None:
        rerun_called["flag"] = True

    conn = sqlite3.connect(":memory:")
    try:
        upload_components.render_upload_page(conn, rerun_callback=_rerun)
    finally:
        conn.close()

    assert rerun_called["flag"] is True
    assert len(ingested_paths) == 1

    saved_path = ingested_paths[0]
    assert saved_path.exists()
    assert saved_path.parent == tmp_path
    # Filename sanitisation should replace spaces and punctuation with underscores.
    assert saved_path.name == "Patient_Records_.zip"
    assert len(received_hashes) == 1
    assert received_hashes[0]

    feedback = stubs.session_state.get("upload_feedback")
    assert feedback is not None
    assert feedback["errors"] == []
    assert feedback["success"] == [f"Ingested {saved_path.name}"]


def test_render_upload_page_blocks_oversized_archives(monkeypatch, tmp_path):
    """Verify archives exceeding the size limit are rejected without ingestion."""
    oversize = upload_components.MAX_ARCHIVE_BYTES + 1
    stub_file = _DummyUploadedFile(
        "too_large.zip",
        _build_zip_bytes(),
        declared_size=oversize,
    )
    stubs = _StreamlitStub(uploads=[stub_file], submit_result=True)
    monkeypatch.setattr(upload_components, "st", stubs)
    monkeypatch.setattr(upload_components, "RAW_ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(
        upload_components, "archive_was_ingested", lambda conn, sha: None
    )

    ingest_called = False

    def _fake_ingest(
        conn: sqlite3.Connection,
        archive_path: Path,
        *,
        archive_sha256: Optional[str] = None,
    ) -> None:
        nonlocal ingest_called
        ingest_called = True

    monkeypatch.setattr(upload_components, "ingest_archive", _fake_ingest)

    rerun_called = {"flag": False}

    def _rerun() -> None:
        rerun_called["flag"] = True

    conn = sqlite3.connect(":memory:")
    try:
        upload_components.render_upload_page(conn, rerun_callback=_rerun)
    finally:
        conn.close()

    assert ingest_called is False
    assert rerun_called["flag"] is True

    feedback = stubs.session_state.get("upload_feedback")
    assert feedback is not None
    assert feedback["success"] == []
    assert len(feedback["errors"]) == 1
    assert "larger than the" in feedback["errors"][0]


def test_render_upload_page_rejects_non_zip(monkeypatch, tmp_path):
    """Reject uploads whose content is not a valid ZIP archive."""
    stub_file = _DummyUploadedFile("notes.zip", b"not-a-zip")
    stubs = _StreamlitStub(uploads=[stub_file], submit_result=True)
    monkeypatch.setattr(upload_components, "st", stubs)
    monkeypatch.setattr(upload_components, "RAW_ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(
        upload_components, "archive_was_ingested", lambda conn, sha: None
    )

    ingest_called = False

    def _fake_ingest(
        conn: sqlite3.Connection,
        archive_path: Path,
        *,
        archive_sha256: Optional[str] = None,
    ) -> None:
        nonlocal ingest_called
        ingest_called = True

    monkeypatch.setattr(upload_components, "ingest_archive", _fake_ingest)

    rerun_called = {"flag": False}

    def _rerun() -> None:
        rerun_called["flag"] = True

    conn = sqlite3.connect(":memory:")
    try:
        upload_components.render_upload_page(conn, rerun_callback=_rerun)
    finally:
        conn.close()

    assert ingest_called is False
    assert rerun_called["flag"] is True

    feedback = stubs.session_state.get("upload_feedback")
    assert feedback is not None
    assert feedback["success"] == []
    assert len(feedback["errors"]) == 1
    assert "not a valid ZIP archive" in feedback["errors"][0]


def test_render_upload_page_detects_duplicate_archives(monkeypatch, tmp_path):
    """Skip ingestion when the archive hash already exists in the registry."""
    stub_file = _DummyUploadedFile("duplicate.zip", _build_zip_bytes())
    stubs = _StreamlitStub(uploads=[stub_file], submit_result=True)
    monkeypatch.setattr(upload_components, "st", stubs)
    monkeypatch.setattr(upload_components, "RAW_ARCHIVE_DIR", tmp_path)

    def _fake_lookup(conn: sqlite3.Connection, archive_hash: str):
        return {
            "archive_name": "duplicate.zip",
            "archive_sha256": archive_hash,
            "first_ingested_at": "2025-10-20T05:14:00Z",
            "last_ingested_at": "2025-10-20T05:14:00Z",
            "ingest_count": 1,
        }

    monkeypatch.setattr(upload_components, "archive_was_ingested", _fake_lookup)

    ingest_called = False

    def _fake_ingest(
        conn: sqlite3.Connection,
        archive_path: Path,
        *,
        archive_sha256: Optional[str] = None,
    ) -> None:
        nonlocal ingest_called
        ingest_called = True

    monkeypatch.setattr(upload_components, "ingest_archive", _fake_ingest)

    rerun_called = {"flag": False}

    def _rerun() -> None:
        rerun_called["flag"] = True

    conn = sqlite3.connect(":memory:")
    try:
        upload_components.render_upload_page(conn, rerun_callback=_rerun)
    finally:
        conn.close()

    assert ingest_called is False
    assert rerun_called["flag"] is True

    feedback = stubs.session_state.get("upload_feedback")
    assert feedback is not None
    assert feedback["success"] == []
    assert len(feedback["errors"]) == 1
    assert "was previously ingested" in feedback["errors"][0]
