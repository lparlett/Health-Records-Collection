"""Main ingestion workflow."""

import zipfile
import sqlite3
from pathlib import Path
from lxml import etree

from parsers import (
    parse_conditions,
    parse_encounters,
    parse_labs,
    parse_medications,
    parse_patient,
    parse_procedures,
)
from db.schema import ensure_provider_schema
from services.patient import insert_patient
from services.encounters import insert_encounters
from services.conditions import insert_conditions
from services.procedures import insert_procedures
from services.medications import insert_medications
from services.labs import insert_labs

RAW_DIR = Path("data/raw")
PARSED_DIR = Path("data/parsed")
DB_PATH = Path("db/health_records.db")
SCHEMA_FILE = Path("schema.sql")


def init_db() -> sqlite3.Connection:
    """Initialise the SQLite database connection and apply the schema if present."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    if SCHEMA_FILE.exists():
        with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
            conn.executescript(f.read())
    ensure_provider_schema(conn)
    return conn


def unzip_raw_files(zip_file: Path, dest: Path) -> None:
    """Unzip a CCD package into *dest* if the directory is missing or empty."""
    if dest.exists() and any(dest.iterdir()):
        print(f"Skipping {zip_file.name}, {dest} already exists and is not empty.")
        return

    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_file, "r") as zip_ref:
        zip_ref.extractall(dest)
    print(f"Extracted {zip_file.name} -> {dest}")


def parse_ccd(xml_file: Path) -> dict[str, object]:
    """Parse a CCD XML document into structured collections."""
    tree = etree.parse(str(xml_file))
    ns = {"hl7": "urn:hl7-org:v3"}

    patient = parse_patient(tree, ns)
    encounters = parse_encounters(tree, ns)
    medications = parse_medications(tree, ns)
    labs = parse_labs(tree, ns)
    conditions = parse_conditions(tree, ns)
    procedures = parse_procedures(tree, ns)

    return {
        "patient": patient,
        "encounters": encounters,
        "medications": medications,
        "labs": labs,
        "conditions": conditions,
        "procedures": procedures,
    }


def main() -> None:
    """Ingest all CCD archives under *data/raw* into the SQLite database."""
    conn = init_db()

    for zip_file in RAW_DIR.glob("*.zip"):
        dest = PARSED_DIR / zip_file.stem
        if not dest.exists():
            unzip_raw_files(zip_file, dest)

        for xml_file in dest.rglob("*.xml"):
            parsed = parse_ccd(xml_file)
            patient_data = parsed.get("patient")
            if not isinstance(patient_data, dict):
                continue

            given = (patient_data.get("given") or "").strip()
            family = (patient_data.get("family") or "").strip()
            if not (given or family):
                continue

            encounters = parsed.get("encounters") or []
            conditions = parsed.get("conditions") or []
            procedures = parsed.get("procedures") or []
            medications = parsed.get("medications") or []
            labs = parsed.get("labs") or []

            if not isinstance(encounters, list):
                encounters = []
            if not isinstance(conditions, list):
                conditions = []
            if not isinstance(procedures, list):
                procedures = []
            if not isinstance(medications, list):
                medications = []
            if not isinstance(labs, list):
                labs = []

            pid = insert_patient(conn, patient_data, zip_file.name)
            insert_encounters(conn, pid, encounters)
            insert_conditions(conn, pid, conditions)
            insert_procedures(conn, pid, procedures)
            dup_meds = insert_medications(conn, pid, medications)
            insert_labs(conn, pid, labs)

            message = (
                f"Inserted patient {given} {family} with "
                f"{len(encounters)} encounters, "
                f"{len(conditions)} conditions, "
                f"{len(procedures)} procedures, "
                f"{len(medications)} meds "
                f"and {len(labs)} labs"
            )
            if dup_meds:
                message += f" (skipped {dup_meds} duplicate meds)"
            print(message)
    conn.close()


if __name__ == "__main__":
    main()
