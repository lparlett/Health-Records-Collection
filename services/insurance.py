# Purpose: Persist insurance coverage metadata into the SQLite datastore.
# Author: Codex + Lauren
# Date: 2025-10-19
# Related tests: tests/test_insurance_service.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Insurance ingestion helpers."""

from __future__ import annotations

import sqlite3
from typing import Mapping, Sequence, Tuple

from services.common import clean_str, coerce_int, ensure_mapping_sequence

__all__ = ["upsert_insurance"]


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
        payer_name = clean_str(policy.get("payer_name"))
        plan_name = clean_str(policy.get("plan_name"))
        member_id = clean_str(policy.get("member_id"))
        payer_identifier = clean_str(policy.get("payer_identifier"))
        group_number = clean_str(policy.get("group_number"))
        if not (payer_name or plan_name or member_id or group_number):
            continue

        ds_id = coerce_int(policy.get("data_source_id"))
        coverage_type = clean_str(policy.get("coverage_type"))
        policy_type = clean_str(policy.get("policy_type"))
        subscriber_id = clean_str(policy.get("subscriber_id"))
        subscriber_name = clean_str(policy.get("subscriber_name"))
        relationship = clean_str(policy.get("relationship"))
        effective_date = clean_str(policy.get("effective_date"))
        expiration_date = clean_str(policy.get("expiration_date"))
        status = clean_str(policy.get("status"))
        source_policy_id = clean_str(policy.get("source_policy_id"))
        notes = clean_str(policy.get("notes"))

        existing = cur.execute(
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
                payer_name or "",
                plan_name or "",
                member_id or "",
                group_number or "",
            ),
        ).fetchone()

        if existing:
            (
                policy_id,
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
                ("coverage_type", coverage_type, existing_coverage),
                ("policy_type", policy_type, existing_policy_type),
                ("subscriber_id", subscriber_id, existing_subscriber_id),
                ("subscriber_name", subscriber_name, existing_subscriber_name),
                ("relationship", relationship, existing_relationship),
                ("effective_date", effective_date, existing_effective),
                ("expiration_date", expiration_date, existing_expiration),
                ("status", status, existing_status),
                ("payer_identifier", payer_identifier, existing_payer_identifier),
                ("source_policy_id", source_policy_id, existing_source_policy_id),
                ("notes", notes, existing_notes),
            ]

            for column, new_value, old_value in column_updates:
                if new_value and (old_value or "") != new_value:
                    updates.append(f"{column} = ?")
                    params.append(new_value)

            if ds_id is not None and (existing_ds_id or 0) != ds_id:
                updates.append("data_source_id = ?")
                params.append(ds_id)

            if updates:
                params.append(policy_id)
                cur.execute(
                    f"UPDATE insurance SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
                updated += 1
            continue

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
                ds_id,
            ),
        )
        inserted += 1

    conn.commit()
    return (inserted, updated)
