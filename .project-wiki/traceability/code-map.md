# Code Traceability Map

Last updated: 2026-11-22

| Behavior / Knowledge | Implementing Source | Verification / Documentation |
| --- | --- | --- |
| Live BGRA desktop capture | `mybalcony/ui/glass.py` — `LiveDesktop`, `Backdrop` | DXCam capture benchmark; complete-app tests in `technical/testing.md` |
| Direct-GPU publication without readback | `mybalcony/ui/glass.py` — `Backdrop.direct_gpu`, `_capture()` | Native `frameSwapped` benchmark |
| Native OpenGL background window | `mybalcony/ui/gpu_window.py` — `NativeGlassWindow` | 90.219 FPS clear-center run; window lifecycle checks |
| Continuous SDF outer refraction | `mybalcony/ui/gpu_widget.py` — `_FRAGMENT`; CPU counterpart in `glass.py` | CPU/GPU semantic comparison and optical regression |
| Dense Gaussian center | `mybalcony/ui/gpu_widget.py` — `gaussianCenter()` | 117.045 FPS native swapped-frame run; appearance-driven sparse-kernel replacement |
| Capture exclusion and background/foreground z-order | `mybalcony/ui/gpu_window.py`, `mybalcony/ui/island.py` | Native startup and lifecycle checks |
| Settled expanded-state fast path | `mybalcony/ui/island.py` — `_tick()`, `_needs_frames()`, `_on_backdrop()` | Complete-app paint and swap timing |
| Medium hover / five-second large expansion | `mybalcony/ui/island.py` — `_poll_hover()`; `compact.py` — `bar_open`, `size_hint()` | Timed 4.8 s and 5.1 s interaction regression |
| Immediate click expansion | `mybalcony/ui/island.py` — `_single_click()` | Click branch interaction regression |
| Default 90 FPS and 5000 ms delay | `mybalcony/core/config.py`, `config.json` | Source inspection and normal-process launch |

No requirement IDs were invented for this targeted map. Existing user-requested behavior is
linked directly to implementing source and observed evidence.
