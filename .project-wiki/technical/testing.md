---
id: TECH-TESTING
type: technical
status: active
title: Testing
created: '2026-11-21'
updated: '2026-11-23'
tags:
- technical
- testing
- performance
- liquid-glass
related:
- TECH-ARCHITECTURE
- TECH-CODEBASE-MAP
source_paths:
- mybalcony/ui/glass.py
- mybalcony/ui/gpu_widget.py
- mybalcony/ui/gpu_window.py
- mybalcony/ui/gpu_glass.py
- mybalcony/ui/island.py
- mybalcony/ui/theme.py
- mybalcony/ui/liquid.py
- mybalcony/ui/lookup.py
- mybalcony/ui/compact.py
- mybalcony/ui/nav.py
- mybalcony/ui/pages/bluetooth.py
confidence: confirmed
---

# Testing

## Acceptance Rules

Liquid-glass performance claims require the complete application running in a normal
Windows graphics session. The primary performance signal is elapsed time between native
OpenGL `frameSwapped` notifications, with `paintGL` timing retained as supporting evidence.
DXCam-only FPS, background version counts, and offscreen shader benchmarks do not establish
end-to-end FPS.

Optical regressions must separately check a continuous outer ring, rounded corners, zero
central lens displacement, valid premultiplied colors (RGB <= alpha), an intentionally
dispersed edge with a clean center, and that `dispersion = 0` restores a colorless ring. The
old "absence of colored fringe" criterion is superseded: fringe at the center or caused by
premultiplied overflow is still a defect, but edge-only RGB dispersion is now expected.
Interaction tests must distinguish medium hover content from the full expanded island.

## Observed Environment

Measurements on 2026-11-22 used the user's Windows machine with a 2560x1600, 165 Hz display
and an NVIDIA GeForce RTX 3060 Laptop GPU. The test scenario was the expanded home page,
settled after its opening animation, with live DXCam background capture. Results are
specific to that environment and are not a guarantee on other hardware.

## Performance Evidence

| Implementation | Measurement | Result |
| --- | --- | --- |
| DXCam alone, 1440x720 BGRA, 90 FPS target | Five-second capture benchmark | 86.94 FPS; capture-only evidence |
| Native OpenGL background before center blur | Five-second complete-app `frameSwapped` | 90.219 FPS; `paintGL` 90.216 FPS; mean paint 4.09 ms |
| Dense 5x5 Gaussian center plus live outer refraction | Five-second complete-app `frameSwapped` | 117.045 FPS; `paintGL` 117.043 FPS; mean paint 2.89 ms |

The final Gaussian result was higher than the earlier clear-center run because the dense
sampling pattern was also more cache-friendly; these were separate chronological runs, not
an isolated Gaussian-only A/B benchmark. Do not interpret the difference as a universal
speedup from adding texture samples.

Rejected performance directions measured during diagnosis included the offscreen
readback/QPainter round trip (about 26-26.7 FPS), direct `QOpenGLWidget` top-level
composition (about 23 FPS), a single native scheduler (72.26 FPS), and a 10 ms native
schedule (79.92 FPS). These figures explain the architecture choice but are not the current
performance baseline.

## Optical Evidence

- CPU regression checks reported zero outside-island pollution, zero central-channel
  difference for the clear-center optical baseline, and zero premultiplied-color overflow.
- The offscreen GPU/CPU comparison passed after aligning GPU fragment centers with CPU
  integer-pixel coordinates; mean RGBA absolute differences were below 0.031/255.
- The earlier 3x3 center blur used sparse offsets and was rejected from actual appearance
  feedback as ghosting. The active dense 5x5 kernel uses normalized separable weights and
  1.25-texel spacing. Outer-ring sampling was not changed by this blur fix.

## Interaction Evidence

A timed interaction smoke test drove `_poll_hover()` with an inside cursor and controlled
hover timestamps, then exercised the normal click expansion method. All three checks
passed on 2026-11-22:

- At 4.8 seconds, medium content was open and the large island remained collapsed.
- At 5.1 seconds, the large island expanded.
- A normal single click expanded the large island immediately.

This was a logic-level timed regression, not a physical mouse automation test.

## Static And Lifecycle Checks

`py_compile` passed for the modified shader/window files and Island integration. Native
startup, page lifecycle, capture exclusion, and normal-process launch were exercised.
Performance scripts temporarily pin and expand the island; `hover` / unpinned configuration
is restored before the normal `run.pyw` process is launched.

## 2026-11-22 Small/Medium GPU Fast-Path And Theme Verification

The migrated small/medium GPU fast path and the liquid-theme white PingFang text were verified
by importing the production `island.py` methods onto a stub receiver and mocking only external
dependencies (theme, cfg, cursor, timer, springs, backdrop). This exercises real production
branches rather than a logic re-implementation. Result: 67/67 assertions passed, routing
`NoOne`; no source bug found. Four early failures were test-harness defects and were fixed by
QA before the passing run.

- `_gpu_active()` gate returned the expected value across 9 cases (non-liquid, no native GPU,
  invisible window, drag, snap, fullscreen-hide, hidden window, all-true).
- Expanded settled frame: one `gpu_view.update()`, an 11 ms interval, and no spring/geometry/
  layout recomputation.
- Small/medium settled frame: 6 ticks produced 4 GPU-only frames and 2 full frames; `look`/`near`
  refreshed twice so breathing/shimmer/expression are not starved; `_fast_skip` returned to 0.
- `compact.busy()`, near-cursor (`body`-relative 96 px), and non-rest poke/lift/tilt each forced
  a full frame. Timer pacing was 11 ms (GPU idle), 16 ms (GPU busy / CPU busy), and 33 ms
  (CPU idle). Capture interval was 1/90 for expanded or GPU-active collapsed states, 1/12 for
  non-GPU/non-liquid, and 1/40 while dragging.
- AST comparison of `_poll_hover`, `_single_click`, `paintEvent`, `_paint_glass`, drag, and
  backdrop handlers against HEAD showed no changes; shader/native-window/capture-exclusion
  files were untouched.
- Theme smoke check: liquid text `(255,255,255,255)`, `ui_font(13)` families begin with
  `PingFang SC`, `icon_font()` unchanged, menu foreground still `#0d1219`, and switching to
  `light` restored original font families and text color.
- `py_compile` and `git diff --check` passed for all modified source files.

Real-FPS, optical, and physical-interaction verification for these changes was **not** possible
in the test environment (no RTX 3060 / 165 Hz normal graphics session). The complete-app native
`frameSwapped` benchmark, four optical invariants, timed hover, drag/CPU fallback, and the
visual smoothness of the 2/3 lightweight-frame cadence remain to be re-run by the user on the
reference machine.

## 2026-11-22 Foreground Accents And Lyric Repaint Verification

The expanded GPU foreground accents and the shape-invariant foreground repaint fix were
verified with the same production-method + mock approach (real unbound `Island` methods on a
stub receiver). Result: 69/69 assertions passed, routing `NoOne`, within two rounds. Four early
failures were test-harness defects fixed by QA, not source bugs.

- `paintEvent()` invoked `_gpu_liquid_accents()` only for native GPU + visible + anchored +
  liquid + expanded; CPU/offscreen/drag/non-liquid/non-expanded paths never called it, so the
  accents and the CPU `_paint_glass()` path cannot double-draw.
- `_gpu_liquid_accents()`: one `setClipPath()`, one `dual_edge(bb, 92, 46)` at 1.3 px, one
  `paint_spec()` with the cursor-following `_spec_pt`; the point lerps toward the cursor by 0.34
  and falls back to the home point when the cursor leaves the body. All layers are white alpha
  inside the clipped path, so premultiplied RGB <= alpha holds with no fringe.
- `_update_geometry()` (real method, fixed shape `old == new`) called `self.update()` for a
  collapsed media island and not for an expanded settled island with an expired specular
  window. `_foreground_animating()` truth table covered busy, active specular, visible
  collapsed, non-liquid expired, and fullscreen-hidden cases.
- Expanded settled `_tick()` took the pure-GPU early return only when `now >= _spec_until`;
  inside the window it ran the full path so the highlight could repaint. A `not self.expanded`
  guard on the collapsed lightweight block was added after QA observed that a fast cursor exit
  (>96 px) inside the specular window otherwise downgraded the highlight return to ~30 fps.
- 2/3 collapsed throttle intact: 6 ticks gave 4 GPU-only frames and 2 full frames with `look`/
  `near` refreshed twice; early returns precede `_update_geometry()`. Timer and capture pacing
  matched the prior verification.

AST comparison of `_paint_glass`, `_paint_liquid`, `_paint_edge`, `_paint_rest`,
`_paint_foreground`, `_poll_hover`, and `_single_click` against HEAD showed byte-identical
bodies; shader/native-window/capture-exclusion files were untouched. Real-FPS, optical (edge
brightness / color fringe / outline overflow), and physical specular-follow and lyric-smoothness
checks remain for the reference machine.

## 2026-11-22 Liquid Outlined-Text Verification

`theme.outlined_text()` and its 73 body-text call sites were verified with AST scanning,
runtime spies on real Qt objects, and offscreen pixel checks. Result: 47/47 assertions passed
(42 runtime + 5 pixel), routing `NoOne`, on the first round.

- Icon glyphs (30 `drawText` sites, all `G.*` / weather glyphs) were never passed to the helper;
  body text was never left on a plain `drawText`. Light-surface foregrounds (`pill_text`,
  `on_fg`, menu QSS) stayed unstroked, both via `outline=False` and via preserved plain calls.
- A gradient `QPen` (simulating the lyric sweep) was restored object-identical for the body pass
  with `LinearGradientPattern` and width intact. Non-liquid themes took one plain `drawText`
  with zero `setPen` changes. Faded text scaled stroke/shadow alpha by `k = 0.35 + 0.65*alpha`.
- `apply_qss_text_shadow()` attached a tagged `QGraphicsDropShadowEffect` in liquid, did not
  overwrite an existing effect, and removed only its own effect on theme switch; style callbacks
  in shape widgets re-attach on switch and the helper is idempotent.
- Each liquid body text drew exactly 6 `drawText` calls (1 shadow + 4 strokes + 1 body); the
  three-line lyric loop drew 18 with no doubling. Pixel check on a grey background: non-liquid
  dark pixels 0, liquid dark pixels 924 (stroke + shadow real), white body pixels 468 in both.
- `py_compile` passed for all 13 modified UI files and `git diff --check` was clean.

One non-blocking behavior change was found and fixed: `home.py` `CoverTitle` originally drew a
4-direction glow in non-liquid themes; routing it unconditionally through the helper removed
that glow. It now uses a liquid-only branch (`theme.liquid` → helper + early return) and the
original glow block is byte-identical to HEAD for light/dark themes. Real-machine checks for
stroke sharpness on PingFang glyphs, shadow depth, `QGraphicsDropShadowEffect` on transparent
Tool windows and input widgets, theme-switch repaint, and low-end lyric FPS remain pending.

## 2026-11-23 Liquid Menu Text And Battery Bottom Fade

Liquid QMenu text was verified with 49/49 assertions (routing `NoOne`). The decisive check was
that a dressed menu with plain/submenu/disabled/checkable/icon items received **9** `CE_MenuItem`
calls in the real `_LiquidMenuStyle.drawControl` — not a placebo — while adding a `background`
rule to the QSS dropped it to **0**, confirming why the minimal color/font-only QSS is required.
`theme.outlined_text` was spied on all seven visible items with pure-white `(255,255,255,255)`
body and gray `(176,180,188,255)` for disabled, `outline=True`, PingFang SC 13 px; the base
style received `text=''` (no double draw); separators used their own branch. Pixel check on a
light `(225,232,242)` background showed 360 near-black stroke pixels adjacent to 192 white body
pixels. The dark overlay was confirmed absent (`_paint` byte-identical to HEAD, selection alpha
restored to palette value `(120,170,230,70)`). Dark/light themes showed zero proxy calls and
original QSS; five liquid↔dark round trips did not crash, and switching back re-dressed menus
with 9 proxy calls again. Real-machine checks for stroke weight, selection contrast, submenu
spacing, hot theme switch, and contrast on busy wallpapers remain pending.

The battery bottom fade was verified with real production methods (routing `NoOne`). A
methodology note matters: offscreen `host.grab()` returns opaque RGB32 (no alpha), so alpha tests
via `grab()` are invalid; using an ARGB32 QImage with `widget.render(painter, ...)` and the real
`_EdgeFade` class showed band alphas 242→13 (outside band 255), proving `DestinationOut` erases
sibling-widget pixels — the effect is real, not a placebo. `can_fade()` truth table, fade geometry
on scroll/resize, the 14 px spacer surviving `insertWidget`, mouse-event pass-through, and
`theme.changed` reconnection all passed. Real-GPU appearance (glass revealed, not desktop), fast
scroll frame stability, hot theme switch, and the `WA_TranslucentBackground` difference remain
for the reference machine.

The navigation capsule fit was checked geometrically: with `CAP_PAD = 0`, the capsule's left/right
edges coincided exactly with the leftmost tab and rightmost button (69.0 / 449.0, zero error),
no overflow. `py_compile` and `git diff --check` passed for all modified files.

## 2026-11-23 Page Card Inset And Liquid Shadow Removal

An independent QA run (fresh receiver, self-written temporary scripts, routing `NoOne`)
passed 15/15 assertions with zero failures. Two implementation-run assertions that first failed
were traced to test-harness assumptions (wrong default page; module-constant vs patched-method
inset) and corrected by QA, not source defects.

- Liquid `_content_margin()` measured 26.0 = `CARD_MARGIN 10 + CARD_INNER 8 + PAGE_CARD_INSET 8`;
  non-liquid stayed 12 (`PAD`). `_content_lay.contentsMargins()` was (26,24,26,26) top and
  (26,26,26,24) bottom, matching the `(m-2)...+m` design in `page_body_height()`.
- Three-layer outer shadow: monkeypatching `QPainter.strokePath` and filtering by pen width and
  pure-black color showed **0** liquid strokes at widths 6/12/20 and **3** non-liquid strokes at
  exactly [6,12,20]. Path was non-empty and `paintError` was None on both runs, proving the zero
  was a real guard, not an early return. No other liquid outer soft shadow was found tree-wide.
- All nine pages (home/msg/stock/weather/ctl/bat/clip/trans/blank) grew exactly +16 px in
  `expanded_size()` and all stayed below the 680 px window (largest: clip 400→494). Usable stack
  height was identical before/after inset (clip 396/396), so no content was lost.
- Seven liquid↔non-liquid round trips flipped margin (26/12) and shadow count (0/3) correctly with
  no residue or accumulation. `py_compile` passed.
- Known pre-existing observation (not introduced here): `_content_lay` spacing uses
  `NAV_GAP = 12.4` while `page_body_height()` adds 8, so stack height runs ~4 px below page
  `preferred_height()` (clip 400→396). Identical before and after this change; not a regression.

## 2026-11-23 React-Style RGB Dispersion

Two independent layers passed: the implementation run, and a fresh QA run (self-written scripts,
routing `NoOne`) that passed 30/30 assertions with zero failures.

- Real GLSL compile/link succeeded on the user-class machine in a default-platform GL 3.3 core
  context (`GL_VERSION 3.3.0`, GLSL 3.30, NVIDIA 621.24, RTX 3060 Laptop). `dispersion` was an
  active uniform (`glGetUniformLocation = 5`). Offscreen Qt platform could not create a context,
  so hardware-context compilation is required for this check.
- Both QA runs independently recomputed the shader math (`d = -thickness*amplitude*circleMap`,
  `s = dispersion*circleMap`, `R = d(1+s)`, `G = d`, `B = d(1-s)`): `circleMap = 0` gave R=G=B
  (no center fringe); `circleMap = 1, dispersion = 0.16` gave R/G = 1.16 and B/G = 0.84
  (+/-16%); `dispersion = 0` gave identical channels at every tested `circleMap`; R-B separation
  rose monotonically and scaled with `circleMap^2`; six out-of-range samples were clamped to
  <= alpha by `min(rgb, a)`, so premultiplied output stays legal.
- Uniform completeness: `_FRAGMENT` declares 18 uniforms; `gpu_widget.py` assigns all 18 and
  `gpu_window.py` assigns 17/18 (only `fgTex`, an existing design because its `useForeground` is
  always 0). Both paths assign the new `dispersion` and the raised `amplitude = 0.95`.
- Parameter regression: `thickness = max(2.0, min(hw,hh)*0.10)`, `ringFade = 1.25`,
  `lensScale = 1.0`, edge-light coefficient 0.20 were all unchanged. `main()` contains exactly
  three `sampleTiny` calls (not six), and the 5x5 Gaussian center loop is unchanged, so fragment
  cost did not regress. `py_compile` passed on both files.
- Observations (not defects): `hiTex` is declared but unused by the fragment body and is
  optimized out of the active-uniform list (17 active vs 18 declared), an existing dead uniform.
  The edge-light add precedes the new `min(rgb, a)`, so on bright near-opaque backgrounds the
  highlight can be clipped back to alpha while dark backgrounds are unaffected — a
  premultiplied-legality tradeoff, not a correctness failure.
- Active-path check: `island.py` instantiates `NativeGlassWindow` for the liquid theme and sets
  `Backdrop.direct_gpu = True`; `glass.py` returns before `_refract()` in that mode, so the
  independent `gpu_glass.py` refractor is not on the live path and was left unchanged.
- Real-machine appearance of the edge fringe, center cleanliness on busy wallpapers, and native
  `frameSwapped` FPS after the extra two samples remain pending on the reference machine.

## 2026-11-23 Edge-Hugging Band And Vivid Interior

An independent QA run (fresh receiver, self-written scripts, routing `NoOne`) passed 35/35
static/numeric assertions plus a real GL 3.3 core compile. The user asked for the refraction
band to sit on the island edge rather than read as an outside ring, and for the interior to use
the demo's approach.

- Band anchoring proved numerically: with `band = clamp(1 - max(-sd,0)/thickness, 0, 1)` and
  `circleMap = 1 - sqrt(1 - band²)`, `sd = 0` gives band/circleMap 1.0 (full refraction exactly
  at the rounded-rectangle boundary), `sd = -thickness` gives 0.0 (zero one band inward), and
  center samples are 0. The sampled sequence sd = 0,-1,-2,-3,-4,-6,-8,-10,-11,-12 gave
  circleMap 1.000/0.600/0.447/0.339/0.255/0.134/0.057/0.014/0.003/0.000 — monotonic decay
  inward, i.e. an edge-hugging band, not an outer collar.
- Fixed band cap verified: hh=173 → 12.0, hh=40 → 12.0, hh=20 → 6.0, hh=5 → 2.0 (floor).
  Displacement `thickness * amplitude` = 14.4 px expanded (was ~16.4), 7.2 px small island.
  The small-island jump (old ~1.9 px, factor ~3.8x) is real and was flagged as a visual-risk
  tradeoff; the small island uses 30% of its half-height as band width vs the large island's
  ~7%, so it deserves a dedicated real-machine look. Not a blocker.
- Interior: `film` confirmed absent by text and AST. Rec.709 weights sum to 1.0; neutral gray
  stays `(0.5,0.5,0.5)`; `sat(0.8,0.2,0.4) = (1.029,0.129,0.429)` scales R-B from 0.4 to 0.6.
  Gaussian `stepUV` is `tinyTexel * 0.8` (was 1.25), tap count unchanged at 25.
- Premultiplied legality: `min(rgb, a)` follows saturate and edge-light. QA found saturate can
  drive channels negative (`sat(1,0,0) = (1.3937,-0.1063,-0.1063)`); negative writes to a UNORM
  default framebuffer are deterministically clamped to zero by GL, so no visual defect on the
  active native path. The engineer then added `max(rgb, 0)` before `min(rgb, a)` and corrected
  the comment; re-verified `sat(1,0,0)` → `(1.0, 0.0, 0.0)` at a=1.0 and `(0.5,0.0,0.0)` at
  a=0.5, both 0 <= rgb <= a.
- Performance: 25 Gaussian taps + 3 dispersion `sampleTiny` = 28 per fragment, identical to
  before; no regression. `ringFade = 1.25`, `lensScale = 1.0`, `dispersion = 0.16`,
  `cornerRadius` via `panel_radius()`, and the three-channel split are unchanged. Both files
  set `thickness`/`amplitude` identically; the only missing uniform in `gpu_window.py` is
  `fgTex` (existing design, `useForeground = 0.0`).
- Real GLSL compile on both runs: GL 3.3.0 NVIDIA 621.24 / GLSL 3.30 (RTX 3060 Laptop),
  `compileProgram(_VERTEX, _FRAGMENT)` success with empty logs. Offscreen Qt cannot create a
  GL context, so a default-platform hardware context is required for this check. py_compile
  passed. Real-machine appearance (edge band width, interior vividness, small-island band,
  native `frameSwapped` FPS) remains pending.

## 2026-11-23 Demo-Level Center Blur Via hiTex Mipmap

An independent QA run (fresh receiver, self-written scripts, routing `NoOne`) passed 9/9 checks
with no failures. The user reported the center was still less blurred than the demo. Root cause:
`glass.py:763-766` deliberately skips CPU `_blur` in liquid mode, leaving only a ~1-2 px 5x5
Gaussian over the downsampled `sharp` texture, versus the demo dialog's ~9.7 px sigma.

- **Render-level proof the center really blurs (decisive)**: reusing the project's real
  `_FRAGMENT` in an FBO render with an 8 px checkerboard in `hiTex` and a body region forcing
  `circleMap = 0` (so `coverage = 0`), a 128x128 center patch gave std 111.56 at lod=0 versus
  std 3.61 at lod=4.6 (-96.8%) and std 0.0 at lod=5.2. Changing the tiny (edge) texture from 40
  to 200 left the center mean/std unchanged, proving the sample came from `base`, not the edge
  and not a transparent region. Step-edge method measured sigma 0.39 px (lod 0), 9.75 px
  (lod 4.6), 11.31 px (lod 5.2); the trilinear blend of fractional LODs runs ~11% above the
  conservative comment formula, still inside the 8-12 px target and matching the demo's 9.7 px.
- `hiTex` is now an **active** uniform (18/18 active after the change, previously 17/18 with
  `hiTex` optimized out). Real GL 3.3 core compile/link succeeded (GL_VERSION 3.3.0 NVIDIA
  621.24, GLSL 3.30, RTX 3060 Laptop). `glGetTexParameteriv` measured MIN_FILTER hi=9987
  (`LINEAR_MIPMAP_LINEAR`), tiny=9729 / fg=9729 (`LINEAR`); hi mip levels 0..8 each attached to
  an FBO returned FRAMEBUFFER_COMPLETE (36053), so no incomplete-black risk.
- LOD math independently recomputed without importing the implementation function: tpl=1.5
  (live) → lod 5.2254, tpl=1.113 (plate crop) → lod 4.7949, both giving sigma 9.00 px via
  `1.25*2^L/(sqrt(12)*tpl)`; clamping at [0,8] verified. Pre-change sigma recomputed as
  0.9024 tiny-texels → 1.26-2.35 logical px, so the ~4-7x increase is real.
- Edge zero-regression: 31/31 static assertions covering band, circleMap, displacement,
  split, three `sampleTiny` calls, coverage, mix, saturate 1.5, edge light 0.12, the max/min
  clamp, and the foreground branch all matched the WLOG-003 baseline. Method note: the worktree
  diff against HEAD mixes earlier uncommitted rounds, so a literal "before this round" snapshot
  was unavailable; the baseline used was the documented prior state, not an absolute line diff.
- Sample budget: 3 `textureLod` (center) + 3 `sampleTiny` (edge) = 6, down from 28 (25 Gaussian
  + 3 edge). `gaussianCenter` and `tinyTexel` have zero remaining references tree-wide. Both
  files' `center_blur_lod(hi, hi_rect)` call and uniform assignment are character-identical.

## 2026-11-23 — background Gaussian blur removed (supersedes the blur QA below)

The user asked to remove the background Gaussian blur. All blur QA below (mip and Gaussian) is
historical; the shipped shader has no blur.

- Source scan: zero remaining references to `SeparableBlur`, `center_blur_sigma`,
  `center_blur_lod`, `blurredTex`, `generateMipmap`, `textureLod`, or any blur uniform in
  `mybalcony/ui/*.py`. Imports of `_FRAGMENT` / `NativeGlassWindow` succeed.
- Real GL 3.3 compile/link OK (3.3.0 NVIDIA 621.24). 15 active uniforms, all expected; `bgTex`
  active (type 35678 = sampler2D), `fgTex` active, and no `uRadius`/`uDir`/`uTexSize` blur
  uniforms. `sampleBg` appears 5 times in the shader (definition + 4 calls: base + 3 dispersion).
- Decisive render proof: an 0/255 8 px column checkerboard uploaded as `bgTex`, rendered through
  the real lens at `dispersion=0`, `ringFade=0` (coverage=0, pure base), gave center row values
  of only 0 and 255 with isolated 127 at checker boundaries (bilinear filtering) — 3 distinct
  levels, no blur gradient. With the Gaussian this same input produced 37 levels; with the mip
  it collapsed to ~std 3.6. Clear background is confirmed.
- Real-machine clarity and native FPS remain pending user sign-off.

## 2026-11-23 — refraction band aligned to body, widened inward

The user reported that top/bottom refraction bands aligned with the border but left/right still
overhung, and asked that all four sides align while the band widens inward for a better effect.

- Root cause measured in `shape.py`: for a top-anchored 640×300 body, `neck_path` at full contact
  spans 666 px wide (body x=[130,770] vs path x=[117,783]) — a 13 px fillet on each side — while
  the vertical path overhang is only ~1.5 px at the top and 0 at the bottom. The old SDF used
  `path.boundingRect()`, so the left/right band sat outside the visible border; the asymmetry
  matches the report exactly.
- Both GL paths now build the SDF from `island.body`. Geometry check: body x=[130,770] y=[20,320]
  is the exact rounded-rect the foreground stroke draws, so the band's outer edge (`sd=0`,
  `shapeAlpha` 0.5) lands on the border on all four sides.
- Band width decoupled from displacement: `thickness` stays `min(12, max(2, min(hw,hh)*0.30))` for
  peak refraction, and `bandWidth = min(30, max(6, thickness*2.4))` sets inward spread — expanded
  island 12 → 28.8 px, small island 3 → 7.2 px. Real GL 3.3 compile OK with 16 active uniforms,
  `bandWidth` present; py_compile OK. The wider circleMap tail increases coverage in the interior
  but leaves peak `thickness * amplitude` displacement unchanged; real-machine look is pending.

## 2026-11-23 — inward refraction band widened 1.5×; color-fringe explanation

- User asked to widen the inward refraction band by another half. Both GL paths changed
  `bandWidth` from `min(30, max(6, thickness*2.4))` to `min(45, max(9, thickness*3.6))` — exactly
  1.5×. Numeric check: expanded island thickness 12 → bandWidth 28.8 → 43.2 px; small island
  thickness 3 → 7.2 → 10.8 px; square 200×200 same as expanded. `thickness` (peak displacement),
  `amplitude = 1.2`, and `dispersion = 0.16` untouched. py_compile OK; both files' uniform lines
  character-identical.
- User also asked why the refraction is colored. Answer grounded in the shared fragment shader:
  `split = dispersion * circleMap` makes R sample at `displacement*(1+split)` and B at
  `displacement*(1-split)` while G holds the base displacement and supplies alpha; at
  `dispersion = 0.16` the perimeter separates R/B by ±16%, producing the colored fringe. It is an
  intentional demo-following effect, edge-only (center `circleMap = 0` stays fringe-free), and
  `dispersion = 0` restores a colorless ring. No code change made for the color question.

## 2026-11-23 — 2-pass separable Gaussian replaces the ghosting golden-angle disc

The user's two real-machine screenshots showed "全重影" on high-contrast browser text behind the
glass. Root cause: the 16-tap golden-angle disc is a sparse single-pass sampler — each tap lands
on a different shifted copy of a glyph, producing ~16 translucent copies (ghosting). No parameter
tuning fixes a discrete sampler. Replaced with the demo dialog's real pipeline.

- Restored `SeparableBlur`: two FBOs / two textures, `_BLUR_FRAGMENT` is a 33-tap ±3σ `exp(-0.5x²)`
  normalized 1D kernel (`_gaussian_kernel_1d`), H `hi->tex[0]` then V `tex[0]->tex[1]` → continuous
  2D gaussian, no discrete copies. `blur()` saves/restores FBO/viewport/blend; `_ensure_size`
  rebuilds on resize. `CENTER_BLUR_SIGMA=9` logical px → `center_blur_sigma(hi,hiRect)` texels from
  measured density (1350/450 → 27 texels). Lens shader uses two samplers: `base=sampleBlur(uvG0)`
  blurred center, `refracted=sampleBg()` clear edge. All golden-angle code removed tree-wide.
- Verified: 33 weights sum 1.0, offset ±3σ; py_compile OK; real GL 3.3 compile — LENS 17 uniforms
  (`blurredTex`/`bgTex` both active), BLUR 4 uniforms. End-to-end FBO test on a 4px 0/255 stripe
  sheet (simulating text strokes), sigma 8: source 2 levels / 16 strong peaks; blurred 39 levels,
  min 52 / max 203, and the center row read 125-130 (±5 quantization noise, no surviving peaks) —
  the high-contrast strokes collapsed to a smooth continuous field with no discrete glyph copies.
  Real-machine look and two-pass FPS cost pending.

## 2026-11-23 — golden-angle disc gaussian center blur restored

The user asked to re-add the earlier 5x5 gaussian and, when offered 5x5 / golden-angle / 2-pass,
picked the golden-angle option as the more delicate one.

- `_make_blur_gather()` mirrors `liquid-glass-react`'s `generateGaussianDisc()` from
  `web-prototype/assets/lib-check.js:301`: goldenAngle = `pi*(3-sqrt(5))`, 16 taps at
  `r = 3*sqrt((i+0.5)/16)` sigma units around the spiral, weight `exp(-0.5*r²)`, normalized.
  Verified 16 weights summing to 1.0 exactly. Default tap count matches demo `DEFAULT_BLUR_TAPS=16`.
- `blurBg()` returns one sharp `sampleBg` tap when `blurRadiusPx < 0.5`, otherwise the 16-tap
  gather with offsets scaled by `blurRadiusPx / hiRect.zw`. `blurRadiusPx = CENTER_BLUR_RADIUS
  (9.0) * dpr`. Only center `base = blurBg(uvG0)` is blurred — `refracted` and dispersion stay on
  clear `sampleBg()`, preserving the edge squeeze. Both GL paths share `_FRAGMENT` and set the
  same `blurRadiusPx`.
- py_compile OK. Real GL 3.3 compile OK, 17 active uniforms including `blurRadiusPx`, no mip/FBO
  uniforms. End-to-end FBO render on an 8px 0/255 checker (160×160, body covering full viewport
  so center circleMap=0): with radius 0 the center 60×60 region had 3 distinct gray levels,
  mean 129.6, std 119.81 (sharp checker); with radius 18 it had 16 distinct levels, mean 126.2,
  std 27.08 — the checker is genuinely smoothed into a gaussian gradient. Real-machine look
  pending.

## 2026-11-23 — edge color dispersion turned off (user: "I don't need color")

- Both GL paths changed `dispersion` 0.16 → 0. With `split = dispersion * circleMap = 0`, R/B
  sample at exactly the G displacement, so `refracted.r/g/b` come from one background point and
  the ring is colorless. The three-channel shader and its `dispersion` uniform are retained
  (inert), so the effect is reversible by setting 0.16 again. `thickness`, `bandWidth`,
  `amplitude`, `ringFade` unchanged. py_compile OK; both uniform lines character-identical.
- **End-to-end GL 3.3 render proof** on a gray horizontal gradient (R=G=B at every source pixel,
  value = x/160*255), body 144×144 centered in a 160×160 FBO, thickness 16 / bandWidth 43:
  with `dispersion = 0.16`, 1118 opaque pixels had |R-B|>3 (max |R-B| = 10, max |R-G| = 5) —
  the channel split only appears where the background has a slope inside the band. With
  `dispersion = 0`, **0 pixels** had |R-B|>3 and max |R-B| = max |R-G| = 0 across all opaque
  pixels — no color fringe anywhere. Note: an earlier attempt with a pure red/cyan step background
  was invalid because the source itself had R≠B; the gray gradient isolates the shader's effect.

## 2026-11-23 — topmost Finder-bar click blocking

The user reported that hovering the island and then clicking did nothing when the
MyDockFinder bar was on top. Root cause and verification:

- `HWND_TOPMOST = -1` passed to an undeclared `ctypes.WinDLL("user32").SetWindowPos` becomes
  32-bit `0x00000000FFFFFFFF`, not the 64-bit `(HWND)-1` `0xFFFFFFFFFFFFFFFF` that x64 Win32
  expects. Confirmed by direct ctypes inspection; the old `_raise_topmost()` therefore failed
  silently and never changed z-order. Fixed with `ctypes.c_void_p(-1).value` plus explicit
  `HWND` argtypes/restype on `SetWindowPos`, `BringWindowToTop`, `WindowFromPoint`, `GetAncestor`,
  and `GetCursorPos`.
- `_covered()` previously passed Qt's logical `QCursor.pos()` to `WindowFromPoint`, which needs
  physical pixels. At DPR 1.5 a logical (620,240) maps to physical (930,360); the old code hit
  the wrong location. Now uses `GetCursorPos` (no argument = cursor) or converts a supplied
  logical point with the owning screen's DPR. Direct method test on an opaque topmost window:
  `_covered()` and `_covered(logical center)` both False (self), True on the desktop.
- Decisive Z-order test with two real topmost windows (a mock Finder bar A above the island B,
  overlapping region hit-tested): after A raises, hit = A; after `Island._raise_topmost(B)`,
  hit = B; forcing A topmost again gives A, and a second island raise gives B again — every
  cycle. `WS_EX_TOPMOST` is set on the island and the foreground window is unchanged (no focus
  steal). `_poll_hover()` additionally raises once on cursor entry and checks at 0.15 s / 0.3 s.
- Real MyDockFinder confirmation on the user's machine is still pending.

## 2026-11-23 — demo-faithful two-pass Gaussian blur (supersedes the mip risk above)

The user said the mip center was "not delicate enough, want the demo's blur". The three-mip
approach was replaced by the demo's real separable Gaussian FBO, so the mip-specific QA above
(std/lod/sigma, mip completeness, generateMipmap cost) no longer describes the shipped code.

- Kernel: `_gaussian_kernel_1d()` returns 33 taps, offsets -3.0..3.0, weights summing to 1.0
  (verified to 6 decimals), matching `generateGaussianKernel1D` / `computeBlur1DTapCount` in
  `lib-check.js`. `_BLUR_FRAGMENT` contains 33 texture taps; translating the kernel into GLSL
  generates them at compile time, no sparse tap field.
- End-to-end FBO render (real GL 3.3 context, 64x64 0/255 column checkerboard source, sigma 8):
  the blurred output row had 37 distinct grayscale levels versus 2 input levels, spanning
  39..216 — a continuous gradient instead of mip box blockiness. Both shaders compile/link under
  GL 3.3.0 NVIDIA 621.24; `center_blur_sigma()` maps 9 logical px at dpr 2 to sigma 18 texels.
- Density mapping preserved: sigma derives from measured `hi.width / hiRect.width`, so live
  full-resolution and plate snapshot-crop paths both hit 9 logical px.
- Reference check: `lib-check.js` dialog card (`buildDialog`) uses `useSeparableBlur = true`,
  `dialogBlurRadius = 16dp` light / 8dp dark, a colorControls pass before the two-pass blur, and
  `uBlurRadius = 0` at shader time because the backdrop FBO is pre-blurred — base and all seven
  dispersion samples use that one blurred FBO. The project mirrors this with `blurredTex` for
  base + three channel samples (the 7-path dispersion remains intentionally approximated by 3).
- Cost: uniform texture samples fell 6 → 4, and the flagged ~0.52 ms median / 1.46 ms p95
  per-frame `generateMipmap` risk is gone because mips are no longer used; the blur is two
  dedicated FBO passes. Real-machine appearance and native FPS are still pending user sign-off.

### 2026-11-23 — full-island clear refraction (clarity / refractSpan)

- Real GL 3.3.0 compile/link of the shared `_FRAGMENT` passed; 19 active uniforms, including
  the new `clarity` and `refractSpan`. Both `_draw_lens` paths set `clarity=1.0` and
  `refractSpan=min(hw,hh)`; `bandWidth` stays edge-light-only.
- End-to-end FBO render (256x128, 8px checker background, gray blurred texture as matte model):
  - Clarity: center-row contrast rose 3.54 (clarity=0, gray matte) → 120.27 (clarity=1, clear
    checker) — the center gaussian matte is gone over the whole island.
  - Displacement reach: vs a near-zero-displacement baseline (span=1), the old edge-only
    span=12 changed 0/5120 pixels in the non-edge center region (rows 48..80, cols 48..208),
    while the full-island span=120 changed 433/5120 (8.5%) — the refraction field now reaches
    the center, not just the rim.
  - Colorless: max |R-B| on the center row = 0 with `dispersion=0`.
- Real-machine appearance and native FPS after covering the full island still pending.

### 2026-11-23 — radial field truly spans the island (refractSpan=0.45, normalized radius)

- Numeric audit of the previous field exposed the bug: with real path params (half-size 200x40,
  span=`min(hw,hh)=40`), `circleMap=1-sqrt(1-t²)` gave 0.00 px displacement at center and only
  0.66 px at 12 px inside the island; the earlier span=120 check had masked this. The prior
  "reaches center" evidence was therefore invalid for the real geometry.
- New field: `pn=p/halfSize`, `radialDir=normalize(pn)`, `reach=smoothstep(0,0.45,length(pn))`,
  `disp=thickness*amplitude*reach*0.7`. Numeric: mid-island (12 px in) ~7.5 px, rim ~10 px —
  full strength well before the rim, no axis-aligned dead zone.
- Real GL 3.3 compile/link of shared `_FRAGMENT` passed (19 active uniforms, `refractSpan`/
  `clarity` active). Offscreen FBO render at real island size (480x140, half-size 200x40):
  center-region (|x-cx|<150, |y-cy|<28) pixels changed by enabling refraction = 10020/16445
  (60.9%). Visual A/B: no-refract image has a straight central band and regular checker; the
  new image warps the central band into an arc and distorts the checker across the whole island,
  not only the rim.

### 2026-11-23 — layered optics restored (rim refraction + transparent center 5x5)

- After the full-island radial trial the user asked for the earlier rim distortion plus a
  transparent 5x5 gaussian center. Shared `_FRAGMENT` restored: `circleMap` rim band drives
  `gradient*displacement`, `coverage = circleMap*ringFade` mixes blurred center with clear
  refracted rim; `clarity`/`refractSpan` and the radial field were removed (compile shows 17
  active uniforms, neither present).
- Center blur: `SeparableBlur` kernel is now 5-tap with integer offsets -2..2, sigma 1.0
  weights ([0.0545,0.2442,0.4026,0.2442,0.0545]); `center_blur_radius()` (renamed from
  `center_blur_sigma`) returns a 1-logical-px texel step.
- Evidence: real GL 3.3 compile/link passed; real two-pass blur of a single white pulse yields
  peak 41.0 (=255*0.4026^2) with 3 px spread vs 29 px for a dense sigma-9 reference — narrow,
  energy-concentrated, transparent. End-to-end FBO render at real island size: center contrast
  72.3 (checker readable through the blur), rim band 6450/8550 (75.4%) pixels distorted,
  max|R-B|=0 with dispersion=0. A/B image shows rim-only distortion and a transparent center.
- Real-machine appearance and FPS pending.

### 2026-11-23 — nav bar text: PingFang white + black outline

- `NavBar.paintEvent` tab labels now draw through `theme.outlined_text()` (previously a bare
  `p.drawText`, the last hand-painted text not going through the outline path); `_TabGhost` lost
  its active-tab exemption (`outline=not self.active` removed) so drag floats match. Font family
  and color were already correct: `ui_font` resolves `PingFang SC` first under the liquid theme
  and `pill_text`/`text` are pure white — no changes needed there.
- Icon glyphs intentionally stay on `icon_font` (Segoe Fluent Icons) without outlines; the icon
  family must never gain PingFang (glyph codepoints would break).
- Evidence: py_compile pass; liquid-theme `ui_font(12.5, DemiBold).families()[0] == "PingFang SC"`;
  `pill_text()` == (255,255,255); `outlined_text` on/off A/B on "主页 Home" gives 448 vs 0 dark
  stroke pixels (outline path proven); real offscreen NavBar render shows 128 black-outline
  pixels around 531 white text pixels; source audit: exactly 2 `theme.outlined_text` calls in
  nav.py, no active-tab exemption left.

### 2026-11-23 — nav bar luminance-adaptive inversion (white background)

- Motive: on an all-white page the nav bar became invisible. White body text is 1:1 with the
  background, so only the 1px black outline survives (hollow glyphs at 12.5px); white icon
  glyphs, the translucent white active pill and the white hover ring disappear the same way.
- Design: `NavBar._bg_luminance()` maps the capsule rect through `_win_origin` into the island's
  existing `backdrop.hi` / `hi_rect` snapshot, scales that crop to 1x1 and takes the Rec.709
  average; cached on `(backdrop.version, x, y, w, h)`. `_refresh_light()` flips at
  `LIGHT_IN=0.58` / `LIGHT_OUT=0.46` (hysteresis) and is a no-op outside the liquid theme or
  when the palette's body text is already dark. `Island._on_backdrop()` calls
  `nav.refresh_light()`, which repaints only when the state actually flips.
- Light state: ink `LIGHT_INK (24,26,32)` via `theme.glass_ink()`, stroke switched to white via
  the new `outlined_text(edge=...)` parameter (shadow scaled to 1/3), active chip
  `rgba(0,0,0,30)`, hover `rgba(0,0,0,46)`; `IconButton.on_light` and `_TabGhost.on_light`
  follow the same flag.
- Evidence (offscreen, liquid theme): ink entry returns white for dark and `(24,26,32)` for
  light; white-background NavBar render → `on_light=True`, 96 ink pixels, 0 white body;
  black-background render → `on_light=False`, 96 white pixels, 0 ink pixels (exact mirror, so
  only the colour swapped, not the layout); hysteresis sequence across background levels
  120..170 stayed constant; `_TabGhost(on_light=True)` renders 40 ink pixels on its white card;
  `outlined_text` A/B on a mid-grey plate gives 264 vs 0 bright stroke pixels with white vs
  default edge while the dark body stays present; `refresh_light()` is idempotent (3 repeats)
  and flips once when the wallpaper snapshot changes to white.
- Real-machine legibility on a white wallpaper still pending.

### 2026-11-23 — rim displacement taper + 50% stronger center blur

- Report to check first: "the refraction band's bottom spills past the island body". Measured the
  SDF coverage directly at real island size (480x140 body in a 540x180 viewport): alpha>0 pixels
  below the bottom edge = 0, right of the right edge = 0, left of the left edge = 0, above the top
  edge = 0; the edge row itself is alpha=127 (antialiasing only). Nothing was geometrically
  overflowing — the visible spill came from the displacement field pushing samples right up to
  the rim, so the outermost texels read background taken from further inside the island and the
  band looked bulged past the outline.
- Fix: `displacement` multiplied by `dispEase = smoothstep(0.0, 8.0, -sd)`. Zero slope at the rim
  means no visible seam where the glass meets the real background outside; `coverage` still uses
  `circleMap` so the rim stays clear rather than falling back to the blurred texture.
- Blur +50%: `_GAUSSIAN_SIGMA` 1.0 → 1.5 and `_GAUSSIAN_STEP` 1.0 → 1.5 logical px, so the 5-tap
  kernel footprint goes from ±2 px to ±3 px. Sigma alone cannot widen a fixed 5-tap footprint, it
  only flattens the weights, so both constants move together. Center weight: 0.4026 → 0.2921,
  normalised weights [0.1201, 0.2339, 0.2921, 0.2339, 0.1201].
- Evidence (real GL 3.3, real `SeparableBlur`): `center_blur_radius()` returns 1.50 texels at
  dpr=1; a single white pulse through the real two-pass kernel spreads 7 px above the
  25%-of-peak threshold with peak 74 (previous 1.0/1.0 kernel: 3 px, peak 41). Rim taper: the
  outermost body row is pixel-identical to the zero-displacement render (mean channel diff 0)
  while rows 8–12 px inside still differ by ~55, i.e. warping survives inland and tapers at the
  rim; below-body alpha remains 0.
- Real-machine appearance and FPS pending.
