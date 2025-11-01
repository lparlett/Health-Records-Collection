# Purpose: Validate settings module path overrides and persistence.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: python -m unittest test_settings.py
# AI-assisted: This test module was generated with AI assistance.
"""Unit tests for the settings module."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from health_records_collection import settings


class TestSettings(unittest.TestCase):
    """Unit tests for settings module."""

    def setUp(self):
        # Create a temporary directory for each test
        self.temp_dir = tempfile.mkdtemp()
        self.settings_file = Path(self.temp_dir) / "user_settings.yaml"
        self.patcher = patch.object(settings, "SETTINGS_FILE", self.settings_file)
        self.patcher.start()

    def tearDown(self):
        # Clean up the temporary directory after each test
        self.patcher.stop()
        for root, dirs, files in os.walk(self.temp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.temp_dir)

    def test_load_paths_uses_defaults(self):
        """Test that load_paths returns and creates default directories."""
        paths = settings.load_paths()

        self.assertTrue(paths["raw_dir"].as_posix().endswith("data/raw"))
        self.assertTrue(paths["parsed_dir"].as_posix().endswith("data/parsed"))
        self.assertTrue(paths["db_path"].as_posix().endswith("db/health_records.db"))

        # Verify directories are created
        self.assertTrue(paths["raw_dir"].exists())
        self.assertTrue(paths["parsed_dir"].exists())
        self.assertTrue(paths["db_path"].parent.exists())

    def test_load_settings_returns_ingestion_defaults(self):
        """Test that default ingestion settings are returned."""
        config = settings.load_settings()
        ingestion = config["ingestion"]

        self.assertTrue(ingestion["delete_uploaded_archives"])
        self.assertTrue(ingestion["delete_unencrypted_extracted_files"])

    def test_save_settings_overrides_defaults(self):
        """Test that saved settings override defaults and directories are created."""
        custom_raw = Path(self.temp_dir) / "custom_raw"
        custom_parsed = Path(self.temp_dir) / "custom_parsed"
        custom_db = Path(self.temp_dir) / "custom_db" / "records.db"

        settings.save_settings(
            {
                "paths": {
                    "raw_dir": custom_raw,
                    "parsed_dir": custom_parsed,
                    "db_path": custom_db,
                },
                "ingestion": {
                    "delete_uploaded_archives": False,
                    "delete_unencrypted_extracted_files": False,
                },
            }
        )

        paths = settings.load_paths()
        self.assertEqual(paths["raw_dir"], custom_raw)
        self.assertEqual(paths["parsed_dir"], custom_parsed)
        self.assertEqual(paths["db_path"], custom_db)
        self.assertTrue(custom_raw.exists())
        self.assertTrue(custom_parsed.exists())
        self.assertTrue(custom_db.parent.exists())

        ingestion = settings.load_settings()["ingestion"]
        self.assertFalse(ingestion["delete_uploaded_archives"])
        self.assertFalse(ingestion["delete_unencrypted_extracted_files"])


if __name__ == "__main__":
    unittest.main()
