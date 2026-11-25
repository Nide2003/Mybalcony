# -*- coding: utf-8 -*-
"""USB / 2.4G 无线接收器上的外设电量。

蓝牙走 GATT 或 HFP 属性，USB 这边没有标准通道 —— HID 规范虽然有个「Battery Strength」
（0x0006/0x0020），但多数厂商不实现，各写各的私有协议。所以按优先级试三条路：

1. **标准 HID 电量字段**：设备在 Feature Report 里显式声明了 0x0006/0x0020、0x0085/0x0066
   这类字段就用它（HidP_GetValueCaps 查字段 + HidP_GetUsageValue 取值）。不猜、不误报。
2. **厂商协议**（只做有公开资料、且能确定字节位置的）：
   - Razer：90 字节 Feature Report，command class 0x07 / id 0x80；
   - ATK/VXE 鼠标：usage page 0xFF05，Report ID 0x08，一问一答；
   - 迈从 MCHOSE：0xFF04 使用页 Feature Report，RID 0x06，第 3 字节。
3. 都没有就只列出来标「没有通用电量接口」，绝不硬猜 —— 往接收器乱写数据有掉配对的风险。

实现上用 SetupAPI 拿 HID 接口路径，再走 HidD_* / HidP_* —— 不用 WinRT 的 HidDevice，
因为它对 report id 的处理和这些设备的裸包对不上。
"""
from __future__ import annotations

import ctypes
import json
import time
from ctypes import wintypes as W

from ..core.config import DATA_DIR
from . import atkdev

HID_GUID = "{4D1E55B2-F16F-11CF-88CB-001111000030}"

# 这些是机器内部的 HID 子设备（RGB 控制器、触摸板、虚拟手柄），不该出现在电量列表里
BLOCK_VID = {0x048D, 0x04F3, 0x5E2A}
BLOCK_NAME = ("hidi2c", "vhf", "hid-compliant", "符合 hid", "usb 输入设备", "device(8910)",
              "usb composite device", "usb 复合设备")
# 无线接收器 / 外设关键词：名字里带这些就不必读到电量也占一行
WIRELESS_HINTS = ("dongle", "receiver", "wireless", "2.4g", "接收器", "无线")
# 手柄/摇杆：2.4G 接收器做 XInput 兼容时，HID 接口往往只报「控制」页、没有电量字段，
# 但用户确实插了一个设备，得列出来 —— 否则就是今天这个「插了手柄列表里没有」的问题。
USAGE_GAMEPAD = (0x0001, 0x0005)
USAGE_JOYSTICK = (0x0001, 0x0004)
GAMEPAD_HINTS = ("gamepad", "game controller", "joystick", "手柄", "摇杆", "赛车")
# 这些名字是「接口描述」而不是产品名，做不了行标题（产品名会走 HidD_GetProductString）
GENERIC_NAMES = BLOCK_NAME

RAZER_VID = 0x1532
NO_USB_CHANNEL = "该 USB 设备没有通用电量接口"
NO_PAD_CHANNEL = "手柄没有上报电量（接收器不提供电量通道）"

# HID 标准用途页/用途：按接口用途判设备类别，不依赖品牌 PID 库（雷蛇这类也能认）
USAGE_MOUSE_IFACE = (0x0001, 0x0002)
USAGE_JOY_IFACE = (0x0001, 0x0004)
USAGE_GAMEPAD_IFACE = (0x0001, 0x0005)
USAGE_KEYBOARD_IFACE = (0x0001, 0x0006)
USAGE_CONSUMER_IFACE = (0x000C, 0x0001)


# ---------------------------------------------------------------- Win32 绑定
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_hid = ctypes.WinDLL("hid", use_last_error=True)
_setup = ctypes.WinDLL("setupapi", use_last_error=True)

_setup.SetupDiGetClassDevsW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, W.HWND, W.DWORD]
_setup.SetupDiGetClassDevsW.restype = W.HANDLE
_setup.SetupDiEnumDeviceInterfaces.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                              W.DWORD, ctypes.c_void_p]
_setup.SetupDiEnumDeviceInterfaces.restype = W.BOOL
_setup.SetupDiGetDeviceInterfaceDetailW.argtypes = [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, W.DWORD,
                                                    ctypes.POINTER(W.DWORD), ctypes.c_void_p]
_setup.SetupDiGetDeviceInterfaceDetailW.restype = W.BOOL
_setup.SetupDiDestroyDeviceInfoList.argtypes = [W.HANDLE]

_k32.CreateFileW.argtypes = [ctypes.c_wchar_p, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
_k32.CreateFileW.restype = W.HANDLE
_k32.CloseHandle.argtypes = [W.HANDLE]
_k32.CreateEventW.argtypes = [ctypes.c_void_p, W.BOOL, W.BOOL, ctypes.c_wchar_p]
_k32.CreateEventW.restype = W.HANDLE
_k32.ResetEvent.argtypes = [W.HANDLE]
_k32.ReadFile.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), ctypes.c_void_p]
_k32.ReadFile.restype = W.BOOL
_k32.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
_k32.WaitForSingleObject.restype = W.DWORD
_k32.CancelIo.argtypes = [W.HANDLE]

_hid.HidD_GetAttributes.argtypes = [W.HANDLE, ctypes.c_void_p]
_hid.HidD_GetProductString.argtypes = [W.HANDLE, ctypes.c_void_p, W.ULONG]
_hid.HidD_GetManufacturerString.argtypes = [W.HANDLE, ctypes.c_void_p, W.ULONG]
_hid.HidD_GetPreparsedData.argtypes = [W.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
_hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
_hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
_hid.HidD_GetFeature.argtypes = [W.HANDLE, ctypes.c_void_p, W.ULONG]
_hid.HidD_GetFeature.restype = W.BOOL
_hid.HidD_SetFeature.argtypes = [W.HANDLE, ctypes.c_void_p, W.ULONG]
_hid.HidD_SetFeature.restype = W.BOOL
_hid.HidP_GetValueCaps.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.POINTER(W.ULONG), ctypes.c_void_p]
_hid.HidP_GetValueCaps.restype = W.LONG
_hid.HidP_GetUsageValue.argtypes = [ctypes.c_int, W.USHORT, W.USHORT, W.USHORT,
                                    ctypes.POINTER(W.ULONG), ctypes.c_void_p,
                                    ctypes.c_void_p, W.ULONG]
_hid.HidP_GetUsageValue.restype = W.LONG

_INVALID = W.HANDLE(-1).value


class _Guid(ctypes.Structure):
    _fields_ = [("a", W.DWORD), ("b", W.WORD), ("c", W.WORD), ("d", ctypes.c_ubyte * 8)]


class _IfaceData(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("guid", _Guid), ("flags", W.DWORD), ("reserved", ctypes.c_void_p)]


class _Attrs(ctypes.Structure):
    _fields_ = [("Size", W.ULONG), ("VendorID", W.USHORT), ("ProductID", W.USHORT), ("Version", W.USHORT)]


class _Caps(ctypes.Structure):
    _fields_ = [("Usage", W.USHORT), ("UsagePage", W.USHORT),
                ("InputLen", W.USHORT), ("OutputLen", W.USHORT), ("FeatureLen", W.USHORT),
                ("Reserved", W.USHORT * 17),
                ("LinkCollections", W.USHORT), ("InBtn", W.USHORT), ("InVal", W.USHORT), ("InIdx", W.USHORT),
                ("OutBtn", W.USHORT), ("OutVal", W.USHORT), ("OutIdx", W.USHORT),
                ("FeatBtn", W.USHORT), ("FeatVal", W.USHORT), ("FeatIdx", W.USHORT)]


class _ValueCaps(ctypes.Structure):
    """HIDP_VALUE_CAPS（72 字节，x64）。只需要前几个字段和 LogicalMax。"""

    _fields_ = [("UsagePage", W.USHORT), ("ReportID", ctypes.c_ubyte), ("IsAlias", ctypes.c_ubyte),
                ("BitField", W.USHORT), ("LinkCollection", W.USHORT),
                ("LinkUsage", W.USHORT), ("LinkUsagePage", W.USHORT),
                ("IsRange", ctypes.c_ubyte), ("IsStringRange", ctypes.c_ubyte),
                ("IsDesignatorRange", ctypes.c_ubyte), ("IsAbsolute", ctypes.c_ubyte),
                ("HasNull", ctypes.c_ubyte), ("Reserved", ctypes.c_ubyte),
                ("BitSize", W.USHORT), ("ReportCount", W.USHORT),
                ("Reserved2", W.USHORT * 5),
                ("UnitsExp", W.ULONG), ("Units", W.ULONG),
                ("LogicalMin", W.LONG), ("LogicalMax", W.LONG),
                ("PhysicalMin", W.LONG), ("PhysicalMax", W.LONG),
                ("UsageMin", W.USHORT), ("UsageMax", W.USHORT),
                ("StringMin", W.USHORT), ("StringMax", W.USHORT),
                ("DesignatorMin", W.USHORT), ("DesignatorMax", W.USHORT),
                ("DataIndexMin", W.USHORT), ("DataIndexMax", W.USHORT)]


HIDP_FEATURE = 2


def _paths() -> list[str]:
    """枚举所有 HID 接口的设备路径。"""
    guid = _Guid()
    if ctypes.windll.ole32.CLSIDFromString(ctypes.c_wchar_p(HID_GUID), ctypes.byref(guid)) != 0:
        return []
    hdev = _setup.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, 0x12)  # PRESENT|DEVICEINTERFACE
    if not hdev or hdev == _INVALID:
        return []
    out: list[str] = []
    try:
        i = 0
        while True:
            itf = _IfaceData()
            itf.cbSize = ctypes.sizeof(itf)
            if not _setup.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(guid), i, ctypes.byref(itf)):
                break
            i += 1
            need = W.DWORD(0)
            # 第一次调用必然返回 FALSE + ERROR_INSUFFICIENT_BUFFER，只为拿长度，别当失败
            _setup.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(itf), None, 0,
                                                    ctypes.byref(need), None)
            if need.value <= 0:
                continue
            buf = ctypes.create_string_buffer(need.value + 16)
            ctypes.cast(buf, ctypes.POINTER(ctypes.c_ulong))[0] = 8   # cbSize（64 位下含对齐）
            if not _setup.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(itf), ctypes.byref(buf),
                                                           need, ctypes.byref(need), None):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 8)
            if not path.startswith("\\\\?\\"):
                path = "\\\\?\\" + path.lstrip("?\\")
            out.append(path)
    finally:
        _setup.SetupDiDestroyDeviceInfoList(hdev)
    return out


def _open(path: str) -> int | None:
    h = _k32.CreateFileW(ctypes.c_wchar_p(path), 0, 3, None, 3, 0, None)
    return None if (not h or h == _INVALID) else h


def _read_str(fn, h) -> str:
    buf = ctypes.create_unicode_buffer(256)
    return buf.value.strip() if fn(h, buf, 256) else ""


def _describe(path: str) -> dict | None:
    h = _open(path)
    if h is None:
        return None
    try:
        at = _Attrs()
        at.Size = ctypes.sizeof(at)
        if not _hid.HidD_GetAttributes(h, ctypes.byref(at)):
            return None
        caps = _Caps()
        pp = ctypes.c_void_p()
        if _hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
            _hid.HidP_GetCaps(pp, ctypes.byref(caps))
            _hid.HidD_FreePreparsedData(pp)
        return {"path": path, "vid": at.VendorID, "pid": at.ProductID,
                "name": _read_str(_hid.HidD_GetProductString, h),
                "vendor": _read_str(_hid.HidD_GetManufacturerString, h),
                "usage": caps.UsagePage, "usage_id": caps.Usage,
                "out": caps.OutputLen, "feature": caps.FeatureLen}
    except Exception:  # noqa: BLE001
        return None
    finally:
        _k32.CloseHandle(h)


def _razer_level(path: str, feature_len: int) -> int | None:
    """老接口，保留给「只想知道有没有电量」的地方用。"""
    return _razer_read(path, feature_len)[0]


# ---------------------------------------------------------------- 雷蛇 2.4G 接收器
# 91 字节的 Feature Report 控制通道，线上格式是 OpenRazer 的 razer_report（Windows 在
# 前面补了一个 report id，所以窗口是 91 字节）：
#     0 report id / 1 status / 2 tx / 3..4 剩余包 / 5 协议 / 6 数据长度 / 7 class /
#     8 cmd / 9.. args / 89 CRC(= XOR of 3..88)
# 电量查询 class 0x07 / cmd 0x80：args[0] 是充电标志，**args[1] 才是电量**
# （0~100 百分比，或 0~255 原始值，>100 按 255 换算）。
#
# 两条实测出来的规矩：
#   - 必须用 HidD_SetFeature 把请求"发出去"，再轮询 HidD_GetFeature 拉回复；
#     只 GetFeature 拿到的是上一次留下的缓存帧（实测会读出 cmd 字节 0x80，误当 52%）。
#   - 发完立刻拉到的是 status=1(busy) 的回声，要跳过它继续等 status=2。
#
# status: 0 新命令 / 1 busy / 2 成功 / 3 失败 / 4 超时 / 5 不支持
RAZER_STATUS_OK = 0x02
RAZER_STATUS_FAIL = 0x03
RAZER_STATUS_TIMEOUT = 0x04
RAZER_STATUS_UNSUPPORTED = 0x05
RAZER_STATUS_BUSY = 0x01
RAZER_CMD_CLASS = 0x07
RAZER_CMD_BATTERY = 0x80
NO_RAZER_ANSWER = "设备未应答（接收器在，鼠标多半在休眠）"
RAZER_UNSUPPORTED = "该型号不支持电量查询"


def _razer_report(tx: int, feature_len: int) -> ctypes.Array:
    n = feature_len if feature_len >= 91 else 91
    buf = (ctypes.c_ubyte * n)()
    buf[0] = 0x00          # report id
    buf[1] = 0x00          # status: 新命令
    buf[2] = tx            # 事务号：回复要按它对上
    buf[6] = 0x02          # 数据长度
    buf[7] = RAZER_CMD_CLASS
    buf[8] = RAZER_CMD_BATTERY
    crc = 0
    for i in range(3, 89):
        crc ^= int(buf[i])
    buf[89] = crc
    return buf


def _razer_read(path: str, feature_len: int) -> tuple[int | None, str]:
    """-> (电量, 备注)。备注为空表示读到了；否则是拿不到的原因（休眠 / 不支持 / 异常）。"""
    n = feature_len if feature_len >= 91 else 91
    h = _open(path)
    if h is None:
        return None, "打不开设备（可能被厂商软件独占）"
    try:
        for attempt in range(4):                 # 休眠的鼠标每 120ms 叫一次，四次足够唤醒
            tx = 0x20 + attempt
            req = _razer_report(tx, n)
            if not _hid.HidD_SetFeature(h, req, n):
                return None, "发送失败"
            # 轮询回复：先到的几条是 busy 回声，等带同一个 tx 的终态帧
            deadline = 40                        # 40 × 8ms ≈ 320ms
            status = 0
            for _ in range(deadline):
                buf = (ctypes.c_ubyte * n)()
                if _hid.HidD_GetFeature(h, buf, n) and int(buf[2]) == tx:
                    status = int(buf[1])
                    if status in (RAZER_STATUS_OK, RAZER_STATUS_FAIL,
                                  RAZER_STATUS_TIMEOUT, RAZER_STATUS_UNSUPPORTED):
                        break
                time.sleep(0.008)
            if status == RAZER_STATUS_OK:
                if int(buf[6]) < 2:
                    return None, "应答长度异常"
                raw = int(buf[10])               # args[1]
                if raw <= 0:
                    return None, "读数为 0（设备可能刚上电）"
                lv = raw if raw <= 100 else round(raw * 100 / 255)
                return (lv if 0 <= lv <= 100 else None), ("" if 0 <= lv <= 100 else "读数异常")
            if status == RAZER_STATUS_UNSUPPORTED:
                return None, RAZER_UNSUPPORTED
            if status == RAZER_STATUS_FAIL:
                return None, "设备拒绝查询"
            time.sleep(0.12)
        return None, NO_RAZER_ANSWER
    except Exception:  # noqa: BLE001
        return None, "读取异常"
    finally:
        _k32.CloseHandle(h)



def _blocked(name: str, vid: int) -> bool:
    low = (name or "").lower()
    return vid in BLOCK_VID or not low or any(k in low for k in BLOCK_NAME)


# ---------------------------------------------------------------- 标准 HID 电量字段
# 少数设备在 Feature Report 里显式声明了标准电量字段，这种不用猜私有协议：
# 0x0006/0x0020 Battery Strength、0x0085/0x0066 相对电量、0x0085/0x0065 绝对电量、
# 0x000D/0x003B（触摸板）。
HIDP_STATUS_SUCCESS = 0x00110000
BATTERY_USAGES = {(0x0006, 0x0020), (0x0085, 0x0066), (0x0085, 0x0065), (0x000D, 0x003B)}


def _scale(raw: int, logical_max: int) -> int | None:
    if raw <= 100:
        return raw
    pct = round(raw * 100 / logical_max) if logical_max > 100 else round(raw * 100 / 255)
    return pct if 0 <= pct <= 100 else None


def _standard_level(path: str, feature_len: int) -> int | None:
    """从 Feature Report 里声明了标准电量字段的设备读电量。没有这种字段就返回 None。"""
    if feature_len <= 0:
        return None
    h = _open(path)
    if h is None:
        return None
    pp = ctypes.c_void_p()
    try:
        if not _hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
            return None
        n = W.ULONG(0)
        _hid.HidP_GetValueCaps(HIDP_FEATURE, None, ctypes.byref(n), pp)
        if n.value == 0:
            return None
        arr = (_ValueCaps * n.value)()
        got = W.ULONG(n.value)
        if _hid.HidP_GetValueCaps(HIDP_FEATURE, arr, ctypes.byref(got), pp) != HIDP_STATUS_SUCCESS:
            return None
        for cap in list(arr)[:got.value]:
            # IsRange 为真时联合体首字段是 UsageMin，为假时是 Usage —— 偏移相同，取它都对
            if (cap.UsagePage, cap.UsageMin) not in BATTERY_USAGES:
                continue
            buf = (ctypes.c_ubyte * feature_len)()
            buf[0] = cap.ReportID
            if not _hid.HidD_GetFeature(h, buf, feature_len):
                continue
            val = W.ULONG(0)
            if _hid.HidP_GetUsageValue(HIDP_FEATURE, cap.UsagePage, cap.LinkCollection,
                                       cap.UsageMin, ctypes.byref(val), pp,
                                       buf, feature_len) != HIDP_STATUS_SUCCESS:
                continue
            lv = _scale(int(val.value), int(cap.LogicalMax))
            if lv is not None:
                return lv
        return None
    except Exception:  # noqa: BLE001
        return None
    finally:
        if pp:
            _hid.HidD_FreePreparsedData(pp)
        _k32.CloseHandle(h)


# ---------------------------------------------------------------- 迈从（MCHOSE）
# 0xFF04 使用页上的 Feature Report，Report ID 0x06，第 3 字节是 0~100 电量。
MCHOSE_VID = 0x41E4


def _mchose_level(path: str, feature_len: int) -> int | None:
    n = feature_len if feature_len > 8 else 16
    h = _open(path)
    if h is None:
        return None
    try:
        buf = (ctypes.c_ubyte * n)()
        buf[0] = 0x06
        if not _hid.HidD_GetFeature(h, buf, n):
            return None
        lv = int(buf[3])
        return lv if 0 < lv <= 100 else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        _k32.CloseHandle(h)


# ---------------------------------------------------------------- ATK / VXE 鼠标
# 协议来自公开逆向资料（yszyszysz233/2.4G-battery-viewer、Linux hid-pulsar 驱动）：
# usage page 0xFF05 的接口，输出 64 字节报文，Report ID 0x08：
#     08 7D 72 02 00 01 07 01 00…
# 回复校验 resp[1]==0x72 且 resp[5]==0x07，电量 = resp[7]。
# 注意：本机没有 ATK 鼠标（只有 N9V2 耳机接收器，用的 0xFF82/0xFF90，不接受写），
# 所以这条分支在本机没被真实设备验证过，只对 0xFF05 接口生效。
ATK_VID = 0x373B
ATK_USAGE = 0xFF05
_ATK_REQ = (0x08, 0x7D, 0x72, 0x02, 0x00, 0x01, 0x07, 0x01)


class _Overlapped(ctypes.Structure):
    _fields_ = [("internal", ctypes.c_void_p), ("internal_high", ctypes.c_void_p),
                ("offset", W.DWORD), ("offset_high", W.DWORD), ("event", W.HANDLE)]


_GENERIC_RW = 0x80000000 | 0x40000000
_OPEN_EXISTING = 3
_FILE_FLAG_OVERLAPPED = 0x40000000
_ERROR_IO_PENDING = 997


def _atk_level(path: str, out_len: int) -> int | None:
    """一问一答。读用独立的重叠句柄 + 事件超时，绝不阻塞读（阻塞读同时写会让进程直接死）。"""
    n = out_len if out_len >= 64 else 64
    h = _k32.CreateFileW(ctypes.c_wchar_p(path), _GENERIC_RW, 3, None,
                         _OPEN_EXISTING, _FILE_FLAG_OVERLAPPED, None)
    if not h or h == _INVALID:
        return None
    ev = _k32.CreateEventW(None, True, False, None)
    try:
        req = (ctypes.c_ubyte * n)()
        for i, b in enumerate(_ATK_REQ):
            req[i] = b
        if not _hid.HidD_SetOutputReport(h, req, n):
            return None

        out = (ctypes.c_ubyte * n)()
        ov = _Overlapped()
        ov.event = ev
        read = W.DWORD(0)
        _k32.ResetEvent(ev)
        ok = _k32.ReadFile(h, out, n, ctypes.byref(read), ctypes.byref(ov))
        if not ok:
            if ctypes.get_last_error() != _ERROR_IO_PENDING:
                return None
            if _k32.WaitForSingleObject(ev, 600) != 0:   # 鼠标在休眠时不会应答
                _k32.CancelIo(h)
                return None
        if int(out[1]) != 0x72 or int(out[5]) != 0x07:
            return None
        lv = int(out[7])
        return lv if 0 < lv <= 100 else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        if ev:
            _k32.CloseHandle(ev)
        _k32.CloseHandle(h)


def _is_gamepad(d: dict, name: str) -> bool:
    """手柄 / 摇杆判定：先看 HID 用途页，再看名字（XInput 兼容的接收器只有名字可认）。"""
    if (d.get("usage"), d.get("usage_id")) in (USAGE_GAMEPAD, USAGE_JOYSTICK):
        return True
    low = (name or "").lower()
    return any(k in low for k in GAMEPAD_HINTS)


def _level_of(g: dict) -> int | None:
    return _read_of(g)[0]


def _read_of(g: dict) -> tuple[int | None, str]:
    """-> (电量, 拿不到的原因)。原因只在读不到时非空。"""
    if g["vid"] == RAZER_VID:
        return _razer_read(g["path"], g["feature"])
    if g["vid"] == ATK_VID and g["usage"] == ATK_USAGE:
        lv = _atk_level(g["path"], g["out"])
        return lv, ("" if lv is not None else "设备未应答（多半在休眠）")
    if g["vid"] == MCHOSE_VID:
        lv = _mchose_level(g["path"], g["feature"])
        return lv, ("" if lv is not None else "设备未应答")
    lv = _standard_level(g["path"], g["feature"])
    return lv, ""


# ---------------------------------------------------------------- 最后一次读数
# 2.4G 设备睡着就不应答，但「没应答」不等于「没有电量通道」。读到过一次就记下来，
# 下次问不到时沿用并注明时间 —— 休眠的鼠标仍然能提供信息，而不是显示一个破折号。
LAST_CACHE = DATA_DIR / "usb_battery.json"
_last: dict[str, list] = {}
_last_dirty = False


def _load_last() -> None:
    try:
        raw = json.loads(LAST_CACHE.read_text("utf-8"))
        for k, v in raw.items():
            try:
                lv, ts = int(v["level"]), float(v["ts"])
            except Exception:  # noqa: BLE001
                continue
            if 0 <= lv <= 100:
                _last[str(k)] = [lv, ts]
    except Exception:  # noqa: BLE001
        pass


def _remember(key: str, level: int) -> None:
    global _last_dirty
    old = _last.get(key)
    if old and old[0] == level:
        return
    _last[key] = [int(level), time.time()]
    _last_dirty = True


def _recall(key: str) -> tuple[int, float] | None:
    v = _last.get(key)
    if not v:
        return None
    return int(v[0]), float(v[1])


def _flush_last() -> None:
    global _last_dirty
    if not _last_dirty:
        return
    _last_dirty = False
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        LAST_CACHE.write_text(json.dumps(
            {k: {"level": v[0], "ts": v[1]} for k, v in _last.items()}, ensure_ascii=False), "utf-8")
    except Exception:  # noqa: BLE001
        pass


_load_last()



def _usage_type(usages) -> str | None:
    """按 HID 用途判类别。

    一个设备会挂多个接口（雷蛇鼠标还带键盘和宏接口），按优先级取主类别：
    鼠标 > 手柄 > 键盘 > 媒体键。2.4G dongle 往往同时报鼠标和键盘，鼠标优先即正确答案。
    """
    s = set(usages or ())
    if USAGE_MOUSE_IFACE in s:
        return "mouse"
    if USAGE_JOY_IFACE in s or USAGE_GAMEPAD_IFACE in s:
        return "gamepad"
    if USAGE_KEYBOARD_IFACE in s:
        return "keyboard"
    if USAGE_CONSUMER_IFACE in s:
        return "media"
    return None


def scan_rows() -> list[dict]:
    """USB / 2.4G 外设，返回结构和蓝牙那边一致。

    只要不是机器内部的 HID 子设备，插上来就占一行：读得到电量就给电量，读不到就写原因。
    以前这里按「无线关键词」筛，结果 2.4G 手柄（HID 只报控制页、名字里没有 dongle/receiver）
    被整行丢掉，插了也看不见。
    """
    groups: dict[tuple[int, int, str], dict] = {}
    try:
        for path in _paths():
            d = _describe(path)
            if not d:
                continue
            name = (d["name"] or "").strip()
            vendor = (d["vendor"] or "").strip()
            if not name or _blocked(name, d["vid"]):
                # 产品名拿不到时退回厂商名，总比一整行消失强
                if vendor and not _blocked(vendor, d["vid"]):
                    name = vendor
                else:
                    continue
            key = (d["vid"], d["pid"], name)
            g = groups.get(key)
            if g is None:
                groups[key] = {**d, "name": name, "vendor": vendor, "paths": [d["path"]],
                               "usages": {(d["usage"], d.get("usage_id"))}}
            else:
                g["paths"].append(d["path"])
                g.setdefault("usages", set()).add((d["usage"], d.get("usage_id")))
                # Razer 的电量在 feature report 最长的接口上；ATK 的在 0xFF05 那个接口上
                if d["usage"] == ATK_USAGE:
                    g["path"], g["usage"], g["out"] = d["path"], d["usage"], d["out"]
                elif d["feature"] > g["feature"]:
                    g["path"], g["feature"] = d["path"], d["feature"]
                if _is_gamepad(d, name):
                    g["usage"], g["usage_id"] = d["usage"], d.get("usage_id")
    except Exception:  # noqa: BLE001
        return []

    rows: list[dict] = []
    for g in groups.values():
        level, why = _read_of(g)
        pad = _is_gamepad(g, g["name"])
        cache_key = f"{g['vid']:04x}:{g['pid']:04x}:{g['name']}"
        note = ""
        stale = False
        if level is not None:
            _remember(cache_key, level)
        elif why and why != RAZER_UNSUPPORTED:
            # 问不到（多半是休眠）：有历史读数就沿用，并注明时间
            hit = _recall(cache_key)
            if hit:
                level = hit[0]
                stale = True
                note = "休眠 · 上次读数（" + time.strftime("%H:%M", time.localtime(hit[1])) + "）"
            else:
                note = why
        elif level is None:
            note = why or (NO_PAD_CHANNEL if pad else NO_USB_CHANNEL)
        # 有电量、是手柄、或者名字是真正的产品名 —— 才值得占一行（纯厂商名/接口描述的不列）
        real_name = bool(g["name"]) and g["name"] != g["vendor"]
        if level is None and not (pad or real_name
                                  or any(k in g["name"].lower() for k in WIRELESS_HINTS)):
            continue
        ident = atkdev.identify(g["vid"], g["pid"], g["name"])
        if ident:
            display, dev_type = ident
        else:
            display = g["name"]
            # 名字里写明了就信名字（不少键盘会顺带暴露一个鼠标接口），否则看 HID 接口用途
            dev_type = atkdev.guess_type(g["name"]) or _usage_type(g.get("usages"))
        rows.append({"name": display, "raw_name": g["name"], "type": dev_type, "mac": "",
                     "kind": "usb", "connected": True,
                     "battery": level, "note": note, "pad": pad, "stale": stale,
                     "vid": g["vid"], "pid": g["pid"]})
    _flush_last()
    return rows

