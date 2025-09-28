import sqlite3
import pandas as pd
import yaml
from pathlib import Path

# Load config
CONFIG_PATH = Path(__file__).parent / "config.yaml"
with open(CONFIG_PATH, "r") as f:
    CONFIG = yaml.safe_load(f)

DB_PATH = CONFIG["db_path"]

def get_connection(db_path=DB_PATH):
    return sqlite3.connect(db_path)

def list_tables(conn):
    query = "SELECT name FROM sqlite_master WHERE type='table';"
    return [row[0] for row in conn.execute(query).fetchall()]

def get_table_preview(conn, table_name, limit=None):
    if limit is None:
        limit = CONFIG["default_row_limit"]
    query = f"SELECT * FROM {table_name} LIMIT {limit};"
    return pd.read_sql(query, conn)

def run_query(conn, sql):
    return pd.read_sql(sql, conn)
