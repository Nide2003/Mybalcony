# Project Changelog

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
