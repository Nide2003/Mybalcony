# -*- coding: utf-8 -*-
"""本机电池。用 GetSystemPowerStatus 读，同步、零依赖、开销可以忽略。"""
from __future__ import annotations

import ctypes


class _POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", ctypes.c_ulong),
        ("BatteryFullLifeTime", ctypes.c_ulong),
    ]


def system_battery() -> dict:
    """-> percent(0-100 或 None)、charging、plugged、present。

    BatteryFlag: 1 满 2 低 4 严重 8 充电中 128 无电池 255 未知。
    """
    st = _POWER_STATUS()
    try:
        ok = ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st))
    except Exception:  # noqa: BLE001
        ok = 0
    if not ok:
        return {"present": False, "percent": None, "charging": False, "plugged": False, "low": False}
    flag = int(st.BatteryFlag)
    pct = int(st.BatteryLifePercent)
    present = pct != 255 and flag != 128
    return {
        "present": present,
        "percent": pct if present else None,
        "plugged": int(st.ACLineStatus) == 1,
        "charging": bool(flag & 8),
        "low": bool(flag & 2) or bool(flag & 4),
    }
