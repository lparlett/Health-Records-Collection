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
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS: Dict[str, Dict[str, str]] = {
    "paths": {
        "raw_dir": "data/raw",
        "parsed_dir": "data/parsed",
        "db_path": "db/health_records.db",
    }
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


def load_settings() -> Dict[str, Dict[str, Path]]:
    """Return settings merged with user overrides (paths as Path objects)."""
    settings = deepcopy(DEFAULT_SETTINGS)
    if SETTINGS_FILE.exists():
        try:
            user_settings = yaml.safe_load(SETTINGS_FILE.read_text(encoding="utf-8")) or {}
            if isinstance(user_settings, dict):
                settings = _merge_dicts(settings, user_settings)
            else:
                logger.warning(
                    "User settings file %s did not contain a dictionary; ignoring.",
                    SETTINGS_FILE,
                )
        except yaml.YAMLError as exc:
            logger.warning("Failed to parse %s: %s", SETTINGS_FILE, exc)
    paths = {
        key: Path(value).expanduser()
        for key, value in settings.get("paths", {}).items()
    }
    return {"paths": paths}


def ensure_runtime_paths(settings: Dict[str, Dict[str, Path]]) -> None:
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
    settings = load_settings()
    ensure_runtime_paths(settings)
    return settings["paths"]


def save_settings(updates: Dict[str, Dict[str, Path | str]]) -> None:
    """Persist user overrides to disk."""
    current = load_settings()
    serialisable_current = {
        "paths": {key: str(value) for key, value in current["paths"].items()}
    }
    serialisable_updates = {
        "paths": {
            key: str(Path(value).expanduser())
            for key, value in updates.get("paths", {}).items()
            if value is not None
        }
    }
    merged = _merge_dicts(serialisable_current, serialisable_updates)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(
        yaml.safe_dump(merged, sort_keys=True), encoding="utf-8"
    )
    logger.debug("User settings saved to %s", SETTINGS_FILE)
