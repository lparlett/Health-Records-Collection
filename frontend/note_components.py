from __future__ import annotations

# Purpose: Streamlit helpers for rendering clinical progress notes.
# Author: Codex + Lauren
# Date: 2025-10-21
# Tests: Manual Streamlit verification pending.
# AI-assisted: This module was created with AI assistance.

import html
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional, Tuple

import streamlit as st

SECTION_TITLES: set[str] = {
    "SUBJECTIVE",
    "OBJECTIVE",
    "ASSESSMENT",
    "PLAN",
    "ASSESSMENT AND PLAN",
    "ASSESSMENT/PLAN",
    "HISTORY OF PRESENT ILLNESS",
    "PHYSICAL EXAM",
    "PHYSICAL EXAMINATION",
    "REVIEW OF SYSTEMS",
    "MEDICATIONS",
    "CURRENT MEDICATIONS",
    "CURRENT OUTPATIENT MEDICATIONS",
    "MEDICATIONS REVIEWED",
    "ALLERGIES",
    "PAST MEDICAL HISTORY",
    "PAST SURGICAL HISTORY",
    "OCCUPATIONAL HISTORY",
    "SOCIOECONOMIC HISTORY",
    "FAMILY HISTORY",
    "SOCIAL HISTORY",
    "LABORATORY DATA",
    "DIAGNOSTIC STUDIES",
    "IMPRESSION",
    "DISPOSITION",
    "FOLLOW UP",
    "FOLLOW-UP",
    "PROCEDURES",
    "INSTRUCTIONS",
    "LABS/TESTS/IMAGES",
    "LABS/TESTS",
    "HPI",
    "ROS",
    "CC",
    "CHIEF COMPLAINT",
}


@lru_cache(maxsize=1)
def _load_progress_note_css() -> str:
    """Return the static CSS for progress note rendering."""
    css_path = Path(__file__).resolve().parent / "static" / "progress_notes.css"
    return css_path.read_text(encoding="utf-8")

def _load_progress_note_color_css() -> str:
    """Return the static CSS for progress note rendering."""
    colors_css_path = Path(__file__).resolve().parent / "static" / "colors.css"
    return colors_css_path.read_text(encoding="utf-8")

def _normalize_heading_candidate(text: str) -> str:
    stripped = text.strip()
    stripped = re.sub(r"^[\-\*\u2022\uFFFD•]+\s*", "", stripped)
    stripped = stripped.rstrip(":").strip()
    return re.sub(r"\s+", " ", stripped).upper()

def _looks_like_section_heading(line: str) -> bool:
    """Return True when a line resembles an uppercase section heading."""
    stripped = line.strip()
    if len(stripped) < 3:
        return False
    normalized = _normalize_heading_candidate(stripped)
    if not normalized:
        return False
    if normalized in SECTION_TITLES:
        return True
    if any(char.isdigit() for char in normalized):
        return False
    letters = [char for char in stripped if char.isalpha()]
    if not letters:
        return False
    return all(char.isupper() for char in letters)


def _format_paragraph_body(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(
        r"&lt;br\s*/?&gt;",
        "<br />",
        escaped,
        flags=re.IGNORECASE,
    )
    return escaped.replace("\n", "<br />")


def _extract_heading(raw_line: str) -> tuple[Optional[str], Optional[str]]:
    stripped = raw_line.strip()
    if not stripped:
        return None, None
    if _looks_like_section_heading(stripped):
        return stripped, None
    for delimiter in (":", "-"):
        if delimiter in stripped:
            before, after = stripped.split(delimiter, 1)
            if _looks_like_section_heading(before):
                heading_text = before.strip()
                if delimiter == ":":
                    heading_text = f"{heading_text}:"
                remainder = after.strip()
                return heading_text, remainder or None
    return None, None


def _build_progress_note_html(note_text: Optional[str], container_id: str) -> str:
    """Transform raw note text into paragraph elements with section detection."""
    if not note_text:
        return f'<div id="{container_id}" class="progress-note"><p>No text provided.</p></div>'

    cleaned = note_text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(
        r"(?:<br\s*/?>\s*){2,}",
        "\n\n",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    paragraphs = [
        segment.strip()
        for segment in re.split(r"\n{2,}", cleaned)
        if segment.strip()
    ]

    html_lines: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        body_buffer: list[str] = []
        lines = paragraph.split("\n")
        for raw_line in lines:
            heading_text, remainder_line = _extract_heading(raw_line)
            if heading_text:
                if body_buffer:
                    body_text = "\n".join(body_buffer).strip("\n")
                    if body_text.strip():
                        html_lines.append(
                            f"<p>{_format_paragraph_body(body_text)}</p>"
                        )
                    body_buffer.clear()
                html_lines.append(
                    f'<p class="progress-note-section">{html.escape(heading_text)}</p>'
                )
                body_buffer = []
                if remainder_line:
                    body_buffer.append(remainder_line)
            else:
                body_buffer.append(raw_line)

        if body_buffer:
            body_text = "\n".join(body_buffer).strip("\n")
            if body_text.strip():
                html_lines.append(f"<p>{_format_paragraph_body(body_text)}</p>")

    if not html_lines:
        html_lines.append("<p>No text provided.</p>")

    inner_html = "\n".join(html_lines)
    return f'<div id="{container_id}" class="progress-note">\n{inner_html}\n</div>'


def render_progress_notes(
    notes: list[dict[str, Any]],
    *,
    format_datetime: Callable[..., str],
) -> None:
    """Render a collection of progress notes with expandable sections."""
    css_flag = "progress-note-css-loaded"
    if not st.session_state.get(css_flag):
        try:
            color_css_rules = _load_progress_note_color_css()
            css_rules = _load_progress_note_css()
            st.markdown(f"<style>{color_css_rules}{css_rules}</style>", unsafe_allow_html=True)
        except OSError:
            st.warning("Progress note styles could not be loaded.")
        else:
            st.session_state[css_flag] = True

    st.subheader("Progress Notes")
    if not notes:
        st.info("No progress notes recorded.")
        return

    for idx, note in enumerate(notes):
        title = note.get("note_title") or f"Progress Note #{idx + 1}"
        timestamp = format_datetime(note.get("note_datetime"), show_time=True)
        with st.expander(f"{title} | {timestamp}"):
            container_id = f"progress-note-{idx + 1}"
            note_html = _build_progress_note_html(note.get("note_text"), container_id)
            st.markdown(note_html, unsafe_allow_html=True)
            source_id = note.get("source_note_id")
            if source_id:
                st.caption(f"Source ID: {source_id}")
