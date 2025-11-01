from __future__ import annotations

# Purpose: Streamlit helpers to document the database schema and ER relationships.
# Author: Codex + Lauren
# Date: 2025-10-27
# Tests: Manual Streamlit validation; automated frontend coverage pending.
# AI-assisted: Module generated with AI assistance.

import html
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, Literal, Sequence

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


Anchor = Literal["left", "right", "top", "bottom"]


@dataclass(frozen=True)
class NodeSpec:
    """Static definition for a table node in the ER diagram."""

    identifier: str
    title: str
    fields: tuple[str, ...]
    column: int
    row: int


@dataclass
class PositionedNode:
    """Node with computed coordinates and dimensions."""

    spec: NodeSpec
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class EdgeSpec:
    """Relationship connector between two nodes."""

    source: str
    target: str
    label: str
    source_anchor: Anchor
    target_anchor: Anchor


@dataclass(frozen=True)
class ForeignKey:
    """Foreign key relationship extracted from schema.sql."""

    column: str
    target_table: str
    target_column: str


@dataclass(frozen=True)
class TableDefinition:
    """Table metadata parsed from schema.sql."""

    name: str
    columns: tuple[str, ...]
    foreign_keys: tuple[ForeignKey, ...]


@dataclass(frozen=True)
class RelationshipSummary:
    """Outgoing and incoming relationships associated with a node."""

    outgoing: tuple[EdgeSpec, ...]
    incoming: tuple[EdgeSpec, ...]
    base_height: float


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema.sql"

LAYOUT_HINTS: Dict[str, tuple[int, int]] = {
    "data_source": (0, 1),
    "attachment": (0, 2),
    "patient": (1, 1),
    "provider": (1, 0),
    "encounter": (2, 1),
    "medication": (3, 0),
    "lab_result": (3, 1),
    "vital": (3, 2),
    "procedure": (4, 0),
    "progress_note": (4, 1),
    "immunization": (4, 2),
}


def _normalize_column_line(raw_line: str) -> str:
    """Return a cleaned column definition for display."""
    stripped = raw_line.strip().rstrip(",")
    if stripped.upper().startswith("PRIMARY KEY"):
        return stripped
    collapsed = " ".join(stripped.split())
    collapsed = re.sub(r"\bPRIMARY\s+KEY\b", "PK", collapsed, flags=re.IGNORECASE)
    collapsed = re.sub(r"\bAUTOINCREMENT\b", "AUTO", collapsed, flags=re.IGNORECASE)
    collapsed = re.sub(r"\bINTEGER\b", "INT", collapsed, flags=re.IGNORECASE)
    collapsed = re.sub(r"\bNOT\s+NULL\b", "NN", collapsed, flags=re.IGNORECASE)
    collapsed = re.sub(
        r"\bDEFAULT\s+([^\s]+)\b", r"DEF \1", collapsed, flags=re.IGNORECASE
    )
    return collapsed


def _parse_foreign_key(raw_line: str) -> ForeignKey | None:
    """Parse a foreign key constraint line into a ForeignKey object."""
    stripped = raw_line.strip().rstrip(",")
    upper = stripped.upper()
    if not upper.startswith("FOREIGN KEY"):
        return None
    try:
        before_ref, after_ref = stripped.split("REFERENCES", maxsplit=1)
    except ValueError:
        return None
    column_part_start = before_ref.find("(")
    column_part_end = before_ref.find(")", column_part_start)
    target_part_start = after_ref.find("(")
    target_part_end = after_ref.find(")", target_part_start)
    if (
        column_part_start == -1
        or column_part_end == -1
        or target_part_start == -1
        or target_part_end == -1
    ):
        return None
    column_name = before_ref[column_part_start + 1 : column_part_end].strip()
    target_table = after_ref[:target_part_start].strip().split()[0]
    target_column = after_ref[target_part_start + 1 : target_part_end].strip()
    return ForeignKey(
        column=column_name,
        target_table=target_table,
        target_column=target_column,
    )


@lru_cache(maxsize=1)
def _load_schema_definitions() -> tuple[TableDefinition, ...]:
    """Parse schema.sql into table and foreign key metadata."""
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"schema.sql not found at {SCHEMA_PATH}")
    tables: list[TableDefinition] = []
    current_name: str | None = None
    current_columns: list[str] = []
    current_fks: list[ForeignKey] = []
    capturing = False

    for line in SCHEMA_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if not capturing and upper.startswith("CREATE TABLE"):
            match = re.match(
                r"CREATE TABLE(?: IF NOT EXISTS)?\s+([A-Za-z_][A-Za-z0-9_]*)",
                stripped,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            current_name = match.group(1)
            current_columns = []
            current_fks = []
            capturing = True
            continue
        if not capturing:
            continue
        if upper.startswith("--"):
            continue
        if stripped.startswith(")"):
            if current_name is not None:
                tables.append(
                    TableDefinition(
                        name=current_name,
                        columns=tuple(current_columns),
                        foreign_keys=tuple(current_fks),
                    )
                )
            capturing = False
            current_name = None
            current_columns = []
            current_fks = []
            continue
        if not stripped:
            continue
        fk = _parse_foreign_key(stripped)
        if fk is not None:
            current_fks.append(fk)
            continue
        upper_stripped = stripped.upper()
        if upper_stripped.startswith("PRIMARY KEY") or upper_stripped.startswith(
            "UNIQUE"
        ):
            current_columns.append(_normalize_column_line(stripped))
            continue
        if upper_stripped.startswith("CONSTRAINT"):
            continue
        current_columns.append(_normalize_column_line(stripped))

    return tuple(tables)


def _assign_layout(
    definitions: Sequence[TableDefinition],
) -> Dict[str, tuple[int, int]]:
    """Return column/row positions for each table using hints with sensible fallbacks."""
    layout: Dict[str, tuple[int, int]] = dict(LAYOUT_HINTS)
    next_column = (max((col for col, _ in layout.values()), default=-1) + 1) or 0
    next_row = 0
    for definition in definitions:
        if definition.name in layout:
            continue
        layout[definition.name] = (next_column, next_row)
        next_row += 1
    return layout


def _build_specs() -> tuple[tuple[NodeSpec, ...], tuple[EdgeSpec, ...]]:
    """Construct node and edge specifications from schema metadata."""
    definitions = _load_schema_definitions()
    layout = _assign_layout(definitions)

    node_specs: list[NodeSpec] = []
    edge_specs: list[EdgeSpec] = []

    for table in definitions:
        column, row = layout[table.name]
        node_specs.append(
            NodeSpec(
                identifier=table.name,
                title=table.name,
                fields=table.columns,
                column=column,
                row=row,
            )
        )

    def infer_anchor(
        source: tuple[int, int], target: tuple[int, int]
    ) -> tuple[Anchor, Anchor]:
        src_col, src_row = source
        tgt_col, tgt_row = target
        if src_col < tgt_col:
            return "right", "left"
        if src_col > tgt_col:
            return "left", "right"
        if src_row < tgt_row:
            return "bottom", "top"
        if src_row > tgt_row:
            return "top", "bottom"
        return "right", "right"

    for table in definitions:
        for fk in table.foreign_keys:
            if fk.target_table not in layout:
                continue
            source_anchor, target_anchor = infer_anchor(
                layout[table.name],
                layout[fk.target_table],
            )
            label = fk.column
            if fk.column != fk.target_column:
                label = f"{fk.column} → {fk.target_column}"
            edge_specs.append(
                EdgeSpec(
                    source=table.name,
                    target=fk.target_table,
                    label=label,
                    source_anchor=source_anchor,
                    target_anchor=target_anchor,
                )
            )

    return tuple(node_specs), tuple(edge_specs)


def render_schema_documentation() -> None:
    """Render ER diagram and supporting notes for the SQLite schema."""
    st.markdown("### Display options")
    col_zoom, col_color = st.columns([2, 1])
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
            help="Switch between preset zoom levels. Larger options increase font size but may take longer to render.",
        )
        zoom = zoom_options[zoom_label]
    with col_color:
        text_color = st.color_picker(
            "Text color",
            value="#202124",
            key="schema_text_color",
            help="Adjust label contrast within the diagram.",
        )
    st.header("Database Schema")
    st.markdown(
        (
            "The diagram below summarizes how patient encounters, clinical "
            "artifacts, and provenance records relate within the "
            "Health Records Collection workspace."
        )
    )
    diagram_html, diagram_height = _build_schema_diagram(
        zoom=zoom, text_color=text_color
    )
    components.html(diagram_html, height=diagram_height, scrolling=True)
    st.markdown("### Entity Summary")
    st.table(pd.DataFrame(_schema_summary()))


def _build_schema_diagram(*, zoom: float, text_color: str) -> tuple[str, int]:
    """Return HTML-wrapped SVG markup plus a recommended container height."""
    node_specs, edge_specs = _build_specs()
    scale = max(0.75, min(3.0, zoom))
    title_size = 18 * scale
    field_size = 13 * scale
    label_size = 11 * scale
    edge_color = "#5c7080"
    card_fill = "#f5f7fb"
    card_border = "#c3ccd6"

    BASE_CARD_WIDTH = 250.0
    BASE_CARD_HEIGHT = 250.0
    BASE_H_GAP = 80.0
    BASE_V_GAP = 60.0
    BASE_MARGIN = 60.0
    REL_SECTION_MARGIN = 8.0
    REL_HEADER_OFFSET = 0.0
    REL_LINE_SPACING = 12.0
    REL_FOOTER_PADDING = 8.0
    HEADER_BLOCK_HEIGHT = 36.0
    FIELD_LINE_SPACING = 16.0
    FIELD_BOTTOM_MARGIN = 12.0
    REL_SECTION_GAP = 12.0

    def compute_position(col: int, row: int) -> tuple[float, float]:
        x = BASE_MARGIN + col * (BASE_CARD_WIDTH + BASE_H_GAP)
        y = BASE_MARGIN + row * (BASE_CARD_HEIGHT + BASE_V_GAP)
        return x, y

    nodes: list[PositionedNode] = []
    for spec in node_specs:
        x, y = compute_position(spec.column, spec.row)
        nodes.append(
            PositionedNode(
                spec=spec,
                x=x,
                y=y,
                width=BASE_CARD_WIDTH,
                height=BASE_CARD_HEIGHT,
            )
        )

    node_lookup: Dict[str, PositionedNode] = {
        node.spec.identifier: node for node in nodes
    }
    edges_by_pair: Dict[tuple[str, str], list[EdgeSpec]] = defaultdict(list)
    outgoing_edges: Dict[str, list[EdgeSpec]] = defaultdict(list)
    incoming_edges: Dict[str, list[EdgeSpec]] = defaultdict(list)
    source_anchor_slots: Dict[str, Dict[Anchor, list[EdgeSpec]]] = {}
    target_anchor_slots: Dict[str, Dict[Anchor, list[EdgeSpec]]] = {}
    for edge in edge_specs:
        edges_by_pair[(edge.source, edge.target)].append(edge)
        outgoing_edges[edge.source].append(edge)
        incoming_edges[edge.target].append(edge)
        source_anchor_slots.setdefault(edge.source, {}).setdefault(
            edge.source_anchor, []
        ).append(edge)
        target_anchor_slots.setdefault(edge.target, {}).setdefault(
            edge.target_anchor, []
        ).append(edge)

    relationship_info: Dict[str, RelationshipSummary] = {}
    row_max_height: Dict[int, float] = {}
    for node in nodes:
        outgoing = outgoing_edges.get(node.spec.identifier, [])
        incoming = incoming_edges.get(node.spec.identifier, [])
        field_required = (
            HEADER_BLOCK_HEIGHT
            + len(node.spec.fields) * FIELD_LINE_SPACING
            + FIELD_BOTTOM_MARGIN
        )
        base_height = max(BASE_CARD_HEIGHT, field_required)
        extra_height = 0.0
        if outgoing:
            extra_height += (
                REL_SECTION_MARGIN
                + REL_HEADER_OFFSET
                + len(outgoing) * REL_LINE_SPACING
                + REL_FOOTER_PADDING
            )
        if incoming:
            gap = REL_SECTION_MARGIN if not outgoing else REL_SECTION_GAP
            extra_height += (
                gap
                + REL_HEADER_OFFSET
                + len(incoming) * REL_LINE_SPACING
                + REL_FOOTER_PADDING
            )
        node.height = base_height + extra_height
        node.width = BASE_CARD_WIDTH
        relationship_info[node.spec.identifier] = RelationshipSummary(
            outgoing=tuple(outgoing),
            incoming=tuple(incoming),
            base_height=base_height,
        )
        row_max_height[node.spec.row] = max(
            row_max_height.get(node.spec.row, 0.0), node.height
        )

    row_offsets: Dict[int, float] = {}
    current_y = BASE_MARGIN
    for row in sorted(row_max_height):
        row_offsets[row] = current_y
        current_y += row_max_height[row] + BASE_V_GAP

    for node in nodes:
        node.x = BASE_MARGIN + node.spec.column * (BASE_CARD_WIDTH + BASE_H_GAP)
        node.y = row_offsets.get(node.spec.row, BASE_MARGIN)

    def anchor_point(
        node_id: str, anchor: Anchor, slot: int, total: int
    ) -> tuple[float, float]:
        node = node_lookup[node_id]
        x = node.x * scale
        y = node.y * scale
        width = node.width * scale
        height = node.height * scale
        total = max(total, 1)
        offset = slot + 1
        if anchor == "left":
            step = height / (total + 1)
            return x, y + step * offset
        if anchor == "right":
            step = height / (total + 1)
            return x + width, y + step * offset
        if anchor == "top":
            step = width / (total + 1)
            return x + step * offset, y
        if anchor == "bottom":
            step = width / (total + 1)
            return x + step * offset, y + height
        return x + width / 2, y + height / 2

    extent_x = max((node.x + node.width) for node in nodes) if nodes else 0.0
    extent_y = max((node.y + node.height) for node in nodes) if nodes else 0.0
    diagram_width = int((extent_x + BASE_MARGIN) * scale)
    diagram_height = int((extent_y + BASE_MARGIN) * scale)
    svg: list[str] = [
        (
            f'<div style="width:100%; overflow:auto; background-color:#ffffff;">'
            f'<svg width="{diagram_width}" height="{diagram_height}" '
            f'viewBox="0 0 {diagram_width} {diagram_height}" '
            'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Health Records schema diagram">'
        ),
        "<defs>",
        (
            f'<marker id="arrowhead" markerWidth="{10 * scale}" markerHeight="{10 * scale}" '
            f'refX="{10 * scale}" refY="{5 * scale}" orient="auto">'
            f'<path d="M0,0 L0,{10 * scale} L{10 * scale},{5 * scale} Z" fill="{edge_color}" />'
            "</marker>"
        ),
        "</defs>",
    ]

    def _curve_path(
        x1: float, y1: float, x2: float, y2: float, *, orientation: str
    ) -> str:
        if orientation == "horizontal":
            offset = max(60.0 * scale, abs(x2 - x1) / 2)
            if x2 < x1:
                offset = -offset
            return (
                f"M{x1:.1f},{y1:.1f} "
                f"C{x1 + offset:.1f},{y1:.1f} {x2 - offset:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"
            )
        if orientation == "vertical":
            offset = max(40.0 * scale, abs(y2 - y1) / 2)
            if y2 < y1:
                offset = -offset
            return (
                f"M{x1:.1f},{y1:.1f} "
                f"C{x1:.1f},{y1 + offset:.1f} {x2:.1f},{y2 - offset:.1f} {x2:.1f},{y2:.1f}"
            )
        # Diagonal or mixed orientation
        h_offset = max(40.0 * scale, abs(x2 - x1) / 2)
        v_offset = max(40.0 * scale, abs(y2 - y1) / 2)
        if x2 < x1:
            h_offset = -h_offset
        if y2 < y1:
            v_offset = -v_offset
        return (
            f"M{x1:.1f},{y1:.1f} "
            f"C{x1 + h_offset:.1f},{y1:.1f} {x2:.1f},{y2 - v_offset:.1f} {x2:.1f},{y2:.1f}"
        )

    legend_entries = [
        ("AUTO", "Auto-incrementing"),
        ("DEF", "Default value"),
        ("INT", "Integer"),
        ("NN", "Not Null"),
        ("PK", "Primary Key"),
    ]
    legend_padding = 10.0 * scale
    legend_line_height = (label_size + 4.0) * scale
    legend_header_height = (label_size + 6.0) * scale
    legend_width = 220.0 * scale
    legend_height = (
        legend_padding * 2
        + legend_header_height
        + len(legend_entries) * legend_line_height
    )
    legend_x = 16.0 * scale
    legend_y = 16.0 * scale
    svg.append(
        (
            f'<rect x="{legend_x:.1f}" y="{legend_y:.1f}" '
            f'width="{legend_width:.1f}" height="{legend_height:.1f}" '
            'rx="12" ry="12" fill="rgba(255,255,255,0.86)" '
            'stroke="#c3ccd6" stroke-width="1.0" />'
        )
    )
    legend_header_y = legend_y + legend_padding + legend_header_height * 0.8
    svg.append(
        (
            f'<text x="{legend_x + legend_width / 2:.1f}" y="{legend_header_y:.1f}" '
            f'fill="{edge_color}" font-size="{label_size:.1f}" '
            'font-family="Helvetica" text-anchor="middle" font-weight="600">'
            "Legend"
            "</text>"
        )
    )
    for idx, (abbr, meaning) in enumerate(legend_entries, start=1):
        entry_y = legend_header_y + idx * legend_line_height
        svg.append(
            (
                f'<text x="{legend_x + legend_padding:.1f}" y="{entry_y:.1f}" '
                f'fill="{edge_color}" font-size="{label_size:.1f}" '
                'font-family="Helvetica" text-anchor="start">'
                f"{html.escape(abbr)} = {html.escape(meaning)}"
                "</text>"
            )
        )

    # Draw curves without inline labels
    for edges_for_pair in edges_by_pair.values():
        for edge in edges_for_pair:
            source_slots = source_anchor_slots.get(edge.source, {}).get(
                edge.source_anchor, [edge]
            )
            target_slots = target_anchor_slots.get(edge.target, {}).get(
                edge.target_anchor, [edge]
            )
            source_index = source_slots.index(edge)
            target_index = target_slots.index(edge)
            start_x, start_y = anchor_point(
                edge.source, edge.source_anchor, source_index, len(source_slots)
            )
            end_x, end_y = anchor_point(
                edge.target, edge.target_anchor, target_index, len(target_slots)
            )
            if edge.source_anchor in {"left", "right"} and edge.target_anchor in {
                "left",
                "right",
            }:
                orientation = "horizontal"
            elif edge.source_anchor in {"top", "bottom"} and edge.target_anchor in {
                "top",
                "bottom",
            }:
                orientation = "vertical"
            else:
                orientation = "diagonal"
            path = _curve_path(start_x, start_y, end_x, end_y, orientation=orientation)
            svg.append(
                (
                    f'<path d="{path}" '
                    f'stroke="{edge_color}" stroke-width="{1.2 * scale:.2f}" '
                    'fill="none" marker-end="url(#arrowhead)" />'
                )
            )

    for node in nodes:
        x = node.x * scale
        y = node.y * scale
        width = node.width * scale
        height = node.height * scale
        svg.append(
            (
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" '
                f'rx="{12 * scale:.1f}" ry="{12 * scale:.1f}" '
                f'fill="{card_fill}" stroke="{card_border}" stroke-width="{1.2 * scale:.2f}" />'
            )
        )
        title_y = y + 28 * scale
        svg.append(
            (
                f'<text x="{x + width / 2:.1f}" y="{title_y:.1f}" '
                f'fill="{text_color}" font-size="{title_size:.1f}" '
                'font-family="Helvetica" font-weight="600" text-anchor="middle">'
                f"{html.escape(node.spec.title)}"
                "</text>"
            )
        )
        for idx, field in enumerate(node.spec.fields, start=1):
            line_y = (
                title_y
                + (HEADER_BLOCK_HEIGHT - 8.0) * scale
                + (idx - 1) * FIELD_LINE_SPACING * scale
            )
            if line_y + 16 * scale > y + height:
                break
            svg.append(
                (
                    f'<text x="{x + width / 2:.1f}" y="{line_y:.1f}" '
                    f'fill="{text_color}" font-size="{field_size:.1f}" '
                    'font-family="Helvetica" text-anchor="middle">'
                    f"{html.escape(field)}"
                    "</text>"
                )
            )
        summary = relationship_info.get(
            node.spec.identifier,
            RelationshipSummary((), (), BASE_CARD_HEIGHT),
        )
        base_height = summary.base_height
        cursor = y + base_height * scale

        if summary.outgoing:
            cursor += REL_SECTION_MARGIN * scale
            header_y = cursor + REL_HEADER_OFFSET * scale
            svg.append(
                (
                    f'<text x="{x + width / 2:.1f}" y="{header_y:.1f}" '
                    f'fill="{edge_color}" font-size="{label_size:.1f}" '
                    'font-family="Helvetica" text-anchor="middle" font-weight="600">'
                    "References"
                    "</text>"
                )
            )
            for rel_idx, edge in enumerate(summary.outgoing, start=1):
                rel_y = header_y + rel_idx * (REL_LINE_SPACING * scale)
                svg.append(
                    (
                        f'<text x="{x + 12 * scale:.1f}" y="{rel_y:.1f}" '
                        f'fill="{edge_color}" font-size="{label_size:.1f}" '
                        'font-family="Helvetica" text-anchor="start">'
                        f"- {html.escape(edge.label)} → {html.escape(edge.target)}"
                        "</text>"
                    )
                )
            cursor = (
                header_y
                + len(summary.outgoing) * (REL_LINE_SPACING * scale)
                + REL_FOOTER_PADDING * scale
            )

        if summary.incoming:
            gap = REL_SECTION_GAP if summary.outgoing else REL_SECTION_MARGIN
            cursor += gap * scale
            header_y = cursor + REL_HEADER_OFFSET * scale
            svg.append(
                (
                    f'<text x="{x + width / 2:.1f}" y="{header_y:.1f}" '
                    f'fill="{edge_color}" font-size="{label_size:.1f}" '
                    'font-family="Helvetica" text-anchor="middle" font-weight="600">'
                    "Referenced by"
                    "</text>"
                )
            )
            for rel_idx, edge in enumerate(summary.incoming, start=1):
                rel_y = header_y + rel_idx * (REL_LINE_SPACING * scale)
                svg.append(
                    (
                        f'<text x="{x + 12 * scale:.1f}" y="{rel_y:.1f}" '
                        f'fill="{edge_color}" font-size="{label_size:.1f}" '
                        'font-family="Helvetica" text-anchor="start">'
                        f"- {html.escape(edge.source)} ← {html.escape(edge.label)}"
                        "</text>"
                    )
                )
            cursor = (
                header_y
                + len(summary.incoming) * (REL_LINE_SPACING * scale)
                + REL_FOOTER_PADDING * scale
            )

    svg.append("</svg></div>")
    return "".join(svg), int(diagram_height + 40)


def _schema_summary() -> Iterable[dict[str, str]]:
    """Return high level descriptions for the most used tables."""
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
