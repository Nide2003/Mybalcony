# -*- coding: utf-8 -*-
"""顶部导航：透明顶栏 + 图标组。

- 标签没有背景色和分割线，图标/文字直接落在玻璃上；
- 当前项展开显示文字，并加半透明白色圆角底；其余只留图标；
- 切换时每项宽度都由弹簧驱动（欠阻尼 -> 弹性缓动），底块跟着宽度一起流动；
- 长按空白处 -> drag_requested，用来拖动整个灵动岛；
- 长按页签后左右拖动 -> 重排页签（和天气页城市胶囊一样的 sortable list），松手后发 reordered。
"""
from __future__ import annotations

import time

from PySide6 import QtCore, QtGui, QtWidgets

from .anim import Spring, clamp
from .theme import W, icon_font, theme, ui_font
from .widgets import IconButton, painter

Qt = QtCore.Qt

ICON_W = 34.0
GAP = 16.0
BTN_GAP = 14.0        # 图标组与右侧按钮之间的间距（整组居中时一起算）
CAP_PAD = 14.0        # 玻璃胶囊在图标组两侧各留的空白（用户要"缩进去"，就是它）
LONG_PRESS_MS = 380


class _TabGhost(QtWidgets.QWidget):
    """拖动时浮起来的那枚页签：抬高、放大、带阴影，跟着鼠标走。"""
    PADX, PADY, PADB = 14.0, 8.0, 16.0
    BODY_H = 32.0

    def __init__(self, glyph: str, label: str, width: float, full_w: float, active: bool, parent=None):
        super().__init__(parent)
        self.glyph, self.label = glyph, label
        self.full_w, self.active = full_w, active
        self.lift = Spring(0.0, 320, 0.55, 0.02)
        self.setFixedSize(round(width + self.PADX * 2), round(self.BODY_H + self.PADY + self.PADB))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.font_ = ui_font(12.5, W.DemiBold)

    def body(self) -> QtCore.QRectF:
        return QtCore.QRectF(self.PADX, self.PADY, self.width() - self.PADX * 2, self.BODY_H)

    def paintEvent(self, e):
        p = painter(self)
        r = self.body()
        t = clamp(self.lift.x, 0.0, 1.0)
        p.save()
        p.translate(0, -6 * t)                        # 抬离原位
        k = 1.0 + 0.06 * t
        p.translate(r.center())
        p.scale(k, k)
        p.translate(-r.center())
        rad = r.height() / 2
        for dy, a in ((9, 0.05), (6, 0.09), (3, 0.13)):      # 阴影：越远越淡
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QtGui.QColor(0, 0, 0, int(255 * a * t)))
            p.drawRoundedRect(r.adjusted(-1, dy - 1, 1, dy + 1), rad, rad)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.active_pill() if self.active else theme.card(1.5))
        p.drawRoundedRect(r, rad, rad)
        p.setFont(icon_font(15))
        p.setPen(theme.pill_text() if self.active else theme.text(0.9))
        p.drawText(QtCore.QRectF(r.x(), r.y(), ICON_W, r.height()), Qt.AlignmentFlag.AlignCenter, self.glyph)
        extra = self.full_w - ICON_W
        prog = clamp((r.width() - ICON_W) / extra, 0, 1) if extra > 0 else 0
        if prog > 0.02:
            p.save()
            p.setClipRect(r.adjusted(0, 0, -4, 0))
            p.setFont(self.font_)
            p.setPen(theme.pill_text(prog) if self.active else theme.text(0.85 * prog))
            p.drawText(QtCore.QRectF(r.x() + ICON_W - 4, r.y(), extra + 8, r.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.label)
            p.restore()
        p.restore()


class NavBar(QtWidgets.QWidget):
    changed = QtCore.Signal(str)
    drag_requested = QtCore.Signal(QtCore.QPoint)
    reordered = QtCore.Signal(list)            # 拖动排序结束：参数为新的 key 顺序

    def __init__(self, items: list[tuple[str, str, str]], parent=None, height: int = 36):
        super().__init__(parent)
        self.items = items                       # (key, glyph, label)
        self.index = 0
        self.hidden: set[str] = set()             # 被关掉的页签：不占位、不绘制、点不到
        self.setFixedHeight(height)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.font_ = ui_font(12.5, W.DemiBold)
        fm = QtGui.QFontMetrics(self.font_)
        self.full_w = [ICON_W + fm.horizontalAdvance(lbl) + 46 for _, _, lbl in items]   # 选中时文字右侧留出更大空白
        self.anchor_fn = None          # 返回第一个标签（主页）中心应对齐的 x（导航栏坐标），None = 整组居中
        self.anchor_key = "home"       # 只有排在第一位的这个页签才跟随锚点，顺序变了就退回居中
        self.w = [Spring(ICON_W, 260, 0.56, 0.05) for _ in items]
        self.hover = [Spring(0, 400, 1.0, 0.01) for _ in items]
        self.pops = [Spring(0.0, 420, 0.32, 0.01) for _ in items]   # 落位后的果冻
        self.badges: dict[str, int] = {}
        self.w[0].snap(self.full_w[0])
        self._hover_i = -1
        self._press_pos: QtCore.QPoint | None = None
        self._press_i = -1                        # 按在哪个页签上（还没成为拖动）
        self._press_g: QtCore.QPoint | None = None
        self._drag_i = -1                         # 正在拖动的页签下标
        self._drag_moved = False
        self._ghost = None                        # 拖起来的那枚页签（浮层）
        self._ghost_host = None
        self._ghost_cx = 0.0                      # 浮层中心（浮层宿主坐标）
        self._ghost_gy = 0.0                      # 浮层固定高度
        self._landing = -1                        # 正在落位的页签下标
        self._ghost_x = Spring(0.0, 560, 0.62, 0.5)
        self._ghost_y = Spring(0.0, 560, 0.62, 0.5)
        self._lp = QtCore.QTimer(self, singleShot=True, interval=LONG_PRESS_MS, timeout=self._long_press)
        self._lp_tab = QtCore.QTimer(self, singleShot=True, interval=LONG_PRESS_MS, timeout=self._begin_tab_drag)
        self._t = QtCore.QTimer(self, interval=16, timeout=self._tick)
        self._last = time.perf_counter()
        theme.changed.connect(self.update)

        # 右侧按钮（不属于图标组）
        self.extra = QtWidgets.QHBoxLayout()
        self.right_buttons: list[IconButton] = []

    def add_right_button(self, glyph: str, tip: str, cb) -> IconButton:
        b = IconButton(glyph, 30, 13, tip, self)
        b.clicked.connect(cb)
        self.right_buttons.append(b)
        self._place_right()
        return b

    def resizeEvent(self, e):
        self._place_right()

    def _place_right(self):
        """右侧按钮跟在图标组尾巴后面，跟着一起居中；没有图标组时退回贴右。"""
        rects = self._rects()
        xs = [r.right() for r in rects if r.width() > 0]
        if not xs:
            x = self.width()
            for b in reversed(self.right_buttons):
                x -= b.width()
                b.move(x, (self.height() - b.height()) // 2)
                x -= 2
            return
        x = max(xs) + BTN_GAP
        for b in self.right_buttons:
            b.move(round(x), (self.height() - b.height()) // 2)
            x += b.width() + 2

    def capsule_rect(self) -> QtCore.QRectF:
        """导航玻璃胶囊的范围（导航控件局部坐标）：图标组 + 右侧按钮 + 两侧各 CAP_PAD。

        胶囊要贴着内容，不能铺满控件宽度（那样两端会各空出一大块）。
        图标组宽度随当前页签弹性变化，所以这个矩形也是每帧变的。
        """
        rects = [r for r in self._rects() if r.width() > 0]
        xs = [r.left() for r in rects] + [b.x() for b in self.right_buttons]
        xe = [r.right() for r in rects] + [b.x() + b.width() for b in self.right_buttons]
        if not xs:
            return QtCore.QRectF(0, 0, self.width(), self.height())
        x0 = min(xs) - CAP_PAD
        x1 = max(xe) + CAP_PAD
        return QtCore.QRectF(x0, 0, x1 - x0, self.height())

    # --- 状态 ---
    def keys(self) -> list[str]:
        return [k for k, _, _ in self.items]

    def visible_keys(self) -> list[str]:
        return [k for k, _, _ in self.items if k not in self.hidden]

    def reorder(self, keys) -> bool:
        """按给定 key 顺序重排页签；没出现过的 key 依原顺序补在末尾。

        只换显示顺序：items 与每项自己的弹簧、宽度缓存一起搬家，当前页跟着自己的 key 走。
        """
        old = self.keys()
        order = [k for k in (keys or ()) if k in old]
        order += [k for k in old if k not in order]
        if order == old:
            return False
        cur = old[self.index]
        at = {k: i for i, k in enumerate(old)}
        self.items = [self.items[at[k]] for k in order]
        self.full_w = [self.full_w[at[k]] for k in order]
        self.w = [self.w[at[k]] for k in order]
        self.hover = [self.hover[at[k]] for k in order]
        self.pops = [self.pops[at[k]] for k in order]
        self.index = order.index(cur)
        self._kick()
        return True

    def set_hidden(self, keys) -> None:
        """关掉若干页签：只影响显示与点击，页面对象本身还在（切回来是同一个实例）。"""
        if self._ghost is not None:               # 拖动中改页签：先把浮层收掉
            self._cancel_ghost()
        self.hidden = {k for k in (keys or ()) if k in self.keys()}
        if all(k in self.hidden for k in self.keys()):
            self.hidden.clear()                   # 不许把导航栏关空
        if self.items[self.index][0] in self.hidden:
            vis = self.visible_keys()
            if vis:
                self.set_current(vis[0])
        self.update()

    def set_current(self, key: str, emit: bool = False):
        keys = self.keys()
        if key not in keys or key in self.hidden:
            return
        i = keys.index(key)
        if i == self.index:
            return
        self.index = i
        for j, s in enumerate(self.w):
            s.to(self.full_w[j] if j == i else ICON_W)
        self._kick()
        if emit:
            self.changed.emit(key)

    def current(self) -> str:
        return self.items[self.index][0]

    def set_badge(self, key: str, n: int):
        if self.badges.get(key, 0) != n:
            self.badges[key] = n
            self.update()

    def _kick(self):
        if not self._t.isActive():
            self._last = time.perf_counter()
            self._t.start()

    def _tick(self):
        now = time.perf_counter()
        dt = min(0.05, now - self._last)
        self._last = now
        for s in self.w + self.hover + self.pops:
            s.step(dt)
        busy = self._ghost_tick()
        self._place_right()                       # 宽度动画时按钮跟着图标组走
        rest = all(s.rest for s in self.w + self.hover + self.pops)   # 落位时可能刚触发果冻
        self.update()
        win = self.window()
        if win is not None and win is not self:
            # 页签底块是透明底上的圆角形状，局部重绘会让四角闪白，整窗重绘躲开这个坑
            win.update()
        if rest and not busy:
            self._t.stop()

    def _rects(self) -> list[QtCore.QRectF]:
        """「主页」标签固定在播放器封面正上方；最后一个标签放在与之对称的位置，
        中间的标签按比例均分间距，整排左右居中。没有锚点时整组居中。
        被关掉的页签宽度按 0 算，既不占位也不进 hit-test。"""
        widths = [0.0 if it[0] in self.hidden else max(ICON_W * 0.7, self.w[i].x)
                  for i, it in enumerate(self.items)]
        vis = [i for i, w in enumerate(widths) if w > 0.0]
        right = sum(b.width() + 2 for b in self.right_buttons)
        h = self.height()
        out = [QtCore.QRectF() for _ in self.items]
        if not vis:
            return out
        ax = None
        if self.anchor_fn is not None:
            try:
                ax = self.anchor_fn()
            except Exception:  # noqa: BLE001
                ax = None
        if ax is not None and len(vis) > 1 and self.items[vis[0]][0] == self.anchor_key:
            left = ax - widths[vis[0]] / 2
            end = self.width() - ax + widths[vis[-1]] / 2          # 与主页标签对称
            end = min(end, self.width() - right - 6)
            gap = (end - left - sum(widths[i] for i in vis)) / (len(vis) - 1)
            gap = max(GAP * 0.5, gap)
        else:
            gap = GAP
            tabs = sum(widths[i] for i in vis) + gap * (len(vis) - 1)
            btns = sum(b.width() + 2 for b in self.right_buttons)
            total = tabs + (BTN_GAP + btns if self.right_buttons else 0.0)
            left = (self.width() - total) / 2
        x = max(2.0, left)
        for i in vis:
            out[i] = QtCore.QRectF(x, 2, widths[i], h - 4)
            x += widths[i] + gap
        return out

    def _hit(self, pos: QtCore.QPointF) -> int:
        for i, r in enumerate(self._rects()):
            if r.contains(pos):
                return i
        return -1

    # --- 交互 ---
    def mouseMoveEvent(self, e):
        if self._drag_i >= 0:                     # 页签拖动中：只做重排，不触发悬停 / 拖动本体
            self._drag_to(e.globalPosition().toPoint().x())
            e.accept()
            return
        if self._press_i >= 0 and self._press_g is not None \
                and (e.globalPosition().toPoint() - self._press_g).manhattanLength() > 8:
            self._release_tab_press()             # 等长按前先滑走：这次算普通滑动，不排序
        i = self._hit(e.position())
        if i != self._hover_i:
            if self._hover_i >= 0:
                self.hover[self._hover_i].to(0)
            if i >= 0:
                self.hover[i].to(1)
            self._hover_i = i
            self.setCursor(Qt.CursorShape.PointingHandCursor if i >= 0 else Qt.CursorShape.ArrowCursor)
            self._kick()
        if self._press_pos is not None and (e.position().toPoint() - self._press_pos).manhattanLength() > 4:
            # 在空白处按住并移动 -> 立即拖动灵动岛
            self._press_pos = None
            self.drag_requested.emit(QtGui.QCursor.pos())

    def leaveEvent(self, e):
        if self._hover_i >= 0:
            self.hover[self._hover_i].to(0)
            self._hover_i = -1
            self._kick()

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        i = self._hit(e.position())
        if i >= 0:
            self._press_pos = None
            self._press_i = i
            self._press_g = e.globalPosition().toPoint()
            self._lp_tab.start()                  # 长按后进入排序
        else:
            self._press_i = -1
            self._press_pos = e.position().toPoint()

    def mouseReleaseEvent(self, e):
        self._lp.stop()
        self._lp_tab.stop()
        self._press_pos = None
        self._press_g = None
        if self._drag_i >= 0:                      # 排序结束：落盘由 Island 负责
            moved = self._drag_moved
            i = self._drag_i
            self._drag_moved = False
            self._press_i = -1
            self.hover[i].to(0)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            if moved:
                self.reordered.emit(self.keys())
                self._land()                       # 浮层落回格子 → 落稳后弹一下
                return
            self._drag_i = -1                      # 只长按没挪动：收掉浮层，当作一次单击
            self._cancel_ghost()
            self._press_i = i
        i, self._press_i = self._press_i, -1
        if i >= 0 and e.button() == Qt.MouseButton.LeftButton:
            self.set_current(self.items[i][0], emit=True)

    def _long_press(self):
        if self._press_pos is not None:
            self._press_pos = None
            self.drag_requested.emit(QtGui.QCursor.pos())

    # --- 页签拖动排序 ---
    def _release_tab_press(self):
        self._lp_tab.stop()
        self._press_i = -1
        self._press_g = None

    def _begin_tab_drag(self):
        if self._press_i < 0:
            return
        i = self._press_i
        self._drag_i = i
        self._press_i = -1
        self._drag_moved = False
        self.hover[i].to(1)
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        # 浮层挂在顶层窗口上：导航栏贴着内容区顶边，往上抬会被自己裁掉
        wnd = self.window()
        self._ghost_host = wnd if wnd is not self else (self.parentWidget() or self)
        r = self._rects()[i]
        gl = self.mapTo(self._ghost_host, r.topLeft().toPoint())
        _key, glyph, label = self.items[i]
        self._ghost = _TabGhost(glyph, label, r.width(), self.full_w[i], i == self.index, self._ghost_host)
        self._ghost_gy = gl.y() - _TabGhost.PADY
        self._ghost_cx = gl.x() + r.width() / 2
        self._place_ghost()
        self._ghost.show()
        self._ghost.raise_()
        self._ghost.lift.to(1.0, 300, 0.62)        # 抓起来的瞬间浮起
        self._landing = -1
        self._kick()

    def _place_ghost(self):
        g = self._ghost
        if g is None:
            return
        b = g.body()
        hx = self.mapTo(self._ghost_host, QtCore.QPoint(0, 0)).x()
        lo = hx - _TabGhost.PADX
        hi = hx + self.width() - g.width() + _TabGhost.PADX
        x = clamp(self._ghost_cx - b.width() / 2 - b.x(), lo, max(lo, hi))
        g.move(round(x), round(self._ghost_gy))

    def _ghost_tick(self) -> bool:
        """推进浮层动画；返回 True 表示还要继续刷新。"""
        g = self._ghost
        if g is None:
            return False
        g.lift.step(0.016)
        if self._landing >= 0:                     # 落位：位置也走弹簧
            self._ghost_x.step(0.016)
            self._ghost_y.step(0.016)
            g.move(round(self._ghost_x.x), round(self._ghost_y.x))
            if g.lift.rest and self._ghost_x.rest and self._ghost_y.rest:
                self._finish_landing()
                return False
            return True
        g.update()
        return not g.lift.rest

    def _land(self):
        """松手：浮层落回格子，落稳后由 _finish_landing 弹一下。"""
        g = self._ghost
        if g is None:
            return
        r = self._rects()[self._drag_i]
        gl = self.mapTo(self._ghost_host, r.topLeft().toPoint())
        self._ghost_x.snap(g.x())
        self._ghost_y.snap(g.y())
        self._ghost_x.to(gl.x() - _TabGhost.PADX, 560, 0.62)
        self._ghost_y.to(gl.y() - _TabGhost.PADY, 560, 0.62)
        g.lift.to(0.0, 320, 0.7)
        self._landing = self._drag_i
        self._kick()

    def _finish_landing(self):
        i, self._drag_i, self._landing = self._landing, -1, -1
        if self._ghost is not None:
            self._ghost.hide()
            self._ghost.deleteLater()
        self._ghost, self._ghost_host = None, None
        if 0 <= i < len(self.pops):
            self.pops[i].snap(1.0)                  # 果冻：拉长压扁 → 弹回
            self.pops[i].to(0.0)
        self._kick()

    def _cancel_ghost(self):
        if self._ghost is not None:
            self._ghost.hide()
            self._ghost.deleteLater()
        self._ghost, self._ghost_host = None, None
        self._drag_i = self._landing = -1
        self._kick()

    def _drag_to(self, gx: int):
        if self._drag_i < 0:
            return
        self._ghost_cx = self._ghost_host.mapFromGlobal(QtCore.QPoint(gx, 0)).x() \
            if self._ghost_host is not None else gx
        self._place_ghost()
        target = self._target_index(gx)
        cur = self._drag_i
        if target == cur or target < 0:
            return
        keys = self.keys()
        key = keys[cur]
        order = keys[:]
        order.pop(cur)
        order.insert(target, key)
        self.reorder(order)
        self._drag_i = self.keys().index(key)
        self._drag_moved = True

    def _target_index(self, gx: int) -> int:
        """落在哪个页签上：越过它的中心就插到它前面（和城市胶囊同一套判定）。"""
        rects = self._rects()
        vis = [i for i, it in enumerate(self.items) if it[0] not in self.hidden]
        for i in vis:
            r = rects[i]
            if gx < self.mapToGlobal(QtCore.QPoint(int(r.center().x()), 0)).x():
                return i
        return vis[-1] if vis else self._drag_i

    def wheelEvent(self, e):
        d = -1 if e.angleDelta().y() > 0 else 1
        keys = self.keys()
        vis = [keys.index(k) for k in self.visible_keys()]
        if not vis:
            return
        try:
            cur = vis.index(self.index)
        except ValueError:
            cur = 0
        self.set_current(keys[vis[int(clamp(cur + d, 0, len(vis) - 1))]], emit=True)

    # --- 绘制 ---
    def paintEvent(self, e):
        p = painter(self)
        rects = self._rects()
        p.setPen(Qt.PenStyle.NoPen)
        for i, (key, glyph, label) in enumerate(self.items):
            r = rects[i]
            if r.isEmpty():
                continue                          # 这一页被关掉了
            active = i == self.index
            osc = self.pops[i].x
            placeholder = i == self._drag_i        # 拖动中：原位只留一个淡淡的占位
            p.save()
            if placeholder:
                p.setOpacity(0.3)
            if abs(osc) > 0.004:
                # 果冻：横向拉长 + 纵向压扁，弹回去时反向再来一下
                kx = 1.0 + 0.10 * osc
                ky = 1.0 - 0.07 * osc if osc > 0 else 1.0
                p.translate(r.center())
                p.scale(kx, ky)
                p.translate(-r.center())
            if active:                            # 当前项底块一起被果冻带着走
                if theme.liquid:
                    from .liquid import paint_interactive_chip
                    paint_interactive_chip(p, self, r, r.height() / 2, hover=max(self.hover[i].x, 0.45))
                else:
                    p.setBrush(theme.active_pill())
                    p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
            # 悬停：极淡的圆
            if not active and self.hover[i].x > 0.01:
                c = theme.hover()
                c.setAlphaF(c.alphaF() * self.hover[i].x * 0.8)
                p.setBrush(c)
                p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
            a = 1.0 if active else 0.55 + 0.4 * self.hover[i].x
            p.setFont(icon_font(15))
            p.setPen(theme.pill_text() if active else theme.text(a))
            p.drawText(QtCore.QRectF(r.x(), r.y(), ICON_W, r.height()), Qt.AlignmentFlag.AlignCenter, glyph)
            # 文字：随宽度展开渐显，裁剪在本项矩形内
            extra = self.full_w[i] - ICON_W
            prog = clamp((r.width() - ICON_W) / extra, 0, 1) if extra > 0 else 0
            if prog > 0.02:
                p.save()
                p.setClipRect(r.adjusted(0, 0, -4, 0))
                p.setFont(self.font_)
                p.setPen(theme.pill_text(prog))
                p.drawText(QtCore.QRectF(r.x() + ICON_W - 4, r.y(), extra + 8, r.height()),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
                p.restore()
            n = self.badges.get(key, 0)
            if n:
                p.setBrush(QtGui.QColor("#ff453a"))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QtCore.QPointF(r.x() + ICON_W / 2 + 7, r.y() + 8), 3.2, 3.2)
            p.restore()
