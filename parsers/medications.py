"""Medication extraction utilities for CCD documents.

This module provides functions to parse and extract medication administration details
from Continuity of Care Document (CCD) XML files. It focuses on 
identifying medication entries, including their names, dosages, 
routes, frequencies, start and end dates, statuses, notes, providers, 
and RxNorm codes.
"""

from __future__ import annotations

from typing import List, Optional, TypedDict

from lxml import etree

from .common import XSI_NS, extract_provider_name, get_text_by_id



class MedicationEntry(TypedDict, total=False):
    name: Optional[str]
    rxnorm: Optional[str]
    dose: Optional[str]
    route: Optional[str]
    frequency: Optional[str]
    start: Optional[str]
    end: Optional[str]
    status: Optional[str]
    notes: Optional[str]
    provider: Optional[str]
    author_time: Optional[str]
    source_id: Optional[str]


def parse_medications(tree: etree._ElementTree, 
                      ns: dict[str, str]) -> List[MedicationEntry]:
    """Extract medication administrations from a CCD document.

    Args:
        tree: The XML tree of the CCD document.
        ns: The namespace mapping for XPath queries.
    Returns:
        A list of dictionaries, each representing a medication entry 
        with details.
    """
    medications: List[MedicationEntry] = []
    raw_med_nodes = tree.xpath(
        ".//hl7:substanceAdministration[hl7:templateId[@root='2.16.840.1.113883.10.20.22.4.16']]",
        namespaces=ns,
    )
    if not isinstance(raw_med_nodes, list):
        return medications

    for med in [node for node in raw_med_nodes if isinstance(node, etree._Element)]:
        code_el = med.find(".//hl7:manufacturedMaterial/hl7:code", namespaces=ns)
        med_name: Optional[str] = None
        rxnorm_code: Optional[str] = None
        if code_el is not None:
            med_name = (code_el.get("displayName") or "").strip() or None
            rxnorm_code = (code_el.get("code") or "").strip() or None
            if not med_name:
                ref = code_el.find("hl7:originalText/hl7:reference", namespaces=ns)
                if ref is not None and ref.get("value"):
                    med_name = get_text_by_id(tree, ns, ref.get("value"))

        sig_text: Optional[str] = None
        sig_ref = med.find("hl7:text/hl7:reference", namespaces=ns)
        if sig_ref is not None and sig_ref.get("value"):
            sig_text = get_text_by_id(tree, ns, sig_ref.get("value"))
        med_id = None
        id_el = med.find("hl7:id", namespaces=ns)
        if id_el is not None:
            med_id = id_el.get("extension") or id_el.get("root")

        author_time = None
        author_time_el = med.find("hl7:author/hl7:time", namespaces=ns)
        if author_time_el is not None:
            author_time = author_time_el.get("value")

        provider_name = extract_provider_name(
            med,
            "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
            "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
            ns,
        )


        start_el = med.find("hl7:effectiveTime/hl7:low", namespaces=ns)
        start = start_el.get("value") if start_el is not None else None
        end_el = med.find("hl7:effectiveTime/hl7:high", namespaces=ns)
        end = end_el.get("value") if end_el is not None else None

        route_el = med.find("hl7:routeCode", namespaces=ns)
        route: Optional[str] = None
        if route_el is not None:
            route = (route_el.get("displayName") or route_el.get("code") or "").strip() or None
            if not route:
                route = (route_el.findtext("hl7:originalText", namespaces=ns) or "").strip() or None

        dose: Optional[str] = None
        dose_el = med.find("hl7:doseQuantity", namespaces=ns)
        if dose_el is not None:
            dose_value = (dose_el.get("value") or "").strip()
            dose_unit = (dose_el.get("unit") or "").strip()
            if dose_value or dose_unit:
                dose = " ".join([part for part in (dose_value, dose_unit) if part])

        frequency: Optional[str] = None
        for eff in med.findall("hl7:effectiveTime", namespaces=ns):
            xsi_type = eff.get(f"{{{XSI_NS}}}type")
            if xsi_type and xsi_type.upper() == "PIVL_TS":
                period = eff.find("hl7:period", namespaces=ns)
                if period is not None:
                    period_value = (period.get("value") or "").strip()
                    period_unit = (period.get("unit") or "").strip()
                    if period_value and period_unit:
                        frequency = f"Every {period_value} {period_unit}"
                    elif period_unit:
                        frequency = f"Every {period_unit}"
                    elif period_value:
                        frequency = f"Every {period_value}"
                if not frequency:
                    freq_text = eff.findtext("hl7:originalText", namespaces=ns)
                    if freq_text:
                        frequency = freq_text.strip()
                break

        status: Optional[str] = None
        raw_status_nodes = med.xpath(
            "hl7:entryRelationship/hl7:observation[hl7:code[@code='33999-4']]/hl7:value",
            namespaces=ns,
        )
        status_nodes = [el for el in raw_status_nodes if isinstance(el, etree._Element)]
        status_value = status_nodes[0] if status_nodes else None
        if status_value is not None:
            status = (status_value.get("displayName") or status_value.get("code") or "").strip() or None
        if status is None:
            status_code_el = med.find("hl7:statusCode", namespaces=ns)
            if status_code_el is not None:
                status = (status_code_el.get("code") or "").strip() or None
        if status:
            status = status.title()

        if not med_name:
            if sig_text:
                med_name = sig_text
            elif rxnorm_code:
                med_name = rxnorm_code
        if not med_name:
            continue

        medications.append(
            {
                "name": med_name,
                "rxnorm": rxnorm_code,
                "dose": dose,
                "route": route,
                "frequency": frequency,
                "start": start,
                "end": end,
                "status": status,
                "notes": sig_text,
                "provider": provider_name,
                "author_time": author_time,
                "source_id": med_id,
            }
        )

    return medications
