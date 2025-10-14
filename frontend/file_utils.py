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

from . import static_resources, xml_utils

REPO_ROOT = Path(__file__).resolve().parent.parent

PathLike = Union[str, os.PathLike[str]]


def build_file_uri(file_path: PathLike, *, validate: bool = True) -> Optional[str]:
    """Return a file:// URI for the provided path, handling UNC shares."""
    path = Path(file_path)
    if not path.is_absolute():
        path = REPO_ROOT / path
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path.absolute()

    resolved_str = str(resolved)
    is_unc_path = resolved_str.startswith("\\\\")

    if validate and not resolved.exists() and not is_unc_path:
        return None

    if is_unc_path:
        unc_body = resolved_str[2:].replace("\\", "/")
        return f"file://{unc_body}"

    try:
        return resolved.as_uri()
    except ValueError:
        normalized = resolved_str.replace("\\", "/")
        return f"file:///{normalized.lstrip('/')}"


def open_file(file_path: str) -> None:
    """
    Open a file using the appropriate handler based on type.

    For XML files, transforms to HTML first so the user's default browser can
    render CDA documents with the bundled stylesheet.
    """
    try:
        logger = logging.getLogger(__name__)
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
    except Exception as exc:
        print(f"Error opening file {file_path}: {exc}")
