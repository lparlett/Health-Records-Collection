"""Update CDA stylesheets from HL7 repository."""

from frontend import static_resources

static_resources.update_static_files(force=True)
