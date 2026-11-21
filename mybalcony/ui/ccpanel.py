# -*- coding: utf-8 -*-
"""控制页磁贴的二级面板（iOS 控制中心风格）。

不用 QMenu：里面有开关、可点击列表和输入框，QMenu 的 item 模型与键盘焦点都 hold 不住，
改成独立的 Qt.Tool 无边框窗口，自绘卡片背景 + 轮询鼠标键实现「点面板外关闭」。
"""
from __future__ import annotations

import ctypes
import os

from PySide6 import QtCore, QtGui, QtWidgets

from .anim import clamp
from .theme import G, W, icon_font, theme, ui_font
from .widgets import Hoverable, LineEdit, PillButton, Segmented, Switch, painter
from ..core import bg
from ..services import bluetooth, wifi

Qt = QtCore.Qt
_u32 = ctypes.WinDLL("user32")


def _rgba(c: QtGui.QColor) -> str:
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"


def _panel_brush(rect: QtCore.QRectF) -> QtGui.QBrush:
    """和岛本体同一套玻璃色调（tint / tint2 渐变）。

    独立窗口没有岛那层「截图模糊」，所以把 alpha 提实一点，避免直接透出桌面。
    注意不能用 menu_qss 里的 "rgba(...)" 字符串：QColor 解析不了这种 CSS 写法，
    会得到 invalid → 纯黑，主题怎么换都是黑的。
    """
    c = theme.tint()
    c.setAlpha(max(c.alpha(), 232))
    g2 = theme.pal.get("tint2")
    if not g2:
        return QtGui.QBrush(c)
    g = QtGui.QLinearGradient(rect.left(), rect.top(),
                              rect.right() * 0.25 + rect.left() * 0.75, rect.bottom())
    c2 = QtGui.QColor(*g2)
    c2.setAlpha(max(c2.alpha(), 232))
    g.setColorAt(0, c)
    g.setColorAt(1, c2)
    return QtGui.QBrush(g)


def _style_label(w, level: float):
    w.setStyleSheet(f"color:{_rgba(theme.text(level))};background:transparent")


def _style_button(b):
    c, h = theme.card(1.6), theme.hover()
    b.setStyleSheet(
        f"QPushButton{{background:{_rgba(c)};border:none;border-radius:9px;padding:6px 9px;"
        f"color:{_rgba(theme.text())}}}"
        f"QPushButton:hover{{background:{_rgba(h)}}}")


def _style_icon(b):
    b.setStyleSheet(f"QToolButton{{background:transparent;border:none;color:{_rgba(theme.text(0.85))}}}")


def _style_sep(line):
    line.setStyleSheet(f"QFrame{{background:{_rgba(theme.text(0.10))};border:none}}")


def _label(text: str, px: float = 13, weight=None, level: float = 1.0) -> QtWidgets.QLabel:
    w = QtWidgets.QLabel(text)
    w.setFont(ui_font(px, weight or W.Normal))
    w.setProperty("cc_level", level)
    _style_label(w, level)
    return w


CCSwitch = Switch          # 开关已经挪到通用控件里（页签菜单也要用），这里保留旧名字


class CCRow(Hoverable):
    """一行设备/网络：圆形图标 + 名称 + 右侧状态 + 锁。"""
    def __init__(self, glyph: str, title: str, right: str = "", lock: bool = False,
                 active: bool = False, strength: float = 1.0, parent=None):
        super().__init__(parent)
        self.glyph, self.title, self.right = glyph, title, right
        self.lock, self.active, self.strength = lock, active, strength
        self.setFixedHeight(38)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Fixed)

    def paintEvent(self, e):
        p = painter(self)
        r = QtCore.QRectF(self.rect())
        if self._hover.x > 0.01:
            c = theme.hover()
            c.setAlphaF(c.alphaF() * self._hover.x)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(r.adjusted(2, 1, -2, -1), 9, 9)
        d = 26.0
        cr = QtCore.QRectF(r.x() + 6, r.center().y() - d / 2, d, d)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.card(1.8))
        p.drawEllipse(cr)
        p.setFont(icon_font(13))
        p.setPen(theme.text(0.35 + 0.65 * clamp(self.strength, 0.0, 1.0)))
        p.drawText(cr, Qt.AlignmentFlag.AlignCenter, self.glyph)

        tx = cr.right() + 10
        tw = r.right() - tx - 58
        f = ui_font(13, W.DemiBold if self.active else W.Normal)
        p.setFont(f)
        p.setPen(theme.text(1.0 if self.active else 0.92))
        fm = QtGui.QFontMetrics(f)
        p.drawText(QtCore.QRectF(tx, r.y(), tw, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   fm.elidedText(self.title, Qt.TextElideMode.ElideRight, int(tw)))

        if self.right:
            f2 = ui_font(11.5)
            p.setFont(f2)
            p.setPen(theme.text3())
            p.drawText(QtCore.QRectF(r.right() - 56, r.y(), 40, r.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, self.right)
        if self.lock:
            p.setFont(icon_font(10))
            p.setPen(theme.text3(0.8))
            p.drawText(QtCore.QRectF(r.right() - 14, r.y(), 14, r.height()),
                       Qt.AlignmentFlag.AlignCenter, G.LOCK)


class CCPanel(QtWidgets.QWidget):
    """弹出卡片：标题+开关、分组、动态行区、底部操作。"""
    def __init__(self, island=None, width: int = 306):
        super().__init__(None)
        self.island = island
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(width)
        self.box = QtWidgets.QVBoxLayout(self)
        self.box.setContentsMargins(16, 13, 16, 13)
        self.box.setSpacing(7)
        self.rows_w = None
        self.rows_lay = None
        self._footer = None
        self._status = None
        self._anchor = QtCore.QPoint(0, 0)
        self._armed = False
        self._status_ok = True
        self._watch = QtCore.QTimer(self, interval=25, timeout=self._watch_tick)
        theme.changed.connect(self._retheme)

    # --- 背景 ---
    def showEvent(self, e):
        if theme.liquid:
            # 先抓一次屏：此刻窗口还是全透明的，抓到的是桌面；paint 时直接复用这份缓存
            from .liquid import precapture
            precapture(self, 18.0)
        super().showEvent(e)

    def paintEvent(self, e):
        p = painter(self)
        if theme.liquid:
            from .liquid import paint_panel
            paint_panel(p, self, QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 18.0)
            return
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QtGui.QPen(theme.rim_top(), 1))
        p.setBrush(_panel_brush(r))
        p.drawRoundedRect(r, 18, 18)
        # 岛本体同款纵向光泽，让面板看起来是同一块玻璃
        g = QtGui.QLinearGradient(0, r.top(), 0, r.bottom())
        g.setColorAt(0, QtGui.QColor(255, 255, 255, 26 if not theme.dark else 14))
        g.setColorAt(0.5, QtGui.QColor(255, 255, 255, 0))
        g.setColorAt(1, QtGui.QColor(255, 255, 255, 10))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(r, 18, 18)

    def _retheme(self):
        """主题切换时，静态 QSS 也要跟着换（自绘控件由 Themed 自己 update）。"""
        for w in self.findChildren(QtWidgets.QLabel):
            if w.property("cc_status"):
                w.setStyleSheet(
                    f"color:{_rgba(theme.down() if self._status_ok else theme.up())};background:transparent")
            else:
                lv = w.property("cc_level")
                if lv is not None:
                    _style_label(w, float(lv))
        for b in self.findChildren(QtWidgets.QPushButton):
            if b.property("cc_button"):
                _style_button(b)
        for b in self.findChildren(QtWidgets.QToolButton):
            if b.property("cc_icon"):
                _style_icon(b)
        for f in self.findChildren(QtWidgets.QFrame):
            if f.property("cc_sep"):
                _style_sep(f)
        self.update()

    # --- 骨架 ---
    def add_header(self, title: str, sub: str, on: bool, cb) -> CCSwitch:
        h = QtWidgets.QHBoxLayout()
        h.setSpacing(8)
        left = QtWidgets.QVBoxLayout()
        left.setSpacing(1)
        left.addWidget(_label(title, 15, W.DemiBold))
        if sub:
            left.addWidget(_label(sub, 11, W.Normal, 0.55))
        h.addLayout(left, 1)
        sw = CCSwitch(on)
        sw.toggled.connect(cb)
        h.addWidget(sw, 0, Qt.AlignmentFlag.AlignVCenter)
        self.box.addLayout(h)
        return sw

    def add_group(self, text: str, action=None):
        h = QtWidgets.QHBoxLayout()
        h.setSpacing(6)
        h.addWidget(_label(text, 11.5, W.DemiBold, 0.5), 1)
        if action:
            b = QtWidgets.QToolButton()
            b.setText(G.REFRESH)
            b.setFont(icon_font(12))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty("cc_icon", True)
            _style_icon(b)
            b.clicked.connect(action)
            h.addWidget(b)
        self.box.addLayout(h)
        self.rows_w = QtWidgets.QWidget()
        self.rows_lay = QtWidgets.QVBoxLayout(self.rows_w)
        self.rows_lay.setContentsMargins(0, 0, 0, 0)
        self.rows_lay.setSpacing(2)
        self.box.addWidget(self.rows_w)
        self._sep()

    def _sep(self):
        line = QtWidgets.QFrame()
        line.setFixedHeight(1)
        line.setProperty("cc_sep", True)
        _style_sep(line)
        self.box.addWidget(line)

    def clear_rows(self):
        if self.rows_lay is None:
            return
        while self.rows_lay.count():
            it = self.rows_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def set_busy(self, text: str):
        self.clear_rows()
        self.rows_lay.addWidget(_label("  " + text, 12, W.Normal, 0.55))

    def add_note(self, text: str):
        w = _label("  " + text, 11.5, W.Normal, 0.5)
        (self.rows_lay if self.rows_lay is not None else self.box).addWidget(w)

    def add_row(self, row: CCRow):
        self.rows_lay.addWidget(row)

    def add_field(self, name: str, widget):
        h = QtWidgets.QHBoxLayout()
        h.setSpacing(8)
        lab = _label(name, 12, W.Normal, 0.62)
        lab.setFixedWidth(54)
        h.addWidget(lab)
        h.addWidget(widget, 1)
        self.box.addLayout(h)

    def add_button(self, text: str, cb):
        b = PillButton(text, G.CHECK, height=30)
        b.clicked.connect(cb)
        self.box.addWidget(b)
        return b

    def add_footer(self, items: list[tuple[str, object]]):
        if self._footer is not None:
            return
        self._sep()
        h = QtWidgets.QHBoxLayout()
        h.setSpacing(6)
        for text, cb in items:
            b = QtWidgets.QPushButton(text)
            b.setFont(ui_font(11.5))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty("cc_button", True)
            _style_button(b)
            b.clicked.connect(lambda _=False, f=cb: f())
            h.addWidget(b, 1)
        self.box.addLayout(h)
        self._footer = h

    def set_status(self, text: str, ok: bool = True):
        self._status_ok = ok
        if self._status is None:
            self._status = QtWidgets.QLabel("")
            self._status.setFont(ui_font(11.5))
            self._status.setProperty("cc_status", True)
            self.box.addWidget(self._status)
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color:{_rgba(theme.down() if ok else theme.up())};background:transparent")

    def finish(self):
        self.adjustSize()
        self._place()

    # --- 弹出 / 关闭 ---
    def popup_near(self, anchor: QtWidgets.QWidget):
        self._anchor = anchor.mapToGlobal(QtCore.QPoint(0, anchor.height() + 8))
        self._place()
        self.show()
        self.raise_()
        self.activateWindow()
        if self.island is not None:
            self.island.locks.add("menu")
        self._armed = False
        self._watch.start()

    def _place(self):
        scr = QtWidgets.QApplication.primaryScreen().geometry()
        h = max(120, self.sizeHint().height())
        x = min(max(scr.left() + 8, self._anchor.x()), scr.right() - self.width() - 8)
        y = min(max(scr.top() + 8, self._anchor.y()), scr.bottom() - h - 8)
        self.move(x, y)

    def _watch_tick(self):
        if not self.isVisible():
            self._watch.stop()
            return
        down = any(_u32.GetAsyncKeyState(k) & 0x8000 for k in (0x01, 0x02, 0x04))
        if not self._armed:
            self._armed = not down          # 先等打开面板的那次按键松开
            return
        if down and not self.geometry().contains(QtGui.QCursor.pos()):
            self.close()
            self._watch.stop()

    def closeEvent(self, e):
        self._watch.stop()
        if self.island is not None:
            self.island.locks.discard("menu")
        super().closeEvent(e)


# ====================================================================== 三类面板

def _settings(uri: str):
    def go():
        os.startfile(uri)  # noqa: S606
    return go


def _wifi_connect(panel: CCPanel, ssid: str, saved: set[str]):
    if ssid not in saved:
        # 没保存过的网络不猜 profile（WPA3 / 企业认证都会失败），交给系统面板收密码
        os.startfile("ms-settings:network-wifi")  # noqa: S606
        panel.set_status(f"{ssid}：请在系统面板里输入密码", False)
        return
    def done(res):
        ok, msg = res
        if panel.isVisible():
            panel.set_status(f"{ssid}：{msg}" if not ok else f"正在连接 {ssid}…", ok)
    panel.set_status(f"正在连接 {ssid}…")
    bg.run_bg(wifi.connect, ssid, on_done=done)


def open_wifi(ctx, island, anchor) -> CCPanel:
    radio = ctx.radio
    p = CCPanel(island)
    st = radio.state
    p.add_header("WLAN", "已保存的网络可直接连接", bool(st.get("wifi_on")), radio.set_wifi)

    def load():
        p.set_busy("正在扫描可用网络…")
        p.finish()
        bg.run_bg(wifi.snapshot, on_done=fill,
                  on_error=lambda e: (p.set_busy("扫描失败，请检查 WLAN 是否开启"), p.finish()))

    def fill(s):
        if not p.isVisible():
            return
        p.clear_rows()
        cur, saved = s["current"], s["profiles"]
        nets = s["networks"][:8]
        if not nets:
            p.add_note("没有搜索到可用网络")
        for n in nets:
            row = CCRow(G.WIFI, n["ssid"], right=f"{n['signal']}%", lock=n["secured"],
                        active=(n["ssid"] == cur), strength=n["signal"] / 100.0)
            row.clicked.connect(lambda ssid=n["ssid"]: _wifi_connect(p, ssid, saved))
            p.add_row(row)
        p.add_footer([("打开 Wi-Fi 设置", _settings("ms-settings:network-wifi")),
                      ("重新扫描", load)])
        p.finish()

    p.add_group("其他网络", action=load)
    p.set_busy("正在扫描可用网络…")
    p.popup_near(anchor)
    bg.run_bg(wifi.snapshot, on_done=fill,
              on_error=lambda e: (p.set_busy("扫描失败，请检查 WLAN 是否开启"), p.finish()))
    return p


def open_bluetooth(ctx, island, anchor) -> CCPanel:
    radio = ctx.radio
    p = CCPanel(island)
    st = radio.state
    p.add_header("蓝牙", "已配对与附近的设备", bool(st.get("bt_on")), radio.set_bluetooth)

    def load():
        p.set_busy("正在扫描设备…")
        p.finish()
        bg.run_bg(bluetooth.scan, on_done=fill,
                  on_error=lambda e: (p.set_busy("扫描失败"), p.finish()))

    def fill(rows):
        if not p.isVisible():
            return
        p.clear_rows()
        if not rows:
            p.add_note("没有找到设备")
        for d in rows[:8]:
            lv = d.get("battery")
            right = f"{lv}%" if lv is not None else ("已连接" if d.get("connected") else "未连接")
            glyph = G.USB if d.get("kind") == "usb" else G.BT
            p.add_row(CCRow(glyph, d.get("name") or "未知设备", right=right,
                            active=bool(d.get("connected")), lock=False))
        p.add_footer([("设备电量", lambda: island.show_page("bat") if island else None),
                      ("重新扫描", load)])
        p.finish()

    p.add_group("其他设备", action=load)
    p.set_busy("正在扫描设备…")
    p.popup_near(anchor)
    bg.run_bg(bluetooth.scan, on_done=fill,
              on_error=lambda e: (p.set_busy("扫描失败"), p.finish()))
    return p


def open_hotspot(ctx, island, anchor) -> CCPanel:
    radio = ctx.radio
    p = CCPanel(island)
    st = radio.state
    sw = p.add_header("个人热点", "设置名称、密码与兼容性",
                      bool(st.get("hotspot_on")), radio.set_hotspot)
    cfg = radio.hotspot_config()
    if cfg is None:
        p.add_note("当前没有可用的网络连接，无法读取热点配置")
        p.add_footer([("打开移动热点设置", _settings("ms-settings:network-mobilehotspot"))])
    else:
        name = LineEdit("热点名称")
        name.setText(cfg["ssid"])
        p.add_field("名称", name)
        pwd = LineEdit("至少 8 位")
        pwd.setText(cfg["passphrase"])
        pwd.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        eye = QtWidgets.QToolButton()
        eye.setText(G.EYE)
        eye.setFont(icon_font(12))
        eye.setCursor(Qt.CursorShape.PointingHandCursor)
        eye.setProperty("cc_icon", True)
        _style_icon(eye)
        eye.clicked.connect(lambda: pwd.setEchoMode(
            QtWidgets.QLineEdit.EchoMode.Normal if pwd.echoMode() == QtWidgets.QLineEdit.EchoMode.Password
            else QtWidgets.QLineEdit.EchoMode.Password))
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(pwd, 1)
        row.addWidget(eye)
        holder = QtWidgets.QWidget()
        holder.setLayout(row)
        h = QtWidgets.QHBoxLayout()
        h.setSpacing(8)
        lab = _label("密码", 12, W.Normal, 0.62)
        lab.setFixedWidth(54)
        h.addWidget(lab)
        h.addWidget(holder, 1)
        p.box.addLayout(h)
        for edit in (name, pwd):
            edit.focus_wanted.connect(lambda: (p.activateWindow(), p.raise_()))

        auth = Segmented([a["label"] for a in cfg["auths"]], height=28)
        auth.set_index(min(cfg["auth"], len(cfg["auths"]) - 1))
        p.add_field("兼容性", auth)
        band = Segmented([b["label"] for b in cfg["bands"]], height=28)
        band.set_index(min(cfg["band"], len(cfg["bands"]) - 1))
        p.add_field("频段", band)
        bad_b = [b["label"] for b in cfg["bands"] if not b.get("ok", True)]
        bad_a = [a["label"] for a in cfg["auths"] if not a.get("ok", True)]
        p.add_note(f"最多 {cfg['max_clients']} 台设备")
        if bad_b:
            p.add_note(f"{'/'.join(bad_b)} 频段此设备不支持")
        if bad_a:
            p.add_note(f"{'/'.join(bad_a)} 认证此设备不支持")

        def save():
            ssid, pw = name.text().strip(), pwd.text().strip()
            if not ssid:
                p.set_status("名称不能为空", False)
                return
            if len(pw) < 8:
                p.set_status("密码至少需要 8 位", False)
                return
            b_item = cfg["bands"][min(band.index, len(cfg["bands"]) - 1)]
            a_item = cfg["auths"][min(auth.index, len(cfg["auths"]) - 1)]
            if not b_item.get("ok", True):
                p.set_status(f"{b_item['label']} 频段此设备不支持", False)
                return
            if not a_item.get("ok", True):
                p.set_status(f"{a_item['label']} 认证此设备不支持", False)
                return
            p.set_status("正在应用…")

            def done(ok):
                if p.isVisible():
                    p.set_status("已保存，开关一次热点后生效" if ok else "保存失败：需要管理员权限或设备不支持", ok)
                if ok:
                    radio.refresh()
            bg.run_bg(radio.set_hotspot_config, ssid, pw, b_item["value"], a_item["value"],
                      on_done=done)

        p.add_button("保存并应用", save)
        p.add_footer([("移动热点设置", _settings("ms-settings:network-mobilehotspot"))])
    p.finish()
    p.popup_near(anchor)
    return p
