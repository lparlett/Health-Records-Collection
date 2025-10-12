from __future__ import annotations

# Purpose: Streamlit views for patient encounter overview, detail, and trends.
# Author: Codex + Lauren
# Date: 2025-10-12
# Tests: Manual Streamlit verification; frontend pytest coverage pending.
# AI-assisted: Portions of this module were updated with AI assistance.

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import altair as alt
import pandas as pd
import streamlit as st

import db_utils
import ui_components


def _ensure_state() -> None:
    state = st.session_state
    state.setdefault("app_view", "overview")
    state.setdefault("nav_view", "overview")
    state.setdefault("detail_return_view", "overview")
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
    nav_view = _navigation_controls()
    if state["app_view"] == "detail" and nav_view != state.get("detail_return_view"):
        state["selected_encounter_id"] = None
        state["app_view"] = nav_view
    elif state["app_view"] != "detail":
        state["app_view"] = nav_view

    if state["app_view"] == "detail":
        _show_encounter_detail(conn)
        return False
    if state["app_view"] == "trends":
        _show_patient_trends_page(conn)
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


def _navigation_controls() -> str:
    state = st.session_state
    _sidebar_divider()
    st.sidebar.header("Navigation")
    options = [
        ("Encounter overview", "overview"),
        ("Patient trends", "trends"),
    ]
    labels = [label for label, _ in options]
    nav_view = state.get("nav_view", "overview")
    default_index = next(
        (idx for idx, (_, value) in enumerate(options) if value == nav_view),
        0,
    )
    selected_label = st.sidebar.radio(
        "View",
        labels,
        index=default_index,
        key="navigation-view",
    )
    selected_view = dict(options)[selected_label]
    if selected_view != state.get("nav_view"):
        state["nav_view"] = selected_view
    return state["nav_view"]


def _select_patient(
    patients: pd.DataFrame,
    *,
    sidebar_header: str,
) -> tuple[Optional[int], Optional[pd.Series]]:
    if patients.empty:
        return None, None

    patient_options = {
        str(row["display_name"]): int(row["id"]) for _, row in patients.iterrows()
    }
    labels = list(patient_options.keys())

    state = st.session_state
    default_index = 0
    if state.get("selected_patient_label") in patient_options:
        default_index = labels.index(state["selected_patient_label"])

    _sidebar_divider()
    st.sidebar.header(sidebar_header)
    selected_label = st.sidebar.selectbox(
        "Patient",
        options=labels,
        index=default_index,
        key="patient-selector",
    )
    patient_id = patient_options[selected_label]
    if state.get("selected_patient_id") != patient_id:
        state["selected_encounter_id"] = None
    state["selected_patient_id"] = patient_id
    state["selected_patient_label"] = selected_label

    patient_row = patients[patients["id"] == patient_id].iloc[0]
    return patient_id, patient_row


def _show_encounter_overview(conn) -> None:
    st.header("Encounter Overview")

    patients = db_utils.get_patients(conn)
    if patients.empty:
        st.info("No patients found in the database.")
        return

    patient_id, patient_row = _select_patient(patients, sidebar_header="Encounter Filters")
    if patient_id is None or patient_row is None:
        st.info("No patients found in the database.")
        return

    state = st.session_state
    patient_label = state.get("selected_patient_label") or patient_row.get("display_name")
    subtitle_parts = [f"Patient: {patient_label}"]
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
                state["detail_return_view"] = state.get("nav_view", "overview")
                state["app_view"] = "detail"
                _rerun()


def _show_patient_trends_page(conn) -> None:
    st.header("Patient Trends")

    patients = db_utils.get_patients(conn)
    if patients.empty:
        st.info("No patients found in the database.")
        return

    patient_id, patient_row = _select_patient(patients, sidebar_header="Trend Filters")
    if patient_id is None or patient_row is None:
        st.info("No patients found in the database.")
        return

    state = st.session_state
    patient_label = state.get("selected_patient_label") or patient_row.get("display_name")
    subtitle_parts = [f"Patient: {patient_label}"]
    birth_date = patient_row.get("birth_date")
    if birth_date:
        subtitle_parts.append(f"DOB: {birth_date}")
    st.caption(" | ".join(subtitle_parts))

    _render_patient_trends(conn, patient_id, show_section_header=False)


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


def _render_patient_trends(
    conn,
    patient_id: int,
    *,
    show_section_header: bool = True,
) -> None:
    """Render patient-level lab and vital trends."""

    if show_section_header:
        st.subheader("Patient Trends")
    vitals_df = db_utils.get_patient_vitals_timeseries(conn, patient_id)
    labs_df = db_utils.get_patient_lab_timeseries(conn, patient_id)

    if vitals_df.empty and labs_df.empty:
        st.info("No vitals or lab results recorded for this patient.")
        return

    def _clean_label(value: Any) -> Optional[str]:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if pd.isna(value):
            return None
        text = str(value).strip()
        return text or None

    options: list[tuple[str, dict[str, Any]]] = []

    if not vitals_df.empty:
        vitals_df = vitals_df.copy()
        vitals_df["_type_clean"] = vitals_df["vital_type"].apply(_clean_label)
        for vital_name in sorted(
            {name for name in vitals_df["_type_clean"].dropna().unique()}
        ):
            label = f"Vital • {vital_name}"
            options.append((label, {"dataset": "vital", "name": vital_name}))
        if vitals_df["_type_clean"].isna().any():
            options.append(
                (
                    "Vital • Unspecified type",
                    {"dataset": "vital", "name": None},
                )
            )

    if not labs_df.empty:
        labs_df = labs_df.copy()
        labs_df["_name_clean"] = labs_df["test_name"].apply(_clean_label)
        labs_df["_loinc_clean"] = labs_df["loinc_code"].apply(_clean_label)
        lab_keys = (
            labs_df[["_name_clean", "_loinc_clean"]]
            .drop_duplicates()
            .sort_values(["_name_clean", "_loinc_clean"])
        )
        for _, row in lab_keys.iterrows():
            test_clean = row["_name_clean"]
            loinc_clean = row["_loinc_clean"]
            primary = test_clean or loinc_clean or "Unspecified lab"
            label = f"Lab • {primary}"
            if test_clean and loinc_clean:
                label += f" ({loinc_clean})"
            options.append(
                (
                    label,
                    {
                        "dataset": "lab",
                        "test_name": test_clean,
                        "loinc_code": loinc_clean,
                    },
                )
            )

    if not options:
        st.info("No trendable data found for this patient.")
        return

    options.sort(key=lambda item: item[0])
    labels = [label for label, _ in options]
    selected_label = st.selectbox(
        "Measurement",
        labels,
        key="trend-measurement",
    )
    selected_meta = next(meta for label, meta in options if label == selected_label)

    if selected_meta["dataset"] == "vital":
        series_df = vitals_df.copy()
        if selected_meta["name"] is None:
            mask = series_df["_type_clean"].isna()
            display_name = "Unspecified vital"
        else:
            mask = series_df["_type_clean"] == selected_meta["name"]
            display_name = selected_meta["name"]
        series_df = series_df.loc[mask].copy()
        tooltip_fields = [
            alt.Tooltip("measurement_time:T", title="Timestamp"),
            alt.Tooltip("value_numeric:Q", title="Value"),
            alt.Tooltip("unit:N", title="Unit"),
            alt.Tooltip("value_text:N", title="Original Value"),
            alt.Tooltip("encounter_id:N", title="Encounter"),
        ]
        table_columns = ["date", "value_text", "unit", "encounter_id"]
    else:
        series_df = labs_df.copy()
        mask = pd.Series(True, index=series_df.index)
        if selected_meta["test_name"] is None:
            mask &= series_df["_name_clean"].isna()
            display_name = selected_meta["loinc_code"] or "Unspecified lab"
        else:
            mask &= series_df["_name_clean"] == selected_meta["test_name"]
            display_name = selected_meta["test_name"]
        if selected_meta["loinc_code"] is None:
            mask &= series_df["_loinc_clean"].isna()
        else:
            mask &= series_df["_loinc_clean"] == selected_meta["loinc_code"]
            if selected_meta["test_name"]:
                display_name += f" ({selected_meta['loinc_code']})"
        series_df = series_df.loc[mask].copy()
        tooltip_fields = [
            alt.Tooltip("measurement_time:T", title="Timestamp"),
            alt.Tooltip("value_numeric:Q", title="Value"),
            alt.Tooltip("unit:N", title="Unit"),
            alt.Tooltip("value_text:N", title="Original Value"),
            alt.Tooltip("abnormal_flag:N", title="Abnormal"),
            alt.Tooltip("reference_range:N", title="Reference Range"),
            alt.Tooltip("encounter_id:N", title="Encounter"),
        ]
        table_columns = [
            "date",
            "value_text",
            "unit",
            "abnormal_flag",
            "reference_range",
            "encounter_id",
        ]

    st.caption(f"Selected series: {display_name}")

    units = sorted(
        {
            str(unit).strip()
            for unit in series_df["unit"].dropna()
            if str(unit).strip()
        }
    )
    if len(units) > 1:
        st.warning(
            "Multiple units detected for this series; values may not be "
            "comparable."
        )
    elif not units:
        st.info("No unit information recorded for this series.")

    non_numeric = series_df[
        series_df["value_numeric"].isna() & series_df["value_text"].notna()
    ]
    if not non_numeric.empty:
        st.warning(
            "Some results are non-numeric and are excluded from the chart."
        )

    chart_df = series_df.dropna(subset=["measurement_time", "value_numeric"])
    if len(chart_df) >= 2:
        y_title = "Value"
        if len(units) == 1:
            y_title = f"Value ({units[0]})"
        chart = (
            alt.Chart(chart_df)
            .mark_line(point=True)
            .encode(
                x=alt.X("measurement_time:T", title="Date"),
                y=alt.Y("value_numeric:Q", title=y_title),
                tooltip=tooltip_fields,
            )
            .interactive()
        )
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info(
            "Not enough numeric data points with valid dates to render a "
            "chart."
        )

    st.dataframe(series_df[table_columns], use_container_width=True)


def _show_encounter_detail(conn) -> None:
    state = st.session_state
    encounter_id = state.get("selected_encounter_id")
    if encounter_id is None:
        st.warning("No encounter selected.")
        if st.button("Back to encounters"):
            target_view = state.get("detail_return_view", "overview")
            state["selected_encounter_id"] = None
            state["app_view"] = target_view
            state["nav_view"] = target_view
            _rerun()
        return

    detail = db_utils.get_encounter_detail(conn, encounter_id)
    metadata = detail["metadata"]

    st.header("Encounter Detail")
    if st.button("Back to encounters"):
        target_view = state.get("detail_return_view", "overview")
        state["selected_encounter_id"] = None
        state["app_view"] = target_view
        state["nav_view"] = target_view
        _rerun()

    patient_label = state.get("selected_patient_label") or f"#{detail['patient_id']}"
    st.markdown(f"**Patient:** {patient_label}")

    summary_tab, trends_tab = st.tabs(["Encounter summary", "Patient trends"])

    with summary_tab:
        with st.container():
            st.subheader("Encounter Metadata")
            cols = st.columns(2)
            with cols[0]:
                st.markdown(
                    f"**Date:** {_format_datetime(metadata.get('encounter_date'), show_time=True)}"
                )
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
                    st.markdown(
                        f"**Document Size:** {ds.get('document_size')} bytes"
                    )
                if ds.get("author_institution"):
                    st.markdown(
                        f"**Author Institution:** {ds.get('author_institution')}"
                    )

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

    with trends_tab:
        _render_patient_trends(conn, detail["patient_id"])


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
