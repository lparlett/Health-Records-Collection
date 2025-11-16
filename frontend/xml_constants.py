"""XML security constants and configuration for CDA document processing.

This module provides shared security configurations for XML parsing and XSLT
processing across multiple frontend modules.
"""

from typing import TYPE_CHECKING

from lxml import etree as unsafe_etree  # nosec import_lxml

if TYPE_CHECKING:
    from lxml.etree import XMLParser as _XMLParser  # nosec import_lxml
else:  # pragma: no cover - runtime access only
    _XMLParser = unsafe_etree.XMLParser  # type: ignore[attr-defined]

# Namespace for XSLT documents
XSLT_NS = "http://www.w3.org/1999/XSL/Transform"

# Configure restricted parser for XSLT processing with security controls
# Note: We use lxml for XSLT as there's no pure-Python alternative,
# but we restrict it heavily to prevent XML attacks
RESTRICTED_PARSER = _XMLParser(
    resolve_entities=False,  # Prevent XXE attacks
    no_network=True,  # Prevent network-based attacks
    remove_blank_text=True,  # Normalize whitespace
    remove_comments=True,  # Remove potentially dangerous content
    remove_pis=True,  # Remove processing instructions
    load_dtd=False,  # Prevent DTD-based attacks
    collect_ids=False,  # Prevent memory attacks
)
