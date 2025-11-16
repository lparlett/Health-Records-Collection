"""SVG diagram generation for database schema ER diagrams.

Purpose: Extract diagram building and SVG rendering logic from schema_components.py.
Author: Lauren Parlett
Date: 2025-11-01
Tests: Manual Streamlit validation; automated frontend coverage pending.
AI-assisted: Module generated with AI assistance.
"""

import html
from dataclasses import dataclass
from typing import Callable, Dict, Sequence

from health_records_collection.frontend.common_types import (
    Anchor,
    DiagramLayout,
    EdgeSpec,
)


@dataclass(frozen=True)
class PositionedNode:
    """Node with computed coordinates and dimensions (flattened for rendering)."""

    identifier: str
    title: str
    fields: tuple[str, ...]
    x: float
    y: float
    width: float
    height: float


@dataclass
class RelationshipLayout:
    """Layout context for relationship sections."""

    x: float
    width: float
    cursor: float
    top_margin: float


@dataclass
class CardMetrics:
    """Scaled dimensions for a rendered node card."""

    x: float
    y: float
    width: float
    height: float


@dataclass(slots=True)
class DiagramStyle:
    """Precomputed style values derived from zoom/text settings."""

    scale: float
    text_color: str
    title_size: float
    field_size: float
    label_size: float
    edge_color: str = "#5c7080"
    card_fill: str = "#f5f7fb"
    card_border: str = "#c3ccd6"

    @classmethod
    def from_zoom(cls, zoom: float, text_color: str) -> "DiagramStyle":
        """Construct a style instance from zoom and text color inputs."""
        scale = max(0.75, min(3.0, zoom))
        return cls(
            scale=scale,
            text_color=text_color,
            title_size=18 * scale,
            field_size=13 * scale,
            label_size=11 * scale,
        )


@dataclass(slots=True)
class AnchorRequest:
    """Parameters required to compute an anchor coordinate."""

    node_id: str
    anchor: Anchor
    slot: int
    total: int


class DiagramBuilder:
    """Generate SVG markup for database schema ER diagram."""

    def __init__(
        self,
        nodes: list[PositionedNode],
        edges: list[EdgeSpec],
        *,
        zoom: float = 1.0,
        text_color: str = "#202124",
        show_edges: bool = True,
        focus_table: str | None = None,
        layout: DiagramLayout | None = None,
    ) -> None:
        """Initialize builder with positioned nodes and edges.

        Args:
            nodes: List of positioned node specs with coordinates.
            edges: List of edge specs defining relationships.
            zoom: Zoom factor (0.75-3.0). Defaults to 1.0.
            text_color: Hex color for text. Defaults to "#202124".
        """
        self.nodes = nodes
        self.edges = edges
        self.style = DiagramStyle.from_zoom(zoom, text_color)
        self.show_edges = show_edges
        self.focus_table = focus_table
        self.layout = layout or DiagramLayout()

    @property
    def scale(self) -> float:
        """Return the scaling multiplier for layout measurements."""
        return self.style.scale

    @property
    def text_color(self) -> str:
        """Return the configured text color for rendered elements."""
        return self.style.text_color

    @property
    def title_size(self) -> float:
        """Return the computed font size for table titles."""
        return self.style.title_size

    @property
    def field_size(self) -> float:
        """Return the computed font size for field rows."""
        return self.style.field_size

    @property
    def label_size(self) -> float:
        """Return the computed font size for relationship labels."""
        return self.style.label_size

    @property
    def edge_color(self) -> str:
        """Return the stroke color used for relationship edges."""
        return self.style.edge_color

    @property
    def card_fill(self) -> str:
        """Return the fill color used for node cards."""
        return self.style.card_fill

    @property
    def card_border(self) -> str:
        """Return the stroke color for the card outline."""
        return self.style.card_border

    def build(self) -> tuple[str, int]:
        """Generate SVG markup and recommended container height.

        Returns:
            Tuple of (html_wrapped_svg, recommended_height_px).
        """
        svg_lines = self._build_svg_header()
        svg_lines.extend(self._build_legend())
        if self.show_edges:
            svg_lines.extend(self._build_edges())
        svg_lines.extend(self._build_nodes())
        svg_lines.append("</svg></div>")

        svg_markup = "".join(svg_lines)
        diagram_height = self._compute_diagram_height()

        return svg_markup, int(diagram_height + 40)

    def _build_svg_header(self) -> list[str]:
        """Generate SVG header with defs and styling."""
        extent_x = (
            max((node.x + node.width) for node in self.nodes) if self.nodes else 0.0
        )
        extent_y = (
            max((node.y + node.height) for node in self.nodes) if self.nodes else 0.0
        )
        diagram_width = int((extent_x + self.layout.margin) * self.scale)
        diagram_height = int((extent_y + self.layout.margin) * self.scale)

        return [
            (
                f'<div style="width:100%; overflow:auto; background-color:#ffffff;">'
                f'<svg width="{diagram_width}" height="{diagram_height}" '
                f'viewBox="0 0 {diagram_width} {diagram_height}" '
                'xmlns="http://www.w3.org/2000/svg" role="img" '
                'aria-label="Health Records schema diagram">'
            ),
            "<defs>",
            (
                f'<marker id="arrowhead" markerWidth="{10 * self.scale}" '
                f'markerHeight="{10 * self.scale}" '
                f'refX="{10 * self.scale}" refY="{5 * self.scale}" orient="auto">'
                f'<path d="M0,0 L0,{10 * self.scale} '
                f'L{10 * self.scale},{5 * self.scale} Z" '
                f'fill="{self.edge_color}" />'
                "</marker>"
            ),
            "</defs>",
        ]

    def _build_legend(self) -> list[str]:
        """Generate legend box for column attribute abbreviations."""
        legend_entries = [
            ("AUTO", "Auto-incrementing"),
            ("DEF", "Default value"),
            ("INT", "Integer"),
            ("NN", "Not Null"),
            ("PK", "Primary Key"),
        ]

        legend_padding = 10.0 * self.scale
        legend_line_height = (self.label_size + 4.0) * self.scale
        legend_header_height = (self.label_size + 6.0) * self.scale
        legend_width = 220.0 * self.scale
        legend_height = (
            legend_padding * 2
            + legend_header_height
            + len(legend_entries) * legend_line_height
        )
        legend_x = 16.0 * self.scale
        legend_y = 16.0 * self.scale

        svg_lines = [
            (
                f'<rect x="{legend_x:.1f}" y="{legend_y:.1f}" '
                f'width="{legend_width:.1f}" height="{legend_height:.1f}" '
                'rx="12" ry="12" fill="rgba(255,255,255,0.86)" '
                'stroke="#c3ccd6" stroke-width="1.0" />'
            ),
        ]

        legend_header_y = legend_y + legend_padding + legend_header_height * 0.8
        svg_lines.append(
            (
                f'<text x="{legend_x + legend_width / 2:.1f}" '
                f'y="{legend_header_y:.1f}" '
                f'fill="{self.edge_color}" font-size="{self.label_size:.1f}" '
                'font-family="Helvetica" text-anchor="middle" font-weight="600">'
                "Legend"
                "</text>"
            )
        )

        for idx, (abbr, meaning) in enumerate(legend_entries, start=1):
            entry_y = legend_header_y + idx * legend_line_height
            svg_lines.append(
                (
                    f'<text x="{legend_x + legend_padding:.1f}" y="{entry_y:.1f}" '
                    f'fill="{self.edge_color}" font-size="{self.label_size:.1f}" '
                    'font-family="Helvetica" text-anchor="start">'
                    f"{html.escape(abbr)} = {html.escape(meaning)}"
                    "</text>"
                )
            )

        return svg_lines

    def _build_edges(self) -> list[str]:
        """Generate SVG paths for relationship edges."""
        svg_lines: list[str] = []
        node_lookup = self._node_lookup()
        filtered_edges = self._edges_for_paths()
        edges_by_pair = self._edges_grouped_by_pair(filtered_edges)
        source_slots, target_slots = self._anchor_slot_maps(filtered_edges)

        for edges_for_pair in edges_by_pair.values():
            for edge in edges_for_pair:
                start, end, orientation = self._edge_segment(
                    edge, node_lookup, source_slots, target_slots
                )
                path = self._curve_path(start, end, orientation=orientation)
                svg_lines.append(
                    (
                        f'<path d="{path}" '
                        f'stroke="{self.edge_color}" '
                        f'stroke-opacity="{self._edge_opacity(edge):.2f}" '
                        f'stroke-width="{1.2 * self.scale:.2f}" '
                        'fill="none" marker-end="url(#arrowhead)" />'
                    )
                )

        return svg_lines

    def _edges_for_paths(self) -> list[EdgeSpec]:
        """Return edges included when rendering connector paths."""
        if not self.focus_table:
            return self.edges
        return [
            edge
            for edge in self.edges
            if self.focus_table in (edge.source, edge.target)
        ]

    def _node_lookup(self) -> Dict[str, PositionedNode]:
        """Return dictionary of nodes keyed by identifier."""
        return {node.identifier: node for node in self.nodes}

    def _edges_grouped_by_pair(
        self, edges: list[EdgeSpec]
    ) -> Dict[tuple[str, str], list[EdgeSpec]]:
        """Group edges by their (source, target) pair."""
        grouped: Dict[tuple[str, str], list[EdgeSpec]] = {}
        for edge in edges:
            grouped.setdefault((edge.source, edge.target), []).append(edge)
        return grouped

    def _anchor_slot_maps(self, edges: list[EdgeSpec]) -> tuple[
        Dict[str, Dict[Anchor, list[EdgeSpec]]],
        Dict[str, Dict[Anchor, list[EdgeSpec]]],
    ]:
        """Return mappings of edges per anchor for parallel routing."""
        source_slots: Dict[str, Dict[Anchor, list[EdgeSpec]]] = {}
        target_slots: Dict[str, Dict[Anchor, list[EdgeSpec]]] = {}
        for edge in edges:
            source_slots.setdefault(edge.source, {}).setdefault(
                edge.source_anchor, []
            ).append(edge)
            target_slots.setdefault(edge.target, {}).setdefault(
                edge.target_anchor, []
            ).append(edge)
        return source_slots, target_slots

    def _edge_segment(
        self,
        edge: EdgeSpec,
        node_lookup: Dict[str, PositionedNode],
        source_slots: Dict[str, Dict[Anchor, list[EdgeSpec]]],
        target_slots: Dict[str, Dict[Anchor, list[EdgeSpec]]],
    ) -> tuple[tuple[float, float], tuple[float, float], str]:
        """Return start/end coordinates and orientation for an edge."""
        source_edges = source_slots.get(edge.source, {}).get(edge.source_anchor, [edge])
        target_edges = target_slots.get(edge.target, {}).get(edge.target_anchor, [edge])
        start = self._anchor_point(
            node_lookup,
            AnchorRequest(
                node_id=edge.source,
                anchor=edge.source_anchor,
                slot=source_edges.index(edge),
                total=len(source_edges),
            ),
        )
        end = self._anchor_point(
            node_lookup,
            AnchorRequest(
                node_id=edge.target,
                anchor=edge.target_anchor,
                slot=target_edges.index(edge),
                total=len(target_edges),
            ),
        )
        orientation = self._edge_orientation(edge)
        return start, end, orientation

    @staticmethod
    def _edge_orientation(edge: EdgeSpec) -> str:
        """Return routing orientation based on anchor positions."""
        if edge.source_anchor in {"left", "right"} and edge.target_anchor in {
            "left",
            "right",
        }:
            return "horizontal"
        if edge.source_anchor in {"top", "bottom"} and edge.target_anchor in {
            "top",
            "bottom",
        }:
            return "vertical"
        return "diagonal"

    def _build_nodes(self) -> list[str]:
        """Generate SVG rectangles and text for all nodes."""
        svg_lines: list[str] = []
        outgoing_edges, incoming_edges = self._group_edges()

        for node in self.nodes:
            svg_lines.extend(
                self._render_node(
                    node,
                    outgoing_edges.get(node.identifier, []),
                    incoming_edges.get(node.identifier, []),
                )
            )

        return svg_lines

    def _group_edges(
        self,
    ) -> tuple[Dict[str, list[EdgeSpec]], Dict[str, list[EdgeSpec]]]:
        """Return mappings of outgoing and incoming edges keyed by node id."""
        outgoing_edges: Dict[str, list[EdgeSpec]] = {}
        incoming_edges: Dict[str, list[EdgeSpec]] = {}
        for edge in self.edges:
            outgoing_edges.setdefault(edge.source, []).append(edge)
            incoming_edges.setdefault(edge.target, []).append(edge)
        return outgoing_edges, incoming_edges

    def _render_node(
        self,
        node: PositionedNode,
        outgoing: Sequence[EdgeSpec],
        incoming: Sequence[EdgeSpec],
    ) -> list[str]:
        """Return SVG fragments for a single positioned node."""
        node_lines: list[str] = []
        x = node.x * self.scale
        y = node.y * self.scale
        width = node.width * self.scale
        height = node.height * self.scale
        node_opacity = self._node_opacity(node.identifier)
        metrics = CardMetrics(x=x, y=y, width=width, height=height)

        node_lines.append(self._card_rect(metrics, node_opacity))
        title_y = y + 28 * self.scale
        node_lines.append(self._card_title(node.title, metrics, title_y, node_opacity))
        field_stack_height = self._append_fields(
            node_lines,
            node,
            metrics,
            title_y=title_y,
            text_opacity=node_opacity,
        )

        cursor = y + field_stack_height * self.scale
        rel_lines, cursor = self._render_relationship_section(
            title="References",
            edges=outgoing,
            layout=RelationshipLayout(
                x=x,
                width=width,
                cursor=cursor,
                top_margin=self.layout.relationship_section_margin,
            ),
            formatter=self._format_outgoing_label,
            text_opacity=node_opacity,
        )
        node_lines.extend(rel_lines)

        gap = (
            self.layout.relationship_section_gap
            if outgoing
            else self.layout.relationship_section_margin
        )
        rel_lines, _ = self._render_relationship_section(
            title="Referenced by",
            edges=incoming,
            layout=RelationshipLayout(x=x, width=width, cursor=cursor, top_margin=gap),
            formatter=self._format_incoming_label,
            text_opacity=node_opacity,
        )
        node_lines.extend(rel_lines)

        return node_lines

    def _card_rect(self, metrics: CardMetrics, opacity: float) -> str:
        """Return SVG rect string for the node card."""
        return (
            f'<rect x="{metrics.x:.1f}" y="{metrics.y:.1f}" '
            f'width="{metrics.width:.1f}" height="{metrics.height:.1f}" '
            f'rx="{12 * self.scale:.1f}" ry="{12 * self.scale:.1f}" '
            f'fill="{self.card_fill}" fill-opacity="{opacity:.2f}" '
            f'stroke="{self.card_border}" stroke-opacity="{max(opacity, 0.45):.2f}" '
            f'stroke-width="{1.2 * self.scale:.2f}" />'
        )

    def _card_title(
        self, title: str, metrics: CardMetrics, title_y: float, text_opacity: float
    ) -> str:
        """Return SVG text element for a card title."""
        return (
            f'<text x="{metrics.x + metrics.width / 2:.1f}" y="{title_y:.1f}" '
            f'fill="{self.text_color}" font-size="{self.title_size:.1f}" '
            f'opacity="{text_opacity:.2f}" '
            'font-family="Helvetica" font-weight="600" text-anchor="middle">'
            f"{html.escape(title)}"
            "</text>"
        )

    def _append_fields(
        self,
        node_lines: list[str],
        node: PositionedNode,
        metrics: CardMetrics,
        *,
        title_y: float,
        text_opacity: float,
    ) -> float:
        """Append field lines to node_lines and return base block height."""
        for idx, field in enumerate(node.fields, start=1):
            line_y = (
                title_y
                + (self.layout.header_block_height - 8.0) * self.scale
                + (idx - 1) * self.layout.field_line_spacing * self.scale
            )
            if line_y + 16 * self.scale > metrics.y + metrics.height:
                break
            node_lines.append(
                (
                    f'<text x="{metrics.x + metrics.width / 2:.1f}" y="{line_y:.1f}" '
                    f'fill="{self.text_color}" font-size="{self.field_size:.1f}" '
                    f'opacity="{text_opacity:.2f}" '
                    'font-family="Helvetica" text-anchor="middle">'
                    f"{html.escape(field)}"
                    "</text>"
                )
            )
        return (
            self.layout.header_block_height
            + len(node.fields) * self.layout.field_line_spacing
        )

    def _render_relationship_section(
        self,
        *,
        title: str,
        edges: Sequence[EdgeSpec],
        layout: RelationshipLayout,
        formatter: Callable[[EdgeSpec], str],
        text_opacity: float,
    ) -> tuple[list[str], float]:
        """Render a relationship subsection and return lines plus updated cursor."""
        if not edges:
            return [], layout.cursor

        lines: list[str] = []
        cursor = layout.cursor + layout.top_margin * self.scale
        header_y = cursor + self.layout.relationship_header_offset * self.scale
        lines.append(
            (
                f'<text x="{layout.x + layout.width / 2:.1f}" y="{header_y:.1f}" '
                f'fill="{self.edge_color}" font-size="{self.label_size:.1f}" '
                f'opacity="{text_opacity:.2f}" '
                'font-family="Helvetica" text-anchor="middle" font-weight="600">'
                f"{title}"
                "</text>"
            )
        )
        for rel_idx, edge in enumerate(edges, start=1):
            rel_y = header_y + rel_idx * (
                self.layout.relationship_line_spacing * self.scale
            )
            lines.append(
                (
                    f'<text x="{layout.x + 12 * self.scale:.1f}" y="{rel_y:.1f}" '
                    f'fill="{self.edge_color}" '
                    f'font-size="{self.label_size:.1f}" '
                    f'opacity="{text_opacity:.2f}" '
                    'font-family="Helvetica" text-anchor="start">'
                    f"{formatter(edge)}"
                    "</text>"
                )
            )

        cursor = (
            header_y
            + len(edges) * (self.layout.relationship_line_spacing * self.scale)
            + self.layout.relationship_footer_padding * self.scale
        )
        return lines, cursor

    @staticmethod
    def _format_outgoing_label(edge: EdgeSpec) -> str:
        """Return formatted text for outgoing relationships."""
        return f"- {html.escape(edge.label)} \u2192 {html.escape(edge.target)}"

    @staticmethod
    def _format_incoming_label(edge: EdgeSpec) -> str:
        """Return formatted text for incoming relationships."""
        return f"- {html.escape(edge.source)} \u2190 {html.escape(edge.label)}"

    def _anchor_point(
        self,
        node_lookup: Dict[str, PositionedNode],
        request: AnchorRequest,
    ) -> tuple[float, float]:
        """Compute anchor point coordinates on node edge."""
        node = node_lookup[request.node_id]
        x = node.x * self.scale
        y = node.y * self.scale
        width = node.width * self.scale
        height = node.height * self.scale
        total = max(request.total, 1)
        offset = request.slot + 1

        if request.anchor == "left":
            step = height / (total + 1)
            return x, y + step * offset
        if request.anchor == "right":
            step = height / (total + 1)
            return x + width, y + step * offset
        if request.anchor == "top":
            step = width / (total + 1)
            return x + step * offset, y
        if request.anchor == "bottom":
            step = width / (total + 1)
            return x + step * offset, y + height

        return x + width / 2, y + height / 2

    def _curve_path(
        self, start: tuple[float, float], end: tuple[float, float], *, orientation: str
    ) -> str:
        """Generate SVG Bezier curve path for edge routing."""
        x1, y1 = start
        x2, y2 = end
        if orientation == "horizontal":
            offset = max(60.0 * self.scale, abs(x2 - x1) / 2)
            if x2 < x1:
                offset = -offset
            return (
                f"M{x1:.1f},{y1:.1f} "
                f"C{x1 + offset:.1f},{y1:.1f} {x2 - offset:.1f},"
                f"{y2:.1f} {x2:.1f},{y2:.1f}"
            )

        if orientation == "vertical":
            offset = max(40.0 * self.scale, abs(y2 - y1) / 2)
            if y2 < y1:
                offset = -offset
            return (
                f"M{x1:.1f},{y1:.1f} "
                f"C{x1:.1f},{y1 + offset:.1f} {x2:.1f},"
                f"{y2 - offset:.1f} {x2:.1f},{y2:.1f}"
            )

        # Diagonal or mixed orientation
        h_offset = max(40.0 * self.scale, abs(x2 - x1) / 2)
        v_offset = max(40.0 * self.scale, abs(y2 - y1) / 2)
        if x2 < x1:
            h_offset = -h_offset
        if y2 < y1:
            v_offset = -v_offset
        return (
            f"M{x1:.1f},{y1:.1f} "
            f"C{x1 + h_offset:.1f},{y1:.1f} {x2:.1f},"
            f"{y2 - v_offset:.1f} {x2:.1f},{y2:.1f}"
        )

    def _compute_diagram_height(self) -> float:
        """Compute the total SVG diagram height based on nodes."""
        if not self.nodes:
            return self.layout.margin * 2

        extent_y = max((node.y + node.height) for node in self.nodes)
        return (extent_y + self.layout.margin) * self.scale

    def _node_opacity(self, node_id: str) -> float:
        """Return opacity for card/text based on focus selection."""
        if not self.focus_table:
            return 1.0
        return 1.0 if node_id == self.focus_table else 0.35

    def _edge_opacity(self, edge: EdgeSpec) -> float:
        """Return opacity for connector lines."""
        if not self.focus_table:
            return 1.0
        return 1.0 if self.focus_table in (edge.source, edge.target) else 0.15
