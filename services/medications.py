# Purpose: Persist medication administrations into the SQLite database.
# Author: Codex assistant
# Date: 2025-10-12
# Related tests: tests/test_ingest.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Medication ingestion services."""

from __future__ import annotations

import sqlite3
from types import ModuleType
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence, Tuple

from health_records_collection.services.common import clean_str, coerce_int
from health_records_collection.services.encounters import (
    EncounterLookup,
    find_encounter_id,
)

# Initialize module level variables
sqlcipher_module: None | ModuleType = None
sqlcipher_integrity_error: type[Exception] | None = None

try:  # pragma: no cover - depends on optional SQLCipher driver
    from sqlcipher3 import dbapi2 as sqlcipher_dbapi2
    from sqlcipher3.dbapi2 import IntegrityError as SqlCipherIntegrityError

    sqlcipher_module = sqlcipher_dbapi2
    sqlcipher_integrity_error = SqlCipherIntegrityError
except ImportError:  # pragma: no cover - fallback for plain sqlite
    pass

# Define integrity error types to catch based on available database modules
if sqlcipher_integrity_error is not None:
    INTEGRITY_ERRORS: Tuple[type[Exception], ...] = (
        sqlite3.IntegrityError,
        sqlcipher_integrity_error,
    )
else:
    INTEGRITY_ERRORS = (sqlite3.IntegrityError,)

__all__ = ["insert_medications"]


@dataclass
class MedicationRecord:
    """Normalized medication data for persistence."""

    patient_id: int
    encounter_id: Optional[int]
    name: Optional[str]
    dose: Optional[str]
    route: Optional[str]
    frequency: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    status: Optional[str]
    notes: Optional[str]
    data_source_id: Optional[int]

    def as_row(self) -> tuple[object, ...]:
        """Return tuple representation for SQL insertion."""
        return (
            self.patient_id,
            self.encounter_id,
            self.name,
            self.dose,
            self.route,
            self.frequency,
            self.start_date,
            self.end_date,
            self.status,
            self.notes,
            self.data_source_id,
        )


def insert_medications(
    conn: sqlite3.Connection,
    patient_id: int,
    meds: Sequence[Mapping[str, object]],
) -> int:
    """Store medication administrations and align them with encounters.

    Args:
        conn: Active SQLite connection.
        patient_id: Identifier for the patient owning the administrations.
        meds: Collection of parsed medication entries.

    Returns:
        int: Number of duplicate entries detected during insertion.
    """
    if not meds:
        return 0

    # Static SQL query with fixed column list
    INSERT_MEDICATION_SQL = """
        INSERT INTO medication (
            patient_id,
            encounter_id,
            name,
            dose,
            route,
            frequency,
            start_date,
            end_date,
            status,
            notes,
            data_source_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    cur = conn.cursor()
    duplicates = 0
    for med in meds:
        record = _build_medication_record(conn, patient_id, med)
        try:
            cur.execute(INSERT_MEDICATION_SQL, record.as_row())
        except INTEGRITY_ERRORS:
            duplicates += 1
            _update_existing_medication(cur, record)

    conn.commit()
    return duplicates


def _build_medication_record(
    conn: sqlite3.Connection,
    patient_id: int,
    med: Mapping[str, object],
) -> MedicationRecord:
    """Return normalized medication record."""
    notes = _compose_notes(clean_str(med.get("notes")), clean_str(med.get("rxnorm")))
    encounter_id = _resolve_encounter(conn, patient_id, med)
    start_date = clean_str(med.get("start_bucket")) or clean_str(med.get("start"))
    end_date = clean_str(med.get("end_bucket")) or clean_str(med.get("end"))

    return MedicationRecord(
        patient_id=patient_id,
        encounter_id=encounter_id,
        name=clean_str(med.get("name")),
        dose=clean_str(med.get("dose")),
        route=clean_str(med.get("route")),
        frequency=clean_str(med.get("frequency")),
        start_date=start_date,
        end_date=end_date,
        status=clean_str(med.get("status")),
        notes=notes,
        data_source_id=coerce_int(med.get("data_source_id")),
    )


def _compose_notes(notes: Optional[str], rxnorm: Optional[str]) -> Optional[str]:
    """Return notes string augmented with RxNorm when present."""
    if rxnorm:
        prefix = f"RxNorm: {rxnorm}"
        return f"{notes} ({prefix})" if notes else prefix
    return notes


def _resolve_encounter(
    conn: sqlite3.Connection,
    patient_id: int,
    med: Mapping[str, object],
) -> Optional[int]:
    """Return encounter ID for medication entry, if resolvable."""
    encounter_date = (
        clean_str(med.get("start"))
        or clean_str(med.get("end"))
        or clean_str(med.get("author_time"))
    )
    provider_name = clean_str(med.get("provider"))
    lookup = EncounterLookup(
        patient_id=patient_id,
        encounter_date=encounter_date,
        provider_name=provider_name,
    )
    return find_encounter_id(conn, lookup)


def _update_existing_medication(
    cur: sqlite3.Cursor,
    record: MedicationRecord,
) -> None:
    """Update existing medication row with missing data source id."""
    if record.data_source_id is None:
        return

    cur.execute(
        """
        UPDATE medication
           SET data_source_id = COALESCE(data_source_id, ?)
         WHERE patient_id = ?
           AND COALESCE(encounter_id, -1) = COALESCE(?, -1)
           AND COALESCE(name, '') = COALESCE(?, '')
           AND COALESCE(dose, '') = COALESCE(?, '')
           AND COALESCE(start_date, '') = COALESCE(?, '')
        """,
        (
            record.data_source_id,
            record.patient_id,
            record.encounter_id,
            record.name or "",
            record.dose or "",
            record.start_date or "",
        ),
    )
