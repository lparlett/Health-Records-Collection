from __future__ import annotations

from typing import Dict, List, Optional

from lxml import etree

from .common import XSI_NS, extract_provider_name

LabEntry = Dict[str, Optional[str]]


def parse_labs(tree: etree._ElementTree, ns: dict[str, str]) -> List[LabEntry]:
    labs: List[LabEntry] = []
    results_section_nodes = tree.xpath(
        ".//hl7:section[hl7:code[@code='30954-2']]",
        namespaces=ns,
    )
    results_section = results_section_nodes[0] if results_section_nodes else None
    if results_section is not None and results_section.get("nullFlavor") != "NI":
        for organizer in results_section.findall("hl7:entry/hl7:organizer", namespaces=ns):
            organizer_flag: Optional[str] = None
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
            encounter_source_id: Optional[str] = None
            encounter_start: Optional[str] = None
            encounter_end: Optional[str] = None
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
            for obs in lab_observations:
                code_el = obs.find("hl7:code", namespaces=ns)
                if code_el is None:
                    print("Skipping observation: no <code> element")
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
                    panel_flag: Optional[str] = None
                    if panel_val_el is not None:
                        panel_flag = panel_val_el.get("value")
                        if not panel_flag:
                            text_val = (panel_val_el.text or "").strip()
                            if not text_val:
                                text_val = panel_val_el.xpath("string()").strip()
                            panel_flag = (
                                text_val
                                or panel_val_el.get("displayName")
                                or panel_val_el.get("code")
                            )
                    if panel_flag:
                        organizer_flag = panel_flag
                    continue

                loinc = code
                test_name = display_name or code_el.findtext("hl7:originalText", namespaces=ns)
                if not test_name:
                    test_name = loinc

                val_el = obs.find("hl7:value", namespaces=ns)
                value: Optional[str] = None
                unit: Optional[str] = None
                if val_el is not None:
                    xsi_type = val_el.get(f"{{{XSI_NS}}}type")
                    if val_el.get("value"):
                        value = val_el.get("value")
                    else:
                        text_val = (val_el.text or "").strip()
                        if not text_val:
                            text_val = val_el.xpath("string()").strip()
                        value = text_val or val_el.get("displayName") or val_el.get("code")
                    unit = val_el.get("unit")
                    if not unit and xsi_type in {"CD", "CE", "CV"}:
                        unit = val_el.get("codeSystemName")
                if not value:
                    continue

                date: Optional[str] = None
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

                ref_range: Optional[str] = None
                ref_text = obs.findtext(
                    ".//hl7:referenceRange//hl7:observationRange//hl7:text",
                    namespaces=ns,
                )
                if ref_text:
                    ref_range = ref_text.strip()

                abnormal_flag: Optional[str] = None
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

