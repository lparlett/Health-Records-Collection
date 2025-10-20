# ROADMAP

This roadmap describes the next development stages for Health-Records-Collection, focusing on a unified Streamlit interface, improved usability, transparent data provenance, and clean local resource management.

## Future versions

### v0.2.0 — Schema Growth & Notes Handling

Goal: extend structured data without widening ingestion scope.

* Add Allergies and Insurance tables with clear relationships.
* Implement a Notes viewer for narrative clinical text.
* Auto-generate ER diagram and schema browser.

### v0.3.0 — Integrated Ingestion

Goal: unify ingestion and display under the Streamlit front end.

* Upload ZIPs directly through Streamlit.
* Display progress indicators and error messages in real time.
* Maintain a configurable local data directory for SQLite and imported archives.
* Add error-sandbox tab for ingestion diagnostics and downloadable logs.
* Begin file-housekeeping routines: clean temp files, verify hashes, log storage use.

### v0.4.0 — Editing & Provenance

Goal: enable safe, auditable data curation early in the lifecycle.

* Add editable tables using Streamlit’s st.data_editor.
* Introduce an audit_log table capturing table, record, field, old/new value, user, and timestamp.
* Provide rollback controls to restore original imported values.
* Create an audit-trail viewer tab.
* Optional basic-auth or local PIN for sensitive sessions.
* Start color-coding or tagging edited records in the interface.

### v0.5.0 — Interface Redesign & UX Foundation

Goal: make the application visually cohesive and comfortable to navigate.

* Two-panel layout with persistent sidebar navigation.
* Introduce dark/light mode toggle and theming presets (“clinical,” “minimalist,” “research notebook”).
* Add help overlay and inline tooltips.
* Unify typography and spacing for all Streamlit components.
* Launch compact analytics dashboard (patients, meds, encounters, abnormal-lab counts).

### v0.6.0 — Filtering & Visualization

Goal: provide intuitive exploration and quick interpretation.

* Calendar/date filtering for encounters and observations.
* Provider and visit-type filtering; manual tagging system (“urgent care,” “follow-up,” “immunization”).
* Highlight abnormal labs via color-coded ranges.
* Add record-provenance viewer (file name, import date, SHA-256 hash).
* Add data-quality tab showing missing values, inconsistent codes, duplicates.

### v0.7.0 — Search, Export, and Refinement

Goal: complete the round-trip workflow.

* Global search across diagnoses, labs, medications.
* Data-export panel for filtered CSV downloads.
* Persistent session filters (remember last view and settings).

## Ongoing and Background Tasks

* Continuous file housekeeping: cleanup, hash checks, DB vacuuming, storage metrics.
* Performance optimization: indexing, caching, parallel parsing.
* Accessibility and color-contrast review.
* Incremental test coverage: ingestion, validation, rollback integrity.

## Development Philosophy

* Local-first: all processing remains on the user’s machine.
* Reproducible: every data change is logged and reversible.
* Usable: clean, quiet, human-centered design.
* Responsible: efficient resource use and transparent provenance.
