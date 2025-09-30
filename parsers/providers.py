"""Provider parsing and normalization utilities."""
from __future__ import annotations

import re
from typing import Optional

KEYWORDS = (
    ' hospital',
    ' clinic',
    ' health',
    ' medical',
    ' center',
    ' centre',
    ' physicians',
    ' associates',
    ' services',
    ' department',
    ' university',
    ' institute',
    ' group',
    ' surgery',
    ' of ',
)


__all__ = [
    "normalize_spaces",
    "parse_person_name",
    "normalize_person_key",
    "normalize_organization_key",
    "is_probable_organization",
]


def normalize_spaces(value: str) -> str:
    """Return a lowercase string with all whitespace removed."""
    return ''.join(value.split()).lower()


def parse_person_name(raw: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse a provider name into given, family, and credentials components."""
    name = (raw or '').strip()
    if not name:
        return None, None, None

    parts = [part.strip() for part in name.split(',') if part.strip()]
    if parts:
        name_part = parts[0]
        comma_credentials = ' '.join(parts[1:]) or None if len(parts) > 1 else None
    else:
        name_part = name
        comma_credentials = None

    tokens = name_part.split()
    if not tokens:
        return None, None, comma_credentials

    credential_tokens: list[str] = []
    credential_pattern = re.compile(r'^[A-Z]{2,}(?:[./][A-Z]{2,})*$')

    while tokens:
        token = tokens[-1]
        cleaned = re.sub(r'[^A-Za-z./]', '', token)
        stripped = cleaned.replace('.', '')
        if credential_pattern.fullmatch(stripped):
            credential_tokens.insert(0, stripped)
            tokens.pop()
            continue
        suffix_match = re.match(r'^(.*?)([A-Z]{2,})$', stripped)
        if suffix_match and len(tokens) == 1:
            base = suffix_match.group(1)
            suffix = suffix_match.group(2)
            base_original = token[: len(token) - len(suffix)]
            if base_original:
                tokens[-1] = base_original
            else:
                tokens.pop()
            credential_tokens.insert(0, suffix)
            continue
        break

    if len(tokens) == 1:
        token = tokens[0]
        camel_parts = re.findall(r'[A-Z][^A-Z]*', token)
        if len(camel_parts) >= 2:
            tokens = [' '.join(camel_parts[:-1]), camel_parts[-1]]

    given: Optional[str] = None
    family: Optional[str] = None
    if tokens:
        if len(tokens) == 1:
            family = tokens[0]
        else:
            family = tokens[-1]
            given = ' '.join(tokens[:-1])

    credentials_components: list[str] = []
    if comma_credentials:
        credentials_components.append(comma_credentials)
    if credential_tokens:
        credentials_components.append(' '.join(credential_tokens))
    credentials_value = ' '.join(credentials_components).strip() or None

    return given or None, family or None, credentials_value


def normalize_person_key(
    given: Optional[str],
    family: Optional[str],
    fallback: str,
) -> str:
    """Create a normalization key for a person provider."""
    base = ''
    if given:
        base += given
    if family:
        base += family
    base = ''.join(base.split())
    if base:
        return base.lower()
    return normalize_spaces(fallback)


def normalize_organization_key(name: str) -> str:
    """Create a normalization key for an organization provider."""
    return normalize_spaces(name)


def is_probable_organization(name: str) -> bool:
    lower = name.strip().lower()
    if not lower:
        return False
    if any(keyword in lower for keyword in KEYWORDS):
        return True
    tokens = lower.split()
    if len(tokens) >= 3 and any(
        token in {
            'of', 'for', 'and', 'medical', 'health', 'hospital', 'clinic',
            'physicians', 'associates', 'services', 'group', 'institute', 'university'
        }
        for token in tokens
    ):
        return True
    return False
