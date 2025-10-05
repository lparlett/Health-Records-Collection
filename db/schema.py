"""Database schema helpers."""
from __future__ import annotations

import sqlite3
from textwrap import dedent
from typing import Iterator

__all__ = ["ensure_schema"]


def _iter_provider_migrations() -> Iterator[str]:
    yield """
        UPDATE provider
           SET entity_type = CASE
               WHEN entity_type IS NOT NULL THEN entity_type
               WHEN (given_name IS NULL OR TRIM(given_name) = '')
                AND (family_name IS NULL OR TRIM(family_name) = '') THEN 'organization'
               ELSE 'person'
           END
    """
    yield """
        UPDATE provider
           SET normalized_key = LOWER(
               REPLACE(COALESCE(given_name, '') || COALESCE(family_name, ''), ' ', '')
           )
         WHERE (normalized_key IS NULL OR TRIM(normalized_key) = '')
           AND ((given_name IS NOT NULL AND TRIM(given_name) <> '')
                OR (family_name IS NOT NULL AND TRIM(family_name) <> ''))
    """
    yield """
        UPDATE provider
           SET normalized_key = LOWER(REPLACE(COALESCE(name, ''), ' ', ''))
         WHERE normalized_key IS NULL OR TRIM(normalized_key) = ''
    """
    yield """
        DELETE FROM provider
              WHERE normalized_key IS NOT NULL
                AND rowid NOT IN (
                    SELECT MIN(rowid)
                      FROM provider
                     WHERE normalized_key IS NOT NULL
                     GROUP BY normalized_key
                )
    """
    yield """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_provider_normalized_key
            ON provider(normalized_key)
    """


def ensure_provider_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(provider)")
    rows = cur.fetchall()
    if not rows:
        return

    columns = {row[1] for row in rows}

    def add_column(column: str, ddl: str) -> None:
        if column not in columns:
            conn.execute(f"ALTER TABLE provider ADD COLUMN {column} {ddl}")
            columns.add(column)

    add_column("given_name", "TEXT")
    add_column("family_name", "TEXT")
    add_column("credentials", "TEXT")
    add_column("organization", "TEXT")
    add_column("normalized_key", "TEXT")
    add_column("entity_type", "TEXT DEFAULT 'person'")
    add_column("name", "TEXT")

    for statement in _iter_provider_migrations():
        conn.execute(dedent(statement))


def ensure_medication_constraints(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        DELETE FROM medication
              WHERE rowid NOT IN (
                    SELECT MIN(rowid)
                      FROM medication
                     GROUP BY patient_id,
                              COALESCE(encounter_id, -1),
                              COALESCE(name, ''),
                              COALESCE(dose, ''),
                              COALESCE(start_date, '')
              )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uniq_medication_composite
            ON medication (
                patient_id,
                COALESCE(encounter_id, -1),
                COALESCE(name, ''),
                COALESCE(dose, ''),
                COALESCE(start_date, '')
            )
        """
    )


def ensure_schema(conn: sqlite3.Connection) -> None:
    ensure_provider_schema(conn)
    ensure_medication_constraints(conn)
    ensure_immunization_constraints(conn)



def ensure_immunization_constraints(conn: sqlite3.Connection) -> None:
    conn.execute("""
        DELETE FROM immunization
              WHERE rowid NOT IN (
                    SELECT MIN(rowid)
                      FROM immunization
                     GROUP BY patient_id,
                              COALESCE(date_administered, ''),
                              COALESCE(cvx_code, '')
              )
        """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_immunization_unique
            ON immunization (
                patient_id,
                COALESCE(date_administered, ''),
                COALESCE(cvx_code, '')
            )
        """)

