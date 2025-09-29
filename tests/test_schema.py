import sqlite3
import pathlib

def test_schema_creates_expected_tables(tmp_path):
    db_file = tmp_path / "schema_test.db"
    conn = sqlite3.connect(db_file)
    schema_path = pathlib.Path("schema.sql")
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")]
    expected = {"patient", "provider", "encounter", "medication", "lab_result", "condition", "condition_code"}
    assert expected.issubset(set(tables))
