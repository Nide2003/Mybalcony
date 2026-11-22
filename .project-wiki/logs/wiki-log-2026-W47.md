# Wiki Audit Log — 2026-W47 (2026-11-16 .. 2026-11-22)

## [2026-11-21] init | WLOG-20261121-001 | Project wiki initialized

Changed:

- `.project-wiki/` — canonical scaffold created (schema 1.7.0, 27 directories / 53 files).
- [PROJECT.md](../PROJECT.md) — project identity captured: purpose, domain, stakeholders, success criteria, global constraints; reflects the 2026-11-21 Wisland → Mybalcony rename.
- [STATUS.md](../STATUS.md) — current focus, recent updates, placeholder/next-step notes.
- [REGISTRY.yml](../REGISTRY.yml) — `PROJECT` record set to `active` / `confirmed` with source paths.
- `AGENTS.md` — always-on Project Wiki Protocol block installed at repository root.
- `.github/copilot-instructions.md` — always-on Project Wiki Protocol block installed.

Summary: Initial bootstrap only. Structural scaffold generated with the deterministic helper;
project identity filled from `README.md`, `config.example.json`, and user-provided context.
All other canonical documents intentionally left as `status: placeholder` / `confidence: unknown`;
no repository scan, requirements extraction, or technical synthesis performed.

Questions: None captured yet (see [requirements/open-questions.md](../requirements/open-questions.md)).
Alerts: None captured yet (see [alerts/INDEX.md](../alerts/INDEX.md)).

## [2026-11-22] update | WLOG-20261122-001 | Liquid-glass rendering and hover behavior synchronized

Changed:

- [PROJECT.md](../PROJECT.md) — revised medium/large island behavior and native Qt/OpenGL
  rendering constraints; added optical and 90 FPS success criteria.
- [STATUS.md](../STATUS.md) — current rendering state, verification snapshot, and absence
  of active work items updated.
- [technical/architecture.md](../technical/architecture.md) — documented native background
  window, DXCam data flow, SDF refraction, dense Gaussian center, scheduling, and fallbacks.
- [technical/codebase-map.md](../technical/codebase-map.md) — mapped rendering,
  configuration, compact-content, and interaction source files with invariants.
- [technical/testing.md](../technical/testing.md) — recorded acceptance rules, reference
  hardware, native `frameSwapped` results, optical checks, and timed-hover evidence.
- [implementation/current-plan.md](../implementation/current-plan.md) — marked rendering
  and interaction work complete; recorded next-change regression guidance.
- [traceability/code-map.md](../traceability/code-map.md) and
  [change-impact-map.md](../traceability/change-impact-map.md) — linked behavior to source,
  evidence, affected boundaries, and required regressions.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the 2026-11-22 implementation and
  verification entry.
- `INDEX.md`, `technical/INDEX.md`, `logs/INDEX.md`, and `REGISTRY.yml` — timestamps,
  coverage, and document metadata synchronized.

Summary: Explicit user-requested wiki update. Only the liquid-glass, configuration, and
hover-interaction scope was synchronized; no full repository scan was represented as done.
Performance values distinguish complete-app swapped frames from capture-only and rejected
architectures. No new requirement IDs or unsupported claims were introduced.

Questions: No new open questions. Existing placeholder open-questions page remains unchanged.
Alerts: None captured.
