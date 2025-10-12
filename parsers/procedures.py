from __future__ import annotations

# Purpose: Parse procedure sections from CCD documents into structured records.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Procedure parsing helpers for CCD ingestion."""

from typing import TypedDict

from lxml import etree

from .common import extract_provider_name, get_text_by_id


class ProcedureCode(TypedDict):
    """Represents a coded procedure descriptor."""

    code: str
    system: str | None
    display: str | None


class ProcedureEntry(TypedDict, total=False):
    """Represents a normalised procedure entry."""

    name: str
    codes: list[ProcedureCode]
    status: str | None
    date: str | None
    notes: str | None
    provider: str | None
    encounter_source_id: str | None
    author_time: str | None


PROCEDURE_SECTION_CODES: set[str] = {
    "47519-4",
    "62387-6",
    "29554-3",
}

PROCEDURE_TEMPLATE_IDS: set[str] = {
    "2.16.840.1.113883.10.20.22.4.14",
    "2.16.840.1.113883.10.20.22.4.13",
    "2.16.840.1.113883.10.20.22.4.12",
}


def _collect_codes(code_element: etree._Element | None, ns: dict[str, str]) -> list[ProcedureCode]:
    """Collect codes from a code element and its translations."""
    codes: list[ProcedureCode] = []
    if code_element is None:
        return codes

    def add(element: etree._Element | None) -> None:
        if element is None:
            return
        code_val = (element.get("code") or "").strip()
        if not code_val:
            return
        system = (element.get("codeSystem") or "").strip() or None
        display = (element.get("displayName") or "").strip() or None
        entry: ProcedureCode = {
            "code": code_val,
            "system": system,
            "display": display,
        }
        if entry not in codes:
            codes.append(entry)

    add(code_element)
    for translation in code_element.findall("hl7:translation", namespaces=ns):
        add(translation)
    return codes


def parse_procedures(tree: etree._ElementTree, ns: dict[str, str]) -> list[ProcedureEntry]:
    """Parse procedure entries from a CCD document.

    Args:
        tree: Root XML tree representing the CCD document.
        ns: Namespace dictionary used for XPath lookups.

    Returns:
        list[ProcedureEntry]: Parsed procedure entries.
    """
    procedures: list[ProcedureEntry] = []

    raw_sections = tree.xpath(".//hl7:section", namespaces=ns)
    if not isinstance(raw_sections, list):
        return procedures

    for section in [sec for sec in raw_sections if isinstance(sec, etree._Element)]:
        code_el = section.find("hl7:code", namespaces=ns)
        section_code = code_el.get("code") if code_el is not None else None
        title = section.findtext("hl7:title", namespaces=ns)
        if not (
            (section_code and section_code in PROCEDURE_SECTION_CODES)
            or (title and "procedure" in title.lower())
        ):
            continue

        for entry in section.findall("hl7:entry", namespaces=ns):
            raw_candidates = entry.xpath(
                "hl7:procedure | hl7:act | hl7:observation",
                namespaces=ns,
            )
            if not isinstance(raw_candidates, list):
                continue
            proc_candidates = [el for el in raw_candidates if isinstance(el, etree._Element)]
            if not proc_candidates:
                continue
            proc = proc_candidates[0]

            template_ids = {
                tpl.get("root") for tpl in proc.findall("hl7:templateId", namespaces=ns)
            }
            if PROCEDURE_TEMPLATE_IDS and not (template_ids & PROCEDURE_TEMPLATE_IDS):
                if section_code not in PROCEDURE_SECTION_CODES:
                    continue

            code_el = proc.find("hl7:code", namespaces=ns)
            codes = _collect_codes(code_el, ns)
            display = None
            if code_el is not None:
                display = code_el.get("displayName") or None
                if not display:
                    ref = code_el.find("hl7:originalText/hl7:reference", namespaces=ns)
                    if ref is not None and ref.get("value"):
                        display = get_text_by_id(tree, ns, ref.get("value"))

            text_ref = proc.find("hl7:text/hl7:reference", namespaces=ns)
            notes = (
                get_text_by_id(tree, ns, text_ref.get("value"))
                if text_ref is not None and text_ref.get("value")
                else None
            )
            status_el = proc.find("hl7:statusCode", namespaces=ns)
            status = status_el.get("code") if status_el is not None else None

            effective = proc.find("hl7:effectiveTime", namespaces=ns)
            date = None
            if effective is not None:
                if effective.get("value"):
                    date = effective.get("value")
                else:
                    low = effective.find("hl7:low", namespaces=ns)
                    if low is not None and low.get("value"):
                        date = low.get("value")

            provider_name = extract_provider_name(
                proc,
                "hl7:performer/hl7:assignedEntity/hl7:assignedPerson/hl7:name",
                "hl7:performer/hl7:assignedEntity/hl7:representedOrganization/hl7:name",
                ns,
            )

            encounter_el = entry.find(".//hl7:encounter", namespaces=ns)
            encounter_source_id = None
            if encounter_el is not None:
                id_el = encounter_el.find("hl7:id", namespaces=ns)
                if id_el is not None:
                    encounter_source_id = id_el.get("extension") or id_el.get("root")

            author_time_el = proc.find("hl7:author/hl7:time", namespaces=ns)
            author_time = author_time_el.get("value") if author_time_el is not None else None

            name = (
                display
                or (codes[0]["display"] if codes else None)
                or (codes[0]["code"] if codes else None)
                or notes
            )
            if not name:
                continue

            procedures.append(
                {
                    "name": name,
                    "codes": codes,
                    "status": status.title() if status else None,
                    "date": date,
                    "notes": notes,
                    "provider": provider_name,
                    "encounter_source_id": encounter_source_id,
                    "author_time": author_time,
                }
            )
    return procedures
