# Purpose: Parse immunisation administrations from CCD documents.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Immunisation parsing helpers for CCD ingestion."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .common import (
    ensure_element_list,
    extract_effective_time,
    extract_notes,
    first_non_empty,
    normalize_whitespace,
)
from .xml_types import ElementType, ElementTreeType

ImmunizationEntry = dict[str, Any]

CVX_CODE_SYSTEMS: set[str] = {
    "2.16.840.1.113883.12.292",  # CVX vaccination codes
    "2.16.840.1.113883.6.59",  # Legacy SNOMED/CVX mapping (occasionally used)
}


def _collect_cvx_codes(
    code_element: ElementType | None, ns: dict[str, str]
) -> list[str]:
    """Collect CVX identifiers from a code element and its translations."""
    codes: list[str] = []
    if code_element is None:
        return codes

    def handle_element(element: ElementType) -> None:
        code_value = element.get("code")
        code_system = element.get("codeSystem")
        if code_value and code_system in CVX_CODE_SYSTEMS:
            codes.append(code_value)
        translations = element.findall("hl7:translation", namespaces=ns)
        for translation in translations:
            handle_element(translation)

    handle_element(code_element)
    return codes


def _unique_non_empty(values: Iterable[str | None]) -> list[str]:
    """Return unique, cleaned string values while preserving order."""
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = normalize_whitespace(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique


def parse_immunizations(
    tree: ElementTreeType, ns: dict[str, str]
) -> list[ImmunizationEntry]:
    """Parse administered immunisations from a CCD document.

    Args:
        tree: Root XML tree representing the CCD.
        ns: Namespace dictionary used for XPath lookups.

    Returns:
        list[ImmunizationEntry]: Normalised vaccine administration entries.
    """
    immunizations: list[ImmunizationEntry] = []
    section_nodes_raw = tree.xpath(
        ".//hl7:section[hl7:code[@code='11369-6']]",
        namespaces=ns,
    )
    section_nodes = ensure_element_list(section_nodes_raw)
    section = section_nodes[0] if section_nodes else None
    if section is None or section.get("nullFlavor") == "NI":
        return immunizations

    admin_nodes_raw = section.xpath(
        "hl7:entry/hl7:substanceAdministration",
        namespaces=ns,
    )
    for admin in ensure_element_list(admin_nodes_raw):
        status_el = admin.find("hl7:statusCode", namespaces=ns)
        status = normalize_whitespace(
            status_el.get("code") if status_el is not None else None
        )

        start, end = extract_effective_time(
            admin.find("hl7:effectiveTime", namespaces=ns),
            ns,
        )
        effective_time = start or end

        code_el = admin.find("hl7:code", namespaces=ns)
        material_code_el = admin.find(
            "hl7:consumable/hl7:manufacturedProduct/hl7:manufacturedMaterial/hl7:code",
            namespaces=ns,
        )

        material_name_el = admin.find(
            "hl7:consumable/hl7:manufacturedProduct/hl7:manufacturedMaterial/hl7:name",
            namespaces=ns,
        )
        product_name: str | None = None
        if material_name_el is not None:
            raw_product = material_name_el.xpath("string()")
            product_name = normalize_whitespace(raw_product)

        name_candidates = [
            (
                normalize_whitespace(code_el.get("displayName"))
                if code_el is not None
                else None
            ),
            (
                extract_notes(tree, code_el, ns, text_xpath="hl7:originalText")
                if code_el is not None
                else None
            ),
            extract_notes(tree, admin, ns),
            (
                normalize_whitespace(material_code_el.get("displayName"))
                if material_code_el is not None
                else None
            ),
            (
                extract_notes(tree, material_code_el, ns, text_xpath="hl7:originalText")
                if material_code_el is not None
                else None
            ),
            product_name,
            normalize_whitespace(code_el.get("code")) if code_el is not None else None,
            (
                normalize_whitespace(material_code_el.get("code"))
                if material_code_el is not None
                else None
            ),
        ]
        vaccine_name = first_non_empty(*name_candidates)

        lot_number_el = admin.find(
            "hl7:consumable/hl7:manufacturedProduct/hl7:manufacturedMaterial/hl7:lotNumberText",
            namespaces=ns,
        )
        lot_number = normalize_whitespace(
            lot_number_el.text if lot_number_el is not None else None
        )

        cvx_codes = _collect_cvx_codes(code_el, ns)
        if material_code_el is not None:
            cvx_codes.extend(_collect_cvx_codes(material_code_el, ns))

        entry: ImmunizationEntry = {
            "vaccine_name": vaccine_name,
            "date": effective_time,
            "status": status,
            "cvx_codes": _unique_non_empty(cvx_codes),
            "product_name": product_name,
            "lot_number": lot_number,
        }
        immunizations.append(entry)

    return immunizations
