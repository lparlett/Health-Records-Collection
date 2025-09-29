import sqlite3
import pytest
import frontend.db_utils as db_utils

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(db_file)
    conn.execute("CREATE TABLE patient (id INTEGER PRIMARY KEY, name TEXT);")
    conn.execute("INSERT INTO patient (name) VALUES ('Alice');")
    conn.commit()
    yield str(db_file)
    conn.close()

def test_list_tables(temp_db):
    conn = sqlite3.connect(temp_db)
    tables = db_utils.list_tables(conn)
    assert "patient" in tables

def test_get_table_preview(temp_db):
    conn = sqlite3.connect(temp_db)
    df = db_utils.get_table_preview(conn, "patient", limit=10)
    assert not df.empty
    assert "name" in df.columns
