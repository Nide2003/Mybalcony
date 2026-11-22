---
id: TECH-ARCHITECTURE
type: technical
status: active
title: Architecture
created: '2026-11-21'
updated: '2026-11-22'
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

The center has zero lens displacement, while the outer perimeter remains continuous around
straight edges and rounded corners. Premultiplied-alpha output avoids the earlier colored
fringe caused by RGB values exceeding alpha.

The center uses a dense 5x5 Gaussian kernel over the live downsampled texture. Its sample
spacing is 1.25 texels. This replaced a sparse 3x3 kernel with 2.75-texel spacing, which
visibly produced separated images/ghosting. The outer refraction still samples the sharp
texture, so center blur does not erase the ring's optical detail.

## Frame Scheduling

Expanded, anchored, settled islands use a static fast path that skips repeated spring,
path, and layout recomputation. Legacy background crossfade state is disabled for the
native path. Native paint requests are driven both by the UI frame loop and new-background
notifications; experiments with a single native timer and with 10 ms scheduling were slower
and were not retained.

## Fallbacks

- `gpu_glass.py` retains the offscreen OpenGL refractor and CPU semantic-comparison path.
- `glass.py` retains CPU OpenCV refraction for non-direct rendering and fallback behavior.
- `gpu_widget.py` contains the shared vertex/fragment shaders and the earlier
  `QOpenGLWidget` compositor. The widget compositor is not the active NativeGlassWindow
  path because top-level QWidget/FBO composition limited it to roughly 23 FPS in testing.
- OpenGL 3.3 context creation requires a normal Windows graphics session. Qt's `offscreen`
  platform is not evidence of hardware OpenGL availability.
