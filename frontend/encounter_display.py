"""Encounter display components for Streamlit UI.

This module provides reusable components for rendering encounter information
in the patient overview and detail views, reducing complexity in the main views.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

import pandas as pd
import streamlit as st


def format_datetime(raw_value: Any, *, show_time: bool = False) -> str:
    """Format a timestamp string to a human-readable date (and optional time).

    Args:
        raw_value: The raw timestamp value (string or None).
        show_time: Whether to include time in the output.

    Returns:
        Formatted date string or "Unknown" if parsing fails.
    """
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


def render_encounter_card(
    row: pd.Series,
    encounter_id: int,
    on_detail_click: Callable[[int], None],
) -> None:
    """Render a single encounter card in the overview listing.

    Args:
        row: Pandas Series containing encounter data.
        encounter_id: Unique encounter identifier.
        on_detail_click: Callback function when "View details" button is clicked.
    """
    encounter_date = format_datetime(row.get("encounter_date"))
    encounter_type = (row.get("encounter_type") or "Encounter").strip() or "Encounter"
    provider = row.get("provider_display_name") or "Unknown provider"
    notes = (row.get("notes") or "").strip()

    with st.container():
        st.markdown(f"### {encounter_date}")
        st.caption(f"{encounter_type} | {provider}")
        if notes:
            st.markdown(notes)
        if st.button("View details", key=f"encounter-detail-{encounter_id}"):
            on_detail_click(encounter_id)


def build_patient_subtitle(
    patient_row: pd.Series, selected_label: Optional[str]
) -> str:
    """Build patient subtitle with name and date of birth.

    Args:
        patient_row: Pandas Series containing patient data.
        selected_label: Optional selected patient label from state.

    Returns:
        Formatted subtitle string.
    """
    patient_label = selected_label or patient_row.get("display_name")
    subtitle_parts = [f"Patient: {patient_label}"]

    birth_date = patient_row.get("birth_date")
    if birth_date:
        subtitle_parts.append(f"DOB: {birth_date}")

    return " | ".join(subtitle_parts)


def render_encounter_metadata_columns(metadata: dict[str, Any]) -> None:
    """Render encounter metadata in a two-column layout.

    Args:
        metadata: Dictionary containing encounter metadata and data source info.
    """
    cols = st.columns(2)

    with cols[0]:
        st.markdown(
            f"**Date:** {format_datetime(
                metadata.get('encounter_date'), show_time=True
            )}"
        )
        st.markdown(f"**Type:** {metadata.get('encounter_type') or 'Unknown'}")
        st.markdown(f"**Provider:** {metadata.get('provider_display_name')}")

    with cols[1]:
        ds = metadata.get("data_source") or {}
        st.markdown(f"**Source Archive:** {ds.get('source_archive') or '-'}")
        st.markdown(f"**Document:** {ds.get('original_filename') or '-'}")

        if ds.get("document_created"):
            st.markdown(
                f"**Document Created:** {format_datetime(
                    ds.get('document_created'), show_time=True
                )}"
            )
        if ds.get("repository_unique_id"):
            st.markdown(f"**Repository ID:** {ds.get('repository_unique_id')}")
        if ds.get("document_hash"):
            st.markdown(f"**Document Hash:** `{ds.get('document_hash')}`")
        if ds.get("document_size"):
            st.markdown(f"**Document Size:** {ds.get('document_size')} bytes")
        if ds.get("author_institution"):
            st.markdown(f"**Author Institution:** {ds.get('author_institution')}")
