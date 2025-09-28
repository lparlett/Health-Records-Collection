import os
import zipfile
import sqlite3
from pathlib import Path
from datetime import datetime
from lxml import etree

# =====================
# Paths
# =====================
RAW_DIR = Path("data/raw")
PARSED_DIR = Path("data/parsed")
DB_PATH = Path("db/health.db")
SCHEMA_FILE = Path("schema.sql")
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

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
    def debug_observation(obs, ns):
        print("\n--- Observation Debug ---")
        for child in obs:
            tag = etree.QName(child).localname
            print(f"Child: {tag}")
            if child.attrib:
                print("  Attributes:", child.attrib)
            if child.text and child.text.strip():
                print("  Text:", child.text.strip())

    tree = etree.parse(str(xml_file))
    ns = {"hl7": "urn:hl7-org:v3"}

    # --- Patient ---
    given = tree.findtext(".//hl7:patient//hl7:given", namespaces=ns)
    family = tree.findtext(".//hl7:patient//hl7:family", namespaces=ns)
    dob = tree.findtext(".//hl7:patient//hl7:birthTime", namespaces=ns)
    gender = tree.findtext(".//hl7:patient//hl7:administrativeGenderCode", namespaces=ns)

    patient = {
        "given": given,
        "family": family,
        "dob": dob,
        "gender": gender
    }

    def get_text_by_id(ref_value):
        if not ref_value:
            return None
        ref_id = ref_value.lstrip("#")
        nodes = tree.xpath(f"//*[@ID='{ref_id}']", namespaces=ns)
        if nodes:
            text_value = nodes[0].xpath("string()")
            if text_value:
                return text_value.strip()
        return None

    # --- Medications ---
    medications = []
    med_nodes = tree.xpath(".//hl7:substanceAdministration[hl7:templateId[@root='2.16.840.1.113883.10.20.22.4.16']]", namespaces=ns)
    for med in med_nodes:
        code_el = med.find(".//hl7:manufacturedMaterial/hl7:code", namespaces=ns)
        med_name = None
        rxnorm_code = None
        if code_el is not None:
            med_name = (code_el.get("displayName") or "").strip() or None
            rxnorm_code = (code_el.get("code") or "").strip() or None
            if not med_name:
                ref = code_el.find("hl7:originalText/hl7:reference", namespaces=ns)
                if ref is not None and ref.get("value"):
                    med_name = get_text_by_id(ref.get("value"))
        sig_text = None
        sig_ref = med.find("hl7:text/hl7:reference", namespaces=ns)
        if sig_ref is not None and sig_ref.get("value"):
            sig_text = get_text_by_id(sig_ref.get("value"))
        start_el = med.find("hl7:effectiveTime/hl7:low", namespaces=ns)
        start = start_el.get("value") if start_el is not None else None
        end_el = med.find("hl7:effectiveTime/hl7:high", namespaces=ns)
        end = end_el.get("value") if end_el is not None else None
        route_el = med.find("hl7:routeCode", namespaces=ns)
        route = None
        if route_el is not None:
            route = (route_el.get("displayName") or route_el.get("code") or "").strip() or None
            if not route:
                route = (route_el.findtext("hl7:originalText", namespaces=ns) or "").strip() or None
        dose = None
        dose_el = med.find("hl7:doseQuantity", namespaces=ns)
        if dose_el is not None:
            dose_value = (dose_el.get("value") or "").strip()
            dose_unit = (dose_el.get("unit") or "").strip()
            if dose_value or dose_unit:
                dose = " ".join([part for part in (dose_value, dose_unit) if part])
        frequency = None
        for eff in med.findall("hl7:effectiveTime", namespaces=ns):
            xsi_type = eff.get(f"{{{XSI_NS}}}type")
            if xsi_type and xsi_type.upper() == "PIVL_TS":
                period = eff.find("hl7:period", namespaces=ns)
                if period is not None:
                    period_value = (period.get("value") or "").strip()
                    period_unit = (period.get("unit") or "").strip()
                    if period_value and period_unit:
                        frequency = f"Every {period_value} {period_unit}"
                    elif period_unit:
                        frequency = f"Every {period_unit}"
                    elif period_value:
                        frequency = f"Every {period_value}"
                if not frequency:
                    freq_text = eff.findtext("hl7:originalText", namespaces=ns)
                    if freq_text:
                        frequency = freq_text.strip()
                break
        status = None
        status_nodes = med.xpath("hl7:entryRelationship/hl7:observation[hl7:code[@code='33999-4']]/hl7:value", namespaces=ns)
        status_value = status_nodes[0] if status_nodes else None
        if status_value is not None:
            status = (status_value.get("displayName") or status_value.get("code") or "").strip() or None
        if status is None:
            status_code_el = med.find("hl7:statusCode", namespaces=ns)
            if status_code_el is not None:
                status = (status_code_el.get("code") or "").strip() or None
        if status:
            status = status.title()
        if not med_name:
            if sig_text:
                med_name = sig_text
            elif rxnorm_code:
                med_name = rxnorm_code
        if not med_name:
            continue
        medications.append({
            "name": med_name,
            "rxnorm": rxnorm_code,
            "dose": dose,
            "route": route,
            "frequency": frequency,
            "start": start,
            "end": end,
            "status": status,
            "notes": sig_text
        })

    # --- Labs ---
    labs = []
    results_section_nodes = tree.xpath(".//hl7:section[hl7:code[@code='30954-2']]", namespaces=ns)
    results_section = results_section_nodes[0] if results_section_nodes else None
    if results_section is not None and results_section.get("nullFlavor") != "NI":
        for organizer in results_section.findall("hl7:entry/hl7:organizer", namespaces=ns):
            organizer_flag = None
            lab_observations = organizer.findall("hl7:component/hl7:observation", namespaces=ns)
            for obs in lab_observations:
                code_el = obs.find("hl7:code", namespaces=ns)
                if code_el is None:
                    print("Skipping observation: no <code> element")
                    continue

                code = code_el.get("code")
                code_system = code_el.get("codeSystem")
                code_system_name = code_el.get("codeSystemName")
                display_name = code_el.get("displayName")

                if not (
                    code_system == "2.16.840.1.113883.6.1"
                    or (code_system_name and code_system_name.upper() == "LOINC")
                ):
                    continue
                if not code:
                    continue
                if code == "56850-1":
                    panel_val_el = obs.find("hl7:value", namespaces=ns)
                    panel_flag = None
                    if panel_val_el is not None:
                        panel_flag = panel_val_el.get("value")
                        if not panel_flag:
                            text_val = (panel_val_el.text or "").strip()
                            if not text_val:
                                text_val = panel_val_el.xpath("string()").strip()
                            panel_flag = text_val or panel_val_el.get("displayName") or panel_val_el.get("code")
                    if panel_flag:
                        organizer_flag = panel_flag
                    continue

                loinc = code
                test_name = display_name or code_el.findtext("hl7:originalText", namespaces=ns)
                if not test_name:
                    test_name = loinc

                val_el = obs.find("hl7:value", namespaces=ns)
                value, unit = None, None
                if val_el is not None:
                    xsi_type = val_el.get(f"{{{XSI_NS}}}type")
                    if val_el.get("value"):
                        value = val_el.get("value")
                    else:
                        text_val = (val_el.text or "").strip()
                        if not text_val:
                            text_val = val_el.xpath("string()").strip()
                        value = text_val or val_el.get("displayName") or val_el.get("code")
                    unit = val_el.get("unit")
                    if not unit and xsi_type in {"CD", "CE", "CV"}:
                        unit = val_el.get("codeSystemName")
                if not value:
                    continue

                date = None
                eff = obs.find("hl7:effectiveTime", namespaces=ns)
                if eff is not None:
                    if eff.get("value"):
                        date = eff.get("value")
                    else:
                        low = eff.find("hl7:low", namespaces=ns)
                        high = eff.find("hl7:high", namespaces=ns)
                        if low is not None and low.get("value"):
                            date = low.get("value")
                        elif high is not None and high.get("value"):
                            date = high.get("value")

                ref_range = None
                ref_text = obs.findtext(".//hl7:referenceRange//hl7:observationRange//hl7:text", namespaces=ns)
                if ref_text:
                    ref_range = ref_text.strip()

                abnormal_flag = None
                interp = obs.find("hl7:interpretationCode", namespaces=ns)
                if interp is not None:
                    abnormal_flag = interp.get("code") or interp.get("displayName")
                if not abnormal_flag:
                    interp = obs.find(".//hl7:referenceRange//hl7:interpretationCode", namespaces=ns)
                    if interp is not None:
                        abnormal_flag = interp.get("code") or interp.get("displayName")
                if not abnormal_flag and organizer_flag:
                    abnormal_flag = organizer_flag

                labs.append({
                    "test_name": test_name,
                    "loinc": loinc,
                    "value": value,
                    "unit": unit,
                    "reference_range": ref_range,
                    "abnormal_flag": abnormal_flag,
                    "date": date
                })

    return {"patient": patient, "medications": medications, "labs": labs}
# =====================
# Insert into DB
# =====================
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

def insert_medications(conn, patient_id, meds):
    cur = conn.cursor()
    for m in meds:
        notes = m.get("notes")
        rxnorm = m.get("rxnorm")
        if rxnorm:
            if notes:
                notes = f"{notes} (RxNorm: {rxnorm})"
            else:
                notes = f"RxNorm: {rxnorm}"
        cur.execute(
            """INSERT INTO medication (patient_id, encounter_id, name, dose, route, frequency, start_date, end_date, status, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                patient_id,
                None,
                m.get("name"),
                m.get("dose"),
                m.get("route"),
                m.get("frequency"),
                m.get("start"),
                m.get("end"),
                m.get("status"),
                notes
            )
        )
    conn.commit()

def insert_labs(conn, patient_id, labs):
    cur = conn.cursor()
    for l in labs:
        cur.execute(
            """INSERT INTO lab_result (patient_id, loinc_code, test_name, result_value, unit, reference_range, abnormal_flag, date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                patient_id,
                l.get("loinc"),
                l.get("test_name"),
                l.get("value"),
                l.get("unit"),
                l.get("reference_range"),
                l.get("abnormal_flag"),
                l.get("date")
            )
        )
    conn.commit()

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
                insert_medications(conn, pid, parsed["medications"])
                insert_labs(conn, pid, parsed["labs"])
                print(f"Inserted patient {patient['given']} {patient['family']} with {len(parsed['medications'])} meds and {len(parsed['labs'])} labs")

    conn.close()

if __name__ == "__main__":
    main()
