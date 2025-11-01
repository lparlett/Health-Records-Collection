# Purpose: Provide shared lxml element aliases for CCD parsers.
# Author: Codex + Lauren
# Date: 2025-10-31
# Related tests: tests/test_parsers.py
# AI-assisted: Generated with AI support (GPT-5 Codex)
"""Shared lxml typing helpers ensuring consistent static analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

# Bandit B410: etree usage is safe because upstream callers provide defused XML.
from lxml import etree  # nosec B410

if TYPE_CHECKING:
    from lxml.etree import _Element as ElementType  # nosec B410
    from lxml.etree import _ElementTree as ElementTreeType  # nosec B410
else:  # pragma: no cover - runtime aliases needed for isinstance checks
    ElementType = etree._Element  # type: ignore[attr-defined]  # pylint: disable=protected-access
    ElementTreeType = etree._ElementTree  # type: ignore[attr-defined]  # pylint: disable=protected-access

__all__ = ["etree", "ElementType", "ElementTreeType"]
