# -*- coding: utf-8 -*-
"""股票（腾讯财经公开行情）与天气（Open-Meteo / OpenWeather）。"""
from __future__ import annotations

import datetime as dt

from PySide6 import QtCore, QtGui, QtWidgets

from ...core.config import cfg
from ..anim import Spring, clamp
from ..theme import G, W, theme, ui_font
from ..widgets import (Card, Hoverable, IconButton, Label, LineEdit, PillButton, ScrollArea, Segmented,
                       Sparkline, Themed, hbox, painter, vbox)
from .base import Page

Qt = QtCore.Qt
MARKETS = [("a", "A股"), ("hk", "港股"), ("us", "美股")]


def _pct_color(pct):
    if pct is None or abs(pct) < 1e-9:
        return theme.text2()
    return theme.up() if pct > 0 else theme.down()


class StockList(QtWidgets.QWidget, Themed):
    picked = QtCore.Signal(dict)
    menu_requested = QtCore.Signal(dict)
    ROW = 36

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[dict] = []
        self.sel = None
        self.hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hook_theme()

    def set_rows(self, rows):
        self.rows = rows
        self.setFixedHeight(max(40, len(rows) * self.ROW))
        self.update()

    def mouseMoveEvent(self, e):
        i = int(e.position().y() // self.ROW)
        if i != self.hover:
            self.hover = i
            self.update()

    def leaveEvent(self, e):
        self.hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        i = int(e.position().y() // self.ROW)
        if e.button() == Qt.MouseButton.RightButton:
            if 0 <= i < len(self.rows):
                self.menu_requested.emit(self.rows[i])
            return
        if 0 <= i < len(self.rows):
            self.sel = self.rows[i].get("code")
            self.picked.emit(self.rows[i])
            self.update()

    def paintEvent(self, e):
        p = painter(self)
        if not self.rows:
            p.setFont(ui_font(12))
            p.setPen(theme.text3())
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "自选为空，点右上角 + 添加")
            return
        w = self.width()
        for i, s in enumerate(self.rows):
            y = i * self.ROW
            r = QtCore.QRectF(0, y + 1, w, self.ROW - 2)
            if i == self.hover or s.get("code") == self.sel:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(theme.hover() if i == self.hover else theme.card(0.8))
                p.drawRoundedRect(r, 12, 12)
            p.setFont(ui_font(13, W.Medium))
            p.setPen(theme.text())
            p.drawText(QtCore.QRectF(12, y, 150, self.ROW), Qt.AlignmentFlag.AlignVCenter, s.get("name") or s.get("code"))
            p.setFont(ui_font(10.5, num=True))
            p.setPen(theme.text3())
            p.drawText(QtCore.QRectF(150, y, 120, self.ROW), Qt.AlignmentFlag.AlignVCenter, s.get("code", ""))
            price, pct = s.get("price"), s.get("pct")
            p.setFont(ui_font(13.5, W.DemiBold, num=True))
            p.setPen(theme.text())
            p.drawText(QtCore.QRectF(w - 210, y, 110, self.ROW), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       "--" if price is None else (f"{price:.3f}" if price < 10 else f"{price:.2f}"))
            # 涨跌幅胶囊
            pr = QtCore.QRectF(w - 88, y + 7, 78, self.ROW - 14)
            col = _pct_color(pct)
            bg = QtGui.QColor(col)
            bg.setAlpha(46)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(pr, pr.height() / 2, pr.height() / 2)
            p.setPen(col)
            p.setFont(ui_font(12.5, W.DemiBold, num=True))
            p.drawText(pr, Qt.AlignmentFlag.AlignCenter, "--" if pct is None else f"{pct:+.2f}%")


class StocksPage(Page):
    key, glyph, title, height = "stock", G.STOCK, "股票", 330

    def __init__(self, ctx):
        super().__init__(ctx)
        self.data: dict = {}
        self.market = "a"
        self.seg = Segmented([n for _, n in MARKETS])
        self.seg.setFixedWidth(180)
        self.seg.changed.connect(self._market)
        self.status = Label("", 11.5, level=3, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.add_btn = IconButton(G.ADD, 28, 12, "添加自选（代码 / 名称 / 拼音）")
        self.add_btn.clicked.connect(self._start_add)
        self.add_edit = LineEdit("代码 / 名称 / 拼音，回车搜索")
        self.add_edit.setFixedWidth(220)
        self.add_edit.setFixedHeight(30)
        self.add_edit.hide()
        self.add_edit.focus_wanted.connect(self.want_focus)
        self.add_edit.returnPressed.connect(self._do_search)
        self.add_edit.installEventFilter(self)
        # 分时卡片
        self.detail = Card(radius=16)
        self.d_name = Label("", 13, W.DemiBold)
        self.d_price = Label("", 13, W.DemiBold, num=True, align=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.spark = Sparkline()
        self.spark.setFixedHeight(56)
        self.detail.setLayout(vbox(hbox(self.d_name, self.d_price), self.spark, spacing=2, margins=(12, 8, 12, 8)))
        self.detail.hide()
        self.list = StockList()
        self.list.picked.connect(self._pick)
        self.list.menu_requested.connect(self._row_menu)
        sc = ScrollArea()
        lay = QtWidgets.QVBoxLayout(sc.inner)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.addWidget(self.list)
        lay.addStretch(1)
        self.err = Label("", 12, level=2, align=Qt.AlignmentFlag.AlignCenter)
        self.err.hide()
        self.setLayout(vbox(hbox(self.seg, None, self.add_edit, self.status, self.add_btn, spacing=6),
                            self.detail, self.err, (sc, 1), spacing=8))

    def _market(self, i):
        self.market = MARKETS[i][0]
        self.detail.hide()
        self.list.sel = None
        self._render()

    def _pick(self, s):
        self.d_name.setText(s.get("name") or s.get("code"))
        pct = s.get("pct")
        self.d_price.setText(f"{s.get('price') or '--'}   {pct:+.2f}%" if pct is not None else "--")
        self.d_price.set_color(_pct_color(pct))
        self.detail.show()
        code = s.get("code")
        prev = s.get("prev_close")
        self.ctx.stocks.minute(code, lambda pts, prev=prev: self._minute(code, pts, prev))

    # ---------- 添加 / 删除自选 ----------
    def _start_add(self):
        self.add_btn.hide()
        self.status.hide()
        self.add_edit.clear()
        self.add_edit.show()
        self.want_focus()
        self.add_edit.setFocus()

    def _end_add(self):
        self.add_edit.hide()
        self.add_btn.show()
        self.status.show()
        if self.island is not None:
            self.island.release_focus()

    def _do_search(self):
        q = self.add_edit.text().strip()
        if not q:
            self._end_add()
            return
        self.ctx.stocks.search(q, self._results)

    def _results(self, items):
        from .system import styled_menu
        self._end_add()
        m = styled_menu(self)
        if not items:
            m.addAction("没有找到匹配的股票").setEnabled(False)
        for it in items[:10]:
            a = m.addAction(f"{it['name']}    {it['code']}")
            a.triggered.connect(lambda _=False, c=it["code"]: self._add(c))
        if self.island:
            self.island.locks.add("menu")
            m.aboutToHide.connect(lambda: self.island.locks.discard("menu"))
        m.popup(QtGui.QCursor.pos())

    def _add(self, code):
        from ...services.stocks import market_of
        self.ctx.stocks.add(code)
        i = [k for k, _ in MARKETS].index(market_of(code))
        self.seg.set_index(i)
        self._market(i)

    def _row_menu(self, row):
        from .system import styled_menu
        m = styled_menu(self)
        m.addAction(f"从自选删除 {row.get('name') or row.get('code')}").triggered.connect(
            lambda: self.ctx.stocks.remove(row.get("code", "")))
        if self.island:
            self.island.locks.add("menu")
            m.aboutToHide.connect(lambda: self.island.locks.discard("menu"))
        m.popup(QtGui.QCursor.pos())

    def eventFilter(self, obj, ev):
        if obj is self.add_edit and ev.type() == QtCore.QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_Escape:
            self._end_add()
            return True
        if obj is self.add_edit and ev.type() == QtCore.QEvent.Type.FocusOut and not self.add_edit.text().strip():
            self._end_add()
        return False

    def _minute(self, code, pts, prev):
        if self.list.sel != code:
            return
        col = _pct_color((pts[-1] - prev) if pts and prev else 0)
        self.spark.color = col
        self.spark.set_values(pts, baseline=prev)

    def set_data(self, d: dict):
        self.data = d
        if self.active:
            self._render()

    def _render(self):
        d = self.data or {}
        rows = (d.get("markets") or {}).get(self.market) or []
        st = (d.get("status") or {}).get(self.market, "")
        t = d.get("time")
        ts = dt.datetime.fromtimestamp(t).strftime("%H:%M:%S") if isinstance(t, (int, float)) else (t or "")
        self.status.setText(f"{st}  {ts}".strip())
        if not d.get("ok") and d.get("error"):
            self.err.setText(d["error"])
            self.err.show()
        else:
            self.err.hide()
        self.list.set_rows(rows)

    def on_show(self):
        super().on_show()
        self._render()


# ======================================================================== 天气
class GlyphLabel(QtWidgets.QWidget, Themed):
    def __init__(self, px: int, parent=None):
        super().__init__(parent)
        self.px = px
        self.glyph = ("", "Segoe Fluent Icons")
        self.setFixedSize(px + 10, px + 10)
        self._hook_theme()

    def set_glyph(self, g):
        self.glyph = g
        self.update()

    def paintEvent(self, e):
        p = painter(self)
        f = QtGui.QFont()
        f.setFamilies([self.glyph[1], "Segoe Fluent Icons", "Segoe UI Symbol"])
        f.setPixelSize(self.px)
        p.setFont(f)
        p.setPen(theme.text(0.9))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.glyph[0])


class Hourly(QtWidgets.QWidget, Themed):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.tz = None
        self.setFixedHeight(78)
        self._hook_theme()

    def set_items(self, items):
        self.items = items[:8]
        self.update()

    def paintEvent(self, e):
        from ...services.weather import weather_glyph
        p = painter(self)
        n = max(1, len(self.items))
        cw = self.width() / n
        for i, it in enumerate(self.items):
            x = i * cw
            p.setFont(ui_font(11, num=True))
            p.setPen(theme.text3())
            p.drawText(QtCore.QRectF(x, 0, cw, 16), Qt.AlignmentFlag.AlignCenter,
                       (dt.datetime.fromtimestamp(it.get("time", 0) + self.tz, dt.timezone.utc) if self.tz is not None
                        else dt.datetime.fromtimestamp(it.get("time", 0))).strftime("%H时"))
            g, fam = weather_glyph(it.get("icon"))
            f = QtGui.QFont()
            f.setFamilies([fam, "Segoe Fluent Icons", "Segoe UI Symbol"])
            f.setPixelSize(19)
            p.setFont(f)
            p.setPen(theme.text(0.9))
            p.drawText(QtCore.QRectF(x, 18, cw, 28), Qt.AlignmentFlag.AlignCenter, g)
            p.setFont(ui_font(13, W.DemiBold, num=True))
            p.setPen(theme.text())
            p.drawText(QtCore.QRectF(x, 46, cw, 16), Qt.AlignmentFlag.AlignCenter, f"{round(it.get('temp', 0))}°")
            pop = it.get("pop") or 0
            if pop >= 0.2:
                p.setFont(ui_font(10, num=True))
                p.setPen(QtGui.QColor("#4f9cff"))
                p.drawText(QtCore.QRectF(x, 62, cw, 14), Qt.AlignmentFlag.AlignCenter, f"{round(pop * 100)}%")


class Daily(QtWidgets.QWidget, Themed):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self._hook_theme()

    def set_items(self, items):
        self.items = items[:5]
        self.update()

    def paintEvent(self, e):
        from ...services.weather import weather_glyph
        if not self.items:
            return
        p = painter(self)
        lo = min(i["min"] for i in self.items)
        hi = max(i["max"] for i in self.items)
        rh = self.height() / len(self.items)
        wk = "一二三四五六日"
        for k, it in enumerate(self.items):
            y = k * rh
            d = it.get("date")
            try:
                day = dt.date.fromisoformat(str(d))
                name = "今天" if day == dt.date.today() else "周" + wk[day.weekday()]
            except Exception:  # noqa: BLE001
                name = str(d)
            p.setFont(ui_font(12.5, W.Medium))
            p.setPen(theme.text())
            p.drawText(QtCore.QRectF(0, y, 44, rh), Qt.AlignmentFlag.AlignVCenter, name)
            g, fam = weather_glyph(it.get("icon"))
            f = QtGui.QFont()
            f.setFamilies([fam, "Segoe Fluent Icons", "Segoe UI Symbol"])
            f.setPixelSize(16)
            p.setFont(f)
            p.drawText(QtCore.QRectF(44, y, 26, rh), Qt.AlignmentFlag.AlignCenter, g)
            p.setFont(ui_font(12, num=True))
            p.setPen(theme.text2())
            p.drawText(QtCore.QRectF(74, y, 30, rh), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, f"{round(it['min'])}°")
            p.setPen(theme.text())
            p.drawText(QtCore.QRectF(self.width() - 32, y, 32, rh), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       f"{round(it['max'])}°")
            bx, bw = 112, self.width() - 112 - 40
            span = max(1e-6, hi - lo)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.track())
            p.drawRoundedRect(QtCore.QRectF(bx, y + rh / 2 - 2.5, bw, 5), 2.5, 2.5)
            x0 = bx + bw * (it["min"] - lo) / span
            x1 = bx + bw * (it["max"] - lo) / span
            g2 = QtGui.QLinearGradient(bx, 0, bx + bw, 0)
            g2.setColorAt(0, QtGui.QColor("#5ac8fa"))
            g2.setColorAt(1, QtGui.QColor("#ff9f0a"))
            p.setBrush(g2)
            p.drawRoundedRect(QtCore.QRectF(x0, y + rh / 2 - 2.5, max(5, x1 - x0), 5), 2.5, 2.5)


def paint_chip(p, r, name: str, temp: str, glyph, selected: bool, default: bool, hover: float = 0.0):
    """一枚城市胶囊的外形：底、天气图标、名称、温度、默认小圆点。"""
    rad = r.height() / 2
    if selected:
        if theme.liquid:
            from ..liquid import paint_chip as glass_chip
            glass_chip(p, r, rad, theme.active_pill(), active=True)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.active_pill())
            p.drawRoundedRect(r, rad, rad)
    elif hover > 0.01:
        c = theme.hover()
        c.setAlphaF(c.alphaF() * hover)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(r, rad, rad)
    f = QtGui.QFont()
    f.setFamilies([glyph[1], "Segoe Fluent Icons", "Segoe UI Symbol"])
    f.setPixelSize(14)
    p.setFont(f)
    p.setPen(theme.text(0.9))
    p.drawText(QtCore.QRectF(r.x() + 8, r.y(), 18, r.height()), Qt.AlignmentFlag.AlignCenter, glyph[0])
    p.setFont(ui_font(12.5, W.DemiBold))
    p.setPen(theme.pill_text() if selected else theme.text(0.75))
    fm = QtGui.QFontMetrics(p.font())
    x = r.x() + 30
    p.drawText(QtCore.QRectF(x, r.y(), 200, r.height()), Qt.AlignmentFlag.AlignVCenter, name)
    x += fm.horizontalAdvance(name) + 6
    p.setFont(ui_font(12, W.Medium, num=True))
    p.setPen(theme.text2())
    p.drawText(QtCore.QRectF(x, r.y(), 60, r.height()), Qt.AlignmentFlag.AlignVCenter, temp or "--°")
    if default:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.on_color())
        p.drawEllipse(QtCore.QPointF(r.right() - 6, r.y() + 6), 2.5, 2.5)


GMX, GMY, GMB = 10.0, 8.0, 14.0       # 拖拽浮层相对胶囊本体左右 / 上 / 下的留白（放阴影和放大）


class ChipGhost(QtWidgets.QWidget):
    """拖动时浮起来的那枚胶囊：放大、抬高、带柔和阴影，跟着鼠标走。"""
    def __init__(self, chip: "CityChip", parent=None):
        super().__init__(parent)
        self.name, self.temp, self.glyph = chip.name, chip.temp, chip.glyph
        self.selected, self.default = chip.selected, chip.default
        self.lift = Spring(0.0, 320, 0.55, 0.02)      # 0 收 / 1 完全浮起
        b = chip.body()
        self.setFixedSize(round(b.width() + GMX * 2), round(b.height() + GMY + GMB))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def body(self) -> QtCore.QRectF:
        return QtCore.QRectF(GMX, GMY, self.width() - GMX * 2, self.height() - GMY - GMB)

    def paintEvent(self, e):
        p = painter(self)
        r = self.body()
        t = clamp(self.lift.x, 0.0, 1.0)
        p.save()
        p.translate(0, -7 * t)                        # 抬离原位
        k = 1.0 + 0.05 * t
        p.translate(r.center())
        p.scale(k, k)
        p.translate(-r.center())
        rad = r.height() / 2
        for dy, a in ((10, 0.05), (6, 0.09), (3, 0.13)):     # 阴影：几层圆角，越远越淡
            c = QtGui.QColor(0, 0, 0, int(255 * a * t))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(r.adjusted(-1, dy - 1, 1, dy + 1), rad, rad)
        if not self.selected:                                  # 未选中的胶囊平时没有底，浮起来要补一层
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.card(1.5))
            p.drawRoundedRect(r, rad, rad)
        paint_chip(p, r, self.name, self.temp, self.glyph, self.selected, self.default, 0.0)
        p.restore()


class CityChip(Hoverable):
    """城市胶囊：名称 + 当前温度；选中时半透明白底。长按后左右拖动可调整顺序。"""
    drag_begin = QtCore.Signal(object)          # 长按成功，payload = 自己
    drag_move = QtCore.Signal(object, QtCore.QPoint)
    drag_end = QtCore.Signal(object)
    PAD = 6                                     # 左右留白：果冻拉伸时不至于被自己的矩形裁掉

    def __init__(self, idx: int, name: str, parent=None):
        super().__init__(parent)
        self.idx, self.name = idx, name
        self.temp = ""
        self.glyph = ("", "Segoe Fluent Icons")
        self.selected = False
        self.default = idx == 0
        self.pop = Spring(0.0, 420, 0.32, 0.01)     # 落位后的果冻：从 1 弹回 0（欠阻尼来回晃）
        self.placeholder = False                    # 拖动中把自己画成半透明的占位
        self.setFixedHeight(30)
        self.setToolTip("单击查看，长按拖动可调整城市顺序；右键可设为默认 / 删除")
        self._fit()
        self._dragging = False
        self._press_global: QtCore.QPoint | None = None
        self._lp = QtCore.QTimer(self, singleShot=True, interval=380)
        self._lp.timeout.connect(self._begin_drag)

    def body(self) -> QtCore.QRectF:
        return QtCore.QRectF(self.rect()).adjusted(self.PAD, 1, -self.PAD, -1)

    def _tick(self):
        self.pop.step(0.016)
        super()._tick()
        if not self.pop.rest and not self._timer.isActive():
            self._timer.start()

    def kick(self, amount: float = 1.0):
        """被放下时弹一下：横向拉长、纵向压扁，再反弹回来。"""
        self.pop.snap(amount)
        self.pop.to(0.0)
        self._kick()

    def _fit(self):
        fm = QtGui.QFontMetrics(ui_font(12.5, W.DemiBold))
        self.setFixedWidth(fm.horizontalAdvance(self.name) + fm.horizontalAdvance(self.temp or "--°")
                           + 50 + self.PAD * 2)

    def set_info(self, temp: str, glyph):
        self.temp, self.glyph = temp, glyph
        self._fit()
        self.update()

    def _begin_drag(self):
        if self._press_global is None:
            return
        self._dragging = True
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        self.drag_begin.emit(self)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press_global = e.globalPosition().toPoint()
            self._lp.start()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging:
            self.drag_move.emit(self, e.globalPosition().toPoint())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._lp.stop()
        if self._dragging:
            self._dragging = False
            self._press_global = None
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self._press.to(0)
            self._kick()
            if e.button() == Qt.MouseButton.LeftButton:
                self.drag_end.emit(self)
            e.accept()
            return
        self._press_global = None
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        from ..widgets import painter as _p
        p = _p(self)
        if self.placeholder:                      # 拖动中：原位只剩一个淡淡的"占位"
            p.setOpacity(0.26)
        r = self.body()
        osc = self.pop.x
        if abs(osc) > 0.004:
            # 果冻：横向拉长 + 纵向压扁，回弹时反向再来一下（左右预留了 PAD，拉长不会被裁）
            kx = 1.0 + 0.10 * osc
            ky = 1.0 - 0.07 * osc if osc > 0 else 1.0
            p.translate(r.center())
            p.scale(kx, ky)
            p.translate(-r.center())
        paint_chip(p, r, self.name, self.temp, self.glyph, self.selected, self.default, self._hover.x)


def _fmt_clock(ts, tz_off):
    if not ts:
        return "--"
    return dt.datetime.fromtimestamp(int(ts) + int(tz_off or 0), dt.timezone.utc).strftime("%H:%M")


def _wind_dir(deg):
    if deg is None:
        return ""
    return ["北", "东北", "东", "东南", "南", "西南", "西", "西北"][int(((deg + 22.5) % 360) // 45)] + "风"


class WeatherPage(Page):
    key, glyph, title, height = "weather", G.CLOUD, "天气", 318

    def __init__(self, ctx):
        super().__init__(ctx)
        self.sel = 0
        self.data: list[dict] = []
        self.chips: list[CityChip] = []
        # 拖拽浮层（长按城市胶囊时浮起来的那一枚）与落位弹簧
        self._drag_chip: CityChip | None = None
        self._ghost: ChipGhost | None = None
        self._ghost_host: QtWidgets.QWidget | None = None
        self._ghost_chip: CityChip | None = None
        self._ghost_center: QtCore.QPoint | None = None
        self._ghost_x = Spring(0.0, 560, 0.5, 0.5)
        self._ghost_y = Spring(0.0, 560, 0.5, 0.5)
        self._ghost_t = QtCore.QTimer(self, interval=16, timeout=self._ghost_tick)
        # 顶部：城市胶囊 + 添加
        self.chip_row = QtWidgets.QHBoxLayout()
        self.chip_row.setSpacing(4)
        self.chip_row.setContentsMargins(0, 0, 0, 0)
        self.add_btn = IconButton(G.ADD, 28, 12, "添加城市")
        self.add_btn.clicked.connect(self._start_add)
        self.add_edit = LineEdit("城市名")
        self.add_edit.setFixedWidth(220)
        self.add_edit.setFixedHeight(30)
        self.add_edit.hide()
        self.add_edit.focus_wanted.connect(self.want_focus)
        self.add_edit.returnPressed.connect(self._do_add)
        self.add_edit.installEventFilter(self)
        refresh = IconButton(G.REFRESH, 28, 12, "刷新")
        refresh.clicked.connect(lambda: ctx.weather.refresh())
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(6)
        head.setContentsMargins(0, 0, 0, 0)
        head.addLayout(self.chip_row)
        head.addWidget(self.add_btn)
        head.addWidget(self.add_edit)
        head.addStretch(1)
        self.msg = Label("", 11.5, level=3)
        head.addWidget(self.msg)
        head.addWidget(refresh)

        # 详情
        self.icon = GlyphLabel(44)
        self.temp = Label("--°", 44, W.Light, num=True)
        self.temp.setFixedHeight(56)
        self.desc = Label("", 14, W.Medium)
        self.city = Label("", 12, level=2)
        self.hourly = Hourly()
        self.daily = Daily()
        self.daily.setFixedWidth(250)
        self.facts = Facts()
        left = vbox(hbox(self.icon, self.temp, None, spacing=6), self.desc, self.city, None, spacing=2)
        self.body = QtWidgets.QWidget()
        self.body.setLayout(vbox(hbox((left, 1), self.daily, spacing=16), self.facts, self.hourly, spacing=6))
        self.err = Label("", 13, level=2, align=Qt.AlignmentFlag.AlignCenter, wrap=True)
        self.err.hide()
        self.setLayout(vbox(head, (self.body, 1), self.err, spacing=8))
        ctx.weather.cities_updated.connect(self.set_cities)
        ctx.weather.city_added.connect(self._added)

    def on_hide(self):
        if self._ghost is not None:             # 切页 / 收起时把浮层一起收掉
            self._abort_drag()
        super().on_hide()

    # ---------- 城市 ----------
    def set_data(self, d: dict):
        """兼容：第一个城市的数据 / 错误。"""
        if not d.get("ok") and not self.data:
            self.err.setText(d.get("error") or "暂无天气数据")
            self.err.show()
            self.body.hide()

    def set_cities(self, data: list):
        from ...services.weather import weather_glyph
        if self._ghost is not None:                 # 数据在这时候刷新：先把拖动收尾，别把浮层留在屏幕上
            self._abort_drag()
        self.data = data
        names = [d.get("name", "?") for d in data]
        if [c.name for c in self.chips] != names:
            for c in self.chips:
                c.deleteLater()
            self.chips = []
            for i, n in enumerate(names):
                c = CityChip(i, n)
                c.clicked.connect(lambda c=c: self.select(self.chips.index(c)))
                c.right_clicked.connect(lambda c=c: self._menu(self.chips.index(c)))
                c.drag_begin.connect(self._drag_begin)
                c.drag_move.connect(self._drag_move)
                c.drag_end.connect(self._drag_end)
                self.chip_row.addWidget(c)
                self.chips.append(c)
        for c, d in zip(self.chips, data):
            c.default = c.idx == 0
            c.set_info(f"{round(d['temp'])}°" if d.get("temp") is not None else "--°", weather_glyph(d.get("icon")))
        self.sel = min(self.sel, max(0, len(data) - 1))
        self.select(self.sel)

    def select(self, i: int):
        self.sel = i
        for c in self.chips:
            c.selected = c.idx == i
            c.update()
        if not self.data:
            return
        self._show(self.data[i])

    # ---------- 长按拖动调整城市顺序 ----------
    def _drag_begin(self, chip):
        self._drag_chip = chip
        if self.island:
            self.island.locks.add("drag")       # 拖到面板外面也不收起
        for c in self.chips:
            c._press.to(0)
        chip.placeholder = True                 # 原位只剩淡淡的占位，真正被拖的是浮层
        chip.pop.snap(0.0)
        chip.update()
        # 浮层挂在整个内容区上（页面本身顶到边，往上抬会被页面裁掉）
        self._ghost_host = getattr(self.island, "content", None) or self
        self._ghost = ChipGhost(chip, self._ghost_host)
        gp = chip.mapTo(self._ghost_host, chip.body().topLeft().toPoint())
        self._ghost.move(gp - QtCore.QPoint(int(GMX), int(GMY)))
        self._ghost.show()
        self._ghost.raise_()
        self._ghost.lift.to(1.0, 300, 0.62)     # 抓起来的瞬间浮起：放大 + 抬高 + 阴影
        self._ghost_center = chip.mapToGlobal(chip.rect().center())
        self._ghost_chip = None
        self._ghost_x.snap(self._ghost.x())
        self._ghost_y.snap(self._ghost.y())
        self._ghost_t.start()

    def _chip_target(self, gx: int) -> int:
        for i, c in enumerate(self.chips):
            if gx < c.mapToGlobal(QtCore.QPoint(c.width() // 2, 0)).x():
                return i
        return len(self.chips) - 1

    def _drag_move(self, chip, gpos):
        if chip is not getattr(self, "_drag_chip", None) or not self.chips:
            return
        self._ghost_center = gpos             # 浮层跟着鼠标；原位占位随顺序一起挪
        cur = self.chips.index(chip)
        target = self._chip_target(gpos.x())
        if target == cur:
            return
        # 实时挪位置：布局、数据、服务里的顺序一起换
        self.chips.pop(cur)
        self.chips.insert(target, chip)
        self.chip_row.removeWidget(chip)
        self.chip_row.insertWidget(target, chip)
        if 0 <= cur < len(self.data) and 0 <= target < len(self.data):
            self.data.insert(target, self.data.pop(cur))
        for k, c in enumerate(self.chips):
            c.idx = k
            c.default = k == 0
            c.update()
        self.ctx.weather.move_city(cur, target)
        self.sel = target

    def _drag_end(self, chip):
        self._drag_chip = None
        if self.island:
            self.island.locks.discard("drag")
        if self.chips:
            self.select(self.chips.index(chip))
        self.msg.setText("已调整城市顺序")
        QtCore.QTimer.singleShot(3000, lambda: self.msg.setText(""))
        ghost = self._ghost
        if ghost is None:
            chip.placeholder = False
            chip.kick()
            return
        # 浮层落回这一格，落稳后本体再"果冻"一下
        self.layout().activate()
        self.chip_row.activate()
        p0 = chip.mapTo(self._ghost_host, chip.body().topLeft().toPoint())
        self._ghost_x.to(p0.x() - GMX, 560, 0.62)
        self._ghost_y.to(p0.y() - GMY, 560, 0.62)
        ghost.lift.to(0.0, 320, 0.7)
        self._ghost_chip = chip
        self._ghost_t.start()

    # ---------- 拖动浮层 ----------
    def _ghost_tick(self):
        ghost = self._ghost
        if ghost is None:
            self._ghost_t.stop()
            return
        ghost.lift.step(0.016)
        if self._ghost_chip is not None:            # 落位阶段：位置也走弹簧
            self._ghost_x.step(0.016)
            self._ghost_y.step(0.016)
            ghost.move(round(self._ghost_x.x), round(self._ghost_y.x))
        elif self._ghost_center is not None:        # 拖动阶段：本体中心跟鼠标
            b = ghost.body()
            c = self._ghost_host.mapFromGlobal(self._ghost_center)
            ghost.move(round(c.x() - b.width() / 2 - b.x()),
                       round(c.y() - b.height() / 2 - b.y()))
        ghost.update()
        if (self._ghost_chip is not None and ghost.lift.rest
                and self._ghost_x.rest and self._ghost_y.rest):
            self._ghost_t.stop()
            self._drop_ghost()

    def _drop_ghost(self):
        chip, ghost = self._ghost_chip, self._ghost
        self._ghost, self._ghost_chip, self._ghost_center = None, None, None
        if ghost is not None:
            ghost.hide()
            ghost.deleteLater()
        if chip is None:
            return
        chip.placeholder = False
        chip.update()
        chip.kick()                                 # 果冻：拉长压扁 → 弹回

    def _abort_drag(self):
        """中途被打断（数据刷新 / 页面收起）：浮层直接收掉，不留落位动画。"""
        self._ghost_t.stop()
        ghost, chip = self._ghost, self._ghost_chip or self._drag_chip
        self._ghost, self._ghost_chip, self._ghost_center, self._drag_chip = None, None, None, None
        if ghost is not None:
            ghost.hide()
            ghost.deleteLater()
        if chip is not None:
            chip.placeholder = False
            chip.pop.snap(0.0)
            chip.update()
        if self.island:
            self.island.locks.discard("drag")


    def _show(self, d: dict):
        from ...services.weather import weather_glyph
        if d.get("temp") is None:
            self.err.setText(d.get("error") or "暂无数据")
            self.err.show()
            self.body.hide()
            return
        self.err.hide()
        self.body.show()
        self.msg.setText(d.get("error") or "")
        self.icon.set_glyph(weather_glyph(d.get("icon")))
        self.temp.setText(f"{round(d.get('temp', 0))}°")
        self.desc.setText(d.get("desc", ""))
        lo, hi = d.get("temp_min"), d.get("temp_max")
        rng = f"   最低 {round(lo)}° 最高 {round(hi)}°" if lo is not None and hi is not None else ""
        self.city.setText(f"{d.get('name', '')}{rng}")
        tz = d.get("tz_offset", 0)
        vis = d.get("visibility")
        self.facts.set_items([
            ("体感", f"{round(d.get('feels_like', 0))}°"),
            ("湿度", f"{d.get('humidity', '--')}%"),
            ("风", f"{_wind_dir(d.get('wind_deg'))} {d.get('wind', '--')}m/s"),
            ("气压", f"{d.get('pressure', '--')}hPa"),
            ("能见度", f"{vis / 1000:.0f}km" if vis else "--"),
            ("云量", f"{d.get('clouds', '--')}%"),
            ("日出", _fmt_clock(d.get("sunrise"), tz)),
            ("日落", _fmt_clock(d.get("sunset"), tz)),
        ])
        self.hourly.tz = tz
        self.hourly.set_items(d.get("hourly") or [])
        self.daily.set_items(d.get("daily") or [])

    def _menu(self, i: int):
        from .system import styled_menu
        m = styled_menu(self)
        if i > 0:
            m.addAction("设为默认").triggered.connect(lambda: self._default(i))
        a = m.addAction("删除该城市")
        a.setEnabled(len(self.data) > 1)
        a.triggered.connect(lambda: self._remove(i))
        if self.island:
            self.island.locks.add("menu")
            m.aboutToHide.connect(lambda: self.island.locks.discard("menu"))
        m.popup(QtGui.QCursor.pos())

    def _default(self, i):
        self.sel = 0
        self.ctx.weather.make_default(i)

    def _remove(self, i):
        if self.sel >= i and self.sel > 0:
            self.sel -= 1
        self.ctx.weather.remove_city(i)

    def _start_add(self):
        self.add_btn.hide()
        self.add_edit.clear()
        self.add_edit.show()
        self.want_focus()
        self.add_edit.setFocus()
        # 点到输入框以外的任何地方就取消（灵动岛内外都算）
        import ctypes
        u32 = ctypes.WinDLL("user32")
        st = {"armed": False}
        if getattr(self, "_add_watch", None) is None:
            self._add_watch = QtCore.QTimer(self, interval=25)

        def tick():
            if not self.add_edit.isVisible():
                self._add_watch.stop()
                return
            down = any(u32.GetAsyncKeyState(k) & 0x8000 for k in (0x01, 0x02))
            if not st["armed"]:
                st["armed"] = not down
                return
            if down:
                r = QtCore.QRect(self.add_edit.mapToGlobal(QtCore.QPoint(0, 0)), self.add_edit.size())
                if not r.contains(QtGui.QCursor.pos()):
                    self._end_add()
        try:
            self._add_watch.timeout.disconnect()
        except (RuntimeError, TypeError):
            pass
        self._add_watch.timeout.connect(tick)
        self._add_watch.start()

    def _end_add(self):
        self.add_edit.hide()
        self.add_btn.show()
        if getattr(self, "_add_watch", None) is not None:
            self._add_watch.stop()
        if self.island is not None:
            self.island.release_focus()

    def _do_add(self):
        q = self.add_edit.text().strip()
        if q:
            self.msg.setText(f"正在查找 {q}…")
            self.ctx.weather.add_city(q)
        self._end_add()

    def _added(self, ok: bool, text: str):
        self.msg.setText(text)
        if ok:
            self.sel = len(self.data)       # 新城市在末尾，刷新后选中它
        QtCore.QTimer.singleShot(4000, lambda: self.msg.setText(""))

    def eventFilter(self, obj, ev):
        if obj is self.add_edit and ev.type() == QtCore.QEvent.Type.KeyPress and ev.key() == Qt.Key.Key_Escape:
            self._end_add()
            return True
        if obj is self.add_edit and ev.type() == QtCore.QEvent.Type.FocusOut and not self.add_edit.text().strip():
            self._end_add()
        return False

    def on_show(self):
        super().on_show()
        if self.data:
            self.select(self.sel)


class Facts(QtWidgets.QWidget, Themed):
    """详情网格：两行四列的小标签。"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[tuple[str, str]] = []
        self.setFixedHeight(44)
        self._hook_theme()

    def set_items(self, items):
        self.items = items
        self.update()

    def paintEvent(self, e):
        p = painter(self)
        cols = 4
        cw = self.width() / cols
        rh = self.height() / 2
        for i, (k, v) in enumerate(self.items[:8]):
            x, y = (i % cols) * cw, (i // cols) * rh
            p.setFont(ui_font(11))
            p.setPen(theme.text3())
            p.drawText(QtCore.QRectF(x, y, 44, rh), Qt.AlignmentFlag.AlignVCenter, k)
            p.setFont(ui_font(12, W.Medium, num=True))
            p.setPen(theme.text())
            p.drawText(QtCore.QRectF(x + 44, y, cw - 46, rh), Qt.AlignmentFlag.AlignVCenter, v)


_ = (cfg, clamp)
