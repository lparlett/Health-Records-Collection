# Purpose: Parse CCD medication sections into structured administration records.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Medication extraction utilities for CCD documents.

This module provides functions to parse and extract medication administration details
from Continuity of Care Document (CCD) XML files. It focuses on identifying medication
entries, including their names, dosages, routes, frequencies, start and end dates,
statuses, notes, providers, and RxNorm codes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from .common import (
    XSI_NS,
    clean_text,
    extract_provider_name,
    get_text_by_id,
    normalize_whitespace,
)
from .xml_types import ElementType, ElementTreeType


@dataclass(slots=True)
class DocumentContext:
    patient_id: str
    encounter_id: str | None
    encounter_start: str | None
    encounter_end: str | None


@dataclass(slots=True)
class MedicationIdentity:
    name: str
    rxnorm: str | None
    notes: str | None
    source_id: str | None
    author_time: str | None
    provider: str | None


@dataclass(slots=True)
class MedicationTiming:
    start: str | None
    end: str | None
    start_bucket: str | None
    end_bucket: str | None


@dataclass(slots=True)
class MedicationEncounter:
    source_id: str | None
    start: str | None
    end: str | None


@dataclass(slots=True)
class MedicationDose:
    route: str | None
    dose: str | None
    frequency: str | None


MedicationKey = tuple[str, str, str, str, str]


class MedicationEntry(TypedDict, total=False):
    name: str | None
    rxnorm: str | None
    dose: str | None
    route: str | None
    frequency: str | None
    start: str | None
    end: str | None
    status: str | None
    notes: str | None
    provider: str | None
    author_time: str | None
    source_id: str | None
    encounter_source_id: str | None
    encounter_start: str | None
    encounter_end: str | None
    patient_id: str | None
    start_bucket: str | None
    end_bucket: str | None


def _bucket_date(value: str | None) -> str | None:
    """Normalise a timestamp to its nearest day-resolution bucket."""
    if not value:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) >= 8:
        return digits[:8]
    stripped = value.strip()
    return stripped or None


def _resolve_encounter_id(
    encounter_el: ElementType | None,
    ns: dict[str, str],
) -> str | None:
    """Return the first usable encounter identifier."""
    if encounter_el is None:
        return None
    for id_el in encounter_el.findall("hl7:id", namespaces=ns):
        extension = clean_text(id_el.get("extension"))
        if extension:
            return extension
        root = clean_text(id_el.get("root"))
        if root:
            return root
    return None


def _resolve_encounter_times(
    encounter_el: ElementType | None,
    ns: dict[str, str],
) -> tuple[str | None, str | None]:
    """Return start/end timestamps resolved from effectiveTime."""
    if encounter_el is None:
        return None, None
    eff_el = encounter_el.find("hl7:effectiveTime", namespaces=ns)
    if eff_el is None:
        return None, None
    value = clean_text(eff_el.get("value"))
    if value:
        return value, value
    low_el = eff_el.find("hl7:low", namespaces=ns)
    high_el = eff_el.find("hl7:high", namespaces=ns)
    start = clean_text(low_el.get("value")) if isinstance(low_el, ElementType) else None
    end = clean_text(high_el.get("value")) if isinstance(high_el, ElementType) else None
    if end is None and start is not None:
        end = start
    return start, end


def _extract_encounter_details(
    encounter_el: ElementType | None,
    ns: dict[str, str],
) -> tuple[str | None, str | None, str | None]:
    """Extract encounter identifiers and times for a medication reference."""
    if encounter_el is None:
        return None, None, None
    source_id = _resolve_encounter_id(encounter_el, ns)
    start, end = _resolve_encounter_times(encounter_el, ns)
    return source_id, start, end


def _find_medication_encounter(
    med_el: ElementType, ns: dict[str, str]
) -> ElementType | None:
    """Locate a related encounter element for the current medication entry."""
    candidates: list[tuple[str, ElementType]] = []
    for entry_rel in med_el.findall("hl7:entryRelationship", namespaces=ns):
        type_code = (entry_rel.get("typeCode") or "").strip().upper()
        raw_encounters = entry_rel.xpath(
            ".//hl7:encounter | .//hl7:externalEncounter",
            namespaces=ns,
        )
        if not isinstance(raw_encounters, list):
            continue
        for encounter in raw_encounters:
            if isinstance(encounter, ElementType):
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


def _collect_document_context(
    tree: ElementTreeType,
    ns: dict[str, str],
) -> tuple[DocumentContext, bool]:
    """Return patient and encounter defaults plus a context-present flag."""
    patient_id = _extract_patient_id(tree, ns) or "unknown_patient"
    root = tree.getroot() if isinstance(tree, ElementTreeType) else None
    has_context = False
    if isinstance(root, ElementType):
        has_context = any(
            root.find(path, namespaces=ns) is not None
            for path in (
                "hl7:componentOf/hl7:encompassingEncounter",
                "hl7:documentationOf/hl7:serviceEvent",
            )
        )

    doc_encounter_el = tree.find(
        "hl7:componentOf/hl7:encompassingEncounter",
        namespaces=ns,
    )
    (
        encounter_id,
        encounter_start,
        encounter_end,
    ) = _extract_encounter_details(doc_encounter_el, ns)
    context = DocumentContext(
        patient_id=patient_id,
        encounter_id=encounter_id,
        encounter_start=encounter_start,
        encounter_end=encounter_end,
    )
    return context, has_context


def _medication_nodes(
    tree: ElementTreeType,
    ns: dict[str, str],
) -> list[ElementType]:
    """Return CCD medication administration nodes."""
    raw_nodes = tree.xpath(
        ".//hl7:substanceAdministration"
        "[hl7:templateId[@root='2.16.840.1.113883.10.20.22.4.16']]",
        namespaces=ns,
    )
    if not isinstance(raw_nodes, list):
        return []
    return [node for node in raw_nodes if isinstance(node, ElementType)]


def _extract_medication_identity(
    tree: ElementTreeType,
    med: ElementType,
    ns: dict[str, str],
) -> MedicationIdentity | None:
    """Resolve core medication identity attributes."""
    code_el = med.find(
        ".//hl7:manufacturedMaterial/hl7:code",
        namespaces=ns,
    )
    med_name = normalize_whitespace(
        code_el.get("displayName") if code_el is not None else None
    )
    rxnorm_code = clean_text(code_el.get("code") if code_el is not None else None)
    if med_name is None and code_el is not None:
        ref = code_el.find("hl7:originalText/hl7:reference", namespaces=ns)
        if ref is not None and ref.get("value"):
            med_name = normalize_whitespace(get_text_by_id(tree, ns, ref.get("value")))

    sig_text = None
    sig_ref = med.find("hl7:text/hl7:reference", namespaces=ns)
    if sig_ref is not None and sig_ref.get("value"):
        sig_text = normalize_whitespace(get_text_by_id(tree, ns, sig_ref.get("value")))

    med_id = None
    id_el = med.find("hl7:id", namespaces=ns)
    if id_el is not None:
        med_id = clean_text(id_el.get("extension")) or clean_text(id_el.get("root"))

    author_time = None
    author_time_el = med.find("hl7:author/hl7:time", namespaces=ns)
    if author_time_el is not None:
        author_time = clean_text(author_time_el.get("value"))

    provider_name = extract_provider_name(
        med,
        "hl7:author/hl7:assignedAuthor/hl7:assignedPerson/hl7:name",
        "hl7:author/hl7:assignedAuthor/hl7:representedOrganization/hl7:name",
        ns,
    )

    resolved_name = med_name or sig_text or rxnorm_code
    if resolved_name is None:
        return None

    return MedicationIdentity(
        name=resolved_name,
        rxnorm=rxnorm_code,
        notes=sig_text,
        source_id=med_id,
        author_time=author_time,
        provider=provider_name,
    )


def _resolve_medication_encounter(
    med: ElementType,
    ns: dict[str, str],
    context: DocumentContext,
) -> MedicationEncounter:
    """Merge medication encounter info with document-level defaults."""
    med_encounter_el = _find_medication_encounter(med, ns)
    source_id, start, end = _extract_encounter_details(med_encounter_el, ns)
    if source_id is None:
        source_id = context.encounter_id
    if start is None:
        start = context.encounter_start
    if end is None:
        end = context.encounter_end
    return MedicationEncounter(
        source_id=source_id,
        start=start,
        end=end,
    )


def _extract_medication_timing(
    med: ElementType,
    ns: dict[str, str],
) -> MedicationTiming:
    """Return start/end values and day buckets for a medication entry."""
    start_el = med.find("hl7:effectiveTime/hl7:low", namespaces=ns)
    end_el = med.find("hl7:effectiveTime/hl7:high", namespaces=ns)
    start_value = clean_text(start_el.get("value") if start_el is not None else None)
    end_value = clean_text(end_el.get("value") if end_el is not None else None)
    return MedicationTiming(
        start=start_value,
        end=end_value,
        start_bucket=_bucket_date(start_value),
        end_bucket=_bucket_date(end_value),
    )


def _extract_frequency(med: ElementType, ns: dict[str, str]) -> str | None:
    """Extract dosing frequency text from effectiveTime structures."""
    for eff in med.findall("hl7:effectiveTime", namespaces=ns):
        xsi_type = clean_text(eff.get(f"{{{XSI_NS}}}type")) or ""
        if xsi_type.upper() != "PIVL_TS":
            continue
        period = eff.find("hl7:period", namespaces=ns)
        if period is not None:
            period_value = clean_text(period.get("value"))
            period_unit = clean_text(period.get("unit"))
            if period_value and period_unit:
                return f"Every {period_value} {period_unit}"
            if period_unit:
                return f"Every {period_unit}"
            if period_value:
                return f"Every {period_value}"
        freq_text = eff.findtext("hl7:originalText", namespaces=ns)
        candidate = clean_text(freq_text)
        if candidate:
            return candidate
        break
    return None


def _extract_medication_dose(
    med: ElementType,
    ns: dict[str, str],
) -> MedicationDose:
    """Return route, dose, and frequency components."""
    route_el = med.find("hl7:routeCode", namespaces=ns)
    route = None
    if route_el is not None:
        route = clean_text(route_el.get("displayName")) or clean_text(
            route_el.get("code")
        )
        if route is None:
            route = clean_text(route_el.findtext("hl7:originalText", namespaces=ns))

    dose = None
    dose_el = med.find("hl7:doseQuantity", namespaces=ns)
    if dose_el is not None:
        dose_value = clean_text(dose_el.get("value"))
        dose_unit = clean_text(dose_el.get("unit"))
        if dose_value or dose_unit:
            dose = " ".join(
                part
                for part in (
                    normalize_whitespace(dose_value),
                    normalize_whitespace(dose_unit),
                )
                if part
            )

    frequency = _extract_frequency(med, ns)
    return MedicationDose(route=route, dose=dose, frequency=frequency)


def _extract_medication_status(
    med: ElementType,
    ns: dict[str, str],
) -> str | None:
    """Return the normalised medication status label."""
    raw_status_nodes = med.xpath(
        "hl7:entryRelationship/hl7:observation" "[hl7:code[@code='33999-4']]/hl7:value",
        namespaces=ns,
    )
    status_value = None
    if isinstance(raw_status_nodes, list):
        nodes = [el for el in raw_status_nodes if isinstance(el, ElementType)]
        status_value = nodes[0] if nodes else None
    if isinstance(status_value, ElementType):
        candidate = clean_text(
            status_value.get("displayName") or status_value.get("code")
        )
        if candidate:
            return candidate.title()

    status_code_el = med.find("hl7:statusCode", namespaces=ns)
    status_code = (
        clean_text(status_code_el.get("code")) if status_code_el is not None else None
    )
    return status_code.title() if status_code else None


def _medication_key(entry: MedicationEntry) -> MedicationKey:
    """Generate a deduplication key for medication entries."""
    patient_id = entry.get("patient_id") or "unknown_patient"
    encounter_key = (entry.get("encounter_source_id") or "").strip()
    name_key = (entry.get("name") or "").strip().lower()
    dose_key = (entry.get("dose") or "").strip().lower()
    start_key = entry.get("start_bucket") or (entry.get("start") or "").strip()
    return (
        patient_id,
        encounter_key,
        name_key,
        dose_key,
        start_key,
    )


def _register_entry(
    key: MedicationKey,
    seen: set[MedicationKey],
    registry: set[MedicationKey] | None,
) -> bool:
    """Record a deduplicated entry, returning False when already registered."""
    if key in seen:
        return False
    if registry is not None and key in registry:
        return False
    seen.add(key)
    if registry is not None:
        registry.add(key)
    return True


def _extract_patient_id(tree: ElementTreeType, ns: dict[str, str]) -> str | None:
    """Return the patient identifier from the CCD, if provided."""
    patient_ids = tree.xpath(
        ".//hl7:recordTarget/hl7:patientRole/hl7:id",
        namespaces=ns,
    )
    if isinstance(patient_ids, list):
        for id_el in patient_ids:
            if isinstance(id_el, ElementType):
                extension = (id_el.get("extension") or "").strip()
                root = (id_el.get("root") or "").strip()
                if extension:
                    return extension
                if root:
                    return root
    return None


def parse_medications(
    tree: ElementTreeType,
    ns: dict[str, str],
    existing_keys: set[MedicationKey] | None = None,
) -> list[MedicationEntry]:
    """Parse medication administrations documented in a CCD.

    Args:
        tree: Root XML tree for the CCD document.
        ns: Namespace dictionary used for XPath lookups.
        existing_keys: Optional registry of deduplication keys to skip.

    Returns:
        list[MedicationEntry]: Medication entries ready for persistence.
    """
    context, has_context = _collect_document_context(tree, ns)
    if not has_context:
        return []

    medications: list[MedicationEntry] = []
    medication_nodes = _medication_nodes(tree, ns)
    if not medication_nodes:
        return medications

    seen_entries: set[MedicationKey] = set()
    registry = existing_keys

    for med in medication_nodes:
        identity = _extract_medication_identity(tree, med, ns)
        if identity is None:
            continue
        encounter = _resolve_medication_encounter(med, ns, context)
        timing = _extract_medication_timing(med, ns)
        dose = _extract_medication_dose(med, ns)
        status = _extract_medication_status(med, ns)

        entry: MedicationEntry = MedicationEntry(
            name=identity.name,
            rxnorm=identity.rxnorm,
            dose=dose.dose,
            route=dose.route,
            frequency=dose.frequency,
            start=timing.start,
            end=timing.end,
            status=status,
            notes=identity.notes,
            provider=identity.provider,
            author_time=identity.author_time,
            source_id=identity.source_id,
            encounter_source_id=encounter.source_id,
            encounter_start=encounter.start,
            encounter_end=encounter.end,
            patient_id=context.patient_id,
            start_bucket=timing.start_bucket,
            end_bucket=timing.end_bucket,
        )

        dedupe_key = _medication_key(entry)
        if not _register_entry(dedupe_key, seen_entries, registry):
            continue
        medications.append(entry)

    return medications
