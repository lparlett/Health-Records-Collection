from __future__ import annotations

# Purpose: Streamlit helpers for rendering patient vital and lab trends.
# Author: Codex + Lauren
# Date: 2025-10-21
# Tests: Manual Streamlit verification pending.
# AI-assisted: This module was created with AI assistance.

import sqlite3

import streamlit as st

from health_records_collection.frontend import (
    trend_chart,
    trend_data,
    trend_formatting,
    trend_options,
)


def render_patient_trends(
    conn: sqlite3.Connection,
    patient_id: int,
    *,
    show_section_header: bool = True,
) -> None:
    """Render patient-level lab and vital trends.

    Orchestrates complete workflow:
    1. Fetch vitals and labs data
    2. Present measurement selection
    3. Render trend chart
    4. Display data table
    """
    if show_section_header:
        st.subheader("Patient Trends")

    # Step 1: Fetch data
    vitals_df, labs_df = trend_data.get_patient_trends_data(conn, patient_id)

    if vitals_df.empty and labs_df.empty:
        st.info("No vitals or lab results recorded for this patient.")
        return

    # Step 2: Clean labels
    vitals_df = trend_data.add_vitals_clean_columns(vitals_df)
    labs_df = trend_data.add_labs_clean_columns(labs_df)

    # Step 3: Build options
    options = trend_options.build_all_options(vitals_df, labs_df)

    if not options:
        st.info("No trendable data found for this patient.")
        return

    # Step 4: Get user selection
    labels = trend_options.extract_labels(options)
    selected_label = st.selectbox(
        "Measurement",
        labels,
        key="trend-measurement",
    )
    selected_meta = trend_options.get_metadata_for_label(options, selected_label)

    # Step 5: Filter series
    series_df, display_name, tooltip_fields, table_columns, reference_band_df = (
        _prepare_series(
            selected_meta,
            vitals_df,
            labs_df,
            selected_label,
        )
    )

    # Step 6: Render display
    st.caption(f"Selected series: {display_name}")
    _display_series_warnings(series_df)
    _render_series_chart(
        series_df,
        tooltip_fields,
        reference_band_df=reference_band_df,
    )
    st.dataframe(series_df[table_columns], use_container_width=True)


def _prepare_series(
    selected_meta: dict,
    vitals_df,
    labs_df,
    selected_label: str,
):
    """Prepare series dataframe based on selection.

    Args:
        selected_meta: Metadata for selected measurement.
        vitals_df: Vitals dataframe.
        labs_df: Labs dataframe.
        selected_label: Selected label for reference band key.

    Returns:
        Tuple of (series_df, display_name, tooltip_fields, table_columns,
        reference_band_df).
    """
    reference_band_df = None

    if selected_meta["dataset"] == "vital":
        series_df = trend_data.filter_vitals_by_type(
            vitals_df, selected_meta.get("name")
        )
        display_name = trend_formatting.format_display_name_vital(
            selected_meta.get("name")
        )
        tooltip_fields = trend_formatting.get_vital_tooltips()
        table_columns = trend_formatting.get_vital_table_columns()
    else:
        series_df = trend_data.filter_labs_by_loinc(
            labs_df, selected_meta.get("loinc_code")
        )
        display_name = trend_formatting.format_display_name_lab(
            selected_meta.get("loinc_code"), selected_meta.get("test_name")
        )
        tooltip_fields = trend_formatting.get_lab_tooltips()
        table_columns = trend_formatting.get_lab_table_columns()

        # Add reference bounds for labs
        series_df = trend_formatting.add_reference_bounds_to_labs(series_df)

        # Handle reference band display
        band_data = trend_formatting.get_reference_band_data(series_df)
        if band_data is not None:
            toggle_key = f"trend-reference-band-{abs(hash(selected_label))}"
            show_band = st.checkbox(
                "Show reference range band",
                value=True,
                key=toggle_key,
            )
            if show_band:
                reference_band_df = band_data

    return series_df, display_name, tooltip_fields, table_columns, reference_band_df


def _display_series_warnings(series_df) -> None:
    """Display warnings about series data quality.

    Args:
        series_df: Series dataframe.
    """
    units = trend_data.get_unique_units(series_df)
    if len(units) > 1:
        st.warning(
            "Multiple units detected for this series; values may not be comparable."
        )
    elif not units:
        st.info("No unit information recorded for this series.")

    non_numeric_count = trend_data.get_non_numeric_count(series_df)
    if non_numeric_count > 0:
        st.warning("Some results are non-numeric and are excluded from the chart.")


def _render_series_chart(
    series_df,
    tooltip_fields,
    *,
    reference_band_df=None,
) -> None:
    """Render trend chart if sufficient data exists.

    Args:
        series_df: Series dataframe.
        display_name: Display name for chart title.
        tooltip_fields: Tooltip configuration.
        table_columns: Columns to display in table.
        reference_band_df: Optional reference band dataframe.
    """
    chart_df = trend_data.get_numeric_chart_data(series_df)

    if len(chart_df) < 2:
        st.info("Not enough numeric data points with valid dates to render a chart.")
        return

    # Build Y-axis title with units
    units = trend_data.get_unique_units(series_df)
    y_title = "Value"
    if len(units) == 1:
        y_title = f"Value ({units[0]})"

    # Build line chart
    line_chart = trend_chart.build_line_chart(chart_df, tooltip_fields, y_title=y_title)

    # Combine and render
    final_chart = trend_chart.build_combined_chart(line_chart, reference_band_df)
    final_chart = trend_chart.finalize_chart(final_chart)
    st.altair_chart(final_chart, use_container_width=True)
