# AGENTS.md

## Purpose

Defines Codex's expected behavior and project conventions for the **Health-Records-Collection** repository.
Goals: reproducibility, privacy, and clarity.

---

## Repository Structure

```txt
/parsers/   → XML and CCDA ingestion logic
/services/  → functions to assist with parsing and cleaning
/tests/     → pytest modules mirroring source structure
/frontend/  → Streamlit-related coding
/docs/      → schema and workflow documentation
/data/      → synthetic or de-identified samples only
```

---

## Environment

* Python 3.12 (Poetry-managed virtual environment)
* SQLite database (`sqlite3`)
* Key libraries: `lxml`, `pandas`, `sqlite-utils`, `pytest`
* Do not assume root/sudo access or system-level writes.

---

## Coding Standards

* Follow **PEP 8** for style, **PEP 484** for typing, **Google-style** for docstrings.
* Use modular, testable functions with clear naming.
* Header comment in each file: purpose, author (Codex + user), date, and related tests.
* Verify every script passes `pylint` and is formatted with `black` before returning results to the user.
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

## Security-First Development Rules

Source: [StackHawk](https://www.stackhawk.com/blog/4-best-practices-for-ai-code-security-a-developers-guide/)

### Code Security Standards

* Always use parameterized queries - never string concatenation for database queries
* Implement proper input validation and sanitization for all user inputs
* Use secure authentication and authorization patterns
* Never hardcode secrets, API keys, or passwords in source code
* Implement proper error handling that doesn't expose sensitive information
* Follow OWASP Top 10 guidelines for web application security

### Dependency Management

* Only suggest well-maintained packages with recent updates
* Prefer packages with strong security track records
* Flag any dependencies that haven't been updated in 12+ months
* Always check for known vulnerabilities before suggesting packages
* Before commits, ensure `pyproject.toml` and `poetry.lock` reflect any dependency changes (`poetry lock` / `poetry update`)

### Code Review Requirements

* Generate TODO comments for any code that needs security review
* Add inline comments explaining security-relevant decisions
* Flag any code that handles sensitive data for manual review
* Suggest security test cases for authentication and authorization logic

### Error Handling

* Implement fail-secure patterns (deny by default)
* Log security events appropriately without exposing sensitive data
* Use structured error responses that don't leak implementation details

## Healthcare Security Requirements

* Encrypt all PHI at rest and in transit using AES-256 and TLS 1.2+
* Log all data access for auditing
* Follow the minimum necessary principle for data access  
* Use cryptographically secure random number generation
* Implement session timeouts for sensitive data access

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

## Versioning & Branching Guidelines

### Commit messages

* Use [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, etc.)
* Keep commits atomic and single-purpose — one logical change per commit
* Write brief, imperative summaries (e.g., `fix: correct null handling in parser`)

### Branch structure

* **main** — always stable, production-ready code  
* **release/X.Y.Z** — branch from `main`  
  * Used to integrate multiple features, test, and prepare for tagging  
* **feature/short-slug** — branch from a current `release/X.Y.Z` branch  
  * Used for developing or refactoring specific features or fixes  
  * When the feature is complete and verified, merge it back into that same release branch immediately.
  * The release branch should therefore accumulate all completed features.
* Subsequent features for the same release must branch from the updated release branch so they include all previously merged work.
* Merge completed `release/X.Y.Z` branches back into `main` when verified
* When the release is ready, merge the release branch back into `main` (and tag as needed) before starting the next release.

### Merging & tagging

* Prefer **squash merges** for feature branches (to keep history readable)
* Tag the final commit on `main` as `vX.Y.Z` upon release
* Delete merged branches after confirmation to keep the repo tidy

### Automation rules

* Never auto-commit, merge, or push without explicit human confirmation
* Always perform `git pull --rebase` before committing to avoid merge noise
* If conflicts occur, pause for human review — do not attempt auto-resolution
* Do not modify `.gitignore`, `.gitattributes`, or `.gitmodules` without approval

### Documentation hints (for AI)

* Each release should have a matching entry in `CHANGELOG.md`
* Include the related issue or PR number in the commit body when available
* Treat commits as part of the project’s provenance record
* Include AI-assisted code attribution in the commit body, referencing the prompt(s) and model used

### Issue and milestone linkage

* Each feature or enhancement must have a corresponding **GitHub issue**.
* The **issue number** defines the branch name:  
  * Example: `feature/17-notes-viewer`
* Assign each issue to the appropriate **milestone** (e.g., `v0.2.0`), which maps to the `release/0.2.0` branch.
* Reference the issue in all commits and PRs using the format `Refs #17` or `Closes #17` as appropriate.
* Do not merge feature branches that are not tied to an issue and milestone.

---

Last updated: 2025-10-29
