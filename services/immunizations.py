# Purpose: Persist immunization administrations into the SQLite datastore.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_immunizations_service.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Immunization ingestion helpers."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence, Tuple

from health_records_collection.services.common import clean_str, coerce_int

__all__ = ["insert_immunizations"]


@dataclass
class ImmunizationRecord:
    """Normalized immunization entry ready for persistence."""

    patient_id: int
    vaccine_name: str
    cvx_code: Optional[str]
    date_administered: Optional[str]
    status: Optional[str]
    lot_number: Optional[str]
    notes: Optional[str]
    data_source_id: Optional[int]


def _normalise_vaccine_name(name: object, fallback: object) -> Optional[str]:
    """Return the preferred vaccine name using a fallback when necessary."""
    primary = clean_str(name)
    if primary:
        return primary
    secondary = clean_str(fallback)
    if secondary:
        return secondary
    return None


def _prepare_notes(
    product_name: Optional[str], existing_notes: Optional[str]
) -> Optional[str]:
    """Compose a note string that includes product metadata when available."""
    parts: list[str] = []
    if product_name:
        parts.append(f"Product: {product_name}")
    if existing_notes:
        parts.append(existing_notes)
    if not parts:
        return None
    return "; ".join(parts)


def _normalise_codes(codes: object) -> Optional[str]:
    """Flatten a collection of CVX codes into a canonical, comma-separated string."""
    if isinstance(codes, str):
        return clean_str(codes)
    if isinstance(codes, Iterable):
        unique_codes: set[str] = set()
        for raw_code in codes:
            cleaned = clean_str(raw_code)
            if cleaned:
                unique_codes.add(cleaned)
        if not unique_codes:
            return None
        return ", ".join(sorted(unique_codes))
    return clean_str(codes)


def insert_immunizations(
    conn: sqlite3.Connection,
    patient_id: int,
    immunizations: Sequence[Mapping[str, object]],
) -> None:
    """Persist immunization data, enforcing uniqueness on CVX code and
        administration date.

    Args:
        conn: Active SQLite connection.
        patient_id: Identifier for the patient receiving the immunisation.
        immunizations: Sequence of parsed immunisation dictionaries.
    """
    if not immunizations:
        return

    cur = conn.cursor()
    existing_keys = _load_existing_keys(cur, patient_id)

    rows_to_insert: list[Tuple[object, ...]] = []

    for entry in immunizations:
        record = _build_record(patient_id, entry)
        if record is None:
            continue

        if _handle_existing_record(cur, existing_keys, record):
            continue

        rows_to_insert.append(
            (
                record.patient_id,
                record.vaccine_name,
                record.cvx_code,
                record.date_administered,
                record.status,
                record.lot_number,
                record.notes,
                record.data_source_id,
            )
        )

    if not rows_to_insert:
        return

    cur.executemany(
        """
        INSERT INTO immunization (
            patient_id,
            vaccine_name,
            cvx_code,
            date_administered,
            status,
            lot_number,
            notes,
            data_source_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows_to_insert,
    )
    conn.commit()


def _load_existing_keys(cur: sqlite3.Cursor, patient_id: int) -> set[tuple[str, str]]:
    """Return existing (cvx_code, date_administered) pairs for patient."""
    existing_keys: set[tuple[str, str]] = set()
    for row in cur.execute(
        "SELECT cvx_code, date_administered FROM immunization WHERE patient_id = ?",
        (patient_id,),
    ):
        existing_keys.add(
            (
                clean_str(row[0]) or "",
                clean_str(row[1]) or "",
            )
        )
    return existing_keys


def _build_record(
    patient_id: int, entry: Mapping[str, object]
) -> Optional[ImmunizationRecord]:
    """Return a normalized immunization record or None if insufficient data."""
    date_administered = clean_str(entry.get("date"))
    cvx_code_value = _normalise_codes(entry.get("cvx_codes"))
    product_name = clean_str(entry.get("product_name"))
    vaccine_name = _normalise_vaccine_name(entry.get("vaccine_name"), product_name)
    if not vaccine_name and cvx_code_value:
        vaccine_name = cvx_code_value
    if not vaccine_name and product_name:
        vaccine_name = product_name
    if not vaccine_name and cvx_code_value is None and date_administered is None:
        return None

    lot_number = clean_str(entry.get("lot_number"))
    status = clean_str(entry.get("status"))
    notes_raw = clean_str(entry.get("notes"))
    notes_value = _prepare_notes(product_name, notes_raw)

    return ImmunizationRecord(
        patient_id=patient_id,
        vaccine_name=vaccine_name or "",
        cvx_code=cvx_code_value,
        date_administered=date_administered,
        status=status,
        lot_number=lot_number,
        notes=notes_value,
        data_source_id=coerce_int(entry.get("data_source_id")),
    )


def _handle_existing_record(
    cur: sqlite3.Cursor,
    existing_keys: set[tuple[str, str]],
    record: ImmunizationRecord,
) -> bool:
    """Update existing row when appropriate. Returns True if record already exists."""
    key = (record.cvx_code or "", record.date_administered or "")
    if key not in existing_keys:
        existing_keys.add(key)
        return False

    if record.data_source_id is None:
        return True

    cur.execute(
        """
        UPDATE immunization
           SET data_source_id = COALESCE(data_source_id, ?)
         WHERE patient_id = ?
           AND COALESCE(cvx_code, '') = COALESCE(?, '')
           AND COALESCE(date_administered, '') = COALESCE(?, '')
        """,
        (
            record.data_source_id,
            record.patient_id,
            record.cvx_code,
            record.date_administered,
        ),
    )
    return True
