# -*- coding: utf-8 -*-
"""收起状态的内容（直接画在灵动岛上，不用子控件）。

三种内容，优先级：临时活动 > 正在播放 > 常态（时间 + 天气 + 未读小圆点）。
"""
from __future__ import annotations

import math
import time

from PySide6 import QtCore, QtGui

from .anim import Spring, clamp, ease_out, ease_out_back
from .theme import KIND_COLORS, G, W, icon_font, theme, ui_font
from .widgets import rounded_pixmap
from ..core.config import cfg

Qt = QtCore.Qt
H_IDLE = 34
H_MEDIA = 36
H_ACT = 40
H_SUB = 60          # 实时字幕：上日语、下中文两行
H_LYR = 66          # 收起态多行歌词：上一行 / 当前行 / 下一行
LYR_ROW = 20        # 歌词行距
POP_PX = 5.0        # 换行时整行从下方弹上来的距离（类似 Lyricify 的弹性归位）
SPIN_DEG = 72.0     # 封面唱片转速：度/秒（72 ≈ 5 秒一圈，33⅓ 转的唱片太快会晃眼）
SUB_HOLD_S = 7.0    # 最后一句字幕之后保留多久再回到原来的视图
W_TEXT = 640        # 显示歌词 / 实时字幕时的胶囊宽度（约为普通收起态的 3 倍）
LYR_LEAD = 0.25     # 歌词整体提前量默认值：屏幕合成 + 音频输出延迟大约这么多，提前一点扫才跟得上
LYR_LEAD_MAX = 0.9  # 配置里能调到多大（再大就会"抢拍"）


class PetFace:
    """原创小形象（极简「发光双眼」风格）。

    常态：默认（东张西望）· 好奇（看向哪边那只眼变高）· 困倦（一分钟没人理）· 眨眼 · 惊讶（新消息）。
    鼠标靠近时随机换一种表情（不与上次重复）：
      开心 · 眨眼 · 爱心 · 星星眼 · 害羞 · 嘟嘴 · 眯眼
    s 为缩放（灵动岛上 1.0，主页上更大）。"""

    MOODS = ["happy", "wink", "love", "star", "shy", "pout", "squint"]

    def __init__(self):
        from .anim import Spring
        self.ex = Spring(0, 140, 0.8, 0.01)        # 视线
        self.ey = Spring(0, 140, 0.8, 0.01)
        self.lh = Spring(0, 160, 0.75, 0.003)      # 左眼下眼睑（开心月牙）
        self.rh = Spring(0, 160, 0.75, 0.003)      # 右眼下眼睑
        self.tired = Spring(0, 60, 1.0, 0.003)     # 上眼睑（困倦）
        self.wide = Spring(0, 220, 0.45, 0.003)    # 放大（惊讶 / 星星眼）
        self.morph = Spring(0, 200, 0.7, 0.003)    # 特殊形状（爱心 / 眯眼 / 嘟嘴）出现的程度
        self.blush = Spring(0, 120, 0.9, 0.003)
        self.mood = "default"
        self._last_mood = ""
        self._near = False
        self.blink_at = time.monotonic() + 2.5
        self.last_attention = time.monotonic()
        self.surprise_until = 0.0
        self._t = time.monotonic()
        self.spread = 0.0          # 被按压时两眼额外分开的距离（s=1 时的像素）
        self.tilt = 0.0            # 被按压时每只眼向外倾斜的角度

    # ---------- 事件 ----------
    def react(self, kind: str = "surprise"):
        self.last_attention = time.monotonic()
        if kind == "surprise":
            self.surprise_until = time.monotonic() + 1.4
            self.wide.v += 9.0

    def _pick(self):
        import random
        choices = [m for m in self.MOODS if m != self._last_mood]
        self.mood = random.choice(choices)
        self._last_mood = self.mood

    # ---------- 状态推进 ----------
    def _step(self, look: QtCore.QPointF, near: bool, s: float):
        now = time.monotonic()
        dt = min(0.05, max(0.001, now - self._t))
        self._t = now
        if near and not self._near:
            self._pick()                       # 鼠标刚靠近：随机换表情
        elif not near and self._near:
            self.mood = "default"
        self._near = near
        if near:
            self.last_attention = now
        m = self.mood if near else "default"
        if now < self.surprise_until:
            m = "surprise"
        self._m = m
        # 视线
        if not near and abs(look.x()) > 420 * s:
            tx = math.sin(now * 0.55) * 0.8 + math.sin(now * 1.7) * 0.15
            ty = math.sin(now * 0.37) * 0.35
        else:
            tx = clamp(look.x() / (90.0 * s), -1, 1)
            ty = clamp(look.y() / (60.0 * s), -1, 1)
        if m == "shy":
            tx, ty = tx * 0.3 + 0.5, 0.75          # 害羞：看向斜下方
        self.ex.to(tx)
        self.ey.to(ty)
        self.lh.to({"happy": 1, "laugh": 1, "shy": 0.55, "wink": 1}.get(m, 0) if m != "wink" else 0)
        self.rh.to({"happy": 1, "laugh": 1, "shy": 0.55, "wink": 1}.get(m, 0))
        self.tired.to(0.55 if (now - self.last_attention > 60 and m == "default") else 0.0)
        self.wide.to({"star": 0.3, "surprise": 0.35}.get(m, 0.0))
        self.morph.to(1.0 if m in ("love", "squint", "pout") else 0.0)
        self.blush.to({"shy": 1.0, "love": 0.8, "happy": 0.5, "laugh": 0.6, "wink": 0.5}.get(m, 0.0))
        for sp in (self.ex, self.ey, self.lh, self.rh, self.tired, self.wide, self.morph, self.blush):
            sp.step(dt)
        # 眨眼（特殊表情时不眨）
        dur = 0.16 + 0.18 * self.tired.x
        if now >= self.blink_at + dur:
            gap = 2.4 + (math.sin(now * 12.9898) * 0.5 + 0.5) * 3.2
            self.blink_at = now + gap * (1.6 if self.tired.x > 0.3 else 1.0)
        b = 0.0
        if self.blink_at <= now < self.blink_at + dur and m in ("default", "pout", "shy", "star"):
            b = math.sin((now - self.blink_at) / dur * math.pi)
        return b

    # ---------- 绘制 ----------
    @staticmethod
    def _heart(cx, cy, size) -> QtGui.QPainterPath:
        p = QtGui.QPainterPath()
        w = size
        p.moveTo(cx, cy + w * 0.42)
        p.cubicTo(cx - w * 0.9, cy - w * 0.05, cx - w * 0.45, cy - w * 0.75, cx, cy - w * 0.28)
        p.cubicTo(cx + w * 0.45, cy - w * 0.75, cx + w * 0.9, cy - w * 0.05, cx, cy + w * 0.42)
        p.closeSubpath()
        return p

    @staticmethod
    def _sparkle(cx, cy, r) -> QtGui.QPainterPath:
        p = QtGui.QPainterPath()
        p.moveTo(cx, cy - r)
        p.quadTo(cx, cy, cx + r, cy)
        p.quadTo(cx, cy, cx, cy + r)
        p.quadTo(cx, cy, cx - r, cy)
        p.quadTo(cx, cy, cx, cy - r)
        return p

    def paint(self, p: QtGui.QPainter, cx: float, cy: float, s: float, a: float,
              look: QtCore.QPointF, near: bool):
        b = self._step(look, near, s)
        m = getattr(self, "_m", "default")
        now = time.monotonic()
        tired = clamp(self.tired.x, 0, 1)
        wide = clamp(self.wide.x, -0.3, 1.0)
        morph = clamp(self.morph.x, 0, 1)
        lx, ly = self.ex.x, self.ey.x
        bounce = math.sin(now * 16) * 1.6 * s if m == "laugh" else 0.0
        base_w, base_h, gap = 11.0 * s, 15.0 * s, 15.0 * s
        eye_col = theme.text(0.95 * a)
        glow_col = QtGui.QColor(theme.on_color()) if theme.dark else QtGui.QColor(0, 0, 0, 0)
        pink = QtGui.QColor(255, 92, 138)
        centers = []
        for side in (-1, 1):
            p.save()
            try:
                # 被按压时两只眼睛各自向外倾斜（按在中间时最明显）
                _ex0 = cx + side * (gap / 2 + base_w / 2 + self.spread * s / 2) + self.ex.x * 5.0 * s
                _ey0 = cy + self.ey.x * 3.0 * s
                if abs(self.tilt) > 0.05:
                    p.translate(_ex0, _ey0)
                    p.rotate(side * self.tilt)
                    p.translate(-_ex0, -_ey0)
                hap = clamp(self.lh.x if side < 0 else self.rh.x, 0, 1)
                curious = 1.0 + 0.22 * max(0.0, lx * side)
                w = base_w * (1 + 0.12 * wide) * (1 + 0.25 * b)
                h = base_h * curious * (1 + 0.18 * wide) * (1 - 0.88 * b)
                ex = cx + side * (gap / 2 + base_w / 2 + self.spread * s / 2) + lx * 5.0 * s
                ey = cy + ly * 3.0 * s + bounce
                centers.append((ex, ey))
                r = QtCore.QRectF(ex - w / 2, ey - h / 2, w, max(1.6 * s, h))
                # 光晕
                if glow_col.alpha() and a > 0.05:
                    g = QtGui.QRadialGradient(r.center(), max(r.width(), r.height()) * 0.85)
                    c1 = QtGui.QColor(pink if m == "love" else glow_col)
                    c1.setAlpha(round(85 * a))
                    c2 = QtGui.QColor(c1)
                    c2.setAlpha(0)
                    g.setColorAt(0.0, c1)
                    g.setColorAt(1.0, c2)
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(g)
                    p.drawEllipse(r.center(), r.width() * 0.95, r.height() * 0.75 + 3 * s)
                # 特殊形状：爱心 / 眯眼 ><
                if m == "love" and morph > 0.05:
                    pulse = 1.0 + 0.08 * math.sin(now * 7)
                    p.setPen(Qt.PenStyle.NoPen)
                    hc = QtGui.QColor(pink)
                    hc.setAlphaF(a * morph)
                    p.setBrush(hc)
                    p.drawPath(self._heart(ex, ey, 15 * s * pulse * (0.6 + 0.4 * morph)))
                    continue
                if m == "squint" and morph > 0.05:
                    pen = QtGui.QPen(eye_col, 2.6 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
                    p.setPen(pen)
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    d = -side                               # 左眼 ">"、右眼 "<"
                    k = 5.5 * s * morph
                    path = QtGui.QPainterPath()
                    path.moveTo(ex - d * k, ey - k)
                    path.lineTo(ex + d * k, ey)
                    path.lineTo(ex - d * k, ey + k)
                    p.drawPath(path)
                    continue
                rad = min(w, r.height()) * 0.42
                eye = QtGui.QPainterPath()
                eye.addRoundedRect(r, rad, rad)
                if tired > 0.01:
                    lid = QtGui.QPainterPath()
                    lid.addRect(QtCore.QRectF(r.left() - 2, r.top() - 2, r.width() + 4, 2 + r.height() * 0.5 * tired))
                    eye = eye.subtracted(lid)
                if m == "pout" and morph > 0.05:
                    # 嘟嘴：内侧上眼角斜切出"小眉头"
                    lid = QtGui.QPainterPath()
                    lid.addRect(QtCore.QRectF(-r.width(), -r.height(), r.width() * 2.2, r.height() * 1.0))
                    tr = QtGui.QTransform()
                    tr.translate(r.center().x() - side * r.width() * 0.1, r.top() + r.height() * 0.32 * morph)
                    tr.rotate(side * -24 * morph)
                    eye = eye.subtracted(tr.map(lid))
                if hap > 0.01:
                    cut_r = r.width() * 0.9
                    cc = QtCore.QPointF(r.center().x(), r.bottom() + cut_r - r.height() * 0.62 * hap)
                    lid = QtGui.QPainterPath()
                    lid.addEllipse(cc, cut_r, cut_r)
                    eye = eye.subtracted(lid)
                if not eye.isEmpty():
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(eye_col)
                    p.drawPath(eye)
                if m == "star" and r.height() > 6 * s:
                    sc = QtGui.QColor(20, 20, 26, round(220 * a)) if not theme.dark else QtGui.QColor(30, 30, 40, round(200 * a))
                    p.setBrush(sc)
                    p.drawPath(self._sparkle(ex + 1.4 * s, ey - 2.2 * s, 3.4 * s))
                    p.drawPath(self._sparkle(ex - 2.2 * s, ey + 3.0 * s, 1.6 * s))

            finally:
                p.restore()
        # 腮红
        bl = clamp(self.blush.x, 0, 1)
        if bl > 0.02:
            for (ex, ey), side in zip(centers, (-1, 1)):
                c = QtGui.QColor(255, 124, 162, round(150 * bl * a))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawEllipse(QtCore.QPointF(ex + side * 7.5 * s, ey + base_h * 0.55), 4.4 * s, 2.4 * s)
        # 嘴
        mx = cx + lx * 5.0 * s
        my = cy + base_h * 0.66 + ly * 3.0 * s + bounce
        mc = theme.text(0.9 * a)
        p.setBrush(Qt.BrushStyle.NoBrush)
        pen = QtGui.QPen(mc, 1.8 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        if m in ("happy", "wink", "love", "shy"):
            path = QtGui.QPainterPath()
            mw = 7.0 * s
            path.moveTo(mx - mw / 2, my)
            path.quadTo(mx, my + 4.2 * s, mx + mw / 2, my)
            p.setPen(pen)
            p.drawPath(path)
        elif m == "laugh":
            path = QtGui.QPainterPath()
            mw = 9.0 * s
            path.moveTo(mx - mw / 2, my - 0.5 * s)
            path.quadTo(mx, my + 8.5 * s, mx + mw / 2, my - 0.5 * s)
            path.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(mc)
            p.drawPath(path)
        elif m in ("star", "surprise"):
            p.setPen(pen)
            p.drawEllipse(QtCore.QPointF(mx, my + 1.5 * s), 2.4 * s, 2.8 * s)
        elif m == "pout":
            p.setPen(pen)
            p.drawLine(QtCore.QPointF(mx - 3 * s, my + 1.5 * s), QtCore.QPointF(mx + 3 * s, my + 1.5 * s))
        elif m == "squint":
            path = QtGui.QPainterPath()
            mw = 6.0 * s
            path.moveTo(mx - mw / 2, my)
            path.quadTo(mx, my + 3.5 * s, mx + mw / 2, my)
            p.setPen(pen)
            p.drawPath(path)


class CompactView:
    def __init__(self):
        # 顶栏胶囊的整体缩放：外框尺寸与内部自绘内容等比，展开面板不受影响
        self.ui_scale = clamp(float(cfg.get("island.scale", 1.0) or 1.0), 0.7, 1.3)
        self.media: dict = {}
        self.cover: QtGui.QPixmap | None = None
        self._spin = 0.0                    # 封面唱片的当前角度（连续累积，暂停时停住）
        self._spin_t = time.monotonic()
        self.activity: dict | None = None
        self.badges: dict[str, int] = {}
        self.weather: tuple | None = None   # (glyph, "18°", font_family)
        self.ticker: list[tuple[str, float, float]] = []  # (name, price, pct)
        self._mode = "idle"
        self._mode_t = 0.0
        # 收起态视图（滚轮切换）：clock = 时间天气，pet = 可爱形象，music = 音乐
        self.views = ["clock", "pet", "music"]
        self.view = "clock"
        self._view_t = -10.0
        self.look = QtCore.QPointF(0, 0)      # 光标相对胶囊中心的位置（形象的眼睛会看过去）
        self.near = False                      # 光标在附近（形象开心）
        self.pet = PetFace()
        self._bars = [0.0] * 4
        self._peak = 0.0
        # 歌词（由 app 设置：services.lyrics.Lyrics 或 None）
        self.lyrics = None
        self._lyr_w = 0.0
        self._lyr_h = 0.0
        self._lyr_tr = False        # 这首歌是否有翻译
        self._lyr_idx = -2
        self._lyr_pos = -2.0        # 当前行（可以是小数，换行时平滑滚动）
        # 歌词位置的自走时钟（见 media_pos）：_clk_pos = 推算出的播放位置，_clk_t = 上次推算时刻，
        # _clk_rate = 当前推进速率（用来在偏差小时的"追赶"）
        self._clk_pos: float | None = None
        self._clk_t = 0.0
        self._clk_rate = 1.0
        # 上报样本 (源时刻, 位置)：用来拟合播放器真实的推进速率、并把 ±0.3s 的抖动抹平
        self._smp: list[tuple[float, float]] = []
        self._smp_key = ""
        self._rate_ema = 1.0        # 播放器真实推进速率（EMA 平滑，实测 Apple Music ≈ 0.9955）
        # 歌词提前量：各播放器上报的进度精度不一样，跟不上就往大调，抢拍就往小调
        self._lyr_lead = clamp(float(cfg.get("media.lyric_lead", LYR_LEAD) or LYR_LEAD), 0.0, LYR_LEAD_MAX)
        self._lyr_from = -2.0
        self._lyr_t = 0.0
        self._lyr_cur = ""
        self._pop = Spring(0.0, 330, 0.42)     # 换行时新的一行弹上来的位移
        self._pop_t = time.monotonic()
        # 嵌进 MyDockFinder 顶栏：栏高只有 24px，收起态压成一行，悬停向下展开
        self.bar_mode = False
        self.bar_h = 24.0
        self.bar_open = False
        self._bar = False           # 本帧是否按"栏内单行"绘制
        # 实时字幕（收起态两行：日语 / 中文）
        self.sub_on = False
        self.sub_jp = ""
        self.sub_zh = ""
        self.sub_t = -100.0
        # 收起态音乐视图右侧的播放 / 暂停键（灵动岛坐标，绘制时更新）
        self.play_rect: QtCore.QRectF | None = None
        self.play_hover = 0.0

    # --- 数据 ---
    def set_media(self, m: dict):
        self.media = m or {}

    def set_lyrics(self, lyr):
        """设置当前歌曲的歌词；按最长一行确定胶囊宽度（避免每句都改变宽度）。"""
        self.lyrics = lyr if lyr else None
        self._lyr_idx, self._lyr_pos = -2, -2.0
        self._lyr_from = -2.0
        self._lyr_cur = ""
        self._pop.snap(0.0)
        if not self.lyrics:
            self._lyr_w = 0.0
            self._lyr_h = 0.0
            self._lyr_tr = False
            return
        self._lyr_tr = any(self.lyrics.trans)
        self._lyr_h = H_LYR
        fm = QtGui.QFontMetrics(ui_font(13, W.Medium))
        widest = max((fm.horizontalAdvance(x) for x in self.lyrics.lines), default=0)
        self._lyr_w = clamp(widest + 160, W_TEXT, 760)      # 宽度按整首最长一句固定，不随每句变化

    # --- 上报样本拟合（精度来自这里）---
    SAMP_MAX = 16           # 最多留 16 个样本（约 10s 播放数据）
    SAMP_SPAN = 12.0        # 超过这个时间跨度就丢掉老样本

    def _note_sample(self, t: float, pos: float):
        """记录一条上报的播放位置（t = 这条值对应的"源时刻"）。"""
        s = self._smp
        if s and t - s[-1][0] < 0.05:
            return                                        # 同一秒内的重复读取
        if s:
            dt = t - s[-1][0]
            expect = s[-1][1] + dt
            if abs(pos - expect) > 2.0 or (pos < s[-1][1] - 0.3):
                s.clear()                                 # 拖了进度 / 换歌 / 倒带：历史作废
        s.append((t, pos))
        while len(s) > self.SAMP_MAX or (s and t - s[0][0] > self.SAMP_SPAN):
            s.pop(0)

    def _fit(self, now: float) -> tuple[float, float]:
        """最小二乘拟合 -> (斜率, now 时刻的位置)。

        斜率就是播放器"报出来的 1 秒"对应真实多少秒：实测 Apple Music 约 0.995，
        也就是每分钟会比真时间慢约 0.27 秒，只靠逐次对齐会越听越落后；
        用斜率推进就不会。同时拟合出的位置比单条原始值稳得多（抖动被平均掉）。
        """
        s = self._smp
        if len(s) < 6 or s[-1][0] - s[0][0] < 6.0:
            return 1.0, (s[-1][1] + (now - s[-1][0]) if s else 0.0)
        n = len(s)
        mx = sum(p[0] for p in s) / n
        my = sum(p[1] for p in s) / n
        sxx = sum((p[0] - mx) ** 2 for p in s)
        if sxx < 1e-6:
            return 1.0, s[-1][1]
        slope = sum((p[0] - mx) * (p[1] - my) for p in s) / sxx
        if 0.96 <= slope <= 1.04:
            # 速率本身变化极慢，用 EMA 压掉单窗口噪声（否则窗口短时斜率能差 ±2%）
            self._rate_ema = self._rate_ema * 0.82 + slope * 0.18
        slope = clamp(self._rate_ema, 0.96, 1.04)
        at_now = my + slope * (now - mx)
        return slope, at_now

    def media_pos(self) -> float:
        """歌词用的播放位置：用自己的连续时钟推进，再向"拟合出来的"上报位置收敛。

        Apple Music（走 SMTC）实测：位置严格量化到整秒，相邻两次上报抖动可达 ±0.3s，
        而且它自己的秒比真实时间慢约 0.5%（连续听几分钟就会落后小半秒）。所以：
          - 每来一条上报都进样本池，用最小二乘同时估出"真实位置"和"推进速率"；
          - 时钟按估出的速率推进（不是 1.0），长时间听也不会越走越慢；
          - 偏差用拟合值收敛而不是单条原始值，避免被 ±0.3s 的抖动带着抖；
          - 偏差大（拖进度、换歌）直接对齐。
        最后统一加一个提前量抵消屏幕合成 + 音频输出延迟（播放器管线延迟是常数，一次调好即可）。
        """
        m = self.media
        dur = float(m.get("duration") or 0)
        raw = float(m.get("position") or 0)
        now = time.monotonic()
        if not m.get("playing"):
            self._clk_pos = None                  # 暂停：下次从上报值重新起跳
            self._smp = []
            self._smp_key = ""
            return min(raw, dur) if dur > 0 else raw
        stamp = float(m.get("stamp") or now)
        key = (m.get("title") or "") + "|" + (m.get("song_id") or "")
        if key != self._smp_key:
            self._smp_key, self._smp = key, []     # 换歌：样本作废
            self._clk_pos = None
        self._note_sample(stamp, raw)
        rate, target = self._fit(now)
        if self._clk_pos is None:
            self._clk_pos, self._clk_t, self._clk_rate = target, now, rate
        else:
            dt = min(0.12, max(0.0, now - self._clk_t))
            self._clk_t = now
            self._clk_pos += dt * self._clk_rate
            err = target - self._clk_pos
            if abs(err) > 1.2:
                self._clk_pos, self._clk_rate = target, rate     # 跳变：直接对齐
            else:
                self._clk_rate = clamp(rate + err * 0.6, rate - 0.18, rate + 0.18)
        pos = self._clk_pos + self._lyr_lead
        return min(pos, dur) if dur > 0 else pos

    def lyric_now(self) -> tuple[int, str, str]:
        """-> (行号, 歌词, 翻译)；没有歌词 / 没在播放时行号为 -1。"""
        if not self.lyrics or not self.media.get("title"):
            return -1, "", ""
        return self.lyrics.at(self.media_pos())

    # --- 实时字幕 ---
    def set_sub_running(self, on: bool):
        self.sub_on = bool(on)
        if not on:
            self.sub_jp = self.sub_zh = ""
            self.sub_t = -100.0

    def set_sub(self, jp: str | None = None, zh: str | None = None):
        if jp is not None:
            self.sub_jp = jp
        if zh is not None:
            self.sub_zh = zh
        self.sub_t = time.monotonic()

    def sub_active(self) -> bool:
        return self.sub_on and bool(self.sub_jp or self.sub_zh) and time.monotonic() - self.sub_t < SUB_HOLD_S

    def set_cover(self, img):
        # 存成圆形大图：绘制时按需缩放并旋转（黑胶唱片），比每帧裁圆便宜
        self.cover = rounded_pixmap(img, 64, 32) if img is not None else None
        self._spin_t = time.monotonic()

    def show_activity(self, act: dict, duration: float = 2.4):
        a = dict(act)
        a["until"] = time.monotonic() + duration
        a["start"] = time.monotonic()
        self.activity = a

    def update_activity(self, **kw):
        """原地更新（例如连续调音量时不重新入场）。"""
        if self.activity:
            self.activity.update(kw)

    def set_view(self, v: str):
        if v in self.views:
            self.view = v

    def cycle_view(self, d: int):
        i = self.views.index(self.view) if self.view in self.views else 0
        self.view = self.views[(i + (1 if d < 0 else -1)) % len(self.views)]
        self._view_t = time.monotonic()
        return self.view

    def playing(self) -> bool:
        return bool(self.media.get("has_session") and self.media.get("playing") and self.media.get("title"))

    def mode(self) -> str:
        now = time.monotonic()
        if self.activity and now < self.activity["until"]:
            m = "activity"
        elif self.sub_active():
            m = "subtitle"            # 有人在说话时字幕优先；安静几秒后回到原视图（音乐 / 时间 / 小形象）
            self.activity = None
        else:
            self.activity = None
            m = {"music": "media", "pet": "pet"}.get(self.view, "idle")
        if m != self._mode:
            self._mode = m
            self._mode_t = now
        return m

    def busy(self) -> bool:
        """是否需要持续动画帧。"""
        return self.mode() in ("media", "activity", "pet", "subtitle") or time.monotonic() - self._view_t < 1.4

    # --- 尺寸 ---
    def size_hint(self) -> tuple[float, float]:
        w, h = self._size_hint()
        # 贴着顶栏：收起时压到栏高，悬停时向下展开成三行歌词
        if self.bar_mode and not self.bar_open and self.mode() in ("idle", "media", "pet"):
            h = max(20.0, self.bar_h - 2.0)
            if self.mode() == "media" and self.media.get("title"):
                w = self._bar_width()          # 宽度跟着当前这句歌词走
        elif self.bar_mode and self.bar_open and self.mode() == "media":
            # 展开时也贴着这三行歌词：不用整首最长一句（至少 W_TEXT=640）把左右撑出大片留白
            w = self._bar_open_width()
        s = self.ui_scale
        return w * s, h * s

    def _bar_open_width(self) -> float:
        """栏内悬停展开：宽度 = 当前显示三行里最长一句 + 封面/播放键/律动条/徽标的占位。

        收起态用单行宽度，展开态如果沿用 _size_hint() 的固定 640+ 会几乎撑满顶栏，
        歌词却在中间居中小小一段，左右各空一大片。这里改成跟着这三行走。
        """
        idx, line, tr = self.lyric_now()
        fm_cur = QtGui.QFontMetrics(ui_font(13, W.Medium))
        fm_sub = QtGui.QFontMetrics(ui_font(11.5, W.Normal))
        fm_tr = QtGui.QFontMetrics(ui_font(11, W.Normal))
        widths: list[float] = []
        if self.lyrics is not None and idx >= 0:
            lines = self.lyrics.lines
            for slot in (-1, 0, 1):
                n = idx + slot
                if 0 <= n < len(lines) and lines[n]:
                    widths.append((fm_cur if slot == 0 else fm_sub).horizontalAdvance(lines[n]))
            if tr:
                widths.append(fm_tr.horizontalAdvance(tr))
        if not widths:
            title = self.media.get("title", "")
            artist = self.media.get("artist", "")
            text = line or (f"{title}  ·  {artist}" if artist else title)
            widths.append(fm_cur.horizontalAdvance(text))
        text_w = max(widths)
        nb = sum(1 for v in self.badges.values() if v)
        # _paint_media 里：tx = left+44；右端徽标/播放键/律动条/展开键约 86+13nb，合计 ≈130+13nb；
        # 再多留 16 让歌词居中时不贴边、也不会被 elide。
        return clamp(text_w + 146 + 13 * nb, 210.0, 760.0)

    def _bar_width(self) -> float:
        """栏内单行版：胶囊长度 = 这一句歌词的长度 + 封面与播放键的位置。"""
        idx, line, _tr = self.lyric_now()
        if line:
            text = line
        else:
            title = self.media.get("title", "")
            artist = self.media.get("artist", "")
            text = f"{title}  ·  {artist}" if artist else title
        if not text:
            return 190.0
        fm = QtGui.QFontMetrics(ui_font(11.5, W.Medium))
        nb = sum(1 for v in self.badges.values() if v) * 12
        return clamp(fm.horizontalAdvance(text) + 76 + nb, 200.0, 1200.0)

    def _size_hint(self) -> tuple[float, float]:
        m = self.mode()
        nb = sum(1 for v in self.badges.values() if v)
        if m == "activity":
            a = self.activity
            t = a.get("type")
            if t in ("volume", "brightness"):
                return 280, H_ACT
            fm = QtGui.QFontMetrics(ui_font(13, W.DemiBold))
            w = 70 + fm.horizontalAdvance(a.get("title", "")) + QtGui.QFontMetrics(ui_font(12)).horizontalAdvance(a.get("sub", ""))
            return clamp(w + 24, 220, 460), H_ACT
        if m == "subtitle":
            return W_TEXT + nb * 12, H_SUB                        # 固定宽度：说话时不会一直伸缩
        if m == "media":
            if not self.playing() and not self.media.get("title"):
                return 190 + nb * 12, H_MEDIA
            h = self._lyr_h if self.lyrics is not None else H_MEDIA
            return max(300, self._lyr_w) + 34 + nb * 12, h
        if m == "pet":
            return 150 + nb * 14, H_IDLE
        w = 150 + (64 if self.weather else 0) + nb * 14
        return w, H_IDLE

    # --- 绘制 ---
    def paint(self, p: QtGui.QPainter, r: QtCore.QRectF, alpha: float, peak: float):
        if alpha <= 0.01 or r.width() < 40:
            return
        m = self.mode()
        fade = ease_out((time.monotonic() - self._mode_t) / 0.28)
        a = alpha * fade
        # 上游（Island._pk）已经做过 attack/release 包络与自动增益，这里只做
        # 极轻的下落保持，避免二次低通把峰值削平（那正是"跳不高"的原因之一）。
        self._peak = max(peak, self._peak * 0.9)
        self._bar = self.bar_mode and not self.bar_open
        p.save()
        p.setClipRect(r.adjusted(6, 0, -6, 0), Qt.ClipOperation.IntersectClip)
        if m != "media":
            self.play_rect = None
        if m == "activity":
            self._paint_activity(p, r, a)
        elif m == "subtitle":
            self._paint_subtitle(p, r, a)
        elif m == "media":
            if not self.media.get("title"):
                self._paint_no_media(p, r, a)
            elif self._bar:
                self._paint_media_bar(p, r, a)
            else:
                self._paint_media(p, r, a)
        elif m == "pet":
            self._paint_pet(p, r, a)
        else:
            self._paint_idle(p, r, a)
        p.restore()
        if m != "activity":
            self._paint_dots(p, r, alpha)

    def _paint_dots(self, p, r, alpha):
        """（已关闭）切换视图时不显示页码小圆点。"""
        return
        k = time.monotonic() - self._view_t
        if k > 1.4:
            return
        a = alpha * (1.0 if k < 0.9 else max(0.0, 1 - (k - 0.9) / 0.5))
        n = len(self.views)
        cx = r.center().x()
        y = r.bottom() - 4.5 if r.height() > 30 else r.bottom() - 3
        for i, v in enumerate(self.views):
            on = v == self.view
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.text((0.9 if on else 0.3) * a))
            w = 9 if on else 3.4
            x = cx + (i - (n - 1) / 2) * 9
            p.drawRoundedRect(QtCore.QRectF(x - w / 2, y - 1.7, w, 3.4), 1.7, 1.7)

    def _paint_subtitle(self, p, r, a):
        """两行字幕：上面日语（小字，较淡），下面中文（大字）；太长时保留结尾（最新的话）。"""
        x = r.x() + 18
        w = r.width() - 36 - (self._badges_w() if any(self.badges.values()) else 0)
        if any(self.badges.values()):
            self._badges(p, r.right() - 14, r.y() + 16, a)
        cy = r.center().y()
        fj, fz = ui_font(12), ui_font(15, W.DemiBold)
        fmj, fmz = QtGui.QFontMetrics(fj), QtGui.QFontMetrics(fz)

        def tail(fm, text):
            text = " ".join((text or "").split())
            if fm.horizontalAdvance(text) <= w:
                return text
            return fm.elidedText(text, Qt.TextElideMode.ElideLeft, int(w))
        jp = tail(fmj, self.sub_jp)
        zh = tail(fmz, self.sub_zh) or "…"
        top = QtCore.QRectF(x, cy - 22, w, 18)
        bot = QtCore.QRectF(x, cy - 3, w, 24)
        p.setFont(fj)
        p.setPen(theme.text(0.62 * a))
        theme.outlined_text(p, top, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, jp)
        p.setFont(fz)
        p.setPen(theme.text(a))
        theme.outlined_text(p, bot, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, zh)

    def _badges_w(self) -> float:
        return 12 + 12 * sum(1 for v in self.badges.values() if v)

    def _paint_no_media(self, p, r, a):
        cy = r.center().y()
        p.setFont(icon_font(14))
        p.setPen(theme.text(0.75 * a))
        p.drawText(QtCore.QRectF(r.x() + 16, r.y(), 22, r.height()), Qt.AlignmentFlag.AlignCenter, G.MUSIC)
        p.setFont(ui_font(13, W.Medium))
        p.setPen(theme.text2(a))
        theme.outlined_text(p, QtCore.QRectF(r.x() + 46, r.y(), r.width() - 60, r.height()),
                   Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, "未在播放")
        _ = cy

    def _paint_pet(self, p, r, a):
        cx, cy = r.center().x(), r.center().y()
        sx, sy = getattr(self, "squash", (1.0, 1.0))
        amount, rel = getattr(self, "press", (0.0, 0.0))
        amount = clamp(amount, 0.0, 1.2)
        side_w = abs(rel)                     # 0 = 按在中间，1 = 按在一端
        lean = -rel * min(1.0, amount * 1.6)   # 向没被按的一侧倾斜
        self.pet.spread = amount * (1 - side_w) * 9.0
        self.pet.tilt = amount * (1 - side_w) * 14.0
        p.save()
        p.translate(cx, cy)
        p.translate(lean * 24.0, 0)            # 明显地偏向没被按的一侧
        p.rotate(lean * 18.0)
        p.scale(sx, sy)                       # 灵动岛被按压时表情一起被压扁
        p.translate(-cx, -cy)
        self.pet.paint(p, cx, cy - 1, 1.0, a, self.look, self.near)
        p.restore()
        x = r.right() - 14
        self._badges(p, x, cy, a)

    def _badges(self, p, right: float, cy: float, a: float) -> float:
        x = right
        for kind in ("mail", "wechat", "qq"):
            if self.badges.get(kind):
                c = QtGui.QColor(KIND_COLORS.get(kind, KIND_COLORS["other"]))
                c.setAlphaF(a)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawEllipse(QtCore.QPointF(x - 4, cy), 4, 4)
                x -= 13
        return x

    def _paint_idle(self, p, r, a):
        cy = r.center().y()
        now = time.localtime()
        p.setFont(ui_font(15, W.DemiBold, num=True))
        p.setPen(theme.text(a))
        txt = time.strftime("%H:%M", now)
        theme.outlined_text(p, QtCore.QRectF(r.x() + 18, r.y(), 80, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, txt)
        x = r.right() - 16
        x = self._badges(p, x, cy, a) - 4
        if self.weather:
            glyph, temp = self.weather[0], self.weather[1]
            fam = self.weather[2] if len(self.weather) > 2 else None
            p.setFont(ui_font(13, W.Medium, num=True))
            p.setPen(theme.text2(a))
            fm = QtGui.QFontMetrics(p.font())
            tw = fm.horizontalAdvance(temp)
            theme.outlined_text(p, QtCore.QRectF(x - tw, r.y(), tw + 2, r.height()), Qt.AlignmentFlag.AlignVCenter, temp)
            f = icon_font(13)
            if fam:
                f.setFamilies([fam, "Segoe Fluent Icons", "Segoe UI Symbol"])
            p.setFont(f)
            p.drawText(QtCore.QRectF(x - tw - 22, r.y(), 20, r.height()), Qt.AlignmentFlag.AlignCenter, glyph)

    def _disc_angle(self) -> float:
        """黑胶转速：播放时匀速转，暂停就停在原处（不回零）。"""
        now = time.monotonic()
        dt = min(0.12, max(0.0, now - self._spin_t))
        self._spin_t = now
        if self.playing():
            self._spin = (self._spin + dt * SPIN_DEG) % 360.0
        return self._spin

    def _draw_disc(self, p, rect, a, icon: bool = False):
        """把封面画成一张转着的黑胶唱片：圆形裁切 + 盘面细边 + 中心孔。"""
        c = rect.center()
        rad = rect.width() / 2.0
        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        clip = QtGui.QPainterPath()
        clip.addEllipse(rect)
        p.setClipPath(clip)
        if self.cover is not None:
            p.translate(c)
            p.rotate(self._disc_angle())
            p.drawPixmap(QtCore.QRectF(-rad, -rad, rad * 2, rad * 2),
                         self.cover, QtCore.QRectF(self.cover.rect()))
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.card(1.4))
            p.drawEllipse(rect)
            if icon:
                p.setFont(icon_font(max(9.0, rad * 1.15)))
                p.setPen(theme.text(a * 0.8))
                p.drawText(rect, Qt.AlignmentFlag.AlignCenter, G.MUSIC)
        p.restore()
        # 盘面细边：让圆片边界清楚，转起来不会糊成一团
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QtGui.QPen(theme.text(a * 0.22), 1.0))
        p.drawEllipse(rect.adjusted(0.5, 0.5, -0.5, -0.5))
        if rad >= 7:                        # 再小就画不出孔了，会像脏点
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.text(a * 0.42))
            h = max(1.4, rad * 0.19)
            p.drawEllipse(c, h, h)

    def _paint_media_bar(self, p, r, a):
        """顶栏里的一行版：小封面（转着的唱片）+ 当前一句歌词 + 一个播放键。"""
        cy = r.center().y()
        d = 16.0
        cr = QtCore.QRectF(r.x() + 8, cy - d / 2, d, d)
        p.setOpacity(a)
        self._draw_disc(p, cr, a)
        p.setOpacity(1.0)
        pr = QtCore.QRectF(r.right() - 24, cy - 8, 16, 16)
        self.play_rect = pr
        p.setFont(icon_font(11))
        p.setPen(theme.text(a * 0.9))
        p.drawText(pr, Qt.AlignmentFlag.AlignCenter, G.PAUSE if self.media.get("playing") else G.PLAY)
        tx = cr.right() + 8
        tw = pr.left() - 8 - tx
        idx, line, _tr = self.lyric_now()
        self._lyric_step(idx)
        self._lyr_pos = float(idx) if idx >= 0 else -2.0
        if line:
            text = line
        else:
            title = self.media.get("title", "")
            artist = self.media.get("artist", "")
            text = f"{title}  ·  {artist}" if artist else title
        p.setFont(ui_font(11.5, W.Medium))
        fm = QtGui.QFontMetrics(p.font())
        shown = fm.elidedText(text, Qt.TextElideMode.ElideRight, int(tw))
        if line:
            half = fm.horizontalAdvance(shown) / 2.0
            p.setPen(self._sweep_pen(a, tx + tw / 2 - half, tx + tw / 2 + half, self._lyr_progress(idx)))
        else:
            p.setPen(theme.text(a))
        theme.outlined_text(p, QtCore.QRectF(tx, r.y() + self._pop_step(), tw, r.height()),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, shown)

    def _paint_media(self, p, r, a):
        cy = r.center().y()
        x = r.x() + 6
        cr = QtCore.QRectF(x + 2, cy - 13, 26, 26)
        p.setOpacity(a)
        self._draw_disc(p, cr, a, icon=True)
        p.setOpacity(1.0)
        # 最右侧：播放 / 暂停键（收起时也能直接点）；左边是音频律动条（跟随系统输出峰值）
        right = self._badges(p, r.right() - 14, cy, a) - 4 if any(self.badges.values()) else r.right() - 8
        pr = QtCore.QRectF(right - 28, cy - 14, 28, 28)
        self.play_rect = pr
        hov = self.play_hover
        if hov > 0.01:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.hover() if hasattr(theme, "hover") else theme.card(1.2))
            p.setOpacity(a * hov)
            p.drawEllipse(pr.adjusted(1, 1, -1, -1))
            p.setOpacity(1.0)
        p.setFont(icon_font(14))
        p.setPen(theme.text(a))
        p.drawText(pr, Qt.AlignmentFlag.AlignCenter, G.PAUSE if self.media.get("playing") else G.PLAY)
        bars_w = 26
        bx = pr.left() - 6 - bars_w
        t = time.monotonic()
        pk = clamp(self._peak, 0, 1)
        for i in range(4):
            target = 0.14 + pk * (0.52 + 0.48 * math.sin(t * (7.3 + i * 2.1) + i * 1.7) ** 2)
            self._bars[i] += (target - self._bars[i]) * 0.4
            h = 3 + 17 * clamp(self._bars[i], 0, 1)
            br = QtCore.QRectF(bx + i * 7, cy - h / 2, 3.6, h)
            c = theme.text(0.85 * a)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(br, 1.8, 1.8)
        # 中间：歌词（多行滚动）或 标题 · 歌手（过长时横向滚动）
        tx = cr.right() + 10
        tw = bx - 10 - tx
        idx, line, tr = self.lyric_now()
        self._lyr_cur = line
        if self.lyrics is not None and idx >= 0:
            self._paint_lyrics(p, tx, tw, r, a, idx, tr)
            return
        title = self.media.get("title", "")
        artist = self.media.get("artist", "")
        self._paint_marquee(p, tx, tw, r, a, f"{title}  ·  {artist}" if artist else title)

    def _lyric_step(self, idx: int) -> float:
        """换行时把 _lyr_pos 从上一行滑到当前行，返回 0..1 的进度。"""
        now = time.monotonic()
        if idx != self._lyr_idx:
            if self._lyr_idx != -2 and abs(idx - self._lyr_idx) <= 2:
                self._pop.snap(POP_PX)          # 新的一行：从下方弹上来
                self._pop.to(0.0, 330, 0.42)    # 欠阻尼，会过冲并回弹一下
            self._lyr_from = self._lyr_pos if self._lyr_idx != -2 else float(idx)
            self._lyr_idx, self._lyr_t = idx, now
        span = abs(float(idx) - self._lyr_from)
        # 正常换行：带一点过冲地"跳"到位；拖动进度条一次跳很多行时不做回弹，免得甩得厉害
        u = (now - self._lyr_t) / (0.42 if span <= 2 else 0.3)
        return ease_out_back(u) if span <= 2 else ease_out(u)

    def _pop_step(self) -> float:
        """弹跳位移，按实际帧间隔推进弹簧。"""
        now = time.monotonic()
        dt = min(0.05, max(0.001, now - self._pop_t))
        self._pop_t = now
        self._pop.step(dt)
        return self._pop.x

    def _lyr_progress(self, idx: int) -> float:
        """这一句唱到哪儿了（0..1）：扫光的分界线跟着音轨走。"""
        if not self.lyrics or idx < 0:
            return 1.0
        return self.lyrics.progress(idx, self.media_pos())

    def _sweep_pen(self, a: float, x0: float, x1: float, p: float) -> QtGui.QPen:
        """当前行的笔：唱过的部分实、没唱的部分淡，分界线跟着音轨往前走。
        渐变坐标必须是绝对坐标，所以按文字实际左右边界传进来。"""
        p = clamp(p, 0.0, 1.0)
        soft = 0.05
        head = theme.text(a)
        tail = theme.text(a * 0.38)
        g = QtGui.QLinearGradient(x0, 0.0, max(x0 + 1.0, x1), 0.0)
        g.setColorAt(0.0, head)
        g.setColorAt(max(0.0, p - soft), head)
        g.setColorAt(min(1.0, p + soft), tail)
        g.setColorAt(1.0, tail)
        return QtGui.QPen(QtGui.QBrush(g), 1.0)

    def _paint_lyrics(self, p, tx, tw, r, a, idx, tr):
        """收起态多行歌词：上一行 / 当前行 / 下一行，换行时整块平滑上移（类似 Lyricify 的滚动）。

        当前行有翻译时，用翻译占住下一行的位置——不然两行挤在 20px 的行距里会叠字。
        """
        lines = self.lyrics.lines
        k = self._lyric_step(idx)
        self._lyr_pos = self._lyr_from + (float(idx) - self._lyr_from) * k
        dpos = self._lyr_pos - float(idx)          # 换行时从 -1 滑到 0
        cy = r.center().y()
        p.save()
        p.setClipRect(QtCore.QRectF(tx - 4, r.y() + 2, tw + 8, r.height() - 4))
        bob = self._pop_step()
        for slot in (-1, 0, 1):
            y = cy + (slot - dpos) * LYR_ROW + bob
            if abs(slot - dpos) > 1.75:
                continue
            if slot == 1 and tr:
                text, px, al = tr, 11.0, 0.5 * a
            else:
                n = idx + slot
                if n < 0 or n >= len(lines) or not lines[n]:
                    continue
                text = lines[n]
                px = 13 if slot == 0 else 11.5
                al = a if slot == 0 else 0.42 * a
            fade = clamp(1.0 - abs(slot - dpos) * 0.35, 0.0, 1.0)
            if al * fade <= 0.02:
                continue
            p.setFont(ui_font(px, W.Medium if slot == 0 else W.Normal))
            fm = QtGui.QFontMetrics(p.font())
            shown = fm.elidedText(text, Qt.TextElideMode.ElideRight, int(tw))
            if slot == 0:
                half = fm.horizontalAdvance(shown) / 2.0
                p.setPen(self._sweep_pen(al * fade, tx + tw / 2 - half, tx + tw / 2 + half,
                                         self._lyr_progress(idx)))
            else:
                p.setPen(theme.text(al * fade))
            theme.outlined_text(p, QtCore.QRectF(tx, y - LYR_ROW / 2.0, tw, LYR_ROW),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, shown)
        p.restore()

    def _paint_marquee(self, p, tx, tw, r, a, text):
        """没有歌词时显示「标题 · 歌手」，过长时来回滚动。"""
        p.setFont(ui_font(13, W.Medium))
        fm = QtGui.QFontMetrics(p.font())
        full = fm.horizontalAdvance(text)
        p.save()
        p.setClipRect(QtCore.QRectF(tx, r.y(), tw, r.height()))
        p.setPen(theme.text(a))
        if full <= tw:
            theme.outlined_text(p, QtCore.QRectF(tx, r.y(), tw, r.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        else:
            gap = 40
            period = (full + gap) / 34.0      # 34 px/s
            ph = time.monotonic() % (period + 2.0)
            off = 0 if ph < 2.0 else (ph - 2.0) * 34.0
            for k in (0, 1):
                theme.outlined_text(p, QtCore.QRectF(tx - off + k * (full + gap), r.y(), full + 4, r.height()),
                           Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        p.restore()

    def _paint_activity(self, p, r, a):
        act = self.activity or {}
        cy = r.center().y()
        t = act.get("type")
        enter = ease_out((time.monotonic() - act.get("start", 0)) / 0.35)
        color = act.get("color")
        # 左侧图标圆
        d = 26
        cr = QtCore.QRectF(r.x() + 9, cy - d / 2, d, d)
        if color is not None:
            c = QtGui.QColor(color)
            c.setAlphaF(a)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawEllipse(cr)
            p.setPen(QtGui.QColor(255, 255, 255, round(255 * a)))
        else:
            p.setPen(theme.text(a))
        img = act.get("icon")
        if isinstance(img, QtGui.QPixmap):
            p.setOpacity(a)
            p.drawPixmap(cr.toRect(), img)
            p.setOpacity(1)
        else:
            p.setFont(icon_font(13 if color is not None else 16))
            p.drawText(cr, Qt.AlignmentFlag.AlignCenter, act.get("glyph", G.BELL))
        x = cr.right() + 10
        if t in ("volume", "brightness"):
            v = clamp(act.get("value", 0.0), 0, 1)
            bw = r.right() - 52 - x
            track = QtCore.QRectF(x, cy - 3, bw, 6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.track())
            p.drawRoundedRect(track, 3, 3)
            p.setBrush(theme.text(a))
            p.drawRoundedRect(QtCore.QRectF(x, cy - 3, max(6, bw * v * enter), 6), 3, 3)
            p.setFont(ui_font(12.5, W.DemiBold, num=True))
            p.setPen(theme.text(a))
            theme.outlined_text(p, QtCore.QRectF(r.right() - 48, r.y(), 34, r.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       "静音" if act.get("muted") else f"{round(v * 100)}")
            return
        title = act.get("title", "")
        sub = act.get("sub", "")
        p.setFont(ui_font(13, W.DemiBold))
        fm = QtGui.QFontMetrics(p.font())
        tw = fm.horizontalAdvance(title)
        avail = r.right() - 14 - x
        tc = act.get("title_color")
        p.setPen(QtGui.QColor(tc) if tc else theme.text(a))
        theme.outlined_text(p, QtCore.QRectF(x, r.y(), min(tw + 2, avail), r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   fm.elidedText(title, Qt.TextElideMode.ElideRight, int(avail)))
        if sub and tw + 10 < avail:
            p.setFont(ui_font(12))
            fm2 = QtGui.QFontMetrics(p.font())
            sc = act.get("sub_color")
            p.setPen(QtGui.QColor(sc) if sc else theme.text2(a))
            sw = avail - tw - 10
            theme.outlined_text(p, QtCore.QRectF(x + tw + 10, r.y(), sw, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       fm2.elidedText(sub, Qt.TextElideMode.ElideRight, int(sw)))

