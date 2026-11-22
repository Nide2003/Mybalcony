---
id: CURRENT-PLAN
type: note
status: active
title: Current Plan
created: '2026-11-21'
updated: '2026-11-22'
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
confidence: confirmed
---

# Current Plan

## Active Work

No active liquid-glass work item remains from the 2026-11-22 rendering and interaction
requests. The normal application configuration is hover-expanded and unpinned.

## Completed

- Rebuilt the outer liquid refraction from a rounded-rectangle SDF and analytic gradient.
- Replaced static/repeated cropping with live DXCam desktop capture.
- Removed colored premultiplied-alpha fringes and the GPU readback/upload round trip.
- Moved the active background renderer to a native `QOpenGLWindow` below the Qt foreground.
- Met the 90 FPS complete-application target; the later dense-Gaussian build measured
  117.045 native swapped frames per second in the documented test scenario.
- Replaced sparse center blur that looked like ghosting with a dense 5x5 Gaussian kernel.
- Changed hover behavior to open only medium content; large expansion requires a click or
  at least five seconds of continuous hover.

## Next Change Guidance

Re-run the complete native `frameSwapped` benchmark after changes to capture, texture
upload, shaders, frame scheduling, or window composition. Re-run optical and timed-hover
regressions when their respective code paths change. Preserve the CPU/offscreen fallback
and drag fallback unless a replacement is separately verified.
