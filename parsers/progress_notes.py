# Purpose: Parse progress note narratives from CCD documents.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Progress note parsing helpers."""

from __future__ import annotations

import re
from typing import Any, Optional, Sequence, cast

from lxml import etree

__all__ = ["parse_progress_notes"]

_TZ_OFFSETS = {
    "UTC": "+0000",
    "UT": "+0000",
    "GMT": "+0000",
    "EST": "-0500",
    "EDT": "-0400",
    "CST": "-0600",
    "CDT": "-0500",
    "MST": "-0700",
    "MDT": "-0600",
    "PST": "-0800",
    "PDT": "-0700",
    "AKST": "-0900",
    "AKDT": "-0800",
    "HST": "-1000",
}

_DATE_PATTERN = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})\s*([AP]M)", re.IGNORECASE)
_TZ_PATTERN = re.compile(r"\b([A-Z]{2,4})$")


def _iter_elements(value: object) -> list[etree._Element]:
    """Convert mixed XPath outputs into a list of XML elements."""
    elements: list[etree._Element] = []
    if isinstance(value, etree._Element):
        elements.append(value)
    elif isinstance(value, Sequence):
        for item in value:
            if isinstance(item, etree._Element):
                elements.append(item)
    return elements


def _normalize_text(value: object) -> str | None:
    """Return a trimmed string representation of XML or scalar data."""
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="ignore")
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    text = text.strip()
    return text or None


def parse_progress_notes(tree: etree._ElementTree, ns: dict[str, str]) -> list[dict[str, Optional[str]]]:
    """Extract structured progress notes from CCD sections.

    Args:
        tree: Root XML tree representing the CCD document.
        ns: Namespace dictionary used for XPath lookups.

    Returns:
        list[dict[str, Optional[str]]]: Normalised progress note entries.
    """
    notes: list[dict[str, Optional[str]]] = []
    section_nodes = cast(Sequence[Any], tree.xpath(".//hl7:section", namespaces=ns))
    for section in _iter_elements(section_nodes):
        title_el = section.find("hl7:title", namespaces=ns)
        title = (_normalize_text(title_el.text) or "").lower() if title_el is not None else ""
        if "progress note" not in title:
            continue

        item_nodes = section.xpath("hl7:text/hl7:list/hl7:item", namespaces=ns)
        for item in _iter_elements(item_nodes):
            caption_el = item.find("hl7:caption", namespaces=ns)
            caption_text = None
            if caption_el is not None:
                caption_text = _normalize_text(caption_el.xpath("string()"))

            provider_name, note_iso_dt, encounter_hint = _parse_caption(caption_text)

            content_el = item.find("hl7:content[@ID]", namespaces=ns)
            if content_el is None:
                content_el = item.find("hl7:content", namespaces=ns)
            if content_el is None:
                continue

            note_text = _text_with_breaks(content_el)
            if not note_text:
                continue

            notes.append(
                {
                    "title": caption_text,
                    "provider": provider_name,
                    "note_datetime": note_iso_dt,
                    "encounter_date": encounter_hint,
                    "text": note_text,
                    "source_id": content_el.get("ID"),
                }
            )
    return notes


def _parse_caption(caption: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse provider and timestamp information from a note caption."""
    if not caption:
        return None, None, None

    provider_part = caption
    meta_part = ""
    if " - " in caption:
        provider_part, meta_part = caption.rsplit(" - ", 1)
    provider_name = provider_part.strip() or None
    meta = meta_part.strip()

    if not meta:
        return provider_name, None, None

    tz_code: Optional[str] = None
    tz_match = _TZ_PATTERN.search(meta)
    if tz_match:
        candidate = tz_match.group(1).upper()
        if candidate in _TZ_OFFSETS:
            tz_code = candidate
            meta = meta[: tz_match.start()].strip()

    date_match = _DATE_PATTERN.search(meta)
    if not date_match:
        return provider_name, None, None

    month, day, year = map(int, date_match.groups())
    compact_date = f"{year:04d}{month:02d}{day:02d}"
    iso_date = f"{year:04d}-{month:02d}-{day:02d}"

    time_match = _TIME_PATTERN.search(meta)
    if not time_match:
        return provider_name, iso_date, compact_date

    hour, minute, am_pm = time_match.groups()
    hour_int = int(hour)
    minute_int = int(minute)
    if am_pm.upper() == "PM" and hour_int != 12:
        hour_int += 12
    if am_pm.upper() == "AM" and hour_int == 12:
        hour_int = 0

    offset = _TZ_OFFSETS.get(tz_code or "")
    encounter = f"{compact_date}{hour_int:02d}{minute_int:02d}00"
    if offset:
        encounter += offset

    iso_time = f"{hour_int:02d}:{minute_int:02d}:00"
    if offset:
        iso_offset = f"{offset[:3]}:{offset[3:]}"
        note_iso = f"{iso_date}T{iso_time}{iso_offset}"
    else:
        note_iso = f"{iso_date}T{iso_time}"

    return provider_name, note_iso, encounter


def _text_with_breaks(node: etree._Element) -> Optional[str]:
    """Traverse an HTML-ish node, preserving explicit line breaks."""
    parts: list[str] = []

    def walk(elem: etree._Element) -> None:
        text_value = _normalize_text(elem.text)
        if text_value:
            parts.append(text_value)
        for child in elem:
            if _local_name(child) == "br":
                parts.append("\n")
            else:
                walk(child)
            tail_value = _normalize_text(child.tail)
            if tail_value:
                parts.append(tail_value)

    walk(node)
    raw_text = "".join(parts)
    if not raw_text:
        return None

    normalized = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    # Trim leading and trailing blank lines while keeping interior spacing.
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    cleaned = "\n".join(lines).strip()
    return cleaned or None


def _local_name(elem: etree._Element) -> str:
    """Return the local tag name sans namespace."""
    tag = elem.tag
    if isinstance(tag, str) and "}" in tag:
        return tag.split("}", 1)[1]
    if isinstance(tag, str):
        return tag
    return ""
