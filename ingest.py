import zipfile
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence, Tuple
from lxml import etree

from parsers import parse_conditions, parse_encounters, parse_labs, parse_medications, parse_patient

# =====================
# Paths
# =====================
RAW_DIR = Path("data/raw")
PARSED_DIR = Path("data/parsed")
DB_PATH = Path("db/health_records.db")
SCHEMA_FILE = Path("schema.sql")

ProviderKey = Tuple[str, str, str, str]
_PROVIDER_CACHE: dict[ProviderKey, int] = {}


# =====================
# Init DB
# =====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    if SCHEMA_FILE.exists():
        with open(SCHEMA_FILE, "r") as f:
            conn.executescript(f.read())
    return conn


# =====================
# Unzip XDM Package
# =====================
def unzip_raw_files(zip_file: Path, dest: Path):
    """
    Unzips a file into the given destination directory,
    but only if the destination doesn't already exist or is empty.
    """
    # Check if destination directory already exists and has files
    if dest.exists() and any(dest.iterdir()):
        print(f"Skipping {zip_file.name}, {dest} already exists and is not empty.")
        return

    # Make sure destination directory exists
    dest.mkdir(parents=True, exist_ok=True)

    # Extract contents
    with zipfile.ZipFile(zip_file, "r") as zip_ref:
        zip_ref.extractall(dest)

    print(f"Extracted {zip_file.name} -> {dest}")


# =====================
# CCD Parsing Helpers
# =====================
def parse_ccd(xml_file):
    """Parse a CCD XML file into a dict of patient + clinical data"""
    tree = etree.parse(str(xml_file))
    ns = {"hl7": "urn:hl7-org:v3"}

    patient = parse_patient(tree, ns)
    encounters = parse_encounters(tree, ns)
    medications = parse_medications(tree, ns)
    labs = parse_labs(tree, ns)
    conditions = parse_conditions(tree, ns)

    return {"patient": patient, "encounters": encounters, "medications": medications, "labs": labs, "conditions": conditions}



def get_or_create_provider(
    conn,
    name: Optional[str],
    npi: Optional[str] = None,
    specialty: Optional[str] = None,
    organization: Optional[str] = None,
) -> Optional[int]:
    if not name:
        return None
    name_clean = name.strip()
    if not name_clean:
        return None
    npi_clean = npi.strip() if npi else ""
    specialty_clean = specialty.strip() if specialty else ""
    organization_clean = organization.strip() if organization else ""
    cache_key: ProviderKey = (name_clean, npi_clean, specialty_clean, organization_clean)
    if cache_key in _PROVIDER_CACHE:
        return _PROVIDER_CACHE[cache_key]
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id
          FROM provider
         WHERE name = ?
           AND COALESCE(npi, '') = ?
           AND COALESCE(specialty, '') = ?
           AND COALESCE(organization, '') = ?
        """,
        (name_clean, npi_clean, specialty_clean, organization_clean),
    )
    row = cur.fetchone()
    if row:
        provider_id = row[0]
        _PROVIDER_CACHE[cache_key] = provider_id
        return provider_id
    cur.execute(
        """
        INSERT INTO provider (name, npi, specialty, organization)
        VALUES (?, ?, ?, ?)
        """,
        (
            name_clean,
            npi_clean or None,
            specialty_clean or None,
            organization_clean or None,
        ),
    )
    conn.commit()
    provider_id = cur.lastrowid
    _PROVIDER_CACHE[cache_key] = provider_id
    return provider_id



def find_encounter_id(
    conn,
    patient_id: int,
    encounter_date: Optional[str] = None,
    provider_name: Optional[str] = None,
    *,
    provider_id: Optional[int] = None,
    source_encounter_id: Optional[str] = None,
) -> Optional[int]:
    if provider_id is None and provider_name:
        provider_id = get_or_create_provider(conn, provider_name)
    cur = conn.cursor()

    def fetch(sql: str, params: tuple) -> Optional[int]:
        row = cur.execute(sql, params).fetchone()
        if row:
            return row[0]
        return None

    def date_only(value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        digits = ''.join(ch for ch in value if ch.isdigit())
        if len(digits) >= 8:
            return digits[:8]
        return None

    def run_query(base_sql: str, base_params: list[Any], order_clause: str) -> Optional[int]:
        if provider_id is not None:
            params_with_provider = tuple(base_params + [provider_id])
            sql_with_provider = base_sql + " AND COALESCE(provider_id, -1) = COALESCE(?, -1)" + order_clause
            match = fetch(sql_with_provider, params_with_provider)
            if match is not None:
                return match
        return fetch(base_sql + order_clause, tuple(base_params))

    encounter_day = date_only(encounter_date)

    if source_encounter_id:
        params = [patient_id, source_encounter_id]
        base_sql = (
            """
            SELECT id
              FROM encounter
             WHERE patient_id = ?
               AND COALESCE(source_encounter_id, '') = COALESCE(?, '')
            """
        )
        if encounter_date:
            base_sql += " AND COALESCE(encounter_date, '') = COALESCE(?, '')"
            params.append(encounter_date)
        match = run_query(base_sql, params, " ORDER BY encounter_date DESC, id DESC LIMIT 1")
        if match is not None:
            return match
        if encounter_day:
            params = [patient_id, source_encounter_id, encounter_day]
            base_sql = (
                """
                SELECT id
                  FROM encounter
                 WHERE patient_id = ?
                   AND COALESCE(source_encounter_id, '') = COALESCE(?, '')
                   AND substr(COALESCE(encounter_date, ''), 1, 8) = ?
                """
            )
            match = run_query(base_sql, params, " ORDER BY encounter_date DESC, id DESC LIMIT 1")
            if match is not None:
                return match

    if encounter_date:
        params = [patient_id, encounter_date]
        base_sql = (
            """
            SELECT id
              FROM encounter
             WHERE patient_id = ?
               AND COALESCE(encounter_date, '') = COALESCE(?, '')
            """
        )
        match = run_query(base_sql, params, " ORDER BY id DESC LIMIT 1")
        if match is not None:
            return match

    if encounter_day:
        params = [patient_id, encounter_day]
        base_sql = (
            """
            SELECT id
              FROM encounter
             WHERE patient_id = ?
               AND substr(COALESCE(encounter_date, ''), 1, 8) = ?
            """
        )
        match = run_query(base_sql, params, " ORDER BY encounter_date DESC, id DESC LIMIT 1")
        if match is not None:
            return match

    if provider_id is not None:
        base_sql = (
            """
            SELECT id
              FROM encounter
             WHERE patient_id = ?
            """
        )
        return run_query(base_sql, [patient_id], " ORDER BY encounter_date DESC, id DESC LIMIT 1")

    return None

def insert_records(
    conn,
    table: str,
    columns: Sequence[str],
    items: Iterable[dict],
    row_builder: Callable[[dict], Sequence[object]],
) -> None:
    if not items:
        return
    placeholders = ', '.join(['?'] * len(columns))
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})"
    cur = conn.cursor()
    cur.executemany(sql, (row_builder(item) for item in items))
    conn.commit()


def insert_patient(conn, patient, source_file):
    cur = conn.cursor()

    given_raw = patient.get("given") or ""
    family_raw = patient.get("family") or ""
    dob_raw = patient.get("dob") or ""
    gender_raw = patient.get("gender") or ""

    given = given_raw.strip()
    family = family_raw.strip()
    dob = dob_raw.strip()
    gender = gender_raw.strip()

    cur.execute(
        """SELECT id, gender, source_file
           FROM patient
           WHERE COALESCE(given_name, '') = ?
             AND COALESCE(family_name, '') = ?
             AND COALESCE(birth_date, '') = ?""",
        (given, family, dob)
    )
    row = cur.fetchone()
    if row:
        patient_id, existing_gender, existing_source = row
        updates = []
        params = []
        if gender and (existing_gender or "") != gender:
            updates.append("gender = ?")
            params.append(gender)
        if source_file and (existing_source or "") != source_file:
            updates.append("source_file = ?")
            params.append(source_file)
        if updates:
            params.append(patient_id)
            cur.execute(f"UPDATE patient SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        return patient_id

    cur.execute(
        """INSERT INTO patient (given_name, family_name, birth_date, gender, source_file)
           VALUES (?, ?, ?, ?, ?)""",
        (given or None, family or None, dob or None, gender or None, source_file)
    )
    conn.commit()
    return cur.lastrowid



def insert_conditions(conn, patient_id, conditions):
    if not conditions:
        return
    cur = conn.cursor()
    for cond in conditions:
        provider_name = cond.get("provider")
        provider_id = None
        if provider_name:
            provider_id = get_or_create_provider(conn, provider_name)
        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=cond.get("encounter_start") or cond.get("start") or cond.get("author_time"),
            provider_name=provider_name,
            provider_id=provider_id,
            source_encounter_id=cond.get("encounter_source_id"),
        )
        if encounter_id is None and cond.get("encounter_end"):
            encounter_id = find_encounter_id(
                conn,
                patient_id,
                encounter_date=cond.get("encounter_end"),
                provider_name=provider_name,
                provider_id=provider_id,
                source_encounter_id=cond.get("encounter_source_id"),
            )

        codes = cond.get("codes") or []
        primary_code = codes[0] if codes else {}
        code_value = (primary_code.get("code") or "").strip() or None
        code_system = (primary_code.get("system") or "").strip() or None
        code_display = (primary_code.get("display") or "").strip() or None

        name = (cond.get("name") or code_display or code_value or "").strip()
        if not name:
            continue

        onset_date = cond.get("start") or None
        status = cond.get("status") or None
        notes = cond.get("notes") or None

        existing = cur.execute(
            """
            SELECT id, status, notes, provider_id, encounter_id
              FROM condition
             WHERE patient_id = ?
               AND COALESCE(name, '') = COALESCE(?, '')
               AND COALESCE(code, '') = COALESCE(?, '')
               AND COALESCE(onset_date, '') = COALESCE(?, '')
            """,
            (patient_id, name, code_value or '', onset_date or ''),
        ).fetchone()

        if existing:
            condition_id, existing_status, existing_notes, existing_provider_id, existing_encounter_id = existing
            updates = []
            params = []
            if status and (existing_status or "") != status:
                updates.append("status = ?")
                params.append(status)
            if notes and (existing_notes or "") != notes:
                updates.append("notes = ?")
                params.append(notes)
            if provider_id and (existing_provider_id or 0) != provider_id:
                updates.append("provider_id = ?")
                params.append(provider_id)
            if encounter_id and (existing_encounter_id or 0) != encounter_id:
                updates.append("encounter_id = ?")
                params.append(encounter_id)
            if updates:
                params.append(condition_id)
                cur.execute(
                    f"UPDATE condition SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
        else:
            cur.execute(
                """
                INSERT INTO condition (
                    patient_id,
                    name,
                    onset_date,
                    status,
                    notes,
                    provider_id,
                    encounter_id,
                    code,
                    code_system,
                    code_display
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    patient_id,
                    name,
                    onset_date,
                    status,
                    notes,
                    provider_id,
                    encounter_id,
                    code_value,
                    code_system,
                    code_display,
                ),
            )
            condition_id = cur.lastrowid

        for code in codes:
            code_val = (code.get("code") or "").strip()
            if not code_val:
                continue
            code_system_val = (code.get("system") or "").strip()
            display_val = (code.get("display") or "").strip() or None
            cur.execute(
                """
                INSERT OR IGNORE INTO condition_code (condition_id, code, code_system, display_name)
                VALUES (?, ?, ?, ?)
                """,
                (
                    condition_id,
                    code_val,
                    code_system_val,
                    display_val,
                ),
            )
    conn.commit()
def insert_encounters(conn, patient_id, encounters):
    if not encounters:
        return
    cur = conn.cursor()
    for enc in encounters:
        provider_name = enc.get("provider")
        provider_id = None
        if provider_name:
            provider_id = get_or_create_provider(conn, provider_name)
        encounter_date = enc.get("start") or enc.get("end")
        source_encounter_id = enc.get("source_id")
        encounter_type = enc.get("type")
        notes = enc.get("notes")
        if not notes:
            fallback_parts = [
                enc.get("location"),
                enc.get("status"),
                enc.get("mood"),
                enc.get("code"),
            ]
            fallback = " | ".join(part for part in fallback_parts if part)
            notes = fallback or None
        if not (encounter_date or source_encounter_id):
            continue
        existing = cur.execute(
            """
            SELECT id, encounter_type, notes
              FROM encounter
             WHERE patient_id = ?
               AND COALESCE(encounter_date, '') = COALESCE(?, '')
               AND COALESCE(provider_id, -1) = COALESCE(?, -1)
               AND COALESCE(source_encounter_id, '') = COALESCE(?, '')
            """,
            (patient_id, encounter_date, provider_id, source_encounter_id),
        ).fetchone()
        if existing:
            encounter_db_id, existing_type, existing_notes = existing
            updates = []
            params = []
            if encounter_type and (existing_type or "") != encounter_type:
                updates.append("encounter_type = ?")
                params.append(encounter_type)
            if notes and (existing_notes or "") != notes:
                updates.append("notes = ?")
                params.append(notes)
            if updates:
                params.append(encounter_db_id)
                cur.execute(
                    "UPDATE encounter SET " + ", ".join(updates) + " WHERE id = ?",
                    params,
                )
            continue
        cur.execute(
            """
            INSERT INTO encounter (
                patient_id,
                encounter_date,
                provider_id,
                source_encounter_id,
                encounter_type,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id,
                encounter_date,
                provider_id,
                source_encounter_id,
                encounter_type,
                notes,
            ),
        )
    conn.commit()
def insert_medications(conn, patient_id, meds):
    columns = [
        "patient_id",
        "encounter_id",
        "name",
        "dose",
        "route",
        "frequency",
        "start_date",
        "end_date",
        "status",
        "notes",
    ]

    def build_row(m):
        notes = m.get("notes")
        rxnorm = m.get("rxnorm")
        if rxnorm:
            if notes:
                notes = f"{notes} (RxNorm: {rxnorm})"
            else:
                notes = f"RxNorm: {rxnorm}"
        encounter_date = m.get("start") or m.get("end") or m.get("author_time")
        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=encounter_date,
            provider_name=m.get("provider"),
        )
        return (
            patient_id,
            encounter_id,
            m.get("name"),
            m.get("dose"),
            m.get("route"),
            m.get("frequency"),
            m.get("start"),
            m.get("end"),
            m.get("status"),
            notes,
        )

    insert_records(conn, "medication", columns, meds, build_row)




def insert_labs(conn, patient_id, labs):
    columns = [
        "patient_id",
        "encounter_id",
        "loinc_code",
        "test_name",
        "result_value",
        "unit",
        "reference_range",
        "abnormal_flag",
        "date",
        "ordering_provider_id",
        "performing_org_id",
    ]

    def build_row(result):
        ordering_provider_name = result.get("ordering_provider")
        performing_org_name = result.get("performing_org")
        ordering_provider_id = (
            get_or_create_provider(conn, ordering_provider_name)
            if ordering_provider_name
            else None
        )
        performing_org_id = (
            get_or_create_provider(conn, performing_org_name)
            if performing_org_name
            else None
        )
        encounter_id = find_encounter_id(
            conn,
            patient_id,
            encounter_date=result.get("encounter_start") or result.get("date"),
            provider_name=ordering_provider_name,
            provider_id=ordering_provider_id,
            source_encounter_id=result.get("encounter_source_id"),
        )
        if encounter_id is None:
            encounter_id = find_encounter_id(
                conn,
                patient_id,
                encounter_date=result.get("encounter_end") or result.get("date"),
                provider_name=performing_org_name,
                provider_id=performing_org_id,
                source_encounter_id=result.get("encounter_source_id"),
            )
        return (
            patient_id,
            encounter_id,
            result.get("loinc"),
            result.get("test_name"),
            result.get("value"),
            result.get("unit"),
            result.get("reference_range"),
            result.get("abnormal_flag"),
            result.get("date"),
            ordering_provider_id,
            performing_org_id,
        )

    insert_records(conn, "lab_result", columns, labs, build_row)


# =====================
# Main Workflow
# =====================
def main():
    conn = init_db()

    for zip_file in RAW_DIR.glob("*.zip"):
        dest = PARSED_DIR / zip_file.stem
        if not dest.exists():
            unzip_raw_files(zip_file, dest)

        for xml_file in dest.rglob("*.xml"):
            parsed = parse_ccd(xml_file)
            patient = parsed["patient"]

            if patient["given"] or patient["family"]:
                pid = insert_patient(conn, patient, zip_file.name)
                insert_encounters(conn, pid, parsed["encounters"])
                insert_conditions(conn, pid, parsed["conditions"])
                insert_medications(conn, pid, parsed["medications"])
                insert_labs(conn, pid, parsed["labs"])
                print(f"Inserted patient {patient['given']} {patient['family']} with {len(parsed['encounters'])} encounters, {len(parsed['conditions'])} conditions, {len(parsed['medications'])} meds and {len(parsed['labs'])} labs")

    conn.close()


if __name__ == "__main__":
    main()



