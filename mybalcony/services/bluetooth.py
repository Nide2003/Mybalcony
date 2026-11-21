# -*- coding: utf-8 -*-
"""设备电量：BLE 走 GATT，经典蓝牙走 HFP 属性，USB 外设走厂商私有 HID 协议。

BLE 走标准 GATT 电池服务（0x180F）的 Battery Level 特征（0x2A19）。
经典蓝牙耳机（A2DP/HFP）没有 GATT，但系统会把 HFP 上报的电量写进 Hands-Free 节点的
未公开 PnP 属性 —— 见 btprop.py。USB 那边见 usbdev.py。

避开一个坑：从 BluetoothLEDevice 现连设备再发现 GATT 服务，在没有电池服务的设备上会
卡住不返回（实测 >50s）。所以改成先用 GattDeviceService 的 selector 查**系统已缓存**的
电池服务实例，没有就直接跳过，一个设备都不连。
"""
from __future__ import annotations

import asyncio
import re
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from PySide6 import QtCore

from mybalcony.core.bg import run_bg

from . import atkheadset, btprop, usbdev, xinput

BATTERY_SVC = uuid.UUID("0000180f-0000-1000-8000-00805f9b34fb")
BATTERY_LVL = "00002a19-0000-1000-8000-00805f9b34fb"

MAC_TAIL = re.compile(r"([0-9a-f]{2}(?::[0-9a-f]{2}){5})\s*$", re.I)
_CACHE_S = 25.0          # 扫描是阻塞的，别太勤
_SCAN_TIMEOUT = 12.0     # 整次扫描的硬上限

NO_CHANNEL = "设备没有上报电量（未连接或固件不支持）"
# 手柄在蓝牙档会同时冒出「经典蓝牙节点」和「HID 接口」两行，用名字认出来去重
_PAD_ALIAS = re.compile(r"xbox.*(gamepad|controller)|game\s*controller|gamepad|手柄", re.I)


def mac_from_id(dev_id: str) -> str:
    """`Bluetooth#Bluetooth48:51:..-a8:e6:e8:91:10:b0` -> `a8:e6:e8:91:10:b0`"""
    m = MAC_TAIL.search(dev_id or "")
    return m.group(1).lower() if m else ""


# ---------------------------------------------------------------- 枚举
async def _enumerate() -> list[dict]:
    from winrt.windows.devices.enumeration import DeviceInformation
    from winrt.windows.devices.bluetooth import BluetoothAdapter, BluetoothDevice, BluetoothLEDevice

    try:
        if await BluetoothAdapter.get_default_async() is None:
            return []
    except Exception:  # noqa: BLE001
        return []

    rows: dict[str, dict] = {}
    for picker, kind in ((BluetoothDevice.get_device_selector(), "classic"),
                         (BluetoothLEDevice.get_device_selector(), "ble")):
        try:
            devs = await DeviceInformation.find_all_async(picker, [])
        except Exception:  # noqa: BLE001
            continue
        for d in devs:
            mac = mac_from_id(d.id)
            if not mac or mac in rows:
                continue
            rows[mac] = {"name": (d.name or "未知设备").strip(), "mac": mac, "kind": kind,
                         "connected": None, "battery": None, "note": ""}
    return list(rows.values())


async def _probe(rows: list[dict]) -> None:
    """补上连接状态（这一步只建对象、不做服务发现，很快）。"""
    from winrt.windows.devices.bluetooth import BluetoothDevice, BluetoothLEDevice

    for r in rows:
        addr = int(r["mac"].replace(":", ""), 16)
        try:
            if r["kind"] == "ble":
                dev = await BluetoothLEDevice.from_bluetooth_address_async(addr)
            else:
                dev = await BluetoothDevice.from_bluetooth_address_async(addr)
            if dev is not None:
                r["connected"] = int(dev.connection_status) == 1
        except Exception:  # noqa: BLE001
            r["connected"] = None


# ---------------------------------------------------------------- 电量
async def _levels() -> dict[str, int]:
    """-> {mac: 电量}。只处理系统已经枚举出电池服务的设备。"""
    from winrt.windows.devices.bluetooth.genericattributeprofile import GattDeviceService
    from winrt.windows.devices.enumeration import DeviceInformation
    from winrt.windows.storage.streams import DataReader

    sel = GattDeviceService.get_device_selector_from_uuid(BATTERY_SVC)
    found: dict[str, int] = {}
    try:
        insts = await DeviceInformation.find_all_async(sel, [])
    except Exception:  # noqa: BLE001
        return found
    for inst in insts:
        mac = mac_from_id(inst.id)
        try:
            svc = await GattDeviceService.from_id_async(inst.id)
            if svc is None:
                continue
            for ch in await svc.get_characteristics_async():
                if str(ch.uuid) != BATTERY_LVL:
                    continue
                rr = await ch.read_value_async()
                if int(rr.status) == 1 and rr.value is not None:
                    found[mac] = int(DataReader.from_buffer(rr.value).read_byte())
                break
        except Exception:  # noqa: BLE001
            continue
    return found


async def _scan_async() -> list[dict]:
    rows = await _enumerate()
    if rows:
        await _probe(rows)
        # 设备都在，只是没有电池服务：不去碰会卡死的服务发现
        levels = await _levels()
        # 经典蓝牙（耳机）不走 GATT，电量藏在 Hands-Free 节点的未公开 PnP 属性里
        hfp = btprop.levels()
        for r in rows:
            lv = levels.get(r["mac"])
            if lv is None:
                lv = hfp.get(r["mac"])
            if lv is not None:
                r["battery"] = lv
            elif r["kind"] == "classic":
                r["note"] = NO_CHANNEL
            elif r["connected"]:
                r["note"] = "设备未提供电量服务"
            elif r["connected"] is False:
                r["note"] = "未连接"
    # USB / 2.4G 接收器上的外设并进同一个列表（Razer 这类能读电量的走私有 HID 协议）
    try:
        rows.extend(usbdev.scan_rows())
    except Exception:  # noqa: BLE001
        pass
    # ATK 耳机只在状态变化时吐一帧，扫描时未必能问到，用监听线程存下来的上一次读数
    for r in rows:
        if r["battery"] is None and r["kind"] == "usb" and "ATK" in (r["name"] or "").upper():
            lv = atkheadset.cached()
            if lv is not None:
                r["battery"] = lv
                r["note"] = atkheadset.cached_note()
    # XInput 手柄：HID 侧没有电量字段时，退回系统给的档位电量；有线模式下只说明原因
    pads = [r for r in rows if r.get("pad") and r["battery"] is None]
    if len(pads) == 1:
        states = xinput.pad_states()
        if len(states) == 1:
            st = states[0]
            if st["percent"] is not None:
                pads[0]["battery"] = st["percent"]
                pads[0]["note"] = xinput.COARSE_NOTE
            elif st["type"] == xinput.TYPE_WIRED:
                pads[0]["note"] = xinput.WIRED_NOTE
    # 蓝牙档的手柄会同时出现在两个节点里：经典蓝牙（Xbox Wireless Controller）
    # 和 HID 接口（Xbox Bluetooth Gamepad），指向同一只手柄。保留带 XInput 语义的
    # HID 行，丢经典蓝牙那一行，免得列表里同款出现两次。
    if any(r.get("pad") for r in rows):
        rows = [r for r in rows if not (r["kind"] == "classic" and _PAD_ALIAS.search(r["name"] or ""))]
    rows.sort(key=lambda r: (r["battery"] is None, not r["connected"], r["name"].lower()))
    return rows


def scan() -> list[dict]:
    """同步执行，带硬超时（防某个 WinRT 调用把线程拖死）。

    超时/失败直接抛出去，让调用方保留手上已有的列表 —— 以前这里 `return []`，
    定时刷新一超时整页设备就「全部消失」，比读到旧值糟得多。
    """
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        fut = pool.submit(lambda: asyncio.run(_scan_async()))
        return fut.result(timeout=_SCAN_TIMEOUT)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


class BluetoothService(QtCore.QObject):
    updated = QtCore.Signal(list)
    failed = QtCore.Signal(str)
    alert = QtCore.Signal(str, int)          # 设备名, 电量

    LOW = 20          # 低于这个就提醒一次
    RESET = 25        # 回到这个以上才允许再提醒（避免在阈值附近反复弹）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.devices: list[dict] = []
        self._busy = False
        self._pending = False
        self._last = 0.0
        self._alerted: set[str] = set()

    def _check_alerts(self):
        for d in self.devices:
            lv = d.get("battery")
            key = d.get("mac") or d.get("name") or ""
            if lv is None or not key:
                continue
            if lv <= self.LOW:
                if key not in self._alerted:
                    self._alerted.add(key)
                    self.alert.emit(d.get("name") or "设备", int(lv))
            elif lv >= self.RESET:
                self._alerted.discard(key)

    def patch(self, needle: str, level: int, note: str = ""):
        """监听线程拿到新电量时就地更新已有行，不必重扫（扫描要 0.5s）。"""
        hit = False
        for d in self.devices:
            if needle.lower() in (d.get("name") or "").lower():
                d["battery"] = level
                d["note"] = note
                hit = True
        if hit:
            self._check_alerts()
            self.updated.emit(self.devices)

    def refresh(self, force: bool = False):
        import time as _t

        if self._busy:
            # 设备刚插上时热插拔信号可能连发几次，忙的时候记一笔，扫完再补一次
            self._pending = self._pending or force
            return
        if not force and self.devices and _t.monotonic() - self._last < _CACHE_S:
            self.updated.emit(self.devices)
            return
        self._busy = True

        def done(res):
            self._busy = False
            self._last = _t.monotonic()
            self.devices = res
            self._check_alerts()
            self.updated.emit(res)
            if self._pending:
                self._pending = False
                self.refresh(force=True)

        def err(e):
            self._busy = False
            # 超时/失败不清空列表：旧数据比一片空白有用，界面上只标一下失败原因
            self.failed.emit(f"{type(e).__name__}: {e}"[:120])
            if self._pending:
                self._pending = False

        run_bg(scan, on_done=done, on_error=err)
