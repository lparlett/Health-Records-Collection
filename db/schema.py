"""Database schema helpers."""
from __future__ import annotations

import sqlite3
from textwrap import dedent
from typing import Iterator

__all__ = ["ensure_schema"]


def _add_column_if_missing(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    ddl: str,
) -> None:
    """Add a column to a table if it is absent."""
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    rows = cur.fetchall()
    if not rows:
        return
    columns = {row[1] for row in rows}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


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





def ensure_encounter_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(encounter)")
    columns = {row[1] for row in cur.fetchall()}
    if "reason_for_visit" not in columns:
        conn.execute("ALTER TABLE encounter ADD COLUMN reason_for_visit TEXT")

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


def ensure_allergy_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(allergy)")
    rows = cur.fetchall()
    if not rows:
        return
    columns = {row[1] for row in rows}

    def add(column: str, ddl: str) -> None:
        if column not in columns:
            conn.execute(f"ALTER TABLE allergy ADD COLUMN {column} {ddl}")
            columns.add(column)

    add("encounter_id", "INTEGER REFERENCES encounter(id)")
    add("provider_id", "INTEGER REFERENCES provider(id)")
    add("substance_code", "TEXT")
    add("substance_code_system", "TEXT")
    add("substance_code_display", "TEXT")
    add("reaction_code", "TEXT")
    add("reaction_code_system", "TEXT")
    add("criticality", "TEXT")
    add("onset_date", "TEXT")
    add("noted_date", "TEXT")
    add("source_allergy_id", "TEXT")
    add("notes", "TEXT")

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_allergy_patient
            ON allergy(patient_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_allergy_encounter
            ON allergy(encounter_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_allergy_provider
            ON allergy(provider_id)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_allergy_unique
            ON allergy (
                patient_id,
                COALESCE(substance_code, ''),
                COALESCE(onset_date, ''),
                COALESCE(status, '')
            )
        """
    )


def ensure_insurance_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS insurance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            payer_name TEXT,
            plan_name TEXT,
            coverage_type TEXT,
            policy_type TEXT,
            member_id TEXT,
            group_number TEXT,
            subscriber_id TEXT,
            subscriber_name TEXT,
            relationship TEXT,
            effective_date TEXT,
            expiration_date TEXT,
            status TEXT,
            source_policy_id TEXT,
            notes TEXT,
            data_source_id INTEGER,
            FOREIGN KEY(patient_id) REFERENCES patient(id) ON DELETE CASCADE,
            FOREIGN KEY(data_source_id) REFERENCES data_source(id)
        )
        """
    )
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(insurance)")
    rows = cur.fetchall()
    columns = {row[1] for row in rows}

    def add(column: str, ddl: str) -> None:
        if column not in columns:
            conn.execute(f"ALTER TABLE insurance ADD COLUMN {column} {ddl}")
            columns.add(column)

    add("policy_type", "TEXT")
    add("subscriber_id", "TEXT")
    add("subscriber_name", "TEXT")
    add("relationship", "TEXT")
    add("effective_date", "TEXT")
    add("expiration_date", "TEXT")
    add("status", "TEXT")
    add("source_policy_id", "TEXT")
    add("notes", "TEXT")
    add("coverage_type", "TEXT")
    add("plan_name", "TEXT")
    add("payer_identifier", "TEXT")
    add("payer_name", "TEXT")
    add("member_id", "TEXT")
    add("group_number", "TEXT")
    add("data_source_id", "INTEGER REFERENCES data_source(id)")

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_insurance_patient
            ON insurance(patient_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_insurance_payer
            ON insurance(payer_name)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_insurance_unique
            ON insurance (
                patient_id,
                COALESCE(payer_name, ''),
                COALESCE(plan_name, ''),
                COALESCE(member_id, ''),
                COALESCE(group_number, '')
            )
        """
    )


def ensure_data_source_columns(conn: sqlite3.Connection) -> None:
    """Ensure core tables reference the shared data_source metadata."""
    _add_column_if_missing(conn, "data_source", "document_created", "TEXT")
    _add_column_if_missing(conn, "data_source", "repository_unique_id", "TEXT")
    _add_column_if_missing(conn, "data_source", "document_hash", "TEXT")
    _add_column_if_missing(conn, "data_source", "document_size", "INTEGER")
    _add_column_if_missing(conn, "data_source", "author_institution", "TEXT")
    _add_column_if_missing(conn, "data_source", "attachment_id", "INTEGER REFERENCES attachment(id)")
    column_ddl = "data_source_id INTEGER REFERENCES data_source(id)"
    for table in (
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
    ):
        _add_column_if_missing(conn, table, "data_source_id", column_ddl)


def ensure_schema(conn: sqlite3.Connection) -> None:
    ensure_provider_schema(conn)
    ensure_encounter_schema(conn)
    ensure_allergy_schema(conn)
    ensure_insurance_schema(conn)
    ensure_medication_constraints(conn)
    ensure_immunization_constraints(conn)
    ensure_data_source_columns(conn)



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

