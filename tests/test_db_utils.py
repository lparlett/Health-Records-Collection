from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from health_records_collection.frontend import db_utils


class TestDbUtils(unittest.TestCase):
    """Test suite for database utilities."""

    def setUp(self) -> None:
        """Set up temporary database for each test."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_file = Path(self.temp_dir.name) / "test.db"
        self.conn = sqlite3.connect(str(self.db_file))
        self.conn.execute("CREATE TABLE patient (id INTEGER PRIMARY KEY, name TEXT);")
        self.conn.execute("INSERT INTO patient (name) VALUES ('Alice');")
        self.conn.commit()

    def tearDown(self) -> None:
        """Clean up temporary database after each test."""
        self.conn.close()
        self.temp_dir.cleanup()

    def test_list_tables(self) -> None:
        """Test that list_tables correctly identifies tables."""
        tables = db_utils.list_tables(self.conn)
        self.assertIn("patient", tables)

    def test_get_table_preview(self) -> None:
        """Test that get_table_preview returns correct data."""
        df = db_utils.get_table_preview(self.conn, "patient", limit=10)
        self.assertFalse(df.empty)
        self.assertIn("name", df.columns)
