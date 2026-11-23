---
id: TECH-CODEBASE-MAP
type: technical
status: active
title: Codebase Map
created: '2026-11-21'
updated: '2026-11-23'
tags:
- technical
- codebase
- liquid-glass
related:
- TECH-ARCHITECTURE
- TECH-TESTING
source_paths:
- run.pyw
- mybalcony/app.py
- mybalcony/core/config.py
- mybalcony/ui/island.py
- mybalcony/ui/glass.py
- mybalcony/ui/gpu_widget.py
- mybalcony/ui/gpu_window.py
- mybalcony/ui/gpu_glass.py
- mybalcony/ui/compact.py
- mybalcony/ui/theme.py
- mybalcony/ui/liquid.py
- mybalcony/ui/lookup.py
- mybalcony/ui/widgets.py
- mybalcony/ui/nav.py
- mybalcony/ui/ccpanel.py
- mybalcony/ui/pages/home.py
- mybalcony/ui/pages/info.py
- mybalcony/ui/pages/bluetooth.py
- mybalcony/ui/pages/system.py
- mybalcony/ui/pages/tools.py
- requirements.txt
confidence: confirmed
---

# Codebase Map

## Entry And Configuration

- `run.pyw`: silent Windows launcher.
- `mybalcony/app.py`: application assembly and `main()` entry point.
- `mybalcony/core/config.py`: defaults and dotted-path persistence. Relevant defaults are
  `island.blur_fps = 90` and `island.hover_expand_ms = 5000`.
- `config.json`: user-specific runtime configuration; performance and interaction scripts
  may temporarily change it, so normal `hover` / unpinned state must be restored after tests.
- `requirements.txt`: includes `dxcam==0.3.0`, `PyOpenGL>=3.1.10`, and
  `windows-capture==2.0.1` in addition to the Qt/OpenCV/NumPy runtime.

## Island And Interaction

- `mybalcony/ui/island.py`
  - Creates `NativeGlassWindow` for the liquid theme and enables `Backdrop.direct_gpu`.
  - Owns expanded/collapsed geometry, spring animation, foreground painting, z-order, drag
    fallback, and native-background update scheduling.
  - `_tick()` contains the settled-state fast path for all three island states. `_gpu_active()`
    gates it on liquid theme + live native GPU + anchored + visible; the expanded branch is a
    pure GPU-only frame, and the small/medium branch runs 2/3 lightweight frames plus one full
    frame to keep breathing/shimmer/`look`/`near` alive. `_compact_cursor_far()` uses the island
    body (not the transparent window) so near-cursor tracking is not blocked.
  - `_poll_hover()` opens the compact/medium content on hover and expands the large island
    only after `hover_expand_ms`. It also guards against a topmost MyDockFinder bar covering the
    island: on cursor entry, or when `_covered()` reports the physical hit test belongs to
    another window, it calls `_raise_topmost()` (`SetWindowPos` with 64-bit `HWND_TOPMOST`,
    `SWP_NOACTIVATE | SWP_NOOWNERZORDER`). Win32 signatures are declared for `SetWindowPos`,
    `BringWindowToTop`, `WindowFromPoint`, `GetAncestor`, and `GetCursorPos`; `_covered()` uses
    physical `GetCursorPos` coordinates because Qt's `QCursor.pos()` is logical and misses at
    DPI > 1. Raise throttles are 0.15 s (cursor) and 0.3 s (expanded panel center).
  - `_single_click()` expands the large island immediately.
  - `_request_backdrop()` captures at `blur_fps` for expanded or `_gpu_active()` states; the
    old `min(fps, 12)` clamp now applies only to non-GPU/non-liquid fallbacks.
  - `_foreground_animating()` reports shape-invariant foreground animation (media/pet/
    subtitle/activity, active expanded specular window, or a visible collapsed island).
    `_update_geometry()` uses it to repaint the Qt foreground even when the shape is static.
  - `_gpu_liquid_accents()` adds the dual-source edge and cursor-following specular spot to
    the native liquid expanded foreground, mirroring the CPU `_paint_liquid()` layers. The
    expanded specular window suppresses the pure-GPU early return so the highlight repaints
    every frame.
  - `PAGE_CARD_INSET = 8` is added to the liquid content margin in `_content_margin()` and
    `_place_nav()`, so expanded page content sits inside the outer glass card. `page_body_height()`
    absorbs the inset on both vertical edges (+16 px total); usable content height is unchanged.
    Non-liquid themes still use `PAD`.
  - The three-layer soft black stroke shadow outside the island path is guarded by
    `if not theme.liquid:` in `paintEvent()`; liquid relies on the refraction ring for separation,
    non-liquid keeps the original 20/12/6 px strokes.
- `mybalcony/ui/compact.py`
  - Owns small/medium capsule content and `size_hint()`.
  - In MyDockFinder bar mode, `bar_open` exposes the medium content; media mode can show
    three lyric lines without opening the full panel.
  - `busy()` reports whether continuous animation (media/activity/pet/subtitle or a recent view
    change) requires full frame pacing; the GPU fast path yields to it.
- `mybalcony/ui/theme.py`
  - `PALETTES["liquid-glass"]["text"]` is white `(255,255,255)`; `text2`/`text3` inherit it via
    `t2`/`t3` alpha. Light-background foregrounds (`menu`, `on_fg`, unset `pill_fg`) stay dark
    for contrast.
  - `ui_font()` selects `LIQUID_UI_FAMILIES` / `LIQUID_NUM_FAMILIES` (PingFang SC first) when
    `theme.liquid`; `icon_font()` keeps the Segoe icon families only. `font_css()` exposes the
    active text family list to QSS callers. Fonts are fixed at widget construction, so runtime
    theme switches refresh color but not font family.
  - `outlined_text()` draws liquid-theme body text white with a 1 px black stroke and a light
    black shadow (one shadow + four strokes + one body `drawText`); non-liquid themes and
    `outline=False` sites take one plain `drawText()`. It restores the caller's original
    `QPen`, so gradient pens such as the lyric sweep survive. Icon glyphs and light-surface
    foregrounds (`pill_text`, `on_fg`) are excluded. `apply_qss_text_shadow()` attaches
    a light `QGraphicsDropShadowEffect` to standard text widgets (Qt QSS cannot stroke text)
    and removes only its own effect on theme switch. Per-widget files (`compact.py`,
    `widgets.py`, `nav.py`, `ccpanel.py`, `lookup.py`, `pages/*.py`) route body text through
    the helper.
- `mybalcony/ui/liquid.py`, `mybalcony/ui/lookup.py`
  - QSS font-family strings now use `theme.font_css()` instead of a hardcoded family list.
  - `MenuGlass` still paints the original light liquid glass under every QMenu (no dark overlay).
    Liquid menu items are white with the shared stroke via `_LiquidMenuStyle(QProxyStyle)`:
    the menu QSS deliberately contains only color/font (a `background` rule makes
    `QStyleSheetStyle` swallow `CE_MenuItem` instead of forwarding to the proxy). The proxy draws
    the selection highlight and stroked text; the base style draws icons/checkmarks/arrows.
    Theme switches dress/undress existing menus in both directions; non-liquid menus are unchanged.
- `mybalcony/ui/pages/bluetooth.py` (`BatteryPage`)
  - A battery-page-only `_EdgeFade` overlay fades the device list into the glass at the scroll
    bottom using `DestinationOut` on the content layer, enabled only for liquid + visible native
    GPU glass. A 14 px bottom spacer keeps the last card off the edge; the overlay is transparent
    to mouse input. Non-liquid/CPU fallback keeps only the spacer (no fade) to avoid erasing the
    glass in the same backing store.
- `mybalcony/ui/nav.py`
  - `NavBar.capsule_rect()` hugs the leftmost tab and rightmost buttons with `CAP_PAD = 0`;
    the navigation glass strip in `island.py` samples exactly this rect.

## Live Background And Optics

- `mybalcony/ui/glass.py`
  - `LiveDesktop`: thread-owned DXCam capture and latest-frame access.
  - `Backdrop`: screen-region requests, full-resolution/downsampled image publication,
    direct-GPU bypass, and CPU refraction fallback.
  - CPU optical helpers implement rounded-rectangle SDF, analytic gradients, circle-map
    displacement, highlight fields, and premultiplied-alpha handling.
- `mybalcony/ui/gpu_widget.py`
  - Shared GLSL vertex and fragment shaders.
  - Fragment shader implements the continuous SDF refraction band anchored at `sd = 0` and
    decaying inward, plus React-demo-style edge-only RGB dispersion: `split = dispersion *
    circleMap`, R/B sample at `displacement * (1 +/- split)`, G keeps base displacement and
    supplies alpha (3 `sampleTiny` calls). `dispersion = 0` disables the fringe.
  - The SDF is built from `island.body` (pure rounded-rect body), not `path.boundingRect()`:
    the anchored liquid bridge widens the latter by ~13 px per side, which put the left/right
    refraction band outside the border. Body geometry pins all four band edges to the border.
  - Peak displacement is a fixed logical-pixel cap `thickness = min(12.0, max(2.0,
    min(hw,hh)*0.30))` (demo's 12dp refraction height); displacement = `thickness * amplitude`
    with `amplitude = 1.2`. A separate `bandWidth = min(45.0, max(9.0, thickness*3.6))` widens
    how far inward the band `band = clamp(1 - max(-sd,0)/bandWidth, 0, 1)` spreads (43.2 px
    expanded / 10.8 px small; 1.5× the former 2.4× width) without raising the peak displacement.
    Edge-light coefficient is
    0.12. A `max(rgb, 0)` / `min(rgb, a)` pair keeps premultiplied output within 0 <= rgb <= a.
  - Center material: Rec.709 `saturation = 1.5` boost over a **2-pass separable Gaussian FBO**
    blur of the real background — the demo dialog's real pipeline. `SeparableBlur` holds 2 FBOs /
    2 textures; `blur(src,w,h,sigma)` runs `_BLUR_FRAGMENT` (33 taps, ±3σ, `exp(-0.5*x²)` kernel
    from `_gaussian_kernel_1d()`) horizontally `hi -> tex[0]` then vertically `tex[0] -> tex[1]`,
    returning `tex[1]`. Continuous 2D gaussian, no discrete copies (the 16-tap golden-angle disc
    tried just before produced visible ghosting on text and was removed). `_ensure_size` rebuilds
    the FBOs on size change; `blur()` saves/restores FBO, viewport and blend state.
    `CENTER_BLUR_SIGMA = 9.0` logical px → `center_blur_sigma(hi, hiRect)` texels from measured
    density, shared by both GL paths. The lens shader has two samplers: only `base = sampleBlur()`
    (center) reads the blurred texture; `refracted` + dispersion use `sampleBg()` (clear) so the
    edge squeeze stays visible. The earlier three-mip stack and 25-tap 5x5 gaussian were tried and
    superseded. `gpu_window.py` imports `_FRAGMENT`/`_VERTEX`/`SeparableBlur`/`center_blur_sigma`
    and runs the same blur; all textures stay `GL_LINEAR`.
  - Also contains the earlier `GlassGLWidget`; this is not the active native-window path (only
    `gpu_window.py`'s `NativeGlassWindow` is instantiated), but it runs the same `SeparableBlur`
    and sets the same shader uniforms (`dispersion`, `amplitude`) from the shared `_FRAGMENT`.
  - `gpu_glass.py` has its own independent single-texture refractor used only when the native
    GPU path fails (`direct_gpu = False`); it does not carry this dispersion change.
- `mybalcony/ui/gpu_window.py`
  - Active `NativeGlassWindow` top-level OpenGL background.
  - Handles texture allocation/upload, geometry synchronization, capture exclusion, shader
    uniforms, and drawing without readback.
- `mybalcony/ui/gpu_glass.py`
  - Offscreen OpenGL refractor retained for fallback and CPU/GPU semantic comparisons.
- `mybalcony/ui/liquid.py`, `widgets.py`, `nav.py`, and `theme.py`
  - Foreground liquid materials, interactive controls, navigation, and color roles.

## Change-Sensitive Invariants

- Do not reintroduce tangent/normal mixing into the new refraction-ring algorithm.
- Preserve zero central lens displacement and a continuous outer band around all corners. The
  band's outer edge must sit on the body border on all four sides — do not swap `island.body`
  back for `path.boundingRect()` (the anchored neck widens the box left/right). The center must
  remain fringe-free; RGB dispersion is permitted only at the edge via `dispersion * circleMap`,
  and `dispersion = 0` must restore the colorless ring.
- Keep premultiplied RGB within 0 <= RGB <= alpha; saturate can drive extreme channels negative,
  so both `max(rgb, 0)` and `min(rgb, a)` are required. The intentional dispersion must come
  from channel sampling differences, never from illegal premultiplied values.
- Keep the refraction band anchored at the shape boundary (`sd = 0`) with a fixed logical-pixel
  cap; do not revert to a size-relative band that grows into an outer collar on the large island.
- Both top-level windows must be excluded from capture to avoid self-image feedback.
- Do not judge full application FPS from DXCam capture rate, background versions, or shader
  microbenchmarks alone; use actual native `frameSwapped` timing.
- The large-island hover delay is five seconds. A short hover opens only medium content;
  a normal click still opens the large island immediately.
