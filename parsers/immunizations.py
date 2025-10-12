from __future__ import annotations

# Purpose: Parse immunisation administrations from CCD documents.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Immunisation parsing helpers for CCD ingestion."""

from collections.abc import Iterable
from typing import Any

from lxml import etree

from .common import get_text_by_id

ImmunizationEntry = dict[str, Any]

CVX_CODE_SYSTEMS: set[str] = {
    "2.16.840.1.113883.12.292",  # CVX vaccination codes
    "2.16.840.1.113883.6.59",  # Legacy SNOMED/CVX mapping (occasionally used)
}


def _clean_text(value: str | None) -> str | None:
    """Trim and normalise whitespace in a narrative string."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return " ".join(cleaned.split())


def _extract_time(node: etree._Element | None, ns: dict[str, str]) -> str | None:
    """Extract a timestamp value from an ``effectiveTime`` element."""
    if node is None:
        return None
    value = node.get("value")
    if value:
        return value
    low = node.find("hl7:low", namespaces=ns)
    if low is not None and low.get("value"):
        return low.get("value")
    high = node.find("hl7:high", namespaces=ns)
    if high is not None and high.get("value"):
        return high.get("value")
    return None


def _collect_cvx_codes(code_element: etree._Element | None, ns: dict[str, str]) -> list[str]:
    """Collect CVX identifiers from a code element and its translations."""
    codes: list[str] = []
    if code_element is None:
        return codes

    def handle_element(element: etree._Element) -> None:
        code_value = element.get("code")
        code_system = element.get("codeSystem")
        if code_value and code_system in CVX_CODE_SYSTEMS:
            codes.append(code_value)
        translations = element.findall("hl7:translation", namespaces=ns)
        for translation in translations:
            handle_element(translation)

    handle_element(code_element)
    return codes


def _get_reference_text(
    tree: etree._ElementTree,
    ns: dict[str, str],
    parent: etree._Element | None,
    xpath: str,
) -> str | None:
    """Resolve a referenced narrative string relative to the provided parent."""
    if parent is None:
        return None
    ref = parent.find(xpath, namespaces=ns)
    if ref is None:
        return None
    ref_value = ref.get("value")
    if not ref_value:
        return None
    return _clean_text(get_text_by_id(tree, ns, ref_value))


def _ensure_element_list(value: object) -> list[etree._Element]:
    """Coerce XPath results into a list of XML elements."""
    if isinstance(value, list):
        return [node for node in value if isinstance(node, etree._Element)]
    if isinstance(value, etree._Element):
        return [value]
    return []


def _unique_non_empty(values: Iterable[str | None]) -> list[str]:
    """Return unique, cleaned string values while preserving order."""
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_text(value)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique


def parse_immunizations(tree: etree._ElementTree, ns: dict[str, str]) -> list[ImmunizationEntry]:
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
    section_nodes = _ensure_element_list(section_nodes_raw)
    section = section_nodes[0] if section_nodes else None
    if section is None or section.get("nullFlavor") == "NI":
        return immunizations

    admin_nodes_raw = section.xpath(
        "hl7:entry/hl7:substanceAdministration",
        namespaces=ns,
    )
    for admin in _ensure_element_list(admin_nodes_raw):
        status_el = admin.find("hl7:statusCode", namespaces=ns)
        status = status_el.get("code") if status_el is not None else None

        effective_time = _extract_time(admin.find("hl7:effectiveTime", namespaces=ns), ns)

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
            if not isinstance(raw_product, str):
                raw_product = str(raw_product or "")
            product_name = _clean_text(raw_product)

        name_candidates = [
            _clean_text(code_el.get("displayName")) if code_el is not None else None,
            _get_reference_text(tree, ns, code_el, "hl7:originalText/hl7:reference"),
            _get_reference_text(tree, ns, admin, "hl7:text/hl7:reference"),
            _clean_text(material_code_el.get("displayName")) if material_code_el is not None else None,
            _get_reference_text(tree, ns, material_code_el, "hl7:originalText/hl7:reference"),
            product_name,
            _clean_text(code_el.get("code")) if code_el is not None else None,
            _clean_text(material_code_el.get("code")) if material_code_el is not None else None,
        ]

        vaccine_name: str | None = None
        for candidate in name_candidates:
            if candidate:
                vaccine_name = candidate
                break

        lot_number_el = admin.find(
            "hl7:consumable/hl7:manufacturedProduct/hl7:manufacturedMaterial/hl7:lotNumberText",
            namespaces=ns,
        )
        lot_number = _clean_text(lot_number_el.text if lot_number_el is not None else None)

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
