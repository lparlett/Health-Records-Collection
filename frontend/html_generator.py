"""HTML template generation for CDA document transformation.

This module handles the generation of the final HTML output with embedded CSS
and metadata, separated from the core XML transformation logic.
"""

from __future__ import annotations

import datetime
import tempfile
from dataclasses import dataclass
from typing import Optional

import logging

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class HtmlAssets:
    """Container for CSS content and diagnostic paths."""

    color_css: str
    css: str
    xml_path: str
    xsl_path: str
    css_path: str


def generate_html_file(html_body: str, assets: HtmlAssets) -> Optional[str]:
    """Generate a complete HTML file from transformation output with embedded CSS.

    Args:
        html_body: The HTML body content from XSLT transformation.
        assets: CSS content and diagnostic metadata.

    Returns:
        Path to temporary HTML file or None if generation fails.
    """
    try:
        html_str = _build_html_template(html_body, assets.color_css, assets.css)

        # Create temporary HTML file
        temp_suffix = ".xhtml" if "<?xml" in html_str else ".html"
        with tempfile.NamedTemporaryFile(suffix=temp_suffix, delete=False) as f:
            html_path = f.name

            # Add diagnostic comments
            content_type = (
                "application/xhtml+xml" if temp_suffix == ".xhtml" else "text/html"
            )
            diagnostic_info = _build_diagnostic_comment(
                assets.xml_path, assets.xsl_path, assets.css_path, content_type
            )
            html_str = diagnostic_info + html_str

            # Write the file
            f.write(html_str.encode("utf-8"))

            logger.debug("Transformation successful")
            logger.debug("Output saved as: %s file", temp_suffix)
            logger.debug("File saved to: %s", html_path)

        return html_path

    except (OSError, ValueError) as exc:
        logger.error("Error generating HTML file: %s", exc)
        return None


def _build_html_template(
    html_body: str,
    color_css_content: str,
    css_content: str,
) -> str:
    """Build the complete HTML template with embedded CSS and scripts.

    Args:
        html_body: The HTML body content.
        color_css_content: Color scheme CSS.
        css_content: Custom styling CSS.

    Returns:
        Complete HTML document string.
    """
    return """<?xml version="1.0" encoding="UTF-8"?>
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
        %s
        %s
    </style>
    <script>
        // Check if user has a preferred color scheme
        function updateTheme() {
            if (
                window.matchMedia &&
                window.matchMedia('(prefers-color-scheme: dark)').matches
            ) {
                document.documentElement.setAttribute('data-theme', 'dark');
            } else {
                document.documentElement.setAttribute('data-theme', 'light');
            }
        }
        
        // Initial theme check
        document.addEventListener('DOMContentLoaded', updateTheme);
        
        // Listen for changes in system dark mode
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', updateTheme);
    </script>
</head>
<body>
    %s
</body>
</html>""" % (
        color_css_content,
        css_content,
        html_body,
    )


def _build_diagnostic_comment(
    xml_path: str,
    xsl_path: str,
    css_path: str,
    content_type: str,
) -> str:
    """Build diagnostic HTML comment with transformation metadata.

    Args:
        xml_path: Path to source XML.
        xsl_path: Path to XSL stylesheet.
        css_path: Path to CSS file.
        content_type: MIME type of output.

    Returns:
        HTML comment string with diagnostic info.
    """
    return f"""<!--
CDA Document Transformation Info:
Source XML: {xml_path}
XSL Path: {xsl_path}
CSS Path: {css_path}
Transformation Time: {datetime.datetime.now().isoformat()}
Content-Type: {content_type}
-->
"""
