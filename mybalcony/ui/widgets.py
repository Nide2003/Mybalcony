# -*- coding: utf-8 -*-
"""通用控件：全部自绘、跟随主题；背景透明，直接落在毛玻璃上。"""
from __future__ import annotations

import math
import time

from PySide6 import QtCore, QtGui, QtWidgets

from .anim import Spring, clamp
from .liquid import paint_chip, paint_interactive_chip
from .theme import G, W, apply_qss_text_shadow, icon_font, theme, ui_font

Qt = QtCore.Qt
AA = QtGui.QPainter.RenderHint.Antialiasing


def painter(w: QtWidgets.QWidget) -> QtGui.QPainter:
    p = QtGui.QPainter(w)
    p.setRenderHint(AA)
    p.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    return p


def backdrop_luminance(w: QtWidgets.QWidget) -> float | None:
    """控件背后壁纸的平均亮度（0~1）；拿不到背景快照时返回 None。

    液态玻璃的 tint 近乎全透明，白色字形压在玻璃上会跟着壁纸一起"消失"。
    这里按控件在窗口里的位置，把 backdrop 快照对应区域缩成 1×1 求加权亮度，
    成本很低（一次缩略），可以在 paintEvent 里直接调。
    """
    win = w.window()
    bd = getattr(win, "backdrop", None)
    hi = getattr(bd, "hi", None)
    hr = getattr(bd, "hi_rect", None)
    if hi is None or hi.isNull() or hr is None or hr.width() <= 0 or hr.height() <= 0:
        return None
    if w.width() <= 0 or w.height() <= 0:
        return None
    top = w.mapTo(win, QtCore.QPoint(0, 0))
    origin = getattr(win, "_win_origin", win.mapToGlobal(QtCore.QPoint(0, 0)))
    sx = hi.width() / float(hr.width())
    sy = hi.height() / float(hr.height())
    src = QtCore.QRectF((top.x() + origin.x() - hr.x()) * sx,
                        (top.y() + origin.y() - hr.y()) * sy,
                        w.width() * sx, w.height() * sy).toAlignedRect()
    src = src.intersected(hi.rect())
    if src.width() < 2 or src.height() < 2:
        return None
    c = hi.copy(src).scaled(1, 1, Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation).pixelColor(0, 0)
    return 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()


def glass_ink(w: QtWidgets.QWidget, a: float = 1.0) -> QtGui.QColor:
    """压在玻璃上的前景色（图标 / 数字）：亮底切深墨、暗底回白。

    非液态主题直接返回正文色，行为与改动前完全一致；液态下才是"跟随壁纸反色"。
    阈值与导航胶囊一致（0.58），拿不到背景快照时按亮底处理。
    """
    if not theme.liquid:
        return theme.text(a)
    lum = backdrop_luminance(w)
    return theme.glass_ink(lum is None or lum > 0.58, a)


def card_geometry(p, r, radius):
    """卡片框 → 设备像素对齐后的（本地框, 圆角, 设备缩放）。

    直接描边的四边落点各不相同，抗锯齿给出的强度也就不同；这里把卡片框映射到设备像素、
    按半像素对齐再映射回来，四边就一样粗、一样实。填充和描边共用这个框，否则转角处
    黑线会比卡片外沿小半圈，看着就是「折角、不圆滑」。按下旋转时外接框对不上卡片，退回原框。
    """
    m = p.combinedTransform()
    scale = math.sqrt(abs(m.determinant())) or 1.0
    if abs(m.m12()) > 1e-6 or abs(m.m21()) > 1e-6:
        return r, radius, scale
    inv, ok = m.inverted()
    if not ok:
        return r, radius, scale
    box = m.mapRect(r)
    snap = QtCore.QRectF(QtCore.QPointF(round(box.left()) + 0.5, round(box.top()) + 0.5),
                         QtCore.QPointF(round(box.right()) - 0.5, round(box.bottom()) - 0.5))
    local = inv.mapRect(snap)
    if local.width() < 2 or local.height() < 2:
        return r, radius, scale
    rad = max(0.0, radius * (local.width() / max(1.0, r.width())))
    return local, rad, scale


def card_path(p, r, radius):
    local, rad, scale = card_geometry(p, r, radius)
    path = QtGui.QPainterPath()
    path.addRoundedRect(local, rad, rad)
    return path, scale


def squircle_radius(rect) -> float:
    """苹果黄金比例圆角：半径 = 短边 × 18%（squircle 的等效肉眼看感）。"""
    return max(6.0, min(rect.width(), rect.height()) * 0.18)


class Themed:
    """混入：主题切换时自动重绘。"""
    def _hook_theme(self):
        theme.changed.connect(self._on_theme)
        # 透明底的子控件：告诉 Qt"我底下还有东西"，重绘时会连着底下一起画。
        # 不设的话局部重绘前 Qt 会把这块清成透明，圆角四角就闪一下空白。
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        except (AttributeError, RuntimeError):
            pass

    def _on_theme(self):
        try:
            self.update()
        except RuntimeError:
            pass


class Hoverable(QtWidgets.QWidget, Themed):
    clicked = QtCore.Signal()
    right_clicked = QtCore.Signal()

    CARD_PAD = 3.0      # uiverse 卡片与控件边的最小留白：给 hover 放大和投影留位置

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hover = Spring(0, 420, 1.0, 0.01)
        self._press = Spring(0, 600, 0.7, 0.01)
        self._timer = QtCore.QTimer(self, interval=16, timeout=self._tick)
        self._last = time.perf_counter()
        self._hook_theme()

    def _kick(self):
        if not self._timer.isActive():
            self._last = time.perf_counter()
            self._timer.start()

    def _repaint_area(self):
        """让整个窗口重画一遍。

        这些控件是透明底、只画圆角形状的；Qt 局部重绘时会先把这块清成透明，
        又不保证同帧把底下的岛身玻璃补画回来，圆角四角就会闪一下空白。
        局部重绘这条路试过（限定区域 update + 透明链标记）都压不住，
        干脆整窗重绘：岛身玻璃有折射/模糊缓存，一帧只有几毫秒，悬停动画也只有几百毫秒。
        """
        self.update()
        win = self.window()
        if win is not None and win is not self:
            win.update()

    def _tick(self):
        now = time.perf_counter()
        dt = min(0.05, now - self._last)
        self._last = now
        self._hover.step(dt)
        self._press.step(dt)
        self._repaint_area()
        if self._hover.rest and self._press.rest:
            self._timer.stop()

    def enterEvent(self, e):
        self._hover.to(1)
        self._kick()

    def leaveEvent(self, e):
        self._hover.to(0)
        self._press.to(0)
        self._kick()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press.to(1)
            self._kick()
        e.accept()

    def mouseReleaseEvent(self, e):
        self._press.to(0)
        self._kick()
        if self.rect().contains(e.position().toPoint()):
            if e.button() == Qt.MouseButton.LeftButton:
                self.clicked.emit()
            elif e.button() == Qt.MouseButton.RightButton:
                self.right_clicked.emit()
        e.accept()

    def press_scale(self) -> float:
        return 1.0 - 0.06 * self._press.x

    def card_transform(self, p, r):
        """uiverse card 变换：hover 放大、按下缩小并旋转 1.7°。

        放大倍数会被控件边界夹住：按下时卡片还会转 1.7°，宽扁的卡片一转，角就会顶出控件，
        所以按"旋转后的外接框"算上限——宁可少放大一点，也不能让描边被裁掉。
        """
        hx, px = self._hover.x, self._press.x
        if theme.liquid:
            sc = (1.0 + 0.025 * hx) * (1.0 - 0.035 * px)
            p.translate(r.center())
            p.scale(sc, 1.0 - 0.055 * px + 0.018 * hx)
            p.translate(-r.center())
            return
        ang = 1.7 * px
        sc = (1.0 + 0.05 * hx) * (1.0 - 0.05 * px)
        w, h = r.width(), r.height()
        if w > 1 and h > 1:
            rad = math.radians(ang)
            c, s = abs(math.cos(rad)), abs(math.sin(rad))
            sc = min(sc, self.width() / max(1.0, w * c + h * s),
                     self.height() / max(1.0, w * s + h * c))
        p.translate(r.center())
        p.rotate(ang)
        p.scale(sc, sc)
        p.translate(-r.center())

    def card_rect(self, bottom_extra: float = 1.5) -> QtCore.QRectF:
        """卡片绘制区：四周留出 CARD_PAD，底部再多留一点给投影，避免任何东西溢出控件边界。"""
        pad = self.CARD_PAD
        return QtCore.QRectF(self.rect()).adjusted(pad, pad, -pad, -(pad + bottom_extra))

    def paint_card_bg(self, p, r, radius, nav=False):
        """液态主题使用共享背景采样的薄玻璃；其他主题保留原有卡片皮肤。

        nav=True 走导航条同款玻璃配方（强雾化 + 淡 tint），仅供控制中心这类
        “按钮背景要和导航胶囊一致”的控件使用。
        """
        if theme.liquid:
            paint_interactive_chip(p, self, r, radius, self._hover.x, self._press.x, nav=nav)
            return
        card, scale = card_path(p, r, radius)
        hx = clamp(self._hover.x, 0.0, 1.0)
        if hx < 0.6:                              # 悬停时阴影跟着淡出，免得下边比其余三边厚
            k = 1.0 - hx / 0.6
            p.strokePath(card.translated(0.8, 1.6), QtGui.QPen(QtGui.QColor(0, 0, 0, int(20 * k)), 4.2))
            p.strokePath(card.translated(0.4, 0.9), QtGui.QPen(QtGui.QColor(0, 0, 0, int(26 * k)), 2.6))
        p.fillPath(card, QtGui.QColor(217, 217, 217, 148))
        if hx > 0.02:
            p.strokePath(card, QtGui.QPen(QtGui.QColor(255, 255, 255, int(42 * hx)), 6.2 / scale))
            p.strokePath(card, QtGui.QPen(QtGui.QColor(255, 255, 255, int(86 * hx)), 3.0 / scale))
            p.strokePath(card, QtGui.QPen(QtGui.QColor(255, 255, 255, int(205 + 50 * hx)), 1.15 / scale))
        else:
            p.strokePath(card, QtGui.QPen(QtGui.QColor(255, 255, 255, 235), 1.0 / scale))

    @staticmethod
    def paint_card_edge(p, r, radius, color, width: float = 1.0):
        """卡片边框：1 个设备像素，路径与填充共用同一条设备像素对齐的圆角框。"""
        path, scale = card_path(p, r, radius)
        p.strokePath(path, QtGui.QPen(color, width / scale))


class IconButton(Hoverable):
    """圆形图标按钮：悬停时出现半透明白底。"""
    def __init__(self, glyph: str, size: int = 32, icon_px: int = 15, tip: str = "", parent=None,
                 filled: bool = False):
        super().__init__(parent)
        self.glyph = glyph
        self.icon_px = icon_px
        self.filled = filled
        self.active = False
        self.color: QtGui.QColor | None = None
        # 亮底反色：白图标压在纯白背景上会消失。导航栏按背景亮度替自己的按钮翻色，
        # 其余调用点保持 False（白底场景由使用方决定，不擅自改全局观感）；
        # 传 None = 自动：每次绘制按身后壁纸亮度现算，主页这类会随背景变化的地方用它。
        self.on_light = False
        self.setFixedSize(size, size)
        if tip:
            self.setToolTip(tip)

    def set_glyph(self, g: str):
        if g != self.glyph:
            self.glyph = g
            self.update()

    def set_active(self, on: bool):
        if on != self.active:
            self.active = on
            self.update()

    def paintEvent(self, e):
        p = painter(self)
        if theme.liquid:
            r = self.card_rect()
            self.card_transform(p, r)
            ol = self.on_light
            if ol is None:                      # 自动：按身后壁纸亮度定前景，和电量图标同一套
                lum = backdrop_luminance(self)
                ol = lum is None or lum > 0.58
            hx = clamp(self._hover.x, 0.0, 1.0)
            if ol:
                # 亮底：玻璃薄片在白背景上等于没有，悬停改用淡墨圆给出反馈
                if hx > 0.01:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QtGui.QColor(0, 0, 0, int(46 * hx)))
                    rad = min(14.0, r.height() / 2)
                    p.drawRoundedRect(r, rad, rad)
            else:
                self.paint_card_bg(p, r, min(14.0, r.height() / 2))
            p.setFont(icon_font(self.icon_px))
            p.setPen(theme.glass_ink(ol, 0.94))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.glyph)
            return
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        s = self.press_scale()
        p.translate(r.center())
        p.scale(s, s)
        p.translate(-r.center())
        if self.active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.color or theme.fill())
            p.drawEllipse(r)
        elif self.filled or self._hover.x > 0.01:
            bg = QtGui.QColor(theme.card() if self.filled else theme.hover())
            if not self.filled:
                bg.setAlphaF(bg.alphaF() * self._hover.x)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawEllipse(r)
        p.setFont(icon_font(self.icon_px))
        fg = QtGui.QColor(20, 20, 24) if self.active else (self.color or theme.text(0.9))
        if self.active and self.color is not None:
            fg = QtGui.QColor("white")
        p.setPen(fg)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.glyph)


class PillButton(Hoverable):
    """胶囊按钮：图标 + 文字。"""
    def __init__(self, text: str, glyph: str = "", parent=None, height: int = 30, primary: bool = False):
        super().__init__(parent)
        self.text = text
        self.glyph = glyph
        self.primary = primary
        self.setFixedHeight(height)
        self._fit()

    def _fit(self):
        fm = QtGui.QFontMetrics(ui_font(12.5, W.Medium))
        w = fm.horizontalAdvance(self.text) + 26 + (20 if self.glyph else 0)
        self.setMinimumWidth(min(w, self.maximumWidth()))

    def set_text(self, t: str):
        self.text = t
        self._fit()
        self.update()

    def paintEvent(self, e):
        p = painter(self)
        if theme.liquid:
            r = self.card_rect()
            self.card_transform(p, r)
            self.paint_card_bg(p, r, min(14.0, r.height() / 2))
            p.setPen(theme.text(0.94))
            x = r.x() + 12
            if self.glyph:
                p.setFont(icon_font(13))
                p.drawText(QtCore.QRectF(x, r.y(), 16, r.height()), Qt.AlignmentFlag.AlignCenter, self.glyph)
                x += 19
            p.setFont(ui_font(12.5, W.DemiBold))
            tw = r.right() - x - 10
            theme.outlined_text(p, QtCore.QRectF(x, r.y(), tw, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       QtGui.QFontMetrics(p.font()).elidedText(self.text, Qt.TextElideMode.ElideRight, int(tw)))
            return
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        s = self.press_scale()
        p.translate(r.center())
        p.scale(s, s)
        p.translate(-r.center())
        bg = theme.fill() if self.primary else theme.card(1.0 + 0.6 * self._hover.x)
        if theme.liquid:
            paint_chip(p, r, r.height() / 2, bg, active=self.primary)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        fg = QtGui.QColor(20, 20, 24) if self.primary else theme.text(0.92)
        p.setPen(fg)
        x = r.x() + 13
        if self.glyph:
            p.setFont(icon_font(13))
            p.drawText(QtCore.QRectF(x, r.y(), 16, r.height()), Qt.AlignmentFlag.AlignCenter, self.glyph)
            x += 20
        p.setFont(ui_font(12.5, W.Medium))
        tw = r.right() - x - 11
        theme.outlined_text(p, QtCore.QRectF(x, r.y(), tw, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   QtGui.QFontMetrics(p.font()).elidedText(self.text, Qt.TextElideMode.ElideRight, int(tw)))


class Label(QtWidgets.QWidget, Themed):
    """主题文字：level 1/2/3 = 主/次/弱。支持省略号与可选滚动(marquee)。"""
    clicked = QtCore.Signal()

    def __init__(self, text: str = "", px: float = 13, weight=W.Normal, level: int = 1, parent=None,
                 align=Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, num: bool = False,
                 color: QtGui.QColor | None = None, wrap: bool = False):
        super().__init__(parent)
        self._text = text
        self.font_ = ui_font(px, weight, num)
        self.level = level
        self.align = align
        self.color = color
        self.wrap = wrap
        fm = QtGui.QFontMetrics(self.font_)
        if not wrap:
            self.setFixedHeight(fm.height() + 2)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred if not wrap else QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Fixed if not wrap else QtWidgets.QSizePolicy.Policy.Expanding)
        self._hook_theme()

    def sizeHint(self):
        fm = QtGui.QFontMetrics(self.font_)
        return QtCore.QSize(fm.horizontalAdvance(self._text) + 4, fm.height() + 2)

    def minimumSizeHint(self):
        return QtCore.QSize(0, QtGui.QFontMetrics(self.font_).height() + 2)

    def setText(self, t: str):
        t = t or ""
        if t != self._text:
            self._text = t
            self.updateGeometry()
            self.update()

    def text(self) -> str:
        return self._text

    def set_color(self, c: QtGui.QColor | None):
        self.color = c
        self.update()

    def mouseReleaseEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, e):
        p = painter(self)
        p.setFont(self.font_)
        c = self.color or (theme.text() if self.level == 1 else theme.text2() if self.level == 2 else theme.text3())
        p.setPen(c)
        r = QtCore.QRectF(self.rect())
        if self.wrap:
            theme.outlined_text(p, r, int(self.align) | int(Qt.TextFlag.TextWordWrap), self._text)
        else:
            fm = QtGui.QFontMetrics(self.font_)
            theme.outlined_text(p, r, self.align, fm.elidedText(self._text, Qt.TextElideMode.ElideRight, int(r.width())))


class Slider(QtWidgets.QWidget, Themed):
    """iOS 控制中心风格的粗滑块：整条可拖，左侧图标，填充为白色。"""
    moved = QtCore.Signal(float)        # 拖动中（0..1）
    released = QtCore.Signal(float)
    icon_clicked = QtCore.Signal()

    def __init__(self, glyph: str, parent=None, height: int = 34, nav: bool = False):
        super().__init__(parent)
        self.glyph = glyph
        self.nav = nav
        self.value = 0.0
        self.shown = Spring(0, 520, 1.0, 0.002)
        self.dragging = False
        self.label = ""
        self.setFixedHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._t = QtCore.QTimer(self, interval=16, timeout=self._tick)
        self._last = time.perf_counter()
        self._hook_theme()

    def set_value(self, v: float, animate: bool = True):
        if self.dragging:
            return
        self.value = clamp(v, 0, 1)
        self.shown.to(self.value)
        if not animate:
            self.shown.snap(self.value)
        self._kick()

    def _kick(self):
        if not self._t.isActive():
            self._last = time.perf_counter()
            self._t.start()

    def _tick(self):
        now = time.perf_counter()
        self.shown.step(min(0.05, now - self._last))
        self._last = now
        self.update()
        if self.shown.rest:
            self._t.stop()

    def _val_at(self, x: float) -> float:
        return clamp(x / max(1, self.width()), 0, 1)

    def mousePressEvent(self, e):
        if e.position().x() < self.height() * 0.9:
            self._icon_press = True
            return
        self._icon_press = False
        self.dragging = True
        self.value = self._val_at(e.position().x())
        self.shown.to(self.value)
        self._kick()
        self.moved.emit(self.value)

    def mouseMoveEvent(self, e):
        if self.dragging:
            self.value = self._val_at(e.position().x())
            self.shown.to(self.value)
            self._kick()
            self.moved.emit(self.value)

    def mouseReleaseEvent(self, e):
        if getattr(self, "_icon_press", False):
            self._icon_press = False
            self.icon_clicked.emit()
            return
        if self.dragging:
            self.dragging = False
            self.released.emit(self.value)

    def wheelEvent(self, e):
        """滑块不响应滚轮（只允许点击与拖动），滚轮事件交给外层。"""
        e.ignore()

    def paintEvent(self, e):
        p = painter(self)
        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        rad = r.height() / 2
        path = QtGui.QPainterPath()
        path.addRoundedRect(r, rad, rad)
        if theme.liquid:
            paint_interactive_chip(p, self, r, rad, press=1.0 if self.dragging else 0.0, nav=self.nav)
        else:
            p.fillPath(path, theme.track())
        v = clamp(self.shown.x, 0, 1)
        if v > 0:
            fw = max(r.height(), r.width() * v)
            fr = QtCore.QRectF(r.x(), r.y(), fw, r.height())
            fp = QtGui.QPainterPath()
            fp.addRoundedRect(fr, rad, rad)
            p.fillPath(fp, theme.fill())
        # 图标：在填充上用深色，在轨道上用主题色
        p.setFont(icon_font(14))
        p.setPen(QtGui.QColor(30, 30, 34) if v * r.width() > r.height() * 0.8 else theme.text(0.85))
        p.drawText(QtCore.QRectF(r.x(), r.y(), r.height() * 1.05, r.height()), Qt.AlignmentFlag.AlignCenter, self.glyph)
        txt = self.label or f"{round(v * 100)}"
        p.setFont(ui_font(11.5, W.Medium, num=True))
        p.setPen(QtGui.QColor(30, 30, 34, 170) if v > 0.9 else theme.text2())
        theme.outlined_text(p, r.adjusted(0, 0, -12, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                            txt, outline=not (v > 0.9))   # 填充段上的深色字不描边


class Switch(Hoverable):
    """iOS 开关：44×26 胶囊 + 白色滑块。"""
    toggled = QtCore.Signal(bool)

    def __init__(self, on: bool = False, parent=None):
        super().__init__(parent)
        self.on = bool(on)
        self.s = Spring(1.0 if on else 0.0, 460, 0.85, 0.004)
        self.setFixedSize(44, 26)

    def _tick(self):
        self.s.step(0.016)
        super()._tick()
        if not self.s.rest and not self._timer.isActive():
            self._timer.start()

    def set_on(self, on: bool):
        self.on = bool(on)
        self.s.to(1.0 if on else 0.0)
        self._kick()

    def flip(self):
        self.set_on(not self.on)
        self.toggled.emit(self.on)

    def mouseReleaseEvent(self, e):
        if (e.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(e.position().toPoint())):
            self._press.to(0)
            self.flip()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = painter(self)
        r = QtCore.QRectF(self.rect())
        t = clamp(self.s.x, 0.0, 1.0)
        off, on = theme.track(), theme.on_color()
        col = QtGui.QColor(
            round(off.red() + (on.red() - off.red()) * t),
            round(off.green() + (on.green() - off.green()) * t),
            round(off.blue() + (on.blue() - off.blue()) * t),
            round(off.alpha() + (255 - off.alpha()) * t))
        p.setPen(Qt.PenStyle.NoPen)
        if theme.liquid:
            paint_interactive_chip(p, self, r, 13, self._hover.x, self._press.x)
        p.setBrush(col)
        p.drawRoundedRect(r, 13, 13)
        knob = 22.0
        x = r.x() + 2 + (r.width() - knob - 4) * t
        p.setBrush(theme.on_fg())
        knob_rect = QtCore.QRectF(x, r.y() + 2, knob, knob)
        p.drawEllipse(knob_rect)
        if theme.liquid:
            shine = QtGui.QLinearGradient(knob_rect.topLeft(), knob_rect.bottomRight())
            shine.setColorAt(0.0, QtGui.QColor(255, 255, 255, 150))
            shine.setColorAt(0.48, QtGui.QColor(255, 255, 255, 12))
            shine.setColorAt(1.0, QtGui.QColor(30, 40, 60, 22))
            p.setBrush(shine)
            p.drawEllipse(knob_rect)


class SwitchRow(QtWidgets.QWidget, Themed):
    """菜单里的一行：左侧名称 + 右侧开关，点整行也能切换（菜单不用「✓」）。
    guard 返回 False 时拒绝切换（例如页签只剩一个，不允许再关）。"""
    toggled = QtCore.Signal(bool)

    def __init__(self, text: str, on: bool = False, guard=None, parent=None, width: int = 206):
        super().__init__(parent)
        self.text = text
        self.on = bool(on)
        self.guard = guard
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(31)
        self.setMinimumWidth(width)
        self._hover = Spring(0, 420, 1.0, 0.01)
        self._timer = QtCore.QTimer(self, interval=16, timeout=self._tick)
        self._last = time.perf_counter()
        self.sw = Switch(self.on, self)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 8, 0)
        lay.addStretch(1)
        lay.addWidget(self.sw, 0, Qt.AlignmentFlag.AlignVCenter)
        self.sw.toggled.connect(self._on_switch)
        self._hook_theme()

    def _on_switch(self, on: bool):
        if self.guard is not None and not self.guard(on):
            self.sw.set_on(not on)             # 不允许切换：开关自己回弹
            return
        self.on = bool(on)                     # 开关自己去点的情况：同步状态再往外发
        self.toggled.emit(on)

    def set_on(self, on: bool):
        self.on = bool(on)
        self.sw.set_on(on)

    def _flip(self):
        want = not self.on
        if self.guard is not None and not self.guard(want):
            return
        self.on = want
        self.sw.set_on(want)
        self.toggled.emit(want)

    def _tick(self):
        now = time.perf_counter()
        dt = min(0.05, now - self._last)
        self._last = now
        self._hover.step(dt)
        self.update()
        if self._hover.rest:
            self._timer.stop()

    def enterEvent(self, e):
        self._hover.to(1)
        self._timer.start()

    def leaveEvent(self, e):
        self._hover.to(0)
        self._timer.start()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self._flip()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        p = painter(self)
        r = QtCore.QRectF(self.rect()).adjusted(2, 1, -2, -1)
        if self._hover.x > 0.01:
            c = theme.hover()
            c.setAlphaF(c.alphaF() * self._hover.x)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(r, 9, 9)
        p.setFont(ui_font(12.5, W.Medium))
        p.setPen(theme.text(0.95 if self.on else 0.8))
        fm = QtGui.QFontMetrics(p.font())
        tw = self.sw.x() - r.x() - 22
        theme.outlined_text(p, QtCore.QRectF(r.x() + 10, r.y(), max(10, tw), r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   fm.elidedText(self.text, Qt.TextElideMode.ElideRight, int(max(10, tw))))


class Tile(Hoverable):
    """控制中心磁贴：圆形图标 + 标题 + 副标题；on 时图标圆为蓝色。"""
    def __init__(self, glyph: str, title: str, parent=None, height: int = 52):
        super().__init__(parent)
        self.glyph = glyph
        self.title = title
        self.sub = ""
        self.on = False
        self.enabled_ = True
        self.on_spring = Spring(0, 380, 0.85, 0.005)
        self.setFixedHeight(height)
        self.setMinimumWidth(120)

    def set_state(self, on: bool, sub: str = "", enabled: bool = True):
        changed = on != self.on or sub != self.sub or enabled != self.enabled_
        self.on, self.sub, self.enabled_ = on, sub, enabled
        self.on_spring.to(1.0 if on else 0.0)
        if changed:
            self._kick()

    def _tick(self):
        self.on_spring.step(0.016)
        super()._tick()
        if not self.on_spring.rest and not self._timer.isActive():
            self._timer.start()

    def paintEvent(self, e):
        p = painter(self)
        if theme.liquid:
            r = self.card_rect()
            self.card_transform(p, r)
            self.paint_card_bg(p, r, 16)
        else:
            r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
            s = self.press_scale()
            p.translate(r.center())
            p.scale(s, s)
            p.translate(-r.center())
            base = theme.card(1.0 + 0.5 * self._hover.x)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(base)
            p.drawRoundedRect(r, 16, 16)
        d = r.height() - 16
        cr = QtCore.QRectF(r.x() + 8, r.y() + 8, d, d)
        t = clamp(self.on_spring.x, 0.0, 1.0)
        off = theme.track()
        on = theme.on_color()
        col = QtGui.QColor(
            round(off.red() + (on.red() - off.red()) * t),
            round(off.green() + (on.green() - off.green()) * t),
            round(off.blue() + (on.blue() - off.blue()) * t),
            round(off.alpha() + (255 - off.alpha()) * t))
        p.setBrush(col)
        p.drawEllipse(cr)
        p.setFont(icon_font(15))
        p.setPen(theme.on_fg() if t > 0.5 else theme.text(0.85))
        p.drawText(cr, Qt.AlignmentFlag.AlignCenter, self.glyph)
        tx = cr.right() + 9
        tw = r.right() - tx - 6
        a = 1.0 if self.enabled_ else 0.45
        p.setFont(ui_font(12.5, W.DemiBold))
        p.setPen(theme.text(a))
        fm = QtGui.QFontMetrics(p.font())
        if self.sub:
            theme.outlined_text(p, QtCore.QRectF(tx, r.y() + 7, tw, r.height() / 2 - 5),
                       Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft,
                       fm.elidedText(self.title, Qt.TextElideMode.ElideRight, int(tw)))
            p.setFont(ui_font(11))
            fm2 = QtGui.QFontMetrics(p.font())
            p.setPen(theme.text2(a))
            theme.outlined_text(p, QtCore.QRectF(tx, r.center().y() + 1, tw, r.height() / 2 - 6),
                       Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                       fm2.elidedText(self.sub, Qt.TextElideMode.ElideRight, int(tw)))
        else:
            theme.outlined_text(p, QtCore.QRectF(tx, r.y(), tw, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       fm.elidedText(self.title, Qt.TextElideMode.ElideRight, int(tw)))


def _paint_expand_glyph(p: QtGui.QPainter, cx: float, cy: float, color: QtGui.QColor,
                        size: float = 9.0):
    """画「⌃⌄」双箭头（iOS 控制中心里表示"这一块能展开二级菜单"的那个小图标）。

    直接画两段折线而不是用图标字体：字形细、上下间距也不好调；
    折线可以自己定粗细（1.7px 起，比字体里的箭头粗一档）和紧凑间距。
    """
    w = size * 0.88                 # 单枚箭头宽
    h = size * 0.30                 # 单枚箭头高
    gap = size * 0.36               # 两枚之间的空隙：够紧，但不至于糊成一个菱形
    pen = QtGui.QPen(color, max(1.4, size * 0.17))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.save()
    p.setPen(pen)
    p.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    x0 = cx
    # 上箭头（尖朝上）
    yt = cy - gap / 2.0
    path = QtGui.QPainterPath(QtCore.QPointF(x0, yt))
    path.lineTo(x0 + w / 2.0, yt - h)
    path.lineTo(x0 + w, yt)
    p.drawPath(path)
    # 下箭头（尖朝下）
    yb = cy + gap / 2.0
    path = QtGui.QPainterPath(QtCore.QPointF(x0, yb))
    path.lineTo(x0 + w / 2.0, yb + h)
    path.lineTo(x0 + w, yb)
    p.drawPath(path)
    p.restore()


class CCTile(Hoverable):
    """iOS 控制中心式方块磁贴：左上彩色圆图标，底部标题 + 状态（右侧一个小 chevron）。

    和横向的 Tile 是两套版式：这个是正方形、竖排，用在控制页右侧的 2×2 宫格。
    底部状态行是「二级菜单」热区：点它发 menu_clicked，点其余区域发 clicked（切换开关）。
    """
    menu_clicked = QtCore.Signal()

    def __init__(self, glyph: str, title: str, parent=None, size: int = 118,
                 tint: QtGui.QColor | None = None, has_menu: bool = True):
        super().__init__(parent)
        self.glyph = glyph
        self.title = title
        self.sub = ""
        self.on = False
        self.enabled_ = True
        self.tint = tint
        self.has_menu = has_menu            # 飞行模式没有二级菜单，不画 chevron
        self.on_spring = Spring(0, 380, 0.85, 0.005)
        self._menu_hot = False
        self.setMouseTracking(True)          # 悬停到状态行时给高亮，提示这里能展开
        self.setFixedSize(size, size)

    def _menu_rect(self) -> QtCore.QRectF:
        """状态行 + chevron 的点击区域（比文字本身宽一点，好点中）。"""
        if not self.has_menu:
            return QtCore.QRectF()
        r = QtCore.QRectF(self.rect())
        return QtCore.QRectF(r.x() + 6, r.bottom() - 32, r.width() - 12, 28)

    def mouseMoveEvent(self, e):
        hot = self._menu_rect().contains(e.position())
        if hot != self._menu_hot:
            self._menu_hot = hot
            self.update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._menu_hot = False
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if (e.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(e.position().toPoint())
                and self._menu_rect().contains(e.position())):
            self._press.to(0)
            self._kick()
            self.menu_clicked.emit()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def set_state(self, on: bool, sub: str = "", enabled: bool = True):
        changed = on != self.on or sub != self.sub or enabled != self.enabled_
        self.on, self.sub, self.enabled_ = on, sub, enabled
        self.on_spring.to(1.0 if on else 0.0)
        if changed:
            self._kick()

    def _tick(self):
        self.on_spring.step(0.016)
        super()._tick()
        if not self.on_spring.rest and not self._timer.isActive():
            self._timer.start()

    def paintEvent(self, e):
        p = painter(self)
        if theme.liquid:
            r = self.card_rect()
            self.card_transform(p, r)
            self.paint_card_bg(p, r, squircle_radius(r), nav=True)
        else:
            r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
            s = self.press_scale()
            p.translate(r.center())
            p.scale(s, s)
            p.translate(-r.center())
            base = theme.card(1.0 + 0.5 * self._hover.x)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(base)
            rad = squircle_radius(r)
            p.drawRoundedRect(r, rad, rad)

        a = 1.0 if self.enabled_ else 0.45
        t = clamp(self.on_spring.x, 0.0, 1.0)
        off = theme.track()
        on = QtGui.QColor(self.tint) if self.tint else theme.on_color()
        col = QtGui.QColor(
            round(off.red() + (on.red() - off.red()) * t),
            round(off.green() + (on.green() - off.green()) * t),
            round(off.blue() + (on.blue() - off.blue()) * t),
            round(off.alpha() + (255 - off.alpha()) * t))

        d = min(34.0, r.width() * 0.30)
        cr = QtCore.QRectF(r.x() + 12, r.y() + 11, d, d)
        p.setBrush(col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(cr)
        p.setFont(icon_font(d * 0.46))
        p.setPen(theme.on_fg() if t > 0.5 else theme.text(0.8 * a + 0.2))
        p.drawText(cr, Qt.AlignmentFlag.AlignCenter, self.glyph)

        # 标题（下沿上方）+ 状态行（带 chevron）
        tx = r.x() + 13
        tw = r.right() - tx - 12
        # 有状态行时标题上移一点（不再是给胶囊让位，只是让两行读起来不挤）
        ty = r.bottom() - (48 if self.sub else 46)
        p.setFont(ui_font(14, W.DemiBold))
        p.setPen(theme.text(a))
        fm = QtGui.QFontMetrics(p.font())
        theme.outlined_text(p, QtCore.QRectF(tx, ty, tw, 20),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
                   fm.elidedText(self.title, Qt.TextElideMode.ElideRight, int(tw)))

        if self.sub:
            sr = self._menu_rect()
            maxw = int(tw - (18 if self.has_menu else 2))
            # 状态文字长度不固定（"已连接到 3 个设备"、很长的 Wi-Fi 名）：先按 12px 试，
            # 放不下就逐档缩到 9px，实在还长才省略 —— 别一上来就截成"已连接…"。
            f = ui_font(12, W.DemiBold)
            fm2 = QtGui.QFontMetrics(f)
            px = 12
            while px > 9 and fm2.horizontalAdvance(self.sub) > maxw:
                px -= 1
                f = ui_font(px, W.DemiBold)
                fm2 = QtGui.QFontMetrics(f)
            sub = fm2.elidedText(self.sub, Qt.TextElideMode.ElideRight, maxw)
            adv = fm2.horizontalAdvance(sub)
            if theme.liquid:
                pass                     # 液态玻璃下不要底框：状态行只留文字 + ⌃⌄ 箭头
            elif self._menu_hot and self.has_menu:
                # 状态行悬停：淡底 + 更亮的箭头，提示这里是二级菜单入口
                hc = theme.hover()
                hc.setAlphaF(min(1.0, hc.alphaF() * 1.8))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(hc)
                p.drawRoundedRect(sr.adjusted(0, 0, 0, -2), 9, 9)
            p.setFont(f)
            p.setPen(theme.text3(0.95 * a + 0.05))
            theme.outlined_text(p, QtCore.QRectF(tx, r.bottom() - 26, tw - 12, 18),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sub)
            if self.has_menu:
                # ⌃⌄（Ctrl Center 那种上/下双箭头）：跟在状态文字后面，
                # 点这一行会弹出该模块的二级菜单
                cx = tx + min(adv + 6, tw - 14)
                _paint_expand_glyph(p, cx, r.bottom() - 17,
                                    theme.text(1.0 if self._menu_hot else 0.72))


class Segmented(QtWidgets.QWidget, Themed):
    """分段选择：选中项半透明白色圆角底，底块弹性滑动。"""
    changed = QtCore.Signal(int)
    def __init__(self, items: list[str], parent=None, height: int = 28):
        super().__init__(parent)
        self.items = items
        self.index = 0
        self.pos_ = Spring(0, 520, 0.72, 0.002)
        self.setFixedHeight(height)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        fm = QtGui.QFontMetrics(ui_font(12, W.Medium))
        self.setMinimumWidth(sum(fm.horizontalAdvance(t) + 24 for t in items))
        self._t = QtCore.QTimer(self, interval=16, timeout=self._tick)
        self._hook_theme()

    def set_index(self, i: int, emit: bool = False):
        i = int(clamp(i, 0, len(self.items) - 1))
        if i != self.index:
            self.index = i
            self.pos_.to(i)
            self._t.start()
            if emit:
                self.changed.emit(i)

    def _tick(self):
        self.pos_.step(0.016)
        self.update()
        win = self.window()
        if win is not None and win is not self:
            win.update()
        if self.pos_.rest:
            self._t.stop()

    def mouseReleaseEvent(self, e):
        n = len(self.items)
        self.set_index(int(e.position().x() / max(1, self.width()) * n), emit=True)

    def paintEvent(self, e):
        p = painter(self)
        r = QtCore.QRectF(self.rect())
        n = len(self.items)
        cw = r.width() / n
        sel = QtCore.QRectF(r.x() + cw * self.pos_.x + 2, r.y() + 2, cw - 4, r.height() - 4)
        if theme.liquid:
            paint_interactive_chip(p, self, sel, sel.height() / 2, hover=0.45)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.active_pill())
            p.drawRoundedRect(sel, sel.height() / 2, sel.height() / 2)
        p.setFont(ui_font(12, W.Medium))
        for i, t in enumerate(self.items):
            sel_text = i == self.index
            p.setPen(theme.pill_text() if sel_text else theme.text(0.6))
            theme.outlined_text(p, QtCore.QRectF(r.x() + cw * i, r.y(), cw, r.height()),
                                Qt.AlignmentFlag.AlignCenter, t, outline=not sel_text)


class Sparkline(QtWidgets.QWidget, Themed):
    def __init__(self, parent=None, color: QtGui.QColor | None = None, fixed_max: float | None = None):
        super().__init__(parent)
        self.values: list[float] = []
        self.color = color
        self.fixed_max = fixed_max
        self.baseline: float | None = None
        self._hook_theme()

    def set_values(self, vals, baseline: float | None = None):
        self.values = [float(v) for v in vals if v is not None]
        self.baseline = baseline
        self.update()

    def paintEvent(self, e):
        if len(self.values) < 2:
            return
        p = painter(self)
        r = QtCore.QRectF(self.rect()).adjusted(1, 2, -1, -2)
        vs = self.values
        lo = 0.0 if self.fixed_max else min(vs + ([self.baseline] if self.baseline is not None else []))
        hi = self.fixed_max or max(vs + ([self.baseline] if self.baseline is not None else []))
        if hi - lo < 1e-9:
            hi = lo + 1
        n = len(vs)
        pts = [QtCore.QPointF(r.x() + r.width() * i / (n - 1), r.bottom() - (v - lo) / (hi - lo) * r.height())
               for i, v in enumerate(vs)]
        col = QtGui.QColor(self.color or theme.text(0.8))
        path = QtGui.QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        fill = QtGui.QPainterPath(path)
        fill.lineTo(r.right(), r.bottom())
        fill.lineTo(r.x(), r.bottom())
        fill.closeSubpath()
        g = QtGui.QLinearGradient(0, r.top(), 0, r.bottom())
        c1 = QtGui.QColor(col)
        c1.setAlpha(70)
        c2 = QtGui.QColor(col)
        c2.setAlpha(0)
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p.fillPath(fill, g)
        if self.baseline is not None:
            y = r.bottom() - (self.baseline - lo) / (hi - lo) * r.height()
            pen = QtGui.QPen(theme.text3(), 1, Qt.PenStyle.DashLine)
            p.setPen(pen)
            p.drawLine(QtCore.QPointF(r.x(), y), QtCore.QPointF(r.right(), y))
        p.setPen(QtGui.QPen(col, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)


class Card(QtWidgets.QFrame, Themed):
    """轻卡片：极淡的白色圆角底（无描边、无分割线）。

    nav=True 时液态主题改用导航胶囊同款玻璃，圆角按短边 18%（squircle）。
    """
    def __init__(self, parent=None, radius: float = 18, alpha: float = 1.0, nav: bool = False):
        super().__init__(parent)
        self.radius = radius
        self.alpha = alpha
        self.nav = nav
        self._hook_theme()

    def paintEvent(self, e):
        p = painter(self)
        r = QtCore.QRectF(self.rect())
        rad = squircle_radius(r) if self.nav else self.radius
        if theme.liquid:
            paint_interactive_chip(p, self, r, rad, nav=self.nav)
            return
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.card(self.alpha))
        p.drawRoundedRect(r, rad, rad)


class ScrollArea(QtWidgets.QScrollArea):
    """透明滚动区，细滚动条；滚轮走缓动动画（所有主题一致）。"""

    _WHEEL_STEP = 52.0     # 一格滚轮的行程：设备行 44+6=50，略超一格，滚一次就整行进位
    _WHEEL_DUR = 240       # 动画基准时长（ms）；距离越远按比例延长，上限 _WHEEL_DUR_MAX
    _WHEEL_DUR_MAX = 320

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.viewport().setAutoFillBackground(False)
        self.setStyleSheet("QScrollArea{background:transparent;border:none}")
        self.viewport().setStyleSheet("background:transparent")
        self.inner = QtWidgets.QWidget()
        self.inner.setAutoFillBackground(False)
        self.inner.setObjectName("scrollInner")
        self.inner.setStyleSheet("#scrollInner{background:transparent}")
        self.setWidget(self.inner)
        self.inner.setAutoFillBackground(False)   # setWidget 会强制打开
        theme.changed.connect(self._style_bar)
        self._style_bar()

        # 滚轮平滑滚动：QScrollArea 默认是「一格 = 立即跳一格」，液态玻璃下面这种硬跳
        # 和整个岛的缓动语言不搭。这里自己维护目标值 + OutCubic 补间，所有主题通用。
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_smooth_value)
        self._target = 0.0
        # 一格滚轮的行程：默认 52；列表页可以按自己的行距改（44+6=50），滚一次正好一整行
        self.row_step = self._WHEEL_STEP
        self.verticalScrollBar().sliderPressed.connect(self._anim.stop)   # 手拖滚动条时不抢

    def _style_bar(self):
        c = theme.qss_color(theme.text(0.25))
        self.verticalScrollBar().setStyleSheet(
            "QScrollBar:vertical{background:transparent;width:6px;margin:4px 0 4px 0}"
            f"QScrollBar::handle:vertical{{background:{c};border-radius:3px;min-height:24px}}"
            "QScrollBar::add-line,QScrollBar::sub-line{height:0}"
            "QScrollBar::add-page,QScrollBar::sub-page{background:transparent}")

    def _on_smooth_value(self, v: float):
        self.verticalScrollBar().setValue(int(round(v)))

    def smooth_to(self, target: float):
        """滚到指定 scrollbar 值（带缓动）；外部想程序化滚动时也可以直接用。"""
        bar = self.verticalScrollBar()
        target = float(clamp(target, bar.minimum(), bar.maximum()))
        if abs(target - bar.value()) < 0.5:
            self._anim.stop()
            bar.setValue(int(target))
            return
        self._target = target
        dur = int(min(self._WHEEL_DUR_MAX, max(self._WHEEL_DUR * 0.6, abs(target - bar.value()) * 2.4)))
        self._anim.stop()
        self._anim.setDuration(dur)
        self._anim.setStartValue(float(bar.value()))
        self._anim.setEndValue(target)
        self._anim.start()

    def wheelEvent(self, e):
        bar = self.verticalScrollBar()
        if bar.maximum() <= bar.minimum():
            e.ignore()                     # 不能滚：交回外层（大岛自己还有别的滚轮语义）
            return
        # 动画中途再滚，要从「目标」接着加，否则连续滚动会打架、滚不动
        cur = self._target if self._anim.state() == QtCore.QAbstractAnimation.State.Running else float(bar.value())
        pd = e.pixelDelta().y()
        ad = e.angleDelta().y()
        # 滚轮 y 正 = 向上滚，滚动条的 value 要变小，所以统一取负
        if pd:
            step = -pd * 2.4              # 精密触控板：按像素给，短步长更跟手
        elif ad:
            step = -(ad / 120.0) * self.row_step
        else:
            e.ignore()
            return
        self.smooth_to(cur + step)
        e.accept()



def hbox(*items, spacing: int = 8, margins=(0, 0, 0, 0)) -> QtWidgets.QHBoxLayout:
    lay = QtWidgets.QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        _add(lay, it)
    return lay


def vbox(*items, spacing: int = 8, margins=(0, 0, 0, 0)) -> QtWidgets.QVBoxLayout:
    lay = QtWidgets.QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        _add(lay, it)
    return lay


def _add(lay, it):
    if it is None:
        lay.addStretch(1)
    elif isinstance(it, int):
        lay.addSpacing(it)
    elif isinstance(it, QtWidgets.QLayout):
        lay.addLayout(it)
    elif isinstance(it, tuple):
        if isinstance(it[0], QtWidgets.QLayout):
            lay.addLayout(it[0], it[1])
        else:
            lay.addWidget(it[0], it[1])
    else:
        lay.addWidget(it)


def rounded_pixmap(img: QtGui.QImage | QtGui.QPixmap | None, size: int, radius: float,
                   dpr: float = 2.0) -> QtGui.QPixmap | None:
    if img is None:
        return None
    src = QtGui.QPixmap.fromImage(img) if isinstance(img, QtGui.QImage) else img
    if src.isNull():
        return None
    px = round(size * dpr)
    out = QtGui.QPixmap(px, px)
    out.fill(Qt.GlobalColor.transparent)
    p = QtGui.QPainter(out)
    p.setRenderHint(AA)
    p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    path = QtGui.QPainterPath()
    path.addRoundedRect(QtCore.QRectF(0, 0, px, px), radius * dpr, radius * dpr)
    p.setClipPath(path)
    scaled = src.scaled(px, px, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    p.drawPixmap((px - scaled.width()) // 2, (px - scaled.height()) // 2, scaled)
    p.end()
    out.setDevicePixelRatio(dpr)
    return out


class LineEdit(QtWidgets.QLineEdit):
    """需要键盘焦点的输入框：点击时通知灵动岛临时接受焦点。"""
    focus_wanted = QtCore.Signal()

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setProperty("wants_focus", True)
        self.setFixedHeight(32)
        self.setFont(ui_font(13))
        theme.changed.connect(self._style)
        self._style()

    def _style(self):
        self.setStyleSheet(
            f"QLineEdit{{background:{theme.qss_color(theme.card())};border:none;border-radius:16px;"
            f"padding:0 14px;color:{theme.qss_color(theme.text())};"
            f"selection-background-color:rgba(79,140,255,120)}}")
        pal = self.palette()
        pal.setColor(QtGui.QPalette.ColorRole.PlaceholderText, theme.text3())
        self.setPalette(pal)
        apply_qss_text_shadow(self)

    def mousePressEvent(self, e):
        self.focus_wanted.emit()
        super().mousePressEvent(e)


class TextEdit(QtWidgets.QPlainTextEdit):
    focus_wanted = QtCore.Signal()
    submit = QtCore.Signal()

    def __init__(self, placeholder: str = "", parent=None, px: float = 14):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setProperty("wants_focus", True)
        self.setFont(ui_font(px))
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.viewport().setAutoFillBackground(False)
        theme.changed.connect(self._style)
        self._style()

    def _style(self):
        self.setStyleSheet(
            f"QPlainTextEdit{{background:{theme.qss_color(theme.card())};border:none;border-radius:16px;"
            f"padding:8px 10px;color:{theme.qss_color(theme.text())};"
            f"selection-background-color:rgba(79,140,255,120)}}"
            "QScrollBar:vertical{width:0}")
        pal = self.palette()
        pal.setColor(QtGui.QPalette.ColorRole.PlaceholderText, theme.text3())
        self.setPalette(pal)
        apply_qss_text_shadow(self)

    def mousePressEvent(self, e):
        self.focus_wanted.emit()
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.submit.emit()
            return
        super().keyPressEvent(e)


def fmt_bytes(n: float, per_s: bool = False) -> str:
    units = ["B", "K", "M", "G", "T"]
    i = 0
    n = float(n or 0)
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    s = f"{n:.0f}" if n >= 100 or i == 0 else f"{n:.1f}"
    return f"{s}{units[i]}" + ("/s" if per_s else "")


def fmt_time(sec: float) -> str:
    sec = max(0, int(sec or 0))
    return f"{sec // 60}:{sec % 60:02d}"


def glyph_pixmap(glyph: str, px: int, color: QtGui.QColor) -> QtGui.QPixmap:
    pm = QtGui.QPixmap(px * 2, px * 2)
    pm.fill(Qt.GlobalColor.transparent)
    p = QtGui.QPainter(pm)
    p.setFont(icon_font(px * 2 * 0.8))
    p.setPen(color)
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, glyph)
    p.end()
    pm.setDevicePixelRatio(2)
    return pm


_ = math  # 保留导入（部分页面使用）
