# Purpose: Provide SQLCipher-backed database helpers for the frontend.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: tests/test_db_utils.py
# AI-assisted: Module updated with AI assistance.
"""Helpers for working with the encrypted application database."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, TypeAlias, cast, TYPE_CHECKING

import pandas as pd  # type: ignore
import sqlcipher3.dbapi2 as sqlcipher  # type: ignore
import yaml  # type: ignore

from health_records_collection.db.schema import ensure_schema
from health_records_collection import settings
from health_records_collection.security import sqlcipher_support

if TYPE_CHECKING:
    # This block is only used for type checking
    from sqlite3 import Connection as SQLite3Connection
    SQLCipherConnection = SQLite3Connection
else:
    # Runtime definition
    SQLCipherConnection: TypeAlias = sqlite3.Connection

logger = logging.getLogger(__name__)

# Load config
CONFIG_PATH = Path(__file__).parent / "config.yaml"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)

DEFAULT_DB_PATH = Path(CONFIG["db_path"]).expanduser()
SCHEMA_SQL_PATH = Path(__file__).resolve().parents[1] / "schema.sql"


def _resolve_db_path() -> Path:
    try:
        paths = settings.load_paths()
        return paths["db_path"]
    except (KeyError, FileNotFoundError, yaml.YAMLError):  # pragma: defensive fallback
        # KeyError: Missing db_path in settings
        # FileNotFoundError: Settings file not found
        # YAMLError: Invalid YAML format
        return DEFAULT_DB_PATH


def _database_has_patient_table(conn: Any) -> bool:
    query = (
        "SELECT 1 FROM sqlite_master "
        "WHERE type = 'table' AND name = 'patient' LIMIT 1"
    )
    return conn.execute(query).fetchone() is not None


def _ensure_database_ready(conn: Any) -> None:
    """Create base schema when the database file is empty."""
    # AI-assisted change: bootstrap schema for fresh database files.
    if _database_has_patient_table(conn):
        ensure_schema(conn)
        conn.commit()
        return

    if not SCHEMA_SQL_PATH.exists():
        raise FileNotFoundError(
            f"schema.sql not found at expected path: {SCHEMA_SQL_PATH}"
        )

    schema_sql = SCHEMA_SQL_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    ensure_schema(conn)
    conn.commit()


def _open_encrypted_connection(
    db_path: Path, *, passphrase: str
) -> SQLCipherConnection:
    """Return an SQLCipher connection initialised with hardening pragmas."""
    conn = cast(SQLCipherConnection, sqlcipher.connect(str(db_path)))  # pylint: disable=no-member
    sqlcipher_support.configure_connection(conn, passphrase)
    return conn


def get_connection(
    db_path: Path | str | None = None, *, passphrase: str | None = None
) -> Any:
    """
    Return an SQLCipher-encrypted database connection, ensuring schema exists.

    Args:
        db_path: Explicit path to the database file. Defaults to configured path.
        passphrase: Optional SQLCipher passphrase override. When omitted, the
            value is sourced via `security.sqlcipher_support.get_passphrase()`.

    Returns:
        An initialised SQLCipher connection ready for use.

    Raises:
        RuntimeError: If the connection cannot be unlocked with the passphrase.
    """
    if db_path is None:
        db_path = _resolve_db_path()
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if passphrase:
        key = sqlcipher_support.cache_passphrase(passphrase)
    else:
        key = sqlcipher_support.get_passphrase()
    try:
        conn = _open_encrypted_connection(db_path, passphrase=key)
    except sqlite3.DatabaseError as exc:  # pragma: no cover - defensive
        logger.error("Unable to unlock encrypted database %s: %s", db_path, exc)
        raise RuntimeError("Invalid SQLCipher passphrase supplied.") from exc

    _ensure_database_ready(conn)
    return conn


def list_tables(conn):
    """List all table names in the database."""
    query = "SELECT name FROM sqlite_master WHERE type='table';"
    return [row[0] for row in conn.execute(query).fetchall()]


def get_table_preview(
    conn: SQLCipherConnection, table_name: str, limit: int | None = None
    ) -> pd.DataFrame:
    """Get a preview of table contents with SQL injection protection.
    
    Args:
        conn: Database connection
        table_name: Name of the table to preview (must be a valid SQL identifier)
        limit: Maximum number of rows to return, defaults to CONFIG["default_row_limit"]
    
    Returns:
        DataFrame containing the table preview
        
    Raises:
        ValueError: If table_name is not a valid SQL identifier
    """
    # Validate table name is a safe identifier
    if not (table_name.isidentifier() and table_name.isascii()):
        raise ValueError("Invalid table name")

    # Check if table exists to prevent SQL injection
    table_names = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if table_name not in table_names:
        raise ValueError(f"Table '{table_name}' does not exist")

    # Ensure we have a valid integer limit
    row_limit = CONFIG["default_row_limit"] if limit is None else limit
    if not isinstance(row_limit, int) or row_limit < 1:
        raise ValueError("Limit must be a positive integer")

    # Table name is now verified to exist and be safe
    query = f"SELECT * FROM {table_name} LIMIT ?"  # nosec B608
    return pd.read_sql(query, conn, params=(row_limit,))

def run_query(conn, sql):
    """Run an arbitrary SQL query and return the results as a DataFrame."""
    return pd.read_sql(sql, conn)


def _format_person_name(primary, given, family, fallback_label):
    """Return a human friendly display name with sensible fallbacks."""
    for value in (primary,):
        if isinstance(value, str):
            trimmed = value.strip()
            if trimmed:
                return trimmed
    given_clean = (given or "").strip()
    family_clean = (family or "").strip()
    if given_clean and family_clean:
        return f"{family_clean}, {given_clean}"
    if family_clean:
        return family_clean
    if given_clean:
        return given_clean
    return fallback_label


def get_patients(conn):
    """Return a DataFrame of patients with a display name column."""
    query = """
        SELECT id, given_name, family_name, birth_date
          FROM patient
         ORDER BY COALESCE(family_name, ''), COALESCE(given_name, ''), id
        """
    df = pd.read_sql(query, conn)
    if df.empty:
        df["display_name"] = []
        return df

    df["display_name"] = df.apply(
        lambda row: _format_person_name(
            None,
            row.get("given_name"),
            row.get("family_name"),
            f"Patient #{row.get('id')}"
            + (f" ({row.get('birth_date')})" if row.get("birth_date") else ""),
        ),
        axis=1,
    )
    cols = ["id", "display_name", "given_name", "family_name", "birth_date"]
    return df[cols]


def get_patient_encounters(conn, patient_id):
    """Fetch encounter summary data for a patient."""
    encounters_query = """
        SELECT e.id AS encounter_id,
               e.encounter_date,
               e.encounter_type,
               e.notes,
               p.name AS provider_name,
               p.given_name AS provider_given_name,
               p.family_name AS provider_family_name
          FROM encounter e
          LEFT JOIN provider p ON e.provider_id = p.id
         WHERE e.patient_id = ?
         ORDER BY COALESCE(e.encounter_date, '' ) DESC, e.id DESC
        """
    encounters = pd.read_sql(encounters_query, conn, params=(patient_id,))
    if encounters.empty:
        encounters["provider_display_name"] = []
        return encounters

    encounters["provider_display_name"] = encounters.apply(
        lambda row: _format_person_name(
            row.get("provider_name"),
            row.get("provider_given_name"),
            row.get("provider_family_name"),
            "Unknown provider",
        ),
        axis=1,
    )
    return encounters


def _fetch_records(conn, query, params, drop=None):
    df = pd.read_sql(query, conn, params=params)
    if df.empty:
        return []
    if drop:
        df = df.drop(columns=drop)
    return df.to_dict("records")


def get_encounter_detail(conn, encounter_id):
    """Return a dictionary containing the complete encounter detail."""
    meta_query = """
        SELECT e.id AS encounter_id,
               e.patient_id,
               e.encounter_date,
               e.encounter_type,
               e.notes,
               p.name AS provider_name,
               p.given_name AS provider_given_name,
               p.family_name AS provider_family_name,
               ds.id AS data_source_id,
               ds.original_filename,
               ds.source_archive_id,
               ds.document_created,
               ds.repository_unique_id,
               ds.document_hash,
               ds.document_size,
               ds.author_institution,
               ds.attachment_id,
               ia.archive_name AS source_archive,
               ia.ingest_count AS source_archive_ingest_count,
               ia.last_ingested_at AS source_archive_last_ingested_at,
               a.file_path AS attachment_path,
               a.mime_type AS attachment_mime_type
          FROM encounter e
          LEFT JOIN provider p ON e.provider_id = p.id
          LEFT JOIN data_source ds ON e.data_source_id = ds.id
          LEFT JOIN ingested_archive ia ON ds.source_archive_id = ia.id
          LEFT JOIN attachment a ON ds.attachment_id = a.id
         WHERE e.id = ?
        """
    meta_df = pd.read_sql(meta_query, conn, params=(encounter_id,))
    if meta_df.empty:
        raise ValueError(f"Encounter {encounter_id} not found.")

    meta_row = meta_df.iloc[0].to_dict()
    patient_id = int(meta_row["patient_id"])

    metadata = {
        "encounter_id": encounter_id,
        "patient_id": patient_id,
        "encounter_date": meta_row.get("encounter_date"),
        "encounter_type": meta_row.get("encounter_type"),
        "notes": meta_row.get("notes"),
        "provider_display_name": _format_person_name(
            meta_row.get("provider_name"),
            meta_row.get("provider_given_name"),
            meta_row.get("provider_family_name"),
            "Unknown provider",
        ),
        "data_source": {
            "id": meta_row.get("data_source_id"),
            "original_filename": meta_row.get("original_filename"),
            "source_archive_id": meta_row.get("source_archive_id"),
            "source_archive": meta_row.get("source_archive"),
            "source_archive_ingest_count": meta_row.get("source_archive_ingest_count"),
            "source_archive_last_ingested_at": meta_row.get(
                "source_archive_last_ingested_at"
            ),
            "document_created": meta_row.get("document_created"),
            "repository_unique_id": meta_row.get("repository_unique_id"),
            "document_hash": meta_row.get("document_hash"),
            "document_size": meta_row.get("document_size"),
            "author_institution": meta_row.get("author_institution"),
        },
        "attachment": {
            "id": meta_row.get("attachment_id"),
            "file_path": meta_row.get("attachment_path"),
            "mime_type": meta_row.get("attachment_mime_type"),
        },
    }

    conditions = _fetch_records(
        conn,
        """
        SELECT name,
               status,
               COALESCE(code, '') AS code,
               COALESCE(code_display, '') AS code_display,
               onset_date,
               notes
          FROM condition
         WHERE encounter_id = ?
         ORDER BY name
        """,
        (encounter_id,),
    )

    medications = _fetch_records(
        conn,
        """
        SELECT name,
               dose,
               route,
               frequency,
               start_date,
               end_date,
               status,
               notes
          FROM medication
         WHERE encounter_id = ?
         ORDER BY name
        """,
        (encounter_id,),
    )

    lab_results = _fetch_records(
        conn,
        """
        SELECT loinc_code,
               test_name,
               result_value,
               unit,
               reference_range,
               abnormal_flag,
               date
          FROM lab_result
         WHERE encounter_id = ?
         ORDER BY date, test_name
        """,
        (encounter_id,),
    )

    vitals = _fetch_records(
        conn,
        """
        SELECT vital_type,
               value,
               unit,
               date
          FROM vital
         WHERE encounter_id = ?
         ORDER BY date, vital_type
        """,
        (encounter_id,),
    )

    progress_notes = _fetch_records(
        conn,
        """
        SELECT note_title,
               note_datetime,
               note_text,
               source_note_id
          FROM progress_note
         WHERE encounter_id = ?
         ORDER BY note_datetime
        """,
        (encounter_id,),
    )

    procedures = _fetch_records(
        conn,
        """
        SELECT name,
               code,
               code_system,
               code_display,
               status,
               date,
               notes
          FROM procedure
         WHERE encounter_id = ?
         ORDER BY date, name
        """,
        (encounter_id,),
    )

    encounter_date = metadata["encounter_date"]
    immunization_cutoff = encounter_date if encounter_date else None
    immunizations_query = """
        SELECT vaccine_name,
               cvx_code,
               date_administered,
               status,
               lot_number,
               notes
          FROM immunization
         WHERE patient_id = ?
           AND ( ? IS NULL
                 OR date_administered IS NULL
                 OR date_administered <= ? )
         ORDER BY date_administered
    """
    immunizations = _fetch_records(
        conn,
        immunizations_query,
        (patient_id, immunization_cutoff, immunization_cutoff),
    )

    return {
        "patient_id": patient_id,
        "metadata": metadata,
        "conditions": conditions,
        "medications": medications,
        "lab_results": lab_results,
        "vitals": vitals,
        "progress_notes": progress_notes,
        "procedures": procedures,
        "immunizations": immunizations,
    }


# AI-assisted change: Implemented with help from gpt-5-codex.
def get_patient_vitals_timeseries(
    conn: SQLCipherConnection,
    patient_id: int,
    vital_type: str | None = None,
) -> pd.DataFrame:
    """Return a patient-level vital sign time series as a DataFrame."""

    query = """
        SELECT vital_type,
               value,
               unit,
               date,
               encounter_id
          FROM vital
         WHERE patient_id = ?
        """
    params: list = [patient_id]
    if vital_type:
        query += " AND vital_type = ?"
        params.append(vital_type)
    query += " ORDER BY date, id"

    df = pd.read_sql(query, conn, params=params)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "vital_type",
                "value",
                "unit",
                "date",
                "encounter_id",
                "value_text",
                "value_numeric",
                "measurement_time",
            ]
        )

    df["value_text"] = df["value"]
    df["value_numeric"] = pd.to_numeric(df["value"], errors="coerce")
    df["measurement_time"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values(["measurement_time", "date", "vital_type"]).reset_index(
        drop=True
    )
    return df


# AI-assisted change: Implemented with help from gpt-5-codex.
def get_patient_lab_timeseries(
    conn: SQLCipherConnection,
    patient_id: int,
    *,
    loinc_code: str | None = None,
    test_name: str | None = None,
) -> pd.DataFrame:
    """Return lab result time series for a patient as a DataFrame."""

    query = """
        SELECT loinc_code,
               test_name,
               result_value,
               unit,
               reference_range,
               abnormal_flag,
               date,
               encounter_id
          FROM lab_result
         WHERE patient_id = ?
        """
    params: list = [patient_id]
    if loinc_code:
        query += " AND loinc_code = ?"
        params.append(loinc_code)
    if test_name:
        query += " AND test_name = ?"
        params.append(test_name)
    query += " ORDER BY date, id"

    df = pd.read_sql(query, conn, params=params)
    if df.empty:
        return pd.DataFrame(
            columns=[
                "loinc_code",
                "test_name",
                "result_value",
                "unit",
                "reference_range",
                "abnormal_flag",
                "date",
                "encounter_id",
                "value_text",
                "value_numeric",
                "result_text",
                "result_numeric",
                "measurement_time",
            ]
        )

    df["value_text"] = df["result_value"]
    df["value_numeric"] = pd.to_numeric(df["result_value"], errors="coerce")
    df["result_text"] = df["value_text"]
    df["result_numeric"] = df["value_numeric"]
    df["measurement_time"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values(
        ["measurement_time", "date", "loinc_code", "test_name"]
    ).reset_index(drop=True)
    return df
