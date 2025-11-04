# Purpose: Parse laboratory results from CCD documents into structured entries.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Laboratory result parsing helpers for CCD ingestion."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .common import (
    XSI_NS,
    clean_text,
    extract_effective_time,
    extract_encounter_details,
    extract_provider_name,
    first_non_empty,
    iter_elements,
    normalize_whitespace,
    safe_xpath_text,
)
from .xml_types import ElementType, ElementTreeType

logger = logging.getLogger(__name__)

LabEntry = dict[str, Optional[str]]


@dataclass(slots=True)
class OrganizerContext:
    encounter_id: Optional[str]
    encounter_start: Optional[str]
    encounter_end: Optional[str]
    ordering_provider: Optional[str]
    performing_org: Optional[str]
    panel_flag: Optional[str] = None


def _lab_sections(tree: ElementTreeType, ns: dict[str, str]) -> list[ElementType]:
    """Return CCD sections that correspond to laboratory findings."""
    root = tree.getroot()
    sections = root.xpath(".//hl7:section[hl7:code[@code='30954-2']]", namespaces=ns)
    return iter_elements(sections)


def _organizer_context(
    organizer: ElementType,
    ns: dict[str, str],
) -> OrganizerContext:
    """Assemble reusable context data for lab organizer entries."""
    encounter_id, encounter_start, encounter_end = extract_encounter_details(
        organizer.find(".//hl7:encounter", namespaces=ns),
        ns,
    )
    ordering_provider = extract_provider_name(
        organizer,
        "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
        "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
        ns,
    )
    performing_org = extract_provider_name(
        organizer,
        "hl7:performer/hl7:assignedEntity/hl7:assignedPerson/hl7:name",
        "hl7:performer/hl7:assignedEntity/hl7:representedOrganization/hl7:name",
        ns,
    )
    return OrganizerContext(
        encounter_id=encounter_id,
        encounter_start=encounter_start,
        encounter_end=encounter_end,
        ordering_provider=ordering_provider,
        performing_org=performing_org,
    )


def _panel_flag(observation: ElementType, ns: dict[str, str]) -> Optional[str]:
    """Return panel interpretation flag when observation represents a panel summary."""
    code_el = observation.find("hl7:code", namespaces=ns)
    if code_el is None or clean_text(code_el.get("code")) != "56850-1":
        return None
    value_el = observation.find("hl7:value", namespaces=ns)
    if value_el is None:
        return None
    return first_non_empty(
        clean_text(value_el.get("value")),
        normalize_whitespace(value_el.xpath("string()")),
        normalize_whitespace(value_el.get("displayName")),
        normalize_whitespace(value_el.get("code")),
    )


def _loinc_code(code_el: ElementType | None) -> Optional[str]:
    """Return the LOINC code when the observation is LOINC-based."""
    if code_el is None:
        return None
    code = clean_text(code_el.get("code"))
    if not code:
        return None
    code_system = clean_text(code_el.get("codeSystem"))
    code_system_name = clean_text(code_el.get("codeSystemName"))
    if code_system == "2.16.840.1.113883.6.1":
        return code
    if code_system_name and code_system_name.upper() == "LOINC":
        return code
    return None


def _resolve_test_name(
    observation: ElementType,
    ns: dict[str, str],
    loinc: str,
) -> str:
    """Derive a user-friendly test name."""
    code_el = observation.find("hl7:code", namespaces=ns)
    display = normalize_whitespace(
        code_el.get("displayName") if code_el is not None else None
    )
    if display:
        return display
    original_text = observation.find("hl7:code/hl7:originalText", namespaces=ns)
    if isinstance(original_text, ElementType):
        resolved = normalize_whitespace(original_text.xpath("string()"))
        if resolved:
            return resolved
    return loinc


def _extract_result_value(
    value_el: ElementType | None,
) -> tuple[Optional[str], Optional[str]]:
    """Return numeric/text value and unit for a lab observation."""
    if value_el is None:
        return None, None
    value = clean_text(value_el.get("value"))
    if not value:
        value = first_non_empty(
            normalize_whitespace(value_el.xpath("string()")),
            normalize_whitespace(value_el.get("displayName")),
            normalize_whitespace(value_el.get("code")),
        )
    unit = normalize_whitespace(value_el.get("unit"))
    xsi_type = clean_text(value_el.get(f"{{{XSI_NS}}}type"))
    if not unit and xsi_type and xsi_type.upper() in {"CD", "CE", "CV"}:
        unit = normalize_whitespace(value_el.get("codeSystemName"))
    return value, unit


def _extract_reference_range(
    observation: ElementType,
    ns: dict[str, str],
) -> Optional[str]:
    """Return the reference range text if provided."""
    ref_text = safe_xpath_text(
        observation,
        ".//hl7:referenceRange//hl7:observationRange//hl7:text",
        ns,
    )
    return normalize_whitespace(ref_text)


def _extract_interpretation(
    observation: ElementType,
    ns: dict[str, str],
) -> Optional[str]:
    """Return the interpretation code flag for the observation."""
    for interp in iter_elements(
        observation.findall("hl7:interpretationCode", namespaces=ns)
    ):
        flag = first_non_empty(
            normalize_whitespace(interp.get("code")),
            normalize_whitespace(interp.get("displayName")),
        )
        if flag:
            return flag
    nested = observation.xpath(
        ".//hl7:referenceRange//hl7:interpretationCode",
        namespaces=ns,
    )
    for interp in iter_elements(nested):
        flag = first_non_empty(
            normalize_whitespace(interp.get("code")),
            normalize_whitespace(interp.get("displayName")),
        )
        if flag:
            return flag
    return None


def _build_lab_entry(
    observation: ElementType,
    context: OrganizerContext,
    ns: dict[str, str],
) -> Optional[LabEntry]:
    """Construct a normalised lab entry from the observation."""
    code_el = observation.find("hl7:code", namespaces=ns)
    if code_el is None:
        logger.debug("Skipping observation without <code> element.")
        return None

    loinc = _loinc_code(code_el)
    if loinc is None:
        return None

    test_name = _resolve_test_name(observation, ns, loinc)
    value, unit = _extract_result_value(observation.find("hl7:value", namespaces=ns))
    if value is None:
        return None

    date, _ = extract_effective_time(
        observation.find("hl7:effectiveTime", namespaces=ns),
        ns,
    )
    reference_range = _extract_reference_range(observation, ns)
    abnormal_flag = _extract_interpretation(observation, ns) or context.panel_flag

    return {
        "encounter_source_id": context.encounter_id,
        "encounter_start": context.encounter_start,
        "encounter_end": context.encounter_end,
        "test_name": test_name,
        "loinc": loinc,
        "value": value,
        "unit": unit,
        "reference_range": reference_range,
        "abnormal_flag": abnormal_flag,
        "date": date,
        "ordering_provider": context.ordering_provider,
        "performing_org": context.performing_org,
    }


def parse_labs(tree: ElementTreeType, ns: dict[str, str]) -> list[LabEntry]:
    """Parse laboratory results documented within a CCD."""
    labs: list[LabEntry] = []
    for section in _lab_sections(tree, ns):
        organizer_nodes = section.findall("hl7:entry/hl7:organizer", namespaces=ns)
        for organizer in iter_elements(organizer_nodes):
            context = _organizer_context(organizer, ns)

            observations = organizer.findall(
                "hl7:component/hl7:observation", namespaces=ns
            )
            for observation in iter_elements(observations):
                flag = _panel_flag(observation, ns)
                if flag:
                    context.panel_flag = flag
                    continue

                entry = _build_lab_entry(observation, context, ns)
                if entry:
                    labs.append(entry)
    return labs
