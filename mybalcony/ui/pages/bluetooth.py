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
from ..widgets import IconButton, Label, ScrollArea, Themed, glass_ink, hbox, painter, vbox
from ..devicon import dev_glyph
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
        # 液态玻璃下圆底只有 42/255 的白，等于跟着壁纸走：白字形在浅壁纸上看不见。
        # 用和电量圆环同一套 glass_ink，按背景亮度反色。
        p.setPen(glass_ink(self, 0.72 if dev.get("connected") else 0.32))
        p.drawText(cr, Qt.AlignmentFlag.AlignCenter, dev_glyph(dev))

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
        theme.outlined_text(p, QtCore.QRectF(tx, r.top() + 5, tw, 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(dev.get("name") or "", Qt.TextElideMode.ElideRight, int(tw)))
        p.setFont(ui_font(10.5, W.Normal))
        p.setPen(theme.text3(0.95))
        fm2 = QtGui.QFontMetrics(p.font())
        theme.outlined_text(p, QtCore.QRectF(tx, r.bottom() - 19, tw, 14),
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
        theme.outlined_text(p, QtCore.QRectF(r.right() - 14 - vw, r.top(), vw + 2, r.height()),
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
        theme.outlined_text(p, QtCore.QRectF(tx, r.top() + 9, 260, 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "本机电池")
        p.setFont(ui_font(10.5, W.Normal))
        p.setPen(theme.text3(0.95))
        theme.outlined_text(p, QtCore.QRectF(tx, r.bottom() - 24, 260, 15),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._status_text())

        if pct is None:
            p.setFont(ui_font(18, W.Light))
            p.setPen(theme.text3(0.85))
            theme.outlined_text(p, QtCore.QRectF(r.right() - 100, r.top(), 84, r.height()),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "—")
            return
        p.setFont(ui_font(24, W.Light, num=True))
        p.setPen(_level_color(int(pct)))
        val = f"{int(pct)}%"
        vw = QtGui.QFontMetrics(p.font()).horizontalAdvance(val)
        theme.outlined_text(p, QtCore.QRectF(r.right() - 18 - vw, r.top(), vw + 2, r.height()),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, val)


class _EdgeFade(QtWidgets.QWidget):
    """滚动区底边的柔和淡出层（电量页专用）。

    透明分层窗口上不能用 ``QGraphicsOpacityEffect``：带效果的子控件会单独重绘，
    出现没有玻璃底的帧。也不碰 ``island.py`` 的二值 ``setMask``（那正是硬裁切的来源）。
    本层在**内容层**用 ``QPainter.CompositionMode_DestinationOut`` 画一道纵向 alpha
    渐变，把已经画好的设备行按渐变擦成透明，露出底下的玻璃——这就是「淡出到玻璃」。

    仅在液态玻璃 + 原生 GPU 玻璃层可见时启用：液态主题的玻璃底是独立的
    ``NativeGlassWindow`` 原生窗口，不在本窗口的 backing store 里，擦掉前景正好露出
    它；非液态主题的玻璃底与前景同处一张 backing store，DestinationOut 会把玻璃一起
    擦掉（露出桌面、失去玻璃底），因此那种情况宁可只保留底部留白，绝不冒黑块风险。

    鼠标事件完全穿透（``WA_TransparentForMouseEvents``），不影响滚动 / 悬停 / tooltip。
    """

    H = 4  # 淡出带高度（px）；必须小于 BatteryPage._BOTTOM_SPACER(6)，滚到底时不擦最后卡片

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        # 只穿透鼠标、不设 WA_TranslucentBackground：保持与兄弟控件共用同一张
        # backing store，DestinationOut 才能擦到已经画好的设备行像素。
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)

    def can_fade(self) -> bool:
        """液态玻璃 + 原生 GPU 玻璃层可见时，底下才有一层真玻璃可供淡出。"""
        if not theme.liquid:
            return False
        gpu = getattr(self.window(), "gpu_view", None)
        return bool(gpu is not None and gpu.isVisible())

    def paintEvent(self, e) -> None:
        if not self.can_fade() or self.height() <= 0:
            return
        p = QtGui.QPainter(self)
        # 上缘不擦（alpha 0），越往下擦得越狠，到面板底边完全透明，露出 GPU 玻璃。
        grad = QtGui.QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0.0, QtGui.QColor(0, 0, 0, 0))
        grad.setColorAt(1.0, QtGui.QColor(0, 0, 0, 255))
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_DestinationOut)
        p.fillRect(self.rect(), grad)
        p.end()


class BatteryPage(Page):
    key, glyph, title, height = "bat", G.BATTERY, "电量", 252
    _LIST_TOP = 102      # 列表区在页面里的起点，实测值（head 28 + spacing 8 + 本机卡 58 + spacing 8）
    _VISIBLE_ROWS = 3    # 固定露出 3 行，其余靠滚动
    _ROW_PITCH = int(DeviceRow.H) + 6          # 44 + 行间距 6 = 50：滚动步长按它走，整行进位
    # 视口高度恰好 = 3 行 150px：第 4 行起点正好落在视口外，一行都不露，
    # 且每次滚动 50px 后每屏仍是 3 整行，不会停在两行中间。
    _VIEW_H = _VISIBLE_ROWS * _ROW_PITCH
    # 内容层底部留白 6px：让总内容高成为 50 的整数倍（滚动终点也整行对齐），
    # 同时滚到底时最后一张卡片下缘抬高 6px，圆角不被视口底切平。
    _BOTTOM_SPACER = 6

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
        # 底部留白放在 stretch 之后：set_devices 的 insertWidget(i, row) 只会往前插，
        # 不碰这段 spacer，设备少时列表依旧顶上、设备多时滚到底仍有呼吸空间。
        self.list_lay.addSpacing(self._BOTTOM_SPACER)
        self.list.setLayout(self.list_lay)
        self.scroll = ScrollArea()
        self.scroll.row_step = self._ROW_PITCH      # 滚轮一格 = 一整行（44 + 6）
        self.scroll.setWidget(self.list)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._install_edge_fade()

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

    # ---------- 滚动底边淡出（纯视觉，不碰数据 / 定时器） ----------
    def preferred_height(self) -> int:
        """页高固定：列表区只给 3 行的位置，设备再多也不撑高，靠滚动看剩余的。

        页高 = 列表起点 102 + 视口 150（正好 3 行 × 50）。设备 ≤3 个时
        列表用 stretch 顶在上面，4 个起就滚动；滚轮步长锁 50px（整行 44+6），
        所以每一次滚动都是整行进位，不会停在两行中间被切一刀。
        """
        return self._LIST_TOP + self._VIEW_H

    def _install_edge_fade(self) -> None:
        """在滚动视口底边叠一层淡出遮罩，随视口尺寸与滚动位置更新。

        只挂在电量页自己的 ``scroll.viewport()`` 上：其它页没有这层 widget，零污染；
        ``ScrollArea`` 通用类也没动，默认行为零变化。
        """
        vp = self.scroll.viewport()
        self._fade = _EdgeFade(vp)
        self._fade.setGeometry(0, 0, 0, 0)
        vp.installEventFilter(self)
        bar = self.scroll.verticalScrollBar()
        bar.valueChanged.connect(self._update_fade)
        # 设备增减会改 range 但 value 可能不变；rangeChanged 才能可靠捕获「列表变得可滚动」
        bar.rangeChanged.connect(self._update_fade)
        # 液态 ↔ 非液态切换后 can_fade 判定会变，主题信号来了重画一次即可
        theme.changed.connect(self._fade.update)
        self._update_fade()

    def _update_fade(self, *_args) -> None:
        """淡出带贴在 viewport 视觉底边（吸附底边时即靠导航那侧）。

        内容不足以滚动时不显示：避免把整片静止的面板底部擦成透明。
        """
        vp = self.scroll.viewport()
        fade = getattr(self, "_fade", None)
        if fade is None:
            return
        bar = self.scroll.verticalScrollBar()
        h = fade.H if bar.maximum() > 0 else 0
        fade.setGeometry(0, max(0, vp.height() - h), max(0, vp.width()), h)
        if h:
            fade.update()

    def eventFilter(self, obj, event):
        if obj is self.scroll.viewport() and event.type() == QtCore.QEvent.Type.Resize:
            self._update_fade()
        return super().eventFilter(obj, event)

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
            self.set_height(self.preferred_height())
            return
        self.stack.setCurrentIndex(0)
        self.set_height(self.preferred_height())

