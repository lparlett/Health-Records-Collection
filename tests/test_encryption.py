# Purpose: Tests for encryption utilities.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: python -m unittest test_encryption
# AI-assisted: This test module was generated with AI assistance.
"""Tests for security.encryption helpers."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from health_records_collection.security import encryption


class TestEncryption(unittest.TestCase):
    """Test suite for encryption utilities."""

    def setUp(self) -> None:
        """Set up temporary directory for encryption testing."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        """Clean up temporary directory after testing."""
        self.temp_dir.cleanup()

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """Test that files can be encrypted and decrypted correctly."""
        plaintext = self.tmp_path / "sample.xml"
        plaintext.write_text("<xml>test</xml>", encoding="utf-8")

        manager = encryption.get_encryption_manager()
        encrypted_path = manager.encrypt_file(plaintext)

        self.assertTrue(encrypted_path.exists())
        self.assertEqual(encrypted_path.suffix, ".enc")
        # Original file removed
        self.assertFalse(plaintext.exists())

        decrypted_path = manager.decrypt_to_temp(encrypted_path)
        self.assertEqual(decrypted_path.read_text(encoding="utf-8"), "<xml>test</xml>")
