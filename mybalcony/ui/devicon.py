# -*- coding: utf-8 -*-
"""设备图标：按设备类别选 glyph，USB 外设不再一律显示成 U 盘。"""
from __future__ import annotations

from .theme import G

_KIND_GLYPH = {
    "headset": G.HEADPHONE,
    "mouse": G.MOUSE,
    "keyboard": G.KEYBOARD,
    "gamepad": G.GAMEPAD,
    "monitor": G.MONITOR,
    "tv": G.MONITOR,
    "tablet": G.TABLET,
    "speaker": G.VOLUME,
    "webcam": G.IMAGE,
    "microphone": G.LIVE,
    "dock": G.USB,
    "dongle": G.USB,
    "mousemat": G.MOUSE,
    "keypad": G.KEYBOARD,
    "media": G.VOLUME,
}


def dev_glyph(dev: dict) -> str:
    """优先按类别；认不出类别时退回旧的 kind 判断（usb → U 盘，其余 → 蓝牙）。"""
    g = _KIND_GLYPH.get((dev or {}).get("type") or "")
    if g:
        return g
    return G.USB if (dev or {}).get("kind") == "usb" else G.BT
