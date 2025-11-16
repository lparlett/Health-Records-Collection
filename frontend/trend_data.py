"""Data fetching and cleaning for patient trends.

Purpose: Handle retrieval and initial processing of vitals and lab data.
Author: Lauren Parlett
Date: 2025-11-01
Tests: Manual Streamlit validation pending.
AI-assisted: Module generated with AI assistance.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

import pandas as pd

from health_records_collection.frontend import db_utils


def get_patient_trends_data(
    conn: sqlite3.Connection, patient_id: int
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch patient vitals and lab timeseries data.

    Args:
        conn: Database connection.
        patient_id: Patient ID.

    Returns:
        Tuple of (vitals_df, labs_df).
    """
    vitals_df = db_utils.get_patient_vitals_timeseries(conn, patient_id)
    labs_df = db_utils.get_patient_lab_timeseries(conn, patient_id)
    return vitals_df, labs_df


def clean_label(value: Any) -> Optional[str]:
    """Convert value to clean string label.

    Args:
        value: Raw value from dataframe.

    Returns:
        Cleaned string or None if empty/null.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def add_vitals_clean_columns(vitals_df: pd.DataFrame) -> pd.DataFrame:
    """Add cleaned column labels to vitals dataframe.

    Args:
        vitals_df: Vitals dataframe.

    Returns:
        DataFrame with _type_clean column added.
    """
    df = vitals_df.copy()
    df["_type_clean"] = df["vital_type"].apply(clean_label)
    return df


def add_labs_clean_columns(labs_df: pd.DataFrame) -> pd.DataFrame:
    """Add cleaned column labels to labs dataframe.

    Args:
        labs_df: Labs dataframe.

    Returns:
        DataFrame with _name_clean and _loinc_clean columns added.
    """
    df = labs_df.copy()
    df["_name_clean"] = df["test_name"].apply(clean_label)
    df["_loinc_clean"] = df["loinc_code"].apply(clean_label)
    return df


def filter_vitals_by_type(
    vitals_df: pd.DataFrame, vital_type: Optional[str]
) -> pd.DataFrame:
    """Filter vitals to specific type.

    Args:
        vitals_df: Vitals dataframe with _type_clean column.
        vital_type: Type name or None for unspecified.

    Returns:
        Filtered dataframe.
    """
    if vital_type is None:
        mask = vitals_df["_type_clean"].isna()
    else:
        mask = vitals_df["_type_clean"] == vital_type

    result = vitals_df.loc[mask].copy()

    # Fallback: if no results and type specified, try raw column
    if result.empty and vital_type is not None:
        mask = vitals_df["vital_type"] == vital_type
        result = vitals_df.loc[mask].copy()

    return result


def filter_labs_by_loinc(
    labs_df: pd.DataFrame, loinc_code: Optional[str]
) -> pd.DataFrame:
    """Filter labs to specific LOINC code.

    Args:
        labs_df: Labs dataframe with _loinc_clean and _name_clean columns.
        loinc_code: LOINC code to filter by.

    Returns:
        Filtered dataframe.
    """
    df = labs_df.copy()
    mask = pd.Series(True, index=df.index)
    mask &= df["_loinc_clean"] == loinc_code

    # Fallback: if no results, try unspecified
    if mask.sum() == 0:
        mask = df["_loinc_clean"].isna()

    return df.loc[mask].copy()


def get_unique_units(series_df: pd.DataFrame) -> list[str]:
    """Extract unique units from series.

    Args:
        series_df: Series dataframe.

    Returns:
        Sorted list of unique unit strings.
    """
    return sorted(
        {str(unit).strip() for unit in series_df["unit"].dropna() if str(unit).strip()}
    )


def get_numeric_chart_data(series_df: pd.DataFrame) -> pd.DataFrame:
    """Extract only numeric data points with valid timestamps for charting.

    Args:
        series_df: Series dataframe.

    Returns:
        Filtered dataframe with measurement_time and value_numeric.
    """
    return series_df.dropna(subset=["measurement_time", "value_numeric"])


def get_non_numeric_count(series_df: pd.DataFrame) -> int:
    """Count non-numeric values that won't be charted.

    Args:
        series_df: Series dataframe.

    Returns:
        Count of non-numeric values.
    """
    non_numeric = series_df[
        series_df["value_numeric"].isna() & series_df["value_text"].notna()
    ]
    return len(non_numeric)
