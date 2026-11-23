# Project Changelog

## 2026-11-23 (refraction no longer spills past the rim; center blur +50%)

- Reported: the refraction band's bottom edge appeared to spill past the island body's bottom
  rim; also asked for the body blur to get 50% stronger.
- Measured first: the SDF coverage is exact — 0 pixels with alpha>0 below the body bottom, left,
  right or top edges (the 1 px row at the edge is `alpha=127`, i.e. antialiasing only). So nothing
  was geometrically overflowing; the spill was the displacement field pushing samples right up to
  the rim, so the outermost texels showed background pulled from further inside and the band
  looked like it bulged past the outline.
- Fix: displacement now converges to zero over the outermost 8 px —
  `dispEase = smoothstep(0.0, 8.0, -sd)` multiplying `displacement`. `smoothstep` gives zero slope
  at the rim, so the glass edge joins the real background outside the outline without a visible
  seam. `coverage` still uses `circleMap`, so the rim stays *clear* (no gaussian edge) — only the
  warping is tapered off, not the clarity. Kernel/`bandWidth`/`lensScale`/dispersion unchanged.
- Blur +50%: `_GAUSSIAN_SIGMA` 1.0 → 1.5 **and** the sampling step 1.0 → 1.5 logical px
  (`_GAUSSIAN_STEP`), so the 5-tap kernel now covers ±3 px instead of ±2 px. Raising sigma alone
  would only flatten the weights without widening the footprint; both must scale together.
  Center weight drops 0.4026 → 0.2921, as expected for the wider kernel.
- Evidence: GL 3.3 compile/link passed; real two-pass pulse in the shared `SeparableBlur` now
  spreads 7 px above the 25%-of-peak threshold (was 3 px) with peak 74; the outermost body row is
  pixel-identical to the zero-displacement render (mean diff 0) while rows deeper in still warp;
  below-body alpha stays 0 on all four edges.
- Real-machine look and FPS pending.

## 2026-11-23 (nav bar auto-inverts on light backgrounds)

- Reported: on an all-white page/wallpaper the nav bar "disappears". Root cause: white text only
  reads through its 1px black outline — the glyph body is 1:1 with a white background (hollow
  outline at 12.5px), and the white icon glyphs, the translucent white active pill and the white
  hover ring vanish the same way. Deepening the outline cannot fix it; the palette itself is
  wrong for light surfaces.
- Added luminance-adaptive inversion scoped to the nav bar. `NavBar._bg_luminance()` samples the
  island's existing full-resolution backdrop snapshot (`backdrop.hi` + `hi_rect`, mapped through
  `_win_origin`, scaled to 1×1) for a Rec.709 average of the area under the capsule; results are
  cached on `(backdrop.version, x, y, w, h)`. `_refresh_light()` flips at `LIGHT_IN=0.58` /
  `LIGHT_OUT=0.46` (hysteresis so a mid-tone edge does not flicker) and only in the liquid theme,
  where the tint is nearly transparent and the surface follows the wallpaper.
- Light state: text/glyph use `theme.glass_ink()` = `LIGHT_INK (24,26,32)`, `outlined_text()`
  gains an `edge` parameter so the stroke turns white (shadow drops to 1/3 to avoid a grey halo),
  the active chip becomes `rgba(0,0,0,30)` and hover `rgba(0,0,0,46)`. `IconButton` gained an
  `on_light` flag (default False) so the nav's right-side buttons invert with it; `_TabGhost`
  inherits the state from `NavBar._on_light`. `Island._on_backdrop()` calls `nav.refresh_light()`
  so a wallpaper/page change re-evaluates the choice even when the island does not repaint.

## 2026-11-23 (nav bar text: PingFang white + black outline, active tab included)

- The user asked for the nav-bar font to also be PingFang white with a black outline. The font
  family and color were already correct (`NavBar`/`_TabGhost` use `ui_font`, which resolves to
  `PingFang SC` first under the liquid theme; `pill_text`/`text` resolve to pure white), so the
  missing piece was the outline: the tab label in `NavBar.paintEvent` was drawn with a bare
  `p.drawText()`. It now goes through `theme.outlined_text()` like every other hand-painted text.
  `_TabGhost.paintEvent` already used `outlined_text` but exempted the active tab
  (`outline=not self.active`); the exemption was removed so dragging floats match too.
- Icon glyphs stay on `icon_font` (Segoe Fluent Icons) and stay unoutlined per project
  convention — the family must never gain PingFang (glyph codepoints would break).
- Verified: py_compile; liquid-theme `ui_font` first family is `PingFang SC`; `pill_text` is
  (255,255,255); `outlined_text` on/off comparison gives 448 vs 0 dark stroke pixels; a real
  offscreen `NavBar` render shows 128 black-outline pixels around 531 white text pixels; source
  audit shows exactly 2 `outlined_text` calls and no active-tab exemption.

## 2026-11-23 (layered optics restored: rim refraction + transparent center 5x5 gaussian)

- After seeing the full-island radial refraction, the user asked to restore the earlier rim
  distortion and add a **transparent 5x5 gaussian blur** to the center instead. The shared
  `_FRAGMENT` went back to the layered architecture: `circleMap` (SDF rim band, `bandWidth`
  edge-only) drives `gradient * displacement` distortion in the rim, and
  `coverage = circleMap * ringFade` mixes the clear refracted rim with a blurred center `base`.
  The full-island uniforms (`clarity`, `refractSpan`, radial field) were removed entirely.
- The center blur is now a **5x5 separable gaussian**: `_GAUSSIAN_TAPS=5` with integer texel
  offsets (-2..2), sigma 1.0 weights ([0.054, 0.244, 0.403, 0.244, 0.054]), and
  `center_blur_radius()` (renamed from `center_blur_sigma`) feeding a 1-logical-px texel step.
  This replaces the 33-tap ±3σ σ9 kernel whose wide spread caused the frosted look.
- Verified: py_compile; real GL 3.3 compile (17 active uniforms, no `clarity`/`refractSpan`);
  real two-pass `SeparableBlur` on a single white pulse gives peak ≈41 (=255·0.4026²) with a
  3 px spread vs 29 px for a dense σ9 reference — narrow, energy-concentrated, transparent.
  End-to-end FBO render: center contrast 72.3 (checker still readable), rim 75.4% of pixels
  distorted, max|R-B|=0 (colorless). A/B image confirms rim-only distortion + transparent center.

## 2026-11-23 (refraction now truly spans the island — radial field replaces shallow circleMap)

- The user reported that despite the previous `refractSpan` change, refraction was still visible
  only in the outermost rim. Root cause confirmed numerically: the old `circleMap = 1-sqrt(1-t²)`
  falls off far too fast — on a 200x40 half-size island the center displacement was 0.00 px and
  mid-island (12 px in) only 0.66 px; the earlier verification had wrongly used span=120 while
  the real path fed `min(hw,hh)=40`, masking the problem.
- The shared `_FRAGMENT` now uses a **normalized radial displacement field**: `pn = p/halfSize`,
  `radialDir = normalize(pn)`, `reach = smoothstep(0, refractSpan, length(pn))`, with
  `refractSpan=0.45` fed by both GL paths. Displacement is `thickness*amplitude*reach*0.7` along
  `radialDir`. This makes the field rise from the center and be full-strength well before the rim
  (mid-island ~7.5 px, rim ~10 px), with no axis-aligned dead zone. `gradient` is retained only
  for the edge-light highlight; `clarity=1`, `dispersion=0` and premultiply unchanged.
- Verified: py_compile + real GL 3.3 compile (19 active uniforms); offscreen FBO render at real
  island size showed 60.9% of center-region pixels change when refraction is enabled, and the
  rendered image shows the whole island's checker/stripe warped, not just its rim. Real-machine
  appearance pending.

## 2026-11-23 (full-island clear refraction; center frosted blur removed)

- The user asked whether the refraction band could cover the whole island and, when offered
  choices, picked "全岛清晰折射"; they also said the gaussian blur looked frosted/matte and
  wanted it more transparent. Both shaders (`gpu_widget.py` shared `_FRAGMENT`, used by both
  GL paths) now decouple displacement from clarity with two new uniforms: `clarity` (1 = whole
  island samples the clear `bgTex`, no center gaussian matte) and `refractSpan` (displacement
  falloff radius in logical px, fed `min(hw,hh)` so the field reaches from the edge to center).
  The narrow `bandWidth` is retained only for the edge-light (刃口) highlight, so edge feel is
  unchanged; dispersion stays 0 (colorless) and premultiplied RGB<=alpha still holds.
- `clarity`/`refractSpan` are set in both `_draw_lens` paths (gpu_widget + gpu_window). The demo
  2-pass Gaussian FBO is retained but no longer mixed into the visible island at clarity=1.
- Verified: py_compile OK; GL 3.3 compile/link (19 active uniforms, both new ones active);
  end-to-end FBO render — clarity 0→1 raised center checker contrast 3.54→120.27 (matte gone),
  old edge-only span=12 changed 0/5120 center-region pixels vs no-displacement while full
  span=120 changed 433/5120 (field reaches center), and max |R-B|=0 (colorless). Real-machine
  look and native FPS pending.

## 2026-11-23 (submenu no longer covered by island; control tiles/sliders swapped and equalized)

- Bug: the auto-raise poll (`Island._poll_hover` → `_raise_topmost`) re-lifted the island to the
  topmost group every 150/300 ms whenever hit-testing found a non-island window under the cursor.
  A visible submenu is exactly such a window, so the island was raised over its own popup menu and
  first-level buttons bled through the second-level menu. Added `Island._popup_open()` — checks
  `QApplication.activePopupWidget()` plus visible `QMenu`/`CCPanel`/`LookupPopup` top-level windows —
  and `_raise_topmost()` now returns early while any such layer is showing, so the popup stays on
  top; raising resumes as soon as it hides.
- The control page swapped its two columns: the 2×2 tile grid is now on the LEFT, the three sliders
  (volume/brightness/scale) on the RIGHT. The tile widget and a fixed-height slider widget are both
  pinned to `TILE*2+15` (251 px) so the two columns share identical top/bottom edges instead of the
  slider column standing taller.
- Verified: py_compile OK; offscreen assertions — `_popup_open` true for visible QMenu/CCPanel and
  false once hidden, tile grid at layout index 0 / sliders at 1, both columns 251 px. Real-machine
  confirmation of the menu Z-order and control layout pending.

## 2026-11-23 (2-pass separable Gaussian replaces ghosting golden-angle disc)

- The user's real-machine screenshots showed "全重影" on browser text behind the glass. Root cause:
  the 16-tap golden-angle disc is a sparse single-pass sampler; each tap hits a shifted glyph copy,
  producing ~16 translucent copies. Replaced with `SeparableBlur` — the demo dialog's 2-pass
  separable Gaussian FBO (33-tap ±3σ `exp(-0.5x²)`, H then V) which gives a continuous gaussian
  with no discrete copies. `CENTER_BLUR_SIGMA = 9` logical px × measured density (not dpr).
- The lens shader now has two background samplers: only the center `base` uses the blurred texture;
  `refracted` and dispersion keep the clear `bgTex` so the edge squeeze survives (the earlier
  fully-blurred version was removed at the user's request). `dispersion = 0`, `bandWidth` 3.6× and
  the body-based SDF are unchanged. Both GL paths share `_FRAGMENT`/`SeparableBlur`.
- Verified: 33 weights sum 1.0; GL 3.3 compile (LENS 17 / BLUR 4 uniforms); end-to-end 4px-stripe
  render collapsed 0/255 source amplitudes to a 125-130 field (±5), i.e. no ghost copies.

## 2026-11-23 (demo golden-angle disc gaussian restores center blur)

- The user asked to bring back the earlier 5x5 gaussian and, offered alternatives, chose the more
  delicate option. Implemented `liquid-glass-react`'s `generateGaussianDisc()` in `_make_blur_gather()`:
  16 taps on the golden spiral (`pi*(3-sqrt(5))`), `r = 3*sqrt((i+0.5)/N)` sigma units, weights
  `exp(-0.5*r²)` normalized to 1.0, injected into the shared `_FRAGMENT` as `blurBg()`.
  `CENTER_BLUR_RADIUS = 9.0` logical px × dpr → `blurRadiusPx`; offsets scale by
  `blurRadiusPx/hiRect.zw`. Only the center `base` is blurred; `refracted`/dispersion stay on the
  clear `sampleBg()` so the edge squeeze remains visible. No mip or FBO pipeline.
- Verified: 16 weights sum to 1.0; GL 3.3 compile with 17 uniforms (`blurRadiusPx` active);
  end-to-end checker render — center std 119.81 → 27.08, gray levels 3 → 16 with blur on.
  Replaces the fully-clear center that had followed the blur removal.

## 2026-11-23 (edge color dispersion turned off — colorless refraction)

- The user said "I don't need color". Both GL paths changed `dispersion` from 0.16 to 0; with
  `split = dispersion * circleMap = 0`, R and B now sample at exactly the G displacement, so the
  refraction ring has no color fringe. The three-channel shader structure is retained (inert),
  and `thickness`/`bandWidth`/`amplitude` are unchanged.
- Verified: py_compile OK; an end-to-end GL 3.3 render on a gray-gradient background showed
  `dispersion = 0.16` produced 1118 pixels with |R-B|>3 (max 10) while `dispersion = 0` produced
  0 such pixels (max |R-B| = 0, max |R-G| = 0).

## 2026-11-23 (inward refraction band widened 1.5×)

- The user asked to widen the inward refraction band by another half. In both GL paths
  `bandWidth` changed from `min(30, max(6, thickness*2.4))` to `min(45, max(9, thickness*3.6))`
  — exactly 1.5×: expanded island 28.8 → 43.2 px, small island 7.2 → 10.8 px. Peak displacement
  (`thickness`/`amplitude`) and `dispersion = 0.16` were left unchanged, so only the band's inward
  spread grows.
- The user also asked why the refraction is colored. The shared shader's `split = dispersion *
  circleMap` samples R at `displacement*(1+split)` and B at `displacement*(1-split)` while G holds
  the base displacement and supplies alpha; at 0.16 the perimeter separates R/B by ±16%. This is
  the intentional demo-following, edge-only RGB dispersion (center stays fringe-free); setting
  `dispersion = 0` makes the ring colorless. No code change was made for the color question.
- Verified: py_compile OK; numeric bandWidth check confirms 1.5× at all three shape sizes.

## 2026-11-23 (refraction band aligned to body on all four sides, widened inward)

- The user reported that top/bottom refraction bands aligned with the border but left/right still
  overhung. Root cause: the SDF was built from `path.boundingRect()`, and the anchored liquid
  bridge (`neck_path`) widens that box by one fillet (~13 px) per side (measured 640 → 666 px),
  while vertical overhang is only ~1.5 px — exactly the observed asymmetry.
- Both GL paths now build the SDF from `island.body` (pure rounded-rect body), pinning the band's
  outer edge to the border on all four sides. Displacement strength stays on the fixed `thickness`
  cap; a new `bandWidth = min(30, max(6, thickness*2.4))` widens the band inward from 12 → 28.8 px
  on the expanded island (3 → 7.2 px small) without increasing peak displacement.
- Verified: py_compile, real GL 3.3 compile with `bandWidth` active (16 uniforms), geometry
  measurement showing the path overhang vs exact body match, and bandWidth scaling.

## 2026-11-23 (topmost Finder-bar click blocking fixed)

- The user reported that hovering the island then clicking did nothing when the MyDockFinder
  bar was on top. Root cause: `HWND_TOPMOST` was the bare Python `-1`, which ctypes passes to
  an undeclared `SetWindowPos` as 32-bit `0xFFFFFFFF` — an invalid handle on x64 — so every
  `_raise_topmost()` call failed silently and the bar stayed above the island.
- `HWND_TOPMOST` is now the correct 64-bit `(HWND)-1` (`ctypes.c_void_p(-1).value`), all
  z-order Win32 calls declare explicit `HWND` argtypes/restype, `_raise_topmost()` leads with
  `SetWindowPos(HWND_TOPMOST, SWP_NOACTIVATE | SWP_NOOWNERZORDER)`, and `_covered()` uses
  physical `GetCursorPos` coordinates for `WindowFromPoint` (Qt `QCursor.pos()` is logical and
  mis-hits at DPI > 1). `_poll_hover()` also raises once on cursor entry and the throttles are
  0.15 s / 0.3 s.
- Verified in a real two-topmost-window test: after the mock Finder bar raises, the island
  raise brings the island back to the top of the hit test on every cycle without stealing focus;
  `WS_EX_TOPMOST` set, `_covered()` returns False on the window and True on the desktop at
  DPR 1.5.

## 2026-11-23 (background Gaussian blur removed)

- The user asked to remove the background Gaussian blur. Deleted the entire two-pass
  `SeparableBlur` FBO pipeline from both GL paths: the class, the generated 33-tap blur shader,
  `center_blur_sigma()` / `CENTER_BLUR_SIGMA`, the `blurredTex` uniform, and all blur state.
- The lens shader's `sampleBg()` now reads `bgTex` — the clear full-resolution `hi` upload — for
  the base and all three dispersion channels. Each GL path uploads `hi` once as `bg` and binds it
  directly; no mip chain, 25-tap, or Gaussian pass runs. Edge refraction (`band/circleMap/split/
  coverage`), saturation 1.5, edge light 0.12, and all optical parameters are unchanged.
- Verification: real GL 3.3 compile (15 active uniforms, `bgTex` active, no blur uniforms); an
  end-to-end render of an 0/255 column checkerboard through the lens with `dispersion=0`,
  `ringFade=0` (pure base) gave center values of only 0/255 with isolated 127 samples at checker
  boundaries — no gradient, confirming the background is clear and unblurred.

## 2026-11-23 (demo-faithful two-pass Gaussian center blur)

- The user reported the three-mip center blur was "not delicate enough" and asked for the demo's
  blur exactly. Diagnosis from `web-prototype/assets/lib-check.js`: the demo dialog does NOT stack
  mips — it uses a real 2-pass separable Gaussian FBO (`separable-blur.ts`, 33 taps, ±3σ), applies
  colorControls before blur, and samples one blurred backdrop for both the base and every
  dispersion path. The earlier mip box-stack produced visible blockiness.
- Added `SeparableBlur` (`gpu_widget.py`, shared by both GL paths): two FBOs/textures, a generated
  33-tap `exp(-0.5*x^2)` kernel normalized to sum 1, H `hi -> tex[0]` then V `tex[0] -> tex[1]`,
  returning the blurred texture as `blurredTex`. `center_blur_lod()` was replaced by
  `center_blur_sigma()` (density-derived texel sigma from `CENTER_BLUR_SIGMA = 9.0`). The lens
  shader's `blurredCenter()` / `sampleTiny()` were replaced by `sampleBg()` reading `blurredTex`
  for base + all three dispersion channels; `hiTex`, `tinyTex`, mip filtering and per-frame
  `generateMipmap` are removed. Fragment uniform samples fell 6 → 4; Gaussian cost moved to the
  dedicated two-pass FBO, and the flagged per-frame mipmap overhead is gone. Edge
  `band/circleMap/split/coverage` logic and all optical parameters are unchanged.
- Verification: 33 taps with weights summing to 1.0 over ±3σ; an end-to-end FBO render of a
  0/255 checkerboard (two input levels) produced 37 distinct grayscale levels in the output row,
  confirming a smooth gradient rather than mip blockiness; both shaders compile and link under
  real GL 3.3 (NVIDIA 621.24). Real-machine appearance and FPS remain pending user confirmation.

## 2026-11-23 (demo-level center blur via hiTex mipmap)

- The liquid center was only ~1-2 logical px blurred (a 5x5 Gaussian at `tinyTexel * 0.8` over
  the downsampled `sharp` texture), while `glass.py:763-766` deliberately skips CPU `_blur` in
  liquid mode. The user reported it was still less blurry than the demo (~9.7 px dialog sigma).
- The previously dead `hiTex` (uploaded/bound but never sampled, optimized out by GL) now carries
  the center: `blurredCenter()` takes three `textureLod` samples at adjacent mips (weights
  0.5/0.25/0.25), hardware trilinear giving a smooth strong blur with no discrete ghosting. `CENTER_BLUR_SIGMA
  = 9.0` and shared `center_blur_lod()` derive the level from measured `hi.width/hiRect.width`
  (live full-resolution vs plate snapshot crop have different densities), clamped to [0, 8].
  Only `hi` uses `GL_LINEAR_MIPMAP_LINEAR`; mip chain regenerates on upload. The 25-tap Gaussian
  and its `tinyTexel` are removed; total samples dropped 28 → 6.
- Edge refraction is untouched: all `band/circleMap/split/sampleTiny×3/coverage` logic and
  parameters remain identical; coverage still selects base in the center and refracted at the
  edge. Verification: 9/9 independent checks passed, including a real FBO render of an 8 px
  checkerboard where center std fell 111.56 → 3.61 (lod 4.6, -96.8%) and the step-edge method
  measured σ≈9.75 px (live lod 5.2 → 11.31 px); `hiTex` is active, all mip levels framebuffer-
  complete, 31/31 edge-no-regression assertions passed, real GL 3.3 compile OK. A performance
  microbenchmark measured ~0.52 ms median (1.46 ms p95) for the new per-frame `generateMipmap`;
  with the ~90.2 fps baseline this is a flagged risk requiring a real-machine `frameSwapped`
  recheck, not a confirmed regression.

## 2026-11-23 (edge-hugging refraction band, vivid interior)

- The liquid refraction band now anchors to the shape boundary (`sd = 0`) and decays inward,
  and its width is a fixed logical-pixel cap `min(12.0, max(2.0, min(hw,hh)*0.30))` instead of
  the size-relative `min(hw,hh)*0.10` that reached ~17 px on the expanded island and read as an
  outer collar. This matches the demo's fixed 12dp `refractionHeight`. Displacement is
  `thickness * amplitude` with `amplitude = 1.2` (expanded ~14.4 px, small island ~7.2 px — the
  small island is ~3.8x its former ~1.9 px, a flagged visual-risk tradeoff pending a real-machine
  look). `edgeLight` dropped 0.20 → 0.12 so the rim is thin, not a wide bright band.
- The interior now uses the demo's optical model: the graying `film` wash toward alpha was
  replaced by a Rec.709 `saturation = 1.5` boost, and the center Gaussian step went
  `tinyTexel * 1.25` → `* 0.8` (tap count unchanged at 25), keeping live-wallpaper texture vivid
  and legible. Premultiplied output is clamped both ways (`max(rgb, 0)` then `min(rgb, a)`), so
  0 <= RGB <= alpha holds even when saturate drives an extreme channel negative.
- The demo reference was verified in `web-prototype/assets/lib-check.js`: a WebGL/AGSL
  GooseHyperGlass shader port (12dp height / -24dp amount / 2dp blur / 1.5 saturation, SDF
  early-exit), not SVG filters; its 7-path spectral dispersion remains approximated here by
  three channel samples.
- Verification: 35/35 independent static/numeric assertions (`NoOne`) plus real GL 3.3
  compile/link on the RTX 3060 machine; edge anchoring, fixed band cap, saturate 1.5, 28-tap
  sample budget, and both-render-path uniform parity all confirmed. Real-machine appearance and
  native FPS pending.

## 2026-11-23 (React-style RGB dispersion, page card inset, no liquid outer shadow)

- The liquid glass now uses React `liquid-glass-react`-style edge dispersion in the shared
  fragment shader. `split = dispersion * circleMap` (default `dispersion = 0.16`): R/B sample
  at `displacement * (1 +/- split)`, G keeps the base displacement and supplies alpha, using
  three `sampleTiny` calls. The center stays fringe-free; the perimeter separates R/B by
  +/-16%; `dispersion = 0` restores the colorless ring. `amplitude` rose 0.68→0.95 for stronger
  refraction; `thickness`, `ringFade`, `lensScale`, and edge-light coefficient are unchanged. A
  final `min(rgb, a)` keeps premultiplied output legal. Both `gpu_widget.py` and `gpu_window.py`
  set the new uniform. The independent `gpu_glass.py` refractor is not on the live path
  (`direct_gpu = True` bypasses `_refract()`) and was left unchanged. This deliberate edge fringe
  supersedes the earlier "no colored fringe anywhere" rule at the user's explicit direction;
  clean centers and legal premultiplied RGB remain required.
- The three-layer soft black stroke outside the island is disabled for the liquid theme
  (`if not theme.liquid:`); the refraction ring alone provides separation. Non-liquid themes
  keep the original 20/12/6 px strokes.
- All expanded liquid pages are inset one step inside the outer glass via a new
  `PAGE_CARD_INSET = 8` applied in `_content_margin()` and `_place_nav()`. Expanded height grows
  16 px while usable content height is identical; no page clips (largest clip page 494 < 680).
- Verification: page inset/shadow 15/15 (`NoOne`), dispersion 30/30 (`NoOne`) including real
  GL 3.3 compile/link on the RTX 3060 machine; real-machine appearance and native FPS pending.

## 2026-11-23 (liquid menu text, battery bottom fade, nav capsule fit)

- Liquid QMenu items now draw white text with the shared 1 px black stroke and light shadow over
  the **original light glass background** (a dark overlay was implemented then removed at the
  user's request). `_LiquidMenuStyle(QProxyStyle)` takes over `CE_MenuItem`: a minimal QSS with
  only color/font is required so `QStyleSheetStyle` forwards menu items to the proxy (a
  `background` rule makes it swallow them); the proxy draws the selection highlight and text
  while the base style draws icons/checkmarks/arrows. Non-liquid menus are untouched; theme
  switches dress/undress existing menus in both directions.
- The battery page's device list now fades softly into the glass at the scroll bottom. A
  battery-page-only `_EdgeFade` overlay uses `DestinationOut` on the content layer, enabled only
  for liquid + visible native GPU glass (non-liquid/CPU fallback disables it to avoid erasing
  the glass in the same backing store). A 14 px bottom spacer keeps the last card from touching
  the edge; hover/scroll input passes through the overlay. Verified with ARGB32 `render()` that
  the real `DestinationOut` erases sibling pixels; real-GPU appearance still pending.
- The navigation glass capsule now hugs the leftmost tab and rightmost buttons with zero end
  padding (`CAP_PAD` 14 → 0); geometry verification confirmed its edges coincide with the
  content extents. No clipping or overflow.
- Verification: liquid menu 49/49 assertions (`NoOne`), including proof the proxy is actually
  invoked; battery fade verified non-placebo via ARGB32 render (`NoOne`). Real-machine FPS,
  optical, and interaction checks remain pending.

## 2026-11-22 (foreground accents, lyric repaint, outlined text)

- Added the dual-source edge and cursor-following specular spot (`_gpu_liquid_accents()`) to the
  native GPU expanded foreground, matching the CPU `_paint_liquid()` accents that the GPU path
  previously skipped. The expanded pure-GPU early return is now suppressed while the specular
  window is active and a `not self.expanded` guard keeps that window out of the collapsed
  lightweight block, so the highlight repaints every frame including fast cursor exits.
- Fixed frozen shape-invariant foreground animations (most visibly collapsed-state lyric
  sweep). `_update_geometry()` now repaints the Qt foreground when `_foreground_animating()`
  reports media/pet/subtitle/activity, an active expanded specular window, or a visible
  collapsed island, not only when the shape bounding box changes. The 2/3 collapsed
  lightweight throttle is preserved because those frames return before the gate.
- Made liquid-theme body text white with a 1 px black stroke plus a light black shadow via
  `theme.outlined_text()`; non-liquid themes, icon glyphs, and light-surface foregrounds stay
  unchanged. The helper restores the caller's gradient pen, so the lyric sweep is intact.
  Qt QSS has no text stroke, so standard text widgets receive a light drop shadow instead.
- Verified GPU/foreground changes with production-method logic regression: 69/69 assertions
  passed, routing `NoOne`; CPU fallbacks, hover timing, shader/optics, and capture exclusion
  unchanged. Real-FPS, optical, and physical-interaction checks remain for the reference
  machine.

## 2026-11-22 (small/medium GPU fast path and theme)

- Extended the native-GPU settled fast path from the expanded island to the collapsed small and
  medium islands. `_gpu_active()` gates the path on liquid theme + live `NativeGlassWindow` +
  anchored + visible; drag, non-liquid themes, fullscreen-hide, and GPU init failure keep the
  original QPainter fallback. In the stable state with `compact.busy()` false, poke/lift/tilt at
  rest, and the cursor beyond 96 px from the island body, 2 of every 3 ticks are GPU-only
  frames and the third runs the full path to preserve breathing, edge shimmer, and `look`/`near`
  at about 30 fps; near-cursor, continuous animation, and press/drag always take full frames.
- Removed the collapsed-state `min(blur_fps, 12)` capture clamp for the native-GPU path: small
  and medium islands now capture at the same `blur_fps` target as the expanded island. Non-GPU
  and non-liquid fallbacks keep the low-frequency capture behavior.
- Changed the liquid-glass palette text color to white `(255,255,255)` and made `ui_font()`
  prefer PingFang SC (`LIQUID_UI_FAMILIES` / `LIQUID_NUM_FAMILIES`) for that theme. Light-surface
  foregrounds (menu text, switch foreground) stay dark for contrast; the Segoe icon font is
  unchanged. QSS font-family strings in `liquid.py` and `lookup.py` now use `theme.font_css()`.
- Verified via production-method logic regression: 67/67 assertions passed, routing `NoOne`;
  hover timing, shader/optics, capture exclusion, and drag/CPU fallbacks unchanged. Real-FPS,
  optical, and physical-interaction checks remain to be re-run on the reference machine.

## 2026-11-22

- Rebuilt liquid outer refraction using rounded-rectangle SDF, analytic gradients, and
  circle-map displacement; retained zero central lens displacement and valid premultiplied
  alpha. Replaced static background reuse with live DXCam BGRA capture.
- Added the active `NativeGlassWindow` OpenGL 3.3 background below the Qt foreground,
  direct `QImage.constBits()` texture upload, capture exclusion for both windows, and a
  settled expanded-state scheduling fast path. Removed the direct path's GPU readback and
  QPainter re-upload round trip.
- Verified the clear-center native build at 90.219 complete-app swapped frames per second.
  Earlier offscreen and `QOpenGLWidget` routes did not meet the target and are not the
  active architecture.
- Replaced sparse 3x3 center blur that looked like ghosting with a dense 5x5 Gaussian
  kernel at 1.25-texel spacing. The outer ring continues to use sharp refraction sampling;
  the resulting build measured 117.045 native swapped frames per second in the documented
  reference scenario.
- Changed `island.hover_expand_ms` to 5000 in defaults and runtime config. Hover now opens
  only medium compact content; clicking or hovering continuously for at least five seconds
  opens the large island. Timed regression passed for 4.8 s, 5.1 s, and single-click cases.
- Restored normal hover/unpinned configuration after performance scripts and relaunched
  `run.pyw`. Added DXCam and PyOpenGL dependencies to `requirements.txt`.

## 2026-11-21

- Lyrics service (`mybalcony/services/lyrics.py`) now uses a two-source cascade: NetEase Cloud Music first, then LRCLIB (`https://lrclib.net/api`) when NetEase has no lyric. LRCLIB synced LRC is parsed with the existing `parse_lrc`; exact `/get` match is attempted before `/search`, with duration-based ranking.
- Network failures are no longer cached as a permanent "no lyric" result. A failure cooldown (`FAIL_COOLDOWN = 60s`) suppresses repeat requests, after which the track is retried. Confirmed-empty results remain cached for the process lifetime.
- Verified: NetEase regression unchanged (synchronous lyrics still resolve); unreachable LRCLIB raises `ConnectError` and enters the cooldown path; `py_compile` passes.
