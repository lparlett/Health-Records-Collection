from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path


class TestSchema(unittest.TestCase):
    """Test suite for database schema."""

    def setUp(self) -> None:
        """Set up temporary database for schema testing."""
        self.tmp_path = Path(tempfile.mkdtemp())
        self.conn: sqlite3.Connection | None = None

    def tearDown(self) -> None:
        """Clean up temporary database after testing."""
        if self.conn:
            self.conn.close()
        shutil.rmtree(self.tmp_path, ignore_errors=True)

    def _load_schema(self) -> sqlite3.Connection:
        """Helper to load schema into temporary database."""
        db_file = self.tmp_path / "schema_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("PRAGMA foreign_keys = ON;")
        # Find schema.sql relative to the project root
        schema_path = Path(__file__).parent.parent / "schema.sql"
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        return conn

    def test_schema_creates_expected_tables(self) -> None:
        """Test that schema creates expected tables."""
        conn = self._load_schema()
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table';"
            )
        }
        expected = {
            "data_source",
            "patient",
            "provider",
            "encounter",
            "allergy",
            "insurance",
            "medication",
            "lab_result",
            "condition",
            "condition_code",
            "progress_note",
        }
        self.assertTrue(expected.issubset(tables))
        conn.close()

    def test_schema_includes_data_source_foreign_keys(self) -> None:
        """Test that schema includes data_source foreign keys."""
        conn = self._load_schema()
        cursor = conn.cursor()
        tables_to_check = [
            "patient",
            "encounter",
            "medication",
            "lab_result",
            "allergy",
            "insurance",
            "condition",
            "immunization",
            "vital",
            "procedure",
            "attachment",
            "progress_note",
        ]

        for table in tables_to_check:
            cursor.execute(f"PRAGMA table_info({table})")
            columns = {row[1] for row in cursor.fetchall()}
            self.assertIn(
                "data_source_id", columns, f"{table} missing data_source_id column"
            )

            cursor.execute(f"PRAGMA foreign_key_list({table})")
            fk_targets = {(row[3], row[2]) for row in cursor.fetchall()}
            self.assertIn(
                ("data_source_id", "data_source"),
                fk_targets,
                f"{table} missing FK to data_source",
            )

        cursor.execute("PRAGMA table_info(data_source)")
        ds_columns = {row[1] for row in cursor.fetchall()}
        self.assertIn("attachment_id", ds_columns)

        cursor.execute("PRAGMA foreign_key_list(data_source)")
        ds_fk = {(row[3], row[2]) for row in cursor.fetchall()}
        self.assertIn(("attachment_id", "attachment"), ds_fk)

        conn.close()
