# -*- coding: utf-8 -*-
"""ATK N9V2 ULTIMATE 耳机（2.4G 接收器）的电量。

这台设备的协议跟 ATK 鼠标不是一套，也不在公开逆向资料里，是实测摸出来的：

- 接收器有两个厂商接口：`0xFF82`（RID 0x41，可读可写）和 `0xFF90`（RID 0x55，只读）。
- **它不主动上报，也不回答查询**：试过 0x41 通道 + 各种查询帧，一律没有回应。
- 只在耳机状态变化时（开机 / 重连）通过 `0xFF90` 吐一帧：
      55 65 32 02 02 00 00 02 00 00 00 00 01 02
      └RID │  └ 0x32 = 50 = 电量（已和 ATK Hub 显示的值对过）
- 换句话说，电量只能"捡"，捡到一次就存起来。

所以这里的策略是：开机后常驻监听 `0xFF90`，抓到帧就更新并落盘（data/atk_battery.json），
没抓到就沿用上次的值 —— 界面上会注明是几点的读数，不假装是实时的。
"""
from __future__ import annotations

import ctypes
import json
import threading
import time
from ctypes import wintypes as W

from PySide6 import QtCore

from ..core.config import DATA_DIR
from . import usbdev

CACHE = DATA_DIR / "atk_battery.json"
VID = 0x373B
NOTIFY_USAGE = 0xFF90        # 只读的那个接口，状态帧从这里出来
FRAME_RID = 0x55
FRAME_HEADER = 0x65          # 帧里第二个字节：`55 65 32 ...`。只认 RID 会把别的 0x55 帧误当电量
LEVEL_IDX = 2                # 55 65 [32] ...

_GENERIC_READ = 0x80000000
_OPEN_EXISTING = 3
_FILE_FLAG_OVERLAPPED = 0x40000000
_ERROR_IO_PENDING = 997
_INVALID = W.HANDLE(-1).value

_level: int | None = None
_stamp: float = 0.0


def _load() -> None:
    global _level, _stamp
    try:
        d = json.loads(CACHE.read_text("utf-8"))
        lv, ts = int(d.get("level")), float(d.get("ts"))
        if 0 < lv <= 100:
            _level, _stamp = lv, ts
    except Exception:  # noqa: BLE001
        pass


def _save(level: int) -> None:
    global _level, _stamp
    _level, _stamp = level, time.time()
    try:
        CACHE.write_text(json.dumps({"level": level, "ts": _stamp}), "utf-8")
    except Exception:  # noqa: BLE001
        pass


_name_hint = "ATK"

_load()          # 导入就读一次缓存：扫描时不必等监听线程起来


def cached() -> int | None:
    return _level


def cached_note() -> str:
    """给界面用的说明：这是几点的读数，不是实时的。"""
    if _level is None or not _stamp:
        return ""
    return f"开机时读到（{time.strftime('%H:%M', time.localtime(_stamp))}）"


def _find_notify_path() -> str | None:
    try:
        for p in usbdev._paths():
            d = usbdev._describe(p)
            if d and d["vid"] == VID and d["usage"] == NOTIFY_USAGE:
                return p
    except Exception:  # noqa: BLE001
        pass
    return None


class _Overlapped(ctypes.Structure):
    _fields_ = [("internal", ctypes.c_void_p), ("internal_high", ctypes.c_void_p),
                ("offset", W.DWORD), ("offset_high", W.DWORD), ("event", W.HANDLE)]


def _parse(frame: bytes) -> int | None:
    if len(frame) > LEVEL_IDX and frame[0] == FRAME_RID and frame[1] == FRAME_HEADER:
        lv = frame[LEVEL_IDX]
        if 0 < lv <= 100:
            return lv
    return None


class AtkWatcher(QtCore.QObject):
    """常驻监听接收器状态帧。抓到就发 changed(level)。"""

    changed = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop = False
        self._thread: threading.Thread | None = None
        _load()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="atk-headset", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop = True

    # ---------- 监听 ----------
    def _run(self) -> None:
        k32 = usbdev._k32
        k32.ReadFile.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), ctypes.c_void_p]
        k32.CreateEventW.argtypes = [ctypes.c_void_p, W.BOOL, W.BOOL, ctypes.c_wchar_p]
        k32.CreateEventW.restype = W.HANDLE
        k32.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
        k32.CancelIo.argtypes = [W.HANDLE]
        k32.ResetEvent.argtypes = [W.HANDLE]

        while not self._stop:
            path = _find_notify_path()
            if not path:
                time.sleep(8)
                continue
            h = k32.CreateFileW(ctypes.c_wchar_p(path), _GENERIC_READ, 3, None,
                                _OPEN_EXISTING, _FILE_FLAG_OVERLAPPED, None)
            if not h or h == _INVALID:
                time.sleep(5)
                continue
            ev = k32.CreateEventW(None, True, False, None)
            try:
                while not self._stop:
                    buf = (ctypes.c_ubyte * 64)()
                    ov = _Overlapped()
                    ov.event = ev
                    got = W.DWORD(0)
                    k32.ResetEvent(ev)
                    ok = k32.ReadFile(h, buf, 64, ctypes.byref(got), ctypes.byref(ov))
                    if not ok:
                        if ctypes.get_last_error() != _ERROR_IO_PENDING:
                            break                       # 设备被拔了，出去重找
                        if k32.WaitForSingleObject(ev, 600) != 0:
                            k32.CancelIo(h)
                            continue
                    lv = _parse(bytes(buf[:got.value or 64]))
                    if lv is not None and lv != _level:
                        _save(lv)
                        self.changed.emit(lv)
            except Exception:  # noqa: BLE001
                pass
            finally:
                if ev:
                    k32.CloseHandle(ev)
                k32.CloseHandle(h)
            time.sleep(3)
