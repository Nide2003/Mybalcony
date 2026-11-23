# -*- coding: utf-8 -*-
"""控制中心（音量 / 亮度 / WiFi / 蓝牙 / Clash Verge）、窗口切换、性能监控。"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ...core.bg import run_bg
from ...core.config import cfg
from .. import ccpanel
from ..anim import clamp
from ..theme import G, W, icon_font, theme, ui_font
from ..widgets import (Card, CCTile, Hoverable, IconButton, Label, PillButton, ScrollArea, Segmented, Slider,
                       Sparkline, Themed, Tile, fmt_bytes, hbox, painter, vbox)
from .base import Page

Qt = QtCore.Qt
MODES = [("rule", "规则"), ("global", "全局"), ("direct", "直连")]


def short_node(name: str) -> str:
    """"JMS-1411881@c51s2.xxx:443" -> "c51s2"（@ 后面 5 个字符）。"""
    if "@" in name:
        return name.split("@", 1)[1][:5]
    return name


def _close_on_outside_click(m: QtWidgets.QMenu):
    """灵动岛不抢焦点，Qt 的"点外面关闭菜单"不会触发；这里轮询鼠标键，点到菜单外就关闭。"""
    import ctypes
    u32 = ctypes.WinDLL("user32")
    st = {"armed": False}
    t = QtCore.QTimer(m)
    t.setInterval(25)

    def down() -> bool:
        return any(u32.GetAsyncKeyState(k) & 0x8000 for k in (0x01, 0x02, 0x04))

    def tick():
        if not m.isVisible():
            t.stop()
            return
        if not st["armed"]:
            st["armed"] = not down()          # 先等打开菜单的那次按键松开
            return
        if down():
            pos = QtGui.QCursor.pos()
            menus = [w for w in QtWidgets.QApplication.topLevelWidgets()
                     if isinstance(w, QtWidgets.QMenu) and w.isVisible()]
            if not any(w.geometry().contains(pos) for w in menus):
                m.close()
                t.stop()
    t.timeout.connect(tick)
    m.aboutToShow.connect(lambda: (st.update(armed=False), t.start()))
    m.aboutToHide.connect(t.stop)


def styled_menu(parent=None) -> QtWidgets.QMenu:
    m = QtWidgets.QMenu(parent)
    _close_on_outside_click(m)
    m.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    m.setWindowFlag(Qt.WindowType.FramelessWindowHint)
    m.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint)
    if theme.liquid:
        # 液态玻璃：背景交给 self-drawn 玻璃（项目里所有 QMenu 由 liquid.MenuGlass 统管）
        from ..liquid import MenuGlass
        MenuGlass.dress(m)
        return m
    bg, fg, sel = theme.menu_qss()
    m.setStyleSheet(
        f"QMenu{{background:{bg};border-radius:14px;padding:6px;color:{fg};font-family:'HarmonyOS Sans','Microsoft YaHei UI';font-size:13px}}"
        f"QMenu::item{{padding:6px 22px 6px 14px;border-radius:9px}}"
        f"QMenu::item:selected{{background:{sel}}}"
        f"QMenu::item:disabled{{color:gray}}"
        "QMenu::separator{height:6px;background:transparent}"
        "QMenu::indicator{width:0}")
    return m


TILE = 118          # 控制中心方块磁贴的边长


class ControlsPage(Page):
    key, glyph, title, height = "ctl", G.SLIDERS, "控制", 260

    def __init__(self, ctx):
        super().__init__(ctx)
        self.vol = Slider(G.VOLUME)
        self.bri = Slider(G.SUN)
        self.vol.moved.connect(self._set_vol)
        self.vol.icon_clicked.connect(lambda: ctx.audio.toggle_mute())
        self.bri.moved.connect(lambda v: ctx.brightness.set(None, round(v * 100)))
        # 顶栏胶囊大小：放在音量/亮度下面那块空白里，只缩放收起态
        self.scale = Slider(G.MONITOR)
        self.scale.moved.connect(self._scale_moved)
        self.scale.released.connect(self._scale_saved)
        s0 = clamp(float(cfg.get("island.scale", 1.0) or 1.0), 0.7, 1.3)
        self.scale.set_value((s0 - 0.7) / 0.6, animate=False)
        self.scale.label = f"{round(s0 * 100)}%"
        self.scale_box = Card(radius=16)
        self.scale_box.setLayout(vbox(
            hbox(Label("顶栏胶囊大小", 12, W.DemiBold), None, spacing=6),
            self.scale, spacing=6, margins=(12, 8, 12, 8)))
        self.wifi = CCTile(G.WIFI, "无线局域网", tint=QtGui.QColor(0, 122, 255))
        self.hotspot = CCTile(G.STREAM, "个人热点", tint=QtGui.QColor(52, 199, 89))
        self.bt = CCTile(G.BT, "蓝牙", tint=QtGui.QColor(0, 122, 255))
        self.air = CCTile(G.PLANE, "飞行模式", tint=QtGui.QColor(255, 159, 10), has_menu=False)
        self.proxy = CCTile(G.GLOBE, "系统代理")
        self.tun = CCTile(G.BOLT, "TUN 模式")
        self._radio = {}
        self._clash = {}
        self._panel = None
        self.wifi.clicked.connect(lambda: self._toggle("wifi"))
        self.bt.clicked.connect(lambda: self._toggle("bt"))
        self.hotspot.clicked.connect(lambda: self._toggle("hotspot"))
        self.air.clicked.connect(lambda: self.ctx.radio.set_airplane(not self._radio.get("airplane_on")))
        self.proxy.clicked.connect(lambda: ctx.clash.set_sysproxy(not self._clash.get("sysproxy")))
        self.tun.clicked.connect(lambda: ctx.clash.set_tun(not self._clash.get("tun")))
        # 状态行右侧的 chevron：WLAN / 蓝牙 / 热点弹自定义二级面板，其余走普通菜单
        for t, kind in ((self.wifi, "wifi"), (self.hotspot, "hotspot"), (self.bt, "bt"),
                        (self.proxy, "proxy"), (self.tun, "tun")):
            t.menu_clicked.connect(lambda k=kind: self._open_menu(k))
        grid = QtWidgets.QGridLayout()
        grid.setSpacing(15)
        # 宫格必须严丝合缝地等于 gw 的尺寸：QGridLayout 默认带 9px 外边距，会让 2×2 需要
        # 269px 而容器只有 251px，Qt 去偷间距，最后一行就被页面下沿切掉一条边。
        grid.setContentsMargins(0, 0, 0, 0)
        self._tiles = (self.wifi, self.hotspot, self.bt, self.air, self.proxy, self.tun)
        for i, t in enumerate(self._tiles):
            grid.addWidget(t, i // 2, i % 2)

        # Clash 卡片
        self.card = Card(radius=18)
        self.mode = Segmented([n for _, n in MODES])
        self.mode.setFixedWidth(168)
        self.mode.changed.connect(lambda i: ctx.clash.set_mode(MODES[i][0]))
        self.node = PillButton("节点", G.GLOBE, height=28)
        self.node.clicked.connect(self._node_menu)
        self.node.setMaximumWidth(190)
        self.speed = Label("", 11.5, level=2, num=True)
        self.clash_state = Label("Clash Verge", 13, W.DemiBold)
        openv = IconButton(G.OPEN, 28, 12, "打开 Clash Verge")
        openv.clicked.connect(lambda: ctx.clash.open_app())
        self.card.setLayout(vbox(hbox(self.clash_state, None, self.speed, openv, spacing=6),
                                 hbox(self.mode, None, self.node, spacing=8), spacing=6, margins=(14, 10, 10, 10)))
        sliders = vbox(self.vol, self.bri, self.scale_box, self.card, None, spacing=8)
        for w in (self.card, self.proxy, self.tun):
            w.hide()
        # 宫格（4 个按钮）在左、3 条滑块在右；两列都定高到宫格高度，顶边/底边对齐，
        # 不再出现「滑块列比按钮宫格高一截」。
        gw = QtWidgets.QWidget()
        gw.setLayout(grid)
        gw.setFixedSize(TILE * 2 + 15, TILE * 2 + 15)
        sliders_w = QtWidgets.QWidget()
        sliders_w.setLayout(sliders)
        sliders_w.setFixedHeight(gw.height())
        self.setLayout(hbox(gw, (sliders_w, 1), spacing=10))
        self._sync_height()

    def _sync_height(self):
        """宫格是方块，页高得跟着行数走：两行（默认）或三行（Clash 在跑时多出代理两块）。"""
        rows = 3 if self._clash.get("ok") else 2
        self.set_height(rows * TILE + (rows - 1) * 15)

    def _toggle(self, kind: str):
        """可用就切换开关；检测不到（台式机没蓝牙 / 驱动不支持）时打开对应的系统设置页。"""
        import os
        if kind == "hotspot":
            if not self._radio.get("hotspot_available", False):
                os.startfile("ms-settings:network-mobilehotspot")  # noqa: S606
                if self.island:
                    self.island.collapse()
                return
            self.ctx.radio.set_hotspot(not self._radio.get("hotspot_on"))
            return
        if not self._radio.get(f"{kind}_available", False):
            os.startfile("ms-settings:" + ("bluetooth" if kind == "bt" else "network-wifi"))  # noqa: S606
            if self.island:
                self.island.collapse()
            return
        if kind == "bt":
            self.ctx.radio.set_bluetooth(not self._radio.get("bt_on"))
        else:
            self.ctx.radio.set_wifi(not self._radio.get("wifi_on"))

    def _open_panel(self, kind: str):
        """WLAN / 蓝牙 / 个人热点的二级面板：内容较多，用独立卡片而不是 QMenu。"""
        if self._panel is not None:
            try:
                self._panel.close()
            except RuntimeError:
                pass
            self._panel = None
        build = {"wifi": ccpanel.open_wifi, "bt": ccpanel.open_bluetooth,
                 "hotspot": ccpanel.open_hotspot}[kind]
        anchor = {"wifi": self.wifi, "bt": self.bt, "hotspot": self.hotspot}[kind]
        self._panel = build(self.ctx, self.island, anchor)

    def _open_menu(self, kind: str):
        """点磁贴状态行的 chevron 弹出该模块的二级菜单（底部还有一层「更多」子菜单）。"""
        if kind in ("wifi", "bt", "hotspot"):
            self._open_panel(kind)
            return
        import os
        d, c = self._radio, self._clash
        m = styled_menu(self)

        def info(text):
            a = m.addAction(text)
            a.setEnabled(False)         # 只展示读到的真实状态，不可点

        def act(text, fn, checked=None):
            label = text if checked is None else (("✓  " if checked else "     ") + text)
            a = m.addAction(label)
            a.triggered.connect(lambda _=False: fn())

        def settings(uri):
            def go():
                os.startfile(uri)  # noqa: S606
                if self.island:
                    self.island.collapse()
            return go

        def more():
            sub = m.addMenu("更多  ›")
            sub.setStyleSheet(m.styleSheet())
            return sub

        def sub_act(sub, text, fn):
            a = sub.addAction(text)
            a.triggered.connect(lambda _=False: fn())

        if kind == "wifi":
            on = bool(d.get("wifi_on"))
            info(f"无线局域网 · {'已开启' if on else '已关闭'}")
            m.addSeparator()
            act("开启无线局域网", lambda: self._toggle("wifi"), on)
            if d.get("wifi_ssid"):
                info(f"当前网络：{d['wifi_ssid']}")
            if d.get("wifi_signal"):
                info(f"信号强度：{d['wifi_signal']}%")
            m.addSeparator()
            sub = more()
            sub_act(sub, "打开 Wi-Fi 设置", settings("ms-settings:network-wifi"))
            sub_act(sub, "打开网络状态", settings("ms-settings:network-status"))
        elif kind == "hotspot":
            on = bool(d.get("hotspot_on"))
            info(f"个人热点 · {'已开启' if on else '已关闭'}")
            m.addSeparator()
            act("开启个人热点", lambda: self._toggle("hotspot"), on)
            if d.get("hotspot_ssid"):
                info(f"网络名称：{d['hotspot_ssid']}")
            if d.get("hotspot_available"):
                info(f"已连接设备：{int(d.get('hotspot_clients') or 0)} 台")
            m.addSeparator()
            sub = more()
            sub_act(sub, "打开移动热点设置", settings("ms-settings:network-mobilehotspot"))
            sub_act(sub, "打开网络状态", settings("ms-settings:network-status"))
        elif kind == "bt":
            on = bool(d.get("bt_on"))
            info(f"蓝牙 · {'已开启' if on else '已关闭'}")
            m.addSeparator()
            act("开启蓝牙", lambda: self._toggle("bt"), on)
            m.addSeparator()
            act("查看设备电量", lambda: self.island.show_page("bat") if self.island else None)
            sub = more()
            sub_act(sub, "打开蓝牙设置", settings("ms-settings:bluetooth"))
            sub_act(sub, "打开设备列表", settings("ms-settings:devices"))
        elif kind == "air":
            on = bool(d.get("airplane_on"))
            info(f"飞行模式 · {'已开启' if on else '已关闭'}")
            m.addSeparator()
            act("开启飞行模式", lambda: self.ctx.radio.set_airplane(not d.get("airplane_on")), on)
            info("关掉 Wi-Fi 与蓝牙，退出时恢复")
            m.addSeparator()
            sub = more()
            sub_act(sub, "打开网络状态", settings("ms-settings:network-status"))
            sub_act(sub, "打开 Wi-Fi 设置", settings("ms-settings:network-wifi"))
        elif kind == "proxy":
            on = bool(c.get("sysproxy"))
            info(f"系统代理 · {'已开启' if on else '已关闭'}")
            m.addSeparator()
            act("启用系统代理", lambda: self.ctx.clash.set_sysproxy(not on), on)
            if on:
                info("本地地址：127.0.0.1")
            m.addSeparator()
            sub = more()
            sub_act(sub, "打开 Clash Verge", lambda: self.ctx.clash.open_app())
            sub.addSeparator()
            for key_, name in MODES:
                sub_act(sub, ("✓  " if c.get("mode") == key_ else "     ") + f"切换到{name}模式",
                        lambda k=key_: self.ctx.clash.set_mode(k))
        elif kind == "tun":
            on = bool(c.get("tun"))
            info(f"TUN 模式 · {'已开启' if on else '已关闭'}")
            m.addSeparator()
            act("启用 TUN 模式", lambda: self.ctx.clash.set_tun(not on), on)
            info("接管全局流量，需要管理员权限")
            m.addSeparator()
            sub = more()
            sub_act(sub, "打开 Clash Verge", lambda: self.ctx.clash.open_app())
            sub_act(sub, "打开网络状态", settings("ms-settings:network-status"))

        if self.island:
            self.island.locks.add("menu")
            m.aboutToHide.connect(lambda: self.island.locks.discard("menu"))
        m.popup(QtGui.QCursor.pos())

    def _set_vol(self, v: float):
        a = self.ctx.audio
        a.set_volume(v)
        if v > 0.001 and a.muted():
            a.set_muted(False)          # 调大音量时顺便取消静音（否则看起来"没反应"）

    def _scale_moved(self, v: float):
        s = 0.7 + v * 0.6
        self.scale.label = f"{round(s * 100)}%"
        self.scale.update()
        if self.island:
            self.island.set_compact_scale(s, save=False)

    def _scale_saved(self, v: float):
        # 松手才写盘，拖动中不反复落 config.json
        if self.island:
            self.island.set_compact_scale(0.7 + v * 0.6, save=True)

    # --- 数据 ---
    def set_volume(self, v: float, muted: bool):
        self.vol.glyph = G.MUTE if muted else (G.VOLUME_LOW if v < 0.34 else G.VOLUME)
        self.vol.label = "静音" if muted else ""
        self.vol.set_value(v)

    def set_brightness(self, mons: list):
        if not mons:
            self.bri.label = "不支持"
            self.bri.update()
            return
        vals = [m.get("brightness") for m in mons if m.get("brightness") is not None]
        if vals:
            self.bri.label = ""
            self.bri.set_value(sum(vals) / len(vals) / 100)

    def set_radio(self, d: dict):
        self._radio = d
        self.wifi.set_state(bool(d.get("wifi_on")),
                            (d.get("wifi_ssid") or ("已开启" if d.get("wifi_on") else "已关闭"))
                            + (f" · {d['wifi_signal']}%" if d.get("wifi_signal") and d.get("wifi_ssid") else ""),
                            d.get("wifi_available", True))
        bt_ok = d.get("bt_available", True)
        self.bt.set_state(bool(d.get("bt_on")),
                          ("已开启" if d.get("bt_on") else "已关闭") if bt_ok else "未检测到", bt_ok)
        hs_ok = d.get("hotspot_available", False)
        if not hs_ok:
            hs_sub = "未检测到"
        elif d.get("hotspot_on"):
            n = int(d.get("hotspot_clients") or 0)
            hs_sub = f"{n} 台已连接" if n else "已开启"
        else:
            hs_sub = "已关闭"
        self.hotspot.set_state(bool(d.get("hotspot_on")), hs_sub, hs_ok)
        self.air.set_state(bool(d.get("airplane_on")),
                           "已开启" if d.get("airplane_on") else "已关闭",
                           d.get("airplane_available", True))

    def set_clash(self, d: dict):
        self._clash = d
        ok = d.get("ok")
        # 只有检测到 Clash Verge 在运行时才显示代理相关的卡片和磁贴（没装的用户看不到无用的面板）
        for w in (self.card, self.proxy, self.tun):
            w.setVisible(bool(ok))
        self._sync_height()
        self.proxy.set_state(bool(d.get("sysproxy")), "127.0.0.1" if d.get("sysproxy") else "已关闭")
        self.tun.set_state(bool(d.get("tun")), "已开启" if d.get("tun") else "已关闭", bool(ok))
        if ok:
            self.clash_state.setText("Clash Verge")
            self.speed.setText(f"↑ {fmt_bytes(d.get('up', 0), True)}   ↓ {fmt_bytes(d.get('down', 0), True)}")
            keys = [k for k, _ in MODES]
            if d.get("mode") in keys:
                self.mode.set_index(keys.index(d["mode"]))
            delay = d.get("delay")
            node = short_node(d.get("node") or "—")
            self.node.set_text(f"{node}" + (f"  {delay}ms" if delay else ""))
        else:
            self.clash_state.setText("Clash 未运行")
            self.speed.setText(d.get("error") or "")
            self.node.set_text("—")

    def _node_menu(self):
        d = self._clash
        nodes = d.get("nodes") or []
        if not nodes:
            return
        m = styled_menu(self)
        group = d.get("group")
        for n in nodes[:60]:
            a = m.addAction(("✓  " if n == d.get("node") else "    ") + short_node(n) + ("" if "@" not in n else f"    {n.split('@')[0]}"))
            a.triggered.connect(lambda _=False, n=n: self.ctx.clash.select(group, n))
        m.addSeparator()
        t = m.addAction("    测试当前节点延迟")
        t.triggered.connect(lambda: self.ctx.clash.test_delay(d.get("node"), lambda ms: self.node.set_text(
            f"{short_node(d.get('node') or '')}  {ms}ms" if ms else f"{short_node(d.get('node') or '')}  超时")))
        if self.island:
            self.island.locks.add("menu")
            m.aboutToHide.connect(lambda: self.island.locks.discard("menu"))
        m.popup(QtGui.QCursor.pos())

    def on_show(self):
        super().on_show()
        self.ctx.brightness.refresh()
        self.ctx.radio.refresh()


# ======================================================================== 窗口切换
class WinCard(Hoverable):
    closed = QtCore.Signal()

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self.info = info
        img = info.get("icon")
        self.pm = QtGui.QPixmap.fromImage(img) if isinstance(img, QtGui.QImage) and not img.isNull() else None
        self.setFixedHeight(54)
        self.setToolTip(f"{info.get('title')}\n{info.get('exe')}")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.MiddleButton or (
                e.button() == Qt.MouseButton.LeftButton and self._close_rect().contains(e.position())):
            self.closed.emit()
            return
        super().mouseReleaseEvent(e)

    def _close_rect(self):
        return QtCore.QRectF(self.width() - 26, 6, 20, 20)

    def paintEvent(self, e):
        p = painter(self)
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        s = self.press_scale()
        p.translate(r.center())
        p.scale(s, s)
        p.translate(-r.center())
        if theme.liquid:
            br = self.card_rect()
            self.card_transform(p, br)
            self.paint_card_bg(p, br, 14)
            if self.info.get("active"):
                cp = QtGui.QPainterPath()
                cp.addRoundedRect(br, 14, 14)
                p.strokePath(cp, QtGui.QPen(theme.on_color(), 1.2))
        else:
            fill = theme.card(1.0 + 0.7 * self._hover.x) if not self.info.get("active") else theme.active_pill()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(r, 14, 14)
        ir = QtCore.QRectF(r.x() + 10, r.center().y() - 14, 28, 28)
        if self.pm is not None:
            p.drawPixmap(ir.toRect(), self.pm)
        else:
            p.setFont(icon_font(18))
            p.setPen(theme.text(0.8))
            p.drawText(ir, Qt.AlignmentFlag.AlignCenter, G.APPS)
        tx = ir.right() + 9
        tw = r.right() - tx - (26 if self._hover.x > 0.3 else 8)
        p.setFont(ui_font(12.5, W.Medium))
        p.setPen(theme.text())
        fm = QtGui.QFontMetrics(p.font())
        theme.outlined_text(p, QtCore.QRectF(tx, r.y() + 8, tw, 20), Qt.AlignmentFlag.AlignVCenter,
                   fm.elidedText(self.info.get("title", ""), Qt.TextElideMode.ElideRight, int(tw)))
        p.setFont(ui_font(10.5))
        p.setPen(theme.text3())
        theme.outlined_text(p, QtCore.QRectF(tx, r.y() + 27, tw, 18), Qt.AlignmentFlag.AlignVCenter,
                   (self.info.get("exe") or "").removesuffix(".exe"))
        if self._hover.x > 0.05:
            cr = self._close_rect()
            c = theme.text(0.55 * self._hover.x)
            p.setFont(icon_font(10))
            p.setPen(c)
            p.drawText(cr, Qt.AlignmentFlag.AlignCenter, G.CLOSE)


class TasksPage(Page):
    key, glyph, title, height = "tasks", G.WINDOWS, "窗口", 300

    def __init__(self, ctx):
        super().__init__(ctx)
        self.sc = ScrollArea()
        self.grid = QtWidgets.QGridLayout(self.sc.inner)
        self.grid.setContentsMargins(0, 0, 4, 0)
        self.grid.setSpacing(8)
        self.count = Label("", 12, level=3)
        self.setLayout(vbox(hbox(Label("点击切换 · 中键或 × 关闭", 12, level=2), None, self.count), (self.sc, 1), spacing=8))
        self.timer = QtCore.QTimer(self, interval=2000, timeout=self.refresh)
        self._sig = None

    def refresh(self):
        wins = self.ctx.windows.list_windows()
        sig = tuple((w["hwnd"], w["title"], w.get("active")) for w in wins)
        if sig == self._sig:
            return
        self._sig = sig
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        cols = 3
        for i, w in enumerate(wins):
            c = WinCard(w)
            c.clicked.connect(lambda h=w["hwnd"]: self._activate(h))
            c.closed.connect(lambda h=w["hwnd"]: self._close(h))
            self.grid.addWidget(c, i // cols, i % cols)
        for k in range(cols):
            self.grid.setColumnStretch(k, 1)
        self.grid.setRowStretch(len(wins) // cols + 1, 1)
        self.count.setText(f"{len(wins)} 个窗口")
        rows = (len(wins) + cols - 1) // cols
        self.set_height(int(clamp(30 + rows * 62, 120, 330)))

    def _activate(self, hwnd):
        if self.island:
            self.island.collapse()
        QtCore.QTimer.singleShot(60, lambda: self.ctx.windows.activate(hwnd))

    def _close(self, hwnd):
        self.ctx.windows.close(hwnd)
        QtCore.QTimer.singleShot(400, self.refresh)

    def on_show(self):
        super().on_show()
        self._sig = None
        self.refresh()
        self.timer.start()

    def on_hide(self):
        super().on_hide()
        self.timer.stop()


# ======================================================================== 性能
class Meter(Card):
    def __init__(self, title: str, color: str, parent=None):
        super().__init__(parent, 18)
        self.t = Label(title, 12, W.DemiBold, level=2)
        self.v = Label("--", 22, W.DemiBold, num=True)
        self.v.setFixedHeight(30)
        self.sub = Label("", 10.5, level=3)
        self.spark = Sparkline(color=QtGui.QColor(color), fixed_max=100)
        self.spark.setFixedHeight(40)
        self.setLayout(vbox(hbox(self.t, None, self.sub), self.v, self.spark, spacing=0, margins=(12, 8, 12, 8)))


class PerfPage(Page):
    key, glyph, title, height = "perf", G.PULSE, "性能", 296

    def __init__(self, ctx):
        super().__init__(ctx)
        self.cpu = Meter("CPU", "#4f8cff")
        self.gpu = Meter("GPU", "#bf5af2")
        self.mem = Meter("内存", "#30d158")
        self.net = Card(radius=18)
        self.net_up = Label("", 12, W.Medium, num=True)
        self.net_dn = Label("", 12, W.Medium, num=True)
        self.disk = Label("", 11, level=3, num=True)
        self.sp_up = Sparkline(color=QtGui.QColor("#ff9f0a"))
        self.sp_dn = Sparkline(color=QtGui.QColor("#64d2ff"))
        for s in (self.sp_up, self.sp_dn):
            s.setFixedHeight(28)
        self.net.setLayout(vbox(hbox(Label("网络", 12, W.DemiBold, level=2), None, self.disk),
                                hbox(self.net_up, (self.sp_up, 1), spacing=6),
                                hbox(self.net_dn, (self.sp_dn, 1), spacing=6), spacing=2, margins=(12, 8, 12, 8)))
        self.top = Label("", 11.5, level=2, wrap=True)
        self.top.setFixedHeight(84)
        topcard = Card(radius=18)
        topcard.setLayout(vbox(Label("占用最高", 12, W.DemiBold, level=2), self.top, spacing=2, margins=(12, 8, 12, 8)))
        self.setLayout(vbox(hbox(self.cpu, self.gpu, self.mem, spacing=8),
                            hbox((self.net, 3), (topcard, 2), spacing=8), spacing=8))
        self.ttimer = QtCore.QTimer(self, interval=3000, timeout=self._top)
        for l in (self.net_up, self.net_dn):
            l.setFixedWidth(84)

    def set_data(self, d: dict):
        if not self.active:
            return
        h = d.get("history") or {}
        self.cpu.v.setText(f"{d.get('cpu', 0):.0f}%")
        self.cpu.spark.set_values(h.get("cpu") or [])
        cores = d.get("cpu_per_core") or []
        self.cpu.sub.setText(f"{len(cores)} 线程" if cores else "")
        g = d.get("gpu")
        self.gpu.v.setText("--" if g is None else f"{g:.0f}%")
        self.gpu.spark.set_values([x for x in (h.get("gpu") or []) if x is not None])
        gm = d.get("gpu_mem")
        self.gpu.sub.setText(f"显存 {fmt_bytes(gm)}" if gm else "")
        self.mem.v.setText(f"{d.get('mem_pct', 0):.0f}%")
        self.mem.spark.set_values(h.get("mem") or [])
        self.mem.sub.setText(f"{fmt_bytes(d.get('mem_used', 0))} / {fmt_bytes(d.get('mem_total', 0))}")
        self.net_up.setText(f"↑ {fmt_bytes(d.get('net_up', 0), True)}")
        self.net_dn.setText(f"↓ {fmt_bytes(d.get('net_down', 0), True)}")
        self.sp_up.set_values(h.get("net_up") or [])
        self.sp_dn.set_values(h.get("net_down") or [])
        self.disk.setText(f"磁盘 读 {fmt_bytes(d.get('disk_r', 0), True)} · 写 {fmt_bytes(d.get('disk_w', 0), True)}")

    def _top(self):
        def done(rows):
            if rows:
                self.top.setText("\n".join(f"{r['name'].removesuffix('.exe')[:18]:<18}  {r['cpu']:.1f}%  {fmt_bytes(r['mem'])}"
                                           for r in rows[:4]))
        run_bg(self.ctx.perf.top_processes, 4, on_done=done)

    def on_show(self):
        super().on_show()
        st = getattr(self.ctx.perf, "state", None)
        if st:
            self.set_data(st)
        self._top()
        self.ttimer.start()

    def on_hide(self):
        super().on_hide()
        self.ttimer.stop()

