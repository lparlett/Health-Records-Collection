# Purpose: Streamlit helpers to document the database schema and ER relationships.
# Author: Codex + Lauren
# Date: 2025-10-27
# Tests: Manual Streamlit validation; automated frontend coverage pending.
# AI-assisted: Module generated with AI assistance.
from __future__ import annotations

from pathlib import Path
from typing import Dict, cast

from health_records_collection.frontend.common_types import Anchor, NodeSpec, EdgeSpec
from health_records_collection.frontend.layout_engine import LayoutEngine
from health_records_collection.frontend.schema_parser import (
    SchemaParser,
    TableDefinition,
)
from health_records_collection.frontend.schema_ui import (
    get_display_options,
    render_diagram,
    render_entity_summary,
)


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


def _load_schema_definitions() -> tuple[TableDefinition, ...]:
    """Parse schema.sql into table and foreign key metadata using SchemaParser."""
    parser = SchemaParser(SCHEMA_PATH)
    return parser.parse()


def _build_specs() -> tuple[tuple[NodeSpec, ...], tuple[EdgeSpec, ...]]:
    """Construct node and edge specifications from schema metadata.

    Uses LayoutEngine to compute table positions and anchor inference.
    """
    definitions = _load_schema_definitions()

    # Use LayoutEngine to compute layout
    engine = LayoutEngine(definitions, LAYOUT_HINTS)
    layout = engine.get_layout()

    node_specs: list[NodeSpec] = []
    edge_specs: list[EdgeSpec] = []

    # Build node specs with layout positions
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

    # Build edge specs using anchor inference from engine
    for table in definitions:
        for fk in table.foreign_keys:
            if fk.target_table not in layout:
                continue
            source_anchor_str, target_anchor_str = engine.infer_anchor(
                table.name, fk.target_table
            )
            label = fk.column
            if fk.column != fk.target_column:
                label = f"{fk.column} → {fk.target_column}"
            edge_specs.append(
                EdgeSpec(
                    source=table.name,
                    target=fk.target_table,
                    label=label,
                    source_anchor=cast(Anchor, source_anchor_str),
                    target_anchor=cast(Anchor, target_anchor_str),
                )
            )

    return tuple(node_specs), tuple(edge_specs)


def render_schema_documentation() -> None:
    """Render ER diagram and supporting notes for the SQLite schema.

    Orchestrates the complete schema documentation workflow:
    1. Get user display options
    2. Build schema specs
    3. Render diagram with options
    4. Display entity summary
    """
    # Get display options from user
    options = get_display_options()

    # Build diagram specifications
    node_specs, edge_specs = _build_specs()

    # Render the diagram
    render_diagram(node_specs, edge_specs, options)

    # Render entity summary
    render_entity_summary()
