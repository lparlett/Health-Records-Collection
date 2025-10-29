# Purpose: Tests for encryption utilities.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: pytest -k test_encryption
# AI-assisted: This test module was generated with AI assistance.
"""Tests for security.encryption helpers."""

from __future__ import annotations

from pathlib import Path

from security import encryption


def test_encrypt_decrypt_roundtrip(tmp_path, monkeypatch):
    plaintext = tmp_path / "sample.xml"
    plaintext.write_text("<xml>test</xml>", encoding="utf-8")

    manager = encryption.get_encryption_manager()
    encrypted_path = manager.encrypt_file(plaintext)

    assert encrypted_path.exists()
    assert encrypted_path.suffix == ".enc"
    # Original file removed
    assert not plaintext.exists()

    decrypted_path = manager.decrypt_to_temp(encrypted_path)
    assert decrypted_path.read_text(encoding="utf-8") == "<xml>test</xml>"
