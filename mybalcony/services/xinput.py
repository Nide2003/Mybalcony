# -*- coding: utf-8 -*-
"""XInput 手柄的粗档位电量。

Xbox / 兼容手柄的电量不走 HID 通用通道，走 XInput 的 `XInputGetBatteryInformation`。
**它只给四个档位**（空 / 低 / 中 / 满），不是百分比 —— 系统设置里那个小电池也是这么来的。

档位映射取每档的中值：满 100 / 中 50 / 低 20 / 空 5。取中值而不是取上界，是为了不让
"中档"被读成"快满了"（Voltide 项目也是这么定的，实测对得上）。

`BatteryType`：0 未连接 / 1 有线 / 2 碱性 / 3 镍氢 / 4 未知。
只有 2、3 是真电池，才谈得上电量；type=1 是有线（或接收器模拟成有线），XInput 会一起回
`FULL`，那个 100% 是假的，不能显示，只能说明"没有电量数据"。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes as W

_DLLS = ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll")
TYPE_WIRED = 1
TYPE_ALKALINE = 2
TYPE_NIMH = 3
TYPE_UNKNOWN = 4
LEVEL_TO_PCT = {0: 5, 1: 20, 2: 50, 3: 100}     # EMPTY / LOW / MEDIUM / FULL
COARSE_NOTE = "手柄只上报电量档位（低 / 中 / 满）"
WIRED_NOTE = "接收器按 Xbox 有线模式上报，无电量档位"

_lib = None
_tried = False


def _load():
    global _lib, _tried
    if _tried:
        return _lib
    _tried = True
    for name in _DLLS:
        try:
            lib = ctypes.WinDLL(name)
        except Exception:  # noqa: BLE001
            continue

        class Info(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ubyte), ("level", ctypes.c_ubyte)]

        lib.XInputGetBatteryInformation.argtypes = [W.DWORD, ctypes.c_ubyte, ctypes.POINTER(Info)]
        lib.XInputGetBatteryInformation.restype = W.DWORD
        _lib = (lib, Info)
        return _lib
    return None


def pad_states() -> list[dict]:
    """-> [{type, level, percent}]，四个槽位里已连接的手柄。percent 为 None 表示不可换算。"""
    pair = _load()
    if pair is None:
        return []
    lib, info_t = pair
    out: list[dict] = []
    for slot in range(4):
        info = info_t()
        try:
            rc = lib.XInputGetBatteryInformation(slot, 0, ctypes.byref(info))
        except Exception:  # noqa: BLE001
            continue
        if rc != 0:                                  # 1167 = ERROR_DEVICE_NOT_CONNECTED
            continue
        pct = LEVEL_TO_PCT.get(int(info.level)) if int(info.type) in (TYPE_ALKALINE, TYPE_NIMH) else None
        out.append({"slot": slot, "type": int(info.type), "level": int(info.level), "percent": pct})
    return out


def wireless_levels() -> list[int]:
    """-> 已连接的**真电池**手柄各自的档位电量（0~100）。"""
    return [s["percent"] for s in pad_states() if s["percent"] is not None]
