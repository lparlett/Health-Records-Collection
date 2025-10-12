from __future__ import annotations

# Purpose: Provide shared helper utilities for CCD parser modules.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Common helper functions for CCD parsing routines."""

from typing import Any, Sequence, cast

from lxml import etree

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def _string_value(node: etree._Element) -> str | None:
    """Return the concatenated string content for an XML element."""
    result = node.xpath("string()")
    return _normalize_text(result)


def _normalize_text(value: object) -> str | None:
    """Coerce various text-like XPath results into a trimmed string."""
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


def _iter_text_candidates(value: object) -> list[str]:
    """Extract possible string values from a mixed XPath result."""
    texts: list[str] = []
    if isinstance(value, etree._Element):
        text = _string_value(value)
        if text:
            texts.append(text)
    elif isinstance(value, (str, bytes)):
        text = _normalize_text(value)
        if text:
            texts.append(text)
    elif isinstance(value, (list, tuple)):
        for item in value:
            texts.extend(_iter_text_candidates(item))
    else:
        text = _normalize_text(value)
        if text:
            texts.append(text)
    return texts


def _first_text(value: object) -> str | None:
    """Return the first string extracted from an XPath result."""
    for candidate in _iter_text_candidates(value):
        return candidate
    return None


def get_text_by_id(tree: etree._ElementTree, ns: dict[str, str], ref_value: str | None) -> str | None:
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
        text_value = _first_text(candidate)
        if text_value:
            return text_value
    return None


def extract_provider_name(
    parent: etree._Element,
    person_xpath: str,
    org_xpath: str,
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
    person = parent.find(person_xpath, namespaces=ns)
    text = _first_text(person)
    if text:
        return " ".join(text.split())

    if allow_org_fallback:
        organization = parent.find(org_xpath, namespaces=ns)
        text = _first_text(organization)
        if text:
            return " ".join(text.split())

    return None
