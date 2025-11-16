"""Settings management components for Streamlit UI.

This module handles the application settings form, validation, and persistence,
reducing complexity in the main views.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

import streamlit as st

from health_records_collection import settings as app_settings


def render_settings_form(
    rerun_callback: Callable[[], None],
) -> None:
    """Render the application settings form with validation and persistence.

    Args:
        rerun_callback: Callback function to trigger app rerun after save.
    """
    st.header("Application Settings")
    st.subheader("Storage Locations")

    current = app_settings.load_settings()
    paths = current["paths"]
    ingestion_settings = current["ingestion"]

    with st.form("app-settings-form"):
        raw_dir_input = st.text_input(
            "Raw data directory",
            str(paths["raw_dir"]),
            help="Incoming ZIP archives are stored here before parsing.",
        )
        parsed_dir_input = st.text_input(
            "Parsed data directory",
            str(paths["parsed_dir"]),
            help="XML documents extracted from archives are maintained here.",
        )
        db_path_input = st.text_input(
            "Database file",
            str(paths["db_path"]),
            help="Path to the SQLite database file used by the application.",
        )

        st.subheader("Ingestion Cleanup")
        delete_archives = st.checkbox(
            "Delete uploaded ZIP archives after ingestion",
            value=ingestion_settings["delete_uploaded_archives"],
            help=(
                "Remove original CCD archives from disk once ingestion completes "
                "successfully. Disable to retain the source ZIP files."
            ),
        )
        delete_non_xml = st.checkbox(
            "Delete extracted non-XML files after ingestion",
            value=ingestion_settings["delete_unencrypted_extracted_files"],
            help=(
                "Remove unencrypted artifacts (e.g., PDFs, HTML) generated during "
                "parsing while keeping XML and encrypted (.enc) files."
            ),
        )
        submitted = st.form_submit_button("Save settings")

    if not submitted:
        st.caption(
            "User-specific overrides are stored at " f"{app_settings.SETTINGS_FILE}."
        )
        return

    settings: dict[str, str | bool] = {
        "raw_dir": str(raw_dir_input),
        "parsed_dir": str(parsed_dir_input),
        "db_path": str(db_path_input),
        "delete_uploaded_archives": bool(delete_archives),
        "delete_unencrypted_extracted_files": bool(delete_non_xml),
    }
    _save_validated_settings(
        settings,
        rerun_callback,
    )


def _save_validated_settings(
    settings: dict[str, str | bool],
    rerun_callback: Callable[[], None],
) -> None:
    """Validate and persist settings configuration.

    Args:
        settings: Dictionary containing settings inputs.
        rerun_callback: Callback to trigger app rerun on success.
    """
    candidate_paths = {
        "raw_dir": settings["raw_dir"],
        "parsed_dir": settings["parsed_dir"],
        "db_path": settings["db_path"],
    }
    resolved_paths: dict[str, Path] = {}
    errors: list[str] = []

    for key, value in candidate_paths.items():
        if isinstance(value, str):
            error = _validate_path(key, value, resolved_paths)
        else:
            error = f"Invalid type for {key.replace('_', ' ')}: expected a string."
        if error:
            errors.append(error)

    if errors:
        for error in errors:
            st.error(error)
        return

    try:
        app_settings.save_settings(
            {
                "paths": {key: str(value) for key, value in resolved_paths.items()},
                "ingestion": {
                    "delete_uploaded_archives": settings["delete_uploaded_archives"],
                    "delete_unencrypted_extracted_files": settings[
                        "delete_unencrypted_extracted_files"
                    ],
                },
            }
        )
        app_settings.ensure_runtime_paths({"paths": resolved_paths})
    except RuntimeError as exc:  # pragma: no cover - defensive
        st.error(f"Failed to persist settings: {exc}")
        return

    st.success("Settings updated. Reloading app...")
    rerun_callback()


def _validate_path(
    key: str, value: str, resolved_paths: dict[str, Path]
) -> Optional[str]:
    """Validate a single path setting.

    Args:
        key: Setting key name (e.g., 'raw_dir').
        value: Path string to validate.
        resolved_paths: Dictionary to store resolved path if valid.

    Returns:
        Error message if validation fails, None if valid.
    """
    trimmed = value.strip()
    if not trimmed:
        return f"{key.replace('_', ' ').title()} cannot be empty."

    try:
        resolved = Path(trimmed).expanduser()
    except (ValueError, OSError) as exc:  # pragma: no cover - defensive
        return f"Invalid path for {key.replace('_', ' ')}: {exc}"

    if key != "db_path" and resolved.suffix:
        return f"{key.replace('_', ' ').title()} should be a directory, not a file."

    resolved_paths[key] = resolved
    return None
