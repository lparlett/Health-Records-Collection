from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path


def _load_schema(tmp_path: Path) -> sqlite3.Connection:
    """Helper to load schema into temporary database."""
    db_file = tmp_path / "schema_test.db"
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON;")
    schema_path = Path("schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    return conn


class TestSchema(unittest.TestCase):
    """Test suite for database schema."""

    def test_schema_creates_expected_tables(self, tmp_path: Path) -> None:
        """Test that schema creates expected tables."""
        conn = _load_schema(tmp_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master " "WHERE type='table';"
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

    def test_schema_includes_data_source_foreign_keys(self, tmp_path: Path) -> None:
        """Test that schema includes data_source foreign keys."""
        conn = _load_schema(tmp_path)
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
