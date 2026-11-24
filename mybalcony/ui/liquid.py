# -*- coding: utf-8 -*-
"""液态玻璃的通用绘制。

岛本体、二级菜单、弹出卡片用的是同一套"光学层"：背景先抓屏（模糊 + 提纯），再沿形状边缘做
位移折射，最后叠暗内壁 / 亮刃口 / 镜面反射。任何自己开窗口自绘的小面板都可以直接复用。
"""
from __future__ import annotations

import re
import time

from PySide6 import QtCore, QtGui, QtWidgets

from . import glass
from .theme import theme
from .theme import ui_font as _ui_font

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


def dual_edge(bb: QtCore.QRectF, hi: int, mid: int = 0,
              rgb: tuple[int, int, int] = (255, 255, 255),
              up_right: float = 1.0) -> QtGui.QLinearGradient:
    """左下 ↔ 右上对角双光渐变。

    沿这条对角线投影：左下角 0、右上角 1 最亮，左上 / 右下正好落在 0.5 处熄灭。
    直接当描边画刷用，刃口就是"两头亮、中间暗"的一道光，而不是均匀一圈白边。
    rgb 默认白：亮背景上白刃口与背景 1:1 会消失，调用方可传墨色改成"厚度暗侧"。
    up_right < 1 把右上端压弱，让左下成为唯一主光源（单向光才有"左下打了高光"的方向感）。
    """
    g = QtGui.QLinearGradient(bb.left(), bb.bottom(), bb.right(), bb.top())
    r, gg, b = rgb
    g.setColorAt(0.00, QtGui.QColor(r, gg, b, hi))
    g.setColorAt(0.30, QtGui.QColor(r, gg, b, mid))
    g.setColorAt(0.50, QtGui.QColor(r, gg, b, 0))
    g.setColorAt(0.70, QtGui.QColor(r, gg, b, round(mid * up_right)))
    g.setColorAt(1.00, QtGui.QColor(r, gg, b, round(hi * up_right)))
    return g


def paint_static_layers(p: QtGui.QPainter, path: QtGui.QPainterPath, bb: QtCore.QRectF,
                        edge_rgb: tuple[int, int, int] = (255, 255, 255)):
    """光学层里不随光标变化的前 6 层。桌面窗口每帧重画这几层渐变描边很贵，调用方可以
    把这几层预渲染成一张透明图缓存起来，每帧只贴一次图 + 画跟手高光。

    edge_rgb：刃口色。纯白背景上白刃口与背景 1:1 会整条消失，调用方可传墨色改画
    "玻璃厚壁的暗侧"（亮底自适应）。
    """
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
    # 2) 细亮刃口：玻璃壁的横截面。光源钉在左下——左下角最亮、右上只留弱轮廓
    #    （up_right=0.45）。对称双光两侧一样亮，左下高光就立不起来。
    eg = dual_edge(bb, 124, 52, edge_rgb, up_right=0.45)
    p.strokePath(path, QtGui.QPen(QtGui.QBrush(eg), 1.4))
    p.restore()


def paint_spec(p: QtGui.QPainter, path: QtGui.QPainterPath, bb: QtCore.QRectF,
               spec_pt: QtCore.QPointF | None = None):
    """第 7 层：跟着光标走的镜面反射点，是光学层里唯一每帧都在变的层。

    光源钉在左下：光标离开时高光回落到左下角（原来回落到左上，与"左下打光"的方向
    相反，边缘刃口和镜面光会互相打架）。
    """
    p.save()
    p.setClipPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    w, h = bb.width(), bb.height()
    sp = spec_pt or QtCore.QPointF(bb.left() + w * 0.16, bb.bottom() - h * 0.22)
    rad = QtGui.QRadialGradient(sp, max(10.0, min(w, h) * 0.2))
    rad.setColorAt(0.0, QtGui.QColor(255, 255, 255, 80))
    rad.setColorAt(0.5, QtGui.QColor(255, 255, 255, 26))
    rad.setColorAt(1.0, QtGui.QColor(255, 255, 255, 0))
    p.fillPath(path, rad)
    p.restore()


def paint_corner_spec(p: QtGui.QPainter, path: QtGui.QPainterPath, bb: QtCore.QRectF,
                      strength: float = 1.0):
    """左下角固定的镜面高光：光源钉在左下，跟手光离开后这里仍留一块"被照到"的亮斑。

    纯白背景上白光与背景 1:1，本身看不出来——它的作用是配合 shader 的边缘压暗
    （左下最亮、右上最暗）构成"光从左下来"的立体感；暗背景上则是直接的亮斑。
    """
    if path.isEmpty() or strength <= 0.0:
        return
    p.save()
    p.setClipPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    w, h = bb.width(), bb.height()
    c = QtCore.QPointF(bb.left() + w * 0.17, bb.bottom() - h * 0.24)
    rad = QtGui.QRadialGradient(c, max(18.0, min(w, h) * 0.55))
    rad.setColorAt(0.0, QtGui.QColor(255, 255, 255, int(46 * strength)))
    rad.setColorAt(0.45, QtGui.QColor(255, 255, 255, int(15 * strength)))
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


# --- QMenu 皮肤 -----------------------------------------------------------
# 液态菜单的字不能只靠 QSS：Qt 样式表没有 text-shadow / text-stroke，菜单项文字又是
# QStyle 画的（不是独立 QLabel），QGraphicsDropShadowEffect 挂不上。这里改用 QProxyStyle
# 接管 CE_MenuItem —— 但有个必须遵守的前提：**液态菜单的 QSS 里绝不能出现 background**。
# 实测（PySide6 6.12 / offscreen）：只要 QMenu{background:...} 这条规则存在，
# QStyleSheetStyle 就会自己包办 CE_MenuItem，ProxyStyle::drawControl 一次都不会被调用；
# 只有 color / font-family / font-size 时才会把菜单项转发给 base style。
# 因此 MENU_QSS 只保留字色与字体；底色仍是项目原有的液态玻璃（MenuGlass._paint 的
# paint_panel），文字由 LiquidMenuStyle 画成白字黑边。
MENU_QSS = "QMenu{{color:{fg};font-family:{fonts};font-size:13px}}"

LIQUID_MENU_RADIUS = 14.0         # 与 paint_panel 的菜单圆角一致
LIQUID_MENU_ITEM_RADIUS = 9.0     # 选中高亮的圆角（沿用原 QSS ::item 的 9px）
LIQUID_MENU_TEXT_PX = 13          # 与 MENU_QSS 的 font-size 一致
LIQUID_MENU_PAD_LEFT = 14         # 普通项文字左内边距（沿用原 QSS ::item）
LIQUID_MENU_PAD_RIGHT = 22        # 普通项文字右内边距
LIQUID_MENU_INDENT = 38           # 有勾选列 / 图标列时，base style 的文字起点
LIQUID_MENU_ARROW = 14            # 子菜单箭头预留宽度
LIQUID_MENU_DISABLED = QtGui.QColor(176, 180, 188)   # 禁用项：灰色语义保留，仍描边


_MENU_SEL_CACHE: dict = {}


def _menu_selection_color() -> QtGui.QColor:
    """选中高亮：用 palette 里 menu[2] 的原值（含原 alpha），不额外加深。

    QColor 不认识 QSS 的 rgba(...) 字符串，所以手动解析数字；这里只做转换，
    不修改 palette、也不改色值/透明度（非液态主题共用同一函数入口）。
    """
    raw = str(theme.menu_qss()[2])
    cached = _MENU_SEL_CACHE.get(raw)
    if cached is not None:
        return cached
    nums = [int(x) for x in re.findall(r"\d+", raw)]
    if len(nums) >= 4:
        c = QtGui.QColor(nums[0], nums[1], nums[2], nums[3])
    elif len(nums) == 3:
        c = QtGui.QColor(nums[0], nums[1], nums[2], 255)
    else:
        c = QtGui.QColor(120, 170, 230, 70)   # 液态 palette 原值兜底
    _MENU_SEL_CACHE[raw] = c
    return c


def _menu_text(text: str) -> str:
    """QStyle 会吃掉加速键的 '&'，自绘时也要做同样的处理（'&&' 表示一个字面量 '&'）。"""
    return text.replace("&&", "\x00").replace("&", "").replace("\x00", "&")


def _prev_menu_style(m: QtWidgets.QMenu):
    """记住调用方自己 setStyle 过的 style；QStyleSheetStyle / 应用 style 不必保存。

    QStyleSheetStyle 归 QWidget 所有，setStyle(代理) 时 Qt 会删掉它，保存指针会在
    undress 时拿到悬空 C++ 对象；这两种情况恢复时只要 setStyle(None) + 还原 QSS 即可。
    """
    style = m.style()
    if style is None:
        return None
    app_style = QtWidgets.QApplication.style()
    if style is app_style or style == app_style:
        return None
    if style.metaObject().className() == "QStyleSheetStyle":
        return None
    return style


class _LiquidMenuStyle(QtWidgets.QProxyStyle):
    """液态菜单专用代理样式：背景/图标/勾/箭头交给 base style，文字自己用 outlined_text 画。

    实测依据：QSS 只要带 background 规则，QStyleSheetStyle 就完全接管 CE_MenuItem，
    ProxyStyle 不会被调用；所以 dress() 里给的 QSS 只有 color/font，底色仍走 paint_panel。
    """

    def __init__(self):
        # 不传 base：QProxyStyle() 自动以 QApplication.style() 为底，且不会接管其所有权。
        super().__init__()

    def drawPrimitive(self, element, option, painter, widget=None):  # noqa: N802
        # 菜单面板玻璃由 MenuGlass._paint 负责；不让 base style 铺一层不透明系统底色。
        panel = getattr(QtWidgets.QStyle.PrimitiveElement, "PE_PanelMenu", None)
        frame = getattr(QtWidgets.QStyle.PrimitiveElement, "PE_FrameMenu", None)
        if element in (panel, frame) and element is not None:
            return
        return super().drawPrimitive(element, option, painter, widget)

    def sizeFromContents(self, typ, opt, contentsSize, widget=None):  # noqa: N802
        if typ == QtWidgets.QStyle.ContentsType.CT_MenuItem:
            if isinstance(opt, QtWidgets.QStyleOptionMenuItem) and \
                    opt.menuItemType == QtWidgets.QStyleOptionMenuItem.MenuItemType.Separator:
                return QtCore.QSize(max(8, contentsSize.width()), 8)
            # 原 QSS 的 item padding 6px 22px 6px 14px：左右 14+22、上下 6+6。
            return QtCore.QSize(contentsSize.width() + LIQUID_MENU_PAD_LEFT + LIQUID_MENU_PAD_RIGHT,
                                max(26, contentsSize.height() + 12))
        return super().sizeFromContents(typ, opt, contentsSize, widget)

    def drawControl(self, element, option, painter, widget=None):  # noqa: N802
        if element != QtWidgets.QStyle.ControlElement.CE_MenuItem or \
                not isinstance(option, QtWidgets.QStyleOptionMenuItem):
            return super().drawControl(element, option, painter, widget)

        if option.menuItemType == QtWidgets.QStyleOptionMenuItem.MenuItemType.Separator:
            r = QtCore.QRectF(option.rect)
            y = r.center().y()
            painter.save()
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 46), 1.0))
            painter.drawLine(QtCore.QPointF(r.left() + LIQUID_MENU_PAD_LEFT, y),
                             QtCore.QPointF(r.right() - LIQUID_MENU_PAD_RIGHT, y))
            painter.restore()
            return

        text = _menu_text(option.text)
        enabled = bool(option.state & QtWidgets.QStyle.StateFlag.State_Enabled)
        hot = enabled and bool(option.state & (QtWidgets.QStyle.StateFlag.State_Selected |
                                              QtWidgets.QStyle.StateFlag.State_MouseOver))

        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        if hot:
            path = QtGui.QPainterPath()
            path.addRoundedRect(QtCore.QRectF(option.rect),
                                LIQUID_MENU_ITEM_RADIUS, LIQUID_MENU_ITEM_RADIUS)
            painter.fillPath(path, _menu_selection_color())
        painter.restore()

        # 让 base style 画背景之外的一切（图标 / ✓ / 子菜单箭头），但**不画文字**：
        # text 置空后 base style 完全没有字形输出（offscreen 像素比对验证过），不会重复画字。
        base_opt = QtWidgets.QStyleOptionMenuItem(option)
        base_opt.text = ""
        base_opt.state = option.state & ~(QtWidgets.QStyle.StateFlag.State_Selected |
                                          QtWidgets.QStyle.StateFlag.State_MouseOver)
        pal = QtGui.QPalette(base_opt.palette)
        for role in (QtGui.QPalette.ColorRole.Text, QtGui.QPalette.ColorRole.WindowText,
                     QtGui.QPalette.ColorRole.HighlightedText):
            pal.setColor(role, theme.text())
        base_opt.palette = pal
        super().drawControl(element, base_opt, painter, widget)

        if not text:
            return
        left = option.rect.left() + LIQUID_MENU_PAD_LEFT
        if (not option.icon.isNull() or
                option.checkType != QtWidgets.QStyleOptionMenuItem.CheckType.NotCheckable or
                option.menuHasCheckableItems):
            # base style 在 12..27 画图标 / 勾选列，文字从 38 起才不会压上去
            left = option.rect.left() + LIQUID_MENU_INDENT
        right = option.rect.right() - LIQUID_MENU_PAD_RIGHT
        if option.menuItemType == QtWidgets.QStyleOptionMenuItem.MenuItemType.SubMenu:
            right -= LIQUID_MENU_ARROW
        rect = QtCore.QRect(left, option.rect.top() + 4,
                            max(4, right - left), max(4, option.rect.height() - 8))
        color = theme.text() if enabled else QtGui.QColor(LIQUID_MENU_DISABLED)
        painter.save()
        painter.setFont(_ui_font(LIQUID_MENU_TEXT_PX))
        painter.setPen(color)
        theme.outlined_text(painter, rect,
                            QtCore.Qt.AlignmentFlag.AlignLeft |
                            QtCore.Qt.AlignmentFlag.AlignVCenter |
                            QtCore.Qt.TextFlag.TextSingleLine,
                            text, color=color)
        painter.restore()


# 强引用 + 主题切换时的原 style：QStyle 不属于 QWidget，Python 侧必须自己留住。
_MENU_STYLE_REFS: dict = {}


class MenuGlass(QtCore.QObject):
    """装在 QApplication 上的事件过滤器：液态玻璃主题下，所有 QMenu（含子菜单）都画成玻璃。"""

    def __init__(self, app):
        super().__init__(app)
        self._app = app
        app.installEventFilter(self)
        theme.changed.connect(self._on_theme)

    def _on_theme(self):
        """主题切换：切出液态时恢复原皮肤，切回液态时把已有菜单重新 dress。"""
        if theme.liquid:
            for m in self._app.topLevelWidgets():
                if isinstance(m, QtWidgets.QMenu):
                    self.dress(m)
            return
        for m in self._app.topLevelWidgets():
            if isinstance(m, QtWidgets.QMenu):
                self.undress(m)
        for m in list(_MENU_STYLE_REFS):
            self.undress(m)

    @staticmethod
    def dress(m: QtWidgets.QMenu):
        """液态菜单：原液态玻璃底 + 白字黑边。QSS 只给字色/字体，绘制交给 _LiquidMenuStyle。"""
        if m.property("lg_dressed"):
            return
        m.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        m.setProperty("lg_prev", m.styleSheet())
        style = _LiquidMenuStyle()
        _MENU_STYLE_REFS[m] = (style, _prev_menu_style(m))
        # 顺序：先 setStyle 再 setStyleSheet。QSS 里没有 background/item 规则时
        # QStyleSheetStyle 才转发 CE_MenuItem 给代理样式（见 MENU_QSS 处的实测说明）。
        m.setStyle(style)
        m.setStyleSheet(MENU_QSS.format(fg=theme.qss_color(theme.text()), fonts=theme.font_css()))
        m.setProperty("lg_dressed", True)

    @staticmethod
    def undress(m: QtWidgets.QMenu):
        """换回别的主题：恢复原来的皮肤 / style，绝不把液态代理样式留给非液态菜单。"""
        if not m.property("lg_dressed"):
            return
        style, prev_style = _MENU_STYLE_REFS.pop(m, (None, None))
        m.setStyle(prev_style if prev_style is not None else None)
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
        _backdrop(m, r, LIQUID_MENU_RADIUS)

    @staticmethod
    def _paint(m: QtWidgets.QMenu):
        p = QtGui.QPainter(m)
        # capture=True：命中 Show 时抓好的缓存；万一缓存过期才会重抓
        paint_panel(p, m, QtCore.QRectF(m.rect()), 14.0)
        p.end()
