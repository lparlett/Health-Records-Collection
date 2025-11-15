# Purpose: Parse condition/problem list sections from CCD documents.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Condition parsing helpers for CCD ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .common import (
    clean_text,
    extract_effective_time,
    extract_provider_name,
    first_non_empty,
    get_text_by_id,
    iter_elements,
    normalize_whitespace,
)
from .xml_types import ElementType, ElementTreeType

ConditionEntry = dict[str, Any]
ConditionKey = tuple[Optional[str], Optional[str], Optional[str]]

SECTION_CODES: set[str] = {
    "11450-4",  # Problem List
    "11348-0",  # History of Past illness
    "29299-5",  # Problem list (report)
    "51848-0",  # Visit diagnoses
}

_ALLOWED_OBS_TEMPLATE_IDS: set[str] = {
    "2.16.840.1.113883.10.20.22.4.4",  # Problem Observation
    "2.16.840.1.113883.10.20.22.2.8",  # Visit Diagnoses
}


def _condition_sections(tree: ElementTreeType, ns: dict[str, str]) -> list[ElementType]:
    """Return CCD sections that correspond to problem lists."""
    root = tree.getroot()
    sections: list[ElementType] = []
    section_nodes = root.xpath(".//hl7:section", namespaces=ns)
    for section in iter_elements(section_nodes):
        code_el = section.find("hl7:code", namespaces=ns)
        code_value = clean_text(code_el.get("code") if code_el is not None else None)
        if code_value in SECTION_CODES:
            sections.append(section)
    return sections


def _is_condition_observation(observation: ElementType, ns: dict[str, str]) -> bool:
    """Return True when the observation matches a recognised problem template."""
    template_ids = {
        template_id.get("root")
        for template_id in observation.findall("hl7:templateId", namespaces=ns)
        if isinstance(template_id, ElementType)
    }
    return bool(_ALLOWED_OBS_TEMPLATE_IDS & template_ids)


def _add_code(codes: list[dict[str, str | None]], element: ElementType | None) -> None:
    """Append a coded value to the output collection if it is unique.

    Args:
        codes: List that accumulates code dictionaries.
        element: XML element containing ``code`` metadata.
    """
    if element is None:
        return

    code = clean_text(element.get("code"))
    if not code:
        return

    system = clean_text(element.get("codeSystem"))
    display = normalize_whitespace(element.get("displayName"))
    entry = {"code": code, "system": system, "display": display}
    if entry not in codes:
        codes.append(entry)


def _extract_status(observation: ElementType, ns: dict[str, str]) -> str | None:
    """Return the textual status label from an observation node."""
    status_value = observation.find(
        "hl7:entryRelationship[@typeCode='REFR']/hl7:observation/hl7:value",
        namespaces=ns,
    )
    if status_value is not None:
        label = normalize_whitespace(
            status_value.get("displayName") or status_value.get("code")
        )
        if label:
            return label

    status_code = observation.find("hl7:statusCode", namespaces=ns)
    label = normalize_whitespace(
        status_code.get("code") if status_code is not None else None
    )
    return label


def _condition_codes(
    observation: ElementType, ns: dict[str, str]
) -> tuple[list[dict[str, str | None]], ElementType | None]:
    """Return coded identifiers for the condition and the primary value element."""
    value_el = observation.find("hl7:value", namespaces=ns)
    codes: list[dict[str, str | None]] = []
    _add_code(codes, observation.find("hl7:code", namespaces=ns))
    _add_code(codes, value_el)
    if value_el is not None:
        for translation in value_el.findall("hl7:translation", namespaces=ns):
            _add_code(codes, translation)
    return codes, value_el


def _observation_text(
    observation: ElementType,
    tree: ElementTreeType,
    ns: dict[str, str],
) -> Optional[str]:
    """Return human-readable text linked to the observation."""
    text_ref = observation.find("hl7:text/hl7:reference", namespaces=ns)
    if text_ref is not None and text_ref.get("value"):
        return normalize_whitespace(get_text_by_id(tree, ns, text_ref.get("value")))
    return None


def _condition_notes(
    tree: ElementTreeType,
    entry: ElementType,
    ns: dict[str, str],
    base_text: Optional[str],
) -> Optional[str]:
    """Aggregate narrative notes for the condition."""
    notes: list[str] = []
    seen: set[str] = set()
    if base_text:
        normalized = normalize_whitespace(base_text)
        if normalized:
            notes.append(normalized)
            seen.add(normalized)

    reference_nodes = entry.xpath(".//hl7:reference[@value]", namespaces=ns)
    for ref in iter_elements(reference_nodes):
        note_text = normalize_whitespace(get_text_by_id(tree, ns, ref.get("value")))
        if note_text and note_text not in seen:
            seen.add(note_text)
            notes.append(note_text)

    if not notes:
        return None
    return " | ".join(sorted(notes))


def _condition_times(
    observation: ElementType,
    entry: ElementType,
    ns: dict[str, str],
) -> tuple[str | None, str | None]:
    """Determine onset and resolution timestamps for the condition."""
    start, end = extract_effective_time(
        observation.find("hl7:effectiveTime", namespaces=ns),
        ns,
    )
    concern_act = entry.find("hl7:act", namespaces=ns)
    if concern_act is not None:
        concern_start, concern_end = extract_effective_time(
            concern_act.find("hl7:effectiveTime", namespaces=ns),
            ns,
        )
        start = start or concern_start
        end = end or concern_end
    return start, end


def _condition_encounter(
    entry: ElementType,
    ns: dict[str, str],
) -> tuple[str | None, str | None, str | None]:
    """Return encounter linkage details if present."""
    encounter_el = entry.find(".//hl7:encounter", namespaces=ns)
    if encounter_el is None:
        return None, None, None
    encounter_id_el = encounter_el.find("hl7:id", namespaces=ns)
    encounter_source_id = (
        clean_text(encounter_id_el.get("extension") or encounter_id_el.get("root"))
        if encounter_id_el is not None
        else None
    )
    encounter_start, encounter_end = extract_effective_time(
        encounter_el.find("hl7:effectiveTime", namespaces=ns),
        ns,
    )
    return encounter_source_id, encounter_start, encounter_end


def _condition_author_time(
    observation: ElementType, ns: dict[str, str]
) -> Optional[str]:
    """Return the time the observation was authored, if provided."""
    author_time_el = observation.find("hl7:author/hl7:time", namespaces=ns)
    return clean_text(
        author_time_el.get("value") if author_time_el is not None else None
    )


def _condition_name(
    obs_text: Optional[str],
    value_el: ElementType | None,
    codes: list[dict[str, str | None]],
) -> Optional[str]:
    """Select the best display name for the condition."""
    value_display = None
    value_code = None
    if value_el is not None:
        value_display = normalize_whitespace(value_el.get("displayName"))
        value_code = normalize_whitespace(value_el.get("code"))
    code_display = codes[0].get("display") if codes else None
    code_value = codes[0].get("code") if codes else None
    return first_non_empty(
        normalize_whitespace(obs_text),
        value_display,
        value_code,
        normalize_whitespace(code_display),
        normalize_whitespace(code_value),
    )


def _condition_key(
    name: Optional[str],
    codes: list[dict[str, str | None]],
    start: Optional[str],
) -> ConditionKey:
    """Generate a deduplication key for condition entries."""
    main_code = codes[0]["code"] if codes else None
    return (name, main_code, start)


@dataclass(slots=True)
class ConditionRecord:
    """Encapsulate a condition entry with its deduplication key."""

    entry: ConditionEntry
    key: ConditionKey


def _build_condition_record(
    observation: ElementType,
    entry: ElementType,
    tree: ElementTreeType,
    ns: dict[str, str],
) -> ConditionRecord | None:
    """Return a condition entry/key pair for a qualifying observation."""
    if not _is_condition_observation(observation, ns):
        return None
    # pylint: disable=line-too-long
    codes, value_el = _condition_codes(observation, ns)
    status = _extract_status(observation, ns)
    start, end = _condition_times(observation, entry, ns)
    provider_name = extract_provider_name(
        observation,
        "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
        "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
        ns,
    )
    # pylint: enable-line-too-long
    author_time = _condition_author_time(observation, ns)
    encounter_source_id, encounter_start, encounter_end = _condition_encounter(
        entry, ns
    )

    obs_text = _observation_text(observation, tree, ns)
    notes = _condition_notes(tree, entry, ns, obs_text)
    name = _condition_name(obs_text, value_el, codes)
    if name is None:
        return None

    key = _condition_key(name, codes, start)
    return ConditionRecord(
        entry={
            "name": name,
            "codes": codes,
            "status": status.title() if status else None,
            "start": start,
            "end": end,
            "notes": notes,
            "provider": provider_name,
            "author_time": author_time,
            "encounter_source_id": encounter_source_id,
            "encounter_start": encounter_start,
            "encounter_end": encounter_end,
        },
        key=key,
    )


def parse_conditions(tree: ElementTreeType, ns: dict[str, str]) -> list[ConditionEntry]:
    """Parse patient problems and conditions from a CCD document.

    Args:
        tree: Root XML tree for a CCD document.
        ns: Namespace dictionary used for XPath lookups.

    Returns:
        list[ConditionEntry]: Normalised condition entries appropriate for persistence.
    """

    conditions: list[ConditionEntry] = []
    seen_keys: set[ConditionKey] = set()

    for section in _condition_sections(tree, ns):
        for entry in iter_elements(section.findall("hl7:entry", namespaces=ns)):
            observations = entry.xpath(".//hl7:observation", namespaces=ns)
            for observation in iter_elements(observations):
                record = _build_condition_record(observation, entry, tree, ns)
                if record is None:
                    continue
                if record.key in seen_keys:
                    continue
                seen_keys.add(record.key)
                conditions.append(record.entry)

    return conditions
