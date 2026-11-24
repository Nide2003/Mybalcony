# -*- coding: utf-8 -*-
"""主题：浅色 / 深色毛玻璃配色、字体、图标码位。auto 模式按身后画面亮度自动切换。"""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

UI_FAMILIES = ["HarmonyOS Sans", "MiSans", "Segoe UI Variable Text", "Microsoft YaHei UI", "Segoe UI"]
NUM_FAMILIES = ["HarmonyOS Sans", "Segoe UI Variable Display", "Segoe UI"]
ICON_FAMILIES = ["Segoe Fluent Icons", "Segoe MDL2 Assets"]
# 液态玻璃：苹方优先，后面的回退族和原 UI / 数字族完全一致（没装苹方时观感不变）。
# ICON_FAMILIES 绝不能加苹方：Segoe Fluent Icons 的 glyph 码位只有图标字体认识。
LIQUID_UI_FAMILIES = ["PingFang SC"] + UI_FAMILIES
LIQUID_NUM_FAMILIES = ["PingFang SC"] + NUM_FAMILIES


class G:
    """Segoe Fluent Icons 码位。"""
    HOME = "\uE80F"
    MESSAGE = "\uE8BD"
    MAIL = "\uE715"
    STOCK = "\uEAFC"
    SUN = "\uE706"
    CLOUD = "\uE753"
    SLIDERS = "\uE9E9"
    WINDOWS = "\uE7C4"
    CPU = "\uE950"
    PULSE = "\uE9D9"
    CLIP = "\uE77F"
    COPY = "\uE8C8"
    TRANSLATE = "\uF2B7"
    VOLUME = "\uE767"
    VOLUME_LOW = "\uE995"
    MUTE = "\uE74F"
    WIFI = "\uE701"
    STREAM = "\uE93E"     # 广播/分享，用作「个人热点」
    PLANE = "\uE709"      # 飞行模式
    BT = "\uE702"
    USB = "\uE88E"
    LOCK = "\uE72E"       # 加密网络的锁
    GLOBE = "\uE774"
    SNIP = "\uE924"
    PLAY = "\uE768"
    PAUSE = "\uE769"
    PREV = "\uE892"
    NEXT = "\uE893"
    PIN = "\uE718"
    UNPIN = "\uE77A"
    CLOSE = "\uE711"
    REFRESH = "\uE72C"
    POWER = "\uE7E8"
    SPEED = "\uEC4A"
    BOLT = "\uE945"
    BATTERY = "\uE83F"
    OPEN = "\uE8A7"
    APPS = "\uECA5"
    GEAR = "\uE713"
    IMAGE = "\uE91B"
    CHECK = "\uE73E"
    BELL = "\uEA8F"
    CHAT = "\uE8F2"
    MUSIC = "\uE8D6"
    MONITOR = "\uE7F4"
    TRASH = "\uE74D"
    UP = "\uE74A"
    DOWN = "\uE74B"
    CHEVRON = "\uE70D"
    ADD = "\uE710"
    POINTER = "\uE8B0"
    EYE = "\uE890"
    EYE_OFF = "\uED1A"
    SEARCH = "\uE721"
    LIVE = "\uE720"   # 麦克风
    CENTER = "\uE8E3"  # 居中对齐（首页「居中显示」按钮）


def ui_font(px: float, weight: QtGui.QFont.Weight = QtGui.QFont.Weight.Normal, num: bool = False) -> QtGui.QFont:
    f = QtGui.QFont()
    # theme 在模块末尾实例化，这里只在**调用时**读取，模块加载期不要调用本函数。
    # 字体在控件构造时就定下：液态玻璃正常启动即苹方，运行中换主题不会重建字体族。
    if theme.liquid:
        f.setFamilies(LIQUID_NUM_FAMILIES if num else LIQUID_UI_FAMILIES)
    else:
        f.setFamilies(NUM_FAMILIES + UI_FAMILIES if num else UI_FAMILIES)
    f.setPixelSize(max(1, round(px)))
    f.setWeight(weight)
    f.setHintingPreference(QtGui.QFont.HintingPreference.PreferNoHinting)
    return f


def icon_font(px: float) -> QtGui.QFont:
    f = QtGui.QFont()
    f.setFamilies(ICON_FAMILIES)
    f.setPixelSize(max(1, round(px)))
    return f


W = QtGui.QFont.Weight


# 每个主题一套色板。文字色 text + 次级 / 弱化透明度 t2 / t3，均按各自玻璃底色单独调过对比度。
PALETTES = {
    "dark": {
        "dark": True, "text": (255, 255, 255), "t2": 0.66, "t3": 0.45,
        "tint": (28, 28, 34, 120), "card": (255, 255, 255, 26), "hover": (255, 255, 255, 30),
        "pill": (255, 255, 255, 52), "track": (255, 255, 255, 34), "fill": (255, 255, 255, 235),
        "on": "#3b82f6", "up": "#ff5a52", "down": "#35c98e",
        "rim1": (255, 255, 255, 60), "rim2": (255, 255, 255, 14), "outline": (0, 0, 0, 70),
        "menu": ("rgba(36,36,40,240)", "white", "rgba(255,255,255,40)"),
    },
    # 浅色：玻璃底做得更"实"（不透出身后的深色），文字更深，保证股票 / 天气等小字可读
    "light": {
        "dark": False, "text": (16, 18, 24), "t2": 0.74, "t3": 0.56,
        "tint": (238, 240, 245, 205), "card": (255, 255, 255, 150), "hover": (0, 0, 0, 14),
        "pill": (255, 255, 255, 250), "track": (0, 0, 0, 30), "fill": (255, 255, 255, 255),
        "on": "#2f6fe0", "up": "#d42c25", "down": "#08875a",
        "rim1": (255, 255, 255, 200), "rim2": (255, 255, 255, 60), "outline": (0, 0, 0, 40),
        "menu": ("rgba(248,248,250,245)", "#14161c", "rgba(0,0,0,18)"),
    },
    # 胭脂撞色：墨黑玻璃 + 胭脂粉 FF7CA2 强调色，正文白色
    "rouge": {
        "dark": True, "text": (255, 255, 255), "t2": 0.70, "t3": 0.50,
        "tint": (0, 0, 0, 205), "card": (255, 255, 255, 24), "hover": (255, 255, 255, 34),
        "pill": (255, 124, 162, 235), "pill_fg": "#000000", "track": (255, 255, 255, 36), "fill": "#FF7CA2",
        "on": "#FF7CA2", "on_fg": "#000000", "up": "#FF7CA2", "down": "#5fe0b0",
        "rim1": (255, 124, 162, 170), "rim2": (255, 124, 162, 40), "outline": (0, 0, 0, 140),
        "menu": ("rgba(8,8,10,245)", "white", "rgba(255,124,162,90)"),
    },
    # 晴空渐变：晴空亮蓝 32ABFD → 柔白浅杏 F7EFE1，正文深海军蓝（两端对比度都足够）
    "sky": {
        "dark": False, "text": (12, 32, 56), "t2": 0.78, "t3": 0.60,
        "tint": (50, 171, 253, 215), "tint2": (247, 239, 225, 230),
        "card": (255, 255, 255, 105), "hover": (255, 255, 255, 120),
        "pill": (255, 255, 255, 190), "track": (12, 32, 56, 34), "fill": (255, 255, 255, 250),
        "on": "#1667c9", "up": "#d42c25", "down": "#06805a",
        "rim1": (255, 255, 255, 210), "rim2": (255, 255, 255, 70), "outline": (12, 32, 56, 60),
        "menu": ("rgba(247,239,225,248)", "#0c2038", "rgba(50,171,253,70)"),
    },
    # 液态玻璃（iOS 风格）：高透明 + 轻磨砂，tint 只铺一层薄霜保证文字可读，壁纸大量透出来
    "liquid-glass": {
        # 正文改纯白（text2/text3 按 t2/t3 倍率继承，同为白色系）；菜单是浅底
        # rgba(246,250,254,240)，菜单文字必须继续用 #0d1219，否则读不清；
        # on_fg / pill_fg 这类"浅底上的前景"也一律不动，只改主题正文文字色。
        "dark": False, "text": (255, 255, 255), "t2": 0.78, "t3": 0.58,
        "tint": (238, 243, 251, 6),
        "card": (248, 250, 254, 42), "hover": (255, 255, 255, 62),
        "pill": (248, 250, 254, 58), "track": (10, 14, 22, 38), "fill": (255, 255, 255, 244),
        "on": "#1668e3", "up": "#d93a2b", "down": "#0a8a5e",
        "rim1": (255, 255, 255, 140), "rim2": (255, 255, 255, 60), "outline": (12, 18, 28, 48),
        "menu": ("rgba(246,250,254,240)", "#0d1219", "rgba(120,170,230,70)"),
        "liquid": True,
        # --- 沉浸光感（HarmonyOS systemMaterialEffect.IMMERSIVE 那套三层合成） ---
        # 材质膜透明度：强 0.85 / 平衡 0.70 / 弱 0.55（对应 HdsTabs 三档）
        "mat": 178, "mat_hover": 204, "mat_weak": 140,
        # 主题色晕染：焦点态 0.08、失活 0.03
        "bloom": (120, 170, 255, 20), "bloom_idle": (120, 170, 255, 8),
        # 顶部反射渐变（0.15 / 0.05 / 0）
        "reflect": (255, 255, 255, 38),
        # 底部微光分割线 0.10
        "hair": (255, 255, 255, 26),
    },
}

THEME_NAMES = [("auto", "跟随背景自动"), ("light", "浅色毛玻璃"), ("dark", "深色毛玻璃"),
               ("liquid-glass", "液态玻璃"), ("rouge", "胭脂撞色"), ("sky", "晴空渐变")]


class Theme(QtCore.QObject):
    changed = QtCore.Signal()

    def __init__(self, mode: str = "auto"):
        super().__init__()
        self.mode = mode
        self._lum = 0.5
        self.pal_name = None
        self._apply(mode if mode in PALETTES else "dark")

    @property
    def lum(self) -> float:
        """身后画面的平滑亮度 0..1（feed_luminance 做过 EMA）。玻璃边缘据此决定
        用"加白刃口"还是"厚度暗侧"定形——纯白背景下白前景与背景 1:1，只有暗侧才可见。"""
        return self._lum

    # --- 自动切换（带滞回，避免在中间亮度来回跳） ---
    def feed_luminance(self, lum: float):
        import time as _t
        self._lum = self._lum * 0.8 + lum * 0.2
        if self.mode != "auto":
            return
        elif self.dark and self._lum > 0.64:
            want = False
        elif not self.dark and self._lum < 0.42:
            want = True
        else:
            want = self.dark
        if want == self.dark:
            self._flip_since = None
            return
        now = _t.monotonic()
        if self.mode == "auto":
            # 身后画面要持续越过阈值 3 秒才切换，滚动的网页之类不会让玻璃来回闪
            if getattr(self, "_flip_since", None) is None:
                self._flip_since = now
                return
            if now - self._flip_since < 3.0:
                return
        self._flip_since = None
        self._apply("dark" if want else "light")

    def set_mode(self, mode: str):
        self.mode = mode
        pal = mode if mode in PALETTES else ("dark" if self.dark else "light")
        self._apply(pal)

    def _apply(self, pal: str):
        changed = pal != getattr(self, "pal_name", None)
        self.pal_name = pal
        self.pal = PALETTES[pal]
        self.dark = self.pal["dark"]
        if changed:
            self.changed.emit()

    # --- 颜色（按当前主题的色板） ---
    def _c(self, key: str, a: float = 1.0) -> QtGui.QColor:
        c = QtGui.QColor(*self.pal[key]) if isinstance(self.pal[key], tuple) else QtGui.QColor(self.pal[key])
        c.setAlphaF(max(0.0, min(1.0, c.alphaF() * a)))
        return c

    def text(self, a: float = 1.0) -> QtGui.QColor:
        return self._c("text", a)

    def text2(self, a: float = 1.0) -> QtGui.QColor:
        return self._c("text", self.pal["t2"] * a)

    def text3(self, a: float = 1.0) -> QtGui.QColor:
        return self._c("text", self.pal["t3"] * a)

    def tint(self) -> QtGui.QColor:
        return self._c("tint")

    def tint_brush(self, rect: QtCore.QRectF) -> QtGui.QBrush:
        """玻璃色调：渐变主题用纵向渐变，其余为纯色。"""
        g2 = self.pal.get("tint2")
        if not g2:
            return QtGui.QBrush(self.tint())
        g = QtGui.QLinearGradient(rect.left(), rect.top(), rect.right() * 0.25 + rect.left() * 0.75, rect.bottom())
        g.setColorAt(0, self._c("tint"))
        g.setColorAt(1, QtGui.QColor(*g2))
        return QtGui.QBrush(g)

    def card(self, a: float = 1.0) -> QtGui.QColor:
        return self._c("card", a)

    def hover(self) -> QtGui.QColor:
        return self._c("hover")

    def active_pill(self) -> QtGui.QColor:
        """导航当前项的圆角底。"""
        return self._c("pill")

    def pill_text(self, a: float = 1.0) -> QtGui.QColor:
        """当前项（亮色底块）上的文字颜色。"""
        fg = self.pal.get("pill_fg")
        if not fg:
            return self.text(a)
        c = QtGui.QColor(fg)
        c.setAlphaF(max(0.0, min(1.0, a)))
        return c

    def track(self) -> QtGui.QColor:
        return self._c("track")

    def fill(self) -> QtGui.QColor:
        """滑块填充。"""
        return self._c("fill")

    @property
    def accent(self) -> QtGui.QColor:
        return self._c("on")

    def on_color(self) -> QtGui.QColor:
        return self._c("on")

    def on_fg(self, a: float = 1.0) -> QtGui.QColor:
        c = QtGui.QColor(self.pal.get("on_fg", "#ffffff"))
        c.setAlphaF(a)
        return c

    def up(self) -> QtGui.QColor:       # A 股习惯：红涨
        return self._c("up")

    def down(self) -> QtGui.QColor:     # 绿跌
        return self._c("down")

    def rim_top(self) -> QtGui.QColor:
        return self._c("rim1")

    def rim_bottom(self) -> QtGui.QColor:
        return self._c("rim2")

    def outline(self) -> QtGui.QColor:
        return self._c("outline")

    def menu_qss(self) -> tuple[str, str, str]:
        return self.pal["menu"]

    def qss_color(self, c: QtGui.QColor) -> str:
        return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"

    def font_css(self) -> str:
        """当前主题正文的 QSS font-family 串；图标字体不走这里（见 icon_font）。"""
        families = LIQUID_UI_FAMILIES if self.liquid else UI_FAMILIES
        return ",".join(f"'{name}'" for name in families)

    # 文字描边入口以实例方法暴露（模块级实现见文件末尾），调用点统一写 theme.outlined_text。
    def outlined_text(self, p, rect, flags, text: str,
                      color: QtGui.QColor | None = None, outline: bool = True,
                      edge: QtGui.QColor | None = None) -> None:
        outlined_text(p, rect, flags, text, color, outline, edge=edge)

    def glass_ink(self, on_light: bool, a: float = 1.0) -> QtGui.QColor:
        """直接压在玻璃上的前景色（图标 glyph / 导航文字）。

        液态玻璃的 tint 几乎全透明，玻璃颜色完全跟着壁纸走：壁纸偏白时白色前景会和
        背景融成一片。亮底（on_light）切深色前景；正文本来就是深色的主题（浅色 /
        晴空）原样返回，不做多余反色。
        """
        if not on_light or self.text().lightness() < 150:
            return self.text(a)
        c = QtGui.QColor(*LIGHT_INK)
        c.setAlphaF(max(0.0, min(1.0, a)))
        return c

    def apply_qss_text_shadow(self, widget) -> None:
        apply_qss_text_shadow(widget)

    @property
    def liquid(self) -> bool:
        """液态玻璃主题：绘制时额外叠一圈折射光 / 色散 / 镜面高光，背景图也做一次提纯。"""
        return bool(self.pal.get("liquid"))


KIND_COLORS = {
    "qq": QtGui.QColor("#12b7f5"),
    "wechat": QtGui.QColor("#07c160"),
    "mail": QtGui.QColor("#ff9f0a"),
    "stock": QtGui.QColor("#ff5a52"),
    "other": QtGui.QColor("#8e8e93"),
}

theme = Theme()


# ---------------------------------------------------------------------------
# 液态玻璃正文描边：所有 QPainter 手绘文字统一走 outlined_text()。
# 非液态主题只有一次 p.drawText()，零额外开销、观感完全不变。
# 液态主题：1 次轻阴影 + 4 次 1px 黑描边 + 1 次正文 = 每处 6 次 drawText
# （歌词 3 行/帧即 18 次，仍是轻量路径；图标 glyph / 浅底前景不调用本函数）。
# ---------------------------------------------------------------------------
LIQUID_STROKE_ALPHA = 208       # 描边黑 alpha（细边不宜全黑，否则小字发糊）
LIQUID_SHADOW_ALPHA = 84        # 阴影黑 alpha
LIQUID_STROKE_PX = 1            # 描边偏移：约 1px
LIQUID_SHADOW_DY = 2            # 阴影下沉：比描边多 1px，才露得出来
LIQUID_QSS_SHADOW_BLUR = 1.0    # QSS 控件投影半径（Qt 无 text-shadow，只能退化成投影）
_STROKE_DIRS = ((-1, 0), (1, 0), (0, -1), (0, 1))

# 亮底反色：液态玻璃的 tint 几乎全透明，玻璃颜色完全跟着壁纸走。壁纸是白的时候，
# 白字黑边会退化成"空心轮廓"——字身与背景 1:1 融成一片，只剩 1px 黑边勾出字形，
# 12.5px 的小字基本读不出来。这类直接压在玻璃上的前景（导航字 / 图标）在亮底改成
# 深字 + 白描边：白描边在浅灰底上把深字从背景里"托"出来，纯白底上自然隐形不碍眼。
LIGHT_INK = (24, 26, 32)        # 亮底前景：深灰近黑，比纯黑柔和，小字不发硬
LIGHT_STROKE_ALPHA = 210        # 亮底描边白 alpha
LIGHT_IN = 0.58                 # 背景亮度高于它 -> 切深字
LIGHT_OUT = 0.46                # 低于它 -> 回白字（滞回带，避免交界处来回闪）


def outlined_text(p: QtGui.QPainter, rect, flags, text: str,
                  color: QtGui.QColor | None = None, outline: bool = True,
                  edge: QtGui.QColor | None = None) -> None:
    """绘制正文文字：非液态直接 drawText；液态加细黑描边 + 轻黑阴影。

    Args:
        p: 目标 QPainter。
        rect: QRectF / QRect 文本布局矩形。
        flags: Qt.AlignmentFlag / Qt.TextFlag 组合（int 亦可）。
        text: 要绘制的文本。
        color: 可选正文色；默认沿用当前 pen —— 这样歌词的渐变扫光笔会被完整保留。
        outline: 浅底前景（pill_text / on_fg）传 False，保持原色不加边。
            液态菜单字现在也要白字黑边（见 liquid._LiquidMenuStyle），走默认的 True。
        edge: 描边（含阴影）的基色，默认黑色 = 白字黑边。亮底反色时传白色：
            深字配白描边才能在浅背景上读出来，且白底上白边自然隐形。亮底阴影
            同时减到 1/3，否则深字下面挂一圈灰，字会发脏。
    """
    if not theme.liquid or not outline:
        p.drawText(rect, flags, text)
        return
    if not text:
        return

    body = p.pen()                       # 完整保存笔：QPen 可带 QBrush 渐变（歌词扫光）
    # 淡字（text2/text3、歌词邻行）等比降低描边强度，避免淡字被黑边压成粗体
    k = 1.0
    if body.brush().style() == QtCore.Qt.BrushStyle.SolidPattern:
        k = 0.35 + 0.65 * max(0.0, min(1.0, body.color().alphaF()))

    light_edge = edge is not None and edge.lightness() > 128
    stroke = QtGui.QColor(edge) if edge is not None else QtGui.QColor(0, 0, 0)

    # 1) 轻阴影：下沉 2px 的半透明黑，位于描边之外
    p.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0,
                                     round(LIQUID_SHADOW_ALPHA * k * (0.34 if light_edge else 1.0)))))
    p.drawText(rect.translated(0, LIQUID_SHADOW_DY), flags, text)

    # 2) 细描边：上下左右各 1px，不画 8 方向以守住每帧重绘的歌词性能
    stroke.setAlpha(round((LIGHT_STROKE_ALPHA if light_edge else LIQUID_STROKE_ALPHA) * k))
    p.setPen(QtGui.QPen(stroke))
    d = LIQUID_STROKE_PX
    for dx, dy in _STROKE_DIRS:
        p.drawText(rect.translated(dx * d, dy * d), flags, text)

    # 3) 正文：恢复原笔（渐变扫光不丢）；显式 color 时只换颜色、保留笔宽与线型
    if color is None:
        p.setPen(body)
    else:
        cp = QtGui.QPen(color)
        cp.setWidthF(body.widthF())
        cp.setStyle(body.style())
        cp.setJoinStyle(body.joinStyle())
        cp.setCapStyle(body.capStyle())
        p.setPen(cp)
    p.drawText(rect, flags, text)


def apply_qss_text_shadow(widget) -> None:
    """QSS 的 color 不支持 text-shadow：液态主题下给标准控件挂一层轻投影。

    退化说明：QLabel / QTextBrowser 等透明控件得到接近文字阴影的效果；
    QLineEdit / QPlainTextEdit 有自身底色，投影落在整框边缘而非单字，
    且 Qt 无法给 QSS 文字加描边（stroke），这是 Qt 样式表的硬限制。
    """
    if widget is None:
        return
    eff = widget.graphicsEffect()
    if not theme.liquid:
        # 切回其它主题时撤掉自己挂的投影（不动调用方原本设置的特效）
        if isinstance(eff, QtWidgets.QGraphicsDropShadowEffect) and eff.property("lg_text_shadow"):
            widget.setGraphicsEffect(None)
        return
    if eff is not None:                  # 不覆盖调用方已有的特效
        return
    shadow = QtWidgets.QGraphicsDropShadowEffect(widget)
    shadow.setProperty("lg_text_shadow", True)
    shadow.setOffset(QtCore.QPointF(0.0, 1.0))
    shadow.setBlurRadius(LIQUID_QSS_SHADOW_BLUR)
    shadow.setColor(QtGui.QColor(0, 0, 0, LIQUID_SHADOW_ALPHA))
    widget.setGraphicsEffect(shadow)
