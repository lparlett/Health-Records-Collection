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
from typing import Optional

from defusedxml.lxml import fromstring
from defusedxml.common import (
    DefusedXmlException as XMLSyntaxError,
    DTDForbidden as DocumentInvalid,
)

from health_records_collection.frontend import html_generator
from health_records_collection.frontend import xml_transform_helpers
from health_records_collection.frontend.xml_constants import (
    XSLT_NS,
)

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def validate_stylesheet(file_path: Path) -> bool:
    """
    Validate that a stylesheet file exists and contains valid XSLT.

    Args:
        file_path: Path to the stylesheet file

    Returns:
        bool: True if valid, False otherwise
    """
    try:
        if not file_path.exists():
            print(f"Stylesheet file not found: {file_path}")
            return False

        content = file_path.read_text(encoding="utf-8")
        if not content.strip():
            print(f"Stylesheet file is empty: {file_path}")
            return False

        if "<?xml" not in content:
            print(f"Stylesheet lacks XML declaration: {file_path}")
            return False

        # Try parsing as XML using defusedxml
        tree = fromstring(content.encode("utf-8"))

        # Get tree attributes safely
        if getattr(tree, "nsmap", {}).get(None) != XSLT_NS:
            print(f"Not a valid XSLT file (wrong namespace): {file_path}")
            return False

        tree_tag = getattr(tree, "tag", "")
        if not (tree_tag.endswith("stylesheet") or tree_tag.endswith("transform")):
            print(f"Not a valid XSLT file (root is {tree_tag}): {file_path}")
            return False

        return True

    except FileNotFoundError:
        print(f"Stylesheet file not found: {file_path}")
        return False
    except (XMLSyntaxError, DocumentInvalid) as e:  # type: ignore
        print(f"XML parsing error in stylesheet {file_path}: {str(e)}")
        return False
    except ValueError as e:
        print(f"Invalid content in stylesheet {file_path}: {str(e)}")
        return False


def transform_cda_to_html(xml_path: str) -> Optional[str]:
    """Transform a CDA XML document to HTML using HL7 CDA.xsl stylesheet.

    Handles encrypted files, validates XML, performs secure XSLT transformation,
    and embeds CSS for styling.

    Args:
        xml_path: Path to the XML file to transform.

    Returns:
        Path to temporary HTML file or None if transformation fails.
    """
    # Step 1: Handle encryption
    handled_xml_path = xml_transform_helpers.handle_encrypted_file(xml_path)
    if handled_xml_path is None:
        return None
    xml_path = handled_xml_path

    logger.debug("Transforming XML file: %s", xml_path)

    # Step 2: Load resources (stylesheets and CSS)
    resources = xml_transform_helpers.load_transformation_resources()
    if resources is None:
        return None

    # Step 3: Load and validate XML
    xml_content = xml_transform_helpers.load_and_validate_xml(xml_path)
    if xml_content is None:
        return None

    # Step 4: Parse XML securely
    xml_doc = xml_transform_helpers.parse_xml_securely(xml_content)
    if xml_doc is None:
        return None

    # Step 5: Build transformer
    transformer = xml_transform_helpers.build_xslt_transformer(str(resources["xsl"]))
    if transformer is None:
        return None

    # Step 6: Perform transformation
    html_body = xml_transform_helpers.perform_xslt_transformation(transformer, xml_doc)
    if html_body is None:
        return None

    # Step 7: Load CSS files
    css_content = xml_transform_helpers.load_css_files(resources)
    if css_content is None:
        return None

    # Step 8: Generate final HTML file
    html_path = html_generator.generate_html_file(
        html_body=html_body,
        color_css_content=css_content["color_css"],
        css_content=css_content["css"],
        xml_path=xml_path,
        xsl_path=str(resources["xsl"]),
        css_path=str(resources["css"]),
    )
    return html_path
