---
id: TECH-ARCHITECTURE
type: technical
status: active
title: Architecture
created: '2026-11-21'
updated: '2026-11-23'
tags:
- technical
- architecture
- liquid-glass
- opengl
related:
- TECH-CODEBASE-MAP
- TECH-TESTING
source_paths:
- mybalcony/ui/island.py
- mybalcony/ui/glass.py
- mybalcony/ui/gpu_widget.py
- mybalcony/ui/gpu_window.py
- mybalcony/ui/gpu_glass.py
confidence: confirmed
---

# Architecture

## Rendering Boundary

Mybalcony uses a hybrid native rendering architecture; it is no longer accurate to describe
all visuals as QPainter-only.

- `Island` remains a `QWidget` top-level window. It owns interaction, shape animation,
  shadows, navigation, page controls, text, and foreground material painted with QPainter.
- `NativeGlassWindow` is a separate frameless `QOpenGLWindow` using an OpenGL 3.3 core
  context. It renders the live glass background immediately below the Qt foreground window.
- Both windows are excluded from desktop capture with `WDA_EXCLUDEFROMCAPTURE`, preventing
  recursive self-capture. Win32 z-order placement keeps the native background behind the
  island. The native window is transparent to input and does not accept focus.
- MyDockFinder's top bar is also a topmost window; if the user clicks it, it can rise above the
  island and swallow clicks. `_poll_hover()` re-raises the island whenever the cursor is inside
  and the physical hit test says another window is on top; it also raises once on cursor entry.
  `_raise_topmost()` uses `SetWindowPos(HWND_TOPMOST, SWP_NOACTIVATE | SWP_NOOWNERZORDER)` to
  restore z-order without stealing focus. `HWND_TOPMOST` is the 64-bit `(HWND)-1`
  (`ctypes.c_void_p(-1).value`): the earlier bare `-1` was truncated by ctypes to 32-bit
  `0xFFFFFFFF`, an invalid handle on x64, so every raise silently failed with return 0 and the
  island stayed buried. All z-order Win32 calls declare explicit 64-bit `HWND` argtypes/restype.
  `_covered()` uses `GetCursorPos` (physical pixels) for `WindowFromPoint`; passing Qt's logical
  `QCursor.pos()` directly hit the wrong location at DPI > 1. Raise throttling is 0.15 s while
  hovering (0.3 s for the expanded panel center) so a click rarely lands before the raise.
- Dragging disables the direct native path and returns to the existing Island painting
  path so drag transforms remain aligned.

## Live Capture And Data Flow

1. `Backdrop` asks `LiveDesktop` for the current physical screen region.
2. DXCam continuously captures BGRA frames on its owning background thread. Cross-thread
   diagnostic code uses `peek()` rather than operating the capture object from the UI thread.
3. `Backdrop._capture()` retains a full-resolution image and produces a downsampled sharp
   image for lens sampling. In `direct_gpu` mode it publishes these images without running
   CPU or offscreen-GPU refraction and without a GPU-to-CPU readback.
4. `NativeGlassWindow.paintGL()` uploads the two `QImage` buffers directly from
   `QImage.constBits()` to OpenGL textures. The shader draws the glass; the Qt window draws
   foreground content independently.

The default liquid capture target is 90 FPS. The background worker no longer applies the
old 45 Hz ceiling; its short sleep guard is 1/120 s.

## Optical Model

The refraction ring is computed independently of the old tangent/normal mixing algorithm.
A rounded-rectangle signed-distance field and its analytic gradient define the entire outer
band. With normalized band coordinate `x`, displacement follows:

`circleMap(x) = 1 - sqrt(1 - x*x)`

The refraction band is anchored to `sd = 0` (the exact rounded-rectangle boundary) and decays
inward, not outward: `band = clamp(1 - max(-sd,0)/bandWidth, 0, 1)` and
`circleMap = 1 - sqrt(1 - band²)` give full effect at the edge and zero one `bandWidth` inside,
so the effect reads as the island edge itself rather than a separate outer ring. The SDF geometry
is built from `island.body` — the pure rounded-rectangle body rect — **not** `path.boundingRect()`.
When the island is anchored to the top edge, the liquid bridge (`neck_path`) widens the path
bounding box by one fillet (~13 px) on each side (measured 640 → 666 px across, with only ~1.5 px
vertical overhang); using that box put the left/right band outside the visible border while
top/bottom looked aligned. Using the body box pins the band's outer edge to the border on all
four sides. Displacement strength and the demo-scale cap stay on `thickness =
min(12.0, max(2.0, min(hw,hh)*0.30))` logical px; a separate `bandWidth =
min(45.0, max(9.0, thickness*3.6))` controls only how far inward the band spreads (12 → 43.2 px
on the expanded island, 3 → 10.8 px on small islands), widening the visual refraction without
increasing the peak displacement. The 3.6 multiplier is 1.5× the earlier 2.4, per the user's
request to widen the band inward by another half. The earlier size-relative `min(hw,hh)*0.10` grew to ~17 px on
the expanded island and looked like an outer collar; that is deliberately not restored.

The center has zero lens displacement, while the outer perimeter remains continuous around
straight edges and rounded corners. The interior follows the demo's optical model: the former
`film` wash toward alpha (which greyed the center) was replaced by a pure Rec.709 saturation
boost `mix(vec3(luma), rgb, 1.5)`. **Current center blur: a 2-pass separable Gaussian FBO** —
the real pipeline behind the `liquid-glass-react` demo dialog, chosen after a 16-tap golden-angle
disc was tried and rejected: on high-contrast browser text the 16 discrete disc taps each land on
a shifted copy of a glyph, so the user saw "all ghosting" (全重影), the exact failure mode of any
sparse single-pass sampler. `SeparableBlur` runs `_BLUR_FRAGMENT` (a 33-tap, ±3σ, `exp(-0.5*x²)`
normalized 1D kernel generated by `_gaussian_kernel_1d()`) twice — H `hi -> tex[0]`, V
`tex[0] -> tex[1]` — producing a genuinely continuous 2D Gaussian with no discrete copies.
`CENTER_BLUR_SIGMA = 9.0` logical px is converted to texels by `center_blur_sigma()` from the
measured texel density (`hi.width / hiRect.width`), since the live path is full physical
resolution while the plate path is a lower-density snapshot crop. The lens shader has two
background samplers: only the center `base = sampleBlur(uvG0)` reads the blurred texture;
`refracted` and all dispersion samples keep reading the clear `bgTex` through `sampleBg()` so the
edge still shows the squeezed structure (this is why the blur is center-only, not the earlier
fully-blurred version that was removed). `SeparableBlur.blur()` saves/restores the FBO binding,
viewport and blend state around the two passes. No mip chain is used. `hi` is uploaded once and
bound as `bgTex`; the blur FBO textures stay `GL_LINEAR`. The edge-light coefficient is 0.12, a
thin rim rather than a wide band.
Premultiplied-alpha output (0 <= RGB <= alpha) is enforced by a `max(rgb, 0)` / `min(rgb, a)`
pair after saturate and edge-light; saturate on extreme colors can drive a channel negative,
which the lower clamp makes explicit. Although a demo-following edge RGB dispersion was added
earlier, the user subsequently said "I don't need color", so the ring is **colorless** again:
both GL paths now set `dispersion = 0`. The shader's channel-split machinery is retained but
inert (with `dispersion = 0`, `split = 0`, so R/B sample at exactly the G displacement).

Following the React `liquid-glass-react` demo, the shared fragment shader can separate the three
channels in the refraction ring only. For normalized band coordinate `x`, `circleMap(x)` is
the edge mask (0 at center, 1 at the perimeter) and `split = dispersion * circleMap`. The R and
B channels sample the clear background at `displacement * (1 + split)` and
`displacement * (1 - split)`; G keeps the unmodified displacement and supplies alpha. The
earlier default `dispersion = 0.16` separated R/B by +/-16% at the perimeter; the center
(`circleMap = 0`) always kept identical channels. **Current state: `dispersion = 0`**, so all
three channels share one displacement and the ring is colorless (this is what the user asked
for). The lens takes one `sampleBlur` (center, from the 2-pass FBO) plus three `sampleBg` calls
(refracted + 2 dispersion channels) on the clear `bgTex`. Both rendering paths set `dispersion` (0), `amplitude`
(now 1.2, up from 0.68 → 0.95 over prior rounds), the fixed `thickness` cap, the derived
`bandWidth` (3.6× thickness, capped 45 px), `ringFade = 1.25`
and `lensScale = 1.0` via the same shared shader. Displacement is `thickness * amplitude`:
~14.4 px on the expanded island (was ~16.4 px) and ~7.2 px on a small island (was ~1.9 px —
the larger side effect of the fixed-band formula, flagged as a visual-risk tradeoff pending
real-machine review).

The demo reference was verified in `web-prototype/assets/lib-check.js`: it is a WebGL/AGSL
shader port (GooseHyperGlass), not SVG filters. Defaults are `refractionHeight = 12dp`,
`refractionAmount = -24dp`, `blurRadius = 2dp`, `saturation = 1.5`, with an SDF early-exit
(`if (-sd) < refractionHeight`) confining refraction to the edge band. The dialog card uses a
higher-quality tier (`dialogBlurRadius = 16dp` light / 8dp dark, `useSeparableBlur`, a two-pass
Gaussian FBO) — the project briefly reproduced that tier, but at the user's direction the
background blur was dropped while keeping the SDF + circleMap refraction model and the demo's
7-path spectral dispersion approximated by three channel samples.

The fringe here is intentional sampling dispersion, not premultiplied overflow: a final
`min(rgb, vec3(a))` after the edge-light add keeps RGB <= alpha. This differs from the earlier
illegal fringe caused by RGB values exceeding alpha.

The center uses a dense 5x5 Gaussian kernel over the live downsampled texture. Its sample
spacing is 1.25 texels. This replaced a sparse 3x3 kernel with 2.75-texel spacing, which
visibly produced separated images/ghosting. The outer refraction still samples the sharp
texture, so center blur does not erase the ring's optical detail.

The liquid island no longer paints the three-layer soft black stroke shadow outside its path;
the refraction ring alone provides separation from the background. Non-liquid themes keep the
original three-stroke shadow unchanged. Liquid page content is additionally inset by
`PAGE_CARD_INSET = 8` inside the glass card, so every expanded page sits one step inside the
outer liquid glass; the expanded height grows by 16 px while the usable content area stays
identical.

## Frame Scheduling

Anchored, settled islands use a static fast path that skips repeated spring, path, and layout
recomputation. This now applies to all three island states when the native GPU background is
active (see `_gpu_active()` in `island.py`), not only the expanded state:

- Expanded: a fully settled island issues only `gpu_view.update()` at an 11 ms interval.
- Small / medium (collapsed): while `compact.busy()` is false, poke/lift/tilt are at rest, and
  the cursor is beyond a 96 px margin from the island body, the lightweight frame runs 2 out
  of every 3 ticks (GPU update only, 11 ms) and every third tick runs the full path so the
  corner breathing, edge shimmer, and small-character `look`/`near` are refreshed at about
  30 fps. Continuous animations, near-cursor tracking, press/drag, or non-GPU fallbacks take
  the normal full frame path.

`_gpu_active()` gates this on `theme.liquid`, a live native `NativeGlassWindow`, anchored
mode, window visibility, and no fullscreen hide; drag, non-liquid themes, and GPU init
failure fall back to the original QPainter path. Legacy background crossfade state is
disabled for the native path. Native paint requests are driven both by the UI frame loop and
new-background notifications; experiments with a single native timer and with 10 ms
scheduling were slower and were not retained.

Collapsed-state capture was previously clamped to `min(blur_fps, 12)`. With the native GPU
background active, the collapsed and medium states now capture at the same `blur_fps` target
as the expanded state, so the live background texture stays equally fresh. Non-liquid themes,
GPU init failure, drag, and fullscreen-hide keep the low-frequency capture behavior.

## Foreground Repaint And Optical Accents

The Qt foreground is painted independently of the native GPU background. `_update_geometry()`
only repainted the foreground when the shape bounding box changed (`old != new`), which froze
all shape-invariant foreground animations — lyric sweep, corner breathing, edge shimmer,
small-character `look`/`near`, and the cursor-following specular highlight. It now also
repaints when `_foreground_animating()` reports `compact.busy()`, an active liquid expanded
specular window (`now < _spec_until`), or a non-hidden collapsed island. Lightweight frames
return earlier in `_tick()` and never reach this gate, so the 2/3 collapsed-state throttle is
unchanged. In the expanded settled state, the pure-GPU early return is suppressed while the
specular window is active, so the highlight is repainted every frame; a `not self.expanded`
guard keeps that expanded window out of the collapsed lightweight block, and the pure-GPU
path resumes once the window expires.

The CPU fallback paints two optical accents — a dual-source edge (`dual_edge`) and a
cursor-following specular spot (`paint_spec`) — inside `_paint_liquid()`, which the native GPU
foreground path did not call. `paintEvent()` now calls `_gpu_liquid_accents()` for the native
liquid expanded foreground, drawing the same two 2D QPainter layers clipped to the island path.
Shaders, background capture, and refraction parameters are untouched; CPU/offscreen/drag
fallbacks still use the original `_paint_glass()` path with no double-drawn accents.

Text in the liquid theme is drawn white with a 1 px black stroke plus a light black shadow.
`theme.outlined_text()` adds the stroke/shadow for liquid-theme body text only (one shadow +
four directional strokes + one body draw call); non-liquid themes and `outline=False` call
sites take a single plain `drawText()`. Icon glyphs and light-surface foregrounds (menu,
`pill_text`, `on_fg`) are excluded. The helper preserves a caller's gradient pen (e.g. the
lyric sweep) by restoring the original `QPen` for the body pass. Qt QSS cannot express a text
stroke, so standard text widgets receive a light `QGraphicsDropShadowEffect` instead.

## Fallbacks

- `gpu_glass.py` retains the offscreen OpenGL refractor and CPU semantic-comparison path.
- `glass.py` retains CPU OpenCV refraction for non-direct rendering and fallback behavior.
- `gpu_widget.py` contains the shared vertex/fragment shaders and the earlier
  `QOpenGLWidget` compositor. The widget compositor is not the active NativeGlassWindow
  path because top-level QWidget/FBO composition limited it to roughly 23 FPS in testing.
- OpenGL 3.3 context creation requires a normal Windows graphics session. Qt's `offscreen`
  platform is not evidence of hardware OpenGL availability.
