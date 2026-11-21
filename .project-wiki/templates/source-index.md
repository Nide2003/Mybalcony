# Sources

This section stores raw source documents used by document-based update workflows. Source documents are raw input, not canonical project knowledge.

## How To Use

- Drop new PDF, DOCX, text, or Markdown files into [inbox/](./inbox/).
- Run `/project-wiki update`.
- The agent runs the project-wiki deterministic inbox preflight with skip quarantine, registers only files classified `process` in [SOURCE_REGISTRY.yml](./SOURCE_REGISTRY.yml), runs document ingestion, and moves successfully processed files to `processed/YYYY-MM/` when possible.
- Keep human instructions in this file. Do not create `README.md` or other guide files inside `inbox/`.

## Routing Rules

- Never read PDF/DOCX source files directly into model context.
- Use source files only through the document ingestion script.
- Treat the inbox preflight report as authoritative for SHA-256 hashes, validated registry and intake-history matches, retry-record selection, inbox duplicates, and quarantine destinations; use agent review only for changed content at a historical path, ambiguous registry history, or explicit reprocessing.
- Use `intake/` artifacts for review and canonical KB integration.
- Ignore inbox housekeeping files such as `README.md`, `.gitkeep`, `.DS_Store`, hidden files, files beginning with `_`, and temporary or partial download files.

## Inbox

- No pending source files registered yet.

## Processed Sources

- None yet.

## Failed, Rejected, Ignored, Or Superseded Sources

- None yet.
