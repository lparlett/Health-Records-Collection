import streamlit as st
from datetime import datetime
import db_utils
import ui_components


def _format_encounter_date(raw_value):
    """Normalize encounter date strings into a readable label."""
    if not raw_value:
        return "Date unknown"
    value = str(raw_value).strip()
    if not value:
        return "Date unknown"
    for fmt in ("%Y%m%d%H%M%S%z", "%Y%m%d%H%M%S", "%Y%m%d"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%b %d, %Y")
        except ValueError:
            continue
    if len(value) >= 8:
        try:
            dt = datetime.strptime(value[:8], "%Y%m%d")
            return dt.strftime("%b %d, %Y")
        except ValueError:
            pass
    return value


def _format_diagnosis_line(entry):
    name = (entry.get("name") or "Unnamed diagnosis").strip()
    code_display = (entry.get("code_display") or "").strip()
    code = (entry.get("code") or "").strip()
    status = (entry.get("status") or "").strip()
    code_part = code_display or code
    pieces = [name]
    if code_part:
        pieces.append(f"({code_part})")
    line = " ".join(pieces)
    if status:
        line += f" - {status}"
    return f"- {line}"


def _format_medication_line(entry):
    name = (entry.get("name") or "Unnamed medication").strip()
    dose = (entry.get("dose") or "").strip()
    route = (entry.get("route") or "").strip()
    frequency = (entry.get("frequency") or "").strip()
    status = (entry.get("status") or "").strip()
    start_date = (entry.get("start_date") or "").strip()
    end_date = (entry.get("end_date") or "").strip()
    notes = (entry.get("notes") or "").strip()

    schedule_parts = [part for part in [dose, route, frequency] if part]
    schedule = ", ".join(schedule_parts)

    duration_parts = []
    if start_date:
        duration_parts.append(start_date)
    if end_date:
        duration_parts.append(f"-> {end_date}")
    duration = " ".join(duration_parts)

    detail_parts = [part for part in [schedule, duration, status] if part]
    detail_text = "; ".join(detail_parts)

    if notes:
        detail_text = detail_text + f" - {notes}" if detail_text else notes

    return f"- {name}" + (f" - {detail_text}" if detail_text else "")


def _sidebar_divider():
    if hasattr(st.sidebar, "divider"):
        st.sidebar.divider()
    else:
        st.sidebar.markdown("---")


def show_tables(conn):
    tables = db_utils.list_tables(conn)
    selected_tables = ui_components.sidebar_table_selector(tables)

    if not selected_tables:
        st.info("<- Select tables from the sidebar to display")
    else:
        for table in selected_tables:
            st.subheader(f"Table: {table}")
            df = db_utils.get_table_preview(conn, table)
            st.dataframe(df, use_container_width=True)


def show_query(conn):
    sql = ui_components.query_box()
    if sql.strip():
        try:
            df = db_utils.run_query(conn, sql)
            st.subheader("Query Results")
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"Error: {e}")


def show_encounters(conn):
    st.header("Encounter Overview")

    patients = db_utils.get_patients(conn)
    if patients.empty:
        st.info("No patients found in the database.")
        return

    patient_options = {row["display_name"]: int(row["id"]) for _, row in patients.iterrows()}

    _sidebar_divider()
    st.sidebar.header("Encounter Filters")
    selected_label = st.sidebar.selectbox("Patient", options=list(patient_options.keys()))
    patient_id = patient_options[selected_label]

    patient_row = patients[patients["id"] == patient_id].iloc[0]
    st.caption(
        " | ".join(
            part
            for part in [
                f"Patient: {selected_label}",
                f"DOB: {patient_row['birth_date']}" if patient_row.get("birth_date") else None,
            ]
            if part
        )
    )

    encounters = db_utils.get_encounter_details(conn, patient_id)
    if encounters.empty:
        st.info("No encounters recorded for this patient.")
        return

    st.write(f"{len(encounters)} encounter{'s' if len(encounters) != 1 else ''} found.")

    for _, row in encounters.iterrows():
        encounter_date = _format_encounter_date(row.get("encounter_date"))
        encounter_type = (row.get("encounter_type") or "Encounter").strip() or "Encounter"
        provider = row.get("provider_display_name") or "Unknown provider"

        header = f"{encounter_date} | {encounter_type}"
        with st.expander(header):
            st.markdown(f"**Provider:** {provider}")
            notes = (row.get("notes") or "").strip()
            if notes:
                st.markdown(f"**Notes:** {notes}")

            diagnoses = row.get("diagnoses") or []
            st.markdown("**Diagnoses**")
            if diagnoses:
                diag_lines = [_format_diagnosis_line(item) for item in diagnoses]
                st.markdown("\n".join(diag_lines))
            else:
                st.markdown("- None recorded")

            medications = row.get("medications") or []
            st.markdown("**Medications**")
            if medications:
                med_lines = [_format_medication_line(item) for item in medications]
                st.markdown("\n".join(med_lines))
            else:
                st.markdown("- None recorded")

