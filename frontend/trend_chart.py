"""Chart building for trend visualization.

Purpose: Construct Altair charts for patient trends with optional reference bands.
Author: Lauren Parlett
Date: 2025-11-01
Tests: Manual Streamlit validation pending.
AI-assisted: Module generated with AI assistance.
"""

from __future__ import annotations

from typing import Optional, cast

import altair as alt
import pandas as pd


def build_line_chart(
    chart_df: pd.DataFrame,
    tooltip_fields: list[alt.Tooltip],
    *,
    y_title: str = "Value",
) -> alt.Chart:
    """Build line chart for time series data.

    Args:
        chart_df: Data with measurement_time and value_numeric columns.
        tooltip_fields: Tooltip configuration.
        y_title: Y-axis title.

    Returns:
        Altair Chart object.
    """
    x_encoding = alt.X("measurement_time:T", title="Measurement Date")
    y_encoding = alt.Y("value_numeric:Q", title=y_title)

    chart = (
        alt.Chart(chart_df)
        .mark_line(point=True)
        .encode(
            x=x_encoding,
            y=y_encoding,
            tooltip=tooltip_fields,
        )
    )
    return cast(alt.Chart, chart)


def build_reference_band_chart(
    reference_band_df: pd.DataFrame,
    *,
    color: str = "#D386FF",
    opacity: float = 0.50,
) -> alt.Chart:
    """Build area chart for reference range band.

    Args:
        reference_band_df: Data with measurement_time, reference_low, reference_high.
        color: Band color (hex).
        opacity: Band opacity (0-1).

    Returns:
        Altair Chart object.
    """
    x_encoding = alt.X("measurement_time:T", title="Measurement Date")
    chart = (
        alt.Chart(reference_band_df)
        .mark_area(opacity=opacity, color=color)
        .encode(
            x=x_encoding,
            y=alt.Y("reference_low:Q"),
            y2="reference_high:Q",
        )
    )
    return cast(alt.Chart, chart)


def build_combined_chart(
    line_chart: alt.Chart,
    reference_band_df: Optional[pd.DataFrame] = None,
) -> alt.Chart:
    """Combine line chart with optional reference band.

    Args:
        line_chart: Line chart object.
        reference_band_df: Optional reference band dataframe.

    Returns:
        Combined or simple chart.
    """
    if reference_band_df is not None and not reference_band_df.empty:
        band_chart = build_reference_band_chart(reference_band_df)
        layered = alt.layer(band_chart, line_chart).resolve_scale(y="shared")
        return cast(alt.Chart, layered)
    return cast(alt.Chart, line_chart)


def finalize_chart(chart: alt.Chart) -> alt.Chart:
    """Add interactivity to chart.

    Args:
        chart: Base chart object.

    Returns:
        Interactive chart.
    """
    return cast(alt.Chart, chart.interactive())
