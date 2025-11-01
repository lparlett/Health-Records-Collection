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

import os
from pathlib import Path
import tempfile
import logging
import datetime
from typing import Optional, Any
from defusedxml.lxml import parse, fromstring
# We need lxml for XSLT processing which defusedxml doesn't support.
# Security is handled through RESTRICTED_PARSER settings.
from lxml import etree as unsafe_etree  # nosec B410

from health_records_collection.frontend import static_resources
from health_records_collection.security import encryption

# Configure restricted parser for XSLT processing with security controls
# Note: We use lxml for XSLT as there's no pure-Python alternative,
# but we restrict it heavily to prevent XML attacks
RESTRICTED_PARSER = unsafe_etree.XMLParser(
    resolve_entities=False,  # Prevent XXE attacks
    no_network=True,        # Prevent network-based attacks
    remove_blank_text=True, # Normalize whitespace
    remove_comments=True,   # Remove potentially dangerous content
    remove_pis=True,       # Remove processing instructions
    load_dtd=False,        # Prevent DTD-based attacks
    collect_ids=False      # Prevent memory attacks
)

# Namespace for XSLT documents
XSLT_NS = "http://www.w3.org/1999/XSL/Transform"

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
        if getattr(tree, 'nsmap', {}).get(None) != XSLT_NS:
            print(f"Not a valid XSLT file (wrong namespace): {file_path}")
            return False

        tree_tag = getattr(tree, 'tag', '')
        if not (
            tree_tag.endswith('stylesheet') or 
            tree_tag.endswith('transform')
        ):
            print(f"Not a valid XSLT file (root is {tree_tag}): {file_path}")
            return False

        return True

    except Exception as e:
        print(f"Error validating stylesheet {file_path}: {str(e)}")
        return False


def transform_cda_to_html(xml_path: str) -> Optional[str]:
    """
    Transform a CDA XML document to HTML using the HL7 CDA.xsl stylesheet
    with custom styling.

    Args:
        xml_path: Path to the XML file to transform

    Returns:
        Path to temporary HTML file or None if transformation fails
    """
    xml_path_obj = Path(xml_path)
    if xml_path_obj.suffix == ".enc":
        try:
            decrypted_path = encryption.decrypt_to_temp(xml_path_obj)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to decrypt %s: %s", xml_path, exc)
            return None
        xml_path_obj = decrypted_path
        xml_path = str(xml_path_obj)
    else:
        xml_path_obj = xml_path_obj
    xml_content = ""  # Initialize for error handling

    try:
        # Get stylesheet path using resource manager
        xsl_path = static_resources.get_stylesheet_path()
        if not xsl_path:
            print("Could not get valid CDA stylesheet")
            return None

        # Get paths for other resources
        static_dir = Path(__file__).parent / "static"
        color_css_path = static_dir / "colors.css"
        if not color_css_path.exists():
            logger.error(f"Color CSS file not found: {color_css_path}")
            return None
        css_path = static_dir / "cda_custom.css"

        # Log transformation details
        logger.debug(f"Transforming XML file: {xml_path}")
        logger.debug(f"Using stylesheet: {xsl_path}")
        logger.debug(f"Using CSS: {css_path}")
        logger.debug(f"Using color CSS: {color_css_path}")

        # Read and validate input XML
        xml_content = Path(xml_path).read_text(encoding="utf-8")
        if not xml_content.strip():
            logger.error(f"XML file is empty: {xml_path}")
            return None

        if "<?xml" not in xml_content:
            logger.debug("Adding XML declaration")
            xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_content

        # Log XML content size for debugging
        logger.debug(f"XML content size: {len(xml_content)} bytes")

        # Parse XML using defusedxml for security
        xml_doc = fromstring(xml_content.encode("utf-8"))
        
        # For XSLT processing we need lxml but with strict security settings
        xsl_text = Path(xsl_path).read_text(encoding="utf-8")
        
        # Create safe transformation pipeline
        try:
            logger.debug("Creating XSLT transformer")
            
            # Parse stylesheet with restricted settings
            # Safe since we use RESTRICTED_PARSER with all security options enabled
            xsl_doc = unsafe_etree.fromstring(  # nosec B320
                xsl_text.encode("utf-8"), 
                parser=RESTRICTED_PARSER
            )
            transform = unsafe_etree.XSLT(xsl_doc)
            
            # Log XSL document details safely
            tag = getattr(xsl_doc, 'tag', 'unknown')
            logger.debug(f"XSL document root tag: {tag}")
            logger.debug(f"XSL document size: {len(xsl_text)} bytes")

            # Convert XML to string and back through restricted parser
            # Safe since we use RESTRICTED_PARSER with all security options enabled
            xml_str = unsafe_etree.tostring(xml_doc)
            safe_doc = unsafe_etree.fromstring(xml_str, parser=RESTRICTED_PARSER)  # nosec B320
            
            # Perform transformation
            logger.debug("Performing XSLT transformation")
            html = transform(safe_doc)

            # Log transformation result details
            result_str = str(html)
            logger.debug(f"Transformation result size: {len(result_str)} bytes")
            logger.debug(f"Result preview: {result_str[:200]}...")

            if not result_str.strip():
                logger.error("Transformation produced empty result")
                return None

        except unsafe_etree.XSLTError as e:
            logger.error(f"XSLT transformation failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during transformation: {str(e)}")
            return None

        # Log success
        logger.debug("XSLT transformation completed successfully")

        # Get our custom and color CSS content
        logger.debug("Reading custom CSS and color CSS")
        with open(color_css_path, "r", encoding="utf-8") as f:
            color_css_content = f.read()

        with open(css_path, "r", encoding="utf-8") as f:
            css_content = f.read()

        # Generate final HTML with embedded CSS and XML processing instruction
        html_str = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <meta http-equiv="Content-Style-Type" content="text/css">
    <title>CDA Document</title>
    <style>
        {color_css_content}
        {css_content}
    </style>
    <script>
        // Check if user has a preferred color scheme
        function updateTheme() {{
            if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {{
                document.documentElement.setAttribute('data-theme', 'dark');
            }} else {{
                document.documentElement.setAttribute('data-theme', 'light');
            }}
        }}
        
        // Initial theme check
        document.addEventListener('DOMContentLoaded', updateTheme);
        
        // Listen for changes in system dark mode
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', updateTheme);
    </script>
</head>
<body>
    {str(html)}
</body>
</html>"""

        # Create temporary HTML file with diagnostic info
        temp_suffix = ".xhtml" if "<?xml" in html_str else ".html"
        with tempfile.NamedTemporaryFile(suffix=temp_suffix, delete=False) as f:
            html_path = f.name

            # Add diagnostic comments at the top of the file
            diagnostic_info = f"""
<!-- 
CDA Document Transformation Info:
Source XML: {xml_path}
XSL Path: {xsl_path}
CSS Path: {css_path}
Transformation Time: {datetime.datetime.now().isoformat()}
Content-Type: {'application/xhtml+xml' if temp_suffix == '.xhtml' else 'text/html'}
-->
"""
            html_str = diagnostic_info + html_str

            # Write the file
            f.write(html_str.encode("utf-8"))

            logger.debug(f"Transformation successful")
            logger.debug(f"Output saved as: {temp_suffix} file")
            logger.debug(f"File saved to: {html_path}")

        return html_path

    except Exception as e:
        logger.error(f"Error in transformation: {str(e)}")
        return None
