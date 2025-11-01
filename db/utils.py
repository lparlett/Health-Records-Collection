"""Database utility helpers."""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

import sqlite3


__all__ = ["insert_records", "update_single_field"]


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
    placeholders = ", ".join(["?"] * len(columns))
    # pylint: disable=line-too-long
    # fmt: off
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})" #nosec B608
    # pylint: enable=line-too-long
    # fmt: on
    cur = conn.cursor()
    cur.executemany(sql, (row_builder(item) for item in items))
    conn.commit()


def update_single_field(
    cur: sqlite3.Cursor,
    table: str,
    field: str,
    value: object,
    record_id: int,
) -> None:
    """Update a single field in a table for a given record ID.

    Args:
        cur: Active SQLite cursor.
        table: Name of the table to update.
        field: Name of the field/column to update.
        value: New value to set.
        record_id: ID of the record to update.

    Raises:
        ValueError: If table or field names contain invalid characters.
    """
    # Validate table and field names to prevent SQL injection
    valid_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
    if not (set(table) <= valid_chars and set(field) <= valid_chars):
        raise ValueError("Invalid table or field name")

    sql = f"UPDATE {table} SET {field} = ? WHERE id = ?"  # nosec B608
    cur.execute(sql, [value, record_id])
