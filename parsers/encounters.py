from __future__ import annotations

from typing import Dict, List, Optional

from lxml import etree

from .common import extract_provider_name, get_text_by_id

EncounterEntry = Dict[str, Optional[str]]


def _join_clean(parts: List[Optional[str]]) -> Optional[str]:
    cleaned = [part.strip() for part in parts if part and part.strip()]
    if not cleaned:
        return None
    return " | ".join(cleaned)


def _extract_time_range(node: etree._Element, ns: dict[str, str]) -> tuple[Optional[str], Optional[str]]:
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


def parse_encounters(tree: etree._ElementTree, ns: dict[str, str]) -> List[EncounterEntry]:
    encounters: List[EncounterEntry] = []
    for enc in tree.xpath(".//hl7:encounter", namespaces=ns):
        code_el = enc.find("hl7:code", namespaces=ns)
        encounter_code = code_el.get("code") if code_el is not None else None
        encounter_type: Optional[str] = None
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
            location_text = location_el.xpath("string()")
            if location_text:
                location_name = " ".join(location_text.split())

        additional_notes: List[str] = []
        for ref in enc.xpath("hl7:entryRelationship//hl7:text/hl7:reference", namespaces=ns):
            ref_value = ref.get("value")
            if ref_value:
                note_text = get_text_by_id(tree, ns, ref_value)
                if note_text:
                    additional_notes.append(note_text)

        encounter_id = None
        id_el = enc.find("hl7:id", namespaces=ns)
        if id_el is not None:
            encounter_id = id_el.get("extension") or id_el.get("root")

        notes = _join_clean([
            description,
            _join_clean(additional_notes),
            f"Location: {location_name}" if location_name else None,
            f"Status: {status}" if status else None,
            f"Mood: {mood}" if mood else None,
            f"Encounter ID: {encounter_id}" if encounter_id else None,
        ])

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
            }
        )

    return encounters
