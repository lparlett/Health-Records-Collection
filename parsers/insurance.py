# Purpose: Parse insurance coverage activities from CCD documents.
# Author: Codex + Lauren
# Date: 2025-10-19
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Insurance coverage parsing helpers."""

from __future__ import annotations

from typing import Any, Optional, Sequence, cast

from lxml import etree

from .common import get_text_by_id

__all__ = ["parse_insurance"]

COVERAGE_SECTION_CODES: set[str] = {
    "48768-6",  # Payment sources
    "55109-3",  # Coverage extensions
    "75274-1",  # Health plan payment
}

COVERAGE_ACTIVITY_TEMPLATE = "2.16.840.1.113883.10.20.22.4.60"
COVERAGE_DETAIL_TEMPLATE = "2.16.840.1.113883.10.20.22.4.61"
INSURANCE_PROVIDER_TEMPLATE = "2.16.840.1.113883.10.20.1.20"


def _clean_text(value: Any) -> Optional[str]:
    """Return a trimmed string or ``None`` when blank."""
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


def _first_non_empty(*values: Optional[str]) -> Optional[str]:
    """Return the first non-empty value from the provided arguments."""
    for value in values:
        cleaned = _clean_text(value)
        if cleaned:
            return cleaned
    return None


def _collect_template_ids(node: etree._Element, ns: dict[str, str]) -> set[str]:
    """Return templateId roots from an element."""
    roots: set[str] = set()
    for template in node.findall("hl7:templateId", namespaces=ns):
        root = _clean_text(template.get("root"))
        if root:
            roots.add(root)
    return roots


def _extract_time_range(node: etree._Element | None, ns: dict[str, str]) -> tuple[Optional[str], Optional[str]]:
    """Return start/end components from an ``effectiveTime`` node."""
    if node is None:
        return (None, None)
    value = _clean_text(node.get("value"))
    if value:
        return (value, value)
    low = node.find("hl7:low", namespaces=ns)
    high = node.find("hl7:high", namespaces=ns)
    start = _clean_text(low.get("value")) if isinstance(low, etree._Element) else None
    end = _clean_text(high.get("value")) if isinstance(high, etree._Element) else None
    return (start, end)


def _extract_payer_name(act: etree._Element, ns: dict[str, str]) -> Optional[str]:
    """Return payer organisation name from performer blocks."""
    performer = act.find("hl7:performer/hl7:assignedEntity", namespaces=ns)
    if performer is None:
        return None
    org = performer.find("hl7:representedOrganization/hl7:name", namespaces=ns)
    if isinstance(org, etree._Element):
        text = org.xpath("string()")
        return _clean_text(text)
    person = performer.find("hl7:assignedPerson/hl7:name", namespaces=ns)
    if isinstance(person, etree._Element):
        text = person.xpath("string()")
        return _clean_text(text)
    return None


def _extract_payer_identifier(act: etree._Element, ns: dict[str, str]) -> Optional[str]:
    """Return the payer identifier (e.g., NAIC) from assigned entity IDs."""
    performer = act.find("hl7:performer/hl7:assignedEntity", namespaces=ns)
    if performer is None:
        return None
    for identifier in performer.findall("hl7:id", namespaces=ns):
        candidate = _clean_text(identifier.get("extension") or identifier.get("root"))
        if candidate:
            return candidate
    return None


def _extract_original_text(
    tree: etree._ElementTree,
    node: etree._Element,
    ns: dict[str, str],
) -> Optional[str]:
    """Return the textual content of an ``originalText`` element."""
    text_value = _clean_text(node.xpath("string()"))
    if text_value:
        return text_value
    reference = node.find("hl7:reference", namespaces=ns)
    if isinstance(reference, etree._Element) and reference.get("value"):
        return get_text_by_id(tree, ns, reference.get("value"))
    return None


def _extract_participant_role(
    tree: etree._ElementTree,
    act: etree._Element,
    ns: dict[str, str],
    *,
    type_code: str,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (id, relationship, name) for a participant role."""
    participant = act.find(f"hl7:participant[@typeCode='{type_code}']/hl7:participantRole", namespaces=ns)
    if participant is None:
        return (None, None, None)
    identifier = None
    ident_el = participant.find("hl7:id", namespaces=ns)
    if isinstance(ident_el, etree._Element):
        identifier = _clean_text(ident_el.get("extension") or ident_el.get("root"))
    relationship = None
    code = participant.find("hl7:code", namespaces=ns)
    if isinstance(code, etree._Element):
        relationship = _first_non_empty(
            _extract_original_text(tree, code, ns),
            code.get("displayName"),
            code.get("code"),
        )
    name_node = participant.find("hl7:playingEntity/hl7:name", namespaces=ns)
    full_name = _clean_text(name_node.xpath("string()")) if isinstance(name_node, etree._Element) else None
    return (identifier, relationship, full_name)


def _extract_coverage_participant(
    tree: etree._ElementTree,
    act: etree._Element,
    ns: dict[str, str],
) -> tuple[Optional[str], Optional[str], Optional[str], tuple[Optional[str], Optional[str]]]:
    """Return details from the coverage (COV) participant role."""
    participant = act.find("hl7:participant[@typeCode='COV']/hl7:participantRole", namespaces=ns)
    if participant is None:
        return (None, None, None, (None, None))

    identifier = None
    id_node = participant.find("hl7:id", namespaces=ns)
    if isinstance(id_node, etree._Element):
        identifier = _clean_text(id_node.get("extension") or id_node.get("root"))

    relationship = None
    code_node = participant.find("hl7:code", namespaces=ns)
    if isinstance(code_node, etree._Element):
        relationship = _first_non_empty(
            _extract_original_text(tree, code_node, ns),
            code_node.get("displayName"),
            code_node.get("code"),
        )

    playing_name = participant.find("hl7:playingEntity/hl7:name", namespaces=ns)
    name = _clean_text(playing_name.xpath("string()")) if isinstance(playing_name, etree._Element) else None

    time_node = participant.find("hl7:time", namespaces=ns)
    coverage_start, coverage_end = _extract_time_range(time_node, ns)

    return (identifier, relationship, name, (coverage_start, coverage_end))


def _extract_notes(tree: etree._ElementTree, act: etree._Element, ns: dict[str, str]) -> Optional[str]:
    """Return textual policy narrative."""
    reference = act.find("hl7:text/hl7:reference", namespaces=ns)
    if isinstance(reference, etree._Element) and reference.get("value"):
        resolved = get_text_by_id(tree, ns, reference.get("value"))
        if resolved:
            return resolved
    text_node = act.find("hl7:text", namespaces=ns)
    if isinstance(text_node, etree._Element):
        text = _clean_text(text_node.xpath("string()"))
        if text:
            return text
    return None


def _extract_plan_name(tree: etree._ElementTree, act: etree._Element, ns: dict[str, str]) -> Optional[str]:
    """Return the plan name from text blocks or referenced narrative."""
    plan_name = _extract_notes(tree, act, ns)
    if plan_name:
        return plan_name

    for rel in act.findall("hl7:entryRelationship", namespaces=ns):
        rel_act = rel.find("hl7:act", namespaces=ns)
        if rel_act is None:
            continue
        rel_text = _extract_notes(tree, rel_act, ns)
        if rel_text:
            return rel_text

    title_node = act.find("hl7:title", namespaces=ns)
    if isinstance(title_node, etree._Element):
        title_text = _clean_text(title_node.xpath("string()"))
        if title_text:
            return title_text
    return None


def _extract_first_identifier(act: etree._Element, ns: dict[str, str]) -> Optional[str]:
    """Return the first identifier extension/root associated with an act."""
    for identifier in act.findall("hl7:id", namespaces=ns):
        candidate = _clean_text(identifier.get("extension") or identifier.get("root"))
        if candidate:
            return candidate
    return None


def _collect_detail_acts(container: etree._Element, ns: dict[str, str]) -> list[etree._Element]:
    """Return nested coverage detail acts within a coverage container."""
    detail_acts: list[etree._Element] = []
    for relationship in container.findall("hl7:entryRelationship", namespaces=ns):
        candidate = relationship.find("hl7:act", namespaces=ns)
        if candidate is None:
            continue
        templates = _collect_template_ids(candidate, ns)
        if COVERAGE_DETAIL_TEMPLATE in templates:
            detail_acts.append(candidate)
    return detail_acts


def _prepare_defaults(
    tree: etree._ElementTree,
    act: etree._Element,
    ns: dict[str, str],
) -> dict[str, Optional[str]]:
    """Capture metadata from the container act for fallback usage."""
    effective_date, expiration_date = _extract_time_range(
        act.find("hl7:effectiveTime", namespaces=ns),
        ns,
    )
    if effective_date and expiration_date == effective_date:
        expiration_date = None
    status_node = act.find("hl7:statusCode", namespaces=ns)
    status = _clean_text(status_node.get("code")) if isinstance(status_node, etree._Element) else None

    coverage_code = act.find("hl7:code", namespaces=ns)
    coverage_type = None
    if isinstance(coverage_code, etree._Element):
        coverage_type = _first_non_empty(
            coverage_code.get("displayName"),
            coverage_code.get("code"),
        )

    group_number = _extract_first_identifier(act, ns)

    return {
        "payer_name": _extract_payer_name(act, ns),
        "payer_identifier": _extract_payer_identifier(act, ns),
        "plan_name": _extract_plan_name(tree, act, ns),
        "coverage_type": coverage_type,
        "policy_type": _clean_text(act.get("classCode")),
        "effective_date": effective_date,
        "expiration_date": expiration_date,
        "status": status,
        "group_number": group_number,
        "source_policy_id": group_number,
        "notes": _extract_notes(tree, act, ns),
        "member_id": None,
        "subscriber_id": None,
        "subscriber_name": None,
        "relationship": None,
    }


def _build_policy(
    tree: etree._ElementTree,
    act: etree._Element,
    ns: dict[str, str],
    defaults: dict[str, Optional[str]],
) -> Optional[dict[str, Optional[str]]]:
    """Normalise a coverage act into a policy dictionary."""
    payer_name = _first_non_empty(_extract_payer_name(act, ns), defaults.get("payer_name"))
    payer_identifier = _first_non_empty(_extract_payer_identifier(act, ns), defaults.get("payer_identifier"))
    plan_name = _first_non_empty(_extract_plan_name(tree, act, ns), defaults.get("plan_name"))

    coverage_code = act.find("hl7:code", namespaces=ns)
    coverage_type = _first_non_empty(
        coverage_code.get("displayName") if isinstance(coverage_code, etree._Element) else None,
        coverage_code.get("code") if isinstance(coverage_code, etree._Element) else None,
        defaults.get("coverage_type"),
    )

    policy_type = _first_non_empty(_clean_text(act.get("classCode")), defaults.get("policy_type"))

    detail_group_number = _extract_first_identifier(act, ns)
    group_number = _first_non_empty(detail_group_number, defaults.get("group_number"))
    source_policy_id = _first_non_empty(detail_group_number, defaults.get("source_policy_id"))

    coverage_effective, coverage_expiration = _extract_time_range(
        act.find("hl7:effectiveTime", namespaces=ns),
        ns,
    )
    if coverage_effective and coverage_expiration == coverage_effective:
        coverage_expiration = None

    cov_identifier, cov_relationship, cov_name, cov_range = _extract_coverage_participant(tree, act, ns)
    sub_id, sub_relationship, sub_name = _extract_participant_role(tree, act, ns, type_code="SUB")
    hld_id, hld_relationship, hld_name = _extract_participant_role(tree, act, ns, type_code="HLD")

    effective_date = _first_non_empty(
        cov_range[0],
        coverage_effective,
        defaults.get("effective_date"),
    )
    expiration_date = _first_non_empty(
        cov_range[1],
        coverage_expiration,
        defaults.get("expiration_date"),
    )
    if expiration_date and effective_date and expiration_date == effective_date:
        expiration_date = None

    member_id = _first_non_empty(cov_identifier, hld_id, defaults.get("member_id"))
    subscriber_id = _first_non_empty(sub_id, cov_identifier, defaults.get("subscriber_id"))
    subscriber_name = _first_non_empty(sub_name, cov_name, hld_name, defaults.get("subscriber_name"))
    relationship = _first_non_empty(
        cov_relationship,
        sub_relationship,
        hld_relationship,
        defaults.get("relationship"),
    )

    status_node = act.find("hl7:statusCode", namespaces=ns)
    status_code = _first_non_empty(
        status_node.get("code") if isinstance(status_node, etree._Element) else None,
        defaults.get("status"),
    )

    notes = _first_non_empty(_extract_notes(tree, act, ns), defaults.get("notes"))

    policy = {
        "payer_name": payer_name,
        "payer_identifier": payer_identifier,
        "plan_name": plan_name,
        "coverage_type": coverage_type,
        "policy_type": policy_type,
        "member_id": member_id,
        "group_number": group_number,
        "subscriber_id": subscriber_id,
        "subscriber_name": subscriber_name,
        "relationship": relationship,
        "effective_date": effective_date,
        "expiration_date": expiration_date,
        "status": status_code,
        "source_policy_id": source_policy_id,
        "notes": notes,
    }

    if any(
        policy.get(key)
        for key in (
            "payer_name",
            "plan_name",
            "member_id",
            "subscriber_id",
            "group_number",
        )
    ):
        return policy

    return None


def parse_insurance(tree: etree._ElementTree, ns: dict[str, str]) -> list[dict[str, Optional[str]]]:
    """Extract insurance policies from a CCD document."""
    policies: list[dict[str, Optional[str]]] = []
    section_nodes = cast(Sequence[Any], tree.xpath(".//hl7:section", namespaces=ns))

    for section in section_nodes:
        if not isinstance(section, etree._Element):
            continue
        code_el = section.find("hl7:code", namespaces=ns)
        code_value = _clean_text(code_el.get("code")) if isinstance(code_el, etree._Element) else None
        if code_value not in COVERAGE_SECTION_CODES:
            continue

        for entry in section.findall("hl7:entry", namespaces=ns):
            for container in entry.findall("hl7:act", namespaces=ns):
                if container.getparent() is not entry:
                    continue
                templates = _collect_template_ids(container, ns)
                if (
                    COVERAGE_ACTIVITY_TEMPLATE not in templates
                    and COVERAGE_DETAIL_TEMPLATE not in templates
                    and INSURANCE_PROVIDER_TEMPLATE not in templates
                ):
                    continue

                defaults = _prepare_defaults(tree, container, ns)

                detail_acts = _collect_detail_acts(container, ns)
                if not detail_acts:
                    detail_acts = [container]

                for coverage_act in detail_acts:
                    policy = _build_policy(tree, coverage_act, ns, defaults)
                    if policy:
                        policies.append(policy)
    return policies
