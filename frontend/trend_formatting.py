"""Formatting and parsing utilities for trend data.

Purpose: Handle reference range parsing, display formatting, tooltip/table config.
Author: Lauren Parlett
Date: 2025-11-01
Tests: Manual Streamlit validation pending.
AI-assisted: Module generated with AI assistance.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import altair as alt
import pandas as pd


def parse_reference_range(raw_value: Any) -> tuple[Optional[float], Optional[float]]:
    """Parse simple low/high ranges from text values.

    Args:
        raw_value: Raw reference range text.

    Returns:
        Tuple of (low, high) floats or (None, None).
    """
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


def add_reference_bounds_to_labs(labs_df: pd.DataFrame) -> pd.DataFrame:
    """Parse reference ranges and add low/high columns to labs data.

    Args:
        labs_df: Labs dataframe.

    Returns:
        DataFrame with reference_low and reference_high columns added.
    """
    df = labs_df.copy()
    parsed_ranges = df["reference_range"].apply(parse_reference_range)
    df["reference_low"] = parsed_ranges.map(lambda bounds: bounds[0])
    df["reference_high"] = parsed_ranges.map(lambda bounds: bounds[1])
    return df


def get_reference_band_data(labs_df: pd.DataFrame) -> Optional[pd.DataFrame]:
    """Extract rows with complete reference range bounds.

    Args:
        labs_df: Labs dataframe with reference_low and reference_high columns.

    Returns:
        Filtered dataframe or None if no valid ranges.
    """
    reference_mask = (
        labs_df["reference_low"].notna() & labs_df["reference_high"].notna()
    )
    if reference_mask.any():
        result = labs_df.loc[
            reference_mask,
            ["measurement_time", "reference_low", "reference_high"],
        ].dropna()
        return result.copy() if not result.empty else None
    return None


def get_vital_tooltips() -> list[alt.Tooltip]:
    """Get Altair tooltip configuration for vital charts.

    Returns:
        List of Tooltip objects.
    """
    return [
        alt.Tooltip("measurement_time:T", title="Timestamp"),
        alt.Tooltip("value_numeric:Q", title="Value"),
        alt.Tooltip("unit:N", title="Unit"),
        alt.Tooltip("value_text:N", title="Original Value"),
        alt.Tooltip("encounter_id:N", title="Encounter"),
    ]


def get_lab_tooltips() -> list[alt.Tooltip]:
    """Get Altair tooltip configuration for lab charts.

    Returns:
        List of Tooltip objects.
    """
    return [
        alt.Tooltip("measurement_time:T", title="Timestamp"),
        alt.Tooltip("value_numeric:Q", title="Value"),
        alt.Tooltip("unit:N", title="Unit"),
        alt.Tooltip("value_text:N", title="Original Value"),
        alt.Tooltip("abnormal_flag:N", title="Abnormal"),
        alt.Tooltip("reference_range:N", title="Reference Range"),
        alt.Tooltip("encounter_id:N", title="Encounter"),
    ]


def get_vital_table_columns() -> list[str]:
    """Get table columns to display for vital series.

    Returns:
        List of column names.
    """
    return ["date", "value_text", "unit", "encounter_id"]


def get_lab_table_columns() -> list[str]:
    """Get table columns to display for lab series.

    Returns:
        List of column names.
    """
    return [
        "date",
        "value_text",
        "unit",
        "abnormal_flag",
        "reference_range",
        "encounter_id",
    ]


def format_display_name_vital(vital_name: Optional[str]) -> str:
    """Format display name for vital type.

    Args:
        vital_name: Vital type or None.

    Returns:
        Formatted string.
    """
    return vital_name or "Unspecified vital"


def format_display_name_lab(
    loinc_code: Optional[str], test_name: Optional[str] = None
) -> str:
    """Format display name for lab test.

    Args:
        loinc_code: LOINC code.
        test_name: Optional test name.

    Returns:
        Formatted string.
    """
    display = loinc_code or "Unspecified lab"
    if test_name:
        display += f" ({test_name})"
    return display
