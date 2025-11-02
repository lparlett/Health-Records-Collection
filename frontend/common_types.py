"""Shared type definitions for frontend diagram and schema components.

This module provides reusable dataclasses and type aliases used across multiple
frontend modules to eliminate duplication and ensure consistency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Type alias for diagram anchor positions
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
