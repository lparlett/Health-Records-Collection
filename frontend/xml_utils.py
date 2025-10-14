"""XML transformation utilities for CDA documents."""
import os
from pathlib import Path
import tempfile
import logging
import datetime
import lxml.etree as ET
from typing import Optional
from . import static_resources

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
            
        content = file_path.read_text(encoding='utf-8')
        if not content.strip():
            print(f"Stylesheet file is empty: {file_path}")
            return False
            
        if '<?xml' not in content:
            print(f"Stylesheet lacks XML declaration: {file_path}")
            return False
            
        # Try parsing as XML
        parser = ET.XMLParser(remove_blank_text=True)
        tree = ET.fromstring(content.encode('utf-8'), parser)
        
        # Verify it's an XSL stylesheet
        if not (tree.tag == '{http://www.w3.org/1999/XSL/Transform}stylesheet' or 
                tree.tag == '{http://www.w3.org/1999/XSL/Transform}transform'):
            print(f"Not a valid XSLT file (root is {tree.tag}): {file_path}")
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
    xml_content = ""  # Initialize for error handling
    def debug_xml(xml_content: str, stage: str) -> None:
        """Helper to log XML content during transformation"""
        debug_path = Path(tempfile.gettempdir()) / f"debug_{stage}.xml"
        with open(debug_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)
        logger.debug(f"Debug file written: {debug_path}")
        
        try:
            # Validate the XML is well-formed
            ET.fromstring(xml_content.encode('utf-8'))
            logger.debug(f"{stage} XML is well-formed")
        except ET.XMLSyntaxError as e:
            logger.error(f"{stage} XML parsing error: {str(e)}")

    try:
        # Get stylesheet path using resource manager
        xsl_path = static_resources.get_stylesheet_path()
        if not xsl_path:
            print("Could not get valid CDA stylesheet")
            return None
            
        # Get paths for other resources
        static_dir = Path(__file__).parent / "static"  
        css_path = static_dir / "cda_custom.css"
            
        # Log transformation details
        logger.info(f"Transforming XML file: {xml_path}")
        logger.info(f"Using stylesheet: {xsl_path}")
        logger.info(f"Using CSS: {css_path}")
            
        # Read and validate input XML
        xml_content = Path(xml_path).read_text(encoding='utf-8')
        if not xml_content.strip():
            logger.error(f"XML file is empty: {xml_path}")
            return None
                
        if '<?xml' not in xml_content:
            logger.info("Adding XML declaration")
            xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_content
            
        debug_xml(xml_content, 'input')
        
        # Log XML content size for debugging
        logger.debug(f"XML content size: {len(xml_content)} bytes")
        
        # Parse XML and XSL
        parser = ET.XMLParser(remove_blank_text=True)
        xml_doc = ET.fromstring(xml_content.encode('utf-8'), parser)
        xsl_doc = ET.parse(str(xsl_path))
        
        # Create transformer and transform with error handling
        logger.debug("Creating XSLT transformer")
        transform = ET.XSLT(xsl_doc)
        
        # Log XSL document details
        logger.debug(f"XSL document root tag: {xsl_doc.getroot().tag}")
        logger.debug(f"XSL document size: {len(ET.tostring(xsl_doc))}")
        
        # Transform and capture any errors
        try:
            logger.debug("Performing XSLT transformation")
            html = transform(xml_doc)
            
            # Log transformation result details
            result_str = str(html)
            logger.debug(f"Transformation result size: {len(result_str)} bytes")
            logger.debug(f"Result preview: {result_str[:200]}...")
            
            if not result_str.strip():
                logger.error("Transformation produced empty result")
                return None
                
        except ET.XSLTError as e:
            logger.error(f"XSLT transformation failed: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during transformation: {str(e)}")
            return None
            
        # Log success
        logger.debug("XSLT transformation completed successfully")
        
        # Get our custom CSS content
        logger.debug("Reading custom CSS")
        with open(css_path, 'r', encoding='utf-8') as f:
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
        temp_suffix = '.xhtml' if '<?xml' in html_str else '.html'
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
            f.write(html_str.encode('utf-8'))
            
            # Create a debug copy that won't be deleted
            debug_path = Path(tempfile.gettempdir()) / f"debug_final_{Path(xml_path).name}{temp_suffix}"
            with open(debug_path, 'wb') as debug_f:
                debug_f.write(html_str.encode('utf-8'))
            
            logger.info(f"Transformation successful")
            logger.debug(f"Output saved as: {temp_suffix} file")
            logger.debug(f"File saved to: {html_path}")
            logger.debug(f"Debug copy saved to: {debug_path}")
            
        return html_path
        
    except Exception as e:
        logger.error(f"Error in transformation: {str(e)}")
        if xml_content:  # Debug the state when error occurred
            debug_xml(xml_content, 'error')
        return None