# Purpose: Validate Streamlit upload workflow for ingestion triggers and safeguards.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: python -m unittest test_upload_components
# AI-assisted: This test module was generated with AI assistance.
"""Unit tests for frontend.upload_components."""

from __future__ import annotations

import io
import sqlite3
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import zipfile
from unittest import mock

from health_records_collection.frontend import upload_components


@dataclass
class _DummyUploadedFile:
    """Test double implementing the UploadedFile interface subset."""

    name: str
    dummydata: bytes
    declared_size: Optional[int] = None

    def __post_init__(self) -> None:
        self._buffer = io.BytesIO(self.dummydata)
        if self.declared_size is None:
            self.declared_size = len(self.dummydata)

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

    def __enter__(self) -> _FormContext:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class _SpinnerContext:
    """No-op context manager emulating streamlit.spinner."""

    def __init__(self, _label: str) -> None:
        self.label = _label

    def __enter__(self) -> _SpinnerContext:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


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
        self.session_state: Dict[str, Any] = {}
        self.success_messages: List[str] = []
        self.error_messages: List[str] = []
        self.warning_messages: List[str] = []

    def header(self, _label: str) -> None:
        return None

    def caption(self, _label: str) -> None:
        return None

    def form(self, _label: str) -> _FormContext:
        return _FormContext()

    def file_uploader(self, *_args: Any, **_kwargs: Any) -> List[_DummyUploadedFile]:
        return self._uploads

    def form_submit_button(self, *_args: Any, **_kwargs: Any) -> bool:
        return self._submit_result

    def spinner(self, label: str) -> _SpinnerContext:
        return _SpinnerContext(label)

    def warning(self, message: str) -> None:
        self.warning_messages.append(message)

    def success(self, message: str) -> None:
        self.success_messages.append(message)

    def error(self, message: str) -> None:
        self.error_messages.append(message)


class UploadComponentsTestCase(unittest.TestCase):
    """Test cases for frontend.upload_components module."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.tempdir = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        """Clean up test fixtures."""
        self.tempdir.cleanup()

    def test_render_upload_page_ingests_archives(self) -> None:
        """Ensure uploaded archives are persisted, ingested, and feedback recorded."""
        tmp_path = Path(self.tempdir.name)
        stub_file = _DummyUploadedFile("Patient Records!.zip", _build_zip_bytes())
        stubs = _StreamlitStub(uploads=[stub_file], submit_result=True)

        ingested_paths: List[Path] = []
        received_hashes: List[str] = []

        def _fake_ingest(
            _conn: sqlite3.Connection,
            archive_path: Path,
            *,
            archive_sha256: Optional[str] = None,
        ) -> None:
            ingested_paths.append(archive_path)
            received_hashes.append(archive_sha256 or "")

        rerun_called: Dict[str, bool] = {"flag": False}

        def _rerun() -> None:
            rerun_called["flag"] = True

        with mock.patch.object(upload_components, "st", stubs), mock.patch.object(
            upload_components, "RAW_ARCHIVE_DIR", tmp_path
        ), mock.patch.object(
            upload_components, "archive_was_ingested", lambda conn, sha: None
        ), mock.patch.object(
            upload_components, "ingest_archive", _fake_ingest
        ):

            conn = sqlite3.connect(":memory:")
            try:
                upload_components.render_upload_page(conn, rerun_callback=_rerun)
            finally:
                conn.close()

        self.assertTrue(rerun_called["flag"])
        self.assertEqual(len(ingested_paths), 1)

        saved_path = ingested_paths[0]
        self.assertTrue(saved_path.exists())
        self.assertEqual(saved_path.parent, tmp_path)
        # Filename sanitisation should replace spaces and punctuation with underscores.
        self.assertEqual(saved_path.name, "Patient_Records_.zip")
        self.assertEqual(len(received_hashes), 1)
        self.assertIsNotNone(received_hashes[0])

        feedback: Dict[str, Any] = stubs.session_state.get(
            "upload_feedback"
        )  # type: ignore
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback["errors"], [])
        self.assertEqual(feedback["success"], [f"Ingested {saved_path.name}"])

    def test_render_upload_page_blocks_oversized_archives(self) -> None:
        """Verify archives exceeding the size limit are rejected without ingestion."""
        tmp_path = Path(self.tempdir.name)
        oversize = upload_components.MAX_ARCHIVE_BYTES + 1
        stub_file = _DummyUploadedFile(
            "too_large.zip",
            _build_zip_bytes(),
            declared_size=oversize,
        )
        stubs = _StreamlitStub(uploads=[stub_file], submit_result=True)

        ingest_called = False

        def _fake_ingest(
            _conn: sqlite3.Connection,
            _archive_path: Path,
            *,
            _archive_sha256: Optional[str] = None,
        ) -> None:
            nonlocal ingest_called
            ingest_called = True

        rerun_called: Dict[str, bool] = {"flag": False}

        def _rerun() -> None:
            rerun_called["flag"] = True

        with mock.patch.object(upload_components, "st", stubs), mock.patch.object(
            upload_components, "RAW_ARCHIVE_DIR", tmp_path
        ), mock.patch.object(
            upload_components, "archive_was_ingested", lambda conn, sha: None
        ), mock.patch.object(
            upload_components, "ingest_archive", _fake_ingest
        ):

            conn = sqlite3.connect(":memory:")
            try:
                upload_components.render_upload_page(conn, rerun_callback=_rerun)
            finally:
                conn.close()

        self.assertFalse(ingest_called)
        self.assertTrue(rerun_called["flag"])

        feedback: Dict[str, Any] = stubs.session_state.get(
            "upload_feedback"
        )  # type: ignore
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback["success"], [])
        self.assertEqual(len(feedback["errors"]), 1)
        self.assertIn("larger than the", feedback["errors"][0])

    def test_render_upload_page_rejects_non_zip(self) -> None:
        """Reject uploads whose content is not a valid ZIP archive."""
        tmp_path = Path(self.tempdir.name)
        stub_file = _DummyUploadedFile("notes.zip", b"not-a-zip")
        stubs = _StreamlitStub(uploads=[stub_file], submit_result=True)

        ingest_called = False

        def _fake_ingest(
            _conn: sqlite3.Connection,
            _archive_path: Path,
            *,
            _archive_sha256: Optional[str] = None,
        ) -> None:
            nonlocal ingest_called
            ingest_called = True

        rerun_called: Dict[str, bool] = {"flag": False}

        def _rerun() -> None:
            rerun_called["flag"] = True

        with mock.patch.object(upload_components, "st", stubs), mock.patch.object(
            upload_components, "RAW_ARCHIVE_DIR", tmp_path
        ), mock.patch.object(
            upload_components, "archive_was_ingested", lambda conn, sha: None
        ), mock.patch.object(
            upload_components, "ingest_archive", _fake_ingest
        ):

            conn = sqlite3.connect(":memory:")
            try:
                upload_components.render_upload_page(conn, rerun_callback=_rerun)
            finally:
                conn.close()

        self.assertFalse(ingest_called)
        self.assertTrue(rerun_called["flag"])

        feedback: Dict[str, Any] = stubs.session_state.get(
            "upload_feedback"
        )  # type: ignore
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback["success"], [])
        self.assertEqual(len(feedback["errors"]), 1)
        self.assertIn("not a valid ZIP archive", feedback["errors"][0])

    def test_render_upload_page_detects_duplicate_archives(self) -> None:
        """Skip ingestion when the archive hash already exists in the registry."""
        tmp_path = Path(self.tempdir.name)
        stub_file = _DummyUploadedFile("duplicate.zip", _build_zip_bytes())
        stubs = _StreamlitStub(uploads=[stub_file], submit_result=True)

        def _fake_lookup(
            _conn: sqlite3.Connection, archive_hash: str
        ) -> Dict[str, Any]:
            return {
                "archive_name": "duplicate.zip",
                "archive_sha256": archive_hash,
                "first_ingested_at": "2025-10-20T05:14:00Z",
                "last_ingested_at": "2025-10-20T05:14:00Z",
                "ingest_count": 1,
            }

        ingest_called = False

        def _fake_ingest(
            _conn: sqlite3.Connection,
            _archive_path: Path,
            *,
            _archive_sha256: Optional[str] = None,
        ) -> None:
            nonlocal ingest_called
            ingest_called = True

        rerun_called: Dict[str, bool] = {"flag": False}

        def _rerun() -> None:
            rerun_called["flag"] = True

        with mock.patch.object(upload_components, "st", stubs), mock.patch.object(
            upload_components, "RAW_ARCHIVE_DIR", tmp_path
        ), mock.patch.object(
            upload_components, "archive_was_ingested", _fake_lookup
        ), mock.patch.object(
            upload_components, "ingest_archive", _fake_ingest
        ):

            conn = sqlite3.connect(":memory:")
            try:
                upload_components.render_upload_page(conn, rerun_callback=_rerun)
            finally:
                conn.close()

        self.assertFalse(ingest_called)
        self.assertTrue(rerun_called["flag"])

        feedback: Dict[str, Any] = stubs.session_state.get(
            "upload_feedback"
        )  # type: ignore
        self.assertIsNotNone(feedback)
        self.assertEqual(feedback["success"], [])
        self.assertEqual(len(feedback["errors"]), 1)
        self.assertIn("was previously ingested", feedback["errors"][0])


if __name__ == "__main__":
    unittest.main()
