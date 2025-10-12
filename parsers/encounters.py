from __future__ import annotations

# Purpose: Parse encounter sections from CCD documents into structured records.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Encounter parsing helpers for CCD ingestion."""

from collections.abc import Iterable
from typing import Any, Sequence, cast

from lxml import etree

from .common import extract_provider_name, get_text_by_id

EncounterEntry = dict[str, Any]

REASON_FOR_VISIT_CODES: set[str] = {
    "29299-5",  # Reason for visit Narrative
    "46241-6",  # Reason for referral
    "78018-7",  # Reason for encounter
}


def _join_clean(parts: Iterable[str | None]) -> str | None:
    """Join non-empty strings with a delimiter after trimming whitespace."""
    cleaned_parts: list[str] = []
    for part in parts:
        if not part:
            continue
        candidate = part.strip()
        if candidate:
            cleaned_parts.append(candidate)
    if not cleaned_parts:
        return None
    return " | ".join(cleaned_parts)


def _extract_time_range(
    node: etree._Element | None,
    ns: dict[str, str],
) -> tuple[str | None, str | None]:
    """Extract start/end timestamps from an HL7 effectiveTime element."""
    start: str | None = None
    end: str | None = None
    if node is None:
        return start, end

    value = node.get("value")
    if value:
        return value, value

    low = node.find("hl7:low", namespaces=ns)
    high = node.find("hl7:high", namespaces=ns)
    if low is not None and low.get("value"):
        start = low.get("value")
    if high is not None and high.get("value"):
        end = high.get("value")
    if end is None and start is not None:
        end = start
    return start, end


def _normalize_reason_text(value: str | None) -> str | None:
    """Collapse whitespace and return a consistent reason-for-visit string."""
    if not value:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _ensure_element_list(value: object) -> list[etree._Element]:
    """Coerce XML nodes returned by XPath into a list of elements."""
    elements: list[etree._Element] = []
    if isinstance(value, etree._Element):
        elements.append(value)
    elif isinstance(value, Iterable):
        for node in value:
            if isinstance(node, etree._Element):
                elements.append(node)
    return elements


def _coerce_text(value: object) -> str | None:
    """Convert mixed XPath results into a trimmed string."""
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
    return []


def _extract_reason_for_visit(tree: etree._ElementTree, ns: dict[str, str]) -> str | None:
    """Pull narrative reason-for-visit text from applicable sections."""
    reasons: list[str] = []
    seen: set[str] = set()
    section_nodes = cast(Sequence[Any], tree.xpath(".//hl7:section", namespaces=ns))
    for section in _ensure_element_list(section_nodes):
        code_el = section.find("hl7:code", namespaces=ns)
        code_val = code_el.get("code") if code_el is not None else None
        title_el = section.find("hl7:title", namespaces=ns)
        title_text = _coerce_text(title_el.xpath("string()") if title_el is not None else None)
        title_norm = (_normalize_reason_text(title_text) or "").lower()
        if code_val not in REASON_FOR_VISIT_CODES and not (
            "reason" in title_norm
            and ("visit" in title_norm or "encounter" in title_norm or "referral" in title_norm)
        ):
            continue

        text_el = section.find("hl7:text", namespaces=ns)
        if text_el is not None:
            fragments = cast(Sequence[Any], text_el.xpath(".//text()"))
            added_direct = False
            for fragment in fragments:
                narrative = _normalize_reason_text(_coerce_text(fragment))
                if narrative and narrative not in seen:
                    seen.add(narrative)
                    reasons.append(narrative)
                    added_direct = True
            if not added_direct:
                narrative = _normalize_reason_text(_coerce_text(text_el.xpath("string()")))
                if narrative and narrative not in seen:
                    seen.add(narrative)
                    reasons.append(narrative)

        reference_nodes = cast(
            Sequence[Any],
            section.xpath(".//hl7:reference", namespaces=ns),
        )
        for ref in _ensure_element_list(reference_nodes):
            ref_value = ref.get("value")
            if not ref_value:
                continue
            resolved = _normalize_reason_text(get_text_by_id(tree, ns, ref_value))
            if resolved and resolved not in seen:
                seen.add(resolved)
                reasons.append(resolved)

        text_nodes = cast(
            Sequence[Any],
            section.xpath(".//hl7:act/hl7:text | .//hl7:observation/hl7:text", namespaces=ns),
        )
        for node in _ensure_element_list(text_nodes):
            candidate = _normalize_reason_text(_coerce_text(node.xpath("string()")))
            if candidate and candidate not in seen:
                seen.add(candidate)
                reasons.append(candidate)

    if not reasons:
        return None
    return "; ".join(reasons)


def parse_encounters(tree: etree._ElementTree, ns: dict[str, str]) -> list[EncounterEntry]:
    """Parse encounters documented within a CCD.

    Args:
        tree: Root XML tree for a CCD document.
        ns: Namespace dictionary used for XPath lookups.

    Returns:
        list[EncounterEntry]: Encounter dictionaries ready for persistence.
    """
    reason_for_visit = _extract_reason_for_visit(tree, ns)
    encounters: list[EncounterEntry] = []

    encounter_nodes = cast(Sequence[Any], tree.xpath(".//hl7:encounter", namespaces=ns))
    for enc in _ensure_element_list(encounter_nodes):
        code_el = enc.find("hl7:code", namespaces=ns)
        encounter_code = code_el.get("code") if code_el is not None else None
        encounter_type: str | None = None
        if code_el is not None:
            encounter_type = code_el.get("displayName")
            if not encounter_type:
                ref = code_el.find("hl7:originalText/hl7:reference", namespaces=ns)
                if ref is not None and ref.get("value"):
                    encounter_type = get_text_by_id(tree, ns, ref.get("value"))
            if not encounter_type:
                translation = code_el.find("hl7:translation[@displayName]", namespaces=ns)
                if translation is not None:
                    encounter_type = translation.get("displayName")
        if not encounter_type and encounter_code:
            encounter_type = encounter_code

        text_ref = enc.find("hl7:text/hl7:reference", namespaces=ns)
        description = None
        if text_ref is not None and text_ref.get("value"):
            description = get_text_by_id(tree, ns, text_ref.get("value"))

        status_el = enc.find("hl7:statusCode", namespaces=ns)
        status = status_el.get("code") if status_el is not None else None
        mood = enc.get("moodCode")

        start, end = _extract_time_range(enc.find("hl7:effectiveTime", namespaces=ns), ns)

        provider_name = extract_provider_name(
            enc,
            "hl7:performer/hl7:assignedEntity/hl7:assignedPerson/hl7:name",
            "hl7:performer/hl7:assignedEntity/hl7:representedOrganization/hl7:name",
            ns,
        )

        location_name = None
        location_el = enc.find(
            "hl7:participant[@typeCode='LOC']/hl7:participantRole/hl7:playingEntity/hl7:name",
            namespaces=ns,
        )
        if location_el is not None:
            location_text_raw = location_el.xpath("string()")
            location_text = (
                location_text_raw if isinstance(location_text_raw, str) else str(location_text_raw or "")
            )
            location_text = location_text.strip()
            if location_text:
                location_name = " ".join(location_text.split())

        additional_notes: list[str] = []
        for ref in _ensure_element_list(
            enc.xpath("hl7:entryRelationship//hl7:text/hl7:reference", namespaces=ns)
        ):
            ref_value = ref.get("value")
            if ref_value:
                note_text = get_text_by_id(tree, ns, ref_value)
                if note_text:
                    additional_notes.append(note_text)

        encounter_id = None
        id_el = enc.find("hl7:id", namespaces=ns)
        if id_el is not None:
            encounter_id = id_el.get("extension") or id_el.get("root")

        notes = _join_clean(
            [
                description,
                _join_clean(additional_notes),
                f"Location: {location_name}" if location_name else None,
                f"Status: {status}" if status else None,
                f"Mood: {mood}" if mood else None,
                f"Encounter ID: {encounter_id}" if encounter_id else None,
            ]
        )

        encounters.append(
            {
                "code": encounter_code,
                "type": encounter_type,
                "status": status,
                "mood": mood,
                "start": start,
                "end": end,
                "provider": provider_name,
                "location": location_name,
                "notes": notes,
                "source_id": encounter_id,
                "reason_for_visit": reason_for_visit,
            }
        )

    return encounters
