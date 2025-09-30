"""Provider database helpers."""
from __future__ import annotations

import sqlite3
from typing import Optional

from parsers.providers import (
    is_probable_organization,
    normalize_organization_key,
    normalize_person_key,
    parse_person_name,
)

ProviderKey = str
_PROVIDER_CACHE: dict[ProviderKey, int] = {}

__all__ = ["get_or_create_provider", "ProviderKey"]


def get_or_create_provider(
    conn: sqlite3.Connection,
    name: Optional[str],
    *,
    npi: Optional[str] = None,
    specialty: Optional[str] = None,
    organization: Optional[str] = None,
    credentials: Optional[str] = None,
    entity_type: str = "person",
) -> Optional[int]:
    """Look up or insert a provider record (person or organization) and cache the result."""
    raw_name = (name or "").strip()
    raw_org = (organization or "").strip()

    if entity_type == "person" and is_probable_organization(raw_name):
        entity_type = "organization"

    if entity_type == "organization":
        if not raw_name:
            return None
        normalized_key = normalize_organization_key(raw_name)
        given_name = None
        family_name = None
        credentials_value = None
        display_name = raw_name
        organization_value = raw_name
    else:
        if not raw_name:
            return None
        given_name, family_name, parsed_credentials = parse_person_name(raw_name)
        credentials_value = credentials or parsed_credentials
        normalized_key = normalize_person_key(given_name, family_name, raw_name)
        display_name = raw_name
        organization_value = raw_org or None

    if not normalized_key:
        return None

    cache_key: ProviderKey = normalized_key
    if cache_key in _PROVIDER_CACHE:
        return _PROVIDER_CACHE[cache_key]

    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM provider WHERE normalized_key = ?",
        (normalized_key,),
    )
    row = cur.fetchone()
    if row:
        provider_id = row[0]
        _PROVIDER_CACHE[cache_key] = provider_id
        return provider_id

    npi_clean = npi.strip() if npi else None
    specialty_clean = specialty.strip() if specialty else None

    cur.execute(
        """
        INSERT INTO provider (
            name,
            given_name,
            family_name,
            credentials,
            npi,
            specialty,
            organization,
            normalized_key,
            entity_type
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            display_name,
            given_name,
            family_name,
            credentials_value,
            npi_clean,
            specialty_clean,
            organization_value,
            normalized_key,
            entity_type,
        ),
    )
    conn.commit()
    provider_id = cur.lastrowid
    _PROVIDER_CACHE[cache_key] = provider_id
    return provider_id
