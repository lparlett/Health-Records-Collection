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


def get_encounter_details(conn, patient_id):
    """Fetch encounter metadata with associated diagnoses and medications."""
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
        encounters["diagnoses"] = []
        encounters["medications"] = []
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

    encounter_ids = encounters["encounter_id"].tolist()
    placeholder = ",".join(["?"] * len(encounter_ids))

    diagnoses_query = (
        """
        SELECT encounter_id,
               name,
               status,
               COALESCE(code, '') AS code,
               COALESCE(code_display, '') AS code_display
          FROM condition
         WHERE encounter_id IN ({})
         ORDER BY encounter_id, name
        """.format(placeholder)
    )
    diagnoses_df = pd.read_sql(diagnoses_query, conn, params=encounter_ids)

    medications_query = (
        """
        SELECT encounter_id,
               name,
               dose,
               route,
               frequency,
               start_date,
               end_date,
               status,
               notes
          FROM medication
         WHERE encounter_id IN ({})
         ORDER BY encounter_id, name
        """.format(placeholder)
    )
    medications_df = pd.read_sql(medications_query, conn, params=encounter_ids)

    diagnoses_map = {
        encounter_id: grp.drop(columns=["encounter_id"]).to_dict("records")
        for encounter_id, grp in diagnoses_df.groupby("encounter_id")
    } if not diagnoses_df.empty else {}

    medications_map = {
        encounter_id: grp.drop(columns=["encounter_id"]).to_dict("records")
        for encounter_id, grp in medications_df.groupby("encounter_id")
    } if not medications_df.empty else {}

    encounters["diagnoses"] = encounters["encounter_id"].map(lambda idx: diagnoses_map.get(idx, []))
    encounters["medications"] = encounters["encounter_id"].map(lambda idx: medications_map.get(idx, []))

    return encounters
