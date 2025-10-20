# Purpose: Parse allergy and intolerance observations from CCD documents.
# Author: Codex + Lauren
# Date: 2025-10-19
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Allergy parsing helpers."""

from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence, cast

from lxml import etree

from .common import extract_provider_name, get_text_by_id

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


def _clean_text(value: Any) -> Optional[str]:
    """Return a trimmed string or ``None`` when empty."""
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


def _iter_elements(value: object) -> Iterable[etree._Element]:
    """Yield XML elements from mixed XPath responses."""
    if isinstance(value, etree._Element):
        yield value
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        for item in value:
            if isinstance(item, etree._Element):
                yield item


def _collect_template_ids(node: etree._Element, ns: dict[str, str]) -> set[str]:
    """Return the templateId roots associated with an element."""
    roots: set[str] = set()
    for template in node.findall("hl7:templateId", namespaces=ns):
        root = _clean_text(template.get("root"))
        if root:
            roots.add(root)
    return roots


def _extract_time_range(node: etree._Element | None, ns: dict[str, str]) -> tuple[Optional[str], Optional[str]]:
    """Return (start, end) values from an HL7 ``effectiveTime``."""
    if node is None:
        return (None, None)
    value = _clean_text(node.get("value"))
    if value:
        return (value, value)
    low = node.find("hl7:low", namespaces=ns)
    high = node.find("hl7:high", namespaces=ns)
    start = _clean_text(low.get("value")) if isinstance(low, etree._Element) else None
    end = _clean_text(high.get("value")) if isinstance(high, etree._Element) else None
    return (start, end)


def _extract_participant_substance(
    observation: etree._Element,
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
    substance_name = _clean_text(code.get("displayName") if code is not None else None)
    if not substance_name:
        substance_name = _clean_text(name.text if isinstance(name, etree._Element) else None)
    substance_code = _clean_text(code.get("code")) if isinstance(code, etree._Element) else None
    substance_system = _clean_text(code.get("codeSystem")) if isinstance(code, etree._Element) else None
    substance_display = _clean_text(code.get("displayName")) if isinstance(code, etree._Element) else None
    return (substance_name, substance_code, substance_system, substance_display)


def _extract_value_details(node: etree._Element | None) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return code, code system, and display name from a ``value`` element."""
    if node is None:
        return (None, None, None)
    if isinstance(node, etree._Element):
        code = _clean_text(node.get("code"))
        code_system = _clean_text(node.get("codeSystem"))
        display = _clean_text(node.get("displayName") or node.text)
        return (code, code_system, display)
    return (None, None, None)


def _extract_reaction_details(
    observation: etree._Element,
    ns: dict[str, str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return reaction description and codes from nested observations."""
    for relationship in observation.findall("hl7:entryRelationship", namespaces=ns):
        if relationship.get("typeCode") not in {"MFST", "SUBJ"}:
            continue
        reaction_obs = relationship.find("hl7:observation", namespaces=ns)
        if reaction_obs is None:
            continue
        if not (_collect_template_ids(reaction_obs, ns) & REACTION_TEMPLATE_IDS):
            continue
        value = reaction_obs.find("hl7:value", namespaces=ns)
        code, code_system, display = _extract_value_details(value)
        reaction = display or code
        if not reaction:
            text = reaction_obs.find("hl7:text", namespaces=ns)
            reaction = _clean_text(text.xpath("string()")) if isinstance(text, etree._Element) else None
        return (reaction, code, code_system)
    return (None, None, None)


def _extract_severity(observation: etree._Element, ns: dict[str, str]) -> Optional[str]:
    """Return the severity label for the observation."""
    for relationship in observation.findall("hl7:entryRelationship", namespaces=ns):
        severity_obs = relationship.find("hl7:observation", namespaces=ns)
        if severity_obs is None:
            continue
        templates = _collect_template_ids(severity_obs, ns)
        if relationship.get("typeCode") not in {"SUBJ", "REFR"} and not templates:
            continue
        if (
            severity_obs.find("hl7:code", namespaces=ns) is not None
            and severity_obs.find("hl7:code", namespaces=ns).get("code") == "SEV"
        ) or templates & SEVERITY_TEMPLATE_IDS:
            value = severity_obs.find("hl7:value", namespaces=ns)
            _, _, display = _extract_value_details(value)
            if display:
                return display
    return None


def _extract_notes(tree: etree._ElementTree, observation: etree._Element, ns: dict[str, str]) -> Optional[str]:
    """Collect narrative text linked to the observation."""
    text_ref = observation.find("hl7:text/hl7:reference", namespaces=ns)
    note = get_text_by_id(tree, ns, text_ref.get("value")) if isinstance(text_ref, etree._Element) else None
    if note:
        return note
    text_node = observation.find("hl7:text", namespaces=ns)
    if isinstance(text_node, etree._Element):
        value = _clean_text(text_node.xpath("string()"))
        if value:
            return value
    return None


def _extract_encounter_hint(
    observation: etree._Element,
    ns: dict[str, str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return encounter identifier and temporal hints."""
    for relationship in observation.findall("hl7:entryRelationship", namespaces=ns):
        encounter = relationship.find("hl7:encounter", namespaces=ns)
        if encounter is None:
            continue
        identifier = None
        enc_id = encounter.find("hl7:id", namespaces=ns)
        if isinstance(enc_id, etree._Element):
            identifier = _clean_text(enc_id.get("extension") or enc_id.get("root"))
        start, end = _extract_time_range(encounter.find("hl7:effectiveTime", namespaces=ns), ns)
        return (identifier, start, end)
    return (None, None, None)


def parse_allergies(tree: etree._ElementTree, ns: dict[str, str]) -> list[dict[str, Optional[str]]]:
    """Extract allergies and intolerances from a CCD document."""
    allergies: list[dict[str, Optional[str]]] = []
    section_nodes = cast(Sequence[Any], tree.xpath(".//hl7:section", namespaces=ns))
    for section in section_nodes:
        if not isinstance(section, etree._Element):
            continue
        code_el = section.find("hl7:code", namespaces=ns)
        code_value = _clean_text(code_el.get("code")) if isinstance(code_el, etree._Element) else None
        if code_value not in ALLERGY_SECTION_CODES:
            continue
        for entry in section.findall("hl7:entry", namespaces=ns):
            observation_candidates = entry.xpath(".//hl7:observation", namespaces=ns)
            for obs in _iter_elements(observation_candidates):
                if not (_collect_template_ids(obs, ns) & ALLERGY_TEMPLATE_IDS):
                    continue

                value_node = obs.find("hl7:value", namespaces=ns)
                code, code_system, display = _extract_value_details(value_node)

                (
                    participant_name,
                    participant_code,
                    participant_system,
                    participant_display,
                ) = _extract_participant_substance(obs, ns)

                substance_name = participant_name or display or code
                substance_code = participant_code or code
                substance_system = participant_system or code_system
                substance_display = participant_display or display

                reaction, reaction_code, reaction_system = _extract_reaction_details(obs, ns)
                severity = _extract_severity(obs, ns)
                notes = _extract_notes(tree, obs, ns)
                status_node = obs.find("hl7:statusCode", namespaces=ns)
                status = _clean_text(status_node.get("code") if isinstance(status_node, etree._Element) else None)

                start, _ = _extract_time_range(obs.find("hl7:effectiveTime", namespaces=ns), ns)
                author_time = obs.find("hl7:author/hl7:time", namespaces=ns)
                noted_date = _clean_text(author_time.get("value")) if isinstance(author_time, etree._Element) else None

                criticality_code = obs.find("hl7:priorityCode", namespaces=ns)
                criticality = _clean_text(
                    criticality_code.get("displayName") if isinstance(criticality_code, etree._Element) else None
                ) or _clean_text(
                    criticality_code.get("code") if isinstance(criticality_code, etree._Element) else None
                )

                provider_name = extract_provider_name(
                    obs,
                    "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
                    "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
                    ns,
                )

                source_id = None
                for identifier in obs.findall("hl7:id", namespaces=ns):
                    source_id = _clean_text(identifier.get("extension") or identifier.get("root"))
                    if source_id:
                        break

                encounter_source_id, encounter_start, encounter_end = _extract_encounter_hint(obs, ns)

                allergies.append(
                    {
                        "substance": substance_name,
                        "substance_code": substance_code,
                        "substance_code_system": substance_system,
                        "substance_code_display": substance_display,
                        "reaction": reaction,
                        "reaction_code": reaction_code,
                        "reaction_code_system": reaction_system,
                        "severity": severity,
                        "criticality": criticality,
                        "status": status,
                        "onset": start,
                        "noted_date": noted_date,
                        "notes": notes,
                        "provider": provider_name,
                        "source_allergy_id": source_id,
                        "encounter_source_id": encounter_source_id,
                        "encounter_start": encounter_start,
                        "encounter_end": encounter_end,
                    }
                )
    return allergies
