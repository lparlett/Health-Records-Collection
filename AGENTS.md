# AGENTS.md

## Purpose

Defines Codex’s expected behavior and project conventions for the **Health-Records-Collection** repository.
Goals: reproducibility, privacy, and clarity.

---

## Prompt Logging

* Ask once per session: “Where should I store this session’s prompts?”
* Record **only prompts** verbatim, not responses.
* Append each prompt chronologically with UTC timestamps.
* Do not duplicate prompts with the same UTC timestamp.
* For each response, include a confirmation that the prompt was logged. Do not stop logging unless requested by the user.
* Skip logging if no path is given.
* When the user wraps part of a prompt in `[redact this from logging] ... [stop redaction]`, replace that inner text with `[redacted]` in the log entry while keeping the rest of the prompt verbatim.
  * Example: `Please note [redact this from logging]secret[/stop redaction] info` is logged as `Please note [redacted] info`.
* Strip or redact diagnostic dumps before logging; replace pasted troubleshooting details with `[troubleshooting redacted]`.
* Log entry format:

  ```txt
  [YYYY-MM-DD HH:MM:SS UTC]
  <prompt text>
  ```

---

## Repository Structure

```txt
/parsers/   → XML and CCDA ingestion logic
/schemas/   → SQLite DDL and enumerations
/tests/     → pytest modules mirroring source structure
/docs/      → schema and workflow documentation
/data/      → synthetic or de-identified samples only
```

---

## Environment

* Python 3.12 (virtual env `.venv/`)
* SQLite database (`sqlite3`)
* Key libraries: `lxml`, `pandas`, `sqlite-utils`, `pytest`
* Do not assume root/sudo access or system-level writes.

---

## Coding Standards

* Follow **PEP 8** for style, **PEP 484** for typing, **Google-style** for docstrings.
* Use modular, testable functions with clear naming.
* Header comment in each file: purpose, author (Codex + user), date, and related tests.
* Keep imports explicit and alphabetized.
* As often as practical, keep line length to 80.
* Favor clarity over brevity; avoid one-liners that obscure logic.
* Normalize mixed-type XPath or schema outputs (e.g., convert to strings before iteration) so static analyzers such as Pylance see consistent types.

---

## Testing Conventions

* All tests use **pytest**.
* Test files named `test_<module>.py`.
* Fixtures stored in `/tests/fixtures/`.
* Assertions preferred over print debugging.
* Coverage for every major parser and schema component.

---

## Data Handling

* Treat all ingested data as **sensitive** even when de-identified.
* Never print or export PHI, IDs, or raw XML except in test fixtures.
* Ingestion scripts must:

  * Handle missing or malformed XML gracefully.
  * Record warnings but not halt execution.
  * Normalize entities by patient and encounter ID.
* LOINC and SNOMED codes serve as semantic anchors, not strict constraints.

---

## Documentation

* Use Sphinx-compatible reStructuredText docstrings.
* Update `/docs/schema_changes.md` for every schema modification.
* Each module added should include a short summary in `README.md`.

---

## AI Disclosure

* Generated code must include a brief comment noting that it was AI-assisted.
* Do not inject this comment into private data or schema dumps.

---

## Communication & Tone

* Provide concise explanations of design choices before generating code.
* Summarize outputs instead of printing large data blocks.
* When uncertain, ask clarifying questions rather than guessing.
* Maintain a factual, explanatory tone.

---

## Versioning

* Use **conventional commit messages** (`feat:`, `fix:`, `refactor:`).
* Avoid multi-purpose commits.
* Never auto-commit without explicit confirmation.

---

Last updated: 2025-10-11
