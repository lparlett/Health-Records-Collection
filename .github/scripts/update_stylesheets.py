"""Update CDA stylesheets from HL7 repository."""
import sys
sys.path.append('frontend')
import static_resources
static_resources.update_static_files(force=True)