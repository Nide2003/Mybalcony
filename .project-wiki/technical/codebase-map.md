---
id: TECH-CODEBASE-MAP
type: technical
status: active
title: Codebase Map
created: '2026-11-21'
updated: '2026-11-22'
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
  - `_tick()` contains the settled expanded-state fast path.
  - `_poll_hover()` opens the compact/medium content on hover and expands the large island
    only after `hover_expand_ms`.
  - `_single_click()` expands the large island immediately.
- `mybalcony/ui/compact.py`
  - Owns small/medium capsule content and `size_hint()`.
  - In MyDockFinder bar mode, `bar_open` exposes the medium content; media mode can show
    three lyric lines without opening the full panel.

## Live Background And Optics

- `mybalcony/ui/glass.py`
  - `LiveDesktop`: thread-owned DXCam capture and latest-frame access.
  - `Backdrop`: screen-region requests, full-resolution/downsampled image publication,
    direct-GPU bypass, and CPU refraction fallback.
  - CPU optical helpers implement rounded-rectangle SDF, analytic gradients, circle-map
    displacement, highlight fields, and premultiplied-alpha handling.
- `mybalcony/ui/gpu_widget.py`
  - Shared GLSL vertex and fragment shaders.
  - Fragment shader implements the continuous SDF refraction ring and dense 5x5 Gaussian
    center.
  - Also contains the earlier `GlassGLWidget`; this is not the active native-window path.
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
- Preserve zero central lens displacement and a continuous outer band around all corners.
- Keep premultiplied RGB at or below alpha.
- Both top-level windows must be excluded from capture to avoid self-image feedback.
- Do not judge full application FPS from DXCam capture rate, background versions, or shader
  microbenchmarks alone; use actual native `frameSwapped` timing.
- The large-island hover delay is five seconds. A short hover opens only medium content;
  a normal click still opens the large island immediately.
