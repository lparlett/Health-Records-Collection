from __future__ import annotations

from typing import Dict, List, Optional

from lxml import etree

from .common import extract_provider_name, get_text_by_id

VitalEntry = Dict[str, Optional[str]]


def _extract_time_range(node: Optional[etree._Element], ns: dict[str, str]) -> tuple[Optional[str], Optional[str]]:
    start: Optional[str] = None
    end: Optional[str] = None
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


def _text_content(element: Optional[etree._Element]) -> Optional[str]:
    if element is None:
        return None
    text_value = element.xpath("string()")
    if text_value:
        cleaned = text_value.strip()
        if cleaned:
            return " ".join(cleaned.split())
    return None


def _resolve_vital_name(tree: etree._ElementTree, ns: dict[str, str], code_el: etree._Element) -> Optional[str]:
    display = code_el.get("displayName")
    if display:
        return display
    original = code_el.find("hl7:originalText", namespaces=ns)
    if original is not None:
        # Some documents embed the label directly, others via narrative reference.
        ref = original.find("hl7:reference", namespaces=ns)
        if ref is not None and ref.get("value"):
            resolved = get_text_by_id(tree, ns, ref.get("value"))
            if resolved:
                return resolved
        original_text = _text_content(original)
        if original_text:
            return original_text
    translation = code_el.find("hl7:translation[@displayName]", namespaces=ns)
    if translation is not None:
        translated = translation.get("displayName")
        if translated:
            return translated
    return code_el.get("code")


def _extract_value_and_unit(value_el: Optional[etree._Element]) -> tuple[Optional[str], Optional[str]]:
    if value_el is None:
        return None, None
    value = value_el.get("value")
    if not value:
        text_value = _text_content(value_el)
        if text_value:
            value = text_value
        else:
            value = value_el.get("displayName") or value_el.get("code")
    unit = value_el.get("unit")
    if not unit:
        # Some coded values express unit via translation attributes; fallback to code system name if provided.
        unit = value_el.get("codeSystemName")
    if value is not None:
        value = str(value).strip()
        if not value:
            value = None
    if unit is not None:
        unit = unit.strip()
        if not unit:
            unit = None
    return value, unit


def parse_vitals(tree: etree._ElementTree, ns: dict[str, str]) -> List[VitalEntry]:
    """Parse vital sign observations (height, weight, temperature, etc.) from a CCD."""
    vitals: List[VitalEntry] = []
    section_nodes = tree.xpath(
        ".//hl7:section[hl7:code[@code='8716-3']]",
        namespaces=ns,
    )
    section = section_nodes[0] if section_nodes else None
    if section is None or section.get("nullFlavor") == "NI":
        return vitals

    for organizer in section.findall("hl7:entry/hl7:organizer", namespaces=ns):
        organizer_start, organizer_end = _extract_time_range(
            organizer.find("hl7:effectiveTime", namespaces=ns),
            ns,
        )
        organizer_id_el = organizer.find("hl7:id", namespaces=ns)
        organizer_source_id: Optional[str] = None
        if organizer_id_el is not None:
            organizer_source_id = organizer_id_el.get("extension") or organizer_id_el.get("root")

        organizer_provider = extract_provider_name(
            organizer,
            "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
            "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
            ns,
        )

        for component in organizer.findall("hl7:component", namespaces=ns):
            observation = component.find("hl7:observation", namespaces=ns)
            if observation is None:
                continue
            code_el = observation.find("hl7:code", namespaces=ns)
            if code_el is None:
                continue

            vital_code = code_el.get("code")
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
