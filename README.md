# Health Records Collection

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Streamlit](https://img.shields.io/badge/Streamlit-dashboard-ff4b4b.svg?logo=streamlit)](https://streamlit.io)
[![SQLite](https://img.shields.io/badge/SQLite-database-07405e.svg?logo=sqlite)](https://www.sqlite.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Project Status](https://img.shields.io/badge/status-in%20progress-yellow.svg)](#)

Tools for unifying personal electronic health record (EHR) exports into a local SQLite database and browsing them with a Streamlit dashboard.

---

## 🚀 Quickstart

```bash
git clone <repo-url>
cd Health-Records-Collection

# (optional) create a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1   # Windows PowerShell
# or: source .venv/bin/activate

pip install -r requirements.txt

# Ingest health record exports (zip files placed in data/raw)
python ingest.py

# Launch the dashboard
streamlit run frontend/app.py
```

Your database will be created at `db/health_records.db` and the dashboard will open at [http://localhost:8501](http://localhost:8501).

---

## ✨ Features

- **CCD ingestion pipeline** (`ingest.py`)
  - Unzips Continuity of Care Document (CCD) exports from `data/raw/`
  - Parses patients, encounters, medications, labs, and conditions via modular parsers in `parsers/`
  - Normalizes providers and links them across encounters, meds, labs, and conditions
  - Persists data into SQLite using `schema.sql`
- **Streamlit dashboard** (`frontend/app.py`)
  - Table browser with configurable row limits
  - Raw SQL query box for ad-hoc exploration
- **Configurable**
  - Database location, page title, layout, row limits via `frontend/config.yaml`
- **Extensible**
  - Add new parsers, schema extensions, or custom dashboard views

---

## 📂 Repository Layout

```
data/                # Raw and parsed health record exports
db/                  # SQLite database (overwritten on ingest)
frontend/            # Streamlit UI
  ├─ app.py
  ├─ config.yaml
  ├─ db_utils.py
  ├─ ui_components.py
  └─ views.py
parsers/             # Modular CCD parsers
ingest.py            # Main ingestion workflow
schema.sql           # Database schema
requirements.txt     # Dependencies
tests/               # Unit tests (currently empty)
```

---

## 🧱 Database Schema (Highlights)

Defined in `schema.sql` and auto-created during ingestion:

- `patient` — demographics, source file reference  
- `provider` — normalized names + metadata  
- `encounter` — date, provider, notes, source IDs  
- `medication` — dose, route, frequency, provider/encounter links  
- `lab_result` — LOINC codes, values, provider + encounter IDs  
- `condition` — problem list, provider/encounter, primary codes  
- `condition_code` — one-to-many codes per condition  

Additional placeholder tables exist (immunizations, vitals, procedures, attachments) for future parser expansion.

---

## 🛠️ Customization & Extensibility

- **Add new parsers** → implement in `parsers/`, register in `parsers/__init__.py`.  
- **Schema changes** → update `schema.sql`, rebuild DB by deleting `db/health_records.db` and re-running `ingest.py`.  
- **Dashboard tweaks** → edit `frontend/config.yaml` (database path, layout, row limits).  
- **Testing** → add regression coverage under `tests/` (pytest recommended).

---

## 🐞 Troubleshooting

- **Missing `lxml` in your IDE** → ensure your IDE uses the same interpreter where you installed deps. You may also install `lxml-stubs` for type hints.  
- **No encounters/conditions linked** → some CCDs omit provider/date info. Parsers fall back to partial matching — inspect parsed rows and refine heuristics.  
- **Schema mismatch errors** → delete `db/health_records.db` and rebuild with `python ingest.py`.  

---

## 📜 License

MIT License. See `LICENSE` for details.
