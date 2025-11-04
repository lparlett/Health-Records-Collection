# Purpose: Parse progress note narratives from CCD documents.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Progress note parsing helpers."""
from __future__ import annotations

import re
from typing import Optional

from .common import iter_elements, normalize_whitespace
from .xml_types import ElementType, ElementTreeType

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


def parse_progress_notes(
    tree: ElementTreeType, ns: dict[str, str]
) -> list[dict[str, Optional[str]]]:
    """Extract structured progress notes from CCD sections.

    Args:
        tree: Root XML tree representing the CCD document.
        ns: Namespace dictionary used for XPath lookups.

    Returns:
        list[dict[str, Optional[str]]]: Normalised progress note entries.
    """
    root = tree.getroot()
    notes: list[dict[str, Optional[str]]] = []
    section_nodes = root.xpath(".//hl7:section", namespaces=ns)
    for section in iter_elements(section_nodes):
        title_el = section.find("hl7:title", namespaces=ns)
        title = (
            (normalize_whitespace(title_el.text) or "").lower()
            if title_el is not None
            else ""
        )
        if "progress note" not in title:
            continue

        item_nodes = section.xpath("hl7:text/hl7:list/hl7:item", namespaces=ns)
        for item in iter_elements(item_nodes):
            caption_el = item.find("hl7:caption", namespaces=ns)
            caption_text = None
            if caption_el is not None:
                caption_text = normalize_whitespace(caption_el.xpath("string()"))

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


def _split_caption_parts(caption: str) -> tuple[Optional[str], str]:
    """Split the caption into provider and metadata segments."""
    if " - " in caption:
        provider_part, meta_part = caption.rsplit(" - ", 1)
    else:
        provider_part, meta_part = caption, ""
    provider_name = provider_part.strip() or None
    return provider_name, meta_part.strip()


def _extract_timezone(meta: str) -> tuple[str, Optional[str]]:
    """Extract a timezone code from the metadata, returning remaining text."""
    tz_match = _TZ_PATTERN.search(meta)
    if not tz_match:
        return meta, None
    candidate = tz_match.group(1).upper()
    if candidate in _TZ_OFFSETS:
        trimmed = meta[: tz_match.start()].strip()
        return trimmed, candidate
    return meta, None


def _parse_date(meta: str) -> tuple[Optional[str], Optional[str]]:
    """Parse date components from metadata."""
    date_match = _DATE_PATTERN.search(meta)
    if not date_match:
        return None, None
    month, day, year = map(int, date_match.groups())
    compact_date = f"{year:04d}{month:02d}{day:02d}"
    iso_date = f"{year:04d}-{month:02d}-{day:02d}"
    return iso_date, compact_date


def _parse_time_component(
    meta: str,
    tz_code: Optional[str],
    *,
    iso_date: str,
    compact_date: str,
) -> tuple[str, Optional[str]]:
    """Return ISO timestamp and encounter identifier from metadata."""
    time_match = _TIME_PATTERN.search(meta)
    if not time_match:
        return iso_date, compact_date

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

    return note_iso, encounter


def _parse_caption(
    caption: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse provider and timestamp information from a note caption."""
    if not caption:
        return None, None, None

    provider_name, meta = _split_caption_parts(caption)

    if not meta:
        return provider_name, None, None

    meta_without_tz, tz_code = _extract_timezone(meta)
    iso_date, compact_date = _parse_date(meta_without_tz)
    if iso_date is None or compact_date is None:
        return provider_name, None, None

    note_iso, encounter = _parse_time_component(
        meta_without_tz,
        tz_code,
        iso_date=iso_date,
        compact_date=compact_date,
    )
    return provider_name, note_iso, encounter


def _text_with_breaks(node: ElementType) -> Optional[str]:
    """Traverse an HTML-ish node, preserving explicit line breaks."""
    parts: list[str] = []

    def walk(elem: ElementType) -> None:
        text_value = normalize_whitespace(elem.text)
        if text_value:
            parts.append(text_value)
        for child in elem:
            if _local_name(child) == "br":
                parts.append("\n")
            else:
                walk(child)
            tail_value = normalize_whitespace(child.tail)
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


def _local_name(elem: ElementType) -> str:
    """Return the local tag name sans namespace."""
    tag = elem.tag
    if isinstance(tag, str) and "}" in tag:
        return tag.split("}", 1)[1]
    if isinstance(tag, str):
        return tag
    return ""
