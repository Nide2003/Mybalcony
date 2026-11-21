# -*- coding: utf-8 -*-
"""经典蓝牙（耳机 / 音箱）的电量。

Windows 在 HFP（免提协议）里收到耳机上报的电量后，会把它写进「Hands-Free AG」节点上的
一个**未公开** PnP 属性：

    PROPERTYKEY {104EA319-6EE2-4701-BD47-8DDBF425BBE5}, PID 2  (DEVPROP_TYPE_BYTE)
    值 = 0~100

以前这里写着「经典蓝牙系统不提供电量接口」，那是找错了地方：
- 属性挂在 **Hands-Free AG 子节点**上，不在设备主节点（BTHENUM\\DEV_xxx）上，
  所以在主节点上查只会拿到 ERROR_NOT_FOUND(1168)。
- 耳机没连上、或固件不做 HFP 电量上报时，属性不存在（或值为 0）。

实测 OPPO Enco Free4 → 60%，和设置页里显示的一致。
"""
from __future__ import annotations

import ctypes
import re
from ctypes import wintypes as W

_DLL = ctypes.WinDLL("setupapi", use_last_error=True)


class GUID(ctypes.Structure):
    _fields_ = [("a", W.DWORD), ("b", W.WORD), ("c", W.WORD), ("d", ctypes.c_ubyte * 8)]


class PropertyKey(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", W.DWORD)]


class DevInfo(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("ClassGuid", GUID), ("DevInst", W.DWORD), ("Reserved", ctypes.c_void_p)]


_DLL.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, W.HWND, W.DWORD]
_DLL.SetupDiGetClassDevsW.restype = W.HANDLE
_DLL.SetupDiEnumDeviceInfo.argtypes = [W.HANDLE, W.DWORD, ctypes.POINTER(DevInfo)]
_DLL.SetupDiEnumDeviceInfo.restype = W.BOOL
_DLL.SetupDiGetDevicePropertyW.argtypes = [W.HANDLE, ctypes.POINTER(DevInfo), ctypes.POINTER(PropertyKey),
                                           ctypes.POINTER(W.ULONG), ctypes.c_void_p, W.DWORD,
                                           ctypes.POINTER(W.DWORD), W.DWORD]
_DLL.SetupDiGetDevicePropertyW.restype = W.BOOL
_DLL.SetupDiGetDeviceInstanceIdW.argtypes = [W.HANDLE, ctypes.POINTER(DevInfo), W.LPWSTR, W.DWORD,
                                             ctypes.POINTER(W.DWORD)]
_DLL.SetupDiGetDeviceInstanceIdW.restype = W.BOOL
_DLL.SetupDiDestroyDeviceInfoList.argtypes = [W.HANDLE]

_FMTID = GUID(0x104EA319, 0x6EE2, 0x4701,
              (ctypes.c_ubyte * 8)(0xBD, 0x47, 0x8D, 0xDB, 0xF4, 0x25, 0xBB, 0xE5))
_PID_LEVEL = 2
_PRESENT, _ALLCLASSES = 0x02, 0x04

# 实例 ID 里的地址，三种写法都见过：
#   `...&0&BLUETOOTHDEVICE_A8E6E89110B0_C00000000`
#   `BTHENUM\DEV_A8E6E89110B0\...`
#   `BTHENUM\{0000111E-...}_LOCALMFG&0002\8&1D2055FE&0&A8E6E89110B0_C00000000`
_MAC_A = re.compile(r"BLUETOOTHDEVICE_([0-9A-F]{12})", re.I)
_MAC_B = re.compile(r"\\DEV_([0-9A-F]{12})\\", re.I)
_MAC_C = re.compile(r"([0-9A-F]{12})_", re.I)


def _mac_colon(hex12: str) -> str:
    h = hex12.lower()
    return ":".join(h[i:i + 2] for i in range(0, 12, 2))


def levels() -> dict[str, int]:
    """-> {mac: 电量}。只包含真的上报了电量的节点。"""
    out: dict[str, int] = {}
    hdev = _DLL.SetupDiGetClassDevsW(None, None, None, _ALLCLASSES | _PRESENT)
    if not hdev or hdev == W.HANDLE(-1).value:
        return out
    try:
        i = 0
        while True:
            info = DevInfo()
            info.cbSize = ctypes.sizeof(info)
            if not _DLL.SetupDiEnumDeviceInfo(hdev, i, ctypes.byref(info)):
                break
            i += 1

            buf = ctypes.create_unicode_buffer(512)
            need = W.DWORD(0)
            if not _DLL.SetupDiGetDeviceInstanceIdW(hdev, ctypes.byref(info), buf, 512, ctypes.byref(need)):
                continue
            iid = buf.value
            if "BTHENUM" not in iid.upper():
                continue
            m = _MAC_A.search(iid) or _MAC_B.search(iid) or _MAC_C.search(iid)
            if not m:
                continue

            key = PropertyKey(_FMTID, _PID_LEVEL)
            ptype = W.ULONG(0)
            val = ctypes.c_ubyte(0)
            need2 = W.DWORD(0)
            if not _DLL.SetupDiGetDevicePropertyW(hdev, ctypes.byref(info), ctypes.byref(key),
                                                  ctypes.byref(ptype), ctypes.byref(val), 1,
                                                  ctypes.byref(need2), 0):
                continue
            lvl = int(val.value)
            if 0 < lvl <= 100:
                out[_mac_colon(m.group(1))] = lvl
    finally:
        _DLL.SetupDiDestroyDeviceInfoList(hdev)
    return out
