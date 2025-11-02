# Purpose: Provide shared helper utilities for CCD parser modules.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Common helper functions for CCD parsing routines."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, Iterable, Optional, cast

from .xml_types import ElementType, ElementTreeType

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

__all__ = [
    "XSI_NS",
    "clean_text",
    "normalize_whitespace",
    "flatten_text",
    "first_non_empty",
    "first_text",
    "iter_elements",
    "ensure_element_list",
    "extract_effective_time",
    "get_text_by_id",
    "extract_provider_info",
    "extract_provider_name",
    "collect_template_ids",
    "extract_notes",
    "extract_status_code",
    "extract_encounter_id",
    "extract_encounter_details",
    "safe_xpath_text",
    "safe_xpath_attr",
]


def clean_text(value: object) -> str | None:
    """Coerce various text-like values into a trimmed string."""
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="ignore")
    else:
        text = str(value)
    text = text.strip()
    return text or None


def normalize_whitespace(value: object) -> str | None:
    """Return a whitespace-collapsed string value."""
    text = clean_text(value)
    if not text:
        return None
    return " ".join(text.split())


def iter_elements(value: object) -> list[ElementType]:
    """Return element nodes extracted from mixed XPath responses."""
    if isinstance(value, ElementType):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, ElementType)]
    return []


def ensure_element_list(value: object) -> list[ElementType]:
    """Alias for iter_elements for semantics in caller code."""
    return iter_elements(value)


def _string_value(node: ElementType) -> str | None:
    """Return the concatenated string content for an XML element."""
    result = node.xpath("string()")
    return clean_text(result)


def _text_candidates(value: object) -> list[str]:
    """Extract possible string values from a mixed XPath result."""
    texts: list[str] = []
    if isinstance(value, ElementType):
        text = _string_value(value)
        if text:
            texts.append(text)
    elif isinstance(value, (str, bytes)):
        text = clean_text(value)
        if text:
            texts.append(text)
    elif isinstance(value, Iterable):
        for item in value:
            texts.extend(_text_candidates(item))
    else:
        text = clean_text(value)
        if text:
            texts.append(text)
    return texts


def first_text(value: object) -> str | None:
    """Return the first string extracted from an XPath result."""
    for candidate in _text_candidates(value):
        return candidate
    return None


def flatten_text(node: ElementType) -> str | None:
    """Join all text descendants with single spaces for readability.

    Args:
        node: An XML element whose text content should be flattened.

    Returns:
        Normalised string with all descendant text nodes joined by spaces,
        or ``None`` if no text found.
    """
    text_nodes = node.xpath(".//text()")
    if not isinstance(text_nodes, list):
        return None

    fragments: list[str] = []
    for fragment in text_nodes:
        cleaned = clean_text(fragment)
        if cleaned:
            fragments.append(cleaned)
    if not fragments:
        return None
    combined = " ".join(fragments)
    return re.sub(r"\s+", " ", combined).strip() or None


def first_non_empty(*values: Optional[str]) -> Optional[str]:
    """Return the first non-empty string from the provided arguments."""
    for value in values:
        cleaned = clean_text(value)
        if cleaned:
            return cleaned
    return None


def extract_effective_time(
    node: ElementType | None,
    ns: dict[str, str],
) -> tuple[str | None, str | None]:
    """Return ``(start, end)`` timestamps from an HL7 ``effectiveTime``."""
    if node is None:
        return None, None
    value = clean_text(node.get("value"))
    if value:
        return value, value
    low = node.find("hl7:low", namespaces=ns)
    high = node.find("hl7:high", namespaces=ns)
    start = clean_text(low.get("value")) if isinstance(low, ElementType) else None
    end = clean_text(high.get("value")) if isinstance(high, ElementType) else None
    if end is None and start is not None:
        end = start
    return start, end


def get_text_by_id(
    tree: ElementTreeType,
    ns: dict[str, str],
    ref_value: str | None,
) -> str | None:
    """Resolve a text node in the CCD by its ID reference.

    Args:
        tree: Parsed CCD XML tree.
        ns: Namespace dictionary used for XPath lookups.
        ref_value: Attribute value referencing a node (e.g., ``#section-id``).

    Returns:
        The stripped text for the referenced node, or ``None`` if not found.
    """
    if not ref_value:
        return None

    ref_id = ref_value.lstrip("#")
    nodes = cast(Sequence[Any], tree.xpath(f"//*[@ID='{ref_id}']", namespaces=ns))
    for candidate in nodes:
        text_value = flatten_text(candidate) or first_text(candidate)
        if text_value:
            return text_value
    return None


def extract_provider_info(
    parent: ElementType,
    person_xpath: str | None,
    org_xpath: str | None,
    ns: dict[str, str],
) -> tuple[str | None, str | None]:
    """Extract both provider name and organization from a CCD section node.

    Args:
        parent: The XML element containing provider information.
        person_xpath: XPath for the individual practitioner's name.
        org_xpath: XPath for the organisation name.
        ns: Namespace dictionary used for the lookup.

    Returns:
        tuple: (provider_name, organization_name) where either may be None
    """
    provider_name = None
    org_name = None

    if person_xpath:
        person = parent.find(person_xpath, namespaces=ns)
        if person is not None:
            text = first_text(person)
            if text:
                provider_name = " ".join(text.split())

    if org_xpath:
        organization = parent.find(org_xpath, namespaces=ns)
        if organization is not None:
            text = first_text(organization)
            if text:
                org_name = " ".join(text.split())

    return provider_name, org_name


def extract_provider_name(
    parent: ElementType,
    person_xpath: str | None,
    org_xpath: str | None,
    ns: dict[str, str],
    *,
    allow_org_fallback: bool = True,
) -> str | None:
    """Return a human-readable provider name from a CCD section node.

    Args:
        parent: The XML element containing provider information.
        person_xpath: XPath for the individual practitioner's name.
        org_xpath: XPath for the organisation name.
        ns: Namespace dictionary used for the lookup.
        allow_org_fallback: When ``False``, skip organisation fallback.

    Returns:
        A cleaned provider display name, or ``None`` if unavailable.
    """
    provider_name, org_name = extract_provider_info(parent, person_xpath, org_xpath, ns)

    if provider_name:
        return provider_name
    if allow_org_fallback and org_name:
        return org_name

    return None


def collect_template_ids(
    node: ElementType,
    ns: dict[str, str],
) -> set[str]:
    """Return the templateId roots associated with an element."""
    roots: set[str] = set()
    template_nodes = node.findall("hl7:templateId", namespaces=ns)
    for template in iter_elements(template_nodes):
        root = clean_text(template.get("root"))
        if root:
            roots.add(root)
    return roots


def extract_notes(
    tree: ElementTreeType,
    node: ElementType,
    ns: dict[str, str],
    *,
    text_xpath: str = "hl7:text",
) -> Optional[str]:
    """Return note content associated with the provided node."""
    text_ref = node.find(f"{text_xpath}/hl7:reference", namespaces=ns)
    if text_ref is not None and text_ref.get("value"):
        note = normalize_whitespace(get_text_by_id(tree, ns, text_ref.get("value")))
        if note:
            return note
    text_el = node.find(text_xpath, namespaces=ns)
    if text_el is not None:
        note = normalize_whitespace(text_el.xpath("string()"))
        if note:
            return note
    return None


def extract_status_code(
    node: ElementType,
    ns: dict[str, str] | None = None,
) -> Optional[str]:
    """Return a normalised status code from the node."""
    status_node = (
        node.find("hl7:statusCode", namespaces=ns)
        if ns
        else node.find("hl7:statusCode")
    )
    if status_node is None:
        return None
    return normalize_whitespace(status_node.get("code"))


def extract_encounter_id(
    element: ElementType | None,
    ns: dict[str, str] | None = None,
) -> Optional[str]:
    """Return encounter identifier (extension or root)."""
    if element is None:
        return None
    if ns:
        id_el = element.find("hl7:id", namespaces=ns)
    else:
        id_el = element.find("hl7:id")
    if id_el is None:
        return None
    return clean_text(id_el.get("extension") or id_el.get("root"))


def extract_encounter_details(
    element: ElementType | None,
    ns: dict[str, str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return encounter identifier and timing information."""
    if element is None:
        return None, None, None
    source_id = extract_encounter_id(element, ns)
    start, end = extract_effective_time(
        element.find("hl7:effectiveTime", namespaces=ns),
        ns,
    )
    return source_id, start, end


def safe_xpath_text(
    element: ElementType, path: str, ns: dict[str, str]
) -> str | None:
    """Safely extract text using xpath, with namespace fallback.

    Handles documents where namespace prefixes may not be declared
    by falling back to unprefixed XPath queries.

    Args:
        element: XML element to query.
        path: XPath expression (may include hl7: prefix).
        ns: Namespace dictionary mapping prefixes to URIs.

    Returns:
        First matching text content or None.
    """
    try:
        results = element.xpath(f"{path}/text()", namespaces=ns)
        return results[0] if results else None
    except (KeyError, AttributeError):  # Namespace not found or xpath failed
        try:
            simple_path = path.replace("hl7:", "").replace("//", "/")
            results = element.xpath(f".//{simple_path}/text()")
            return results[0] if results else None
        except (KeyError, AttributeError):
            return None


def safe_xpath_attr(
    element: ElementType, path: str, attr: str, ns: dict[str, str]
) -> str | None:
    """Safely extract attribute using xpath, with namespace fallback.

    Handles documents where namespace prefixes may not be declared
    by falling back to unprefixed XPath queries.

    Args:
        element: XML element to query.
        path: XPath expression (may include hl7: prefix).
        attr: Attribute name to extract.
        ns: Namespace dictionary mapping prefixes to URIs.

    Returns:
        Attribute value or None.
    """
    try:
        results = element.xpath(f"{path}/@{attr}", namespaces=ns)
        return results[0] if results else None
    except (KeyError, AttributeError):  # Namespace not found or xpath failed
        try:
            simple_path = path.replace("hl7:", "").replace("//", "/")
            results = element.xpath(f".//{simple_path}/@{attr}")
            return results[0] if results else None
        except (KeyError, AttributeError):
            return None
