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
    query = (
        """
        SELECT id, given_name, family_name, birth_date
          FROM patient
         ORDER BY COALESCE(family_name, ''), COALESCE(given_name, ''), id
        """
    )
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
    encounters_query = (
        """
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
    )
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
    meta_query = (
        """
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
               ds.source_archive,
               ds.document_created,
               ds.repository_unique_id,
               ds.document_hash,
               ds.document_size,
               ds.author_institution,
               ds.attachment_id,
               a.file_path AS attachment_path,
               a.mime_type AS attachment_mime_type
          FROM encounter e
          LEFT JOIN provider p ON e.provider_id = p.id
          LEFT JOIN data_source ds ON e.data_source_id = ds.id
          LEFT JOIN attachment a ON ds.attachment_id = a.id
         WHERE e.id = ?
        """
    )
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
            "source_archive": meta_row.get("source_archive"),
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
    conn,
    patient_id,
    vital_type=None,
):
    """Return a patient-level vital sign time series as a DataFrame."""

    query = (
        """
        SELECT vital_type,
               value,
               unit,
               date,
               encounter_id
          FROM vital
         WHERE patient_id = ?
        """
    )
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
    conn,
    patient_id,
    *,
    loinc_code=None,
    test_name=None,
):
    """Return lab result time series for a patient as a DataFrame."""

    query = (
        """
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
    )
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
