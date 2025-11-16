# Purpose: Parse vital sign observations from CCD documents.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Vital sign parsing helpers for CCD ingestion."""
from __future__ import annotations

from dataclasses import dataclass

from .common import (
    extract_effective_time,
    extract_provider_name,
    get_text_by_id,
    iter_elements,
    normalize_whitespace,
)
from .xml_types import ElementType, ElementTreeType

VitalEntry = dict[str, str | None]


@dataclass(slots=True)
class OrganizerContext:
    """Normalization helpers shared by entries from one organizer."""

    start: str | None
    end: str | None
    source_id: str | None
    provider: str | None


def _resolve_vital_name(
    tree: ElementTreeType,
    ns: dict[str, str],
    code_el: ElementType,
) -> str | None:
    """Resolve a human-readable vital label from code metadata."""
    display = normalize_whitespace(code_el.get("displayName"))
    if display:
        return display
    original = code_el.find("hl7:originalText", namespaces=ns)
    if original is not None:
        ref = original.find("hl7:reference", namespaces=ns)
        if ref is not None and ref.get("value"):
            resolved = normalize_whitespace(get_text_by_id(tree, ns, ref.get("value")))
            if resolved:
                return resolved
        original_text = normalize_whitespace(original.xpath("string()"))
        if original_text:
            return original_text
    translation = code_el.find("hl7:translation[@displayName]", namespaces=ns)
    if translation is not None:
        translated = normalize_whitespace(translation.get("displayName"))
        if translated:
            return translated
    return normalize_whitespace(code_el.get("code"))


def _extract_value_and_unit(
    value_el: ElementType | None,
) -> tuple[str | None, str | None]:
    """Extract a vital measurement's numeric value and unit."""
    if value_el is None:
        return None, None
    value = normalize_whitespace(value_el.get("value"))
    if not value:
        text_value = normalize_whitespace(value_el.xpath("string()"))
        if text_value:
            value = text_value
        else:
            value = normalize_whitespace(
                value_el.get("displayName")
            ) or normalize_whitespace(value_el.get("code"))
    unit = normalize_whitespace(value_el.get("unit"))
    if not unit:
        unit = normalize_whitespace(value_el.get("codeSystemName"))
    return value, unit


def _build_organizer_context(
    organizer: ElementType,
    ns: dict[str, str],
) -> OrganizerContext:
    """Capture organizer-level defaults for nested observations."""
    organizer_start, organizer_end = extract_effective_time(
        organizer.find("hl7:effectiveTime", namespaces=ns),
        ns,
    )
    organizer_id_el = organizer.find("hl7:id", namespaces=ns)
    source_id: str | None = None
    if organizer_id_el is not None:
        source_id = organizer_id_el.get("extension") or organizer_id_el.get("root")
    provider = extract_provider_name(
        organizer,
        "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
        "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
        ns,
    )
    return OrganizerContext(
        start=organizer_start,
        end=organizer_end,
        source_id=source_id,
        provider=provider,
    )


def _build_vital_entry(
    tree: ElementTreeType,
    ns: dict[str, str],
    observation: ElementType,
    context: OrganizerContext,
) -> VitalEntry | None:
    """Convert an observation into a normalized vital entry."""
    code_el = observation.find("hl7:code", namespaces=ns)
    if code_el is None:
        return None
    vital_code = normalize_whitespace(code_el.get("code"))
    vital_type = _resolve_vital_name(tree, ns, code_el)
    value_el = observation.find("hl7:value", namespaces=ns)
    value, unit = _extract_value_and_unit(value_el)
    if value is None:
        return None

    status_el = observation.find("hl7:statusCode", namespaces=ns)
    status = status_el.get("code") if status_el is not None else None
    obs_start, obs_end = extract_effective_time(
        observation.find("hl7:effectiveTime", namespaces=ns),
        ns,
    )
    observation_provider = extract_provider_name(
        observation,
        "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
        "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
        ns,
    )
    return {
        "code": vital_code,
        "vital_type": vital_type,
        "value": value,
        "unit": unit,
        "status": status,
        "date": obs_start or obs_end or context.start or context.end,
        "encounter_start": obs_start or context.start,
        "encounter_end": obs_end or context.end,
        "encounter_source_id": context.source_id,
        "provider": observation_provider or context.provider,
    }


def _parse_organizer(
    tree: ElementTreeType,
    ns: dict[str, str],
    organizer: ElementType,
) -> list[VitalEntry]:
    """Extract vital entries from a single organizer node."""
    context = _build_organizer_context(organizer, ns)
    organizer_vitals: list[VitalEntry] = []
    component_nodes = organizer.findall("hl7:component", namespaces=ns)
    for component in iter_elements(component_nodes):
        observation = component.find("hl7:observation", namespaces=ns)
        if observation is None:
            continue
        entry = _build_vital_entry(tree, ns, observation, context)
        if entry:
            organizer_vitals.append(entry)
    return organizer_vitals


def parse_vitals(tree: ElementTreeType, ns: dict[str, str]) -> list[VitalEntry]:
    """Parse vital sign observations (height, weight, temperature, etc.) from a CCD.

    Args:
        tree: Root XML tree representing the CCD document.
        ns: Namespace dictionary used for XPath lookups.

    Returns:
        list[VitalEntry]: Normalised vital sign entries.
    """
    root = tree.getroot()
    vitals: list[VitalEntry] = []
    section_nodes = root.xpath(
        ".//hl7:section[hl7:code[@code='8716-3']]",
        namespaces=ns,
    )
    section = next(iter(iter_elements(section_nodes)), None)
    if section is None or section.get("nullFlavor") == "NI":
        return vitals

    organizer_nodes = section.findall("hl7:entry/hl7:organizer", namespaces=ns)
    for organizer in iter_elements(organizer_nodes):
        vitals.extend(_parse_organizer(tree, ns, organizer))

    return vitals
