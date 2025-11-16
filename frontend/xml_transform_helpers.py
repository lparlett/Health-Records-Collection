"""XML transformation utilities for secure CDA document processing.

This module provides helper functions for handling encrypted files, loading resources,
and validating XML content before XSLT transformation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import logging

from lxml import etree as unsafe_etree  # nosec import_lxml
from defusedxml.lxml import fromstring
from defusedxml.common import (
    DefusedXmlException as XMLSyntaxError,
    DTDForbidden as DocumentInvalid,
)


from health_records_collection.frontend import static_resources
from health_records_collection.frontend.xml_constants import RESTRICTED_PARSER
from health_records_collection.security import encryption

ElementType = unsafe_etree._Element  # type: ignore[attr-defined]  # nosec import_lxml  # pylint: disable=protected-access

logger = logging.getLogger(__name__)


def handle_encrypted_file(xml_path: str) -> Optional[str]:
    """Decrypt encrypted XML file and return path to decrypted temporary file.

    Args:
        xml_path: Path to potentially encrypted XML file.

    Returns:
        Path to file (encrypted file decrypted to temp, or original path).
        Returns None if decryption fails.
    """
    xml_path_obj = Path(xml_path)
    if xml_path_obj.suffix != ".enc":
        return xml_path

    try:
        decrypted_path = encryption.decrypt_to_temp(xml_path_obj)
        return str(decrypted_path)
    except (encryption.DecryptionError, FileNotFoundError) as exc:
        logger.error("Failed to decrypt %s: %s", xml_path, exc)
        return None


def load_transformation_resources() -> Optional[dict[str, Path]]:
    """Load and validate all required transformation resources.

    Returns:
        Dictionary with paths to stylesheet and CSS files, or None if validation fails.
    """
    xsl_path = static_resources.get_stylesheet_path()
    if not xsl_path:
        logger.error("Could not get valid CDA stylesheet")
        return None

    static_dir = Path(__file__).parent / "static"
    color_css_path = static_dir / "colors.css"
    if not color_css_path.exists():
        logger.error("Color CSS file not found: %s", color_css_path)
        return None

    css_path = static_dir / "cda_custom.css"

    logger.debug("Using stylesheet: %s", xsl_path)
    logger.debug("Using CSS: %s", css_path)
    logger.debug("Using color CSS: %s", color_css_path)

    return {
        "xsl": xsl_path,
        "css": css_path,
        "color_css": color_css_path,
    }


def load_and_validate_xml(xml_path: str) -> Optional[str]:
    """Load and validate XML file, adding declaration if needed.

    Args:
        xml_path: Path to XML file to load.

    Returns:
        Validated XML content as string, or None if validation fails.
    """
    try:
        xml_content = Path(xml_path).read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Failed to read XML file %s: %s", xml_path, exc)
        return None

    if not xml_content.strip():
        logger.error("XML file is empty: %s", xml_path)
        return None

    if "<?xml" not in xml_content:
        logger.debug("Adding XML declaration to %s", xml_path)
        xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_content

    logger.debug("XML content size: %s bytes", len(xml_content))
    return xml_content


def parse_xml_securely(xml_content: str) -> Optional[ElementType]:
    """Parse XML content using defusedxml for security.

    Args:
        xml_content: XML content as string.

    Returns:
        Parsed XML document (_Element), or None if parsing fails.
    """
    try:
        result = fromstring(xml_content.encode("utf-8"))
        if not isinstance(result, ElementType):
            logger.error("XML parsing returned unexpected type: %s", type(result))
            return None
        return result
    except (XMLSyntaxError, DocumentInvalid) as exc:
        logger.error("XML parsing failed: %s", exc)
        return None


def build_xslt_transformer(xsl_path: str) -> Optional[unsafe_etree.XSLT]:
    """Build XSLT transformer from stylesheet path.

    Args:
        xsl_path: Path to XSLT stylesheet.

    Returns:
        XSLT transformer object, or None if creation fails.
    """
    try:
        logger.debug("Creating XSLT transformer")

        parser = RESTRICTED_PARSER
        xsl_tree = unsafe_etree.parse(  # nosec xml_bad_etree
            str(Path(xsl_path)), parser=parser
        )

        root = xsl_tree.getroot()
        if not isinstance(root, ElementType):
            logger.error("XSL parsing returned unexpected type: %s", type(root))
            return None

        logger.debug("XSL document root tag: %s", getattr(root, "tag", "unknown"))

        return unsafe_etree.XSLT(xsl_tree)
    except unsafe_etree.XSLTError as exc:
        logger.error("XSLT transformer creation failed: %s", exc)
        return None


def perform_xslt_transformation(
    transformer: unsafe_etree.XSLT, xml_doc: ElementType
) -> Optional[str]:
    """Perform XSLT transformation on XML document.

    Args:
        transformer: XSLT transformer object.
        xml_doc: Parsed XML document (_Element).

    Returns:
        Transformed HTML string, or None if transformation fails.
    """
    if not isinstance(xml_doc, ElementType):
        logger.error("Invalid XML document type: %s (expected _Element)", type(xml_doc))
        return None

    try:
        logger.debug("Performing XSLT transformation")

        # Convert XML to string and back through restricted parser for safety
        xml_str = unsafe_etree.tostring(xml_doc)
        safe_doc = unsafe_etree.fromstring(
            xml_str, parser=RESTRICTED_PARSER
        )  # nosec xml_bad_etree

        if not isinstance(safe_doc, ElementType):
            logger.error(
                "Safe document parsing returned unexpected type: %s", type(safe_doc)
            )
            return None

        html = transformer(safe_doc)
        result_str = str(html)

        logger.debug("Transformation result size: %s bytes", len(result_str))
        logger.debug("Result preview: %s...", result_str[:200])

        if not result_str.strip():
            logger.error("Transformation produced empty result")
            return None

        return result_str
    except unsafe_etree.XSLTError as exc:
        logger.error("XSLT transformation failed: %s", exc)
        return None
    except RuntimeError as exc:
        logger.error("Unexpected error during transformation: %s", exc)
        return None


def load_css_files(resources: dict[str, Path]) -> Optional[dict[str, str]]:
    """Load CSS file content from disk.

    Args:
        resources: Dictionary with CSS file paths.

    Returns:
        Dictionary with CSS content, or None if loading fails.
    """
    try:
        with open(resources["color_css"], "r", encoding="utf-8") as f:
            color_css = f.read()

        with open(resources["css"], "r", encoding="utf-8") as f:
            css = f.read()

        logger.debug("Loaded custom and color CSS successfully")
        return {"color_css": color_css, "css": css}
    except OSError as exc:
        logger.error("Failed to load CSS files: %s", exc)
        return None
