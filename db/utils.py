"""Database utility helpers."""
from __future__ import annotations

from typing import Callable, Iterable, Sequence

import sqlite3


__all__ = ["insert_records"]


def insert_records(
    conn: sqlite3.Connection,
    table: str,
    columns: Sequence[str],
    items: Iterable[dict],
    row_builder: Callable[[dict], Sequence[object]],
) -> None:
    """Bulk insert helper to execute parameterized INSERT statements."""
    items = list(items)
    if not items:
        return
    placeholders = ', '.join(['?'] * len(columns))
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    cur = conn.cursor()
    cur.executemany(sql, (row_builder(item) for item in items))
    conn.commit()
