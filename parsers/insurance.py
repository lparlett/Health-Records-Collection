# Purpose: Parse insurance coverage activities from CCD documents.
# Author: Codex + Lauren
# Date: 2025-10-19
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Insurance coverage parsing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .common import (
    clean_text,
    collect_template_ids,
    extract_effective_time,
    extract_notes,
    first_non_empty,
    get_text_by_id,
    iter_elements,
    normalize_whitespace,
    safe_xpath_text,
)
from .xml_types import ElementType, ElementTreeType

__all__ = ["parse_insurance"]

COVERAGE_SECTION_CODES: set[str] = {
    "48768-6",  # Payment sources
    "55109-3",  # Coverage extensions
    "75274-1",  # Health plan payment
}

COVERAGE_ACTIVITY_TEMPLATE = "2.16.840.1.113883.10.20.22.4.60"
COVERAGE_DETAIL_TEMPLATE = "2.16.840.1.113883.10.20.22.4.61"
INSURANCE_PROVIDER_TEMPLATE = "2.16.840.1.113883.10.20.1.20"


@dataclass(slots=True)
class ParticipantRole:
    """Participant identifying coverage members, subscribers, or holders."""

    identifier: Optional[str]
    relationship: Optional[str]
    name: Optional[str]
    start: Optional[str] = None
    end: Optional[str] = None


@dataclass(slots=True)
class ParticipantRoles:
    """Bundle of coverage, subscriber, and holder participants."""

    coverage: ParticipantRole
    subscriber: ParticipantRole
    holder: ParticipantRole


def _insurance_sections(tree: ElementTreeType, ns: dict[str, str]) -> list[ElementType]:
    """Return CCD sections describing insurance coverage."""
    root = tree.getroot()
    sections = root.xpath(".//hl7:section", namespaces=ns)
    results: list[ElementType] = []
    for section in iter_elements(sections):
        code_el = section.find("hl7:code", namespaces=ns)
        code_value = clean_text(
            code_el.get("code") if isinstance(code_el, ElementType) else None
        )
        if code_value in COVERAGE_SECTION_CODES:
            results.append(section)
    return results


def _is_coverage_act(act: ElementType, ns: dict[str, str]) -> bool:
    """Return True when the act matches insurance coverage templates."""
    templates = collect_template_ids(act, ns)
    return any(
        template in templates
        for template in (
            COVERAGE_ACTIVITY_TEMPLATE,
            COVERAGE_DETAIL_TEMPLATE,
            INSURANCE_PROVIDER_TEMPLATE,
        )
    )


def _collect_detail_acts(act: ElementType, ns: dict[str, str]) -> list[ElementType]:
    """Return nested detail acts providing policy specifics."""
    details = act.findall("hl7:entryRelationship/hl7:act", namespaces=ns)
    return [detail for detail in iter_elements(details) if _is_coverage_act(detail, ns)]


def _extract_original_text(
    tree: ElementTreeType,
    node: ElementType,
    ns: dict[str, str],
) -> Optional[str]:
    """Return the textual content of an ``originalText`` element."""
    text_value = normalize_whitespace(node.xpath("string()"))
    if text_value:
        return text_value
    reference = node.find("hl7:reference", namespaces=ns)
    if isinstance(reference, ElementType) and reference.get("value"):
        return normalize_whitespace(get_text_by_id(tree, ns, reference.get("value")))
    return None


def _extract_payer_details(
    tree: ElementTreeType,
    act: ElementType,
    defaults: dict[str, Optional[str]],
    ns: dict[str, str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return payer organisation name, identifier, and plan name."""
    performer = act.find("hl7:performer/hl7:assignedEntity", namespaces=ns)
    payer_name = defaults.get("payer_name")
    payer_identifier = defaults.get("payer_identifier")
    plan_name = defaults.get("plan_name")

    if performer is not None:
        org_name = performer.find("hl7:representedOrganization/hl7:name", namespaces=ns)
        person_name = performer.find("hl7:assignedPerson/hl7:name", namespaces=ns)
        payer_name = first_non_empty(
            payer_name,
            normalize_whitespace(
                org_name.xpath("string()")
                if isinstance(org_name, ElementType)
                else None
            ),
            normalize_whitespace(
                person_name.xpath("string()")
                if isinstance(person_name, ElementType)
                else None
            ),
        )
        if payer_identifier is None:
            for identifier in iter_elements(performer.findall("hl7:id", namespaces=ns)):
                candidate = clean_text(
                    identifier.get("extension") or identifier.get("root")
                )
                if candidate:
                    payer_identifier = candidate
                    break

    plan_text = extract_notes(tree=tree, node=act, ns=ns)
    plan_el = act.find("hl7:code", namespaces=ns)
    plan_name = first_non_empty(
        plan_text,
        plan_name,
        normalize_whitespace(
            plan_el.get("displayName") if isinstance(plan_el, ElementType) else None
        ),
        clean_text(plan_el.get("code") if isinstance(plan_el, ElementType) else None),
    )

    return payer_name, payer_identifier, plan_name


def _extract_coverage_type(
    act: ElementType, defaults: dict[str, Optional[str]], ns: dict[str, str]
) -> Optional[str]:
    """Return coverage type string."""
    coverage_code = act.find("hl7:code", namespaces=ns)
    return first_non_empty(
        normalize_whitespace(
            coverage_code.get("displayName")
            if isinstance(coverage_code, ElementType)
            else None
        ),
        clean_text(
            coverage_code.get("code")
            if isinstance(coverage_code, ElementType)
            else None
        ),
        defaults.get("coverage_type"),
    )


def _extract_policy_type(
    act: ElementType, defaults: dict[str, Optional[str]]
) -> Optional[str]:
    """Return policy class code."""
    return first_non_empty(
        clean_text(act.get("classCode")), defaults.get("policy_type")
    )


def _extract_original_plan_text(
    tree: ElementTreeType,
    node: ElementType | None,
    ns: dict[str, str],
) -> Optional[str]:
    if node is None:
        return None
    return _extract_original_text(tree, node, ns)


def _extract_participant_role(
    act: ElementType,
    ns: dict[str, str],
    *,
    type_code: str,
) -> ParticipantRole:
    """Return participant role details."""
    participant = act.find(
        f"hl7:participant[@typeCode='{type_code}']/hl7:participantRole", namespaces=ns
    )
    if participant is None:
        return ParticipantRole(identifier=None, relationship=None, name=None)

    identifier = None
    for id_el in iter_elements(participant.findall("hl7:id", namespaces=ns)):
        candidate = clean_text(id_el.get("extension") or id_el.get("root"))
        if candidate:
            identifier = candidate
            break

    code_el = participant.find("hl7:code", namespaces=ns)
    relationship = first_non_empty(
        normalize_whitespace(
            code_el.get("displayName") if isinstance(code_el, ElementType) else None
        ),
        clean_text(code_el.get("code") if isinstance(code_el, ElementType) else None),
    )

    name_el = participant.find("hl7:playingEntity/hl7:name", namespaces=ns)
    name = normalize_whitespace(
        name_el.xpath("string()") if isinstance(name_el, ElementType) else None
    )

    start, end = extract_effective_time(participant.find("hl7:time", namespaces=ns), ns)
    return ParticipantRole(
        identifier=identifier,
        relationship=relationship,
        name=name,
        start=start,
        end=end,
    )


def _extract_coverage_participant(
    tree: ElementTreeType,
    act: ElementType,
    ns: dict[str, str],
) -> ParticipantRole:
    """Return coverage participant information."""
    cov_participant = act.find(
        "hl7:participant[@typeCode='COV']/hl7:participantRole",
        namespaces=ns,
    )
    if cov_participant is None:
        return ParticipantRole(identifier=None, relationship=None, name=None)

    identifier = None
    for id_el in iter_elements(cov_participant.findall("hl7:id", namespaces=ns)):
        candidate = clean_text(id_el.get("extension") or id_el.get("root"))
        if candidate:
            identifier = candidate
            break
    code_el = cov_participant.find("hl7:code", namespaces=ns)
    relationship_text = None
    if isinstance(code_el, ElementType):
        original = code_el.find("hl7:originalText", namespaces=ns)
        if isinstance(original, ElementType):
            relationship_text = _extract_original_text(tree, original, ns)
    relationship = first_non_empty(
        normalize_whitespace(
            code_el.get("displayName") if isinstance(code_el, ElementType) else None
        ),
        relationship_text,
        clean_text(code_el.get("code") if isinstance(code_el, ElementType) else None),
    )

    playing_entity = cov_participant.find("hl7:playingEntity", namespaces=ns)
    name = None
    if playing_entity is not None:
        name = normalize_whitespace(
            playing_entity.xpath("hl7:name/text()", namespaces=ns)
        )
        if not name:
            name = _extract_original_text(tree, playing_entity, ns)

    start, end = extract_effective_time(
        cov_participant.find("hl7:time", namespaces=ns), ns
    )
    return ParticipantRole(
        identifier=identifier,
        relationship=relationship,
        name=name,
        start=start,
        end=end,
    )


def _extract_first_id(
    role: ElementType | None,
    ns: dict[str, str],
) -> Optional[str]:
    """Extract the first ID from a role element."""
    if role is None:
        return None
    for id_el in iter_elements(role.findall("hl7:id", namespaces=ns)):
        candidate = clean_text(id_el.get("extension") or id_el.get("root"))
        if candidate:
            return candidate
    return None


def _extract_payer_info(
    tree: ElementTreeType,
    act: ElementType,
    ns: dict[str, str],
) -> tuple[Optional[str], Optional[str]]:
    """Extract payer name and identifier from performer."""
    payer_name = _extract_original_plan_text(
        tree,
        act.find(
            "hl7:performer/hl7:assignedEntity/hl7:representedOrganization/hl7:name",
            namespaces=ns,
        ),
        ns,
    )
    performer = act.find("hl7:performer/hl7:assignedEntity", namespaces=ns)
    payer_id = _extract_first_id(performer, ns)
    return normalize_whitespace(payer_name), payer_id


def _extract_plan_and_coverage_type(
    plan_el: ElementType | None,
) -> tuple[Optional[str], Optional[str]]:
    """Extract plan name and coverage type from code element."""
    plan_name = first_non_empty(
        normalize_whitespace(
            plan_el.get("displayName") if isinstance(plan_el, ElementType) else None
        ),
        clean_text(plan_el.get("code") if isinstance(plan_el, ElementType) else None),
    )
    coverage_type = first_non_empty(
        normalize_whitespace(
            plan_el.get("displayName") if isinstance(plan_el, ElementType) else None
        ),
        clean_text(plan_el.get("code") if isinstance(plan_el, ElementType) else None),
    )
    return plan_name, coverage_type


def _extract_coverage_role_info(
    act: ElementType,
    ns: dict[str, str],
) -> tuple[Optional[str], Optional[str]]:
    """Extract policy ID and group number from coverage role."""
    coverage_role = act.find(
        "hl7:participant[@typeCode='COV']/hl7:participantRole", namespaces=ns
    )
    if coverage_role is None:
        return None, None

    policy_id = _extract_first_id(coverage_role, ns)
    group_id = coverage_role.find(
        "hl7:id[@root='2.16.840.1.113883.4.340']",
        namespaces=ns,
    )
    group_number = clean_text(
        group_id.get("extension") if isinstance(group_id, ElementType) else None
    )
    return policy_id, group_number


def _extract_subscriber_info(
    tree: ElementTreeType,
    act: ElementType,
    ns: dict[str, str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract subscriber ID, name, and relationship."""
    subscriber_role = act.find(
        "hl7:participant[@typeCode='SUB']/hl7:participantRole", namespaces=ns
    )
    if subscriber_role is None:
        return None, None, None

    subscriber_id = _extract_first_id(subscriber_role, ns)
    subscriber_name = normalize_whitespace(
        safe_xpath_text(subscriber_role, "hl7:playingEntity/hl7:name", ns)
    )
    sub_code = subscriber_role.find("hl7:code", namespaces=ns)
    relationship_text = None
    if isinstance(sub_code, ElementType):
        original = sub_code.find("hl7:originalText", namespaces=ns)
        if isinstance(original, ElementType):
            relationship_text = _extract_original_text(tree, original, ns)

    relationship = first_non_empty(
        normalize_whitespace(
            sub_code.get("displayName") if isinstance(sub_code, ElementType) else None
        ),
        relationship_text,
        clean_text(sub_code.get("code") if isinstance(sub_code, ElementType) else None),
    )
    return subscriber_id, subscriber_name, relationship


def _prepare_defaults(
    tree: ElementTreeType,
    act: ElementType,
    ns: dict[str, str],
) -> dict[str, Optional[str]]:
    """Extract default values from a container act for nested details."""
    defaults: dict[str, Optional[str]] = {}
    defaults.update(_default_payer_info(tree, act, ns))
    defaults.update(_default_plan_info(act, ns))
    defaults.update(_default_coverage_role_info(act, ns))
    defaults.update(_default_dates(act, ns))
    defaults.update(_default_member_info(tree, act, ns))
    defaults.update(_default_status_and_notes(tree, act, ns))
    return defaults


def _default_payer_info(
    tree: ElementTreeType, act: ElementType, ns: dict[str, str]
) -> dict[str, Optional[str]]:
    """Return payer metadata defaults."""
    payer_name, payer_id = _extract_payer_info(tree, act, ns)
    return {"payer_name": payer_name, "payer_identifier": payer_id}


def _default_plan_info(
    act: ElementType, ns: dict[str, str]
) -> dict[str, Optional[str]]:
    """Return plan and coverage defaults."""
    plan_el = act.find("hl7:code", namespaces=ns)
    plan_name, coverage_type = _extract_plan_and_coverage_type(plan_el)
    return {
        "plan_name": plan_name,
        "coverage_type": coverage_type,
        "policy_type": clean_text(act.get("classCode")),
    }


def _default_coverage_role_info(
    act: ElementType, ns: dict[str, str]
) -> dict[str, Optional[str]]:
    """Return defaults derived from coverage role data."""
    policy_id, group_number = _extract_coverage_role_info(act, ns)
    return {"source_policy_id": policy_id, "group_number": group_number}


def _default_dates(
    act: ElementType, ns: dict[str, str]
) -> dict[str, Optional[str]]:
    """Return effective/expiration defaults."""
    effective, expiration = extract_effective_time(
        act.find("hl7:effectiveTime", namespaces=ns),
        ns,
    )
    return {"effective_date": effective, "expiration_date": expiration}


def _default_member_info(
    tree: ElementTreeType, act: ElementType, ns: dict[str, str]
) -> dict[str, Optional[str]]:
    """Return holder and subscriber defaults."""
    holder_role = act.find(
        "hl7:participant[@typeCode='HLD']/hl7:participantRole", namespaces=ns
    )
    subscriber_id, subscriber_name, relationship = _extract_subscriber_info(
        tree, act, ns
    )
    return {
        "member_id": _extract_first_id(holder_role, ns),
        "subscriber_id": subscriber_id,
        "subscriber_name": subscriber_name,
        "relationship": relationship,
    }


def _default_status_and_notes(
    tree: ElementTreeType, act: ElementType, ns: dict[str, str]
) -> dict[str, Optional[str]]:
    """Return status and note defaults."""
    status_el = act.find("hl7:statusCode", namespaces=ns)
    return {
        "status": clean_text(
            status_el.get("code") if isinstance(status_el, ElementType) else None
        ),
        "notes": extract_notes(tree, act, ns),
    }


def _resolve_participants(
    tree: ElementTreeType,
    act: ElementType,
    ns: dict[str, str],
) -> ParticipantRoles:
    """Return (coverage, subscriber, holder) participant roles."""
    coverage = _extract_coverage_participant(tree, act, ns)
    subscriber = _extract_participant_role(act, ns, type_code="SUB")
    holder = _extract_participant_role(act, ns, type_code="HLD")
    return ParticipantRoles(coverage=coverage, subscriber=subscriber, holder=holder)


def _resolve_dates(
    act: ElementType,
    defaults: dict[str, Optional[str]],
    coverage: ParticipantRole,
    ns: dict[str, str],
) -> dict[str, Optional[str]]:
    """Resolve effective and expiration dates from act/coverage/defaults."""
    effective, expiration = extract_effective_time(
        act.find("hl7:effectiveTime", namespaces=ns),
        ns,
    )
    effective = first_non_empty(
        coverage.start, effective, defaults.get("effective_date")
    )
    expiration = first_non_empty(
        coverage.end, expiration, defaults.get("expiration_date")
    )
    if expiration and effective and expiration == effective:
        expiration = None
    return {"effective_date": effective, "expiration_date": expiration}


def _resolve_member_details(
    participants: ParticipantRoles,
    defaults: dict[str, Optional[str]],
) -> dict[str, Optional[str]]:
    """Return member and subscriber identifiers, name, and relationship."""
    member_id = first_non_empty(
        participants.coverage.identifier,
        participants.holder.identifier,
        defaults.get("member_id"),
    )
    subscriber_id = first_non_empty(
        participants.subscriber.identifier,
        participants.coverage.identifier,
        defaults.get("subscriber_id"),
    )
    subscriber_name = first_non_empty(
        participants.subscriber.name,
        participants.coverage.name,
        participants.holder.name,
        defaults.get("subscriber_name"),
    )
    relationship = first_non_empty(
        participants.coverage.relationship,
        participants.subscriber.relationship,
        participants.holder.relationship,
        defaults.get("relationship"),
    )
    return {
        "member_id": member_id,
        "subscriber_id": subscriber_id,
        "subscriber_name": subscriber_name,
        "relationship": relationship,
    }


def _extract_status_code(act: ElementType, ns: dict[str, str]) -> Optional[str]:
    """Return the normalized status code for a coverage act."""
    status_el = act.find("hl7:statusCode", namespaces=ns)
    return clean_text(
        status_el.get("code") if isinstance(status_el, ElementType) else None
    )


def _extract_group_number(act: ElementType, ns: dict[str, str]) -> Optional[str]:
    """Return the fallback group number encoded on the act itself."""
    id_el = act.find("hl7:id", namespaces=ns)
    return clean_text(
        id_el.get("extension") if isinstance(id_el, ElementType) else None
    )


def _collect_plan_details(
    tree: ElementTreeType,
    act: ElementType,
    defaults: dict[str, Optional[str]],
    ns: dict[str, str],
) -> dict[str, Optional[str]]:
    """Collect payer and plan metadata for a policy dictionary."""
    payer_name, payer_identifier, plan_name = _extract_payer_details(
        tree, act, defaults, ns
    )
    coverage_type = _extract_coverage_type(act, defaults, ns)
    policy_type = _extract_policy_type(act, defaults)
    source_policy_id = first_non_empty(defaults.get("source_policy_id"))
    group_number = first_non_empty(
        defaults.get("group_number"), _extract_group_number(act, ns)
    )
    return {
        "payer_name": payer_name,
        "payer_identifier": payer_identifier,
        "plan_name": plan_name,
        "coverage_type": coverage_type,
        "policy_type": policy_type,
        "source_policy_id": source_policy_id,
        "group_number": group_number,
    }


def _build_policy(
    tree: ElementTreeType,
    act: ElementType,
    ns: dict[str, str],
    defaults: dict[str, Optional[str]],
) -> Optional[dict[str, Optional[str]]]:
    """Construct a policy dictionary from a coverage act."""
    plan_details = _collect_plan_details(tree, act, defaults, ns)
    participants = _resolve_participants(tree, act, ns)
    date_info = _resolve_dates(act, defaults, participants.coverage, ns)
    member_details = _resolve_member_details(participants, defaults)
    status_code = first_non_empty(_extract_status_code(act, ns), defaults.get("status"))
    notes = first_non_empty(extract_notes(tree, act, ns), defaults.get("notes"))

    policy = {
        **plan_details,
        **member_details,
        **date_info,
        "status": status_code,
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


def parse_insurance(
    tree: ElementTreeType, ns: dict[str, str]
) -> list[dict[str, Optional[str]]]:
    """Extract insurance policies from a CCD document."""
    policies: list[dict[str, Optional[str]]] = []

    for section in _insurance_sections(tree, ns):
        for entry in iter_elements(section.findall("hl7:entry", namespaces=ns)):
            acts = [
                act
                for act in iter_elements(entry.findall("hl7:act", namespaces=ns))
                if _is_coverage_act(act, ns)
            ]
            if not acts:
                continue

            for container in acts:
                defaults = _prepare_defaults(tree, container, ns)
                detail_acts = _collect_detail_acts(container, ns) or [container]
                for coverage_act in detail_acts:
                    policy = _build_policy(tree, coverage_act, ns, defaults)
                    if policy:
                        policies.append(policy)

    return policies
