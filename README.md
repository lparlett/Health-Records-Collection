# Health Records Collection

<!-- markdownlint-disable MD013 -->
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-dashboard-ff4b4b.svg?logo=streamlit)](https://streamlit.io)
[![SQLCipher](https://img.shields.io/badge/SQLCipher-encrypted%20SQLite-07405e.svg)](https://www.zetetic.net/sqlcipher/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![AI-assisted with Codex](https://img.shields.io/badge/AI--Assisted-OpenAI_Codex-blueviolet?logo=openai&logoColor=white)](AI_disclosure.md)
[![DOI](https://zenodo.org/badge/1065521249.svg)](https://doi.org/10.5281/zenodo.17388275)
<!-- markdownlint-enable MD013 -->

Tools for unifying personal electronic health record (EHR) exports into an
SQLCipher-encrypted SQLite database and exploring them with a Streamlit
dashboard. The repository contains no protected health information; the ingest
pipeline expects you to provide your own CCD exports. Portions of the
scaffolding were drafted with generative AI and reviewed by human maintainers -
see the full [AI disclosure](AI_disclosure.md) for details.

---

## Quick Start

### :ballot_box_with_check: Requirements

- [X] Python 3.12 or newer
- [X] Streamlit-compatible browser (Chrome, Edge, Firefox, Safari)
- [X] No manual SQLCipher install required; `sqlcipher3-wheels` bundles the engine

### :scroll: Setup

```bash
git clone <repo-url>
cd Health-Records-Collection

python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows PowerShell
# or: source .venv/bin/activate   # macOS/Linux

pip install --upgrade pip
pip install -r requirements.txt
```

### :rocket: Launch and Explore

1. Start the Streamlit dashboard:

   ```bash
   streamlit run frontend/app.py
   ```

   The app opens at [http://localhost:8501](http://localhost:8501).
2. Enter the SQLCipher passphrase when prompted. The first successful entry
   establishes the encrypted database; subsequent sessions reuse the same key.
   **If you lose this key, you will not be able to unencrypt the database.**
3. Use **Upload records** in the sidebar to add CCD ZIP archives. Uploaded
   files are saved to `data/raw/`, ingested immediately, and the original XML
   documents are re-encrypted on disk. By default the source ZIP and any
   residual unencrypted artifacts are removed after ingestion; adjust this
   behaviour under *Settings* if you prefer to retain them.
4. Browse encounters, run ad-hoc SQL queries, and review schema notes without
   leaving the dashboard. Command-line ingestion remains available via
   `python ingest.py` for automation, but the Streamlit workflow covers the
   standard path.

---

## :microscope: How It Works

- **Ingestion pipeline (`ingest.py`)**
  - Receives CCD archives from the Streamlit upload flow (or the optional CLI),
    writes them to `data/raw/`, and unzips contents into `data/parsed/`.
  - Parses XML with lxml using modular parsers in `parsers/` for patients,
    encounters, allergies, conditions, medications, labs, procedures, vitals,
    immunizations, progress notes, and insurance coverage.
  - Records file-level provenance in the `data_source` table (original filename,
    archive, SHA256 hash, creation time, repository ID, and author institution
    pulled from XDM `METADATA.XML`) and threads the resulting identifier
    through every downstream insert.
  - Normalizes providers, deduplicates medications and immunizations, and
    invokes service modules in `services/` to load data into SQLite.
  - Encrypts the source CCD documents with `security/encryption` so the original
    XML is stored as `.enc` files alongside the SQLCipher database.
  - Performs post-ingest cleanup according to user preferences, deleting the
    original archive and any leftover non-XML files when the secure defaults
    remain enabled.
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
  - The **Upload records** view invokes ingestion under the hood, hashes archives
    to avoid duplicates, and encrypts the original CCD files before persisting
    them to disk.
  - Database files are encrypted at rest via SQLCipher. The Streamlit
    dashboard prompts for the passphrase at launch, and headless workflows
    can supply it through the `HRC_SQLCIPHER_PASSPHRASE` environment variable
    (handled by `security/sqlcipher_support.py`). We vendor the
    community-maintained `sqlcipher3-wheels` package so Windows installs do not
    require compiling SQLCipher manually; verify the wheel hashes in deployment
    pipelines for defense-in-depth.
  - XML files are rendered using the HL7 CDA Core Stylesheet, automatically
    updated weekly from the official repository with proper attribution.

- **Schema & services (`schema.sql`, `services/`)**
  - `schema.sql` defines core tables for patients, providers, encounters,
    medications, lab results, allergies, insurance coverage, conditions
    (with codes), procedures, vitals, immunizations, attachments, progress notes,
    and the `ingested_archive` registry used to track archive hashes and ingestion
    counts, each linking back to enriched `data_source` metadata (now including
    `source_archive_id` foreign keys to `ingested_archive`).
  - Service modules encapsulate insert logic, deduplication, and foreign key
    wiring for each domain. `services/data_sources.py` manages provenance rows
    so other modules can reference a shared `data_source_id`, while `services/archives.py`
    records archive hashes so duplicate uploads can be flagged safely.
  - `db/schema.py` backfills missing columns, normalizes provider records, and
    adds protective indexes.

---

## :raised_hands: External Resources

- **CDA Rendering**
  - This project uses the [HL7 CDA Core Stylesheet](https://github.com/HL7/cda-core-xsl)
    for rendering CDA XML documents, which is maintained in a separate repository
    and automatically updated via GitHub Actions. The stylesheet files are included
    under the Apache 2.0 license with proper attribution.

- **Color Palette**
  -[Coolors.co](https://coolors.co/2b4162-385f71-f5f0f6-d7b377-8f754f)

---

## :star: Repository Layout

```text
data/               Raw ZIP exports (`raw/`) and extracted XML (`parsed/`)
db/                 SQLite artifacts (`health_records.db`) and schema helpers
frontend/           Streamlit application entry point, views, and utilities
parsers/            CCD XML parsers grouped by domain
security/           Security-related functions
services/           Persistence helpers for each domain table
tests/              Pytest suite covering parsers, services,
                    schema, and ingest flow
user/               User-specific settings
ingest.py           Command-line ingestion workflow
schema.sql          Canonical database definition
requirements.txt    Locked Python dependencies
```

---

## :gear: Configuration & Customization

- Encryption keys are stored in `user/encryption.key`; attachments are encrypted
  at rest and decrypted on demand for previews.
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
- Use the Settings view to toggle post-ingest cleanup (archive deletion and
  removal of non-XML extracts) to match your retention policy.
- Use the **Settings** view in the Streamlit sidebar to update the raw, parsed,
  and database paths. Overrides are saved to `user/settings.yaml` and the app
  automatically reloads after changes.
- Enter the SQLCipher passphrase when the Streamlit dashboard prompts for it,
  or provide `HRC_SQLCIPHER_PASSPHRASE` in your shell for automated ingest
  and headless scripts.

---

## :100: Development

- Run the automated tests with:

  ```bash
  pytest
  ```

- The project targets Python 3.12; please keep new dependencies pinned in
  `requirements.txt`.
- Follow the contributor guidelines in `CONTRIBUTING.md` and report security
  concerns per `SECURITY.md`.

---

## :thumbsup: License

MIT License. See [LICENSE](LICENSE) for full terms.
