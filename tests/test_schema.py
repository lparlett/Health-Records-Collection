import sqlite3
from pathlib import Path


def _load_schema(tmp_path):
    db_file = tmp_path / "schema_test.db"
    conn = sqlite3.connect(db_file)
    conn.execute("PRAGMA foreign_keys = ON;")
    schema_path = Path("schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    return conn


def test_schema_creates_expected_tables(tmp_path):
    conn = _load_schema(tmp_path)
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
        "medication",
        "lab_result",
        "condition",
        "condition_code",
        "progress_note",
    }
    assert expected.issubset(tables)


def test_schema_includes_data_source_foreign_keys(tmp_path):
    conn = _load_schema(tmp_path)
    cursor = conn.cursor()
    tables_to_check = [
        "patient",
        "encounter",
        "medication",
        "lab_result",
        "allergy",
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
        assert (
            "data_source_id" in columns
        ), f"{table} missing data_source_id column"

        cursor.execute(f"PRAGMA foreign_key_list({table})")
        fk_targets = {(row[3], row[2]) for row in cursor.fetchall()}
        assert (
            ("data_source_id", "data_source") in fk_targets
        ), f"{table} missing FK to data_source"

    cursor.execute("PRAGMA table_info(data_source)")
    ds_columns = {row[1] for row in cursor.fetchall()}
    assert "attachment_id" in ds_columns

    cursor.execute("PRAGMA foreign_key_list(data_source)")
    ds_fk = {(row[3], row[2]) for row in cursor.fetchall()}
    assert ("attachment_id", "attachment") in ds_fk
