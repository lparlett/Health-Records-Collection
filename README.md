# Health Records Collection

Tools for unifying personal electronic health record exports into a local SQLite database and browsing them with a Streamlit dashboard.

## Features
- **CCD ingestion pipeline** (`ingest.py`) that:
  - Unzips raw Continuity of Care Documents (CCD) in `data/raw`
  - Parses patients, encounters, medications, labs, and conditions via modular parsers in `parsers/`
  - Normalizes providers into a shared table and links encounters, meds, labs, and conditions to them when possible
  - Persists data using the schema defined in `schema.sql` (including tables for `condition` and `condition_code`)
- **Streamlit dashboard** (`frontend/app.py`) to browse tables and run ad‑hoc SQL using configuration from `frontend/config.yaml`
- **Configurable** default row limits, DB location, and layout
- **Dependencies** captured in `requirements.txt`, including `lxml` for CCD parsing and `streamlit` for the UI

## Repository Layout
├── data/
│ ├── raw/ # Zip files with CCD exports (input)
│ └── parsed/ # Auto-created folders when zips are extracted
├── db/
│ └── health_records.db # SQLite output (overwritten on each ingest run)
├── frontend/
│ ├── app.py # Streamlit entrypoint
│ ├── db_utils.py # DB helpers used by the UI
│ ├── ui_components.py # Streamlit UI primitives
│ ├── views.py # Table + query panes
│ └── config.yaml # UI + DB configuration
├── parsers/
│ ├── patient.py # Patient demographics parser
│ ├── encounters.py # Encounter extraction + metadata
│ ├── medications.py # Medications (incl. RxNorm, providers)
│ ├── labs.py # Lab results with provider/encounter linkage
│ ├── conditions.py # Condition/problem list with multi-code support
│ ├── common.py # Shared helpers (e.g., provider name extraction)
│ └── init.py # Re-export parser entrypoints
├── ingest.py # Main ingestion workflow and DB insert helpers
├── schema.sql # SQLite schema executed during ingest
├── requirements.txt # Python dependencies
├── LICENSE
└── README.md # You are here


## Prerequisites
- Python 3.12+
- `pip` for dependency installation
- (Optional) `virtualenv` for isolated environments
- CCD export zip files (place them in `data/raw`)

## Installation & Setup
```bash
# clone (if needed)
git clone <repo-url>
cd Health-Records-Collection

# (optional) create a virtual environment
python -m venv .venv
source .venv/Scripts/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1

# install dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```
# Ingesting Health Data
1. Drop CCD zip files into data/raw.
2. Run the ingestion script:
`python ingest.py`
- Zips are extracted into data/parsed/<zip-name>/
- Data lands in db/health_records.db (existing DB is overwritten)
- Console output summarizes how many encounters, conditions, medications, and labs were ingested per file

If you modify the schema or parsers, delete db/health_records.db and rerun python ingest.py to rebuild from scratch.

# Launching the Dashboard
```streamlit run frontend/app.py```
- Configure the dashboard in frontend/config.yaml (database path, title, layout, default row limit).
- Sidebar features:
  - Multi-select table viewer (auto-limits results to the configured row count)
  - Raw SQL query box (results rendered in-line)

# Database Schema Highlights
Defined in schema.sql and created automatically during ingest:
- patient (demographics, source file)
- provider (normalized names + metadata)
- encounter (date, provider, source encounter ID, notes)
- medication (dose, route, frequency, linked provider/encounter)
- lab_result (LOINC codes, values, provider + encounter IDs)
- condition (problem list, provider, encounter, primary code fields)
- condition_code (one-to-many codes per condition)

Additional tables for immunizations, vitals, procedures, attachments, etc., ready for future parser expansion

Use SELECT name FROM sqlite_master WHERE type='table' in the UI to inspect the full schema.

# Customization & Extensibility
- Extend parsers or add new ones under parsers/; expose them via parsers/__init__.py and call them inside parse_ccd.
- Adjust ingestion logic in ingest.py (e.g., join strategies, deduplication).
- Update frontend/config.yaml to point at alternative databases or tweak layout defaults.
- Add tests under tests/ (currently empty) for regression coverage.
# Troubleshooting
- Missing lxml.etree in your editor: ensure your IDE points to the same Python interpreter where lxml is installed. Pylance warnings disappear after selecting the correct interpreter (or install lxml-stubs for type hints).
- No encounters/conditions linked: some CCD exports omit provider/date context. The ingest scripts fall back to partial matching; inspect parsed rows to refine heuristics.
- Stale DB schema: delete db/health_records.db and rerun python ingest.py.

License: MIT License