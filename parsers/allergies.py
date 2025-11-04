# Purpose: Parse allergy and intolerance observations from CCD documents.
# Author: Codex + Lauren
# Date: 2025-10-19
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Allergy parsing helpers."""

from __future__ import annotations

from typing import Optional

from .common import (
    clean_text,
    collect_template_ids,
    extract_effective_time,
    extract_notes,
    extract_provider_name,
    extract_status_code,
    first_non_empty,
    iter_elements,
    normalize_whitespace,
)
from .xml_types import ElementType, ElementTreeType

__all__ = ["parse_allergies"]

ALLERGY_SECTION_CODES: set[str] = {
    "48765-2",  # Allergies, adverse reactions, alerts
    "50544-6",  # Allergy and intolerance
    "75305-3",  # Allergy summary
}

ALLERGY_TEMPLATE_IDS: set[str] = {
    "2.16.840.1.113883.10.20.22.4.7",  # Allergy concern act
    "2.16.840.1.113883.10.20.22.4.8",  # Allergy observation
}

REACTION_TEMPLATE_IDS: set[str] = {
    "2.16.840.1.113883.10.20.22.4.9",  # Reaction observation
}

SEVERITY_TEMPLATE_IDS: set[str] = {
    "2.16.840.1.113883.10.20.22.4.8.2",  # Severity observation extension
}


def _allergy_sections(tree: ElementTreeType, ns: dict[str, str]) -> list[ElementType]:
    """Return CCD sections that describe allergies or intolerances."""
    root = tree.getroot()
    sections: list[ElementType] = []
    section_nodes = root.xpath(".//hl7:section", namespaces=ns)
    for section in iter_elements(section_nodes):
        code_el = section.find("hl7:code", namespaces=ns)
        code_value = clean_text(code_el.get("code") if code_el is not None else None)
        if code_value in ALLERGY_SECTION_CODES:
            sections.append(section)
    return sections


def _is_allergy_observation(observation: ElementType, ns: dict[str, str]) -> bool:
    """Return True when the observation matches allergy templates."""
    template_ids = collect_template_ids(observation, ns)
    return bool(template_ids & ALLERGY_TEMPLATE_IDS)


def _extract_participant_substance(
    observation: ElementType,
    ns: dict[str, str],
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Return substance name and coded metadata from participant nodes."""
    participant = observation.find(
        "hl7:participant[@typeCode='CSM']/hl7:participantRole/hl7:playingEntity",
        namespaces=ns,
    )
    if participant is None:
        return (None, None, None, None)
    code = participant.find("hl7:code", namespaces=ns)
    name = participant.find("hl7:name", namespaces=ns)
    raw_name = normalize_whitespace(
        code.get("displayName") if code is not None else None
    )
    if not raw_name and isinstance(name, ElementType):
        raw_name = normalize_whitespace(name.xpath("string()"))
    substance_code = (
        clean_text(code.get("code")) if isinstance(code, ElementType) else None
    )
    substance_system = (
        clean_text(code.get("codeSystem")) if isinstance(code, ElementType) else None
    )
    substance_display = (
        normalize_whitespace(code.get("displayName"))
        if isinstance(code, ElementType)
        else None
    )
    return (raw_name, substance_code, substance_system, substance_display)


def _extract_value_details(
    node: ElementType | None,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return code, code system, and display name from a ``value`` element."""
    if node is None:
        return (None, None, None)
    if isinstance(node, ElementType):
        code = clean_text(node.get("code"))
        code_system = clean_text(node.get("codeSystem"))
        display = normalize_whitespace(node.get("displayName")) or normalize_whitespace(
            node.xpath("string()")
        )
        return (code, code_system, display)
    return (None, None, None)


def _extract_reaction_details(
    observation: ElementType,
    ns: dict[str, str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return reaction description and codes from nested observations."""
    for relationship in observation.findall("hl7:entryRelationship", namespaces=ns):
        if relationship.get("typeCode") not in {"MFST", "SUBJ"}:
            continue
        reaction_obs = relationship.find("hl7:observation", namespaces=ns)
        if reaction_obs is None:
            continue
        if not collect_template_ids(reaction_obs, ns) & REACTION_TEMPLATE_IDS:
            continue
        value = reaction_obs.find("hl7:value", namespaces=ns)
        code, code_system, display = _extract_value_details(value)
        reaction = display or code
        if not reaction:
            text = reaction_obs.find("hl7:text", namespaces=ns)
            if isinstance(text, ElementType):
                reaction = normalize_whitespace(text.xpath("string()"))
        return (reaction, code, code_system)
    return (None, None, None)


def _extract_severity(observation: ElementType, ns: dict[str, str]) -> Optional[str]:
    """Return the severity label for the observation."""
    for relationship in observation.findall("hl7:entryRelationship", namespaces=ns):
        severity_obs = relationship.find("hl7:observation", namespaces=ns)
        if severity_obs is None:
            continue
        templates = collect_template_ids(severity_obs, ns)
        if relationship.get("typeCode") not in {"SUBJ", "REFR"} and not templates:
            continue
        code_elem = severity_obs.find("hl7:code", namespaces=ns)
        if (
            code_elem is not None and code_elem.get("code") == "SEV"
        ) or templates & SEVERITY_TEMPLATE_IDS:
            value = severity_obs.find("hl7:value", namespaces=ns)
            _, _, display = _extract_value_details(value)
            if display:
                return display
    return None


def _extract_encounter_hint(
    observation: ElementType,
    ns: dict[str, str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return encounter identifier and temporal hints."""
    for relationship in observation.findall("hl7:entryRelationship", namespaces=ns):
        encounter = relationship.find("hl7:encounter", namespaces=ns)
        if encounter is None:
            continue
        identifier = None
        enc_id = encounter.find("hl7:id", namespaces=ns)
        if isinstance(enc_id, ElementType):
            identifier = clean_text(enc_id.get("extension") or enc_id.get("root"))
        start, end = extract_effective_time(
            encounter.find("hl7:effectiveTime", namespaces=ns),
            ns,
        )
        return (identifier, start, end)
    return (None, None, None)


def _extract_source_id(observation: ElementType, ns: dict[str, str]) -> Optional[str]:
    """Return the first non-empty identifier from the observation."""
    for identifier in iter_elements(observation.findall("hl7:id", namespaces=ns)):
        value = clean_text(identifier.get("extension") or identifier.get("root"))
        if value:
            return value
    return None


def _extract_author_time(
    observation: ElementType,
    ns: dict[str, str],
) -> Optional[str]:
    """Return the author timestamp for the observation."""
    author_time = observation.find("hl7:author/hl7:time", namespaces=ns)
    if isinstance(author_time, ElementType):
        return clean_text(author_time.get("value"))
    return None


def _extract_criticality(
    observation: ElementType,
    ns: dict[str, str],
) -> Optional[str]:
    """Return the criticality classification for the observation."""
    criticality_code = observation.find("hl7:priorityCode", namespaces=ns)
    if not isinstance(criticality_code, ElementType):
        return None
    return first_non_empty(
        normalize_whitespace(criticality_code.get("displayName")),
        normalize_whitespace(criticality_code.get("code")),
    )


def _build_allergy_entry(
    tree: ElementTreeType,
    observation: ElementType,
    ns: dict[str, str],
) -> Optional[dict[str, Optional[str]]]:
    """Construct an allergy entry from a single observation."""
    if not _is_allergy_observation(observation, ns):
        return None

    value_details = _extract_value_details(observation.find("hl7:value", namespaces=ns))
    participant_details = _extract_participant_substance(observation, ns)

    substance_name = first_non_empty(
        participant_details[0],
        value_details[2],
        value_details[0],
    )
    if substance_name is None:
        return None

    reaction_details = _extract_reaction_details(observation, ns)
    severity = _extract_severity(observation, ns)
    notes = extract_notes(tree, observation, ns)
    status = extract_status_code(observation, ns)
    start, _ = extract_effective_time(
        observation.find("hl7:effectiveTime", namespaces=ns),
        ns,
    )
    author_time = _extract_author_time(observation, ns)
    criticality = _extract_criticality(observation, ns)
    provider_name = extract_provider_name(
        observation,
        "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
        "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
        ns,
    )
    encounter_source_id, encounter_start, encounter_end = _extract_encounter_hint(
        observation,
        ns,
    )
    source_id = _extract_source_id(observation, ns)

    return {
        "substance": substance_name,
        "substance_code": first_non_empty(participant_details[1], value_details[0]),
        "substance_code_system": first_non_empty(
            participant_details[2], value_details[1]
        ),
        "substance_code_display": first_non_empty(
            participant_details[3], value_details[2]
        ),
        "reaction": reaction_details[0],
        "reaction_code": reaction_details[1],
        "reaction_code_system": reaction_details[2],
        "severity": severity,
        "criticality": criticality,
        "status": status,
        "onset": start,
        "noted_date": author_time,
        "notes": notes,
        "provider": provider_name,
        "source_allergy_id": source_id,
        "encounter_source_id": encounter_source_id,
        "encounter_start": encounter_start,
        "encounter_end": encounter_end,
    }


def parse_allergies(
    tree: ElementTreeType, ns: dict[str, str]
) -> list[dict[str, Optional[str]]]:
    """Extract allergies and intolerances from a CCD document."""
    allergies: list[dict[str, Optional[str]]] = []
    for section in _allergy_sections(tree, ns):
        entries = section.findall("hl7:entry", namespaces=ns)
        for entry in iter_elements(entries):
            observations = entry.xpath(".//hl7:observation", namespaces=ns)
            for observation in iter_elements(observations):
                allergy = _build_allergy_entry(tree, observation, ns)
                if allergy:
                    allergies.append(allergy)
    return allergies
