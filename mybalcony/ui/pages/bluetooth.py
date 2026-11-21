# -*- coding: utf-8 -*-
"""电量页：列出蓝牙设备、USB / 2.4G 外设与各自电量。

能读到哪条通道看设备：
- BLE：标准 GATT 电池服务（0x180F/0x2A19）。
- 经典蓝牙耳机：HFP 上报的电量被系统写在 Hands-Free 节点的未公开 PnP 属性里（btprop.py）。
- USB / 2.4G 接收器：标准 HID 电量字段 + 厂商私有协议（Razer / ATK / 迈从），
  2.4G 手柄再兜一层 XInput 的四档电量（usbdev.py / xinput.py）。

插拔设备由窗口收到 WM_DEVICECHANGE 后立刻重扫；页面开着时另外每 20s 刷一次状态。
"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..anim import clamp
from ..theme import G, W, icon_font, theme, ui_font
from ..widgets import IconButton, Label, ScrollArea, Themed, hbox, painter, vbox
from ...services.power import system_battery
from .base import Page

Qt = QtCore.Qt


def _level_color(pct: int) -> QtGui.QColor:
    """电量配色：低了转红，中间琥珀，正常用主题前景色。"""
    if pct <= 20:
        return QtGui.QColor(236, 92, 84)
    if pct <= 45:
        return QtGui.QColor(238, 176, 74)
    return theme.text(0.92)


def draw_battery(p: QtGui.QPainter, rect: QtCore.QRectF, pct: int | None) -> None:
    """画一个小电池：外壳 + 正极 + 按电量填充（pct 为 None 时只画空心壳）。"""
    r = QtCore.QRectF(rect.left() + 0.5, rect.top() + 0.5, rect.width() - 4.0, rect.height() - 1.0)
    p.save()
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    p.setPen(QtGui.QPen(theme.text(0.42), 1.1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(r, 3.0, 3.0)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.text(0.42))
    p.drawRoundedRect(QtCore.QRectF(r.right() + 1.2, r.center().y() - 2.0, 2.2, 4.0), 1.0, 1.0)
    if pct is not None:
        inner = r.adjusted(2.0, 2.0, -2.0, -2.0)
        w = inner.width() * clamp(pct / 100.0, 0.0, 1.0)
        if w > 0.5:
            p.setBrush(_level_color(pct))
            p.drawRoundedRect(QtCore.QRectF(inner.left(), inner.top(), w, inner.height()), 1.6, 1.6)
    p.restore()


class BatteryGlyph(QtWidgets.QWidget, Themed):
    def __init__(self, parent=None, w: float = 26, h: float = 13):
        super().__init__(parent)
        self.pct: int | None = None
        self.setFixedSize(int(w), int(h))
        self._hook_theme()

    def set_level(self, pct: int | None):
        self.pct = pct
        self.update()

    def paintEvent(self, e):
        draw_battery(painter(self), QtCore.QRectF(self.rect()), self.pct)


class DeviceRow(QtWidgets.QWidget, Themed):
    """一行：类型图标 + 名称/状态 + 电量。"""

    H = 44.0

    def __init__(self, dev: dict, parent=None):
        super().__init__(parent)
        self.dev = dev
        self.setFixedHeight(int(self.H))
        # 电量读不到的原因（没有电池服务 / 固件不支持）收进 tooltip，行里不再占字
        if dev.get("note"):
            self.setToolTip(f"{dev.get('name') or ''}\n{dev['note']}")
        self._hook_theme()

    def paintEvent(self, e):
        dev = self.dev
        p = painter(self)
        r = QtCore.QRectF(self.rect()).adjusted(0, 1, 0, -1)
        c = theme.card(0.9)
        if theme.liquid:
            from ..liquid import paint_chip
            paint_chip(p, r, 14, c)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(r, 14, 14)

        d = 26.0
        cr = QtCore.QRectF(r.left() + 10, r.center().y() - d / 2, d, d)
        p.setBrush(theme.card(1.6))
        p.drawEllipse(cr)
        p.setFont(icon_font(12))
        p.setPen(theme.text(0.72 if dev.get("connected") else 0.32))
        p.drawText(cr, Qt.AlignmentFlag.AlignCenter,
                   G.USB if dev.get("kind") == "usb" else G.BT)

        # 副标题：只写连接状态，不解释为什么没有电量（说明放在提示里或者干脆不写）
        battery = dev.get("battery")
        if dev.get("connected"):
            sub = "已连接"
        elif dev.get("connected") is False:
            sub = "未连接"
        else:
            sub = "状态未知"

        tx = cr.right() + 10
        # 右侧只有真有电量时才留位置，没有电量的行把宽度让给设备名
        right_w = 86.0 if battery is not None else 10.0
        tw = max(60.0, r.right() - 14 - right_w - tx)
        p.setFont(ui_font(12.5, W.Medium))
        p.setPen(theme.text(0.94 if dev.get("connected") else 0.7))
        fm = QtGui.QFontMetrics(p.font())
        p.drawText(QtCore.QRectF(tx, r.top() + 5, tw, 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(dev.get("name") or "", Qt.TextElideMode.ElideRight, int(tw)))
        p.setFont(ui_font(10.5, W.Normal))
        p.setPen(theme.text3(0.95))
        fm2 = QtGui.QFontMetrics(p.font())
        p.drawText(QtCore.QRectF(tx, r.bottom() - 19, tw, 14),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm2.elidedText(sub, Qt.TextElideMode.ElideRight, int(tw)))

        if battery is None:
            # 拿不到电量的设备（没有电池服务 / 固件不支持上报）：右侧就空着，
            # 连接状态已经写在名称下面了，这里再写一遍"已连接"是重复
            return

        lvl = int(battery)
        p.setFont(ui_font(16, W.Medium, num=True))
        p.setPen(_level_color(lvl))
        val = f"{lvl}%"
        vw = QtGui.QFontMetrics(p.font()).horizontalAdvance(val)
        p.drawText(QtCore.QRectF(r.right() - 14 - vw, r.top(), vw + 2, r.height()),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, val)
        gw, gh = 24.0, 12.0
        draw_battery(p, QtCore.QRectF(r.right() - 14 - vw - 8 - gw, r.center().y() - gh / 2, gw, gh), lvl)


class SystemBatteryCard(QtWidgets.QWidget, Themed):
    """本机电池：比设备行更醒目一点，因为它是这台机器自己的电量。"""

    H = 58.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.info = {"present": False, "percent": None, "charging": False, "plugged": False, "low": False}
        self.setFixedHeight(int(self.H))
        self._hook_theme()

    def set_info(self, info: dict):
        self.info = info or {}
        self.update()

    def _status_text(self) -> str:
        i = self.info
        if i.get("charging"):
            return "充电中"
        if i.get("plugged"):
            return "已接通电源"
        if i.get("low"):
            return "电量偏低"
        return "使用电池"

    def paintEvent(self, e):
        i = self.info
        pct = i.get("percent")
        p = painter(self)
        r = QtCore.QRectF(self.rect()).adjusted(0, 1, 0, -1)
        if theme.liquid:
            from ..liquid import paint_chip
            paint_chip(p, r, 16, theme.card(1.5))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.card(1.5))
            p.drawRoundedRect(r, 16, 16)

        gw, gh = 34.0, 16.0
        draw_battery(p, QtCore.QRectF(r.left() + 16, r.center().y() - gh / 2, gw, gh), pct)

        tx = r.left() + 16 + gw + 12
        p.setFont(ui_font(13, W.DemiBold))
        p.setPen(theme.text(0.96))
        p.drawText(QtCore.QRectF(tx, r.top() + 9, 260, 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "本机电池")
        p.setFont(ui_font(10.5, W.Normal))
        p.setPen(theme.text3(0.95))
        p.drawText(QtCore.QRectF(tx, r.bottom() - 24, 260, 15),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._status_text())

        if pct is None:
            p.setFont(ui_font(18, W.Light))
            p.setPen(theme.text3(0.85))
            p.drawText(QtCore.QRectF(r.right() - 100, r.top(), 84, r.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "—")
            return
        p.setFont(ui_font(24, W.Light, num=True))
        p.setPen(_level_color(int(pct)))
        val = f"{int(pct)}%"
        vw = QtGui.QFontMetrics(p.font()).horizontalAdvance(val)
        p.drawText(QtCore.QRectF(r.right() - 18 - vw, r.top(), vw + 2, r.height()),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, val)


class BatteryPage(Page):
    key, glyph, title, height = "bat", G.BATTERY, "电量", 372

    def __init__(self, ctx):
        super().__init__(ctx)
        self.rows: list[DeviceRow] = []
        self.svc = ctx.bluetooth

        self.count = Label("", 11.5, level=3)
        self.refresh_btn = IconButton(G.REFRESH, 28, 12, "重新扫描")
        self.refresh_btn.clicked.connect(lambda: self.svc.refresh(force=True))
        head = hbox(Label("设备电量", 13, W.DemiBold), None, self.count, self.refresh_btn, spacing=8)

        self.syscard = SystemBatteryCard()

        self.list = QtWidgets.QWidget()
        self.list_lay = vbox(spacing=6)
        self.list_lay.addStretch(1)          # 只加一次：设备少时也顶着上面排
        self.list.setLayout(self.list_lay)
        self.scroll = ScrollArea()
        self.scroll.setWidget(self.list)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        self.empty = Label("", 12.5, level=2, align=Qt.AlignmentFlag.AlignCenter, wrap=True)

        # 列表和空态共用一块空间：各自占 stretch 会互相挤，把底部说明挤出面板
        self.stack = QtWidgets.QStackedWidget()
        self.stack.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                 QtWidgets.QSizePolicy.Policy.Expanding)
        self.stack.addWidget(self.scroll)
        empty_holder = QtWidgets.QWidget()
        empty_holder.setLayout(vbox(None, self.empty, None, spacing=0))
        self.stack.addWidget(empty_holder)

        self.setLayout(vbox(head, self.syscard, (self.stack, 1), spacing=8))

        self.svc.updated.connect(self.set_devices)
        self.svc.failed.connect(self._failed)

        self._sig: tuple = ()
        # 设备插拔本身有热插拔信号兜底，这个定时器管的是「连接状态/电量变化」：
        # 页面开着时每 20s 刷一次（走服务端 25s 缓存，实际约 25s 一次，开销可接受）
        self._auto = QtCore.QTimer(self)
        self._auto.setInterval(20_000)
        self._auto.timeout.connect(lambda: self.svc.refresh())

        self._bat_timer = QtCore.QTimer(self)
        self._bat_timer.setInterval(20000)
        self._bat_timer.timeout.connect(self._refresh_sys)
        self._refresh_sys()
        self._bat_timer.start()

    def _refresh_sys(self):
        self.syscard.set_info(system_battery())

    # ---------- 数据 ----------
    def on_show(self):
        super().on_show()
        self._refresh_sys()
        if not self.svc.devices:
            self.show_loading()
        else:
            self.set_devices(self.svc.devices)
        self.svc.refresh()
        self._auto.start()

    def on_hide(self):
        super().on_hide()
        self._auto.stop()

    def show_loading(self):
        self.empty.setText("正在扫描设备…")
        self.stack.setCurrentIndex(1)
        self.count.setText("")

    def _failed(self, msg: str):
        # 后台定时刷新失败时不要清空已有列表，只在列表还空着的时候给出原因
        if self.rows:
            return
        self.empty.setText(f"扫描失败：{msg}")
        self.stack.setCurrentIndex(1)

    def set_devices(self, devices: list[dict]):
        # 只有「设备集合/顺序」变了才重建控件；电量、连接状态、备注都就地刷新
        sig = tuple((d.get("name"), d.get("kind")) for d in devices)
        if sig == self._sig and len(self.rows) == len(devices):
            # 只变了电量/状态：就地改 dict，不重建控件（否则每 20s 闪一下、滚动位置也丢）
            for row, dev in zip(self.rows, devices):
                row.dev = dev
                row.update()
        else:
            self._sig = sig
            for r in self.rows:
                self.list_lay.removeWidget(r)
                r.setParent(None)
                r.deleteLater()
            self.rows = []
            for i, dev in enumerate(devices):
                row = DeviceRow(dev)
                self.list_lay.insertWidget(i, row)
                self.rows.append(row)

        n = len(devices)
        conn = sum(1 for d in devices if d.get("connected"))
        self.count.setText(f"{conn} / {n} 已连接" if n else "")
        if not n:
            self.empty.setText("没有找到蓝牙或 USB 设备。\n先在系统设置里配对，或确认蓝牙已打开。")
            self.stack.setCurrentIndex(1)
            return
        self.stack.setCurrentIndex(0)

