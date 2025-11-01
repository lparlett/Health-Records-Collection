# Purpose: Manage application configuration with user-overridable settings.
# Author: Codex + Lauren
# Date: 2025-10-29
# Tests: tests/test_settings.py
# AI-assisted: Portions of this module were generated with AI assistance.
"""Utility functions for loading and persisting application settings."""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Union

import yaml  # type: ignore

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS: Dict[str, Dict[str, Any]] = {
    "paths": {
        "raw_dir": "data/raw",
        "parsed_dir": "data/parsed",
        "db_path": "db/health_records.db",
    },
    "ingestion": {
        "delete_uploaded_archives": True,
        "delete_unencrypted_extracted_files": True,
    },
}

BASE_DIR = Path(__file__).resolve().parent
USER_SETTINGS_DIR = BASE_DIR / "user"
SETTINGS_FILE: Path = USER_SETTINGS_DIR / "settings.yaml"


def _merge_dicts(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge overrides into the base dictionary."""
    merged = deepcopy(base)
    for key, value in overrides.items():
        if value is None:
            continue
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _coerce_ingestion_settings(values: Dict[str, Any]) -> Dict[str, bool]:
    """Return ingestion settings with boolean coercion for robustness."""
    delete_archives = values.get("delete_uploaded_archives", True)
    delete_non_xml = values.get("delete_unencrypted_extracted_files", True)
    return {
        "delete_uploaded_archives": bool(delete_archives),
        "delete_unencrypted_extracted_files": bool(delete_non_xml),
    }


def load_settings() -> Dict[str, Dict[str, Any]]:
    """Return settings merged with user overrides."""
    settings_bundle = deepcopy(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            user_settings = (
                yaml.safe_load(SETTINGS_FILE.read_text(encoding="utf-8")) or {}
            )
            if isinstance(user_settings, dict):
                settings_bundle = _merge_dicts(settings_bundle, user_settings)
            else:
                logger.warning(
                    "User settings file %s did not contain a dictionary; ignoring.",
                    SETTINGS_FILE,
                )
        except yaml.YAMLError as exc:
            logger.warning("Failed to parse %s: %s", SETTINGS_FILE, exc)
    paths = {
        key: Path(value).expanduser()
        for key, value in settings_bundle.get("paths", {}).items()
    }
    ingestion = _coerce_ingestion_settings(settings_bundle.get("ingestion", {}))
    return {"paths": paths, "ingestion": ingestion}


def ensure_runtime_paths(settings: Dict[str, Dict[str, Any]]) -> None:
    """Guarantee required directories exist for configured paths."""
    paths = settings.get("paths", {})
    raw_dir = paths.get("raw_dir")
    parsed_dir = paths.get("parsed_dir")
    db_path = paths.get("db_path")

    for directory in (raw_dir, parsed_dir):
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)


def load_paths() -> Dict[str, Path]:
    """Convenience wrapper returning prepared path settings."""
    settings_bundle = load_settings()
    ensure_runtime_paths(settings_bundle)
    return settings_bundle["paths"]


def _serialise_settings(
    settings_data: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Union[str, Any]]]:
    """Convert paths to strings while preserving other scalar values."""
    serialised: Dict[str, Dict[str, Any]] = {}
    for section, values in settings_data.items():
        if section == "paths":
            serialised[section] = {
                key: str(Path(value).expanduser())
                for key, value in values.items()
                if value is not None
            }
        else:
            serialised[section] = values.copy()
    return serialised


def save_settings(updates: Dict[str, Dict[str, Any]]) -> None:
    """Persist user overrides to disk."""
    current = load_settings()
    serialisable_current = _serialise_settings(current)
    serialisable_updates = _serialise_settings(updates)
    merged = _merge_dicts(serialisable_current, serialisable_updates)

    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(yaml.safe_dump(merged, sort_keys=True), encoding="utf-8")
    logger.debug("User settings saved to %s", SETTINGS_FILE)
