from __future__ import annotations

# Purpose: Parse laboratory results from CCD documents into structured entries.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Laboratory result parsing helpers for CCD ingestion."""

import logging
from typing import Any, Sequence, cast

from lxml import etree

from .common import XSI_NS, extract_provider_name

logger = logging.getLogger(__name__)

LabEntry = dict[str, Any]


def _ensure_element_list(value: object) -> list[etree._Element]:
    """Return a flat list of element nodes extracted from XPath results."""
    elements: list[etree._Element] = []
    if isinstance(value, etree._Element):
        elements.append(value)
    elif isinstance(value, Sequence):
        for item in value:
            if isinstance(item, etree._Element):
                elements.append(item)
    return elements


def _coerce_text(value: object) -> str | None:
    """Normalise mixed text representations into a trimmed string."""
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


def parse_labs(tree: etree._ElementTree, ns: dict[str, str]) -> list[LabEntry]:
    """Parse lab results documented within a CCD.

    Args:
        tree: Root XML tree representing the CCD document.
        ns: Namespace dictionary used for XPath lookups.

    Returns:
        list[LabEntry]: Normalised laboratory observations.
    """
    labs: list[LabEntry] = []
    results_section_nodes = cast(
        Sequence[Any],
        tree.xpath(
        ".//hl7:section[hl7:code[@code='30954-2']]",
        namespaces=ns,
    ),
    )
    results_section = next(iter(_ensure_element_list(results_section_nodes)), None)
    if results_section is None or results_section.get("nullFlavor") == "NI":
        return labs

    organizer_nodes = results_section.findall("hl7:entry/hl7:organizer", namespaces=ns)
    for organizer in _ensure_element_list(organizer_nodes):
        organizer_flag: str | None = None
        ordering_provider_name = extract_provider_name(
            organizer,
            "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
            "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
            ns,
        )
        performing_org_name = extract_provider_name(
            organizer,
            "hl7:performer/hl7:assignedEntity/hl7:assignedPerson/hl7:name",
            "hl7:performer/hl7:assignedEntity/hl7:representedOrganization/hl7:name",
            ns,
        )
        encounter_el = organizer.find(".//hl7:encounter", namespaces=ns)
        encounter_source_id: str | None = None
        encounter_start: str | None = None
        encounter_end: str | None = None
        if encounter_el is not None:
            encounter_id_el = encounter_el.find("hl7:id", namespaces=ns)
            if encounter_id_el is not None:
                encounter_source_id = encounter_id_el.get("extension") or encounter_id_el.get("root")
            eff_el = encounter_el.find("hl7:effectiveTime", namespaces=ns)
            if eff_el is not None:
                value = eff_el.get("value")
                if value:
                    encounter_start = value
                    encounter_end = value
                else:
                    low_el = eff_el.find("hl7:low", namespaces=ns)
                    high_el = eff_el.find("hl7:high", namespaces=ns)
                    if low_el is not None and low_el.get("value"):
                        encounter_start = low_el.get("value")
                    if high_el is not None and high_el.get("value"):
                        encounter_end = high_el.get("value")

        lab_observations = organizer.findall("hl7:component/hl7:observation", namespaces=ns)
        for obs in _ensure_element_list(lab_observations):
            code_el = obs.find("hl7:code", namespaces=ns)
            if code_el is None:
                logger.debug("Skipping observation without <code> element.")
                continue

            code = code_el.get("code")
            code_system = code_el.get("codeSystem")
            code_system_name = code_el.get("codeSystemName")
            display_name = code_el.get("displayName")

            if not (
                code_system == "2.16.840.1.113883.6.1"
                or (code_system_name and code_system_name.upper() == "LOINC")
            ):
                continue
            if not code:
                continue
            if code == "56850-1":
                panel_val_el = obs.find("hl7:value", namespaces=ns)
                panel_flag: str | None = None
                if panel_val_el is not None:
                    panel_flag = _coerce_text(panel_val_el.get("value"))
                    if not panel_flag:
                        text_val = _coerce_text(panel_val_el.text) or _coerce_text(panel_val_el.xpath("string()"))
                        panel_flag = (
                            text_val
                            or _coerce_text(panel_val_el.get("displayName"))
                            or _coerce_text(panel_val_el.get("code"))
                        )
                if panel_flag:
                    organizer_flag = panel_flag
                continue

            loinc = code
            display_name_clean = _coerce_text(display_name)
            original_text = _coerce_text(obs.findtext("hl7:code/hl7:originalText", namespaces=ns))
            test_name = display_name_clean or original_text
            if not test_name:
                test_name = loinc

            val_el = obs.find("hl7:value", namespaces=ns)
            value: str | None = None
            unit: str | None = None
            if val_el is not None:
                xsi_type = val_el.get(f"{{{XSI_NS}}}type")
                raw_value = val_el.get("value")
                if raw_value:
                    value = raw_value
                else:
                    text_val = _coerce_text(val_el.text) or _coerce_text(val_el.xpath("string()"))
                    value = text_val or _coerce_text(val_el.get("displayName")) or _coerce_text(val_el.get("code"))
                unit = _coerce_text(val_el.get("unit"))
                if not unit and xsi_type in {"CD", "CE", "CV"}:
                    unit = _coerce_text(val_el.get("codeSystemName"))
            if not value:
                continue

            date: str | None = None
            eff = obs.find("hl7:effectiveTime", namespaces=ns)
            if eff is not None:
                if eff.get("value"):
                    date = eff.get("value")
                else:
                    low = eff.find("hl7:low", namespaces=ns)
                    high = eff.find("hl7:high", namespaces=ns)
                    if low is not None and low.get("value"):
                        date = low.get("value")
                    elif high is not None and high.get("value"):
                        date = high.get("value")

            ref_range: str | None = None
            ref_text = obs.findtext(
                ".//hl7:referenceRange//hl7:observationRange//hl7:text",
                namespaces=ns,
            )
            if ref_text:
                ref_range = _coerce_text(ref_text)

            abnormal_flag: str | None = None
            interp = obs.find("hl7:interpretationCode", namespaces=ns)
            if interp is not None:
                abnormal_flag = interp.get("code") or interp.get("displayName")
            if not abnormal_flag:
                interp = obs.find(
                    ".//hl7:referenceRange//hl7:interpretationCode",
                    namespaces=ns,
                )
                if interp is not None:
                    abnormal_flag = interp.get("code") or interp.get("displayName")
            if not abnormal_flag and organizer_flag:
                abnormal_flag = organizer_flag

            obs_ordering = extract_provider_name(
                obs,
                "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
                "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
                ns,
            )
            obs_performing = extract_provider_name(
                obs,
                "hl7:performer/hl7:assignedEntity/hl7:assignedPerson/hl7:name",
                "hl7:performer/hl7:assignedEntity/hl7:representedOrganization/hl7:name",
                ns,
            )
            ordering_name = obs_ordering or ordering_provider_name
            performing_name = obs_performing or performing_org_name

            labs.append(
                {
                    "encounter_source_id": encounter_source_id,
                    "encounter_start": encounter_start,
                    "encounter_end": encounter_end,
                    "test_name": test_name,
                    "loinc": loinc,
                    "value": value,
                    "unit": unit,
                    "reference_range": ref_range,
                    "abnormal_flag": abnormal_flag,
                    "date": date,
                    "ordering_provider": ordering_name,
                    "performing_org": performing_name,
                }
            )

    return labs
