import sqlite3
import subprocess
import pathlib

def test_ingest_creates_database(tmp_path):
    # Copy test data zip into data/raw if you want full E2E
    db_file = pathlib.Path("db/health_records.db")
    if db_file.exists():
        db_file.unlink()

    subprocess.run(["python", "ingest.py"], check=True)

    assert db_file.exists()
    conn = sqlite3.connect(db_file)
    tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table';")]
    assert "patient" in tables
