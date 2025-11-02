"""Layout engine for diagram node positioning and sizing.

Purpose: Handle layout computation, node height calculation based on relationships,
and position coordination for schema diagram rendering.
Author: Lauren Parlett
Date: 2025-11-01
Tests: Manual Streamlit validation; automated frontend coverage pending.
AI-assisted: Module generated with AI assistance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Sequence

from health_records_collection.frontend.schema_parser import (
    TableDefinition,
)


@dataclass
class LayoutNode:
    """Node with computed layout dimensions and position."""

    identifier: str
    column: int
    row: int
    width: float
    height: float
    x: float
    y: float


@dataclass
class RelationshipCount:
    """Tracks outgoing and incoming relationships for a node."""

    outgoing_count: int
    incoming_count: int


class LayoutEngine:
    """Compute layout positioning and dimensions for schema diagram nodes.

    Handles:
    - Table positioning using hints and fallbacks
    - Node height calculation based on fields and relationships
    - Row offset computation
    - Anchor point inference for edge routing
    """

    # Layout constants (must match DiagramBuilder)
    BASE_CARD_WIDTH = 250.0
    BASE_CARD_HEIGHT = 250.0
    BASE_H_GAP = 80.0
    BASE_V_GAP = 60.0
    BASE_MARGIN = 60.0

    # Relationship section sizing
    HEADER_BLOCK_HEIGHT = 36.0
    FIELD_LINE_SPACING = 16.0
    FIELD_BOTTOM_MARGIN = 12.0
    REL_SECTION_MARGIN = 8.0
    REL_HEADER_OFFSET = 0.0
    REL_LINE_SPACING = 12.0
    REL_FOOTER_PADDING = 8.0
    REL_SECTION_GAP = 12.0

    def __init__(
        self,
        definitions: Sequence[TableDefinition],
        layout_hints: Dict[str, tuple[int, int]],
    ) -> None:
        """Initialize layout engine with schema and layout hints.

        Args:
            definitions: Table definitions from schema.
            layout_hints: Manual layout positions {table_name: (col, row)}.
        """
        self.definitions = definitions
        self.layout_hints = layout_hints
        self.table_layout: Dict[str, tuple[int, int]] = {}
        self.relationship_counts: Dict[str, RelationshipCount] = {}
        self.row_max_heights: Dict[int, float] = {}
        self.row_offsets: Dict[int, float] = {}

    def compute_layout(self) -> list[LayoutNode]:
        """Compute complete layout for all nodes.

        Returns:
            List of LayoutNode with final positions and dimensions.
        """
        # Step 1: Assign column/row positions
        self._assign_positions()

        # Step 2: Count relationships for each node
        self._count_relationships()

        # Step 3: Compute node heights based on fields and relationships
        self._compute_node_heights()

        # Step 4: Compute row offsets based on max heights
        self._compute_row_offsets()

        # Step 5: Build final layout nodes
        return self._build_layout_nodes()

    def _assign_positions(self) -> None:
        """Assign column/row positions to each table.

        Uses layout hints for manual positioning, fills remaining tables
        with fallback positions (right-to-left, top-to-bottom).
        """
        self.table_layout = dict(self.layout_hints)
        next_column = (
            max((col for col, _ in self.layout_hints.values()), default=-1) + 1
        ) or 0
        next_row = 0

        for definition in self.definitions:
            if definition.name in self.table_layout:
                continue
            self.table_layout[definition.name] = (next_column, next_row)
            next_row += 1

    def _count_relationships(self) -> None:
        """Count outgoing and incoming relationships for each node."""
        self.relationship_counts = {
            definition.name: RelationshipCount(outgoing_count=0, incoming_count=0)
            for definition in self.definitions
        }

        # Count outgoing (foreign keys)
        for definition in self.definitions:
            self.relationship_counts[definition.name].outgoing_count = len(
                definition.foreign_keys
            )

        # Count incoming (referenced by other tables)
        for definition in self.definitions:
            for fk in definition.foreign_keys:
                if fk.target_table in self.relationship_counts:
                    self.relationship_counts[fk.target_table].incoming_count += 1

    def _compute_node_heights(self) -> None:
        """Compute node heights based on fields and relationships.

        Each node has:
        - Header block for title
        - Field lines (one per column)
        - Optional "References" section (for outgoing relationships)
        - Optional "Referenced by" section (for incoming relationships)
        """
        for definition in self.definitions:
            # Base height: header + fields
            field_count = len(definition.columns)
            base_height = (
                self.HEADER_BLOCK_HEIGHT
                + field_count * self.FIELD_LINE_SPACING
                + self.FIELD_BOTTOM_MARGIN
            )
            base_height = max(self.BASE_CARD_HEIGHT, base_height)

            # Extra height for relationship sections
            extra_height = 0.0
            rel_count = self.relationship_counts[definition.name]

            if rel_count.outgoing_count > 0:
                extra_height += (
                    self.REL_SECTION_MARGIN
                    + self.REL_HEADER_OFFSET
                    + rel_count.outgoing_count * self.REL_LINE_SPACING
                    + self.REL_FOOTER_PADDING
                )

            if rel_count.incoming_count > 0:
                gap = (
                    self.REL_SECTION_MARGIN
                    if rel_count.outgoing_count == 0
                    else self.REL_SECTION_GAP
                )
                extra_height += (
                    gap
                    + self.REL_HEADER_OFFSET
                    + rel_count.incoming_count * self.REL_LINE_SPACING
                    + self.REL_FOOTER_PADDING
                )

            final_height = base_height + extra_height

            # Track max height for each row
            _, row = self.table_layout[definition.name]
            current_max = self.row_max_heights.get(row, 0.0)
            self.row_max_heights[row] = max(current_max, final_height)

    def _compute_row_offsets(self) -> None:
        """Compute Y-offset for each row based on cumulative heights.

        Rows are stacked vertically with gaps between them.
        """
        self.row_offsets = {}
        current_y = self.BASE_MARGIN

        for row in sorted(self.row_max_heights.keys()):
            self.row_offsets[row] = current_y
            current_y += self.row_max_heights[row] + self.BASE_V_GAP

    def _build_layout_nodes(self) -> list[LayoutNode]:
        """Build final LayoutNode objects with computed dimensions."""
        nodes: list[LayoutNode] = []

        for definition in self.definitions:
            col, row = self.table_layout[definition.name]
            x = self.BASE_MARGIN + col * (self.BASE_CARD_WIDTH + self.BASE_H_GAP)
            y = self.row_offsets.get(row, self.BASE_MARGIN)

            # Get height from pre-computed values
            height = self.row_max_heights.get(row, self.BASE_CARD_HEIGHT)

            nodes.append(
                LayoutNode(
                    identifier=definition.name,
                    column=col,
                    row=row,
                    width=self.BASE_CARD_WIDTH,
                    height=height,
                    x=x,
                    y=y,
                )
            )

        return nodes

    def get_table_position(self, table_name: str) -> tuple[int, int]:
        """Get the (column, row) position of a table.

        Args:
            table_name: Name of the table.

        Returns:
            Tuple of (column, row) grid position.

        Raises:
            KeyError: If table not in schema.
        """
        return self.table_layout[table_name]

    def get_layout(self) -> Dict[str, tuple[int, int]]:
        """Get the complete table layout mapping.

        Returns:
            Dictionary mapping table names to (column, row) positions.
        """
        if not self.table_layout:
            self._assign_positions()
        return self.table_layout

    def infer_anchor(self, source_table: str, target_table: str) -> tuple[str, str]:
        """Infer edge anchor points based on table positions.

        Determines which edges of source and target nodes the edge should
        connect based on relative positioning (left, right, top, bottom).

        Args:
            source_table: Name of source table.
            target_table: Name of target table.

        Returns:
            Tuple of (source_anchor, target_anchor).
        """
        src_col, src_row = self.table_layout[source_table]
        tgt_col, tgt_row = self.table_layout[target_table]

        if src_col < tgt_col:
            return "right", "left"
        if src_col > tgt_col:
            return "left", "right"
        if src_row < tgt_row:
            return "bottom", "top"
        if src_row > tgt_row:
            return "top", "bottom"

        return "right", "right"

    def get_diagram_extents(self) -> tuple[float, float]:
        """Get total diagram width and height.

        Returns:
            Tuple of (total_width, total_height) before scaling.
        """
        if not self.row_max_heights:
            return self.BASE_MARGIN * 2, self.BASE_MARGIN * 2

        max_col = max((col for col, _ in self.table_layout.values()), default=0)

        extent_x = (
            self.BASE_MARGIN
            + (max_col + 1) * self.BASE_CARD_WIDTH
            + max_col * self.BASE_H_GAP
        )
        extent_y = (
            self.BASE_MARGIN
            + sum(self.row_max_heights.values())
            + len(self.row_max_heights) * self.BASE_V_GAP
        )

        return extent_x, extent_y
