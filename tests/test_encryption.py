# Purpose: Tests for encryption utilities.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: pytest -k test_encryption
# AI-assisted: This test module was generated with AI assistance.
"""Tests for security.encryption helpers."""

from __future__ import annotations

from pathlib import Path
import unittest

from health_records_collection.security import encryption


class TestEncryption(unittest.TestCase):
    """Test suite for encryption utilities."""

    def test_encrypt_decrypt_roundtrip(self, tmp_path: Path) -> None:
        """Test that files can be encrypted and decrypted correctly."""
        plaintext = tmp_path / "sample.xml"
        plaintext.write_text("<xml>test</xml>", encoding="utf-8")

        manager = encryption.get_encryption_manager()
        encrypted_path = manager.encrypt_file(plaintext)

        self.assertTrue(encrypted_path.exists())
        self.assertEqual(encrypted_path.suffix, ".enc")
        # Original file removed
        self.assertFalse(plaintext.exists())

        decrypted_path = manager.decrypt_to_temp(encrypted_path)
        self.assertEqual(decrypted_path.read_text(encoding="utf-8"), "<xml>test</xml>")
