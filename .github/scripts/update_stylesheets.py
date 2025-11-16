"""Update CDA stylesheets from HL7 repository."""

from health_records_collection.frontend import static_resources

static_resources.update_static_files(force=True)
