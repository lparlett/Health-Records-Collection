# Purpose: Parse procedure sections from CCD documents into structured records.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Procedure parsing helpers for CCD ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TypedDict

from .common import (
    extract_effective_time,
    extract_notes,
    extract_provider_name,
    first_non_empty,
    get_text_by_id,
    iter_elements,
    normalize_whitespace,
    safe_xpath_text,
)
from .xml_types import ElementType, ElementTreeType


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


@dataclass(slots=True)
class ProcedureCandidate:
    """Stores an individual procedure observation with metadata."""

    node: ElementType
    encounter_source_id: Optional[str]
    author_time: Optional[str]


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


def _procedure_sections(tree: ElementTreeType, ns: dict[str, str]) -> list[ElementType]:
    """Return CCD sections that likely contain procedure information."""
    sections = tree.xpath(".//hl7:section", namespaces=ns)
    results: list[ElementType] = []
    for section in iter_elements(sections):
        code_el = section.find("hl7:code", namespaces=ns)
        section_code = normalize_whitespace(
            code_el.get("code") if code_el is not None else None
        )
        title_text = normalize_whitespace(safe_xpath_text(section, ".//hl7:title", ns))
        if (section_code and section_code in PROCEDURE_SECTION_CODES) or (
            title_text and "procedure" in title_text.lower()
        ):
            results.append(section)
    return results


def _is_procedure_template(node: ElementType, ns: dict[str, str]) -> bool:
    """Return True when the node matches a known procedure template."""
    template_ids = {
        template.get("root")
        for template in node.findall("hl7:templateId", namespaces=ns)
    }
    return bool(PROCEDURE_TEMPLATE_IDS & template_ids)


def _candidate_nodes(entry: ElementType, ns: dict[str, str]) -> list[ElementType]:
    """Return nodes within the entry that may contain procedure data."""
    raw_candidates = entry.xpath(
        "hl7:procedure | hl7:act | hl7:observation",
        namespaces=ns,
    )
    return list(iter_elements(raw_candidates))


def _collect_codes(
    code_element: ElementType | None, ns: dict[str, str]
) -> list[ProcedureCode]:
    """Collect codes from a code element and its translations."""
    codes: list[ProcedureCode] = []
    if code_element is None:
        return codes

    def add(element: ElementType | None) -> None:
        if element is None:
            return
        code_val = normalize_whitespace(element.get("code"))
        if not code_val:
            return
        system = normalize_whitespace(element.get("codeSystem"))
        display = normalize_whitespace(element.get("displayName"))
        entry = ProcedureCode(code=code_val, system=system, display=display)
        if entry not in codes:
            codes.append(entry)

    add(code_element)
    for translation in code_element.findall("hl7:translation", namespaces=ns):
        add(translation)
    return codes


def _resolve_procedure_name(
    tree: ElementTreeType,
    node: ElementType,
    ns: dict[str, str],
    codes: list[ProcedureCode],
) -> Optional[str]:
    """Determine the most descriptive procedure name."""
    code_el = node.find("hl7:code", namespaces=ns)
    if code_el is not None:
        display = normalize_whitespace(code_el.get("displayName"))
        if display:
            return display
        reference = code_el.find("hl7:originalText/hl7:reference", namespaces=ns)
        if reference is not None and reference.get("value"):
            resolved = normalize_whitespace(
                get_text_by_id(tree, ns, reference.get("value"))
            )
            if resolved:
                return resolved
    if codes:
        primary = codes[0]
        return first_non_empty(primary.get("display"), primary.get("code"))
    return None


def _encounter_source_id(entry: ElementType, ns: dict[str, str]) -> Optional[str]:
    """Return encounter identifier associated with the entry."""
    encounter_el = entry.find(".//hl7:encounter", namespaces=ns)
    if encounter_el is None:
        return None
    id_el = encounter_el.find("hl7:id", namespaces=ns)
    if id_el is None:
        return None
    return normalize_whitespace(id_el.get("extension") or id_el.get("root"))


def _candidate_procedures(
    entry: ElementType,
    section_code: Optional[str],
    ns: dict[str, str],
) -> list[ProcedureCandidate]:
    """Return candidate procedure nodes wrapped with encounter metadata."""
    encounter_source_id = _encounter_source_id(entry, ns)
    candidates: list[ProcedureCandidate] = []
    for node in _candidate_nodes(entry, ns):
        if (
            not _is_procedure_template(node, ns)
            and section_code not in PROCEDURE_SECTION_CODES
        ):
            continue
        author_time_el = node.find("hl7:author/hl7:time", namespaces=ns)
        author_time = normalize_whitespace(
            author_time_el.get("value") if author_time_el is not None else None
        )
        candidates.append(
            ProcedureCandidate(
                node=node,
                encounter_source_id=encounter_source_id,
                author_time=author_time,
            )
        )
    return candidates


def _build_procedure_entry(
    tree: ElementTreeType,
    candidate: ProcedureCandidate,
    ns: dict[str, str],
) -> Optional[ProcedureEntry]:
    """Create a ProcedureEntry from the candidate node."""
    node = candidate.node
    codes = _collect_codes(node.find("hl7:code", namespaces=ns), ns)
    name = _resolve_procedure_name(tree, node, ns, codes)
    if name is None:
        return None

    status_el = node.find("hl7:statusCode", namespaces=ns)
    status = normalize_whitespace(
        status_el.get("code") if isinstance(status_el, ElementType) else None
    )
    date, _ = extract_effective_time(node.find("hl7:effectiveTime", namespaces=ns), ns)
    notes = extract_notes(tree, node, ns)
    provider_name = extract_provider_name(
        node,
        "hl7:performer/hl7:assignedEntity/hl7:assignedPerson/hl7:name",
        "hl7:performer/hl7:assignedEntity/hl7:representedOrganization/hl7:name",
        ns,
    )

    return ProcedureEntry(
        name=name,
        codes=codes,
        status=status.title() if status else None,
        date=date,
        notes=notes,
        provider=provider_name,
        encounter_source_id=candidate.encounter_source_id,
        author_time=candidate.author_time,
    )


def parse_procedures(tree: ElementTreeType, ns: dict[str, str]) -> list[ProcedureEntry]:
    """Parse procedure entries from a CCD document."""
    procedures: list[ProcedureEntry] = []
    for section in _procedure_sections(tree, ns):
        code_el = section.find("hl7:code", namespaces=ns)
        section_code = normalize_whitespace(
            code_el.get("code") if code_el is not None else None
        )
        entries = section.findall("hl7:entry", namespaces=ns)
        for entry in iter_elements(entries):
            candidates = _candidate_procedures(entry, section_code, ns)
            for candidate in candidates:
                record = _build_procedure_entry(tree, candidate, ns)
                if record:
                    procedures.append(record)
    return procedures
