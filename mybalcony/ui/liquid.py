# -*- coding: utf-8 -*-
"""液态玻璃的通用绘制。

岛本体、二级菜单、弹出卡片用的是同一套"光学层"：背景先抓屏（模糊 + 提纯），再沿形状边缘做
位移折射，最后叠暗内壁 / 亮刃口 / 镜面反射。任何自己开窗口自绘的小面板都可以直接复用。
"""
from __future__ import annotations

import time

from PySide6 import QtCore, QtGui, QtWidgets

from . import glass
from .theme import theme

Qt = QtCore.Qt

DOWN = 3                    # 弹层很小，抓屏可以更清楚一点
TTL = 0.8                   # 抓到的背景最多沿用 0.8 秒


def _panel_brush(img: QtGui.QImage, rect: QtCore.QRectF) -> QtGui.QBrush | None:
    if img is None:
        return None
    b = QtGui.QBrush(img)
    tr = QtGui.QTransform()
    tr.translate(rect.left(), rect.top())
    tr.scale(rect.width() / img.width(), rect.height() / img.height())
    b.setTransform(tr)
    return b


def _backdrop(widget: QtWidgets.QWidget, rect: QtCore.QRectF, radius: float) -> QtGui.QImage | None:
    """抓一块窗口背后的真实背景（按窗口 + 形状缓存）：没有桌面内容时返回 None，调用方退回纯色调。"""
    g = widget.mapToGlobal(rect.topLeft().toPoint())
    grect = QtCore.QRect(g.x(), g.y(), int(rect.width()), int(rect.height()))
    key = (theme.pal_name, grect.x(), grect.y(), grect.width(), grect.height(), int(radius))
    cache = getattr(widget, "_lg_cache", None)
    if cache is not None and cache[0] == key and time.perf_counter() - cache[2] < TTL:
        return cache[1]
    img = glass.capture_region(grect, DOWN, material="focused", liquid=True)
    if img is not None:
        try:
            img = glass.refract(img, grect, QtCore.QRectF(grect), radius)
        except Exception:  # noqa: BLE001
            pass
    widget._lg_cache = (key, img, time.perf_counter())
    return img


def paint_chip(p: QtGui.QPainter, rect: QtCore.QRectF, radius: float, fill: QtGui.QColor,
               active: bool = False):
    """玻璃面板上的"玻璃小块"：磁贴 / 卡片 / 胶囊按钮。

    和整块面板的区别是没有自己的背景采样（面板已经把桌面透进来了），所以只用
    上缘受光 + 内底暗影 + 一圈亮边来表达"这块也是玻璃"。
    """
    path = QtGui.QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    p.save()
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.fillPath(path, fill)
    g = QtGui.QLinearGradient(0, rect.top(), 0, rect.bottom())
    g.setColorAt(0.0, QtGui.QColor(255, 255, 255, 120 if active else 96))
    g.setColorAt(0.45, QtGui.QColor(255, 255, 255, 18))
    g.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
    p.fillPath(path, g)
    p.save()
    p.setClipPath(path)
    d = QtGui.QLinearGradient(0, rect.top() + rect.height() * 0.42, 0, rect.bottom())
    d.setColorAt(0.0, QtGui.QColor(10, 16, 26, 0))
    d.setColorAt(1.0, QtGui.QColor(10, 16, 26, 46 if active else 36))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(d)
    p.drawRoundedRect(rect, radius, radius)
    p.restore()
    # 刃口：左下 / 右上双光源（两个角亮，左上与右下淡到消失），才不像"描了一圈方框"
    rim = dual_edge(rect, 232, 120)
    p.strokePath(path, QtGui.QPen(QtGui.QBrush(rim), 1.3))
    p.restore()


def paint_interactive_chip(p: QtGui.QPainter, widget: QtWidgets.QWidget, rect: QtCore.QRectF,
                           radius: float, hover: float = 0.0, press: float = 0.0):
    """交互控件的薄玻璃：共享岛体快照，控件自身只做轻雾化和跟手光学反馈。"""
    hover = max(0.0, min(1.0, hover))
    press = max(0.0, min(1.0, press))
    win = widget.window()
    backdrop = getattr(win, "backdrop", None)
    hi = getattr(backdrop, "hi", None)
    hr = getattr(backdrop, "hi_rect", QtCore.QRect())
    origin = getattr(win, "_win_origin", win.mapToGlobal(QtCore.QPoint(0, 0)))
    if hi is None or hi.isNull() or hr.isEmpty():
        paint_chip(p, rect, radius, QtGui.QColor(248, 250, 254, round(30 + 18 * hover)), hover > 0.35)
        return
    top = widget.mapTo(win, rect.topLeft().toPoint())
    global_rect = QtCore.QRectF(top.x() + origin.x(), top.y() + origin.y(), rect.width(), rect.height())
    state_key = (int(getattr(backdrop, "version", 0)), round(global_rect.x(), 1), round(global_rect.y(), 1),
                 round(rect.width(), 1), round(rect.height(), 1), round(radius, 1),
                 round(hover * 8), round(press * 8))
    cached = getattr(widget, "_lg_material_cache", None)
    if cached is not None and cached[0] == state_key:
        p.drawImage(rect, cached[1])
        return
    sx = hi.width() / max(1.0, float(hr.width()))
    sy = hi.height() / max(1.0, float(hr.height()))
    source_rect = QtCore.QRectF((global_rect.x() - hr.x()) * sx, (global_rect.y() - hr.y()) * sy,
                                global_rect.width() * sx, global_rect.height() * sy).toAlignedRect()
    source_rect = source_rect.intersected(hi.rect())
    if source_rect.width() < 4 or source_rect.height() < 4:
        paint_chip(p, rect, radius, QtGui.QColor(248, 250, 254, round(30 + 18 * hover)), hover > 0.35)
        return
    dpr = max(1.0, min(2.0, widget.devicePixelRatioF()))
    img = QtGui.QImage(max(2, round(rect.width() * dpr)), max(2, round(rect.height() * dpr)),
                       QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(dpr)
    img.fill(Qt.GlobalColor.transparent)
    qp = QtGui.QPainter(img)
    qp.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    qp.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    path = QtGui.QPainterPath()
    local = QtCore.QRectF(0, 0, rect.width(), rect.height())
    path.addRoundedRect(local, radius, radius)
    qp.setClipPath(path)
    sample = hi.copy(source_rect)
    blur = max(5.0, min(rect.width(), rect.height()) * (0.30 + 0.10 * press))
    small = sample.scaled(max(2, round(sample.width() / blur)), max(2, round(sample.height() / blur)),
                          Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    qp.drawImage(local, small)
    paint_chip(qp, local, radius, QtGui.QColor(248, 250, 254, round(42 + 16 * hover + 8 * press)), hover > 0.35)
    if press > 0.01:
        lens = QtGui.QRadialGradient(local.center(), max(local.width(), local.height()) * 0.58)
        lens.setColorAt(0.0, QtGui.QColor(255, 255, 255, round(34 * press)))
        lens.setColorAt(0.62, QtGui.QColor(255, 255, 255, round(10 * press)))
        lens.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
        qp.fillPath(path, lens)
    qp.end()
    widget._lg_material_cache = (state_key, img)
    p.drawImage(rect, img)


def dual_edge(bb: QtCore.QRectF, hi: int, mid: int = 0) -> QtGui.QLinearGradient:
    """左下 ↔ 右上对角双光渐变。

    沿这条对角线投影：左下角 0、右上角 1 最亮，左上 / 右下正好落在 0.5 处熄灭。
    直接当描边画刷用，刃口就是"两头亮、中间暗"的一道光，而不是均匀一圈白边。
    """
    g = QtGui.QLinearGradient(bb.left(), bb.bottom(), bb.right(), bb.top())
    g.setColorAt(0.00, QtGui.QColor(255, 255, 255, hi))
    g.setColorAt(0.30, QtGui.QColor(255, 255, 255, mid))
    g.setColorAt(0.50, QtGui.QColor(255, 255, 255, 0))
    g.setColorAt(0.70, QtGui.QColor(255, 255, 255, mid))
    g.setColorAt(1.00, QtGui.QColor(255, 255, 255, hi))
    return g


def paint_static_layers(p: QtGui.QPainter, path: QtGui.QPainterPath, bb: QtCore.QRectF):
    """光学层里不随光标变化的前 6 层。桌面窗口每帧重画这几层渐变描边很贵，调用方可以
    把这几层预渲染成一张透明图缓存起来，每帧只贴一次图 + 画跟手高光。"""
    p.save()
    p.setClipPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    h = bb.height()
    # 1) 暗内壁：从轮廓往里衰减，底部最重 —— 只留极轻一层（对齐 Inspira 内阴影，约 5%）
    vg = QtGui.QLinearGradient(0, bb.top(), 0, bb.bottom())
    vg.setColorAt(0.0, QtGui.QColor(10, 16, 26, 0))
    vg.setColorAt(0.55, QtGui.QColor(10, 16, 26, 4))
    vg.setColorAt(1.0, QtGui.QColor(10, 16, 26, 12))
    p.strokePath(path, QtGui.QPen(QtGui.QBrush(vg), max(2.0, min(4.0, h * 0.06))))
    # 2) 细亮刃口：玻璃壁的横截面。左下 / 右上双光源 —— 两个角亮起来，左上与右下熄灭。
    eg = dual_edge(bb, 92, 46)
    p.strokePath(path, QtGui.QPen(QtGui.QBrush(eg), 1.4))
    p.restore()


def paint_spec(p: QtGui.QPainter, path: QtGui.QPainterPath, bb: QtCore.QRectF,
               spec_pt: QtCore.QPointF | None = None):
    """第 7 层：跟着光标走的镜面反射点，是光学层里唯一每帧都在变的层。"""
    p.save()
    p.setClipPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    w, h = bb.width(), bb.height()
    sp = spec_pt or QtCore.QPointF(bb.left() + w * 0.12, bb.top() + h * 0.14)
    rad = QtGui.QRadialGradient(sp, max(10.0, min(w, h) * 0.2))
    rad.setColorAt(0.0, QtGui.QColor(255, 255, 255, 80))
    rad.setColorAt(0.5, QtGui.QColor(255, 255, 255, 26))
    rad.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
    p.fillPath(path, rad)
    p.restore()


def paint_layers(p: QtGui.QPainter, path: QtGui.QPainterPath, bb: QtCore.QRectF,
                 spec_pt: QtCore.QPointF | None = None):
    """玻璃的光学层：静态层 + 跟手高光。弹层 / 菜单直接用这个即可。"""
    paint_static_layers(p, path, bb)
    paint_spec(p, path, bb, spec_pt)


def paint_body_fill(p: QtGui.QPainter, path: QtGui.QPainterPath, bb: QtCore.QRectF):
    """大岛整块玻璃面：直接按玻璃自身的轮廓铺乳白底，不再往里缩一圈内卡片。

    缩进的内卡片会在大岛四周留一圈空玻璃，看起来是两层边；这里让这层乳白一直铺到玻璃
    轮廓，整块面板就是「包裹所有组件的那一张卡」，只剩下玻璃本体的那一道边。
    """
    if path.isEmpty():
        return
    p.save()
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    # 1) 乳白底：透明玻璃不放白，只留极淡一层（要"泛白"改的就是这个数）
    p.fillPath(path, QtGui.QColor(248, 250, 254, 8))
    # 2) 上缘受光渐变
    g = QtGui.QLinearGradient(0, bb.top(), 0, bb.bottom())
    g.setColorAt(0.0, QtGui.QColor(255, 255, 255, 34))
    g.setColorAt(0.5, QtGui.QColor(255, 255, 255, 6))
    g.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
    p.fillPath(path, g)
    # 3) 底部轻内阴影
    p.setClipPath(path)
    d = QtGui.QLinearGradient(0, bb.top() + bb.height() * 0.55, 0, bb.bottom())
    d.setColorAt(0.0, QtGui.QColor(12, 18, 30, 0))
    d.setColorAt(1.0, QtGui.QColor(12, 18, 30, 28))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(d)
    p.drawRect(bb)
    p.restore()


def paint_inner_card(p: QtGui.QPainter, bb: QtCore.QRectF, margin: float, radius: float):
    """大岛内部的圆润衬底卡片：与液态玻璃四周保持 margin 距离，包裹全部内容与组件。
    半透明白底 + 上缘受光 + 细刃口 + 底部轻内阴影，用来进一步提升文字可读性。"""
    r = bb.adjusted(margin, margin, -margin, -margin)
    if r.width() <= 4 or r.height() <= 4:
        return
    card = QtGui.QPainterPath()
    card.addRoundedRect(r, radius, radius)
    p.save()
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    # 1) 半透明乳白底：在任意壁纸上都把内容区提亮
    p.fillPath(card, QtGui.QColor(248, 250, 254, 20))
    # 2) 上缘受光渐变：顶部更亮，向下衰减
    g = QtGui.QLinearGradient(0, r.top(), 0, r.bottom())
    g.setColorAt(0.0, QtGui.QColor(255, 255, 255, 64))
    g.setColorAt(0.5, QtGui.QColor(255, 255, 255, 12))
    g.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
    p.fillPath(card, g)
    # 3) 底部轻内阴影：卡片有浮在玻璃上的层次
    p.save()
    p.setClipPath(card)
    d = QtGui.QLinearGradient(0, r.top() + r.height() * 0.55, 0, r.bottom())
    d.setColorAt(0.0, QtGui.QColor(12, 18, 30, 0))
    d.setColorAt(1.0, QtGui.QColor(12, 18, 30, 28))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(d)
    p.drawRoundedRect(r, radius, radius)
    p.restore()
    # 4) 细白刃口：上亮下淡
    rim = QtGui.QLinearGradient(0, r.top(), 0, r.bottom())
    rim.setColorAt(0.0, QtGui.QColor(255, 255, 255, 220))
    rim.setColorAt(0.5, QtGui.QColor(255, 255, 255, 150))
    rim.setColorAt(1.0, QtGui.QColor(255, 255, 255, 90))
    p.strokePath(card, QtGui.QPen(QtGui.QBrush(rim), 1.2))
    p.restore()


def precapture(widget: QtWidgets.QWidget, radius: float):
    """窗口 show 之前/刚 show 时抓一次屏；之后 paint 直接用这份缓存，不会把自己的内容抓进去。"""
    _backdrop(widget, QtCore.QRectF(widget.rect()), radius)


def paint_panel(p: QtGui.QPainter, widget: QtWidgets.QWidget, rect: QtCore.QRectF,
                radius: float, spec_pt: QtCore.QPointF | None = None, capture: bool = True):
    """画一整块液态玻璃面：背后背景（可选）+ 色调 + 光学层。"""
    path = QtGui.QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    img = _backdrop(widget, rect, radius) if capture else None
    br = _panel_brush(img, rect) if img is not None else None
    p.save()
    p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    if br is not None:
        p.fillPath(path, br)
    p.fillPath(path, theme.tint_brush(rect))
    g = QtGui.QLinearGradient(0, rect.top(), 0, rect.bottom())
    g.setColorAt(0, QtGui.QColor(255, 255, 255, 10))
    g.setColorAt(0.5, QtGui.QColor(255, 255, 255, 0))
    g.setColorAt(1, QtGui.QColor(255, 255, 255, 4))
    p.fillPath(path, g)
    paint_layers(p, path, rect, spec_pt)
    p.strokePath(path, QtGui.QPen(theme.outline(), 1.2))
    p.restore()


# --- QMenu 皮肤 ---
MENU_QSS = (
    "QMenu{{background:transparent;border:none;padding:6px;color:{fg};"
    "font-family:'HarmonyOS Sans','Microsoft YaHei UI';font-size:13px}}"
    "QMenu::item{{padding:6px 22px 6px 14px;border-radius:9px}}"
    "QMenu::item:selected{{background:{sel}}}"
    "QMenu::item:disabled{{color:gray}}"
    "QMenu::separator{{height:6px;background:transparent}}"
    "QMenu::indicator{{width:0}}"
)


class MenuGlass(QtCore.QObject):
    """装在 QApplication 上的事件过滤器：液态玻璃主题下，所有 QMenu（含子菜单）都画成玻璃。"""

    def __init__(self, app):
        super().__init__(app)
        self._app = app
        app.installEventFilter(self)
        theme.changed.connect(self._on_theme)

    def _on_theme(self):
        """切出液态玻璃时，正在显示 / 之后显示的菜单都要恢复原皮肤。"""
        if theme.liquid:
            return
        for m in self._app.topLevelWidgets():
            if isinstance(m, QtWidgets.QMenu):
                self.undress(m)

    @staticmethod
    def dress(m: QtWidgets.QMenu):
        """把菜单换成"背景透明 + 圆角项"的皮肤，玻璃由 paint 事件画在底下。"""
        if m.property("lg_dressed"):
            return
        m.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        m.setProperty("lg_prev", m.styleSheet())
        _bg, fg, sel = theme.menu_qss()
        m.setStyleSheet(MENU_QSS.format(fg=fg, sel=sel))
        m.setProperty("lg_dressed", True)

    @staticmethod
    def undress(m: QtWidgets.QMenu):
        """换回别的主题：恢复原来的皮肤，否则会出现"透明菜单"。"""
        if not m.property("lg_dressed"):
            return
        m.setStyleSheet(m.property("lg_prev") or "")
        m.setProperty("lg_dressed", False)

    def eventFilter(self, obj, ev):  # noqa: N802
        if not isinstance(obj, QtWidgets.QMenu):
            return False
        t = ev.type()
        if not theme.liquid:
            if t == QtCore.QEvent.Type.Show:
                self.undress(obj)
            return False
        if t == QtCore.QEvent.Type.Show:
            self.dress(obj)
            self._capture(obj)
        elif t == QtCore.QEvent.Type.Paint:
            self._paint(obj)
        return False

    @staticmethod
    def _capture(m: QtWidgets.QMenu):
        """菜单还没画自己之前抓一次屏（此时窗口是透明的，抓到的是桌面）。"""
        r = QtCore.QRectF(m.rect())
        if r.width() < 4 or r.height() < 4:
            return
        _backdrop(m, r, 14.0)

    @staticmethod
    def _paint(m: QtWidgets.QMenu):
        p = QtGui.QPainter(m)
        # capture=True：命中 Show 时抓好的缓存；万一缓存过期才会重抓
        paint_panel(p, m, QtCore.QRectF(m.rect()), 14.0)
        p.end()
