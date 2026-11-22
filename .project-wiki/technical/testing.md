---
id: TECH-TESTING
type: technical
status: active
title: Testing
created: '2026-11-21'
updated: '2026-11-22'
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
central lens displacement, valid premultiplied colors, and absence of colored fringe.
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
