# Purpose: Persist insurance coverage metadata into the SQLite datastore.
# Author: Codex + Lauren
# Date: 2025-10-19
# Related tests: tests/test_insurance_service.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Insurance ingestion helpers."""

from __future__ import annotations

import sqlite3
from typing import Mapping, Sequence, Tuple, TypedDict

from health_records_collection.db.utils import execute_update
from health_records_collection.services.common import (
    clean_str,
    coerce_int,
    ensure_mapping_sequence,
)

__all__ = ["upsert_insurance"]


class InsuranceData(TypedDict, total=False):
    """Type-safe insurance policy field dictionary."""

    payer_name: str | None
    plan_name: str | None
    member_id: str | None
    payer_identifier: str | None
    group_number: str | None
    ds_id: int | None
    coverage_type: str | None
    policy_type: str | None
    subscriber_id: str | None
    subscriber_name: str | None
    relationship: str | None
    effective_date: str | None
    expiration_date: str | None
    status: str | None
    source_policy_id: str | None
    notes: str | None
    patient_id: int


def _extract_insurance_fields(policy: Mapping[str, object]) -> InsuranceData:
    """Extract and clean all insurance fields from a policy entry."""
    return {
        "payer_name": clean_str(policy.get("payer_name")),
        "plan_name": clean_str(policy.get("plan_name")),
        "member_id": clean_str(policy.get("member_id")),
        "payer_identifier": clean_str(policy.get("payer_identifier")),
        "group_number": clean_str(policy.get("group_number")),
        "ds_id": coerce_int(policy.get("data_source_id")),
        "coverage_type": clean_str(policy.get("coverage_type")),
        "policy_type": clean_str(policy.get("policy_type")),
        "subscriber_id": clean_str(policy.get("subscriber_id")),
        "subscriber_name": clean_str(policy.get("subscriber_name")),
        "relationship": clean_str(policy.get("relationship")),
        "effective_date": clean_str(policy.get("effective_date")),
        "expiration_date": clean_str(policy.get("expiration_date")),
        "status": clean_str(policy.get("status")),
        "source_policy_id": clean_str(policy.get("source_policy_id")),
        "notes": clean_str(policy.get("notes")),
    }  # type: ignore


def _find_existing_insurance(
    cur: sqlite3.Cursor,
    patient_id: int,
    insurance_data: InsuranceData,
) -> tuple | None:
    """Find existing insurance record in database."""
    return cur.execute(
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
            patient_id,
            insurance_data.get("payer_name") or "",
            insurance_data.get("plan_name") or "",
            insurance_data.get("member_id") or "",
            insurance_data.get("group_number") or "",
        ),
    ).fetchone()


def _build_insurance_update_queries(
    insurance_data: InsuranceData,
    existing: tuple,
) -> tuple[list[str], list[object]]:
    """Build update SQL and parameters for changed fields."""
    (
        _,
        existing_coverage,
        existing_policy_type,
        existing_subscriber_id,
        existing_subscriber_name,
        existing_relationship,
        existing_effective,
        existing_expiration,
        existing_status,
        existing_payer_identifier,
        existing_ds_id,
        existing_source_policy_id,
        existing_notes,
    ) = existing

    updates: list[str] = []
    params: list[object] = []

    column_updates = [
        ("coverage_type", insurance_data.get("coverage_type"), existing_coverage),
        ("policy_type", insurance_data.get("policy_type"), existing_policy_type),
        (
            "subscriber_id",
            insurance_data.get("subscriber_id"),
            existing_subscriber_id,
        ),
        (
            "subscriber_name",
            insurance_data.get("subscriber_name"),
            existing_subscriber_name,
        ),
        (
            "relationship",
            insurance_data.get("relationship"),
            existing_relationship,
        ),
        (
            "effective_date",
            insurance_data.get("effective_date"),
            existing_effective,
        ),
        (
            "expiration_date",
            insurance_data.get("expiration_date"),
            existing_expiration,
        ),
        ("status", insurance_data.get("status"), existing_status),
        (
            "payer_identifier",
            insurance_data.get("payer_identifier"),
            existing_payer_identifier,
        ),
        (
            "source_policy_id",
            insurance_data.get("source_policy_id"),
            existing_source_policy_id,
        ),
        ("notes", insurance_data.get("notes"), existing_notes),
    ]

    for column, new_value, old_value in column_updates:
        if new_value and (old_value or "") != new_value:
            updates.append(f"{column} = ?")
            params.append(new_value)

    ds_id = insurance_data.get("ds_id")
    if ds_id is not None and (existing_ds_id or 0) != ds_id:
        updates.append("data_source_id = ?")
        params.append(ds_id)

    return updates, params


def _insert_new_insurance(
    cur: sqlite3.Cursor,
    patient_id: int,
    insurance_data: InsuranceData,
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
            patient_id,
            insurance_data.get("payer_name"),
            insurance_data.get("plan_name"),
            insurance_data.get("coverage_type"),
            insurance_data.get("policy_type"),
            insurance_data.get("member_id"),
            insurance_data.get("group_number"),
            insurance_data.get("subscriber_id"),
            insurance_data.get("subscriber_name"),
            insurance_data.get("relationship"),
            insurance_data.get("effective_date"),
            insurance_data.get("expiration_date"),
            insurance_data.get("status"),
            insurance_data.get("payer_identifier"),
            insurance_data.get("source_policy_id"),
            insurance_data.get("notes"),
            insurance_data.get("ds_id"),
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
        # Extract all fields into type-safe dict
        insurance_data: InsuranceData = _extract_insurance_fields(policy)

        if not (
            insurance_data.get("payer_name")
            or insurance_data.get("plan_name")
            or insurance_data.get("member_id")
            or insurance_data.get("group_number")
        ):
            continue

        insurance_data["patient_id"] = patient_id  # type: ignore

        # Find existing record
        existing = _find_existing_insurance(cur, patient_id, insurance_data)

        if existing:
            # Build updates for changed fields
            updates, params = _build_insurance_update_queries(
                insurance_data,
                existing,
            )

            policy_id = existing[0]
            if execute_update(cur, "insurance", updates, params, policy_id):
                updated += 1
            continue

        # Insert new record
        _insert_new_insurance(cur, patient_id, insurance_data)
        inserted += 1

    conn.commit()
    return (inserted, updated)
