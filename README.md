# Health Records Collection

<!-- markdownlint-disable MD013 -->
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-dashboard-ff4b4b.svg?logo=streamlit)](https://streamlit.io)
[![SQLite](https://img.shields.io/badge/SQLite-database-07405e.svg?logo=sqlite)](https://www.sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![AI-assisted with Codex](https://img.shields.io/badge/AI--Assisted-OpenAI_Codex-blueviolet?logo=openai&logoColor=white)](AI_disclosure.md)
[![DOI](https://zenodo.org/badge/1065521249.svg)](https://doi.org/10.5281/zenodo.17388275)
<!-- markdownlint-enable MD013 -->

Tools for unifying personal electronic health record (EHR) exports into a local
SQLite database and exploring them with a Streamlit dashboard. The repository
contains no protected health information; the ingest pipeline expects you to
provide your own CCD exports. Portions of the scaffolding were drafted with
generative AI and reviewed by human maintainers - see the full
[AI disclosure](AI_disclosure.md) for details.

---

## Quick Start

### Requirements

- Python 3.12 or newer
- SQLite (bundled with Python)
- Streamlit-compatible browser (Chrome, Edge, Firefox, Safari)

### Setup

```bash
git clone <repo-url>
cd Health-Records-Collection

python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows PowerShell
# or: source .venv/bin/activate   # macOS/Linux

pip install --upgrade pip
pip install -r requirements.txt
```

### Ingest and Explore

1. Drop each CCD ZIP export into `data/raw/`.
1. Run the ingestion workflow:

   ```bash
   python ingest.py
   ```
  
   This creates or refreshes `db/health_records.db`, extracts ZIP contents into
   `data/parsed/`, and populates all supported tables.

   - Add `--log-level debug` to surface detailed troubleshooting messages
   while you iterate:

     ```bash
     python ingest.py --log-level debug
     ```

   - To capture logs without printing patient identifiers to the console,
   direct output to a file:

     ```bash
     python ingest.py --log-level info --log-file logs/ingest.log
     ```

     Debug logs include richer context, so avoid enabling them on shared systems.
1. Launch the dashboard:

   ```bash
   streamlit run frontend/app.py
   ```
  
   Streamlit opens at [http://localhost:8501](http://localhost:8501) with an
   encounter overview, table browser, and SQL scratchpad.

---

## How It Works

- **Ingestion pipeline (`ingest.py`)**
  - Unzips CCD packages from `data/raw/` into `data/parsed/` (skipping extracts
    that already exist).
  - Parses XML with lxml using modular parsers in `parsers/` for patients,
    encounters, conditions, medications, labs, procedures, vitals,
    immunizations, and progress notes.
  - Records file-level provenance in the `data_source` table (original filename,
    archive, SHA256 hash, creation time, repository ID, and author institution
    pulled from XDM `METADATA.XML`) and threads the resulting identifier
    through every downstream insert.
  - Normalizes providers, deduplicates medications and immunizations, and
    invokes service modules in `services/` to load data into SQLite.
  - Applies schema migrations on the fly via `db/schema.py` to keep older
    databases compatible.

- **Streamlit dashboard (`frontend/`)**
  - `views.py` renders an Encounter Overview with expandable visit summaries,
    including diagnoses and medications.
  - Sidebar controls let you pick tables to preview using reusable widgets in
    `ui_components.py`.
  - A SQL query box allows ad-hoc exploration; results render with native
    Streamlit dataframes.
  - Connection utilities in `db_utils.py` keep the UI responsive with row
    limits and read-only access.
  - XML files are rendered using the HL7 CDA Core Stylesheet, automatically
    updated weekly from the official repository with proper attribution.

- **Schema & services (`schema.sql`, `services/`)**
  - `schema.sql` defines core tables for patients, providers, encounters,
    medications, lab results, allergies, conditions (with codes), procedures,
    vitals, immunizations, attachments, and progress notes, each
    linking back to enriched `data_source` metadata.
  - Service modules encapsulate insert logic, deduplication, and foreign key
    wiring for each domain. `services/data_sources.py` manages provenance rows
    so other modules can reference a shared `data_source_id`.
  - `db/schema.py` backfills missing columns, normalizes provider records, and
    adds protective indexes.

---

## External Resources

- **CDA Rendering**
  - This project uses the [HL7 CDA Core Stylesheet](https://github.com/HL7/cda-core-xsl)
    for rendering CDA XML documents, which is maintained in a separate repository
    and automatically updated via GitHub Actions. The stylesheet files are included
    under the Apache 2.0 license with proper attribution.

- **Color Palette**
  -[Coolors.co](https://coolors.co/2b4162-385f71-f5f0f6-d7b377-8f754f)

---

## Repository Layout

```text
data/               Raw ZIP exports (`raw/`) and extracted XML (`parsed/`)
db/                 SQLite artifacts (`health_records.db`) and schema helpers
frontend/           Streamlit application entry point, views, and utilities
parsers/            CCD XML parsers grouped by domain
services/           Persistence helpers for each domain table
tests/              Pytest suite covering parsers, services,
                    schema, and ingest flow
ingest.py           Command-line ingestion workflow
schema.sql          Canonical database definition
requirements.txt    Locked Python dependencies
```

---

## Configuration & Customization

- Update `frontend/config.yaml` to change the dashboard title, layout, database
  path, or default row limits.
- Extend parsing coverage by adding new modules in `parsers/` and wiring them
  into `ingest.py`.
- Modify or append tables by editing `schema.sql` and enhancing `db/schema.py`
  to enforce migrations.
- Regenerate the database at any time by deleting `db/health_records.db` and
  rerunning `python ingest.py`.
- Control ingestion verbosity per run with `--log-level {error,warning,info,debug}`
  and optionally persist output via `--log-file path/to/logs.txt`.

---

## Development

- Run the automated tests with:

  ```bash
  pytest
  ```

- The project targets Python 3.12; please keep new dependencies pinned in
  `requirements.txt`.
- Follow the contributor guidelines in `CONTRIBUTING.md` and report security
  concerns per `SECURITY.md`.

---

## License

MIT License. See [LICENSE](LICENSE) for full terms.
