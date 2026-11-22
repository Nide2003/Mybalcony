# Change Impact Map

Last updated: 2026-11-22

| Changed Area | Direct Impact | Required Regression | Fallback / Boundary |
| --- | --- | --- | --- |
| `glass.py` live capture and direct-GPU branch | Background freshness and all liquid-glass rendering | DXCam region validity, full-app swap FPS, no self-capture | CPU/offscreen paths remain available |
| `gpu_widget.py` shared fragment shader | Outer refraction and center material | Continuous perimeter, rounded corners, center blur, premultiplied colors | Old tangent/normal mixing must not return |
| `gpu_window.py` native renderer | Frame rate, z-order, capture exclusion, texture lifetime | Native `frameSwapped`, foreground visibility, no recursive capture | Drag returns to Island painting path |
| `island.py` static fast path and native integration | UI scheduling and expanded-state responsiveness | Full-app FPS, page lifecycle, drag and collapse behavior | Settled expanded anchored state only |
| `island.py` hover threshold and `core/config.py` defaults | Medium versus large island behavior | 4.8 s medium, >=5 s large, immediate click | `never`, `always`, pin, and play-button behavior retained |
| `requirements.txt` | Runtime dependencies | Windows OpenGL 3.3 context and DXCam creation | Offscreen Qt platform is not a hardware support test |

The center Gaussian change does not intentionally alter outer-ring sampling. The hover
change does not alter hotkey/programmatic expansion or the independent media play button.
