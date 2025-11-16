"""Shared type definitions for frontend diagram and schema components.

This module provides reusable dataclasses and type aliases used across multiple
frontend modules to eliminate duplication and ensure consistency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Type alias for diagram anchor positions
Anchor = Literal["left", "right", "top", "bottom"]


# pylint: disable=too-many-instance-attributes
@dataclass(frozen=True)
class DiagramLayout:
    """Shared layout metrics for schema diagrams."""

    card_width: float = 250.0
    card_height: float = 250.0
    horizontal_gap: float = 80.0
    vertical_gap: float = 60.0
    margin: float = 60.0
    header_block_height: float = 36.0
    field_line_spacing: float = 16.0
    field_bottom_margin: float = 12.0
    relationship_section_margin: float = 8.0
    relationship_header_offset: float = 20.0
    relationship_line_spacing: float = 12.0
    relationship_footer_padding: float = 8.0
    relationship_section_gap: float = 12.0


@dataclass(frozen=True)
class NodeSpec:
    """Static definition for a table node in the ER diagram."""

    identifier: str
    title: str
    fields: tuple[str, ...]
    column: int
    row: int
    x: float = 0.0
    y: float = 0.0
    width: float = 250.0
    height: float = 250.0


@dataclass
class PositionedNode:
    """Node with computed coordinates and dimensions (schema layout wrapper).

    This wraps a NodeSpec with computed layout coordinates.
    """

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
class RelationshipSummary:
    """Outgoing and incoming relationships associated with a node."""

    outgoing: tuple[EdgeSpec, ...]
    incoming: tuple[EdgeSpec, ...]
    base_height: float
