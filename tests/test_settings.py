# Purpose: Validate settings module path overrides and persistence.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: pytest -k test_settings
# AI-assisted: This test module was generated with AI assistance.
"""Unit tests for the settings module."""

from __future__ import annotations

from pathlib import Path

import settings


def test_load_paths_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "user_settings.yaml")
    paths = settings.load_paths()

    assert paths["raw_dir"].as_posix().endswith("data/raw")
    assert paths["parsed_dir"].as_posix().endswith("data/parsed")
    assert paths["db_path"].as_posix().endswith("db/health_records.db")

    # load_paths ensures directories exist
    assert paths["raw_dir"].exists()
    assert paths["parsed_dir"].exists()
    assert paths["db_path"].parent.exists()


def test_save_settings_overrides_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "user_settings.yaml")
    custom_raw = tmp_path / "custom_raw"
    custom_parsed = tmp_path / "custom_parsed"
    custom_db = tmp_path / "custom_db" / "records.db"

    settings.save_settings(
        {
            "paths": {
                "raw_dir": custom_raw,
                "parsed_dir": custom_parsed,
                "db_path": custom_db,
            }
        }
    )

    paths = settings.load_paths()
    assert paths["raw_dir"] == custom_raw
    assert paths["parsed_dir"] == custom_parsed
    assert paths["db_path"] == custom_db
    assert custom_raw.exists()
    assert custom_parsed.exists()
    assert custom_db.parent.exists()
