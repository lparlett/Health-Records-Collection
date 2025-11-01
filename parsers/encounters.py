# Purpose: Parse encounter sections from CCD documents into structured records.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Encounter parsing helpers for CCD ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .common import (
    clean_text,
    extract_effective_time,
    extract_provider_info,
    first_non_empty,
    get_text_by_id,
    iter_elements,
    normalize_whitespace,
)
from .xml_types import ElementType, ElementTreeType

EncounterEntry = dict[str, Optional[str]]

REASON_FOR_VISIT_CODES: set[str] = {
    "29299-5",  # Reason for visit Narrative
    "46241-6",  # Reason for referral
    "78018-7",  # Reason for encounter
}


@dataclass(slots=True)
class DocumentContext:
    """Document-level encounter metadata shared across entries."""

    global_start: Optional[str]
    global_end: Optional[str]
    service_start: Optional[str]
    service_end: Optional[str]
    provider_person: Optional[str]
    provider_org: Optional[str]
    invalid_times: set[str]
    reason_for_visit: Optional[str]


def _normalize_reason_text(value: Optional[str]) -> Optional[str]:
    """Collapse whitespace and return a consistent reason-for-visit string."""
    if not value:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def _join_clean(parts: Iterable[Optional[str]]) -> Optional[str]:
    """Join non-empty strings with a delimiter after trimming whitespace."""
    cleaned_parts = [
        normalize_whitespace(part) for part in parts if normalize_whitespace(part)
    ]
    if not cleaned_parts:
        return None
    return " | ".join(cleaned_parts)


def _collect_invalid_times(tree: ElementTreeType, ns: dict[str, str]) -> set[str]:
    """Return timestamps that should be ignored when merging encounter times."""
    invalid_times: set[str] = set()
    birth_el = tree.find(
        "hl7:recordTarget/hl7:patientRole/hl7:patient/hl7:birthTime", namespaces=ns
    )
    birth_time = clean_text(birth_el.get("value") if birth_el is not None else None)
    if birth_time:
        invalid_times.add(birth_time)
        if len(birth_time) >= 8:
            invalid_times.add(birth_time[:8])
    return invalid_times


def _reason_sections(tree: ElementTreeType, ns: dict[str, str]) -> list[ElementType]:
    """Return sections that plausibly describe reason-for-visit narratives."""
    sections = []
    for section in iter_elements(tree.xpath(".//hl7:section", namespaces=ns)):
        code_el = section.find("hl7:code", namespaces=ns)
        code_value = clean_text(code_el.get("code") if code_el is not None else None)
        title_text = normalize_whitespace(section.findtext("hl7:title", namespaces=ns))
        title_lower = (title_text or "").lower()
        if code_value in REASON_FOR_VISIT_CODES or (
            "reason" in title_lower
            and any(
                keyword in title_lower for keyword in ("visit", "encounter", "referral")
            )
        ):
            sections.append(section)
    return sections


def _reason_for_visit(tree: ElementTreeType, ns: dict[str, str]) -> Optional[str]:
    """Collate all unique reason-for-visit narratives from the CCD."""
    reasons: list[str] = []
    seen: set[str] = set()
    for section in _reason_sections(tree, ns):
        text_nodes = section.xpath(
            ".//hl7:act/hl7:text | .//hl7:observation/hl7:text | .//hl7:paragraph | .//hl7:list/hl7:item",
            namespaces=ns,
        )
        for node in iter_elements(text_nodes):
            narrative = _normalize_reason_text(
                normalize_whitespace(node.xpath("string()"))
            )
            if narrative and narrative not in seen:
                seen.add(narrative)
                reasons.append(narrative)
        reference_nodes = section.xpath(".//hl7:reference[@value]", namespaces=ns)
        for reference in iter_elements(reference_nodes):
            resolved = _normalize_reason_text(
                get_text_by_id(tree, ns, reference.get("value"))
            )
            if resolved and resolved not in seen:
                seen.add(resolved)
                reasons.append(resolved)
    if not reasons:
        return None
    return "; ".join(reasons)


def _document_context(tree: ElementTreeType, ns: dict[str, str]) -> DocumentContext:
    """Gather global encounter context for the entire document."""
    encompassing = tree.find("hl7:componentOf/hl7:encompassingEncounter", namespaces=ns)
    provider_person: Optional[str] = None
    provider_org: Optional[str] = None
    if encompassing is not None:
        provider_person, provider_org = extract_provider_info(
            encompassing,
            "hl7:encounterParticipant/hl7:assignedEntity/hl7:assignedPerson/hl7:name",
            "hl7:encounterParticipant/hl7:assignedEntity/hl7:representedOrganization/hl7:name",
            ns,
        )
    global_start, global_end = extract_effective_time(
        (
            encompassing.find("hl7:effectiveTime", namespaces=ns)
            if encompassing is not None
            else None
        ),
        ns,
    )

    service_event = tree.find("hl7:documentationOf/hl7:serviceEvent", namespaces=ns)
    service_start, service_end = extract_effective_time(
        (
            service_event.find("hl7:effectiveTime", namespaces=ns)
            if service_event is not None
            else None
        ),
        ns,
    )

    return DocumentContext(
        global_start=global_start,
        global_end=global_end,
        service_start=service_start,
        service_end=service_end,
        provider_person=provider_person,
        provider_org=provider_org,
        invalid_times=_collect_invalid_times(tree, ns),
        reason_for_visit=_reason_for_visit(tree, ns),
    )


def _encounter_type(
    encounter: ElementType,
    tree: ElementTreeType,
    ns: dict[str, str],
) -> tuple[Optional[str], Optional[str]]:
    """Return encounter code and human-readable type."""
    code_el = encounter.find("hl7:code", namespaces=ns)
    code = clean_text(code_el.get("code") if code_el is not None else None)
    encounter_type = normalize_whitespace(
        code_el.get("displayName") if code_el is not None else None
    )
    if not encounter_type and code_el is not None:
        reference = code_el.find("hl7:originalText/hl7:reference", namespaces=ns)
        if reference is not None and reference.get("value"):
            encounter_type = normalize_whitespace(
                get_text_by_id(tree, ns, reference.get("value"))
            )
        if not encounter_type:
            translation = code_el.find("hl7:translation[@displayName]", namespaces=ns)
            if translation is not None:
                encounter_type = normalize_whitespace(translation.get("displayName"))
    if not encounter_type:
        encounter_type = code
    return code, encounter_type


def _encounter_description(
    encounter: ElementType,
    tree: ElementTreeType,
    ns: dict[str, str],
) -> Optional[str]:
    """Return encounter narrative description if referenced."""
    text_ref = encounter.find("hl7:text/hl7:reference", namespaces=ns)
    if text_ref is not None and text_ref.get("value"):
        return normalize_whitespace(get_text_by_id(tree, ns, text_ref.get("value")))
    return None


def _encounter_status(encounter: ElementType, ns: dict[str, str]) -> Optional[str]:
    """Return encounter status code."""
    status_el = encounter.find("hl7:statusCode", namespaces=ns)
    return clean_text(status_el.get("code") if status_el is not None else None)


def _encounter_location(encounter: ElementType, ns: dict[str, str]) -> Optional[str]:
    """Return encounter location name."""
    location_el = encounter.find(
        "hl7:participant[@typeCode='LOC']/hl7:participantRole/hl7:playingEntity/hl7:name",
        namespaces=ns,
    )
    if location_el is None:
        return None
    return normalize_whitespace(location_el.xpath("string()"))


def _encounter_provider(
    encounter: ElementType,
    ns: dict[str, str],
    fallback_person: Optional[str],
    fallback_org: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Return encounter provider name with organisation fallback."""
    provider_name, attending_org = extract_provider_info(
        encounter,
        "hl7:participant[@typeCode='ATND']/hl7:assignedEntity/hl7:assignedPerson/hl7:name",
        "hl7:participant[@typeCode='ATND']/hl7:assignedEntity/hl7:representedOrganization/hl7:name",
        ns,
    )
    if not provider_name:
        provider_name, performing_org = extract_provider_info(
            encounter,
            "hl7:performer/hl7:assignedEntity/hl7:assignedPerson/hl7:name",
            "hl7:performer/hl7:assignedEntity/hl7:representedOrganization/hl7:name",
            ns,
        )
    else:
        performing_org = None

    provider_name = provider_name or fallback_person
    organisation = first_non_empty(attending_org, performing_org, fallback_org)
    return provider_name, organisation


def _encounter_additional_notes(
    encounter: ElementType,
    tree: ElementTreeType,
    ns: dict[str, str],
) -> list[str]:
    """Collect additional reference notes for the encounter."""
    notes: list[str] = []
    reference_nodes = encounter.xpath(
        "hl7:entryRelationship//hl7:text/hl7:reference", namespaces=ns
    )
    for reference in iter_elements(reference_nodes):
        ref_value = reference.get("value")
        if ref_value:
            note_text = normalize_whitespace(get_text_by_id(tree, ns, ref_value))
            if note_text:
                notes.append(note_text)
    return notes


def _encounter_source_id(encounter: ElementType, ns: dict[str, str]) -> Optional[str]:
    """Return encounter identifier if present."""
    id_el = encounter.find("hl7:id", namespaces=ns)
    if id_el is not None:
        return clean_text(id_el.get("extension") or id_el.get("root"))
    return None


def _is_valid_time_value(value: Optional[str], invalid_values: set[str]) -> bool:
    """Return True when the candidate time is not part of the invalid set."""
    if not value:
        return False
    if not invalid_values:
        return True
    return not any(value.startswith(invalid) for invalid in invalid_values if invalid)


def _merge_time_candidates(
    *candidates: tuple[Optional[str], Optional[str]],
    invalid_values: set[str],
) -> tuple[Optional[str], Optional[str]]:
    """Merge time ranges from most general to specific candidates."""
    start: Optional[str] = None
    end: Optional[str] = None
    for candidate_start, candidate_end in candidates:
        if candidate_start and _is_valid_time_value(candidate_start, invalid_values):
            start = candidate_start
        if candidate_end and _is_valid_time_value(candidate_end, invalid_values):
            end = candidate_end
    if end is None:
        end = start
    return start, end


def _build_encounter_entry(
    encounter: ElementType,
    tree: ElementTreeType,
    ns: dict[str, str],
    context: DocumentContext,
) -> Optional[EncounterEntry]:
    """Create a single encounter entry from the CCD node."""
    code, encounter_type = _encounter_type(encounter, tree, ns)
    status = _encounter_status(encounter, ns)
    mood = clean_text(encounter.get("moodCode"))
    if mood == "APT":
        return None  # Skip appointments; only actual encounters are captured

    description = _encounter_description(encounter, tree, ns)
    encounter_start, encounter_end = extract_effective_time(
        encounter.find("hl7:effectiveTime", namespaces=ns),
        ns,
    )
    start, end = _merge_time_candidates(
        (context.global_start, context.global_end),
        (context.service_start, context.service_end),
        (encounter_start, encounter_end),
        invalid_values=context.invalid_times,
    )

    provider_name, organisation = _encounter_provider(
        encounter,
        ns,
        context.provider_person,
        context.provider_org,
    )
    location = _encounter_location(encounter, ns)
    additional_notes = _encounter_additional_notes(encounter, tree, ns)
    source_id = _encounter_source_id(encounter, ns)

    notes = _join_clean(
        [
            description,
            _join_clean(additional_notes),
            f"Location: {location}" if location else None,
            f"Status: {status}" if status else None,
            f"Mood: {mood}" if mood else None,
            f"Encounter ID: {source_id}" if source_id else None,
        ]
    )

    return {
        "code": code,
        "type": encounter_type,
        "status": status,
        "mood": mood,
        "start": start,
        "end": end,
        "provider": provider_name,
        "organization": organisation,
        "location": location,
        "notes": notes,
        "source_id": source_id,
        "reason_for_visit": context.reason_for_visit,
    }


def parse_encounters(tree: ElementTreeType, ns: dict[str, str]) -> list[EncounterEntry]:
    """Parse encounters documented within a CCD."""
    context = _document_context(tree, ns)
    encounters: list[EncounterEntry] = []
    encounter_nodes = tree.xpath(".//hl7:encounter", namespaces=ns)
    for encounter in iter_elements(encounter_nodes):
        entry = _build_encounter_entry(encounter, tree, ns, context)
        if entry:
            encounters.append(entry)
    return encounters
