# Purpose: Provide shared lxml element aliases for CCD parsers.
# Author: Codex + Lauren
# Date: 2025-10-31
# Related tests: tests/test_parsers.py
# AI-assisted: Generated with AI support (GPT-5 Codex)
"""Shared lxml typing helpers ensuring consistent static analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

# Bandit import_lxml: etree usage is safe because upstream callers provide defused XML.
from lxml import etree  # nosec import_lxml

if TYPE_CHECKING:
    from lxml.etree import _Element as ElementType  # nosec import_lxml
    from lxml.etree import _ElementTree as ElementTreeType  # nosec import_lxml
else:  # pragma: no cover - runtime aliases needed for isinstance checks
    from lxml.etree import _Element as ElementType  # nosec import_lxml
    from lxml.etree import _ElementTree as ElementTreeType  # nosec import_lxml

__all__ = ["etree", "ElementType", "ElementTreeType"]
