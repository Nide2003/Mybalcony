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
    img = glass.capture_region(grect, DOWN)
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
    # 刃口只在上半圈亮起、下半圈淡到消失：这样才不像"描了一圈方框"
    rim = QtGui.QLinearGradient(0, rect.top(), 0, rect.bottom())
    rim.setColorAt(0.0, QtGui.QColor(255, 255, 255, 232))
    rim.setColorAt(0.34, QtGui.QColor(255, 255, 255, 150))
    rim.setColorAt(0.70, QtGui.QColor(255, 255, 255, 34))
    rim.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
    p.strokePath(path, QtGui.QPen(QtGui.QBrush(rim), 1.3))
    p.restore()


def paint_layers(p: QtGui.QPainter, path: QtGui.QPainterPath, bb: QtCore.QRectF,
                 spec_pt: QtCore.QPointF | None = None):
    """玻璃的"光学层"：暗内壁 + 亮刃口 / 暗发丝 + 内折射亮带 + 镜面反射。全部裁在形状内部。"""
    p.save()
    p.setClipPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    w, h = bb.width(), bb.height()
    # 1) 暗内壁：从轮廓往里衰减，底部最重 —— 薄薄一层，太重就成了灰边框
    vg = QtGui.QLinearGradient(0, bb.top(), 0, bb.bottom())
    vg.setColorAt(0.0, QtGui.QColor(10, 16, 26, 0))
    vg.setColorAt(0.55, QtGui.QColor(10, 16, 26, 8))
    vg.setColorAt(1.0, QtGui.QColor(10, 16, 26, 26))
    p.strokePath(path, QtGui.QPen(QtGui.QBrush(vg), max(3.0, min(7.0, h * 0.11))))
    # 2) 亮刃口 + 暗发丝：白/暗/白三层，就是玻璃壁的横截面
    eg = QtGui.QLinearGradient(0, bb.top(), 0, bb.bottom())
    eg.setColorAt(0.0, QtGui.QColor(255, 255, 255, 255))
    eg.setColorAt(0.45, QtGui.QColor(255, 255, 255, 232))
    eg.setColorAt(1.0, QtGui.QColor(255, 255, 255, 196))
    p.strokePath(path, QtGui.QPen(QtGui.QBrush(eg), 3.4))
    dg2 = QtGui.QLinearGradient(0, bb.top(), 0, bb.bottom())
    dg2.setColorAt(0.0, QtGui.QColor(10, 16, 26, 44))
    dg2.setColorAt(1.0, QtGui.QColor(10, 16, 26, 92))
    p.strokePath(path, QtGui.QPen(QtGui.QBrush(dg2), 1.4))
    # 3) 内折射亮带：刃口往里一小段的漫射光，眼睛会读成"弧面"
    p.strokePath(path, QtGui.QPen(QtGui.QColor(255, 255, 255, 40), 6.0))
    # 4) 镜面反射：一道斜穿面板的窄光带（窗口 / 灯管在玻璃上的倒影）
    ng = QtGui.QLinearGradient(bb.left() - h * 0.1, bb.top(), bb.left() + h * 1.5, bb.top() + h * 0.5)
    ng.setColorAt(0.00, QtGui.QColor(255, 255, 255, 0))
    ng.setColorAt(0.30, QtGui.QColor(255, 255, 255, 0))
    ng.setColorAt(0.36, QtGui.QColor(255, 255, 255, 58))
    ng.setColorAt(0.44, QtGui.QColor(255, 255, 255, 118))
    ng.setColorAt(0.52, QtGui.QColor(255, 255, 255, 58))
    ng.setColorAt(0.58, QtGui.QColor(255, 255, 255, 0))
    ng.setColorAt(1.00, QtGui.QColor(255, 255, 255, 0))
    p.fillPath(path, ng)
    # 5) 大面积漫射光：左上更亮，给玻璃一个受光面
    lg = QtGui.QLinearGradient(bb.left() + w * 0.04, bb.top(),
                               bb.left() + w * 0.6, bb.top() + h * 0.62)
    lg.setColorAt(0.0, QtGui.QColor(255, 255, 255, 96))
    lg.setColorAt(0.3, QtGui.QColor(255, 255, 255, 22))
    lg.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
    p.fillPath(path, lg)
    # 6) 边缘暗角：右下压一点点，玻璃就有体积
    dgk = QtGui.QLinearGradient(bb.left() + w * 0.5, bb.top(), bb.right(), bb.bottom())
    dgk.setColorAt(0.0, QtGui.QColor(8, 14, 24, 0))
    dgk.setColorAt(1.0, QtGui.QColor(8, 14, 24, 46))
    p.fillPath(path, dgk)
    # 7) 固定反射点：左上角一枚小而硬的镜面光
    sp = spec_pt or QtCore.QPointF(bb.left() + w * 0.12, bb.top() + h * 0.14)
    rad = QtGui.QRadialGradient(sp, max(10.0, min(w, h) * 0.22))
    rad.setColorAt(0.0, QtGui.QColor(255, 255, 255, 210))
    rad.setColorAt(0.5, QtGui.QColor(255, 255, 255, 70))
    rad.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
    p.fillPath(path, rad)
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
    g.setColorAt(0, QtGui.QColor(255, 255, 255, 26))
    g.setColorAt(0.5, QtGui.QColor(255, 255, 255, 0))
    g.setColorAt(1, QtGui.QColor(255, 255, 255, 10))
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
