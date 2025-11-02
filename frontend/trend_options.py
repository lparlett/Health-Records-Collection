"""Build trend measurement options for user selection.

Purpose: Generate and organize dropdown options for vitals and lab trends.
Author: Lauren Parlett
Date: 2025-11-01
Tests: Manual Streamlit validation pending.
AI-assisted: Module generated with AI assistance.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def build_vital_options(vitals_df: pd.DataFrame) -> list[tuple[str, dict[str, Any]]]:
    """Build vital measurement options from data.

    Args:
        vitals_df: Vitals dataframe with _type_clean column.

    Returns:
        List of (label, metadata) tuples.
    """
    options: list[tuple[str, dict[str, Any]]] = []

    # Add unique vital types
    unique_types = sorted(set(vitals_df["_type_clean"].dropna().unique()))
    for vital_name in unique_types:
        label = f"Vital | {vital_name}"
        options.append((label, {"dataset": "vital", "name": vital_name}))

    # Add unspecified if present
    if vitals_df["_type_clean"].isna().any():
        options.append(
            (
                "Vital | Unspecified type",
                {"dataset": "vital", "name": None},
            )
        )

    return options


def build_lab_options(labs_df: pd.DataFrame) -> list[tuple[str, dict[str, Any]]]:
    """Build lab measurement options from data.

    Args:
        labs_df: Labs dataframe with _name_clean and _loinc_clean columns.

    Returns:
        List of (label, metadata) tuples.
    """
    options: list[tuple[str, dict[str, Any]]] = []

    # Get unique lab combinations
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

    return options


def build_all_options(
    vitals_df: pd.DataFrame, labs_df: pd.DataFrame
) -> list[tuple[str, dict[str, Any]]]:
    """Build combined vital and lab options.

    Args:
        vitals_df: Vitals dataframe with _type_clean column.
        labs_df: Labs dataframe with _name_clean and _loinc_clean columns.

    Returns:
        Sorted list of all (label, metadata) tuples.
    """
    options: list[tuple[str, dict[str, Any]]] = []

    if not vitals_df.empty:
        options.extend(build_vital_options(vitals_df))

    if not labs_df.empty:
        options.extend(build_lab_options(labs_df))

    return sorted(options, key=lambda item: item[0])


def extract_labels(options: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """Extract display labels from options.

    Args:
        options: List of (label, metadata) tuples.

    Returns:
        List of label strings.
    """
    return [label for label, _ in options]


def get_metadata_for_label(
    options: list[tuple[str, dict[str, Any]]], label: str
) -> dict[str, Any]:
    """Look up metadata for a given label.

    Args:
        options: List of (label, metadata) tuples.
        label: Label to search for.

    Returns:
        Metadata dict for the label.

    Raises:
        StopIteration: If label not found.
    """
    return next(meta for lbl, meta in options if lbl == label)
