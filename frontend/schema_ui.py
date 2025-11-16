"""Streamlit UI components for database schema documentation.

Purpose: Handle all Streamlit UI orchestration for schema visualization,
including zoom/color selection, diagram rendering, and entity summary.
Author: Lauren Parlett
Date: 2025-11-01
Tests: Manual Streamlit validation; automated frontend coverage pending.
AI-assisted: Module generated with AI assistance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from health_records_collection.frontend.common_types import NodeSpec
from health_records_collection.frontend.diagram_builder import (
    DiagramBuilder,
    EdgeSpec as DiagramEdgeSpec,
    PositionedNode as DiagramPositionedNode,
)


@dataclass(frozen=True)
class DisplayOptions:
    """User-selected display options for schema diagram."""

    zoom: float
    text_color: str
    show_connectors: bool
    focus_table: str | None


def get_display_options(node_specs: tuple[NodeSpec, ...]) -> DisplayOptions:
    """Render display option controls and return selected values.

    Returns:
        DisplayOptions with zoom level and text color.
    """
    st.markdown("### Display options")
    col_zoom, col_color, col_edges = st.columns([2, 1, 1])

    with col_zoom:
        zoom_options = {
            "0.75x (compact)": 0.75,
            "1x (default)": 1.0,
            "1.5x": 1.5,
            "2x": 2.0,
            "3x": 3.0,
        }
        zoom_label = st.selectbox(
            "Zoom",
            options=list(zoom_options.keys()),
            index=1,
            key="schema_zoom_choice",
            help=(
                "Switch between preset zoom levels. Larger options increase "
                "font size but may take longer to render."
            ),
        )
        zoom = zoom_options[zoom_label]

    with col_color:
        text_color = st.color_picker(
            "Text color",
            value="#202124",
            key="schema_text_color",
            help="Adjust label contrast within the diagram.",
        )

    with col_edges:
        show_connectors = st.checkbox(
            "Show connectors",
            value=True,
            key="schema_show_edges",
            help="Toggle visual connector lines on/off.",
        )

    table_options = ["Show all tables", *sorted(spec.title for spec in node_specs)]
    focus_label = st.selectbox(
        "Highlight relationships for",
        options=table_options,
        index=0,
        key="schema_focus_table",
        help="Highlight relationships for a single table to reduce clutter.",
    )
    focus_table = None
    if focus_label != "Show all tables":
        for spec in node_specs:
            if spec.title == focus_label:
                focus_table = spec.identifier
                break

    return DisplayOptions(
        zoom=zoom,
        text_color=text_color,
        show_connectors=show_connectors,
        focus_table=focus_table,
    )


def render_diagram(
    node_specs: tuple,
    edge_specs: tuple,
    options: DisplayOptions,
) -> None:
    """Render the ER diagram with header and description.

    Args:
        node_specs: Tuple of NodeSpec objects with table metadata.
        edge_specs: Tuple of EdgeSpec objects with relationships.
        options: Display options (zoom, color).
    """
    st.header("Database Schema")
    st.markdown(
        (
            "The diagram below summarizes how patient encounters, clinical "
            "artifacts, and provenance records relate within the "
            "Health Records Collection workspace."
        )
    )

    # Convert specs to diagram builder format
    positioned_nodes: list[DiagramPositionedNode] = []
    for spec in node_specs:
        if spec.x or spec.y:
            node_x = spec.x
            node_y = spec.y
        else:
            node_x = spec.column * 330.0
            node_y = spec.row * 310.0
        positioned_nodes.append(
            DiagramPositionedNode(
                identifier=spec.identifier,
                title=spec.title,
                fields=spec.fields,
                x=node_x,
                y=node_y,
                width=spec.width,
                height=spec.height,
            )
        )

    # Convert edge specs to diagram builder format
    diagram_edges: list[DiagramEdgeSpec] = [
        DiagramEdgeSpec(
            source=edge.source,
            target=edge.target,
            label=edge.label,
            source_anchor=edge.source_anchor,
            target_anchor=edge.target_anchor,
        )
        for edge in edge_specs
    ]

    # Build and render diagram
    builder = DiagramBuilder(
        positioned_nodes,
        diagram_edges,
        zoom=options.zoom,
        text_color=options.text_color,
        show_edges=options.show_connectors,
        focus_table=options.focus_table,
    )
    diagram_html, diagram_height = builder.build()
    components.html(diagram_html, height=diagram_height, scrolling=True)


def render_entity_summary() -> None:
    """Render summary table of key database entities."""
    st.markdown("### Entity Summary")
    st.table(pd.DataFrame(_get_entity_descriptions()))


def _get_entity_descriptions() -> Iterable[dict[str, str]]:
    """Return high-level descriptions for the most used tables.

    Returns:
        Iterable of dicts with "Table" and "Purpose" keys.
    """
    return [
        {
            "Table": "data_source",
            "Purpose": ("Provenance details for every ingested document or archive."),
        },
        {
            "Table": "patient",
            "Purpose": "Core demographic record linked to encounters and notes.",
        },
        {
            "Table": "encounter",
            "Purpose": "Clinical visit metadata tying patients to providers.",
        },
        {
            "Table": "provider",
            "Purpose": "Clinician or organization identifiers referenced elsewhere.",
        },
        {
            "Table": "progress_note",
            "Purpose": "Narrative notes captured per encounter and provider.",
        },
        {
            "Table": "medication",
            "Purpose": "Prescribed medications tied to patients and encounters.",
        },
        {
            "Table": "lab_result",
            "Purpose": "LOINC-based lab observations for a patient encounter.",
        },
        {
            "Table": "vital",
            "Purpose": "Vital sign measurements with per-encounter context.",
        },
        {
            "Table": "procedure",
            "Purpose": "Documented procedures with coding metadata.",
        },
        {
            "Table": "immunization",
            "Purpose": "Immunization history per patient with vaccine details.",
        },
        {
            "Table": "attachment",
            "Purpose": ("Supplemental documents linked to data sources and patients."),
        },
    ]
