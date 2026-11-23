# Code Traceability Map

Last updated: 2026-11-23

| Behavior / Knowledge | Implementing Source | Verification / Documentation |
| --- | --- | --- |
| Live BGRA desktop capture | `mybalcony/ui/glass.py` — `LiveDesktop`, `Backdrop` | DXCam capture benchmark; complete-app tests in `technical/testing.md` |
| Direct-GPU publication without readback | `mybalcony/ui/glass.py` — `Backdrop.direct_gpu`, `_capture()` | Native `frameSwapped` benchmark |
| Native OpenGL background window | `mybalcony/ui/gpu_window.py` — `NativeGlassWindow` | 90.219 FPS clear-center run; window lifecycle checks |
| Continuous SDF outer refraction | `mybalcony/ui/gpu_widget.py` — `_FRAGMENT`; CPU counterpart in `glass.py` | CPU/GPU semantic comparison and optical regression |
| Dense Gaussian center | `mybalcony/ui/gpu_widget.py` — `gaussianCenter()` | 117.045 FPS native swapped-frame run; appearance-driven sparse-kernel replacement |
| Capture exclusion and background/foreground z-order | `mybalcony/ui/gpu_window.py`, `mybalcony/ui/island.py` | Native startup and lifecycle checks |
| Settled-state GPU fast path (all three islands) | `mybalcony/ui/island.py` — `_tick()`, `_needs_frames()`, `_gpu_active()`, `_compact_cursor_far()`, `_on_backdrop()` | 67/67 production-method logic regression; complete-app swap timing pending on reference machine |
| Collapsed-state high-frequency capture | `mybalcony/ui/island.py` — `_request_backdrop()`; `core/config.py` — `blur_fps` | Production-method logic regression (1/90 vs 1/12 intervals); real capture pending |
| Medium hover / five-second large expansion | `mybalcony/ui/island.py` — `_poll_hover()`; `compact.py` — `bar_open`, `size_hint()` | Timed 4.8 s and 5.1 s interaction regression |
| Immediate click expansion | `mybalcony/ui/island.py` — `_single_click()` | Click branch interaction regression |
| Default 90 FPS and 5000 ms delay | `mybalcony/core/config.py`, `config.json` | Source inspection and normal-process launch |
| Liquid white text and PingFang font | `mybalcony/ui/theme.py` — `PALETTES`, `ui_font()`, `font_css()`; `liquid.py`, `lookup.py` | Offscreen theme smoke check (text color, families, icon font, fallback restore) |
| GPU foreground optical accents (edge + specular) | `mybalcony/ui/island.py` — `_gpu_liquid_accents()`, `paintEvent()`, `_tick()` specular-window guard; `liquid.py` — `dual_edge`, `paint_spec` | 69/69 production-method regression (GPU-only call, clip, gradient pen, early-return gating); real appearance pending |
| Shape-invariant foreground repaint (lyric sweep) | `mybalcony/ui/island.py` — `_foreground_animating()`, `_update_geometry()` gate | 69/69 production-method regression (`update()` on static shape when animating, 2/3 throttle intact); real lyric smoothness pending |
| Liquid outlined text (white + black stroke/shadow) | `mybalcony/ui/theme.py` — `outlined_text()`, `apply_qss_text_shadow()`; body-text call sites in `compact.py`, `widgets.py`, `nav.py`, `ccpanel.py`, `lookup.py`, `pages/*.py` | Offscreen pixel check (dark pixels present in liquid, absent in light), gradient-pen and icon/light-surface exclusion checks |
| Liquid QMenu white-stroked text over light glass | `mybalcony/ui/liquid.py` — `_LiquidMenuStyle(QProxyStyle)`, minimal `MENU_QSS`, `MenuGlass.dress/undress/_on_theme` | 49/49 assertions incl. 9 real `CE_MenuItem` proxy calls, 0 with a QSS background, dark-overlay absence, non-liquid zero pollution; real appearance pending |
| Battery scroll-bottom fade and edge spacer | `mybalcony/ui/pages/bluetooth.py` — `_EdgeFade`, `_BOTTOM_SPACER`, `_install_edge_fade()`, `_update_fade()` | ARGB32 `render()` alpha ramp 242→13 proving real `DestinationOut`; `can_fade` truth table; real-GPU appearance pending |
| Navigation capsule hug | `mybalcony/ui/nav.py` — `CAP_PAD = 0`, `capsule_rect()`; `island.py` — `_nav_strip_rect()` | Geometry assertion (capsule edges == first tab / last button, 69.0/449.0) |

No requirement IDs were invented for this targeted map. Existing user-requested behavior is
linked directly to implementing source and observed evidence.
