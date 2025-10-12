from __future__ import annotations

# Purpose: Parse condition/problem list sections from CCD documents.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Condition parsing helpers for CCD ingestion."""

from typing import Any, Sequence, cast

from lxml import etree

from .common import extract_provider_name, get_text_by_id

ConditionEntry = dict[str, Any]

SECTION_CODES: set[str] = {
    "11450-4",  # Problem List
    "11348-0",  # History of Past illness
    "29299-5",  # Problem list (report)
}

_ALLOWED_OBS_TEMPLATE_IDS: set[str] = {
    "2.16.840.1.113883.10.20.22.4.4",  # Problem Observation
}


def _add_code(codes: list[dict[str, str | None]], element: etree._Element | None) -> None:
    """Append a coded value to the output collection if it is unique.

    Args:
        codes: List that accumulates code dictionaries.
        element: XML element containing ``code`` metadata.
    """
    if element is None:
        return

    code = (element.get("code") or "").strip()
    if not code:
        return

    system = (element.get("codeSystem") or "").strip() or None
    display = (element.get("displayName") or "").strip() or None
    entry = {"code": code, "system": system, "display": display}
    if entry not in codes:
        codes.append(entry)


def _extract_status(observation: etree._Element, ns: dict[str, str]) -> str | None:
    """Return the textual status label from an observation node."""
    status_value = observation.find(
        "hl7:entryRelationship[@typeCode='REFR']/hl7:observation/hl7:value",
        namespaces=ns,
    )
    if status_value is not None:
        label = (status_value.get("displayName") or status_value.get("code") or "").strip()
        if label:
            return label

    status_code = observation.find("hl7:statusCode", namespaces=ns)
    if status_code is not None:
        label = (status_code.get("code") or "").strip()
        if label:
            return label
    return None


def _extract_time_range(
    node: etree._Element | None,
    ns: dict[str, str],
) -> tuple[str | None, str | None]:
    """Extract start/end timestamps from an HL7 effectiveTime construct."""
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
    return start, end


def parse_conditions(tree: etree._ElementTree, ns: dict[str, str]) -> list[ConditionEntry]:
    """Parse patient problems and conditions from a CCD document.

    Args:
        tree: Root XML tree for a CCD document.
        ns: Namespace dictionary used for XPath lookups.

    Returns:
        list[ConditionEntry]: Normalised condition entries appropriate for persistence.
    """
    conditions: list[ConditionEntry] = []
    section_nodes = cast(Sequence[Any], tree.xpath(".//hl7:section", namespaces=ns))
    sections: list[etree._Element] = []
    for section in section_nodes:
        if not isinstance(section, etree._Element):
            continue
        code_el = section.find("hl7:code", namespaces=ns)
        if code_el is not None and code_el.get("code") in SECTION_CODES:
            sections.append(section)

    seen_keys: set[tuple[str | None, str | None, str | None]] = set()

    for section in sections:
        for entry in section.findall("hl7:entry", namespaces=ns):
            observation = entry.find(".//hl7:observation", namespaces=ns)
            if observation is None:
                continue

            template_ids = {
                template_id.get("root")
                for template_id in observation.findall("hl7:templateId", namespaces=ns)
                if isinstance(template_id, etree._Element)
            }
            if not (_ALLOWED_OBS_TEMPLATE_IDS & template_ids):
                continue

            notes_parts: list[str] = []
            text_ref = observation.find("hl7:text/hl7:reference", namespaces=ns)
            obs_text = None
            if text_ref is not None and text_ref.get("value"):
                obs_text = get_text_by_id(tree, ns, text_ref.get("value"))
                if obs_text:
                    notes_parts.append(obs_text)

            value_el = observation.find("hl7:value", namespaces=ns)
            codes: list[dict[str, str | None]] = []
            _add_code(codes, observation.find("hl7:code", namespaces=ns))
            _add_code(codes, value_el)
            if value_el is not None:
                for translation in value_el.findall("hl7:translation", namespaces=ns):
                    _add_code(codes, translation)

            status = _extract_status(observation, ns)
            start, end = _extract_time_range(
                observation.find("hl7:effectiveTime", namespaces=ns), ns
            )

            concern_act = entry.find("hl7:act", namespaces=ns)
            if concern_act is not None:
                concern_start, concern_end = _extract_time_range(
                    concern_act.find("hl7:effectiveTime", namespaces=ns), ns
                )
                if concern_start and not start:
                    start = concern_start
                if concern_end and not end:
                    end = concern_end

            provider_name = extract_provider_name(
                observation,
                "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
                "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
                ns,
            )
            author_time_el = observation.find("hl7:author/hl7:time", namespaces=ns)
            author_time = author_time_el.get("value") if author_time_el is not None else None

            encounter_el = entry.find(".//hl7:encounter", namespaces=ns)
            encounter_source_id = None
            encounter_start = None
            encounter_end = None
            if encounter_el is not None:
                encounter_id_el = encounter_el.find("hl7:id", namespaces=ns)
                if encounter_id_el is not None:
                    encounter_source_id = (
                        encounter_id_el.get("extension") or encounter_id_el.get("root")
                    )
                enc_start, enc_end = _extract_time_range(
                    encounter_el.find("hl7:effectiveTime", namespaces=ns), ns
                )
                encounter_start = enc_start
                encounter_end = enc_end

            name = obs_text
            if not name and value_el is not None:
                name = (value_el.get("displayName") or value_el.get("code") or "").strip() or None
            if not name and codes:
                name = codes[0].get("display") or codes[0].get("code")

            reference_nodes = cast(
                Sequence[Any],
                entry.xpath(".//hl7:reference[@value]", namespaces=ns),
            )
            for ref in reference_nodes:
                if not isinstance(ref, etree._Element):
                    continue
                note_text = get_text_by_id(tree, ns, ref.get("value"))
                if note_text and note_text not in notes_parts:
                    notes_parts.append(note_text)

            notes = " | ".join(sorted({part.strip() for part in notes_parts if part})) or None

            main_code = codes[0]["code"] if codes else None
            key = (name, main_code, start)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            conditions.append(
                {
                    "name": name,
                    "codes": codes,
                    "status": status.title() if isinstance(status, str) and status else status,
                    "start": start,
                    "end": end,
                    "notes": notes,
                    "provider": provider_name,
                    "author_time": author_time,
                    "encounter_source_id": encounter_source_id,
                    "encounter_start": encounter_start,
                    "encounter_end": encounter_end,
                }
            )

    return conditions
