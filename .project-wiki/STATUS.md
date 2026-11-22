# Project Status

Last updated: 2026-11-22

## Current Focus

- Liquid-glass rendering and the revised hover interaction are implemented and documented.
- The active renderer uses a native OpenGL background below the Qt foreground island.
- Normal runtime configuration is hover expansion, unpinned, with a 90 FPS capture target
  and a five-second large-island hover delay.

## Recent Wiki Updates

- 2026-11-22: Populated architecture, codebase map, testing, current plan, traceability,
  and project behavior from the live-glass implementation and measured results.
- 2026-11-21: Project wiki initialized (schema 1.7.0); project identity and initial audit
  log captured.

## Active Work Items

- None captured. See [implementation/current-plan.md](./implementation/current-plan.md)
  for completed rendering and interaction work and next-change verification guidance.

## Blockers And Open Questions

- No new open question resulted from the 2026-11-22 rendering or interaction changes.
- See [requirements/open-questions.md](./requirements/open-questions.md).

## Active Alerts

- No active alerts captured.

## Verification Snapshot

- Native clear-center build: 90.219 complete-app swapped frames per second.
- Dense 5x5 Gaussian-center build: 117.045 complete-app swapped frames per second in the
  documented reference scenario.
- Timed hover regression passed at 4.8 seconds (medium only), 5.1 seconds (large), and on
  single click (immediate large). See [technical/testing.md](./technical/testing.md).

## Stale Or Placeholder Areas

- Several requirements, deployment, security, sources, intake, and analysis scaffolds have
  not yet been populated. The architecture, codebase-map, testing, and current-plan pages
  are no longer placeholders.

## Last Scan

- No full repository scan captured. The 2026-11-22 update was a targeted synchronization
  of the liquid-glass rendering, configuration, and hover-interaction source paths.
