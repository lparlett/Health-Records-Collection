"""Health Records Collection package."""

from __future__ import annotations

import importlib
from types import ModuleType


def _import_submodule(module: str) -> ModuleType:
    """Import a submodule, even when loaded outside a package context."""
    package = __spec__.name if __spec__ is not None else "health_records_collection"
    if package == "__init__":
        # Fallback when module is executed without package context.
        package = "health_records_collection"
    return importlib.import_module(f"{package}.{module}")


db = _import_submodule("db")
frontend = _import_submodule("frontend")
parsers = _import_submodule("parsers")
security = _import_submodule("security")
services = _import_submodule("services")
settings = _import_submodule("settings")
ingest_module = _import_submodule("ingest")
ingest_archive = getattr(ingest_module, "ingest_archive")


__all__ = [
    "db",
    "frontend",
    "parsers",
    "security",
    "services",
    "settings",
    "ingest_archive",
]
