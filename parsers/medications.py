"""Medication extraction utilities for CCD documents.""" 
from __future__ import annotations

from typing import List, Optional, Set, Tuple, TypedDict

from lxml import etree

from .common import XSI_NS, extract_provider_name, get_text_by_id

MedicationKey = Tuple[str, str, str, str, str]


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
    encounter_source_id: Optional[str]
    encounter_start: Optional[str]
    encounter_end: Optional[str]
    patient_id: Optional[str]
    start_bucket: Optional[str]
    end_bucket: Optional[str]


def _bucket_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    digits = ''.join(ch for ch in value if ch.isdigit())
    if len(digits) >= 8:
        return digits[:8]
    stripped = value.strip()
    return stripped or None


def _extract_encounter_details(
    encounter_el: Optional[etree._Element],
    ns: dict[str, str],
    *,
    synthetic_prefix: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if encounter_el is None:
        return None, None, None

    encounter_source_id: Optional[str] = None
    for id_el in encounter_el.findall("hl7:id", namespaces=ns):
        extension = (id_el.get("extension") or "").strip()
        root = (id_el.get("root") or "").strip()
        if extension:
            encounter_source_id = extension
            break
        if root:
            encounter_source_id = root
            break

    encounter_start: Optional[str] = None
    encounter_end: Optional[str] = None
    eff_el = encounter_el.find("hl7:effectiveTime", namespaces=ns)
    if eff_el is not None:
        value = (eff_el.get("value") or "").strip()
        if value:
            encounter_start = value
            encounter_end = value
        else:
            low_el = eff_el.find("hl7:low", namespaces=ns)
            high_el = eff_el.find("hl7:high", namespaces=ns)
            if low_el is not None:
                low_val = (low_el.get("value") or "").strip()
                if low_val:
                    encounter_start = low_val
            if high_el is not None:
                high_val = (high_el.get("value") or "").strip()
                if high_val:
                    encounter_end = high_val
            if encounter_end is None and encounter_start is not None:
                encounter_end = encounter_start

    return encounter_source_id, encounter_start, encounter_end


def _find_medication_encounter(
    med_el: etree._Element, ns: dict[str, str]
) -> Optional[etree._Element]:
    candidates: List[Tuple[str, etree._Element]] = []
    for entry_rel in med_el.findall("hl7:entryRelationship", namespaces=ns):
        type_code = (entry_rel.get("typeCode") or "").strip().upper()
        raw_encounters = entry_rel.xpath(
            ".//hl7:encounter | .//hl7:externalEncounter",
            namespaces=ns,
        )
        if not isinstance(raw_encounters, list):
            continue
        for encounter in raw_encounters:
            if isinstance(encounter, etree._Element):
                candidates.append((type_code, encounter))

    if candidates:
        for preferred in ("SUBJ", "REFR", "COMP"):
            for type_code, encounter in candidates:
                if type_code == preferred:
                    return encounter
        return candidates[0][1]

    fallback = med_el.find(".//hl7:encounter", namespaces=ns)
    if fallback is not None:
        return fallback
    return med_el.find(".//hl7:externalEncounter", namespaces=ns)


def _extract_patient_id(tree: etree._ElementTree, ns: dict[str, str]) -> Optional[str]:
    patient_ids = tree.xpath(
        ".//hl7:recordTarget/hl7:patientRole/hl7:id",
        namespaces=ns,
    )
    if isinstance(patient_ids, list):
        for id_el in patient_ids:
            if isinstance(id_el, etree._Element):
                extension = (id_el.get("extension") or "").strip()
                root = (id_el.get("root") or "").strip()
                if extension:
                    return extension
                if root:
                    return root
    return None


def parse_medications(
    tree: etree._ElementTree,
    ns: dict[str, str],
    existing_keys: Optional[Set[MedicationKey]] = None,
) -> List[MedicationEntry]:
    root = tree.getroot() if isinstance(tree, etree._ElementTree) else None
    encompassing_encounter = None
    service_event = None
    if isinstance(root, etree._Element):
        encompassing_encounter = root.find(
            "hl7:componentOf/hl7:encompassingEncounter",
            namespaces=ns,
        )
        service_event = root.find(
            "hl7:documentationOf/hl7:serviceEvent",
            namespaces=ns,
        )
    if encompassing_encounter is None and service_event is None:
        return []

    medications: List[MedicationEntry] = []
    raw_med_nodes = tree.xpath(
        ".//hl7:substanceAdministration[hl7:templateId[@root='2.16.840.1.113883.10.20.22.4.16']]",
        namespaces=ns,
    )
    if not isinstance(raw_med_nodes, list):
        return medications

    doc_encounter_el = tree.find(
        "hl7:componentOf/hl7:encompassingEncounter",
        namespaces=ns,
    )
    doc_prefix = "doc_encounter" if doc_encounter_el is not None else None
    (
        doc_encounter_id,
        doc_encounter_start,
        doc_encounter_end,
    ) = _extract_encounter_details(
        doc_encounter_el,
        ns,
        synthetic_prefix=doc_prefix,
    )

    patient_id = _extract_patient_id(tree, ns) or "unknown_patient"

    seen_entries: Set[MedicationKey] = set()
    registry = existing_keys if existing_keys is not None else None

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
            med_id = (id_el.get("extension") or id_el.get("root") or "").strip() or None

        author_time = None
        author_time_el = med.find("hl7:author/hl7:time", namespaces=ns)
        if author_time_el is not None:
            value = (author_time_el.get("value") or "").strip()
            author_time = value or None

        provider_name = extract_provider_name(
            med,
            "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
            "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
            ns,
        )

        med_encounter_el = _find_medication_encounter(med, ns)
        med_prefix = "encounter" if med_encounter_el is not None else None
        (
            encounter_source_id,
            encounter_start,
            encounter_end,
        ) = _extract_encounter_details(
            med_encounter_el,
            ns,
            synthetic_prefix=med_prefix,
        )

        if not encounter_source_id and doc_encounter_id:
            encounter_source_id = doc_encounter_id
        if not encounter_start and doc_encounter_start:
            encounter_start = doc_encounter_start
        if not encounter_end and doc_encounter_end:
            encounter_end = doc_encounter_end

        start_el = med.find("hl7:effectiveTime/hl7:low", namespaces=ns)
        start = start_el.get("value") if start_el is not None else None
        end_el = med.find("hl7:effectiveTime/hl7:high", namespaces=ns)
        end = end_el.get("value") if end_el is not None else None
        start_bucket = _bucket_date(start)
        end_bucket = _bucket_date(end)

        route_el = med.find("hl7:routeCode", namespaces=ns)
        route: Optional[str] = None
        if route_el is not None:
            route = (
                route_el.get("displayName")
                or route_el.get("code")
                or ""
            ).strip() or None
            if not route:
                route = (
                    route_el.findtext("hl7:originalText", namespaces=ns) or ""
                ).strip() or None

        dose: Optional[str] = None
        dose_el = med.find("hl7:doseQuantity", namespaces=ns)
        if dose_el is not None:
            dose_value = (dose_el.get("value") or "").strip()
            dose_unit = (dose_el.get("unit") or "").strip()
            if dose_value or dose_unit:
                dose = " ".join(part for part in (dose_value, dose_unit) if part)

        frequency: Optional[str] = None
        for eff in med.findall("hl7:effectiveTime", namespaces=ns):
            xsi_type = (eff.get(f"{{{XSI_NS}}}type") or "").upper()
            if xsi_type == "PIVL_TS":
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
        if isinstance(raw_status_nodes, list):
            status_nodes = [el for el in raw_status_nodes if isinstance(el, etree._Element)]
        else:
            status_nodes = []
        status_value = status_nodes[0] if status_nodes else None
        if status_value is not None:
            status = (
                status_value.get("displayName")
                or status_value.get("code")
                or ""
            ).strip() or None
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

        entry: MedicationEntry = {
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
            "encounter_source_id": encounter_source_id,
            "encounter_start": encounter_start,
            "encounter_end": encounter_end,
            "patient_id": patient_id,
            "start_bucket": start_bucket,
            "end_bucket": end_bucket,
        }

        encounter_key = (encounter_source_id or "").strip() if encounter_source_id else ""
        name_key = (med_name or "").strip().lower()
        dose_key = (dose or "").strip().lower()
        start_key = start_bucket or (start or "").strip()
        dedupe_key: MedicationKey = (
            patient_id,
            encounter_key,
            name_key,
            dose_key,
            start_key,
        )
        if dedupe_key in seen_entries:
            continue
        if registry is not None and dedupe_key in registry:
            continue
        seen_entries.add(dedupe_key)
        if registry is not None:
            registry.add(dedupe_key)

        medications.append(entry)

    return medications
