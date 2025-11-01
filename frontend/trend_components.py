from __future__ import annotations

# Purpose: Streamlit helpers for rendering patient vital and lab trends.
# Author: Codex + Lauren
# Date: 2025-10-21
# Tests: Manual Streamlit verification pending.
# AI-assisted: This module was created with AI assistance.

import re
import sqlite3
from typing import Any, Optional, Tuple

import altair as alt
import pandas as pd
import streamlit as st

from health_records_collection.frontend import db_utils


def _parse_reference_range(raw_value: Any) -> Tuple[Optional[float], Optional[float]]:
    """Parse simple low/high ranges from text values."""
    if raw_value is None:
        return (None, None)
    text = str(raw_value).strip()
    if not text:
        return (None, None)
    matches = re.findall(r"-?\d+(?:\.\d+)?", text)
    numbers: list[float] = []
    for match in matches[:2]:
        try:
            numbers.append(float(match))
        except ValueError:
            continue
    if len(numbers) == 2 and numbers[0] > numbers[1]:
        numbers = [numbers[1], numbers[0]]
    lows = numbers[0] if numbers else None
    highs = numbers[1] if len(numbers) > 1 else None
    return (lows, highs)


def render_patient_trends(
    conn: sqlite3.Connection,
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
            label = f"Vital | {vital_name}"
            options.append((label, {"dataset": "vital", "name": vital_name}))
        if vitals_df["_type_clean"].isna().any():
            options.append(
                (
                    "Vital | Unspecified type",
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
            label = f"Lab | {primary}"
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

    show_reference_band = False
    reference_band_df: Optional[pd.DataFrame] = None

    if selected_meta["dataset"] == "vital":
        series_df = vitals_df.copy()
        if selected_meta.get("name"):
            mask = series_df["_type_clean"] == selected_meta["name"]
        else:
            mask = series_df["_type_clean"].isna()
        if mask.sum() == 0 and selected_meta.get("name"):
            mask = series_df["vital_type"] == selected_meta["name"]
        display_name = selected_meta.get("name") or "Unspecified vital"
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
        mask &= series_df["_loinc_clean"] == selected_meta["loinc_code"]
        if mask.sum() == 0:
            mask &= series_df["_loinc_clean"].isna()
        display_name = selected_meta["loinc_code"]
        if selected_meta.get("test_name"):
            display_name += f" ({selected_meta['test_name']})"
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
        parsed_ranges = series_df["reference_range"].apply(_parse_reference_range)
        series_df["reference_low"] = parsed_ranges.map(lambda bounds: bounds[0])
        series_df["reference_high"] = parsed_ranges.map(lambda bounds: bounds[1])
        reference_mask = (
            series_df["reference_low"].notna() & series_df["reference_high"].notna()
        )
        if reference_mask.any():
            toggle_key = f"trend-reference-band-{abs(hash(selected_label))}"
            show_reference_band = st.checkbox(
                "Show reference range band",
                value=True,
                key=toggle_key,
            )
            if show_reference_band:
                reference_band_df = series_df.loc[
                    reference_mask,
                    ["measurement_time", "reference_low", "reference_high"],
                ].dropna()
                if reference_band_df is not None:
                    reference_band_df = reference_band_df.copy()

    st.caption(f"Selected series: {display_name}")

    units = sorted(
        {str(unit).strip() for unit in series_df["unit"].dropna() if str(unit).strip()}
    )
    if len(units) > 1:
        st.warning(
            "Multiple units detected for this series; values may not be comparable."
        )
    elif not units:
        st.info("No unit information recorded for this series.")

    non_numeric = series_df[
        series_df["value_numeric"].isna() & series_df["value_text"].notna()
    ]
    if not non_numeric.empty:
        st.warning("Some results are non-numeric and are excluded from the chart.")

    chart_df = series_df.dropna(subset=["measurement_time", "value_numeric"])
    if len(chart_df) >= 2:
        y_title = "Value"
        if len(units) == 1:
            y_title = f"Value ({units[0]})"
        x_encoding = alt.X("measurement_time:T", title="Measurement Date")
        y_encoding = alt.Y("value_numeric:Q", title=y_title)
        line_chart = (
            alt.Chart(chart_df)
            .mark_line(point=True)
            .encode(
                x=x_encoding,
                y=y_encoding,
                tooltip=tooltip_fields,
            )
        )
        if (
            show_reference_band
            and reference_band_df is not None
            and not reference_band_df.empty
        ):
            band_chart = (
                alt.Chart(reference_band_df)
                .mark_area(opacity=0.50, color="#D386FF")
                .encode(
                    x=x_encoding,
                    y=alt.Y("reference_low:Q"),
                    y2="reference_high:Q",
                )
            )
            chart = alt.layer(band_chart, line_chart).resolve_scale(y="shared")
        else:
            chart = line_chart
        chart = chart.interactive()
        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Not enough numeric data points with valid dates to render a " "chart.")

    st.dataframe(series_df[table_columns], use_container_width=True)
