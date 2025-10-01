"""Progress note parsing helpers."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

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


def parse_progress_notes(tree: etree._ElementTree, ns: dict[str, str]) -> List[dict[str, Optional[str]]]:
    """Extract structured progress notes from CCD sections."""
    notes: List[dict[str, Optional[str]]] = []
    for section in tree.xpath(".//hl7:section", namespaces=ns):
        title_el = section.find("hl7:title", namespaces=ns)
        title = (title_el.text or "").strip().lower() if title_el is not None else ""
        if "progress note" not in title:
            continue

        for item in section.xpath("hl7:text/hl7:list/hl7:item", namespaces=ns):
            caption_el = item.find("hl7:caption", namespaces=ns)
            caption_text = None
            if caption_el is not None:
                caption_text = " ".join(caption_el.xpath("string()" ).split()) or None

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


def _parse_caption(caption: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
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
    parts: List[str] = []

    def walk(elem: etree._Element) -> None:
        text_value = elem.text or ""
        if text_value:
            parts.append(text_value)
        for child in elem:
            if _local_name(child) == "br":
                parts.append("\n")
            else:
                walk(child)
            tail_value = child.tail or ""
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
    tag = elem.tag
    if isinstance(tag, str) and "}" in tag:
        return tag.split("}", 1)[1]
    if isinstance(tag, str):
        return tag
    return ""
