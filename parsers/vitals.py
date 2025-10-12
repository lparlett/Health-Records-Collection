from __future__ import annotations

# Purpose: Parse vital sign observations from CCD documents.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Vital sign parsing helpers for CCD ingestion."""

from collections.abc import Sequence
from typing import Any, Iterable, cast

from lxml import etree

from .common import extract_provider_name, get_text_by_id

VitalEntry = dict[str, str | None]


def _iter_elements(value: object) -> list[etree._Element]:
    """Coerce mixed values returned by XPath into a list of elements."""
    elements: list[etree._Element] = []
    if isinstance(value, etree._Element):
        elements.append(value)
    elif isinstance(value, Sequence):
        for item in value:
            if isinstance(item, etree._Element):
                elements.append(item)
    return elements


def _normalize_text(value: object) -> str | None:
    """Convert varied text representations into a trimmed string."""
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="ignore")
    elif isinstance(value, str):
        text = value
    else:
        text = str(value)
    text = text.strip()
    if not text:
        return None
    return " ".join(text.split())


def _extract_time_range(
    node: etree._Element | None,
    ns: dict[str, str],
) -> tuple[str | None, str | None]:
    """Extract start/end times from an HL7 effectiveTime element."""
    start: str | None = None
    end: str | None = None
    if node is None:
        return start, end
    value = node.get("value")
    if value:
        start = value
        end = value
        return start, end
    low = node.find("hl7:low", namespaces=ns)
    high = node.find("hl7:high", namespaces=ns)
    if low is not None and low.get("value"):
        start = low.get("value")
    if high is not None and high.get("value"):
        end = high.get("value")
    if end is None and start is not None:
        end = start
    return start, end


def _resolve_vital_name(
    tree: etree._ElementTree,
    ns: dict[str, str],
    code_el: etree._Element,
) -> str | None:
    """Resolve a human-readable vital label from code metadata."""
    display = _normalize_text(code_el.get("displayName"))
    if display:
        return display
    original = code_el.find("hl7:originalText", namespaces=ns)
    if original is not None:
        ref = original.find("hl7:reference", namespaces=ns)
        if ref is not None and ref.get("value"):
            resolved = get_text_by_id(tree, ns, ref.get("value"))
            if resolved:
                return resolved
        original_text = _normalize_text(original.xpath("string()"))
        if original_text:
            return original_text
    translation = code_el.find("hl7:translation[@displayName]", namespaces=ns)
    if translation is not None:
        translated = _normalize_text(translation.get("displayName"))
        if translated:
            return translated
    return _normalize_text(code_el.get("code"))


def _extract_value_and_unit(
    value_el: etree._Element | None,
) -> tuple[str | None, str | None]:
    """Extract a vital measurement's numeric value and unit."""
    if value_el is None:
        return None, None
    value = _normalize_text(value_el.get("value"))
    if not value:
        text_value = _normalize_text(value_el.xpath("string()"))
        if text_value:
            value = text_value
        else:
            value = _normalize_text(value_el.get("displayName")) or _normalize_text(value_el.get("code"))
    unit = _normalize_text(value_el.get("unit"))
    if not unit:
        unit = _normalize_text(value_el.get("codeSystemName"))
    return value, unit


def parse_vitals(tree: etree._ElementTree, ns: dict[str, str]) -> list[VitalEntry]:
    """Parse vital sign observations (height, weight, temperature, etc.) from a CCD.

    Args:
        tree: Root XML tree representing the CCD document.
        ns: Namespace dictionary used for XPath lookups.

    Returns:
        list[VitalEntry]: Normalised vital sign entries.
    """
    vitals: list[VitalEntry] = []
    section_nodes = tree.xpath(
        ".//hl7:section[hl7:code[@code='8716-3']]",
        namespaces=ns,
    )
    section = next(iter(_iter_elements(section_nodes)), None)
    if section is None or section.get("nullFlavor") == "NI":
        return vitals

    organizer_nodes = section.findall("hl7:entry/hl7:organizer", namespaces=ns)
    for organizer in _iter_elements(organizer_nodes):
        organizer_start, organizer_end = _extract_time_range(
            organizer.find("hl7:effectiveTime", namespaces=ns),
            ns,
        )
        organizer_id_el = organizer.find("hl7:id", namespaces=ns)
        organizer_source_id: str | None = None
        if organizer_id_el is not None:
            organizer_source_id = organizer_id_el.get("extension") or organizer_id_el.get("root")

        organizer_provider = extract_provider_name(
            organizer,
            "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
            "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
            ns,
        )

        component_nodes = organizer.findall("hl7:component", namespaces=ns)
        for component in _iter_elements(component_nodes):
            observation = component.find("hl7:observation", namespaces=ns)
            if observation is None:
                continue
            code_el = observation.find("hl7:code", namespaces=ns)
            if code_el is None:
                continue

            vital_code = _normalize_text(code_el.get("code"))
            vital_type = _resolve_vital_name(tree, ns, code_el)
            value_el = observation.find("hl7:value", namespaces=ns)
            value, unit = _extract_value_and_unit(value_el)
            if value is None:
                continue

            status_el = observation.find("hl7:statusCode", namespaces=ns)
            status = status_el.get("code") if status_el is not None else None

            obs_start, obs_end = _extract_time_range(
                observation.find("hl7:effectiveTime", namespaces=ns),
                ns,
            )
            observation_provider = extract_provider_name(
                observation,
                "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
                "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
                ns,
            )

            vitals.append(
                {
                    "code": vital_code,
                    "vital_type": vital_type,
                    "value": value,
                    "unit": unit,
                    "status": status,
                    "date": obs_start or obs_end or organizer_start or organizer_end,
                    "encounter_start": obs_start or organizer_start,
                    "encounter_end": obs_end or organizer_end,
                    "encounter_source_id": organizer_source_id,
                    "provider": observation_provider or organizer_provider,
                }
            )

    return vitals
