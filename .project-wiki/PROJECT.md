---
id: PROJECT
type: project
status: active
title: Mybalcony Project Overview
created: '2026-11-21'
updated: '2026-11-22'
tags:
- project
related: []
source_paths:
- README.md
- config.example.json
- mybalcony/app.py
confidence: confirmed
---

# Project Overview

## Purpose

Mybalcony is a Dynamic Island-style desktop widget for Windows 10/11. It renders a liquid
glass capsule anchored to a screen edge. Hover opens a compact medium island; clicking or
continuously hovering for five seconds expands the full panel of music, messages, weather,
stocks, system controls, device battery, clipboard, and translation modules. The goal is to
provide macOS-like glanceable information without occupying desktop space, using native Qt
foreground controls and an OpenGL live-glass background rather than a web shell.

The upstream project is `github.com/AsamiAkito/wisland` (MIT), deployed locally on
2026-11-20 at `D:\download\wisland`. The local deployment was customized to address
concrete problems (wrong-version lyric matches, capsule embedding into the MyDockFinder
top bar, device battery reading on Windows, iOS-style control tiles). On 2026-11-21 the
project was renamed from **Wisland** to **Mybalcony**: the Python package
`wisland/` became `mybalcony/`, the launcher `wisland.vbs` became `mybalcony.vbs`, and
the README was rebranded. The clone URL in the README still points to the upstream
`wisland` repository.

## Domain Context

- Desktop personalization / system utility for Windows 10 and 11.
- Integrates with OS and third-party data sources: Windows SMTC media sessions, NetEase
  Cloud Music local logs, Windows notifications, Open-Meteo / OpenWeather, Tencent Finance,
  WinRT tethering, WinRT Bluetooth, HID feature reports, and Clash Verge.
- Distribution is source-based: `setup.bat` creates a virtual environment,
  `mybalcony.vbs` launches via `pythonw` without a console window.

## Stakeholders

- **End user**: the person running the widget on a Windows desktop; wants glanceable info
  and low system intrusion.
- **Upstream maintainers**: authors of the MIT-licensed source project.
- **Local maintainer**: the person customizing and running this deployment at
  `D:\download\wisland` under the product name Mybalcony.

## Success Criteria

- Capsule stays anchored to the physical screen edge (including inside a third-party top
  bar) and expands/collapses without visible tearing.
- Hover opens only medium content; the full island opens on click or after five seconds of
  continuous hover.
- Liquid glass keeps a continuous outer refraction ring, zero central lens displacement,
  smooth non-ghosting center blur, and a complete-app target of at least 90 native swapped
  frames per second on the documented reference machine.
- Lyric scrolling matches the actual playing track, with per-line progress sweep and
  bounce on line change.
- Device battery readings use real system data; unreadable devices are labeled with the
  reason rather than showing invented values.
- Control panel tiles expose real Wi-Fi networks, Bluetooth devices, and editable hotspot
  settings.
- Startup is silent (no console window), single-instance, and survives restarts with
  persisted configuration.

## Global Constraints

- Python 3.10+, PySide6/Qt with QPainter foreground controls and native OpenGL 3.3 glass
  rendering; DXCam supplies live BGRA desktop frames. No web view is used.
- Must run on Windows 10/11; several integrations rely on WinRT, Win32 APIs, and SetupAPI.
- Wi-Fi network scanning runs only on panel open: on Windows 11 24H2 `netsh wlan` counts
  as location access and would keep the taskbar location icon lit.
- Certain HID protocols are vendor-private; unsafe probing is avoided because writing
  arbitrary feature reports can desynchronize a receiver.
- Wiki content is written in English; replies to the user follow their language.

## Documentation Note

The upstream-derived `README.md` in the repository root is the user-facing install and
feature guide. This wiki is the agent-readable source of truth. A Chinese background
narrative was written during the earlier Wisland phase but is no longer present in the
repository after the rename; do not reference it as an existing source.

