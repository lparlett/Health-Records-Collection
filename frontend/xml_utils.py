"""XML transformation utilities for CDA documents with secure XML processing.

This module implements a secure XML processing pipeline using defusedxml for initial
parsing of untrusted content and a restricted lxml configuration for XSLT processing.

Security measures:
1. All untrusted XML is first parsed using defusedxml to prevent common XML attacks
2. XSLT processing uses a restricted lxml parser that:
   - Disables entity resolution
   - Disables network access
   - Disables DTD loading
   - Strips comments and processing instructions
3. Stylesheet validation ensures namespace compliance
4. All content is validated before processing
"""

from pathlib import Path
import logging
from typing import Optional, TypeVar

from defusedxml.lxml import fromstring
from defusedxml.common import (
    DefusedXmlException as XMLSyntaxError,
    DTDForbidden as DocumentInvalid,
)

from health_records_collection.frontend import html_generator
from health_records_collection.frontend import xml_transform_helpers
from health_records_collection.frontend.xml_constants import XSLT_NS

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class StylesheetValidationError(Exception):
    """Raised when a stylesheet fails validation."""


class TransformationError(Exception):
    """Raised when CDA-to-HTML transformation fails."""


T = TypeVar("T")


def _ensure_value(value: Optional[T], message: str) -> T:
    """Return the provided value or raise a TransformationError."""
    if value is None:
        raise TransformationError(message)
    return value


def validate_stylesheet(file_path: Path) -> bool:
    """
    Validate that a stylesheet file exists and contains valid XSLT.

    Args:
        file_path: Path to the stylesheet file

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        content = _read_stylesheet(file_path)
        tree = fromstring(content.encode("utf-8"))
        _validate_stylesheet_tree(tree, file_path)
        return True

    except FileNotFoundError:
        print(f"Stylesheet file not found: {file_path}")
        return False
    except StylesheetValidationError as exc:
        print(str(exc))
        return False
    except (XMLSyntaxError, DocumentInvalid) as exc:  # type: ignore
        print(f"XML parsing error in stylesheet {file_path}: {exc}")
        return False
    except ValueError as exc:
        print(f"Invalid content in stylesheet {file_path}: {exc}")
        return False


def _read_stylesheet(file_path: Path) -> str:
    """Return stylesheet content or raise validation error."""
    if not file_path.exists():
        raise FileNotFoundError
    content = file_path.read_text(encoding="utf-8")
    if not content.strip():
        raise StylesheetValidationError(f"Stylesheet file is empty: {file_path}")
    if "<?xml" not in content:
        raise StylesheetValidationError(
            f"Stylesheet lacks XML declaration: {file_path}"
        )
    return content


def _validate_stylesheet_tree(tree, file_path: Path) -> None:
    """Validate parsed stylesheet tree."""
    namespace = getattr(tree, "nsmap", {}).get(None)
    if namespace != XSLT_NS:
        raise StylesheetValidationError(
            f"Not a valid XSLT file (wrong namespace): {file_path}"
        )
    tree_tag = getattr(tree, "tag", "")
    if not (tree_tag.endswith("stylesheet") or tree_tag.endswith("transform")):
        raise StylesheetValidationError(
            f"Not a valid XSLT file (root is {tree_tag}): {file_path}"
        )


def transform_cda_to_html(xml_path: str) -> Optional[str]:
    """Transform a CDA XML document to HTML using HL7 CDA.xsl stylesheet.

    Handles encrypted files, validates XML, performs secure XSLT transformation,
    and embeds CSS for styling.

    Args:
        xml_path: Path to the XML file to transform.

    Returns:
        Path to temporary HTML file or None if transformation fails.
    """
    try:
        # Step 1: Handle encryption
        xml_path = _ensure_value(
            xml_transform_helpers.handle_encrypted_file(xml_path),
            "Unable to prepare encrypted XML file",
        )

        logger.debug("Transforming XML file: %s", xml_path)

        # Step 2: Load resources (stylesheets and CSS)
        resources = _ensure_value(
            xml_transform_helpers.load_transformation_resources(),
            "Failed to load transformation resources",
        )

        # Step 3: Load and validate XML
        xml_content = _ensure_value(
            xml_transform_helpers.load_and_validate_xml(xml_path),
            "XML validation failed",
        )

        # Step 4: Parse XML securely
        xml_doc = _ensure_value(
            xml_transform_helpers.parse_xml_securely(xml_content),
            "Secure XML parsing failed",
        )

        # Step 5: Build transformer
        transformer = _ensure_value(
            xml_transform_helpers.build_xslt_transformer(str(resources["xsl"])),
            "Unable to build XSLT transformer",
        )

        # Step 6: Perform transformation
        html_body = _ensure_value(
            xml_transform_helpers.perform_xslt_transformation(transformer, xml_doc),
            "XSLT transformation returned no content",
        )

        # Step 7: Load CSS files
        css_content = _ensure_value(
            xml_transform_helpers.load_css_files(resources),
            "CSS resources missing",
        )

        assets = html_generator.HtmlAssets(
            color_css=css_content["color_css"],
            css=css_content["css"],
            xml_path=xml_path,
            xsl_path=str(resources["xsl"]),
            css_path=str(resources["css"]),
        )

        # Step 8: Generate final HTML file
        return html_generator.generate_html_file(html_body=html_body, assets=assets)

    except TransformationError as exc:
        logger.error("CDA transformation failed: %s", exc)
        return None
