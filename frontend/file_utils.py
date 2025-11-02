# Purpose: File and URI helpers supporting attachment interactions in Streamlit.
# Author: Codex + Lauren
# Date: 2025-10-13
# Tests: Manual Streamlit verification of attachment links and previews.
# AI-assisted: Portions of this module were updated with AI assistance.
"""Helpers for opening files and building shareable URIs."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Union
import webbrowser

from health_records_collection.security import encryption
from health_records_collection.frontend import static_resources, xml_utils


logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent

PathLike = Union[str, os.PathLike[str]]


# Extract decryption into its own helper
def _decrypt_if_needed(path: Path) -> Path:
    """Decrypt encrypted files, return original path if not encrypted."""
    if path.suffix == ".enc":
        try:
            return encryption.decrypt_to_temp(path)
        except (FileNotFoundError, OSError) as exc:
            logger.error("Failed to decrypt %s: %s", path, exc)
            raise
    return path


# Extract UNC path handling
def _is_unc_path(path: Path) -> bool:
    """Check if path is a UNC network path."""
    return str(path).startswith("\\")


def _unc_to_uri(path: Path) -> str:
    """Convert UNC path to file:// URI."""
    unc_body = str(path)[2:].replace("\\", "/")
    return f"file://{unc_body}"


def build_file_uri(file_path: PathLike, *, validate: bool = True) -> Optional[str]:
    """Return a file:// URI for the provided path, handling UNC shares."""
    path = Path(file_path)

    # Make absolute
    if not path.is_absolute():
        path = REPO_ROOT / path

    # Decrypt if needed
    try:
        path = _decrypt_if_needed(path)
    except (FileNotFoundError, OSError):
        return None

    # Resolve path
    try:
        path = path.resolve(strict=False)
    except OSError:
        path = path.absolute()

    # Validate exists (unless UNC or validation disabled)
    if validate and not path.exists() and not _is_unc_path(path):
        return None

    # Convert to URI
    if _is_unc_path(path):
        return _unc_to_uri(path)

    try:
        return path.as_uri()
    except ValueError:
        # Fallback for edge cases
        normalized = str(path).replace("\\", "/")
        return f"file:///{normalized.lstrip('/')}"


def open_file(file_path: str) -> None:
    """
    Open a file using the appropriate handler based on type.

    For XML files, transforms to HTML first so the user's default browser can
    render CDA documents with the bundled stylesheet.
    """
    try:
        logger.debug("Opening file: %s", file_path)

        abs_path = str(Path(file_path).absolute())
        logger.debug("Absolute path: %s", abs_path)

        if file_path.lower().endswith(".xml"):
            xsl_path = static_resources.get_stylesheet_path()
            if not xsl_path or not xsl_path.exists():
                logger.error("CDA stylesheet not found, attempting refresh")
                static_resources.update_static_files(force=True)
                xsl_path = static_resources.get_stylesheet_path()
                if not xsl_path:
                    logger.error("Could not obtain valid stylesheet")
                    return

            logger.debug("Transforming XML using stylesheet: %s", xsl_path)
            html_path = xml_utils.transform_cda_to_html(abs_path)
            if html_path:
                logger.debug("Using transformed HTML: %s", html_path)
                path_to_open = html_path
            else:
                logger.error("Failed to transform XML, falling back to raw file")
                path_to_open = abs_path
        else:
            path_to_open = abs_path

        uri = build_file_uri(path_to_open, validate=False)
        if uri is None:
            logger.error("Unable to construct file URI for %s", path_to_open)
            return

        webbrowser.open(uri)
    except (FileNotFoundError, OSError, ValueError) as exc:
        logger.error("Error opening file %s: %s", file_path, exc)
