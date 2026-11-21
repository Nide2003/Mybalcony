<!-- PROJECT-WIKI:BEGIN -->
## Project Wiki Protocol

When `.project-wiki/INDEX.md` exists:

- Before implementing, modifying, debugging, refactoring, testing, documenting, or planning code, read it and only the linked context needed for the task.
- After reading the index, read effective `.project-wiki/config.yml` with the skill's `wiki_config.py --wiki-root .project-wiki show`. Missing config defaults to auto-sync enabled. If `automation.auto_sync` is false or configuration is invalid, skip automatic impact assessment and all automatic wiki writes (including durable answer filing, status, reconciliation, and logs); retain context preflight and verify relevant claims against current sources. Report invalid config without silently enabling writes. Refresh configuration before post-implementation processing if it may have changed. Explicit wiki requests still run; see `references/configuration.md`.
- For wiki source access, use the skill's `wiki_scope.py` with `.project-wiki/.wikiignore`. Existing wiki history remains consultable; exclusions alone do not indicate drift.
- After agent-made source changes, when auto-sync is enabled, write only if durable knowledge or evidence changes, a wiki claim becomes false, recorded plan progress, work item status, or blockers change, or a relevant open question is resolved. If impact is uncertain, check only the relevant wiki page or work item before deciding; report any remaining uncertainty. Skip wiki edits and logs when the assessment establishes there is no impact. Update only affected records and required metadata once per coherent task, following `references/automatic-workflows.md`. Record observed behavior in `technical/`; do not infer product requirements from code.
- Use the `update` workflow for notes/documents, `sync` for external code changes and periodic reconciliation, and `maintain` for validation/migration and semantic audits. Keep explicit `sync` and `maintain` rigorous even when automatic updates were skipped. Follow the skill's deterministic helpers; never load PDF/DOCX sources directly into model context.
- Reconcile existing open questions before adding new ones. Log every meaningful wiki edit using the skill's Wiki Audit Log Workflow (`references/common-policies.md`), including its cumulative-entry rules and separate mandatory audit events.
- Write wiki content in English and reply in the user's language unless requested otherwise.
<!-- PROJECT-WIKI:END -->
