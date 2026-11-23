---
id: CURRENT-PLAN
type: note
status: active
title: Current Plan
created: '2026-11-21'
updated: '2026-11-23'
tags:
- implementation
- plan
- liquid-glass
related:
- TECH-ARCHITECTURE
- TECH-TESTING
source_paths:
- mybalcony/ui/island.py
- mybalcony/ui/glass.py
- mybalcony/ui/gpu_window.py
- mybalcony/ui/gpu_widget.py
- mybalcony/ui/theme.py
- mybalcony/ui/nav.py
- mybalcony/ui/pages/bluetooth.py
confidence: confirmed
---

# Current Plan

## Active Work

No active liquid-glass work item remains from the 2026-11-22 rendering and interaction
requests. The normal application configuration is hover-expanded and unpinned.

A follow-up 2026-11-22 request migrated the native-GPU fast path and high-frequency capture to
the small and medium islands and restyled liquid-glass text to white PingFang. A later request
added the dual-source edge and cursor-following specular spot to the expanded GPU foreground,
fixed frozen shape-invariant foreground animations (the lyric sweep), and gave liquid body text
a black stroke plus light shadow. A 2026-11-23 request gave liquid QMenu items the same
white-stroked text over the original light glass (a dark overlay was tried then removed at the
user's direction), added a soft fade at the battery page's scroll bottom, and made the navigation
capsule hug its first tab and last button. A further 2026-11-23 request switched the liquid
glass to a React-demo-style strong-refraction RGB-dispersion look, removed the island's outer
three-layer soft shadow, inset all expanded pages inside the outer glass, and raised the center
blur to the demo's ~9 px level (three `hiTex` mip samples, then a two-pass Gaussian FBO), then
removed all background blur at the user's direction — the clear full-resolution `hi` background
is read directly as `bgTex` by the base and dispersion samples. Code and logic regressions are
complete (67/67, 69/69, 47/47, 49/49, 15/15, 30/30, 35/35, 9/9, plus the battery ARGB32 render
check, real GLSL 3.3 compile/link, and an end-to-end render where an 0/255 checker stays 0/255);
real-FPS, optical, and physical-interaction verification on the reference RTX 3060 / 165 Hz
machine is still pending from the user. All center-blur performance risks are moot with blur
removed. A further 2026-11-23 fix addressed clicks swallowed by a topmost MyDockFinder bar:
`HWND_TOPMOST` is now the 64-bit `(HWND)-1` (the bare `-1` was truncated to an invalid 32-bit
handle, so every raise failed), z-order Win32 calls declare `HWND` signatures, `_covered()` uses
physical `GetCursorPos` pixels, and `_poll_hover()` raises on cursor entry plus a 0.15 s / 0.3 s
throttle.   Verified by a real two-topmost-window Z-order test; real MyDockFinder confirmation is
  pending. A further 2026-11-23 change aligned the refraction band's outer edge to the body
  border on all four sides: the SDF now uses `island.body` rather than `path.boundingRect()`,
  whose anchored neck widened the box ~13 px per side (left/right overhang); a separate
  `bandWidth` (2.4× thickness, cap 30 px) widens the band inward without raising peak
  displacement. Verified by GL 3.3 compile and geometry measurement; real-machine look pending.
  A subsequent 2026-11-23 change widened that band inward another half — `bandWidth` 2.4× →
  3.6× thickness (cap 30 → 45 px, expanded 28.8 → 43.2 px) — leaving peak displacement and
  dispersion unchanged; py_compile and scaling check pass, real-machine look pending.
  The user then said "I don't need color", so both paths set `dispersion = 0` — the ring is
  colorless again (split shader kept but inert). An end-to-end gray-gradient render confirmed
  1118 color-fringe pixels at 0.16 vs 0 at dispersion 0 (max|R-B|=0); py_compile OK, real-machine
  look pending.  Finally the user asked to restore blur and chose the golden-angle option: the
  center now uses a 16-tap demo `generateGaussianDisc` gather (`blurBg`, `blurRadiusPx=9×dpr`),
  refraction stays clear; verified 16 weights sum 1.0, GL 3.3 compile (17 uniforms), and a
  checker render std 119.81 → 27.08 with blur on. The user's screenshots then showed that sparse
  disc sampler ghosted on browser text, so the center blur is now the demo's 2-pass separable
  Gaussian FBO (`SeparableBlur`, 33-tap ±3σ, sigma 9 logical by density), center-only; verified
  weights sum 1.0, GL 3.3 compile (LENS 17 / BLUR 4), and a stripe render collapsing 0/255 to
  125-130 (no ghost copies). Real-machine look and two-pass FPS cost pending.

## Completed

- Rebuilt the outer liquid refraction from a rounded-rectangle SDF and analytic gradient.
- Replaced static/repeated cropping with live DXCam desktop capture.
- Removed colored premultiplied-alpha fringes and the GPU readback/upload round trip.
- Moved the active background renderer to a native `QOpenGLWindow` below the Qt foreground.
- Met the 90 FPS complete-application target; the later dense-Gaussian build measured
  117.045 native swapped frames per second in the documented test scenario.
- Replaced sparse center blur that looked like ghosting with a dense 5x5 Gaussian kernel, then
  a demo-level three-mip `hiTex` blur, then a two-pass Gaussian FBO, then removed all background
  blur at the user's direction so the clear background is shown directly.
- Aligned the refraction band to the body border on all four sides (`island.body` SDF instead of
  the neck-widened `path.boundingRect()`) and widened the band inward via a separate `bandWidth`.
- Fixed topmost-window click blocking: correct 64-bit `HWND_TOPMOST`, explicit Win32 `HWND`
  signatures, physical-pixel hit testing, raise-on-entry, and short re-raise throttles.
- Changed hover behavior to open only medium content; large expansion requires a click or
  at least five seconds of continuous hover.
- Extended the settled GPU fast path to collapsed small/medium islands and lifted their capture
  clamp to the `blur_fps` target when the native GPU background is active.
- Restyled liquid-glass body text to white with PingFang SC preferred; kept light-surface
  foregrounds dark and the Segoe icon font unchanged.
- Added dual-source edge and cursor-following specular accents to the native GPU expanded
  foreground, and made shape-invariant foreground animations repaint while the island shape is
  static so the collapsed lyric sweep stays smooth.
- Gave liquid body text a 1 px black stroke plus a light black shadow through a shared helper
  that preserves gradient pens and excludes icon glyphs and light-surface foregrounds.
- Drew liquid QMenu items in white with the shared stroke over the original light glass, using a
  proxy style whose menu QSS carries only color/font so `CE_MenuItem` reaches the proxy.
- Added a battery-page-only scroll-bottom fade and edge spacer, and made the navigation glass
  capsule hug the first tab and last button.
- Replaced the liquid single-channel ring with React-demo-style edge-only RGB dispersion
  (`dispersion`, default 0.16; R/B shifted +/-16%, clean center, `dispersion=0` disables) while
  keeping premultiplied RGB <= alpha; raised `amplitude` to 0.95.
- Removed the liquid island's external three-layer soft shadow and inset every expanded page
  one step inside the outer glass (`PAGE_CARD_INSET = 8`).
- Anchored the refraction band to the island edge with a fixed 12 px logical cap (small islands
  6 px), and replaced the graying interior wash with the demo's saturation 1.5 + lighter Gaussian
  model; thinned the edge light and enforced 0 <= RGB <= alpha with a two-sided clamp.

## Next Change Guidance

Re-run the complete native `frameSwapped` benchmark after changes to capture, texture
upload, shaders, frame scheduling, or window composition. Re-run optical and timed-hover
regressions when their respective code paths change. Preserve the CPU/offscreen fallback
and drag fallback unless a replacement is separately verified.
