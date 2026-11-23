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

## [2026-11-22] update | WLOG-20261122-002 | Small/medium GPU fast path and liquid theme synchronized

Changed:

- [technical/architecture.md](../technical/architecture.md) — Frame Scheduling now covers the
  native-GPU settled fast path for all three island states and the lifted collapsed capture
  clamp, with explicit fallback boundaries.
- [technical/codebase-map.md](../technical/codebase-map.md) — documented `_gpu_active()`,
  `_compact_cursor_far()`, collapsed capture pacing, `compact.busy()`, the liquid palette/font
  and QSS `font_css()` callers; added `theme.py`, `liquid.py`, `lookup.py` source paths.
- [technical/testing.md](../technical/testing.md) — added the 67/67 production-method logic
  regression, theme smoke check, and the pending real-FPS/optical/interaction items.
- [implementation/current-plan.md](../implementation/current-plan.md) — recorded the completed
  fast-path/theme changes and pending reference-machine verification.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the 2026-11-22 small/medium GPU and
  theme entry.
- [STATUS.md](../STATUS.md) — current focus, verification snapshot, and recent updates revised.
- [traceability/code-map.md](../traceability/code-map.md) and
  [change-impact-map.md](../traceability/change-impact-map.md) — linked the new behaviors,
  source paths, verification, and fallback boundaries.
- [REGISTRY.yml](../REGISTRY.yml) — source paths refreshed for the touched technical records.

Summary: Automatic post-implementation synchronization after two related code changes. The
collapsed/medium islands now reuse the verified native-GPU fast path and capture cadence, and
liquid-glass body text was restyled white with PingFang SC. The QA result is a logic-level
regression against production methods, not a real-FPS measurement; reference-machine checks
remain explicitly pending. No requirement IDs or unsupported performance claims introduced.

Questions: No new open questions; the theme restyle is recorded as observed implementation
behavior, not an invented product requirement.
Alerts: None captured.

## [2026-11-22] update | WLOG-20261122-003 | Foreground accents, lyric repaint, and outlined text synchronized

Changed:

- [technical/architecture.md](../technical/architecture.md) — added the foreground repaint gate
  (`_foreground_animating()`), the expanded specular-frame guard, the GPU foreground optical
  accents, and the liquid outlined-text model with its QSS drop-shadow fallback.
- [technical/codebase-map.md](../technical/codebase-map.md) — documented `_gpu_liquid_accents()`,
  `_foreground_animating()`, `theme.outlined_text()`, `apply_qss_text_shadow()`, the body-text
  call sites, and the newly touched source paths.
- [technical/testing.md](../technical/testing.md) — recorded the 69/69 production-method logic
  regression for the island changes, the 47/47 outlined-text verification, and the pending
  real-machine checks.
- [implementation/current-plan.md](../implementation/current-plan.md) — appended the three
  completed changes and their source paths.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the foreground-accent, lyric-repaint,
  and outlined-text entry.
- [STATUS.md](../STATUS.md) — current focus, recent updates, and verification snapshot revised.
- [traceability/code-map.md](../traceability/code-map.md) and
  [change-impact-map.md](../traceability/change-impact-map.md) — linked the new behaviors,
  sources, verification, and fallback/regression boundaries.
- [REGISTRY.yml](../REGISTRY.yml) — source paths refreshed for the touched technical records.

Summary: Automatic post-implementation synchronization after three user-requested changes:
give the expanded GPU island menu-level glass accents, fix frozen shape-invariant foreground
animation (collapsed lyric sweep), and give liquid body text a black stroke plus light shadow.
Two independent QA runs passed (69/69 island logic, 47/47 outlined text), both logic/pixel-level
rather than real-FPS measurements; reference-machine FPS, optical, and interaction checks remain
explicitly pending. Two non-blocking findings were fixed before this sync: a `not self.expanded`
guard for fast cursor exits during the expanded specular window, and a liquid-only branch in
`home.py` `CoverTitle` to preserve the original non-liquid glow. No requirement IDs or
unsupported performance claims introduced.

Questions: No new open questions. Alerts: None captured.
