from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd
import streamlit as st

import db_utils
import ui_components


def _ensure_state() -> None:
    state = st.session_state
    state.setdefault("app_view", "overview")
    state.setdefault("selected_patient_id", None)
    state.setdefault("selected_patient_label", None)
    state.setdefault("selected_encounter_id", None)
    if "_rerun_fn" not in state:
        rerun_fn = getattr(st, "experimental_rerun", None) or getattr(st, "rerun", None)
        state["_rerun_fn"] = rerun_fn


def _rerun() -> None:
    rerun_callable = st.session_state.get("_rerun_fn")
    if rerun_callable is not None:
        rerun_callable()


def render_patient_encounter_experience(conn) -> bool:
    """Render the encounter experience. Returns True when overview is active."""
    _ensure_state()
    state = st.session_state
    if state["app_view"] == "detail":
        _show_encounter_detail(conn)
        return False
    _show_encounter_overview(conn)
    return True


def _format_datetime(raw_value: Any, *, show_time: bool = False) -> str:
    if not raw_value:
        return "Unknown"
    value = str(raw_value).strip()
    if not value:
        return "Unknown"
    for fmt in ("%Y%m%d%H%M%S%z", "%Y%m%d%H%M%S", "%Y%m%d"):
        try:
            dt = datetime.strptime(value, fmt)
            if show_time and fmt != "%Y%m%d":
                return dt.strftime("%b %d, %Y %H:%M")
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


def _sidebar_divider() -> None:
    if hasattr(st.sidebar, "divider"):
        st.sidebar.divider()
    else:
        st.sidebar.markdown("---")


def _show_encounter_overview(conn) -> None:
    st.header("Encounter Overview")

    patients = db_utils.get_patients(conn)
    if patients.empty:
        st.info("No patients found in the database.")
        return

    patient_options = {row["display_name"]: int(row["id"]) for _, row in patients.iterrows()}
    state = st.session_state

    labels = list(patient_options.keys())
    default_index = 0
    if state["selected_patient_label"] in patient_options:
        default_index = labels.index(state["selected_patient_label"])

    _sidebar_divider()
    st.sidebar.header("Encounter Filters")
    selected_label = st.sidebar.selectbox("Patient", options=labels, index=default_index)
    patient_id = patient_options[selected_label]

    if state["selected_patient_id"] != patient_id:
        state["selected_patient_id"] = patient_id
        state["selected_patient_label"] = selected_label
        state["selected_encounter_id"] = None

    patient_row = patients[patients["id"] == patient_id].iloc[0]
    subtitle_parts = [f"Patient: {selected_label}"]
    birth_date = patient_row.get("birth_date")
    if birth_date:
        subtitle_parts.append(f"DOB: {birth_date}")
    st.caption(" | ".join(subtitle_parts))

    encounters = db_utils.get_patient_encounters(conn, patient_id)
    if encounters.empty:
        st.info("No encounters recorded for this patient.")
        return

    st.write(f"{len(encounters)} encounter{'s' if len(encounters) != 1 else ''} found.")

    for _, row in encounters.iterrows():
        encounter_id = int(row["encounter_id"])
        encounter_date = _format_datetime(row.get("encounter_date"))
        encounter_type = (row.get("encounter_type") or "Encounter").strip() or "Encounter"
        provider = row.get("provider_display_name") or "Unknown provider"
        notes = (row.get("notes") or "").strip()

        with st.container():
            st.markdown(f"### {encounter_date}")
            st.caption(f"{encounter_type} • {provider}")
            if notes:
                st.markdown(notes)
            if st.button("View details", key=f"encounter-detail-{encounter_id}"):
                state["selected_encounter_id"] = encounter_id
                state["app_view"] = "detail"
                _rerun()


def _format_records_for_list(records: Iterable[dict[str, Any]], fields: list[str]) -> list[str]:
    lines: list[str] = []
    for record in records:
        parts = [record.get(field) for field in fields if record.get(field)]
        text = " - ".join(str(part).strip() for part in parts if str(part).strip())
        if text:
            lines.append(f"- {text}")
    return lines


def _show_section(
    title: str,
    records: list[dict[str, Any]],
    *,
    dataframe: bool = False,
    fields: Optional[list[str]] = None,
) -> None:
    st.subheader(title)
    if not records:
        st.info("None recorded.")
        return
    if dataframe:
        st.dataframe(pd.DataFrame(records), use_container_width=True)
    else:
        display_fields = fields or ["name"]
        for line in _format_records_for_list(records, display_fields):
            st.markdown(line)


def _show_progress_notes(notes: list[dict[str, Any]]) -> None:
    st.subheader("Progress Notes")
    if not notes:
        st.info("No progress notes recorded.")
        return

    for idx, note in enumerate(notes):
        title = note.get("note_title") or f"Progress Note #{idx + 1}"
        timestamp = _format_datetime(note.get("note_datetime"), show_time=True)
        with st.expander(f"{title} • {timestamp}"):
            st.markdown(note.get("note_text") or "No text provided.")
            source_id = note.get("source_note_id")
            if source_id:
                st.caption(f"Source ID: {source_id}")


def _show_encounter_detail(conn) -> None:
    state = st.session_state
    encounter_id = state.get("selected_encounter_id")
    if encounter_id is None:
        st.warning("No encounter selected.")
        if st.button("Back to encounters"):
            state["app_view"] = "overview"
            _rerun()
        return

    detail = db_utils.get_encounter_detail(conn, encounter_id)
    metadata = detail["metadata"]

    st.header("Encounter Detail")
    if st.button("Back to encounters"):
        state["app_view"] = "overview"
        state["selected_encounter_id"] = None
        _rerun()

    patient_label = state.get("selected_patient_label") or f"#{detail['patient_id']}"
    st.markdown(f"**Patient:** {patient_label}")

    with st.container():
        st.subheader("Encounter Metadata")
        cols = st.columns(2)
        with cols[0]:
            st.markdown(f"**Date:** {_format_datetime(metadata.get('encounter_date'), show_time=True)}")
            st.markdown(f"**Type:** {metadata.get('encounter_type') or 'Unknown'}")
            st.markdown(f"**Provider:** {metadata.get('provider_display_name')}")
        with cols[1]:
            ds = metadata.get("data_source") or {}
            st.markdown(f"**Source Archive:** {ds.get('source_archive') or '-'}")
            st.markdown(f"**Document:** {ds.get('original_filename') or '-'}")
            if ds.get("document_created"):
                st.markdown(
                    f"**Document Created:** {_format_datetime(ds.get('document_created'), show_time=True)}"
                )
            if ds.get("repository_unique_id"):
                st.markdown(f"**Repository ID:** {ds.get('repository_unique_id')}")
            if ds.get("document_hash"):
                st.markdown(f"**Document Hash:** `{ds.get('document_hash')}`")
            if ds.get("document_size"):
                st.markdown(f"**Document Size:** {ds.get('document_size')} bytes")
            if ds.get("author_institution"):
                st.markdown(f"**Author Institution:** {ds.get('author_institution')}")

        notes = metadata.get("notes")
        if notes:
            st.markdown("**Encounter Notes**")
            st.markdown(notes)

        attachment = metadata.get("attachment") or {}
        if attachment.get("file_path"):
            attachment_path = attachment["file_path"]
            attachment_label = Path(attachment_path).name
            mime = attachment.get("mime_type")
            attachment_text = f"`{attachment_label}`"
            if mime:
                attachment_text += f" ({mime})"
            st.markdown(f"**Attachment:** {attachment_text}")

    _show_section(
        "Conditions",
        detail["conditions"],
        fields=["name", "code_display", "status"],
    )
    _show_section(
        "Medications",
        detail["medications"],
        fields=["name", "dose", "route", "frequency", "status"],
    )
    _show_section(
        "Procedures",
        detail["procedures"],
        fields=["name", "code_display", "status", "date"],
    )
    _show_section("Lab Results", detail["lab_results"], dataframe=True)
    _show_section("Vitals", detail["vitals"], dataframe=True)
    _show_section(
        "Immunizations (up to encounter date)",
        detail["immunizations"],
        dataframe=True,
    )
    _show_progress_notes(detail["progress_notes"])


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
