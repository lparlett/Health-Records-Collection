# Purpose: Manage CDA stylesheet and localization assets for XML previews.
# Author: Codex + Lauren
# Date: 2025-10-13
# Tests: Manual download via update_static_files; exercised through xml_utils.transform_cda_to_html.
# AI-assisted: Portions of this module were updated with AI assistance.
"""Utilities for resolving CDA static assets used during XML transformations."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

LOGGER = logging.getLogger(__name__)

CDA_CORE_VERSION = "v4.0.1"
RESOURCE_CATALOG: Tuple[Tuple[str, str], ...] = (
    (
        "CDA.xsl",
        "https://raw.githubusercontent.com/HL7/CDA-core-xsl/master/CDA.xsl",
    ),
    (
        "cda_l10n.xml",
        "https://raw.githubusercontent.com/HL7/CDA-core-xsl/master/cda_l10n.xml",
    ),
    (
        "cda_l10n.xsl",
        "https://raw.githubusercontent.com/HL7/CDA-core-xsl/master/cda_l10n.xsl",
    ),
    (
        "cda_l10n.xsd",
        "https://raw.githubusercontent.com/HL7/CDA-core-xsl/master/cda_l10n.xsd",
    ),
    (
        "cda_narrativeblock.xml",
        "https://raw.githubusercontent.com/HL7/CDA-core-xsl/master/cda_narrativeblock.xml",
    ),
)

MINIMUM_RESOURCE_SIZE: Dict[str, int] = {
    "CDA.xsl": 10_000,
    "cda_l10n.xml": 50_000,
    "cda_l10n.xsl": 4_000,
    "cda_l10n.xsd": 3_000,
    "cda_narrativeblock.xml": 2_000,
}

REQUEST_HEADERS = {"User-Agent": "Health-Records-Collection/1.0"}


def get_static_dir() -> Path:
    """Return the static directory path."""
    return Path(__file__).parent / "static"


def get_attribution_block(filename: str) -> str:
    """Return the attribution comment block included with downloaded resources."""
    return (
        "<!--\n"
        f"This {filename} is sourced from the HL7 CDA Core Stylesheet project:\n"
        "https://github.com/HL7/cda-core-xsl\n\n"
        f"Version: {CDA_CORE_VERSION}\n\n"
        "Licensed under the Apache License, Version 2.0 (the \"License\");\n"
        "you may not use this file except in compliance with the License.\n"
        "You may obtain a copy of the License at\n"
        "http://www.apache.org/licenses/LICENSE-2.0\n\n"
        "Please review the upstream repository for updates and attribution.\n"
        "-->"
    )


def backup_file(file_path: Path) -> None:
    """Create a backup of the given file, overwriting any existing backup."""
    if not file_path.exists():
        return
    backup_path = file_path.with_suffix(f"{file_path.suffix}.bak")
    shutil.copy2(file_path, backup_path)


def _is_valid_resource(file_path: Path) -> bool:
    """Heuristically validate the downloaded resource."""
    if not file_path.exists():
        return False

    minimum_size = MINIMUM_RESOURCE_SIZE.get(file_path.name, 1)
    if file_path.stat().st_size < minimum_size:
        LOGGER.warning("Resource %s is unexpectedly small.", file_path.name)
        return False

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        LOGGER.exception("Failed to read resource %s as UTF-8.", file_path.name)
        return False

    if "404" in content[:200] or "<!DOCTYPE html>" in content[:200]:
        LOGGER.error("Resource %s appears to be an HTML error page.", file_path.name)
        return False

    if not content.lstrip().startswith(("<?xml", "<!--")):
        LOGGER.error("Resource %s is missing an XML declaration.", file_path.name)
        return False

    return True


def _merge_attribution(filename: str, payload: str) -> str:
    """Combine upstream payload with attribution inserted safely."""
    attribution = get_attribution_block(filename)
    if payload.startswith("<?xml"):
        first_line, _, remainder = payload.partition("\n")
        return "\n".join(filter(None, (first_line, attribution, remainder)))
    return f"{attribution}\n{payload}"


def update_static_files(force: bool = False) -> None:
    """
    Download or refresh static CDA resources from the HL7 repository.

    Args:
        force: If True, always download regardless of existing files.
    """
    static_dir = get_static_dir()
    static_dir.mkdir(parents=True, exist_ok=True)

    for filename, url in RESOURCE_CATALOG:
        destination = static_dir / filename
        if destination.exists() and not force and _is_valid_resource(destination):
            continue

        LOGGER.info("Downloading %s from %s", filename, url)
        try:
            response = requests.get(url, headers=REQUEST_HEADERS, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            LOGGER.error("Failed to fetch %s: %s", filename, exc)
            continue

        backup_file(destination)
        destination.write_text(
            _merge_attribution(filename, response.text),
            encoding="utf-8",
        )

        if not _is_valid_resource(destination):
            LOGGER.error("Downloaded %s failed validation; restoring backup.", filename)
            backup = destination.with_suffix(f"{destination.suffix}.bak")
            if backup.exists():
                shutil.copy2(backup, destination)
            else:
                destination.unlink(missing_ok=True)


def verify_static_files() -> bool:
    """Return True when all required resources are present and valid."""
    static_dir = get_static_dir()
    all_valid = True
    for filename, _ in RESOURCE_CATALOG:
        path = static_dir / filename
        if not _is_valid_resource(path):
            LOGGER.warning("Static resource %s is missing or invalid.", filename)
            all_valid = False
    return all_valid


def get_stylesheet_path() -> Optional[Path]:
    """Return the CDA stylesheet path, downloading resources as needed."""
    if not verify_static_files():
        update_static_files(force=True)
        if not verify_static_files():
            LOGGER.error("Unable to obtain valid CDA static resources.")
            return None
    return get_static_dir() / "CDA.xsl"
