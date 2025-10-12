# Schema Changes Log

## 2025-10-12

- Added `data_source` table to capture original filename, ingestion timestamp, SHA256 hash, and optional source archive metadata for provenance (AI-assisted by Codex + Lauren).
- Extended patient and clinical tables (patient, encounter, medication, lab_result, allergy, condition, immunization, vital, procedure, attachment, progress_note) with nullable `data_source_id` foreign keys referencing `data_source`.
- Removed legacy `provenance` table and deprecated `patient.source_file` column now that `data_source` holds ingest metadata.
- Augmented `data_source` with XDM metadata (`document_created`, `repository_unique_id`, `document_hash`, `document_size`, `author_institution`) and introduced attachment records linked to each ingested document.
