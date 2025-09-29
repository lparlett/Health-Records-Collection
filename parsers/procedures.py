"""Parses procedure entries from a CCDA document.

This script extracts procedure information such as codes, status, date,
notes, provider, encounter source ID, and author time from a CCDA XML document.
It defines data structures to represent procedure codes and entries, and
provides a function to parse the procedures section of the document. 

"""
from pathlib import Path
from typing import List, Optional, TypedDict

from lxml import etree

from .common import extract_provider_name, get_text_by_id

class ProcedureCode(TypedDict):
    """A class to represent a procedure code.
    
    Attributes:
        code (str): The procedure code.
        system (Optional[str]): The coding system (e.g., SNOMED, ICD-10).
        display (Optional[str]): The human-readable description of the code.
    """
    code: str
    system: Optional[str]
    display: Optional[str]


class ProcedureEntry(TypedDict, total=False):
    """A class to represent a procedure entry.
    
    Attributes:
        name (str): The name or description of the procedure.
        codes (List[ProcedureCode]): A list of associated procedure codes.
        status (Optional[str]): The status of the procedure (e.g., completed, active).
        date (Optional[str]): The date when the procedure was performed.
        notes (Optional[str]): Additional notes or comments about the procedure.
        provider (Optional[str]): The name of the provider who performed the procedure.
        encounter_source_id (Optional[str]): The source ID of the encounter related to the procedure.
        author_time (Optional[str]): The time when the procedure was documented.
    """
    name: str
    codes: List[ProcedureCode]
    status: Optional[str]
    date: Optional[str]
    notes: Optional[str]
    provider: Optional[str]
    encounter_source_id: Optional[str]
    author_time: Optional[str]

PROCEDURE_SECTION_CODES = {
    "47519-4",
    "62387-6",
    "29554-3",
}

PROCEDURE_TEMPLATE_IDS = {
    "2.16.840.1.113883.10.20.22.4.14",
    "2.16.840.1.113883.10.20.22.4.13",
    "2.16.840.1.113883.10.20.22.4.12",
}


def _collect_codes(code_element: Optional[etree._Element], 
                   ns: dict[str, str]) -> List[ProcedureCode]:
    """Collects codes from a code element and its translations.
    
    Args:
        code_element (Optional[etree._Element]): The XML element 
                                                    containing the code.
        ns (dict[str, str]): The namespace dictionary for XML parsing. 
    Returns:
        List[ProcedureCode]: A list of collected procedure codes.
    """
    codes: List[ProcedureCode] = []
   
    if code_element is None:
        return codes

    def add(el: Optional[etree._Element]) -> None:
        if el is None:
            return
        code_val = (el.get("code") or "").strip()
        if not code_val:
            return
        system = (el.get("codeSystem") or "").strip() or None
        display = (el.get("displayName") or "").strip() or None
        entry: ProcedureCode = {"code": code_val, 
                                "system": system, 
                                "display": display}
        if entry not in codes:
            codes.append(entry)

    add(code_element)
    for translation in code_element.findall("hl7:translation", namespaces=ns):
        add(translation)
    return codes


def parse_procedures(tree: etree._ElementTree, 
                     ns: dict[str, str]) -> List[ProcedureEntry]:
    """Parses procedure entries from a CCDA document.
    
    Args:
        tree (etree._ElementTree): The XML tree of the CCDA document.
        ns (dict[str, str]): The namespace dictionary for XML parsing.
    Returns:
        List[ProcedureEntry]: A list of parsed procedure entries.
    """
    procedures: List[ProcedureEntry] = []

    raw_sections = tree.xpath(".//hl7:section", namespaces=ns)
    if not isinstance(raw_sections, list):
        return procedures

    for section in [sec 
                    for sec in raw_sections 
                    if isinstance(sec, etree._Element)
                    ]:
        code_el = section.find("hl7:code", namespaces=ns)
        section_code = code_el.get("code") if code_el is not None else None
        title = section.findtext("hl7:title", namespaces=ns)
        if not ((section_code and section_code in PROCEDURE_SECTION_CODES) or 
                (title and "procedure" in title.lower())):
            continue

        for entry in section.findall("hl7:entry", namespaces=ns):
            raw_candidates = entry.xpath(
                "hl7:procedure | hl7:act | hl7:observation", 
                namespaces=ns
                )
            if not isinstance(raw_candidates, list):
                continue
            proc_candidates: List[etree._Element] = [
                el 
                for el in raw_candidates 
                if isinstance(el, etree._Element)
                ]
            if not proc_candidates:
                continue
            proc = proc_candidates[0]

            template_ids = {tpl.get("root") for tpl in 
                            proc.findall("hl7:templateId", namespaces=ns)}
            if PROCEDURE_TEMPLATE_IDS and not (template_ids & 
                                               PROCEDURE_TEMPLATE_IDS):
                if section_code not in PROCEDURE_SECTION_CODES:
                    continue

            code_el = proc.find("hl7:code", namespaces=ns)
            codes = _collect_codes(code_el, ns)
            display = None
            if code_el is not None:
                display = code_el.get("displayName") or None
                if not display:
                    ref = code_el.find("hl7:originalText/hl7:reference", 
                                       namespaces=ns)
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
                    encounter_source_id = (
                        id_el.get("extension") or id_el.get("root")
                    )

            author_time_el = proc.find("hl7:author/hl7:time", namespaces=ns)
            author_time = (
                author_time_el.get("value")
                if author_time_el is not None
                else None
            )
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