# Purpose: Normalise provider names and determine provider types from CCD data.
# Author: Codex assistant
# Date: 2025-10-11
# Related tests: tests/test_parsers.py
# AI-assisted: Portions of this file were generated with AI assistance.

"""Provider parsing and normalisation utilities."""

from __future__ import annotations

import re
from typing import Optional, Tuple

KEYWORDS = (
    " hospital",
    " clinic",
    " health",
    " medical",
    " medicine",
    " center",
    " centre",
    " physicians",
    " associates",
    " associate",
    " the",
    " services",
    " department",
    " university",
    " institute",
    " group",
    " surgery",
    " of ",
)


__all__ = [
    "normalize_spaces",
    "parse_person_name",
    "normalize_person_key",
    "normalize_organization_key",
    "is_probable_organization",
]


CREDENTIAL_PATTERN = re.compile(r"^[A-Z]{2,}(?:[./][A-Z]{2,})*$")
CAMEL_PATTERN = re.compile(r"[A-Z][^A-Z]*")


def _split_comma_credentials(name: str) -> Tuple[str, Optional[str]]:
    parts = [part.strip() for part in name.split(",") if part.strip()]
    if not parts:
        return name.strip(), None
    name_part = parts[0]
    comma_credentials = " ".join(parts[1:]) if len(parts) > 1 else None
    if comma_credentials:
        comma_credentials = comma_credentials.strip() or None
    return name_part, comma_credentials


def _tokenize_name(name_part: str) -> list[str]:
    return [token.strip() for token in name_part.split() if token.strip()]


def _extract_trailing_credentials(tokens: list[str]) -> Tuple[list[str], list[str]]:
    """Split trailing credential tokens (e.g., MD, FACP) from the name."""
    tokens = tokens.copy()
    credential_tokens: list[str] = []
    while tokens:
        token = tokens[-1]
        cleaned = re.sub(r"[^A-Za-z./]", "", token)
        stripped = cleaned.replace(".", "")
        if CREDENTIAL_PATTERN.fullmatch(stripped):
            credential_tokens.insert(0, stripped)
            tokens.pop()
            continue
        suffix_match = re.match(r"^(.*?)([A-Z]{2,})$", stripped)
        if suffix_match and len(tokens) == 1:
            suffix = suffix_match.group(2)
            base_original = token[: len(token) - len(suffix)]
            if base_original.strip():
                tokens[-1] = base_original
            else:
                tokens.pop()
            credential_tokens.insert(0, suffix)
            continue
        break
    return tokens, credential_tokens


def _split_single_token(tokens: list[str]) -> list[str]:
    """Split camel-cased tokens such as 'JohnSmith' into separate components."""
    if len(tokens) != 1:
        return tokens
    token = tokens[0]
    camel_parts = CAMEL_PATTERN.findall(token)
    if len(camel_parts) >= 2:
        return [" ".join(camel_parts[:-1]), camel_parts[-1]]
    return tokens


def _assign_name_components(tokens: list[str]) -> Tuple[Optional[str], Optional[str]]:
    if not tokens:
        return None, None
    if len(tokens) == 1:
        return None, tokens[0]
    return " ".join(tokens[:-1]), tokens[-1]


def _combine_credentials(
    comma_credentials: Optional[str],
    credential_tokens: list[str],
) -> Optional[str]:
    components = []
    if comma_credentials:
        components.append(comma_credentials)
    if credential_tokens:
        components.append(" ".join(credential_tokens))
    if not components:
        return None
    combined = " ".join(components).strip()
    return combined or None


def normalize_spaces(value: str) -> str:
    """Return a lowercase string with all whitespace removed.

    Args:
        value: Raw provider name or component.

    Returns:
        str: Normalised string suitable for comparison.
    """
    return "".join(value.split()).lower()


def parse_person_name(raw: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse a provider name into given, family, and credential components."""
    name = (raw or "").strip()
    if not name:
        return None, None, None
    name = re.sub(r"\s+", " ", name)

    name_part, comma_credentials = _split_comma_credentials(name)
    tokens = _tokenize_name(name_part)
    tokens, credential_tokens = _extract_trailing_credentials(tokens)
    tokens = _split_single_token(tokens)
    given, family = _assign_name_components(tokens)
    credentials_value = _combine_credentials(comma_credentials, credential_tokens)
    return given, family, credentials_value


def normalize_person_key(
    given: Optional[str],
    family: Optional[str],
    fallback: str,
) -> str:
    """Create a normalisation key for a person provider.

    Args:
        given: The provider's given name.
        family: The provider's family name.
        fallback: Source string used if the parsed name is incomplete.

    Returns:
        str: Lowercase normalisation key.
    """
    base = ""
    if given:
        base += given
    if family:
        base += family
    base = "".join(base.split())
    if base:
        return base.lower()
    return normalize_spaces(fallback)


def normalize_organization_key(name: str) -> str:
    """Create a normalisation key for an organisation provider.

    Args:
        name: Organisation display name.

    Returns:
        str: Lowercase normalisation key.
    """
    return normalize_spaces(name)


def is_probable_organization(name: str) -> bool:
    """Heuristically determine if the display name refers to an organisation.

    Args:
        name: Provider display name.

    Returns:
        bool: ``True`` when the name likely describes an organisation.
    """
    lower = name.strip().lower()
    if not lower:
        return False
    if any(keyword in lower for keyword in KEYWORDS):
        return True
    tokens = lower.split()
    if len(tokens) >= 3 and any(
        token
        in {
            "of",
            "for",
            "and",
            "medical",
            "health",
            "hospital",
            "clinic",
            "physicians",
            "associates",
            "services",
            "group",
            "institute",
            "university",
        }
        for token in tokens
    ):
        return True
    return False
