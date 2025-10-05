"""Immunization ingestion helpers."""
from __future__ import annotations

import sqlite3
from typing import List, Optional, Tuple

__all__ = ["insert_immunizations"]


def _clean(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    return " ".join(cleaned.split())


def _normalise_vaccine_name(name: Optional[str], fallback: Optional[str]) -> Optional[str]:
    primary = _clean(name)
    if primary:
        return primary
    secondary = _clean(fallback)
    if secondary:
        return secondary
    return None


def _prepare_notes(product_name: Optional[str], existing_notes: Optional[str]) -> Optional[str]:
    parts: List[str] = []
    if product_name:
        parts.append(f"Product: {product_name}")
    if existing_notes:
        parts.append(existing_notes)
    if not parts:
        return None
    return "; ".join(parts)


def insert_immunizations(conn: sqlite3.Connection, patient_id: int, immunizations: List[dict]) -> None:
    """Persist immunization data, enforcing uniqueness on CVX code and administration date."""
    if not immunizations:
        return

    cur = conn.cursor()
    existing_keys = {
        (
            _clean(row[0]) or "",
            _clean(row[1]) or "",
        )
        for row in cur.execute(
            "SELECT cvx_code, date_administered FROM immunization WHERE patient_id = ?",
            (patient_id,),
        )
    }

    rows_to_insert: List[Tuple[object, ...]] = []

    for entry in immunizations:
        date_administered = _clean(entry.get("date"))

        cvx_codes = entry.get("cvx_codes")
        if isinstance(cvx_codes, (list, tuple, set)):
            unique_codes: set[str] = set()
            for raw_code in cvx_codes:
                cleaned_code = _clean(raw_code)
                if cleaned_code:
                    unique_codes.add(cleaned_code)
            normalised_codes = sorted(unique_codes)
            cvx_code_value = ", ".join(normalised_codes) if normalised_codes else None
        else:
            cvx_code_value = _clean(str(cvx_codes)) if cvx_codes is not None else None

        product_name = _clean(entry.get("product_name"))
        vaccine_name = _normalise_vaccine_name(entry.get("vaccine_name"), product_name)
        if not vaccine_name and cvx_code_value:
            vaccine_name = cvx_code_value
        if not vaccine_name and product_name:
            vaccine_name = product_name
        if not vaccine_name and cvx_code_value is None and date_administered is None:
            continue

        key = (cvx_code_value or "", date_administered or "")
        if key in existing_keys:
            continue
        existing_keys.add(key)

        lot_number = _clean(entry.get("lot_number"))
        status = _clean(entry.get("status"))
        notes_raw = _clean(entry.get("notes"))
        notes_value = _prepare_notes(product_name, notes_raw)

        rows_to_insert.append(
            (
                patient_id,
                vaccine_name,
                cvx_code_value,
                date_administered,
                status,
                lot_number,
                notes_value,
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
            notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows_to_insert,
    )
    conn.commit()
