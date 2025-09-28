from __future__ import annotations

from typing import Optional

from lxml import etree

XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def get_text_by_id(tree: etree._ElementTree, ns: dict[str, str], ref_value: Optional[str]) -> Optional[str]:
    if not ref_value:
        return None
    ref_id = ref_value.lstrip("#")
    nodes = tree.xpath(f"//*[@ID='{ref_id}']", namespaces=ns)
    if nodes:
        text_value = nodes[0].xpath("string()")
        if text_value:
            return text_value.strip()
    return None


def extract_provider_name(
    parent: etree._Element,
    person_xpath: str,
    org_xpath: str,
    ns: dict[str, str],
) -> Optional[str]:
    person = parent.find(person_xpath, namespaces=ns)
    if person is not None:
        text = person.xpath("string()")
        if text:
            return " ".join(text.split())
    organization = parent.find(org_xpath, namespaces=ns)
    if organization is not None:
        text = organization.xpath("string()")
        if text:
            return " ".join(text.split())
    return None
