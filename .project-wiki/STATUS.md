# Project Status

Last updated: 2026-11-25

## Current Focus

- Liquid-glass rendering and the revised hover interaction are implemented and documented.
- The active renderer uses a native OpenGL background below the Qt foreground island.
- The native-GPU settled fast path and high-frequency capture now cover the collapsed small and
  medium islands as well as the expanded island.
- The native GPU expanded foreground now draws the dual-source edge and cursor-following
  specular spot, and shape-invariant foreground animations such as the lyric sweep repaint
  even while the island shape is static.
- Liquid-glass body text is white with PingFang SC preferred, a 1 px black stroke, and a light
  black shadow; light-surface foregrounds and the Segoe icon font are unchanged. Liquid QMenu
  items use the same white + stroke treatment via a QProxyStyle, over the original light glass
  background (no dark overlay).
- The battery page fades device rows softly into the glass at the scroll bottom (liquid + native
  GPU only) with a 14 px bottom spacer; the navigation glass capsule hugs the leftmost tab and
  rightmost buttons with zero end padding.
- The liquid glass refraction ring is **colorless** (`dispersion = 0`) at the user's request —
  an earlier demo-style `dispersion = 0.16` edge color fringe was tried and then removed after
  the user said they did not want color. The channel-split shader code is retained but inert.
  Refraction strength stays `amplitude = 1.2`; clean centers and premultiplied RGB <= alpha hold.
- The liquid island no longer draws its external three-layer soft shadow, and every expanded
  page is inset one step inside the outer glass (`PAGE_CARD_INSET = 8`); non-liquid themes keep
  the original shadow and padding.
- The refraction band is anchored to the island edge with a fixed 12 px logical cap (small islands
  scale to 6 px) instead of a size-relative width, and the interior uses the demo's vivid model
  (Rec.709 saturation 1.5) instead of a graying wash. The glass center is softened by a **2-pass
  separable Gaussian FBO** (`SeparableBlur`, 33-tap ±3σ, sigma 9 logical px by measured density) —
  the demo dialog's real pipeline. A 16-tap golden-angle disc tried first was rejected for visible
  text ghosting (discrete taps), so the continuous two-pass convolution replaced it. Only the
  center `base` uses the blurred texture; the edge/refraction stays clear (`sampleBg()`). No mip
  chain. Edge light is a thin rim (0.12), premultiplied RGB <= alpha.
- The glass uses **layered optics** (restored at the user's request after the full-island radial
  trial): the rim is a clear SDF refraction band (`circleMap` × analytic gradient, `bandWidth`
  edge-only) and the center is a **transparent 5x5 separable gaussian** (5-tap, integer offsets,
  σ=1.5, 1.5-logical-px texel step → ±3 px footprint). `coverage = circleMap * ringFade` mixes
  blurred center with refracted rim. The displacement field is tapered to zero over the outermost
  8 px (`dispEase = smoothstep(0.0, 8.0, -sd)`) so the rim itself is never warped and the band
  cannot look like it spills past the outline; the rim stays *clear*, only the warping tapers.
  The full-island uniforms (`clarity`, `refractSpan`) were removed; dispersion stays 0;
  premultiplied RGB <= alpha.
- Runtime interaction is **click-to-expand**: `island.hover_expand_ms = 0` disables the
  five-second hover open (`ms <= 0` never accumulates `_hover_since`), while hover still opens
  the medium content and the dock-bar one-line lyric expand is unchanged. Restoring 5000 brings
  the timed hover back.
- Capture and idle scheduling ran a performance pass ("A"): DXCam capture
  `glass.LIVE_TARGET_FPS` 90 → 60, the collapsed backdrop is capped at 30fps by
  `island._bg_relaxed()`, and `island._idle_gpu()` drops the foreground to 45fps when the
  cursor is >120px away, the spring is at rest and the island is collapsed. Idle CPU
  152.3% → 102.9% with RSS 396 → 378MB.
- Lyrics resolve **word-level timing** without LX Music installed: the cascade is LX local API
  (`media.lx_api`, same-track only) → NetEase `eapi` yrc (LX's wy source, pure-Python AES) →
  NetEase public API → LRCLIB. `Lyrics.words` drives a per-character sweep; empty results now
  expire after 240s and a 6s retry tick re-fetches after the 60s failure cooldown, so one
  dropped request no longer kills lyrics for the whole track.
- Liquid menus and overlay icons are **backdrop-aware**: above `LIGHT_IN = 0.58` luminance
  menu items and overlay glyphs flip to `LIGHT_INK` with a light stroke (plus a ≤0.34 readability
  scrim), below it they stay white with a black stroke. `MENU_QSS` no longer sets `color`, which
  used to double-paint every item through `QStyleSheetStyle`.
- The lyric energy meter reads through `island._pk()` (instant attack, 0.30s release,
  2.5s auto-gain) so the 0.03–0.35 peaks the system reports drive bars to full travel; compact
  busy states repaint at 11ms instead of taking the 2-of-3 GPU skip.

## Recent Wiki Updates

- 2026-11-25: **Word-level lyrics without LX Music**, backdrop-aware menus, lyric-meter gain and
  click-only expansion. Lyrics cascade is LX local API → NetEase `eapi` yrc (LX's wy source with
  a pure-Python AES, FIPS-197 verified) → public NetEase → LRCLIB; yrc's JSON-header and
  `[start,dur](start,dur,0)word…` forms are converted into the project's inline word-time LRC
  dialect. Empty lyric results expire after `EMPTY_TTL = 240s` and a 6s retry tick re-fetches
  after the 60s cooldown, fixing "no lyrics for the whole track". Liquid menus gained
  `_lum_of()`/`_menu_scrim()` and a light/dark ink split (measured text band min 21.7 on white,
  median 238.3 on black) and `MENU_QSS` dropped its `color` rule. `island._pk()` adds attack/release
  envelope plus 2.5s auto-gain (bars `3 + 17·b`), compact busy states repaint at 11ms.
  `island.hover_expand_ms = 0` makes expansion click-only.
- 2026-11-24: **Backdrop-aware overlay ink, three-row battery viewport, peripheral icons, perf A**.
  `widgets.backdrop_luminance`/`glass_ink` flip device rows, battery rings, home tiles and icon
  buttons to `LIGHT_INK` above `LIGHT_IN = 0.58`; `BatteryPage` became a fixed 3-row viewport with
  smooth `ScrollArea` wheel scrolling; `services/atkdev.py` + `ui/devicon.py` identify ATK
  (VID `0x373B`) and Razer peripherals; weather auto-locate resolves 泉州; performance A cut idle
  CPU 152.3% → 102.9% (DXCam 60fps, 30fps collapsed backdrop, 45fps idle foreground).
- 2026-11-23: **Removed the black rim** introduced by the earlier `lightBg` bevel, and pinned the
  light to the **bottom-left**. The shader no longer darkens any part of the perimeter (the
  `rimPx` thickness absorption and `shadeAmt` backlight term are gone) — the rim is additive
  highlight only, `litW = 0.5 + 0.354*(gradient.y - gradient.x)` plus a radial `cornerLit` falloff
  centred on the bottom-left corner, with `brightAmt = mix(0.12, 0.22, lightBg)`. 2D follows:
  `dual_edge(..., up_right=0.45)` (bottom-left 124 / top-right 56 / midpoint 0, never a closed
  ring), `paint_spec` home and `_gpu_liquid_accents` moved to the bottom-left, and a new
  `paint_corner_spec()` fixed corner highlight. The light-background ink stroke was removed
  (`_paint_edge` / `paint_static_layers` are white again). Measured: pure white rim band 255.0 in
  all four quadrants (was 187–228 = the black outline), centre untouched; dark backdrop
  bottom-left 50.1 vs top-right 38.0, corner highlight +13.1 more. Consequence: no darkening means
  the island is transparent-looking again on pure white; a faint body tint is the alternative if
  the boundary must stay visible there.
- 2026-11-23: The island now keeps a **visible rim on pure-white backgrounds**. The edge used to be
  a single additive white highlight, which is 1:1 with white and therefore invisible. It is now a
  **bevelled glass wall**: a new `lightBg` uniform (0..1) darkens the backlit side
  (`shadeAmt = mix(0.07, 0.42, lightBg)`) while keeping the lit side, plus an outermost ~2px
  thickness absorption. `Island._light_bg` maps `theme.lum` continuously
  (`clamp((lum - 0.40) / 0.30, 0, 1)`) and repaints only on a >0.004 change; the 2D layers follow
  the same flag (`_paint_edge` stroke white→`LIGHT_INK`, `dual_edge(..., rgb)` and
  `paint_static_layers(..., edge_rgb)`). Pure white: rim 254 → 207.8 (46 grey levels), centre
  untouched, no alpha outside the body; dark backdrop keeps the original look (rim 6.7 levels
  brighter than the interior).
- 2026-11-23: Refraction no longer appears to **spill past the bottom rim**, and the body blur is
  **50% stronger**. Measurement first showed the SDF coverage was already exact (alpha stays 0
  outside all four edges; the edge row is pure antialiasing), so the spill was the displacement
  field warping texels right up to the rim. `displacement` is now multiplied by
  `dispEase = smoothstep(0.0, 8.0, -sd)`, tapering to zero over the outermost 8 px with zero
  slope so the edge joins the outside background seamlessly; `coverage` still uses `circleMap`,
  so the rim stays clear. Blur: `_GAUSSIAN_SIGMA` 1.0 → 1.5 *and* `_GAUSSIAN_STEP` 1.0 → 1.5
  (footprint ±2 → ±3 px; sigma alone would only flatten the weights).
- 2026-11-23: Nav text now **auto-inverts on light backgrounds**. White-plus-black-outline is
  unreadable on an all-white surface (glyph body 1:1 with the background leaves a hollow 1px
  outline; white icons / active pill / hover ring vanish too). `NavBar` samples the island's
  backdrop snapshot at 1×1 (`_bg_luminance`, cached on `backdrop.version`) and flips between
  white-on-dark and `LIGHT_INK (24,26,32)` + white stroke at 0.58/0.46 with hysteresis,
  liquid theme only. `outlined_text(edge=...)`, `theme.glass_ink()`, `IconButton.on_light`,
  `_TabGhost.on_light` and `Island._on_backdrop → nav.refresh_light()` carry the state.
- 2026-11-23: Nav-bar tab labels now render with the site-wide **PingFang white + black outline**
  look: `NavBar.paintEvent`'s label switched from bare `drawText` to `theme.outlined_text`, and
  `_TabGhost`'s active-tab outline exemption was removed. Fonts/colors were already correct
  (`ui_font` → `PingFang SC` first, `pill_text` → white); icon glyphs stay unoutlined on
  `icon_font`. Verified by offscreen render (448 vs 0 stroke pixels on/off, real NavBar: 128
  outline + 531 white text pixels) and a source audit (2 outlined_text calls, no exemption).
- 2026-11-23: Restored **layered optics** after the full-island radial trial — rim distortion back
  to the SDF `circleMap` band, center now a transparent 5x5 separable gaussian (5-tap integer
  offsets, σ≈1, `center_blur_radius` = 1-logical-px step) replacing the 33-tap σ9 frosted kernel.
  `clarity`/`refractSpan` uniforms removed. Verified: GL 3.3 compile (17 uniforms), pulse test
  (peak ≈41, 3 px spread vs 29 px σ9 reference), end-to-end FBO render (center contrast 72.3,
  rim 75.4% pixels distorted, |R-B|=0). Real-machine look pending.
- 2026-11-23: Fixed "refraction still only at the outer rim" — the old `circleMap` gave ~0.66 px
  displacement mid-island and 0 px at center (the prior check wrongly used span=120 vs the real
  `min(hw,hh)=40`). Replaced it with a normalized radial field (`radialDir` + smoothstep reach,
  `refractSpan=0.45` fed by both paths); mid-island displacement ~7.5 px, rim ~10 px. Offscreen FBO
  render at 480x140 showed 60.9% of center-region pixels change and the whole checker/stripe
  warped, not just the rim. GL 3.3 compile + py_compile pass. Real-machine look pending.
- 2026-11-23: Switched the liquid island to **full-island clear refraction**: the shared shader
  now decouples displacement (`refractSpan = min(hw,hh)`, reaches edge→center) from clarity
  (`clarity=1`, whole island samples clear `bgTex`, center gaussian matte removed). Narrow
  `bandWidth` still drives only the edge highlight; dispersion stays 0. Verified by GL 3.3
  compile (19 uniforms) and an FBO render: center contrast 3.54→120.27, edge-only span changed
  0/5120 center pixels vs full span 433/5120, |R-B|=0. Real-machine look/FPS pending.
- 2026-11-23: Fixed a submenu Z-order bug — the hover poll's auto-raise was lifting the island over
  its own open popup, so first-level buttons bled through the second-level menu. Added
  `Island._popup_open()` and `_raise_topmost()` now no-ops while a visible QMenu / CCPanel /
  LookupPopup is up. Also swapped the control page columns (tile grid LEFT, three sliders RIGHT)
  and pinned both to 251 px so their heights match. Verified by py_compile + offscreen assertions
  (popup detection, layout order, equal 251 px height); real-machine confirmation pending.
- 2026-11-23: Replaced the golden-angle disc blur with the demo's real **2-pass separable Gaussian
  FBO** after the user's screenshots showed "全重影" — 16 discrete disc taps each sampled a shifted
  glyph copy on high-contrast browser text. `SeparableBlur` (33-tap ±3σ, two 1D passes) yields a
  continuous gaussian with no copies; only center `base` is blurred, refraction stays clear.
  Verified: weights sum 1.0, GL 3.3 compile (LENS 17 / BLUR 4 uniforms), and an end-to-end 4px
  stripe render where a 0/255 source collapsed to 125-130 (amplitude 255 → 5). Real look pending.
- 2026-11-23: Restored center blur with the demo's **16-tap golden-angle disc gaussian** after the
  user asked to bring back the 5x5 and picked the more delicate option when offered alternatives.
  `_make_blur_gather()` generates the tap accumulator (golden angle, r=3√t, exp(-0.5r²) weights,
  sum=1.0); `blurRadiusPx = 9×dpr`; only `base` is blurred, refraction stays clear. Verified: 16
  active taps, GL 3.3 compile (17 uniforms), and an end-to-end checker render where center std
  fell 119.81 → 27.08 and gray levels 3 → 16 with blur on. wiki synced; real-machine look pending.
- 2026-11-23: The user said "I don't need color", so both GL paths set `dispersion = 0` — the
  edge RGB dispersion is off and the refraction ring is colorless again (shader split code kept
  but inert). End-to-end gray-gradient render proved it: `dispersion = 0.16` produced 1118
  pixels with |R-B|>3, `dispersion = 0` produced 0 with max|R-B|=0. py_compile OK.
- 2026-11-23: Widened the inward refraction band by another half (`bandWidth` 2.4× → 3.6× thickness,
  cap 30 → 45 px: expanded island 28.8 → 43.2 px, small 7.2 → 10.8 px) at the user's request;
  peak displacement unchanged. Explained that the edge's color fringing is the intentional
  `dispersion = 0.16` RGB channel split added earlier to follow the demo; setting it to 0 restores
  a colorless ring. Verified by py_compile and bandWidth scaling.
- 2026-11-23: Aligned the refraction band's outer edge to the body border on all four sides by
  building the SDF from `island.body` instead of `path.boundingRect()` (the anchored neck widened
  the latter ~13 px per side); added a separate `bandWidth` that widens the band inward 12 → 28.8
  px without raising the fixed peak displacement. Verified by GL 3.3 compile and geometry check.
- 2026-11-23: Fixed clicks swallowed by the topmost MyDockFinder bar. `HWND_TOPMOST` is now
  the 64-bit `(HWND)-1` (bare `-1` was truncated to an invalid 32-bit handle, so every raise
  failed); Win32 z-order calls have explicit `HWND` signatures, `_covered()` uses physical
  `GetCursorPos` pixels instead of logical Qt coordinates, and the island raises on cursor entry
  plus a 0.15 s / 0.3 s hit-test throttle. Verified with a real two-topmost-window Z-order test.
- 2026-11-23: Removed the background Gaussian blur entirely at the user's direction. The glass
  center and RGB dispersion now read the clear full-resolution background (`bgTex`); the
  `SeparableBlur` two-pass FBO class and all blur uniforms were deleted. Verified by GL 3.3
  compile (15 active uniforms, no blur uniforms) and an end-to-end render where an 0/255 checker
  stays 0/255 (only bilinear edge samples at 127) — no gradient, i.e. no blur.
- 2026-11-23: Replaced the three-mip center blur with the demo-faithful two-pass separable
  Gaussian FBO (33 taps, ±3σ) after the user said the mip blur was not delicate enough; base and
  dispersion share one blurred texture, `generateMipmap`/mip filtering removed, uniform samples
  6 -> 4, verified with a real GL 3.3 compile and an end-to-end 0/255-to-37-level FBO render.
- 2026-11-23: Synchronized the demo-level center blur via three `hiTex` mip samples (~9 px sigma,
  dead uniform revived, 28 -> 6 samples), including 9/9 independent QA, a rendered checkerboard
  std drop of 96.8%, and a flagged per-frame `generateMipmap` performance risk.
- 2026-11-23: Synchronized the edge-hugging fixed-width refraction band and the vivid demo-style
  interior (saturation 1.5, lighter Gaussian), including 35/35 independent QA, real GL 3.3
  compile, and the demo WebGL reference verified from `web-prototype/assets/lib-check.js`.
- 2026-11-23: Synchronized the React-style edge RGB dispersion (new "clean center, allowed
  edge fringe" optical criterion), the removed liquid outer shadow, and the 8 px page-card inset,
  including 15/15 layout and 30/30 dispersion independent QA plus a real GLSL 3.3 compile.
- 2026-11-23: Synchronized liquid QMenu white-stroked text over the original light glass,
  the battery-page bottom fade with its production-method verification, and the zero-padding
  navigation capsule fit.
- 2026-11-22: Synchronized the expanded GPU foreground accents, the shape-invariant lyric
  repaint fix, and the liquid outlined-text theme, including a 69/69 production-method logic
  regression for the island changes.
- 2026-11-22: Synchronized the small/medium GPU fast path, collapsed capture change, and the
  liquid white-PingFang theme, including a 67/67 production-method logic regression.
- 2026-11-22: Populated architecture, codebase map, testing, current plan, traceability,
  and project behavior from the live-glass implementation and measured results.
- 2026-11-21: Project wiki initialized (schema 1.7.0); project identity and initial audit
  log captured.

## Active Work Items

- None captured. See [implementation/current-plan.md](./implementation/current-plan.md)
  for completed rendering and interaction work and next-change verification guidance.

## Blockers And Open Questions

- No new open question resulted from the 2026-11-22/23 rendering or interaction changes. Three
  non-blocking observations are recorded in [technical/testing.md](./technical/testing.md): the
  pre-existing `NAV_GAP = 12.4` vs `+8` page-height gap (~4 px), the edge-light clip on bright
  backgrounds, and the small-island refraction band's ~3.8x stronger displacement pending a
  real-machine look. The center blur is now a two-pass Gaussian FBO (33 taps × 2), so the two
  FBO passes' cost — previously measured as a small median with a higher p95 — should be
  re-checked against the >=90 fps target on the reference machine. Real-machine blur appearance
  remains pending
  user sign-off. The Finder-bar click blocking was fixed in code and verified by a synthetic
  two-window Z-order test, but still needs the user's real MyDockFinder confirmation.
- See [requirements/open-questions.md](./requirements/open-questions.md).

## Active Alerts

- No active alerts captured.

## Verification Snapshot

- Native clear-center build: 90.219 complete-app swapped frames per second.
- Dense 5x5 Gaussian-center build: 117.045 complete-app swapped frames per second in the
  documented reference scenario.
- Timed hover regression passed at 4.8 seconds (medium only), 5.1 seconds (large), and on
  single click (immediate large). See [technical/testing.md](./technical/testing.md).
- Small/medium GPU fast path and theme change: 67/67 production-method logic assertions passed
  (routing `NoOne`); real-FPS, optical, and physical-interaction checks still pending on the
  reference machine. See [technical/testing.md](./technical/testing.md).
- Expanded GPU foreground accents and lyric repaint fix: 69/69 production-method logic
  assertions passed (routing `NoOne`). See [technical/testing.md](./technical/testing.md).
- Liquid outlined text: 47/47 assertions passed (42 runtime + 5 pixel, routing `NoOne`).
  See [technical/testing.md](./technical/testing.md).
- Liquid menu text: 49/49 assertions passed (routing `NoOne`), including proof that the
  QProxyStyle actually receives `CE_MenuItem`, the dark overlay is absent, and non-liquid themes
  are untouched. Battery bottom fade: verified via ARGB32 `render()` that `DestinationOut`
  erases sibling pixels (routing `NoOne`); real-GPU appearance still pending. See
  [technical/testing.md](./technical/testing.md).
- Page card inset and liquid shadow removal: 15/15 independent assertions (`NoOne`), including
  zero liquid outer strokes vs exactly three non-liquid strokes at widths 6/12/20, all nine pages
  +16 px and < 680 px, unchanged 396 px usable clip-page height, and seven clean theme flips.
- React-style RGB dispersion: 30/30 independent assertions (`NoOne`) plus real GL 3.3 core
  compile/link on the RTX 3060 machine; center fringe-free, +/-16% R/B at the edge, `dispersion=0`
  colorless, three `sampleTiny` calls, premultiplied RGB <= alpha, parameters unchanged. Real-GPU
  appearance and native FPS after the two extra samples pending. See
  [technical/testing.md](./technical/testing.md).
- Edge-hugging band and vivid interior: 35/35 independent assertions (`NoOne`) plus real GL 3.3
  compile; band anchored at sd=0 with fixed cap (12/6/2 px), saturate 1.5, 28-tap budget unchanged,
  both paths' uniforms in parity, 0 <= RGB <= alpha after the `max`/`min` pair. Small-island
  displacement ~1.9 → 7.2 px flagged for a real-machine look. See
  [technical/testing.md](./technical/testing.md).
- Demo-level center blur: 9/9 independent assertions (`NoOne`) plus real GL 3.3 compile; FBO
  checkerboard center std 111.56 → 3.61 (lod 4.6, -96.8%), step-edge sigma ~9.75 px (live ~11.31),
  `hiTex` active with all mips framebuffer-complete, 31/31 edge-no-regression, samples 28 → 6.
  Per-frame `generateMipmap` ~0.52 ms median / 1.46 ms p95 flagged as a >=90 fps risk requiring
  real-machine `frameSwapped` recheck. See [technical/testing.md](./technical/testing.md).

## Stale Or Placeholder Areas

- Several requirements, deployment, security, sources, intake, and analysis scaffolds have
  not yet been populated. The architecture, codebase-map, testing, and current-plan pages
  are no longer placeholders.

## Last Scan

- No full repository scan captured. The 2026-11-22 update was a targeted synchronization
  of the liquid-glass rendering, configuration, and hover-interaction source paths.
