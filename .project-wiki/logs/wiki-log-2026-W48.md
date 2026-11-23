# Wiki Audit Log — 2026-W48 (2026-11-23 .. 2026-11-29)

## [2026-11-23] update | WLOG-20261123-001 | Liquid menu text, battery bottom fade, nav capsule fit synchronized

Changed:

- [technical/architecture.md](../technical/architecture.md) — foreground/menu text and liquid
  components already cover these paths; no new architecture section required beyond the existing
  outlined-text and foreground models.
- [technical/codebase-map.md](../technical/codebase-map.md) — documented the liquid QMenu proxy
  style and color/font-only QSS, the battery-page `_EdgeFade`/spacer gating, the navigation
  capsule `CAP_PAD = 0`, and updated the outlined-text exclusion note (menu text now stroked).
- [technical/testing.md](../technical/testing.md) — recorded the 49/49 liquid-menu verification
  (proxy really invoked, dark overlay absent, non-liquid zero pollution), the battery fade
  ARGB32 `render()` proof that `DestinationOut` erases sibling pixels (including the RGB32
  `grab()` methodology caveat), and the capsule geometry check.
- [implementation/current-plan.md](../implementation/current-plan.md) — appended the three
  completed 2026-11-23 changes, their source paths, and the accumulated verification counts.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the 2026-11-23 entry.
- [STATUS.md](../STATUS.md) — current focus, recent updates, and verification snapshot revised.
- [traceability/code-map.md](../traceability/code-map.md) and
  [change-impact-map.md](../traceability/change-impact-map.md) — linked the menu, battery-fade,
  and nav-capsule behaviors with sources, evidence, and fallback boundaries.
- [REGISTRY.yml](../REGISTRY.yml) — source paths for touched technical records refreshed if needed.

Summary: Automatic post-implementation synchronization after three user-requested visual changes:
liquid QMenu items in white with the shared black stroke over the original light glass, a soft
fade at the battery page's scroll bottom, and a navigation capsule hugging the first tab and last
button. A dark menu overlay was implemented then removed at the user's explicit direction, so the
original light glass is preserved. Two independent QA runs passed (49/49 menu logic, battery fade
ARGB32 render), both offscreen/logic-level rather than real-FPS measurements; reference-machine
FPS, optical, and interaction checks remain explicitly pending. No requirement IDs or unsupported
performance claims introduced. The `grab()`-returns-opaque-RGB32 caveat is recorded so future
alpha checks use `render()` into an ARGB32 image.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-002 | React-style RGB dispersion, page card inset, liquid shadow removal synchronized

Changed:

- [technical/architecture.md](../technical/architecture.md) — optical model now documents
  React-demo-style edge-only RGB dispersion (`split = dispersion * circleMap`, default 0.16,
  R/B +/-16%, clean center, G supplies alpha, three `sampleTiny` calls), `amplitude` 0.95, the
  final `min(rgb, a)` premultiplied clamp, the removed liquid three-layer outer shadow, and the
  `PAGE_CARD_INSET = 8` page inset (+16 px panel height, unchanged usable content).
- [technical/codebase-map.md](../technical/codebase-map.md) — recorded the new shared-shader
  dispersion uniforms across both render paths, the `gpu_glass.py` fallback boundary, the island
  shadow guard and page-card inset, and revised the optical invariants: center must stay clean,
  edge dispersion allowed via `dispersion * circleMap`, `dispersion = 0` must restore colorless,
  premultiplied RGB <= alpha still required.
- [technical/testing.md](../technical/testing.md) — superseded the "no colored fringe anywhere"
  acceptance rule with "clean center + intentional edge dispersion + legal premultiplied"; added
  the 15/15 layout and 30/30 dispersion independent QA sections, the real GL 3.3 compile result,
  the `hiTex`/edge-light observations, and the live-path check.
- [implementation/current-plan.md](../implementation/current-plan.md) — appended the three
  completed 2026-11-23 changes and the accumulated verification counts.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the 2026-11-23 dispersion/inset/shadow
  entry.
- [STATUS.md](../STATUS.md) — current focus, recent updates, verification snapshot, and
  non-blocking observations revised.
- [traceability/change-impact-map.md](../traceability/change-impact-map.md) — updated shader and
  native-renderer regression rows, added the island shadow/inset row, and clarified the dispersion
  and page-inset boundaries.
- [REGISTRY.yml](../REGISTRY.yml) — updated timestamp refreshed to 2026-11-23; source paths already
  cover all touched files.
- [PROJECT.md](../PROJECT.md), [implementation/current-plan.md](../implementation/current-plan.md),
  [technical/testing.md](../technical/testing.md) — frontmatter `source_paths` reconciled with
  the REGISTRY (an earlier-session drift that made structural validation fail); W48 log
  frontmatter removed to match the plain-Markdown audit-log format. Structural validation now
  passes 0 errors / 0 warnings.

Summary: Automatic post-implementation synchronization after the user chose the React
`liquid-glass-react` demo look over the previous single-channel ring. The user first asked whether
the outer ring could be removed, then selected "switch to the demo look"; when told that demo uses
stronger refraction plus RGB chromatic aberration (and would break the "no color fringe"
invariant), the user reaffirmed "demo strong refraction + chromatic aberration". The clean-center
invariant and premultiplied legality are preserved; only the edge is allowed to fringe, and
`dispersion = 0` remains an off switch. Two independent QA runs passed (15/15 layout, 30/30
dispersion), the latter including a real GL 3.3 compile/link on the RTX 3060 machine; both are
logic/numeric/hardware-compile level, not real-FPS measurements. The outer three-layer soft
shadow was removed for the liquid theme only, and all expanded pages were inset 8 px inside the
outer glass. No requirement IDs or unsupported performance claims introduced. Real-machine
appearance and native `frameSwapped` FPS after two extra samples remain explicitly pending.

Questions: No new open questions (two non-blocking observations recorded in testing.md).
Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-003 | Edge-hugging refraction band and vivid interior synchronized

Changed:

- [technical/architecture.md](../technical/architecture.md) — optical model now records the
  edge-anchored band (`band`/`circleMap` at sd=0), the fixed logical-pixel `thickness` cap
  replacing the size-relative width, `amplitude = 1.2`, the demo-verified interior (Rec.709
  saturation 1.5, `tinyTexel * 0.8`, edge light 0.12), the two-sided premultiplied clamp, and the
  WebGL/AGSL demo reference from `web-prototype/assets/lib-check.js`.
- [technical/codebase-map.md](../technical/codebase-map.md) — shared-shader description updated
  with the fixed band cap, vivid interior, and `max`/`min` clamp; invariants gained two entries
  (keep 0 <= RGB <= alpha, keep the band anchored at the boundary with a fixed cap).
- [technical/testing.md](../technical/testing.md) — added the 35/35 independent QA section:
  edge-anchoring circleMap sweep, fixed-cap table (12/6/2 px), saturate 1.5 color math, negative
  channel finding and `max`/`min` repair, 28-tap sample budget, both-path uniform parity, and real
  GL 3.3 compile result.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the 2026-11-23 edge-band/vivid-interior
  entry.
- [STATUS.md](../STATUS.md) — focus, recent updates, verification snapshot, and non-blocking
  observations revised (small-island ~3.8x displacement flagged).
- [traceability/change-impact-map.md](../traceability/change-impact-map.md) — shader and native
  renderer regression rows updated with the band cap, vivid interior, and two-sided clamp.
- [implementation/current-plan.md](../implementation/current-plan.md) — appended the change and
  the accumulated 35/35 verification count.

Summary: Automatic post-implementation synchronization after the user asked for the refraction
band to sit on the island edge rather than read as an outer ring, with the interior using the
demo's approach. The demo reference was verified in the local WebGL/AGSL port (fixed 12dp
refraction height, saturation 1.5, 2dp blur, SDF early-exit) — it is not SVG filters. One
independent QA run passed 35/35 static/numeric assertions plus a real GL 3.3 compile; checks are
logic/numeric/hardware-compile level, not real-FPS measurements. QA found saturate can produce
negative channels; the engineer added a `max(rgb, 0)` clamp before the existing `min(rgb, a)` and
corrected the comment, re-verified. The small-island band's displacement rose from ~1.9 to ~7.2
px (~3.8x) as a side effect of the fixed-band formula; flagged for real-machine review, not a
blocker. No requirement IDs or unsupported performance claims introduced. Real-machine edge-band
width, interior vividness, small-island appearance, and native `frameSwapped` FPS remain pending.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-004 | Demo-level center blur via hiTex mipmap synchronized

Changed:

- [technical/architecture.md](../technical/architecture.md) — optical model now records the demo-level
  center blur: `CENTER_BLUR_SIGMA = 9.0`, `center_blur_lod()` from measured texel density clamped
  [0,8], `blurredCenter()` three adjacent-mip `textureLod` samples of the revived `hiTex`, and
  the 28 -> 6 sample reduction replacing the 25-tap Gaussian.
- [technical/codebase-map.md](../technical/codebase-map.md) — `gpu_widget.py` / `gpu_window.py` notes
  updated with the center mip material, shared LOD helper, `hi`-only mipmap filtering, and that
  `GlassGLWidget` is not the instantiated path.
- [technical/testing.md](../technical/testing.md) — added the 9/9 independent QA section: render-level FBO
  checkerboard std 111.56 -> 3.61, step-edge sigma 9.75/11.31 px, `hiTex` active, all mips
  complete, 31/31 edge-no-regression, LOD recompute, and the per-frame `generateMipmap` risk.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the 2026-11-23 center-blur entry.
- [STATUS.md](../STATUS.md) — focus, recent updates, verification snapshot, and non-blocking
  observations revised; corrected a stale `amplitude = 0.95` to 1.2.
- [traceability/change-impact-map.md](../traceability/change-impact-map.md) — shader/native rows
  updated with the center mip blur, 6-tap budget, `centerBlurLod` parity, and mip-completeness
  boundary; `generateMipmap` cost added to the native renderer row.
- [implementation/current-plan.md](../implementation/current-plan.md) — appended the change and
  the accumulated 9/9 count plus the pending `generateMipmap` recheck.

Summary: Automatic post-implementation synchronization after the user said the center blur was
still weaker than the demo. Diagnosis: liquid mode skips CPU `_blur` and the only center blur was
a ~1-2 px 5x5 Gaussian, versus the demo dialog's ~9.7 px. The fix revived the previously dead
`hiTex` (uploaded but never sampled) as the center source, taking three adjacent-mip `textureLod`
samples with a shared density-derived LOD; the 25-tap Gaussian and `tinyTexel` were removed and
total samples fell 28 -> 6. Edge refraction was left byte-for-byte intact. One independent QA run
passed 9/9 checks with a real FBO render proving the center std fell 96.8% and sigma reached
~9.75 px, plus a real GL 3.3 compile and 31/31 edge-no-regression. A performance microbenchmark
flagged the new per-frame `generateMipmap` at ~0.52 ms median / 1.46 ms p95 against a ~90.2 fps
baseline with little headroom; this is a risk requiring a real-machine `frameSwapped` recheck,
not a confirmed regression. No requirement IDs or unsupported performance claims introduced.
Real-machine blur appearance, edge stability, and native FPS remain explicitly pending.

Questions: No new open questions (four non-blocking observations recorded in testing.md).
Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-005 | Demo-faithful two-pass Gaussian center blur synchronized

Changed:

- [technical/architecture.md](../technical/architecture.md) — optical model now records the
  demo-dialog blur pipeline: `SeparableBlur` two-pass Gaussian FBO (33 taps, ±3σ), `blurredTex`
  shared by base + dispersion, `center_blur_sigma()`, removal of mip/`tinyTex`/`generateMipmap`,
  and the demo's dialog tier (`dialogBlurRadius` 16dp/8dp, colorControls-before-blur).
- [technical/codebase-map.md](../technical/codebase-map.md) — `gpu_widget.py` / `gpu_window.py`
  notes updated with `SeparableBlur`, the generated kernel, 6 -> 4 uniform samples, and that both
  GL paths share the blur class.
- [technical/testing.md](../technical/testing.md) — added the Gaussian QA section (kernel weights
  sum 1 over ±3σ, 33 generated taps, end-to-end 0/255-to-37-level FBO render, GL 3.3 compile,
  demo dialog reference, removed `generateMipmap` risk), superseding the mip-specific checks.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the 2026-11-23 two-pass Gaussian entry.
- [STATUS.md](../STATUS.md) — focus, recent updates, and observations revised; the mipmap
  performance risk marked resolved.
- [traceability/change-impact-map.md](../traceability/change-impact-map.md) — shader and native
  rows updated with the Gaussian FBO, shared `center_blur_sigma()` / `SeparableBlur`, 4-tap budget,
  and FBO state-restore boundary.
- [implementation/current-plan.md](../implementation/current-plan.md) — recorded the mip -> Gaussian
  replacement and removed the pending `generateMipmap` cost.

Summary: Automatic post-implementation synchronization after the user said the three-mip center
blur was "not delicate enough" and wanted the demo's blur. Diagnosis of `lib-check.js` showed the
demo dialog does not stack mips: it pre-blurs the backdrop with a two-pass separable Gaussian FBO
(`separable-blur.ts`, 33 taps, ±3σ, colorControls before blur) and samples that single blurred FBO
for base and all dispersion paths. Replaced `blurredCenter()`/`sampleTiny()` and `center_blur_lod()`
with `SeparableBlur` (two FBOs/textures, H then V passes) and `center_blur_sigma()`, moved the
lens to `sampleBg(blurredTex)` for base + three channels, and removed `hiTex`/`tinyTex`/mip
filtering/per-frame `generateMipmap`. Uniform samples fell 6 -> 4. Verification: kernel weights
sum 1 over ±3σ, an end-to-end FBO render of a 0/255 checkerboard yielded 37 distinct levels, and
both shaders compiled under real GL 3.3 (NVIDIA 621.24). The flagged ~0.52 ms mipmap risk is
resolved; real-machine blur appearance, two-pass cost, and native FPS remain pending. No
requirement IDs or new open questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-006 | Background Gaussian blur removed synchronized

Changed:

- [technical/architecture.md](../technical/architecture.md) — optical model now records that the
  background Gaussian blur was removed: `sampleBg()` reads the clear `bgTex` for base + dispersion,
  `SeparableBlur` / `center_blur_sigma()` / blur shader and uniforms deleted, demo dialog tier kept
  as reference only.
- [technical/codebase-map.md](../technical/codebase-map.md) — `gpu_widget.py` / `gpu_window.py`
  notes updated: center is clear `hi` upload, blur classes/shaders gone, both paths share
  `_FRAGMENT`.
- [technical/testing.md](../technical/testing.md) — added the clear-background QA section (zero
  blur refs, GL 3.3 compile with 15 active uniforms and no blur uniforms, 0/255-to-0/255 render
  proof), superseding all mip/Gaussian blur checks.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the 2026-11-23 blur-removal entry.
- [STATUS.md](../STATUS.md) — focus, recent updates, and observations revised; all blur
  performance risks marked moot.
- [traceability/change-impact-map.md](../traceability/change-impact-map.md) — shader/native rows
  updated with clear `bgTex`, 4-tap budget, and no-blur boundary.
- [implementation/current-plan.md](../implementation/current-plan.md) — recorded the blur removal
  and that all blur performance risks are moot.

Summary: Automatic post-implementation synchronization after the user asked to remove the
background Gaussian blur. Deleted the entire two-pass `SeparableBlur` FBO pipeline from both GL
paths (class, blur shader, `center_blur_sigma()` / `CENTER_BLUR_SIGMA`, `blurredTex` uniform, all
blur uniforms/states). The lens `sampleBg()` now reads the clear full-resolution `hi` upload
(`bgTex`) for the base and all three RGB dispersion channels; `hi` is uploaded once as `bg` and
bound directly, with no mip/25-tap/Gaussian pass. Edge refraction, saturation 1.5, edge light, and
all optical parameters are untouched. Verification: zero residual blur references in source,
GL 3.3 compile with 15 active uniforms (no blur uniforms), and an end-to-end render where an
0/255 checker through the pure-base lens stayed 0/255 (only bilinear 127 at boundaries) — proving
a clear, unblurred background. All center-blur performance risks are moot; real-machine clarity
and native FPS remain pending. No requirement IDs or new open questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-007 | Topmost Finder-bar click blocking fixed

Changed:

- [technical/architecture.md](../technical/architecture.md) — documented the MyDockFinder
  topmost-window race: `_poll_hover()` re-raises on cursor entry and physical hit-test misses,
  `_raise_topmost()` uses `SetWindowPos` with 64-bit `HWND_TOPMOST` and `SWP_NOACTIVATE`, and
  `_covered()` uses physical `GetCursorPos` pixels because Qt coordinates mis-hit at DPI > 1.
- [technical/codebase-map.md](../technical/codebase-map.md) — expanded the `_poll_hover()` entry
  with the z-order guard, Win32 signatures, DPR-safe hit test, and raise throttles.
- [technical/testing.md](../technical/testing.md) — added the root cause (bare `-1` truncated to
  32-bit invalid handle) and the two-topmost-window hit-test proof: island wins every raise cycle,
  `WS_EX_TOPMOST` set, foreground unchanged, `_covered()` correct at DPR 1.5.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the 2026-11-23 click-blocking fix entry.
- [STATUS.md](../STATUS.md) — recent update, observation, and pending real-machine confirmation.
- [traceability/change-impact-map.md](../traceability/change-impact-map.md) — new `island.py`
  z-order/hit-testing row with silent-failure and DPI boundary conditions.
- [implementation/current-plan.md](../implementation/current-plan.md) — recorded the fix and the
  pending MyDockFinder confirmation.

Summary: Automatic post-implementation synchronization after the user reported that hovering the
island then clicking did nothing when the MyDockFinder bar was on top. Fixed the silent failure:
`HWND_TOPMOST` is now the 64-bit `(HWND)-1`, the z-order Win32 calls declare explicit `HWND`
signatures, `_covered()` uses physical `GetCursorPos` coordinates for `WindowFromPoint`, and
`_poll_hover()` raises on cursor entry plus 0.15 s / 0.3 s hit-test throttles. Verified with a real
two-topmost-window test (island returns to the top of the hit test on every cycle) and a DPR 1.5
hit-test check; real MyDockFinder confirmation remains pending. No requirement IDs or new open
questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-008 | Refraction band aligned to body and widened

Changed:

- [technical/architecture.md](../technical/architecture.md) — optical model now builds the SDF
  from `island.body` (not the neck-widened `path.boundingRect()`) so all four band edges pin to
  the border; band decay uses a separate `bandWidth` (2.4× thickness, cap 30 px) while peak
  displacement keeps the fixed `thickness` cap.
- [technical/codebase-map.md](../technical/codebase-map.md) — recorded the body-based SDF, the
  new `bandWidth`, and the do-not-revert note about the ~13 px neck overhang.
- [technical/testing.md](../technical/testing.md) — added the shape.py overhang measurement
  (640 → 666 px), the exact body match, and the bandWidth scaling / GL 3.3 verification.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the 2026-11-23 alignment entry.
- [STATUS.md](../STATUS.md) — recent wiki updates.
- [traceability/change-impact-map.md](../traceability/change-impact-map.md) — shader row revised
  and a new SDF-geometry-source row added.
- [implementation/current-plan.md](../implementation/current-plan.md) — recorded the fix and the
  pending real-machine look.

Summary: Automatic post-implementation synchronization after the user reported that top/bottom
refraction bands aligned with the border but left/right overhung, and asked that all four sides
align while the band widens inward. Root cause: the SDF used `path.boundingRect()`, widened ~13 px
per side by the anchored liquid bridge (measured 640 → 666 px, only ~1.5 px vertical overhang).
Both GL paths now build the SDF from `island.body`, pinning the outer edge to the border on all
four sides, and a new `bandWidth = min(30, max(6, thickness*2.4))` widens the band inward (12 →
28.8 px expanded) without changing peak displacement. Verified by py_compile, a real GL 3.3
compile with `bandWidth` active (16 uniforms), and geometry/bandWidth measurements; real-machine
appearance remains pending. No requirement IDs or new open questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-009 | Inward refraction band widened 1.5×; color-fringe explained

Changed:

- [technical/architecture.md](../technical/architecture.md) — `bandWidth` current state is
  `min(45.0, max(9.0, thickness*3.6))` (43.2 px expanded / 10.8 px small, 1.5× the former 2.4);
  corrected a stale "pre-blurred background" phrase to "clear background" in the dispersion
  paragraph, since the Gaussian blur was removed.
- [technical/codebase-map.md](../technical/codebase-map.md) — updated the `bandWidth` formula and
  spread values.
- [technical/testing.md](../technical/testing.md) — added a QA note for the 1.5× widening and the
  color-fringe explanation grounded in the shader's `split = dispersion * circleMap`.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the 2026-11-23 widening entry.
- [STATUS.md](../STATUS.md) — recent wiki update recorded.
- [implementation/current-plan.md](../implementation/current-plan.md) — recorded the widening and
  pending real-machine look.
- [traceability/change-impact-map.md](../traceability/change-impact-map.md) — revised the header
  date and the shader row's bandWidth values.

Summary: Automatic post-implementation synchronization after the user asked to widen the inward
refraction band by another half and asked why the refraction is colored. Both GL paths now use
`bandWidth = min(45, max(9, thickness*3.6))` (exactly 1.5× the previous 2.4×, cap 30 → 45);
expanded island 28.8 → 43.2 px, small 7.2 → 10.8 px. Peak displacement (`thickness`/`amplitude`)
and `dispersion = 0.16` unchanged. The color is the intentional demo-following edge-only RGB
dispersion (`split = dispersion * circleMap`, R/B ±16%, center fringe-free, `dispersion = 0`
restores colorless); explained, no code change. Verified by py_compile and a numeric 1.5× scaling
check at three shape sizes; real-machine appearance remains pending. No requirement IDs or new
open questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-010 | Edge color dispersion turned off (colorless ring)

Changed:

- [technical/architecture.md](../technical/architecture.md) — current state is `dispersion = 0`
  (colorless ring at the user's request); the earlier demo-style 0.16 color fringe is recorded as
  history, and the channel-split shader is described as retained but inert.
- [technical/codebase-map.md](../technical/codebase-map.md) — not changed (no dispersion value in
  the current-state bullets; the shader structure description remains accurate).
- [technical/testing.md](../technical/testing.md) — added the end-to-end gray-gradient render proof
  (0.16 → 1118 color-fringe pixels, 0 → 0) and the note about the invalid first test background.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the colorless-ring entry.
- [STATUS.md](../STATUS.md) — current-feature description and recent wiki update revised.
- [implementation/current-plan.md](../implementation/current-plan.md) — recorded the change and
  the render proof.
- [traceability/change-impact-map.md](../traceability/change-impact-map.md) — header and shader row
  revised to the colorless current state.

Summary: Automatic post-implementation synchronization after the user said "I don't need color".
Both GL paths set `dispersion = 0` (was 0.16), so `split = 0` and R/B sample at the same
displacement as G — the refraction ring is colorless again. The three-channel shader is retained
but inert (reversible). `thickness`/`bandWidth`/`amplitude` untouched. Verified by py_compile and
an end-to-end GL 3.3 gray-gradient render: 0.16 gave 1118 pixels with |R-B|>3 while 0 gave 0 with
max|R-B|=0. Real-machine appearance remains pending. No requirement IDs or new open questions.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-011 | Golden-angle disc gaussian center blur restored

Changed:

- [technical/architecture.md](../technical/architecture.md) — center material is now the demo's
  16-tap golden-angle disc gaussian (`blurBg`, `CENTER_BLUR_RADIUS=9×dpr`), replacing the fully
  clear center; documented the `generateGaussianDisc` formula and center-only blurring.
- [technical/codebase-map.md](../technical/codebase-map.md) — recorded `_make_blur_gather()`, the
  tap formula, `blurRadiusPx`, and that `gpu_window.py` imports the shared `_FRAGMENT`.
- [technical/testing.md](../technical/testing.md) — added the weight-normalization, GL 3.3
  compile, and end-to-end checker-std proof.
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the golden-angle blur entry.
- [STATUS.md](../STATUS.md) — current-feature description, recent update, and blocker note revised
  (single-pass gather, no FBO/mip cost).
- [traceability/change-impact-map.md](../traceability/change-impact-map.md) — header and shader row
  revised; noted blur must stay center-only.
- [implementation/current-plan.md](../implementation/current-plan.md) — recorded the restored blur.

Summary: Automatic post-implementation synchronization after the user asked to re-add the earlier
5x5 gaussian and, offered 5x5 / golden-angle / two-pass, chose the golden-angle option as more
delicate. Implemented `liquid-glass-react`'s `generateGaussianDisc()` as a Python-generated 16-tap
golden-spiral gather (`_make_blur_gather` → `blurBg` in the shared `_FRAGMENT`), radius 9 logical
px × dpr, applied only to the center `base` while refraction stays clear. No mip or FBO pipeline.
Verified: 16 weights sum to 1.0, GL 3.3 compile (17 uniforms, `blurRadiusPx` active), and an
end-to-end checker render with center std 119.81 → 27.08 and gray levels 3 → 16 when blurred.
Real-machine appearance pending. No requirement IDs or new open questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-012 | 2-pass Gaussian replaces ghosting golden-angle disc

Changed:

- [technical/architecture.md](../technical/architecture.md) — center blur current state is the
  2-pass separable Gaussian FBO (`SeparableBlur`, 33-tap ±3σ); documented why the golden-angle disc
  was rejected (discrete taps ghosting on high-contrast text) and the two-sampler lens design.
- [technical/codebase-map.md](../technical/codebase-map.md) — `SeparableBlur` class, kernel,
  `center_blur_sigma` density conversion, and shared import path recorded; golden-angle removed.
- [technical/testing.md](../technical/testing.md) — added the ghosting root cause and the
  4px-stripe end-to-end render proof (0/255 → 125-130, no copies).
- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the 2-pass replacement entry.
- [STATUS.md](../STATUS.md) — current-feature, recent update, and FPS-risk note revised.
- [traceability/change-impact-map.md](../traceability/change-impact-map.md) — header, shader row,
  and do-not-revert note revised (sparse single-pass blur must not return).
- [implementation/current-plan.md](../implementation/current-plan.md) — recorded the replacement.

Summary: Automatic post-implementation synchronization after the user sent two real-machine
screenshots reporting "全重影" and asking for the demo's very delicate blur. Root cause: the
16-tap golden-angle disc was a sparse single-pass sampler, so on high-contrast browser text each
tap sampled a shifted glyph copy. Replaced with `SeparableBlur` — the demo dialog's real 2-pass
separable Gaussian FBO (33-tap ±3σ, H then V), a continuous gaussian with no discrete copies.
`CENTER_BLUR_SIGMA = 9` logical px converted by measured texel density; only center `base` is
blurred while refraction stays clear; dispersion 0 / bandWidth 3.6× / body SDF unchanged. Verified:
33 weights sum 1.0, GL 3.3 compile (LENS 17 / BLUR 4 uniforms), end-to-end stripe render collapsing
0/255 to 125-130 with no surviving peaks. Real-machine look and two-pass FPS cost pending. No
requirement IDs or new open questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-013 | Submenu Z-order fix and control-page column swap synchronized

Changed:

- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the submenu-raise bug fix and the
  control-page column swap entry.
- [STATUS.md](../STATUS.md) — recent-updates bullet records both fixes and their verification.

Summary: Automatic post-implementation synchronization after the user reported that a second-level
menu touching a first-level button revealed the button through it, and asked to swap the control
page's right-side tile buttons with its left-side sliders at equal height. Root cause of the first
bug: `Island._poll_hover`'s hit-test auto-raise (`_raise_topmost`) ran while a submenu was open,
pulling the island in front of its own popup so the first-level buttons showed through. Added
`Island._popup_open()` (active popup widget + visible QMenu/CCPanel/LookupPopup) and guarded
`_raise_topmost()` to no-op while such a layer is visible. For the layout, the 2×2 tile grid now
sits on the LEFT and the three sliders on the RIGHT, both pinned to `TILE*2+15` (251 px) for equal
height. Verified with py_compile and offscreen assertions (popup detection, grid/slider order,
equal 251 px height). Real-machine Z-order and layout confirmation pending. No requirement IDs or
new open questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-014 | Full-island clear refraction synchronized

Changed:

- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the full-island clear-refraction entry.
- [STATUS.md](../STATUS.md) — recent-updates bullet records the clarity/refractSpan change.
- [technical/testing.md](../technical/testing.md) — added the GL 3.3 compile and end-to-end FBO
  render evidence (clarity contrast, displacement reach, colorless check).

Summary: Automatic post-implementation synchronization after the user asked whether the
refraction band could cover the whole island, chose "全岛清晰折射" over keeping the center blur,
and asked for the matte gaussian look to be more transparent. The shared `_FRAGMENT` now uses two
new uniforms: `clarity=1` makes the whole island sample the clear background (no center gaussian
matte), and `refractSpan=min(hw,hh)` extends the displacement field from the edge to the center.
`bandWidth` is now edge-light-only; dispersion stays 0. Verified by py_compile, GL 3.3 compile
(19 active uniforms), and an FBO render (center contrast 3.54→120.27, edge-only span 0/5120 vs
full span 433/5120 center pixels, |R-B|=0). Real-machine appearance and FPS pending. No
requirement IDs or new open questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-015 | Radial displacement field replaces shallow circleMap

Changed:

- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the radial-field fix entry.
- [STATUS.md](../STATUS.md) — current-focus and recent-updates describe the normalized radial
  field (`refractSpan=0.45`) replacing `circleMap`.
- [technical/testing.md](../technical/testing.md) — added the numeric audit, GL 3.3 compile and
  60.9% center-region FBO A/B evidence.

Summary: Automatic post-implementation synchronization after the user reported that refraction was
still only at the outermost rim despite the earlier full-island change. Numeric audit with the real
path parameters (half-size 200x40, span=`min(hw,hh)=40`) showed the old `circleMap=1-sqrt(1-t²)`
gave 0.00 px center / 0.66 px mid-island displacement — the prior verification had wrongly used
span=120. Replaced it in the shared `_FRAGMENT` with a normalized radial field: `pn=p/halfSize`,
`radialDir=normalize(pn)`, `reach=smoothstep(0,0.45,length(pn))`, displacement
`thickness*amplitude*reach*0.7`; both GL paths now feed `refractSpan=0.45`. `gradient` retained
for edge light only; clarity=1, dispersion=0, premultiply unchanged. Verified by py_compile, real
GL 3.3 compile (19 active uniforms) and an offscreen FBO render at real island size (60.9% of
center-region pixels changed; whole-island warping visible in A/B images). Real-machine look
pending. No requirement IDs or new open questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-016 | Layered optics restored: rim refraction + center 5x5

Changed:

- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the layered-optics restoration entry.
- [STATUS.md](../STATUS.md) — current-focus and recent-updates now describe rim refraction with a
  transparent 5x5 center gaussian.
- [technical/testing.md](../technical/testing.md) — added pulse-test and end-to-end FBO evidence.

Summary: Automatic post-implementation synchronization after the user asked to restore the earlier
rim distortion and add a transparent 5x5 gaussian blur to the center. The shared `_FRAGMENT`
returned to the layered architecture (circleMap rim band, gradient displacement,
coverage=circleMap*ringFade mixing blurred center with refracted rim); the full-island uniforms
`clarity` and `refractSpan` were removed. The center blur kernel became a 5-tap separable gaussian
with integer offsets and sigma 1.0 weights, fed a 1-logical-px texel step via the renamed
`center_blur_radius()`. Verified with py_compile, real GL 3.3 compile (17 active uniforms), a
two-pass pulse test (peak 41, 3 px spread vs 29 px sigma-9 reference) and an end-to-end FBO render
(center contrast 72.3, rim 75.4% pixels distorted, |R-B|=0). Real-machine appearance pending. No
requirement IDs or new open questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-017 | Nav bar text PingFang white + black outline

Changed:

- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the nav-bar text outline entry.
- [STATUS.md](../STATUS.md) — recent-updates bullet records the outline change and evidence.
- [technical/testing.md](../technical/testing.md) — added font/color/outline verification details.

Summary: Automatic post-implementation synchronization after the user asked for the nav-bar font
to also be PingFang white with a black outline. Font family and color were already correct
(`ui_font` resolves PingFang SC first under the liquid theme; `pill_text`/`text` are white), so
the real gap was the outline: the `NavBar.paintEvent` tab label was drawn with a bare drawText
and now goes through `theme.outlined_text`; the `_TabGhost` active-tab outline exemption was
removed. Icon glyphs stay unoutlined on `icon_font` per convention. Verified with py_compile,
offscreen pixel counts (448 vs 0 stroke pixels on/off; real NavBar 128 outline + 531 white text
pixels) and a source audit (exactly 2 outlined_text calls, no exemption). Real-machine look
pending. No requirement IDs or new open questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-018 | Nav bar inverts on light backgrounds

Changed:

- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the luminance-adaptive nav entry.
- [STATUS.md](../STATUS.md) — recent-updates bullet describes the inversion and its plumbing.
- [technical/testing.md](../technical/testing.md) — added the sampling, hysteresis and pixel
  A/B evidence.

Summary: Automatic post-implementation synchronization after the user asked how to fix the nav
bar visually disappearing on an all-white page. Diagnosis: white body text plus a 1px black
outline is 1:1 with a white background (hollow glyphs), and the white icons, translucent active
pill and white hover ring fade out identically; deepening the outline cannot help. Implemented a
nav-scoped luminance-adaptive inversion: `NavBar._bg_luminance()` averages the capsule area from
the island's existing `backdrop.hi` snapshot at 1x1 (cached on `backdrop.version`),
`_refresh_light()` flips at 0.58/0.46 with hysteresis in the liquid theme only, and the light
state uses `LIGHT_INK (24,26,32)` with a white stroke (`outlined_text(edge=...)`, shadow at 1/3),
a dark active chip and a dark hover ring. `theme.glass_ink()`, `IconButton.on_light`,
`_TabGhost.on_light` and `Island._on_backdrop → nav.refresh_light()` propagate the state, the
last one so a wallpaper/page change re-evaluates without a manual repaint. Verified by
py_compile and offscreen renders (mirrored 96/96 body pixels white vs dark, stable hysteresis
across 120..170, ghost and edge A/B, idempotent refresh). Real-machine look pending. No
requirement IDs or new open questions introduced.

Questions: No new open questions. Alerts: None captured.

## [2026-11-23] update | WLOG-20261123-019 | Rim displacement taper + 50% stronger center blur

Changed:

- [changes/CHANGELOG.md](../changes/CHANGELOG.md) — added the rim-taper and blur-increase entry.
- [STATUS.md](../STATUS.md) — current-focus and recent-updates describe `dispEase`, σ=1.5 and the
  ±3 px footprint.
- [technical/testing.md](../technical/testing.md) — added the coverage measurement, rim diff and
  pulse-spread evidence.

Summary: Automatic post-implementation synchronization after the user reported the refraction band
appearing to spill past the island body's bottom rim and asked for the body blur to be 50%
stronger. Measurement at real island size showed the SDF coverage was already exact (0 alpha
pixels outside all four edges, edge row = antialiasing only), so the spill was displacement
warping texels right up to the rim. `displacement` is now multiplied by
`dispEase = smoothstep(0.0, 8.0, -sd)`, tapering to zero over the outermost 8 px with zero slope;
`coverage` still uses `circleMap`, so the rim stays clear. Blur: `_GAUSSIAN_SIGMA` 1.0 → 1.5 and
the new `_GAUSSIAN_STEP` 1.0 → 1.5 scale together (5-tap footprint ±2 → ±3 px), since sigma alone
would only flatten the weights. Verified by py_compile, GL 3.3 compile, an outermost-row
zero-diff check against the zero-displacement render, and a real two-pass pulse spread of 7 px
(was 3 px). Real-machine look pending. No requirement IDs or new open questions introduced.

Questions: No new open questions. Alerts: None captured.
