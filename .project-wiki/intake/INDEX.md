# Document Intake

This section stores external source documents imported for project-wiki update workflows. Intake documents are provenance, not canonical project knowledge until accepted information is integrated into requirements, changes, technical docs, implementation docs, or traceability maps.

## When To Read

- Process a new PDF, DOCX, text, or Markdown requirements document.
- Review the source provenance behind a requirement, CR, ADR, or open question.
- Investigate conflicts between an imported document and the current KB or as-is technical state.

## Routing Rules

- Read active and reviewed intake documents only when working on document-based updates, provenance, audits, or conflict investigation.
- Read the compact `intake-report.md`, then use `review_progress.py inspect` for structure and coverage. Do not load `chunks.json`, `review-progress.yml`, or generated chunk wrappers directly unless troubleshooting.
- Use `view --section SEC-NNN` only for reliable source-defined sections reported by `inspect`; review every listed section and unsectioned unit. Use `view --all` whenever structure is absent, incomplete, ambiguous, or full-document context may matter.
- After complete coverage, run `review_progress.py audit`; require `review-complete` and record its ledger summary and SHA-256. Rerun after ledger corrections.
- Before a terminal intake status, run `audit --expect-ledger-sha256 <final-ledger-sha256>` with the digest from the reviewed audit.
- Do not mark an intake reviewed or integrated until the ledger is complete. Every classified integrated chunk must link to its registered target IDs; every skipped chunk needs a reason.
- Do not read integrated, archived, superseded, or rejected intake documents during normal coding tasks unless explicitly requested.
- Use canonical KB files, not intake documents, as the source of truth after integration.

## Active Intake Documents

- None yet.

## Reviewed, Integrated, Archived, Superseded, Or Rejected Documents

- None yet.
