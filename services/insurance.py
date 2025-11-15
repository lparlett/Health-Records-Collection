# Purpose: Persist insurance coverage metadata into the SQLite datastore.
# Author: Codex + Lauren
# Date: 2025-10-19
# Related tests: tests/test_insurance_service.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Insurance ingestion helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence, Tuple

from health_records_collection.db.utils import execute_update
from health_records_collection.services.common import (
    clean_str,
    coerce_int,
    ensure_mapping_sequence,
)

__all__ = ["upsert_insurance"]


@dataclass
class SubscriberInfo:
    """Subscriber metadata for an insurance policy."""

    subscriber_id: Optional[str] = None
    subscriber_name: Optional[str] = None
    relationship: Optional[str] = None


@dataclass
class InsuranceIdentifiers:
    """Identifier fields for an insurance policy."""

    member_id: Optional[str] = None
    group_number: Optional[str] = None
    payer_identifier: Optional[str] = None
    source_policy_id: Optional[str] = None


@dataclass
class InsuranceDates:
    """Date metadata for insurance policies."""

    effective_date: Optional[str] = None
    expiration_date: Optional[str] = None


@dataclass
class InsuranceRecord:
    """Normalized insurance policy data ready for persistence."""

    patient_id: int
    payer_name: Optional[str] = None
    plan_name: Optional[str] = None
    coverage_type: Optional[str] = None
    policy_type: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    data_source_id: Optional[int] = None
    subscriber: SubscriberInfo = field(default_factory=SubscriberInfo)
    identifiers: InsuranceIdentifiers = field(default_factory=InsuranceIdentifiers)
    dates: InsuranceDates = field(default_factory=InsuranceDates)

    @property
    def subscriber_id(self) -> Optional[str]:
        return self.subscriber.subscriber_id

    @property
    def subscriber_name(self) -> Optional[str]:
        return self.subscriber.subscriber_name

    @property
    def relationship(self) -> Optional[str]:
        return self.subscriber.relationship

    @property
    def effective_date(self) -> Optional[str]:
        return self.dates.effective_date

    @property
    def expiration_date(self) -> Optional[str]:
        return self.dates.expiration_date

    @property
    def member_id(self) -> Optional[str]:
        return self.identifiers.member_id

    @property
    def group_number(self) -> Optional[str]:
        return self.identifiers.group_number

    @property
    def payer_identifier(self) -> Optional[str]:
        return self.identifiers.payer_identifier

    @property
    def source_policy_id(self) -> Optional[str]:
        return self.identifiers.source_policy_id


@dataclass
class ExistingInsuranceRow:
    """Existing insurance row fetched from the database."""

    id: int
    coverage_type: Optional[str]
    policy_type: Optional[str]
    subscriber: SubscriberInfo
    dates: InsuranceDates
    status: Optional[str]
    payer_identifier: Optional[str]
    data_source_id: Optional[int]
    source_policy_id: Optional[str]
    notes: Optional[str]

    @property
    def subscriber_id(self) -> Optional[str]:
        return self.subscriber.subscriber_id

    @property
    def subscriber_name(self) -> Optional[str]:
        return self.subscriber.subscriber_name

    @property
    def relationship(self) -> Optional[str]:
        return self.subscriber.relationship

    @property
    def effective_date(self) -> Optional[str]:
        return self.dates.effective_date

    @property
    def expiration_date(self) -> Optional[str]:
        return self.dates.expiration_date


def _build_insurance_record(
    policy: Mapping[str, object],
    patient_id: int,
) -> Optional[InsuranceRecord]:
    """Return a normalized insurance record or None if insufficient data."""
    record = InsuranceRecord(
        patient_id=patient_id,
        payer_name=clean_str(policy.get("payer_name")),
        plan_name=clean_str(policy.get("plan_name")),
        coverage_type=clean_str(policy.get("coverage_type")),
        policy_type=clean_str(policy.get("policy_type")),
        status=clean_str(policy.get("status")),
        notes=clean_str(policy.get("notes")),
        data_source_id=coerce_int(policy.get("data_source_id")),
    )
    record.identifiers = InsuranceIdentifiers(
        member_id=clean_str(policy.get("member_id")),
        group_number=clean_str(policy.get("group_number")),
        payer_identifier=clean_str(policy.get("payer_identifier")),
        source_policy_id=clean_str(policy.get("source_policy_id")),
    )
    record.subscriber = SubscriberInfo(
        subscriber_id=clean_str(policy.get("subscriber_id")),
        subscriber_name=clean_str(policy.get("subscriber_name")),
        relationship=clean_str(policy.get("relationship")),
    )
    record.dates = InsuranceDates(
        effective_date=clean_str(policy.get("effective_date")),
        expiration_date=clean_str(policy.get("expiration_date")),
    )
    if not (
        record.payer_name
        or record.plan_name
        or record.identifiers.member_id
        or record.identifiers.group_number
    ):
        return None
    return record


def _find_existing_insurance(
    cur: sqlite3.Cursor,
    record: InsuranceRecord,
) -> Optional[ExistingInsuranceRow]:
    """Find existing insurance record in database."""
    row = cur.execute(
        """
        SELECT
            id,
            coverage_type,
            policy_type,
            subscriber_id,
            subscriber_name,
            relationship,
            effective_date,
            expiration_date,
            status,
            payer_identifier,
            data_source_id,
            source_policy_id,
            notes
          FROM insurance
         WHERE patient_id = ?
           AND COALESCE(payer_name, '') = COALESCE(?, '')
           AND COALESCE(plan_name, '') = COALESCE(?, '')
           AND COALESCE(member_id, '') = COALESCE(?, '')
          AND COALESCE(group_number, '') = COALESCE(?, '')
        """,
        (
            record.patient_id,
            record.payer_name or "",
            record.plan_name or "",
            record.member_id or "",
            record.group_number or "",
        ),
    ).fetchone()
    if row is None:
        return None
    return ExistingInsuranceRow(
        id=int(row[0]),
        coverage_type=row[1],
        policy_type=row[2],
        subscriber=SubscriberInfo(
            subscriber_id=row[3],
            subscriber_name=row[4],
            relationship=row[5],
        ),
        dates=InsuranceDates(
            effective_date=row[6],
            expiration_date=row[7],
        ),
        status=row[8],
        payer_identifier=row[9],
        data_source_id=row[10],
        source_policy_id=row[11],
        notes=row[12],
    )


def _build_insurance_update_queries(
    record: InsuranceRecord,
    existing: ExistingInsuranceRow,
) -> tuple[list[str], list[object]]:
    """Build update SQL and parameters for changed fields."""
    column_updates = [
        ("coverage_type", record.coverage_type, existing.coverage_type),
        ("policy_type", record.policy_type, existing.policy_type),
        ("subscriber_id", record.subscriber_id, existing.subscriber_id),
        ("subscriber_name", record.subscriber_name, existing.subscriber_name),
        ("relationship", record.relationship, existing.relationship),
        ("effective_date", record.effective_date, existing.effective_date),
        ("expiration_date", record.expiration_date, existing.expiration_date),
        ("status", record.status, existing.status),
        ("payer_identifier", record.payer_identifier, existing.payer_identifier),
        ("source_policy_id", record.source_policy_id, existing.source_policy_id),
        ("notes", record.notes, existing.notes),
    ]

    updates: list[str] = []
    params: list[object] = []
    for column, new_value, old_value in column_updates:
        if new_value and (old_value or "") != new_value:
            updates.append(f"{column} = ?")
            params.append(new_value)

    if record.data_source_id is not None and (
        existing.data_source_id or 0
    ) != record.data_source_id:
        updates.append("data_source_id = ?")
        params.append(record.data_source_id)

    return updates, params


def _insert_new_insurance(
    cur: sqlite3.Cursor,
    record: InsuranceRecord,
) -> None:
    """Insert a new insurance record."""
    cur.execute(
        """
        INSERT INTO insurance (
            patient_id,
            payer_name,
            plan_name,
            coverage_type,
            policy_type,
            member_id,
            group_number,
            subscriber_id,
            subscriber_name,
            relationship,
            effective_date,
            expiration_date,
            status,
            payer_identifier,
            source_policy_id,
            notes,
            data_source_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.patient_id,
            record.payer_name,
            record.plan_name,
            record.coverage_type,
            record.policy_type,
            record.member_id,
            record.group_number,
            record.subscriber_id,
            record.subscriber_name,
            record.relationship,
            record.effective_date,
            record.expiration_date,
            record.status,
            record.payer_identifier,
            record.source_policy_id,
            record.notes,
            record.data_source_id,
        ),
    )


def upsert_insurance(
    conn: sqlite3.Connection,
    patient_id: int,
    policies: Sequence[Mapping[str, object]],
) -> Tuple[int, int]:
    """Insert or update insurance policy details for a patient.

    Args:
        conn: Active SQLite connection.
        patient_id: Patient identifier.
        policies: Parsed insurance dictionaries.

    Returns:
        Tuple[int, int]: (inserted_count, updated_count)
    """
    mapping_iter = list(ensure_mapping_sequence(policies))
    if not mapping_iter:
        return (0, 0)

    cur = conn.cursor()
    inserted = 0
    updated = 0

    for policy in mapping_iter:
        record = _build_insurance_record(policy, patient_id)
        if record is None:
            continue

        existing = _find_existing_insurance(cur, record)

        if existing:
            updates, params = _build_insurance_update_queries(record, existing)

            if execute_update(cur, "insurance", updates, params, existing.id):
                updated += 1
            continue

        _insert_new_insurance(cur, record)
        inserted += 1

    conn.commit()
    return (inserted, updated)
