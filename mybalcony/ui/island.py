# -*- coding: utf-8 -*-
"""灵动岛主窗口。

几何有三种模式：
- anchored：吸附在某条屏幕边上，贴边一侧与屏幕边缘通过两侧"表面张力"内凹圆角相连；
- drag：长按后跟随鼠标（弹簧跟随产生拖拽惯性），本体按速度变成泪滴形；
         离开原边缘时液桥被拉长、变细，超过阈值后断开，边缘残留的小水滴缩回；
         靠近任意边缘时会重新"伸出"液桥；
- snap：松手后吸附到最近的边，垂直方向欠阻尼弹簧带回弹，冲过边缘时转化为挤压形变。

窗口本身是固定大小的透明分层窗口，跟着本体移动；透明区域不接收鼠标。
毛玻璃 = 截取身后画面（本窗口已排除在截图之外）-> 缩小模糊 -> 纹理画刷填充形状。
"""
from __future__ import annotations

import ctypes
import math
import time
from ctypes import wintypes

from PySide6 import QtCore, QtGui, QtWidgets

from ..core.config import cfg
from .anim import Spring, clamp, lerp, smooth
from .compact import CompactView
from .glass import (Backdrop, exclude_from_capture, grab_tiny, set_acrylic,
                    _downscale, _set_window_pos, SWP_NOMOVE, SWP_NOSIZE, SWP_NOZORDER, SWP_NOACTIVATE)
from .nav import NavBar
from .shape import body_path, body_points, deform, drip_path, edge_corners, neck_path, poly_path
from .theme import G, theme


Qt = QtCore.Qt
user32 = ctypes.WinDLL("user32")

WIN_W, WIN_H = 900, 680          # 窗口（逻辑像素），需容纳展开尺寸 + 液桥 + 阴影
EXP_W = 640
PAD = 12
CARD_MARGIN = 10                 # 内卡片与液态玻璃四周的距离
CARD_INNER = 8                   # 内容与内卡片边缘的距离（10→8，让 卡片边距 + 轮廓外沿 = 31 = 折射带 band）
CARD_R = 18                      # 内卡片圆角
PAGE_CARD_INSET = 8.0            # 液态主题下页面内容卡片相对外层玻璃再内缩一圈
NAV_GAP = 12.4                   # 导航胶囊与内容的缝 = 0.40 × band（band 31）
PANEL_R = 40.0                   # 面板圆角兜底值（正常路径按 PANEL_R_RATIO 算）
PANEL_R_RATIO = 0.18             # 面板所有圆角 = 短边 × 18%
NAV_GLASS_BLUR = 11.0            # 导航条模糊玻璃：先按 1/11 下采样再平滑放大（等效大半径高斯）
NAV_GLASS_TINT = 15               # 导航条白 tint 的 alpha（0~255）
NAV_H = 36
FILLET = 13.0                    # 贴边两侧内凹圆角
BREAK = 64.0                     # 液桥拉断距离


def panel_radius(w: float, h: float) -> float:
    """面板圆角：短边 × 18%（页面高度一变半径就跟着变）。

    折叠态 / 尺寸动画中途只有二三十像素高，18% 会算出个位数，整条变方 ——
    所以下限取「半高封顶 18」，那一段仍是胶囊。
    """
    return max(PANEL_R_RATIO * min(w, h), min(h * 0.5, 18.0))
ACRYLIC_TINT = 0x08FFFFFF        # DWM 亚克力的底色：只留一点点白，几乎是纯模糊
JOIN = 30.0                      # 靠近到这个距离时液桥伸出
EDGE_MARGIN = 6

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TRANSPARENT = 0x00000020
# 必须是 64 位 (HWND)-1：裸 -1 经无签名的 ctypes 调用会变成 0x00000000FFFFFFFF，
# 在 x64 上是无效句柄，SetWindowPos(..., HWND_TOPMOST, ...) 会静默失败（返回 0）。
HWND_TOPMOST = ctypes.c_void_p(-1).value
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
WM_HOTKEY = 0x0312
WM_DEVICECHANGE = 0x0219      # 插拔 USB / 蓝牙设备连上断开都会广播这个
HSHELL_FLASH = 0x8006
MOD = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
MOD_NOREPEAT = 0x4000

user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetForegroundWindow.restype = wintypes.HWND
user32.RegisterWindowMessageW.restype = wintypes.UINT
# 窗口 z-order 相关调用必须声明 64 位签名，否则 HWND 会被截成 32 位，
# 顶层窗口（MyDockFinder 也是置顶窗口）的抬升会失效。
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetWindowPos.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL


def parse_hotkey(s: str) -> tuple[int, int] | None:
    parts = [x.strip().lower() for x in (s or "").split("+") if x.strip()]
    if not parts:
        return None
    mods = 0
    vk = 0
    for x in parts:
        if x in MOD:
            mods |= MOD[x]
        elif len(x) == 1 and x.isalnum():
            vk = ord(x.upper())
        elif x.startswith("f") and x[1:].isdigit():
            vk = 0x70 + int(x[1:]) - 1
        elif x == "space":
            vk = 0x20
    return (mods | MOD_NOREPEAT, vk) if vk else None


class _RightClickHook:
    """穿透模式下窗口对鼠标完全透明；用低级鼠标钩子只截获落在灵动岛上的右键。
    只在穿透模式开启时安装，回调对非右键消息立即放行。"""
    WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205

    def __init__(self, island):
        self.island = island
        self.handle = None
        self._proc = None

    def install(self):
        if self.handle:
            return
        u = ctypes.WinDLL("user32", use_last_error=True)
        k = ctypes.WinDLL("kernel32", use_last_error=True)

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        LRESULT = ctypes.c_ssize_t
        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        u.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        u.SetWindowsHookExW.restype = ctypes.c_void_p
        u.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        u.CallNextHookEx.restype = LRESULT
        u.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        k.GetModuleHandleW.restype = wintypes.HMODULE
        self._u = u
        isl = self.island

        def proc(code, wparam, lparam):
            if code == 0 and wparam == 0x020A:        # WM_MOUSEWHEEL
                info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                dpr = isl.scr.devicePixelRatio()
                sg = isl.scr.geometry()
                lx = sg.x() + (info.pt.x - sg.x()) / dpr
                ly = sg.y() + (info.pt.y - sg.y()) / dpr
                if isl.isVisible() and not isl.expanded and isl._inside(QtCore.QPoint(round(lx), round(ly))):
                    delta = ctypes.c_short((info.mouseData >> 16) & 0xFFFF).value
                    QtCore.QTimer.singleShot(0, lambda d=delta: isl.wheel_compact.emit(1 if d > 0 else -1))
                    return 1
            if code == 0 and wparam in (self.WM_RBUTTONDOWN, self.WM_RBUTTONUP):
                info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                # 钩子坐标是物理像素，换算成 Qt 逻辑坐标
                dpr = isl.scr.devicePixelRatio()
                sg = isl.scr.geometry()
                lx = sg.x() + (info.pt.x - sg.x()) / dpr
                ly = sg.y() + (info.pt.y - sg.y()) / dpr
                if isl.isVisible() and isl._inside(QtCore.QPoint(round(lx), round(ly))):
                    if wparam == self.WM_RBUTTONUP:
                        pos = QtCore.QPoint(round(lx), round(ly))
                        QtCore.QTimer.singleShot(0, lambda: isl.menu_requested.emit(pos))
                    return 1          # 吞掉右键，不传给下面的窗口
            return u.CallNextHookEx(self.handle, code, wparam, lparam)

        self._proc = HOOKPROC(proc)
        self.handle = u.SetWindowsHookExW(14, self._proc, k.GetModuleHandleW(None), 0)

    def remove(self):
        if self.handle:
            self._u.UnhookWindowsHookEx(self.handle)
        self.handle = None
        self._proc = None


class _Veil(QtWidgets.QWidget):
    """内容渐显用的"玻璃面纱"：盖在内容上，画和灵动岛完全相同的玻璃，不透明度从 1 降到 0。
    普通子控件、与灵动岛同一次绘制，不会像 QGraphicsOpacityEffect 那样出现没有玻璃底的帧。"""

    def __init__(self, island):
        super().__init__(island)
        self.island = island
        self.alpha = 0.0
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, e):
        if self.alpha <= 0.002:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        p.setOpacity(self.alpha)
        p.translate(-self.x(), -self.y())
        self.island._paint_glass(p, self.island.path, crossfade=False)
        p.end()


class _BlankDoubleClick(QtCore.QObject):
    """灵动岛展开后，双击空白区域（不是按钮 / 输入框等控件）也切换 悬停展开 ↔ 长关。"""

    def __init__(self, island):
        super().__init__(island)
        self.island = island

    def eventFilter(self, obj, ev):
        if ev.type() != QtCore.QEvent.Type.MouseButtonDblClick or not isinstance(obj, QtWidgets.QWidget):
            return False
        isl = self.island
        if obj is isl or obj.window() is not isl or ev.button() != Qt.MouseButton.LeftButton:
            return False
        if self._blank(obj, ev):
            isl.toggle_long_off()
            return True
        return False

    @staticmethod
    def _blank(w, ev) -> bool:
        from .nav import NavBar
        from .pages.base import Page
        from .widgets import Card
        if isinstance(w, NavBar):
            return w._hit(ev.position()) < 0
        if isinstance(w, (Page, Card, QtWidgets.QStackedWidget)):
            return True
        if type(w) is QtWidgets.QWidget:                 # 普通容器（内容区、滚动区内层等）
            return True
        p = w.parentWidget()
        if isinstance(p, QtWidgets.QAbstractScrollArea) and w is p.viewport():
            return True
        return False


class Island(QtWidgets.QWidget):
    expanded_changed = QtCore.Signal(bool)
    hotkey = QtCore.Signal(str)
    flash = QtCore.Signal(int)
    devices_changed = QtCore.Signal()
    wheel_compact = QtCore.Signal(int)
    menu_requested = QtCore.Signal(QtCore.QPoint)
    lock_changed = QtCore.Signal(bool)
    passthrough_changed = QtCore.Signal(bool)
    pin_changed = QtCore.Signal(bool)
    mode_changed = QtCore.Signal(str)

    play_pause_requested = QtCore.Signal()      # 收起态音乐视图的播放 / 暂停键

    def __init__(self, pages: list, peak_fn=None):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setWindowTitle("Mybalcony")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.resize(WIN_W, WIN_H)
        self.peak_fn = peak_fn or (lambda: 0.0)
        self._pk_env = 0.0                # 峰值包络（attack 瞬时 / release 慢衰）
        self._pk_hi = 0.05                # 自动增益基准：近几秒的最大值
        self._pk_t = 0.0

        self.backdrop = Backdrop()
        self._plate_at = 0.0              # 上一次整屏快照的时间戳（见 _snap_plate）
        self._clean_plate = None          # 挪走窗口抓到的那张干净快照（补自画像用）
        self._clean_rect = None
        self._snapping = False            # 正在把窗口挪出屏幕抓快照（期间忽略悬停判断）
        self.compact = CompactView()
        self.pages = pages

        # ---- 几何状态 ----
        self.edge: str = cfg.get("island.edge", "top")
        if self.edge not in ("top", "bottom", "left", "right"):
            self.edge = "top"
        self.pos_frac: float = float(cfg.get("island.pos", 0.5))
        self.scr: QtGui.QScreen = self._pick_screen()
        # 装了 MyDockFinder 就把收起态嵌进它的顶栏里（栏高只有 24px 左右）
        self.bar_h = 0.0
        self._bar_probe_t = 0.0
        if self.embed_bar():
            self._sync_bar(self._finder_bar(), force=True)
        self.mode = "anchored"
        self.expanded = False
        cw, ch = self.compact.size_hint()
        self.sw = Spring(cw, 300, 0.62, 0.2)
        self.sh = Spring(ch, 300, 0.62, 0.2)
        self.fx = Spring(0, 900, 0.78, 0.2)
        self.fy = Spring(0, 900, 0.78, 0.2)
        self.along = Spring(0, 260, 0.72, 0.2)
        self.gap = Spring(0, 320, 0.40, 0.2)
        self.neck_edge: str | None = self.edge
        self.neck_s = Spring(1, 520, 1.0, 0.01)
        self.drips: list[dict] = []
        self.content_a = Spring(0, 700, 1.0, 0.01)
        self.compact_a = Spring(1, 700, 1.0, 0.01)
        self.drag_off = QtCore.QPointF()
        self.locks: set[str] = set()
        self._t0 = time.perf_counter()
        self._last = self._t0
        self._last_cap = 0.0
        self._win_origin = QtCore.QPoint(0, 0)
        self.path = QtGui.QPainterPath()
        self.body = QtCore.QRectF()
        self._hover_since = None
        self._expanded_at = -10.0
        self._out_since = None
        self._press: QtCore.QPointF | None = None
        self._press_g: QtCore.QPointF | None = None
        self._clear_box: QtCore.QRectF | None = None
        self._fs_hidden = False
        self._prev_fg = None
        self._registered_hotkeys: dict[int, str] = {}
        self._rhook = _RightClickHook(self)
        self._mask_rect = None
        self._floor_t: dict = {}
        self.poke = Spring(0, 380, 0.55, 0.004)
        self.lift = Spring(0, 380, 0.62, 0.01)      # iOS 拖动"抬起"程度（0 收 / 1 悬浮）
        self.tilt = Spring(0, 520, 0.55, 0.02)      # 拖动速度带来的轻微倾斜（度）
        self._drag_vx = 0.0
        self._poke_pt = QtCore.QPointF()
        self._poke_sm = QtCore.QPointF()          # 平滑后的按压位置（凹陷跟着鼠标滑动）
        self._floor_on: dict = {}
        self._bd_shown = None
        self._bd_prev = None
        self._light_bg = 0.0            # 背景亮度 0..1：玻璃边缘据此在"白刃口"与"厚度暗侧"间过渡
        self._bd_fade_t0 = 0.0
        self._shell_msg = 0
        self._dirty = QtCore.QRect()
        # 液态玻璃的镜面高光跟着光标走：展开静止时帧循环本来是停的，鼠标在面板里
        # 画圈会让高光定格 / 一顿一顿地跳。光标移动时维持一小段时间的逐帧重绘。
        self._spec_until = 0.0
        self._spec_pos = QtCore.QPoint()
        # 小岛 / 中岛稳定态的轻量帧计数：GPU 背景每帧推，前景（圆角呼吸 + 边缘流光 +
        # 小形象 look/near）按 1/3 帧走一次完整路径，避免把 90Hz 全花在 QPainterPath 重算上。
        self._fast_skip = 0
        self._lg_img: QtGui.QImage | None = None     # 液态玻璃静态光学层缓存
        self._lg_key = None

        # ---- 原生 OpenGL 背景层；Qt 窗口保留全部前景与交互 ----
        self.gpu_view = None
        self._native_gpu = False
        if theme.liquid:
            try:
                from .gpu_window import NativeGlassWindow
                self.gpu_view = NativeGlassWindow(self)
                self._native_gpu = True
                self.backdrop.direct_gpu = True
            except Exception as exc:
                self.gpu_view = None
                self.backdrop.direct_gpu = False
                print("Native GPU init failed:", repr(exc))

        # ---- 展开内容 ----
        self.content = QtWidgets.QWidget(self)
        # 透明中间层链：不打这个标记，Qt 局部重绘时不会往下补画玻璃，圆角处会闪白
        for w in (self.content,):
            w.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.nav = NavBar([(pg.key, pg.glyph, pg.title) for pg in pages], self.content, NAV_H)
        # 页签顺序可拖动调整：恢复上次的顺序（stack 里的控件顺序不动，按 key 取页面）
        self.nav.reorder(cfg.get("island.tab_order") or [])
        self.stack = QtWidgets.QStackedWidget(self.content)
        self.stack.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.stack.setAutoFillBackground(False)
        self.page_map = {pg.key: pg for pg in pages}
        for pg in pages:
            self.stack.addWidget(pg)
            pg.island = self
        lay = QtWidgets.QVBoxLayout(self.content)
        lay.setSpacing(NAV_GAP)                    # 导航与内容的缝（12.4 = 0.4 × band）
        self._content_lay = lay
        self._nav_bottom = None
        self._place_nav()
        self.nav.changed.connect(self.show_page)
        self.nav.drag_requested.connect(self.begin_drag)
        self.nav.reordered.connect(self._tabs_reordered)
        self.content.hide()
        self.veil = _Veil(self)
        self._opacity: QtWidgets.QGraphicsOpacityEffect | None = None
        default = cfg.get("island.last_tab") or cfg.get("island.default_tab", "home")
        self._page_key = default if default in self.nav.keys() else self.nav.keys()[0]
        self.nav.set_current(self._page_key)
        self.stack.setCurrentWidget(self.page_map[self._page_key])

        # ---- 计时器 ----
        self.timer = QtCore.QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self._tick)
        self.poll = QtCore.QTimer(self, interval=25, timeout=self._poll_hover)
        self.lp_timer = QtCore.QTimer(self, singleShot=True, interval=420, timeout=self._long_press)
        self._click_timer = QtCore.QTimer(self, singleShot=True, timeout=self._single_click)
        self._dbl_filter = _BlankDoubleClick(self)
        QtWidgets.QApplication.instance().installEventFilter(self._dbl_filter)
        self.backdrop.ready.connect(self._on_backdrop)
        theme.changed.connect(self._theme_changed)

        self._place_initial()

    # ================================================================ 屏幕 / 位置
    def _pick_screen(self) -> QtGui.QScreen:
        screens = QtGui.QGuiApplication.screens()
        i = int(cfg.get("island.screen", 0) or 0)
        return screens[i] if 0 <= i < len(screens) else QtGui.QGuiApplication.primaryScreen()

    def embed_bar(self) -> bool:
        """是否要把收起态嵌进 MyDockFinder 顶栏。"""
        return bool(cfg.get("island.embed_bar", True)) and self.edge == "top"

    def _sync_bar(self, h: float, force: bool = False) -> None:
        """顶栏高度变了就同步给收起态，并让几何重新算一遍。

        MyDockFinder 开机自启时往往比本程序晚建好顶栏窗口，所以启动时可能探到 0；
        运行中要反复重探，否则会一直"掉"到栏下面贴着 availableGeometry。
        """
        if not self.embed_bar():
            h = 0.0                     # 关掉嵌入：按 availableGeometry 贴边
        if not force and abs(h - self.bar_h) < 0.5:
            return
        self.bar_h = h
        if getattr(self, "expanded", False):
            return
        self.compact.bar_mode = bool(h)
        self.compact.bar_h = h
        if getattr(self, "mode", "") == "anchored":
            cw, ch = self.compact.size_hint()
            self.sw.to(cw, 460, 0.64)
            self.sh.to(ch, 460, 0.64)
        if hasattr(self, "_win_origin"):
            self._update_geometry(force=True)

    def _finder_bar(self) -> float:
        """MyDockFinder 顶栏的高度（窗口类 MyFinderApp）；没装 / 没运行返回 0。"""
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, _):
            try:
                if not user32.IsWindowVisible(hwnd):
                    return True
                buf = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(hwnd, buf, 64)
                if buf.value != "MyFinderApp":
                    return True
                r = wintypes.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                ph = r.bottom - r.top
                if 8 <= ph <= 80:
                    found.append(ph / max(1.0, float(self.scr.devicePixelRatio())))
                    return False
            except Exception:  # noqa: BLE001
                pass
            return True

        try:
            user32.EnumWindows(cb, 0)
        except Exception:  # noqa: BLE001
            return 0.0
        return round(found[0], 1) if found else 0.0

    def _avail(self) -> QtCore.QRectF:
        return QtCore.QRectF(self.scr.availableGeometry())

    def _line(self, edge: str, R: QtCore.QRectF | None = None) -> float:
        R = R or self._avail()
        if edge == "top" and self.bar_h:
            # MyDockFinder 用 AppBar 把顶栏那几十像素"预留"掉了，availableGeometry 的 top
            # 是栏的下沿；要嵌进栏里就必须贴着屏幕真正的上沿。
            return float(self.scr.geometry().top())
        return {"top": R.top(), "bottom": R.bottom() + 1, "left": R.left(), "right": R.right() + 1}[edge]

    def _along_range(self, edge: str, w: float, h: float) -> tuple[float, float]:
        R = self._avail()
        if edge in ("top", "bottom"):
            half = w / 2 + FILLET + EDGE_MARGIN
            return R.left() + half, R.right() + 1 - half
        half = h / 2 + FILLET + EDGE_MARGIN
        return R.top() + half, R.bottom() + 1 - half

    def center_on_edge(self):
        """沿当前吸附边把岛移到正中（首页右侧「居中显示」按钮调用）。"""
        if self.mode != "anchored":
            return
        self.pos_frac = 0.5
        cfg.set("island.pos", 0.5, save=True)
        self._update_geometry(force=True)
        self._kick()

    def _anchor_along(self, w: float, h: float) -> float:
        R = self._avail()
        if self.edge in ("top", "bottom"):
            a = R.left() + self.pos_frac * R.width()
        else:
            a = R.top() + self.pos_frac * R.height()
        lo, hi = self._along_range(self.edge, w, h)
        return clamp(a, lo, hi) if lo <= hi else (lo + hi) / 2

    def _center_on_edge(self, edge: str, along: float, gap: float, w: float, h: float) -> QtCore.QPointF:
        line = self._line(edge)
        if edge == "top":
            return QtCore.QPointF(along, line + gap + h / 2)
        if edge == "bottom":
            return QtCore.QPointF(along, line - gap - h / 2)
        if edge == "left":
            return QtCore.QPointF(line + gap + w / 2, along)
        return QtCore.QPointF(line - gap - w / 2, along)

    def _place_initial(self):
        self._update_geometry(force=True)

    # ================================================================ 展开 / 收起
    def current_page(self):
        """当前页面控件（页签顺序可换，所以不依赖 stack 下标与 pages 列表的对应）。"""
        pg = self.stack.currentWidget()
        return pg if pg is not None else self.pages[0]

    def _tabs_reordered(self, keys):
        """页签拖动排序结束：顺序落盘，页面本身不用搬（按 key 取）。"""
        cfg.set("island.tab_order", list(keys))
        self._page_key = self.nav.current()

    def _content_margin(self) -> float:
        """内容区边距：液态主题下内容落在内卡片里，要按卡片边距算，否则页高会短一截。

        液态主题额外叠加 PAGE_CARD_INSET，让页面内容卡片整体比最外层液态玻璃小一圈。
        """
        return CARD_MARGIN + CARD_INNER + PAGE_CARD_INSET if theme.liquid else PAD

    def page_body_height(self, page_h: float) -> float:
        """页高 -> 面板高。边距上下不对称（上 m-2、下 m），再加导航栏和 8px 间距。"""
        m = self._content_margin()
        return (m - 2) + NAV_H + 8 + page_h + m

    def expanded_size(self) -> tuple[float, float]:
        """打开时的尺寸（按上次停留的页面的高度）。"""
        pg = self.current_page()
        return EXP_W, self.page_body_height(pg.preferred_height())

    def target_size(self) -> tuple[float, float]:
        if self.expanded:
            pg = self.current_page()
            return EXP_W, self.page_body_height(pg.preferred_height())
        return self.compact.size_hint()
        return self.compact.size_hint()

    def _snap_plate(self, force: bool = False, move: bool = True):
        """抓一张"身后"的整屏快照，交给 Backdrop 当真实桌面。

        为什么非要避开自己：Windows 对半透明分层窗口的 GDI 截屏只有两条路 —— 排除自己，
        整块窗口连透明边距一起变成纯黑；不排除，拍到的是自家上一帧。

        move=True：把窗口推出屏幕 25ms 再挪回来（实测 SW_HIDE 的窗口重新显示会留下一块
        永远不重绘的黑色）。走 Qt 的 move：SetWindowPos 是物理像素，控件坐标是逻辑像素，
        150% 缩放下回填会错位，窗口就跑到别的地方去了（表现就是鼠标放上去不展开）。
        move=False：窗口还没显示过（启动阶段）时用，这时屏幕本来就是干净的，不用挪。
        关键：**悬停期间绝不挪窗口**，鼠标一动就会被打断。
        """
        if self._snapping:
            return
        if move and not force and self._inside(QtGui.QCursor.pos()):
            return                                    # 鼠标压在岛上，不动它
        g = self.scr.geometry()
        ox, oy = self.x(), self.y()
        veil = False
        vx = vy = 0
        try:
            veil = self.veil.isVisible()
            vx, vy = self.veil.x(), self.veil.y()
        except Exception:  # noqa: BLE001
            veil = False
        off = g.left() - self.width() - 400
        if move:
            self._snapping = True
        try:
            if move:
                self.move(off, oy)
                if veil:
                    self.veil.move(off, vy)
                QtCore.QThread.msleep(25)             # 等 DWM 把移走的窗口从合成里摘掉
            dpr = max(1.0, float(self.scr.devicePixelRatio()))
            pw, ph = int(round(g.width() * dpr)), int(round(g.height() * dpr))
            # 1:1 抓物理像素，缩小交给 Qt 的平滑缩放。原来直接在 GDI 里 StretchBlt 到 1/3，
            # HALFTONE 的 8x8 误差扩散会把细密文字抖成一层网格 —— 磨砂之后就是"脏"的花纹。
            img = grab_tiny(g.x(), g.y(), pw, ph, pw, ph)
            if img is not None:
                # 1900：玻璃中间现在直接铺这块快照（1:1 落图），1280 对应 1707 逻辑像素只有
                # 0.75 倍，放大回去就是"很糊"的根源。1900 ≈ 1.11 倍，落图时是缩小，肉眼等于原生。
                tw = min(pw, 1900)
                th = max(2, int(round(ph * tw / pw)))
                img = _downscale(img, tw, th)
                if move or not self.isVisible():
                    # 挪走窗口抓的、或者窗口还没显示时抓的，才是真·干净快照；
                    # 留一份当"自家窗口那块"的备份，后面不挪窗口的抓图用它盖住自画像。
                    self._clean_plate = img.copy()
                    self._clean_rect = QtCore.QRect(g)
                if not move:
                    # 不挪窗口抓的那一张里，屏幕上还留着我们自己的那一帧（胶囊，或者一次
                    # 还没收起的展开面板）。现在玻璃中间是 1:1 落图，这些自画像会以原生清晰度
                    # 出现在玻璃里（连导航图标一起，还带着折射带的色散彩虹边）。
                    self._plate_patch_self(img, g)
                self.backdrop.set_plate(img, g)
                self._plate_at = time.perf_counter()
        finally:
            if move:
                self.move(ox, oy)
                if veil:
                    self.veil.move(vx, vy)
                self._snapping = False

    def _plate_patch_self(self, img: QtGui.QImage, g: QtCore.QRect):
        """把快照里自家那块（胶囊 / 面板）盖掉（只在不挪窗口抓图时需要）。

        优先用之前"挪走窗口抓到的干净快照"里的同一块像素贴回去 —— 那才是真实的桌面
        （用下方条带盖是兜底，只适合小胶囊）。"""
        try:
            b = self.path.boundingRect()
            org = getattr(self, "_win_origin", None) or QtCore.QPoint(self.x(), self.y())
            gr = QtCore.QRectF(b.x() + org.x(), b.y() + org.y(), b.width(), b.height())
            s = img.width() / max(1.0, float(g.width()))
            r = QtCore.QRect(int(math.floor(gr.x() * s)) - 3, int(math.floor(gr.y() * s)) - 3,
                             int(math.ceil(gr.width() * s)) + 6, int(math.ceil(gr.height() * s)) + 6)
            r = r.intersected(img.rect())
            if r.isEmpty():
                return
            p = QtGui.QPainter(img)
            p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Source)
            clean, crect = getattr(self, "_clean_plate", None), getattr(self, "_clean_rect", None)
            if clean is not None and crect is not None and not clean.isNull() and crect == g:
                # 两张快照同一块屏幕、同一尺度，直接按像素坐标对拷
                p.drawImage(r, clean, r)
                p.end()
                return
            src = r.translated(0, r.height() + 2).intersected(img.rect())
            if src.isEmpty() or src.height() < 2:
                p.end()
                return
            p.drawImage(r.topLeft(), img.copy(src), QtCore.QRect(0, 0, r.width(), r.height()))
            p.end()
        except Exception:  # noqa: BLE001
            pass

    def expand(self, page: str | None = None):
        if self.mode != "anchored" or self._fs_hidden:
            return
        # 展开瞬间的光脉冲（沉浸光感：窗口"活过来"那一下主题色晕提亮）
        self._pulse_t0 = time.perf_counter()
        if not self.expanded:
            # 展开这一瞬间窗口还只有那颗小胶囊，屏幕其余部分是干净的 —— 趁这时抓一张
            # 新的整屏快照，面板就不会再拿启动时那张过期桌面当背景（过期画面糊出来
            # 就是一层"脏"的鬼影，跟背后的真实窗口对不上）。
            self._snap_plate(force=True, move=False)
            # 打开时停留在上次收起前的页面（热键 / 托盘等指定了页面的除外）
            self.show_page(page or self._page_key)
        elif page:
            self.show_page(page)
        if not self.expanded:
            self.expanded = True
            self.compact_a.to(0, 900, 1.0)
            self.poke.snap(0.0)                       # 展开时清掉按压形变
            w, h = self.target_size()
            self.sw.to(w, 420, 0.62)
            self.sh.to(h, 420, 0.62)
            self.content_a.snap(0)
            tw, th = self.target_size()
            self.content.setGeometry(self._content_rect(tw, th))   # 先隐藏，形状长大后再显示
            if self.passthrough():
                self._apply_passthrough()
            self._defer_show(self.current_page())
            self.expanded_changed.emit(True)
        self._kick()

    def collapse(self):
        if not self.expanded or self.pinned():     # 图钉：保持展开
            return
        self.expanded = False
        self.content_a.snap(0)
        self.content.hide()                   # 立即隐藏内容，玻璃形状再收回胶囊
        self.veil.hide()
        self.release_focus()
        if self.passthrough():
            self._apply_passthrough()
        self.locks.discard("pin")
        self.current_page().on_hide()
        if cfg.get("island.last_tab") != self._page_key:
            cfg.set("island.last_tab", self._page_key)          # 下次（包括重启后）打开仍是这一页
        self.expanded_changed.emit(False)
        self._kick()

    def toggle(self, page: str | None = None):
        if self.expanded and (page is None or page == self._page_key):
            if self.pinned():
                self.set_pinned(False)
            self.collapse()
        else:
            self.expand(page)
            self.locks.add("pin")

    def show_page(self, key: str):
        if key not in self.nav.keys() or key in self.nav.hidden:
            return                                # 被关掉的页签不接受跳转
        pg = self.page_map.get(key)
        if pg is None:
            return
        old = self.stack.currentWidget()
        self._page_key = key
        self.nav.set_current(key)
        if pg is not old:
            if self.expanded:
                old.on_hide()
            self.stack.setCurrentWidget(pg)
            if self.expanded:
                self._defer_show(pg)
        if self.expanded:
            w, h = self.target_size()
            self.sw.to(w, 440, 0.6)
            self.sh.to(h, 440, 0.6)
        self._kick()

    def _defer_show(self, pg):
        """页面的数据刷新稍后执行，让形变动画先跑起来。"""
        QtCore.QTimer.singleShot(40, lambda: pg.on_show() if self.expanded and self.current_page() is pg else None)

    def page_size_changed(self):
        """页面内容高度变化时由页面调用。"""
        if self.expanded:
            w, h = self.target_size()
            self.sh.to(h, 440, 0.62)
            self._kick()

    def set_compact_scale(self, s: float, save: bool = True):
        """控制页的胶囊大小滑块：只改收起态，展开面板尺寸不受影响。

        拖动中 save=False 只更新内存（避免每帧写 config.json），松手时再落盘。
        """
        s = clamp(float(s), 0.7, 1.3)
        self.compact.ui_scale = s
        cfg.set("island.scale", round(s, 3), save=save)
        if not self.expanded:
            cw, ch = self.compact.size_hint()
            self.sw.to(cw, 300, 0.55)
            self.sh.to(ch, 300, 0.55)
        self._kick()

    def activity(self, act: dict, duration: float = 2.4):
        self.compact.show_activity(act, duration)
        self._kick()

    def _set_content_opacity(self, a: float):
        """不再使用 QGraphicsOpacityEffect：在透明分层窗口里，带效果的子控件会单独重绘，
        偶尔出现"有内容、没有玻璃底"的帧。内容改为：形状长到约 70% 后直接显示（被形状裁剪），收起时立即隐藏。"""
        return

    # ================================================================ 拖动
    def begin_drag(self, gpos: QtCore.QPoint | None = None):
        if self.mode == "drag" or self.passthrough():
            return
        gpos = QtCore.QPointF(gpos or QtGui.QCursor.pos())
        c = self.body.center() + QtCore.QPointF(self._win_origin)
        if self.expanded:
            self.expanded = False
            self.content_a.snap(0)
            self._set_content_opacity(0)
            self.content.hide()
            self.release_focus()
            self.locks.discard("pin")
            self.current_page().on_hide()
            self.expanded_changed.emit(False)
            # 收成胶囊，中心向鼠标靠拢
            c = QtCore.QPointF(gpos)
        self.compact_a.to(1, 500, 1.0)
        cw, ch = self.compact.size_hint()
        self.sw.to(cw, 300, 0.55)
        self.sh.to(ch, 300, 0.55)
        self.mode = "drag"
        self.fx.snap(c.x())
        self.fy.snap(c.y())
        self._drag_vx = 0.0
        self._drag_t0 = time.monotonic()
        self._drag_c0 = QtCore.QPointF(c)
        self._pending_click = False
        self.lift.to(1.0, 380, 0.58)         # 抓起来的瞬间先稍微放大，再稳定到悬浮
        self.tilt.snap(0.0)
        self.drag_off = c - gpos
        if not (self.body.contains(QtCore.QPointF(gpos) - QtCore.QPointF(self._win_origin))):
            self.drag_off = QtCore.QPointF(0, 0)
        QtWidgets.QApplication.setOverrideCursor(Qt.CursorShape.ClosedHandCursor)
        self._kick()

    def _end_drag(self):
        QtWidgets.QApplication.restoreOverrideCursor()
        # 松手：先缩回原大小（带一点回弹），再吸附到最近的边
        self.lift.to(0.0, 460, 0.42)
        self.tilt.to(0.0, 430, 0.46)
        c = QtCore.QPointF(self.fx.x, self.fy.x)
        # 手点一下时鼠标常会抖出十几像素：位移很小又松手很快的"拖动"其实是想单击，
        # 吸附回去后顺手把面板展开，避免看着像点了没反应。
        self._pending_click = (time.monotonic() - getattr(self, "_drag_t0", 0.0) < 0.55
                               and (c - getattr(self, "_drag_c0", c)).manhattanLength() < 16)
        scr = QtGui.QGuiApplication.screenAt(c.toPoint()) or self.scr
        self.scr = scr
        R = self._avail()
        w, h = self.sw.target, self.sh.target
        body = QtCore.QRectF(c.x() - w / 2, c.y() - h / 2, w, h)
        gaps = {
            "top": body.top() - R.top(),
            "bottom": R.bottom() + 1 - body.bottom(),
            "left": body.left() - R.left(),
            "right": R.right() + 1 - body.right(),
        }
        # 横向的边更"吸"一点（胶囊横放时贴左右边比较少见）
        weights = {"top": 1.0, "bottom": 1.0, "left": 1.35, "right": 1.35}
        edge = min(gaps, key=lambda k: gaps[k] * weights[k])
        self.edge = edge
        horiz = edge in ("top", "bottom")
        along0 = c.x() if horiz else c.y()
        v_along = self.fx.v if horiz else self.fy.v
        # 速度投影：朝边缘运动 => gap 减小
        v_toward = (-self.fy.v if edge == "top" else self.fy.v if edge == "bottom"
                    else -self.fx.v if edge == "left" else self.fx.v)
        self.along.snap(along0)
        self.along.v = v_along
        lo, hi = self._along_range(edge, w, h)
        self.along.to(clamp(along0, lo, hi), 240, 0.74)
        self.gap.snap(max(-4.0, gaps[edge]))
        self.gap.v = -v_toward
        self.gap.to(0, 300, 0.38)
        self.mode = "snap"
        if self.neck_edge and self.neck_edge != edge:
            self._break_neck()
        self._kick()

    def _break_neck(self):
        if not self.neck_edge:
            return
        e = self.neck_edge
        horiz = e in ("top", "bottom")
        c = self.body.center() + QtCore.QPointF(self._win_origin)
        s = Spring(7.5, 160, 0.45, 0.05)
        s.to(0)
        self.drips.append({"edge": e, "line": self._line(e), "c": c.x() if horiz else c.y(), "r": s})
        self.neck_edge = None
        self.neck_s.snap(0)

    # ================================================================ 每帧
    def _kick(self):
        if not self.timer.isActive():
            self._last = time.perf_counter()
            self.timer.start()

    def _gpu_active(self) -> bool:
        """原生 GPU 液态背景层是否正在工作。

        大岛（展开）已验证的办法：NativeGlassWindow 常驻在 Qt 前景下方，背景由 DXCam
        高帧纹理直接上传，Qt 侧只画前景。收起态 / 中岛只要满足同样条件就共用这套机制，
        帧循环因此可以常驻在轻量档而不是耗在 spring / path / layout 重算上。
        拖动、全屏隐藏、非液态主题、GPU 初始化失败时一律返回 False（保留原回退路径）。
        """
        return (theme.liquid and self._native_gpu and self.gpu_view is not None
                and self.gpu_view.isVisible() and self.mode == "anchored"
                and not self._fs_hidden and self.isVisible())

    def _compact_cursor_far(self, margin: float) -> bool:
        """光标是否离小岛本体（不是 900×680 的透明窗口）足够远。

        小形象的 look/near 只跟本体附近的鼠标有关；用整窗口判断的话，光标在屏幕上半区
        就会一直挡住轻量路径，优化等于没做。
        """
        b = self.body.translated(QtCore.QPointF(self._win_origin))
        b = b.adjusted(-margin, -margin, margin, margin)
        return not b.contains(QtCore.QPointF(QtGui.QCursor.pos()))

    def _idle_gpu(self) -> bool:
        """可以走 45fps 前景档：GPU 层在、收起静止、光标离岛 120px 外、无按压/抬起/倾斜。

        媒体播放 / 活动提示 / 字幕时**不降档**：音律跳动、歌词扫光这些看的就是高频，
        45fps 会让"跳"变得没劲；小形象（pet）仍然可以降——光标离得远，眨眼和眼神
        跟随本来就看不见，不必为它常驻 90fps。
        """
        if self.expanded or not self._gpu_active():
            return False
        if not all(s.rest for s in (self.poke, self.lift, self.tilt)):
            return False
        if not self._compact_cursor_far(120.0):
            return False
        return self.compact.mode() not in ("media", "activity", "subtitle")

    def _bg_relaxed(self) -> bool:
        """背景抓屏可以降到 30fps：只看"有没有交互"，与前景是否在跑动画无关。

        实测背景这条路最贵（60fps × 16.5ms ≈ 一整核），它只决定玻璃里映出的桌面
        多久刷新一次；光标离岛远、没展开、形状静止时，30fps 的雾化背景看不出差别。
        """
        return (self.mode == "anchored" and not self.expanded
                and self.sw.rest and self.sh.rest
                and self._compact_cursor_far(120.0))

    def _needs_frames(self) -> bool:
        if self.mode != "anchored" or self.drips or self._bd_prev is not None:
            return True
        if self._gpu_active():
            # GPU 背景层：收起 / 中岛 / 展开都要常驻帧，轻量路径每帧只推一次 GPU 画布。
            return True
        if theme.liquid and self.expanded and time.perf_counter() < self._spec_until:
            return True                  # 镜面高光跟手：鼠标停稳后自动停帧，不常驻 60fps
        for s in (self.sw, self.sh, self.content_a, self.compact_a, self.neck_s, self.lift, self.tilt):
            if not s.rest:
                return True
        if not self.expanded and not self._fs_hidden:
            return True                  # 收起态：常态动画（圆角呼吸 + 边缘流光）持续运行
        return False

    def _foreground_animating(self) -> bool:
        """前景是否存在「形状不变、但需要逐帧刷新」的动画。

        GPU 可见时前景窗口默认只在形状变化（old != new）时重绘；歌词扫光、圆角呼吸、
        边缘流光、pet 表情和液态大岛的镜面高光跟手都属于形状不变的前景动画，需要单独
        放行。该方法只在走到完整帧时由 _update_geometry 调用（轻量帧在 _tick 里已提前
        return），因此不会抵消 2/3 轻量帧节流。
        """
        if self.compact.busy():
            return True                  # 歌词扫光 / pet 表情 / 字幕 / activity
        if theme.liquid and self.expanded and time.perf_counter() < self._spec_until:
            return True                  # 液态大岛：镜面高光跟手窗口
        if not self.expanded and not self._fs_hidden:
            return True                  # 收起态：圆角呼吸 + 边缘流光 + 小形象 look/near
        return False

    def _tick(self):
        now = time.perf_counter()
        dt = min(1 / 30, max(1 / 240, now - self._last))
        self._last = now

        # ---- settled fast path（大岛办法）：GPU 层可见 + 锚定 + 无水滴/背景交叉淡入 +
        #      关键 spring 全 rest 时，只推 GPU 画布，跳过整段 spring / path / layout 重算。
        if (self._gpu_active() and not self.drips and self._bd_prev is None
                and all(s.rest for s in (self.sw, self.sh, self.content_a, self.compact_a))):
            if self.expanded:
                # 大岛：展开态前景默认是静态的，沿用原来的纯 GPU 轻量帧；
                # 但镜面高光跟手窗口内 paint_spec 每帧都在变，必须走完整帧重绘前景，
                # 否则前景窗口拿不到 update()，高光会定格（形状不变也被旧闸门挡住）。
                if time.perf_counter() >= self._spec_until:
                    self.gpu_view.update()
                    self.timer.setInterval(11)
                    return
            # 小岛 / 中岛：前景还有圆角呼吸、边缘流光和小形象 look/near 跟手，不能整段跳过。
            # media / pet / subtitle 这类持续动画（compact.busy()）照常跑完整帧循环；
            # 光标靠近时 look/near 要跟手也走完整帧。真正稳定且光标离岛较远时进轻量档：
            # 每 3 帧放行一次完整路径刷新呼吸 / 流光 / 表情（约 30fps，与原空闲档一致），
            # 其余帧只更新 GPU 背景纹理，避免 90Hz 全花在 QPainterPath / 布局重算上。
            if (not self.expanded and self._gpu_active() and not self.compact.busy()
                    and all(s.rest for s in (self.poke, self.lift, self.tilt))
                    and self._compact_cursor_far(96.0)):
                if self._idle_gpu():
                    # 空闲档：22ms（45fps）完整帧。呼吸 / 边缘流光在 45fps 下已经看不出降帧，
                    # 又比常驻 90fps 省掉一半主线程；背景另按 30fps 抓（见 _request_backdrop）。
                    # 不做 2/3 轻量跳过：轻量帧只推 GPU 画布，45fps 下会变成 15fps 前景动画。
                    self.timer.setInterval(22)
                else:
                    self._fast_skip = (self._fast_skip + 1) % 3
                    if self._fast_skip:
                        self.gpu_view.update()
                        self.timer.setInterval(11)
                        return

        if self.embed_bar() and now - self._bar_probe_t > 1.5:
            # MyDockFinder 可能比本程序晚启动（或中途重启），持续重探顶栏高度
            self._bar_probe_t = now
            self._sync_bar(self._finder_bar())

        if self.mode == "drag":
            if not (user32.GetAsyncKeyState(0x01) & 0x8000):
                self._end_drag()
            else:
                cp = QtCore.QPointF(QtGui.QCursor.pos()) + self.drag_off
                self.fx.to(cp.x())
                self.fy.to(cp.y())
                self._drag_vx = self.fx.v
                # iOS 那种"甩起来会微微倾斜"：按水平速度给一个很小的角度，限幅 6°
                self.tilt.to(clamp(-self._drag_vx * 0.006, -6.0, 6.0), 520, 0.55)
        if self.gpu_view is not None:
            should_show = theme.liquid and self.mode != "drag"
            if self.gpu_view.isVisible() != should_show:
                if self._native_gpu:
                    self.gpu_view.setFlag(Qt.WindowType.WindowStaysOnTopHint,
                                          bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint))
                self.gpu_view.setVisible(should_show)
                if self._native_gpu and should_show:
                    user32.SetWindowPos(int(self.gpu_view.winId()), int(self.winId()),
                                        0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
                    self.raise_()
        if not self.expanded:
            cw, ch = self.compact.size_hint()
            if abs(self.sw.target - cw) > 0.5 or abs(self.sh.target - ch) > 0.5:
                # 尺寸只看目标值就够了：不能再用 content_a 当闸门——面板展开过一次后
                # content_a 会停在 1，收起态就再也长不高（悬停三行会卡在中间高度）。
                self.sw.to(cw, 460, 0.64)
                self.sh.to(ch, 460, 0.64)
                if self.compact_a.target < 1:
                    self.compact_a.to(1, 420, 1.0)
        else:
            w, h = self.target_size()
            # 形状长到完整尺寸后才显示内容（之后不会再缩到比内容小），全程不需要遮罩
            if self.sh.x >= h - 1 and self.sw.x >= w - 1 and self.content_a.target < 1:
                self.content_a.snap(0)
                self.content_a.to(1, 700, 1.0)
                tw, th = self.target_size()
                self.content.setGeometry(self._content_rect(tw, th, self.body))
                self.content.show()
                self.veil.setGeometry(self.content.geometry())
                self.veil.alpha = 1.0
                self.veil.show()
                self.veil.raise_()

        for s in (self.sw, self.sh, self.fx, self.fy, self.along, self.gap, self.neck_s,
                  self.content_a, self.compact_a, self.poke, self.lift, self.tilt):
            s.step(dt)
        if abs(self.poke.x) > 0.01 or self.poke.target:
            if self._poke_sm.isNull():
                self._poke_sm = QtCore.QPointF(self._poke_pt)
            self._poke_sm += (self._poke_pt - self._poke_sm) * 0.3
        if not self.expanded:
            # 小形象看向光标；靠近时开心
            c = self.body.center() + QtCore.QPointF(self._win_origin)
            rel = QtCore.QPointF(QtGui.QCursor.pos()) - c
            self.compact.look = rel
            self.compact.near = abs(rel.x()) < self.body.width() / 2 + 40 and abs(rel.y()) < self.body.height() / 2 + 40
        if self.expanded:
            # 展开态：越过目标后不再回落到目标以下（保留过冲回弹，但不会比内容小）
            for sp, key in ((self.sw, "w"), (self.sh, "h")):
                if self._floor_t.get(key) != sp.target:
                    self._floor_t[key] = sp.target
                    self._floor_on[key] = sp.x >= sp.target
                if sp.x >= sp.target:
                    self._floor_on[key] = True
                elif self._floor_on.get(key):
                    sp.x, sp.v = sp.target, 0.0
        for d in self.drips:
            d["r"].step(dt)
        self.drips = [d for d in self.drips if not (d["r"].rest or d["r"].x < 0.3 and d["r"].v < 0)]

        if self.mode == "snap" and self.along.rest and self.gap.rest:
            self.mode = "anchored"
            self._place_nav()
            if getattr(self, "_pending_click", False):
                # 这次"拖动"其实是单击：落回原边后把面板展开
                self._pending_click = False
                QtCore.QTimer.singleShot(40, self._single_click)
            if self.pinned():
                QtCore.QTimer.singleShot(80, self.expand)
            R = self._avail()
            horiz = self.edge in ("top", "bottom")
            self.pos_frac = clamp(((self.along.x - R.left()) / R.width()) if horiz
                                  else ((self.along.x - R.top()) / R.height()), 0, 1)
            cfg.set("island.edge", self.edge, save=False)
            cfg.set("island.pos", round(self.pos_frac, 4), save=False)
            screens = QtGui.QGuiApplication.screens()
            cfg.set("island.screen", screens.index(self.scr) if self.scr in screens else 0)
            self.neck_edge = self.edge
            self.neck_s.to(1)

        # 收起时：内容淡出完成后隐藏
        if not self.expanded and self.content.isVisible() and self.content_a.x < 0.05:
            self.content.hide()
            self._set_content_opacity(0)
        if self.veil.isVisible():
            a = clamp(1.0 - self.content_a.x, 0.0, 1.0)
            if a <= 0.01 or not self.content.isVisible():
                self.veil.hide()
            else:
                self.veil.alpha = a
                if self.veil.geometry() != self.content.geometry():
                    self.veil.setGeometry(self.content.geometry())
                self.veil.update()

        self._update_geometry()
        if not self._needs_frames() and self.mode == "anchored":
            self.timer.stop()
            self.timer.setInterval(16)
        elif self.mode == "anchored" and self.sw.rest and self.sh.rest and not self.expanded:
            # 收起 / 中岛：GPU 路径按大岛同档 11ms 驱动背景纹理（轻量帧只推 GPU 画布，
            # 完整帧约每 3 帧一次刷新呼吸 / 流光）；有 media/pet/subtitle 持续动画时 16ms
            # 跑完整帧。无 GPU 的 CPU / offscreen 回退仍是 60/30fps 省电档，不无谓高频抓屏。
            if self._gpu_active():
                if self.compact.busy():
                    # 媒体播放 / 活动提示 / 字幕：音律跳动和扫光按最高档跑完整帧，
                    # 不做 2/3 轻量跳过（跳过时前景只有 1/3 帧刷新，律动会"没劲"）。
                    self.timer.setInterval(11)
                else:
                    self.timer.setInterval(22 if self._idle_gpu() else 11)
            else:
                self.timer.setInterval(16 if self.compact.busy() else 33)
        elif (self.mode == "anchored" and self.expanded and theme.liquid
              and self.sw.rest and self.sh.rest):
            # 90 Hz 液态背景由 DXCam 驱动；GPU/CPU 实际帧率由性能采样记录。
            self.timer.setInterval(11)
        else:
            self.timer.setInterval(16)

    # ================================================================ 形状计算
    def _nearest_edge(self, body: QtCore.QRectF) -> tuple[str, float]:
        R = self._avail()
        gaps = {
            "top": body.top() - R.top(),
            "bottom": R.bottom() + 1 - body.bottom(),
            "left": body.left() - R.left(),
            "right": R.right() + 1 - body.right(),
        }
        e = min(gaps, key=gaps.get)
        return e, gaps[e]

    @staticmethod
    def _gap_to(edge: str, body: QtCore.QRectF, line: float) -> float:
        return {"top": body.top() - line, "bottom": line - body.bottom(),
                "left": body.left() - line, "right": line - body.right()}[edge]

    def _update_geometry(self, force: bool = False):
        w, h = max(40.0, self.sw.x), max(24.0, self.sh.x)
        vx = vy = 0.0
        squash = 0.0
        if self.mode == "anchored":
            pk = clamp(self.poke.x, -0.5, 1.2)
            if abs(pk) > 0.002 and not self.expanded:
                # 可穿透时被鼠标"按住"：整颗水滴朝屏幕边压扁、略微变宽，松开后带回弹
                if self.edge in ("top", "bottom"):
                    h, w = h * (1 - 0.16 * pk), w * (1 + 0.05 * pk)
                else:
                    w, h = w * (1 - 0.16 * pk), h * (1 + 0.05 * pk)
            a = self._anchor_along(w, h)
            c = self._center_on_edge(self.edge, a, 0, w, h)
            self.neck_edge = self.edge
        elif self.mode == "snap":
            g = self.gap.x
            if g < 0:                       # 冲过边缘 -> 挤压
                squash = -g
                g = 0.0
            horiz = self.edge in ("top", "bottom")
            if horiz:
                h2 = max(h * 0.62, h - squash)
                w = w + squash * 1.1
                h = h2
            else:
                w2 = max(w * 0.62, w - squash)
                h = h + squash * 1.1
                w = w2
            c = self._center_on_edge(self.edge, self.along.x, g, w, h)
            va, vg = self.along.v, self.gap.v
            vx, vy = {"top": (va, vg), "bottom": (va, -vg), "left": (vg, va), "right": (-vg, va)}[self.edge]
            if self.neck_edge is None and g < JOIN:
                self.neck_edge = self.edge
                self.neck_s.snap(0)
                self.neck_s.to(1, 520, 1.0)
        else:  # drag
            c = QtCore.QPointF(self.fx.x, self.fy.x)
            vx, vy = self.fx.v, self.fy.v
        body = QtCore.QRectF(c.x() - w / 2, c.y() - h / 2, w, h)

        if self.mode == "drag":
            if self.neck_edge:
                gn = self._gap_to(self.neck_edge, body, self._line(self.neck_edge))
                if gn > BREAK:
                    self._break_neck()
            if not self.neck_edge:
                e, g = self._nearest_edge(body)
                if g < JOIN:
                    self.neck_edge = e
                    self.neck_s.snap(0)
                    self.neck_s.to(1, 520, 1.0)

        # ---- 窗口位置：让本体大致居中，并夹在屏幕内（避免跨屏缩放） ----
        sg = self.scr.geometry()
        if self.mode == "anchored":
            # 吸附时窗口贴住吸附边、位置固定：展开 / 收起 / 切页都不移动窗口
            # （移动分层窗口与重绘不是原子操作，会出现内容错位、没有玻璃底的帧）
            R = self._avail()
            line = self._line(self.edge)
            if self.edge in ("top", "bottom"):
                a = R.left() + self.pos_frac * R.width()
                cx_, cy_ = a, (line - 4 + WIN_H / 2) if self.edge == "top" else (line + 4 - WIN_H / 2)
            else:
                a = R.top() + self.pos_frac * R.height()
                cx_, cy_ = ((line - 4 + WIN_W / 2) if self.edge == "left" else (line + 4 - WIN_W / 2)), a
            wx = int(clamp(round(cx_ - WIN_W / 2), sg.left(), sg.right() + 1 - WIN_W))
            wy = int(clamp(round(cy_ - WIN_H / 2), sg.top(), sg.bottom() + 1 - WIN_H))
        else:
            wx = int(clamp(round(c.x() - WIN_W / 2), sg.left(), sg.right() + 1 - WIN_W))
            wy = int(clamp(round(c.y() - WIN_H / 2), sg.top(), sg.bottom() + 1 - WIN_H))
        origin = QtCore.QPoint(wx, wy)
        if origin != self._win_origin or force:
            self._win_origin = origin
            self.move(origin)
        off = QtCore.QPointF(-wx, -wy)
        lbody = body.translated(off)

        # ---- 半径 ----
        # 面板圆角 = 短边 × 18%（原来的固定 40 只是兜底值）
        base_r = panel_radius(w, h)
        t_now = time.perf_counter() - self._t0
        fillet = FILLET
        if self.mode == "anchored" and not self.expanded:
            fillet *= 1.0 + 0.07 * math.sin(t_now * 1.7)            # 常态：圆角轻微"呼吸"
        fillet += min(12.0, (abs(self.sw.v) + abs(self.sh.v)) * 0.012)   # 形变越快，液面拉得越开

        path = QtGui.QPainterPath()
        neck = None
        gap_n = 0.0
        if self.neck_edge:
            ne = self.neck_edge
            line = self._line(ne)
            gap_n = max(0.0, self._gap_to(ne, body, line))
            t = clamp(gap_n / BREAK, 0, 1)
            corner_r = base_r * smooth(t * 1.8)
            corner_r = lerp(base_r, corner_r, self.neck_s.x)
            radii = tuple(corner_r if flag else base_r for flag in edge_corners(ne))
            horiz = ne in ("top", "bottom")
            along_c = body.center().x() if horiz else body.center().y()
            length = w if horiz else h
            lline = line + (-wy if horiz else -wx)
            neck = neck_path(ne, lline, along_c + (-wx if horiz else -wy), length, gap_n, t,
                             self.neck_s.x, fillet, corner_r)
        else:
            radii = (base_r,) * 4

        speed = math.hypot(vx, vy)
        playing_wave = (self.mode == "anchored" and not self.expanded and self.compact.mode() == "media"
                        and self.compact.playing())
        poking = self.mode == "anchored" and abs(self.poke.x) > 0.01
        if speed > 30 or playing_wave or poking:
            pts = body_points(lbody, radii, 4.0)
            wave = None
            poke_params = None
            if poking:
                # 按压：沿"远离屏幕边"的方向整体位移（不是沿中心放射方向），外侧半边（含两端圆角）都参与
                ppt = self._poke_sm - QtCore.QPointF(wx, wy)
                amp = clamp(self.poke.x, -0.6, 1.2) * 8.0
                farv = {"top": (0, 1), "bottom": (0, -1), "left": (1, 0), "right": (-1, 0)}[self.edge]
                horiz = farv[0] == 0
                c_u = lbody.center().x() if horiz else lbody.center().y()
                half = max(20.0, (lbody.width() if horiz else lbody.height()) / 2)
                depth = lbody.height() if horiz else lbody.width()
                u0 = clamp((ppt.x() if horiz else ppt.y()), c_u - half, c_u + half)
                sig = half * 0.5
                near_line = {"top": lbody.top(), "bottom": lbody.bottom(), "left": lbody.left(), "right": lbody.right()}[self.edge]
                poke_params = (amp, farv, horiz, u0, sig, near_line, depth)
            else:
                poke_params = None
            if playing_wave:
                pk = self._pk()
                far = {"top": (0, 1), "bottom": (0, -1), "left": (1, 0), "right": (-1, 0)}[self.edge]
                tt = t_now

                prev = wave

                def wave(px, py, nx, ny, pk=pk, far=far, tt=tt, prev=prev):
                    extra = prev(px, py, nx, ny) if prev else 0.0
                    wgt = max(0.0, nx * far[0] + ny * far[1])
                    if wgt < 0.3:
                        return extra
                    u = px if far[0] == 0 else py
                    return extra + pk * 2.4 * wgt * wgt * math.sin(u * 0.09 - tt * 7.0)
            pts = deform(pts, lbody.center().x(), lbody.center().y(), vx, vy,
                         min(w, h) / 2 + 12, wave)
            if poke_params is not None:
                amp, farv, horiz, u0, sig, near_line, depth = poke_params
                out = []
                for px, py in pts:
                    v = abs((py if horiz else px) - near_line)          # 离屏幕边的距离
                    wgt = clamp((v - depth * 0.3) / (depth * 0.7), 0.0, 1.0)
                    if wgt > 0:
                        d = ((px if horiz else py) - u0) / sig
                        g = math.exp(-0.5 * d * d)
                        disp = amp * wgt * wgt * (-g + 0.35 * (1.0 - g))   # 光标处凹进，其余略鼓（体积守恒）
                        px += farv[0] * disp
                        py += farv[1] * disp
                    out.append((px, py))
                pts = out
            body_p = poly_path(pts)
        else:
            body_p = body_path(lbody, radii)
        path = body_p
        if neck is not None and not neck.isEmpty():
            path = path.united(neck)
        for d in self.drips:
            e = d["edge"]
            horiz = e in ("top", "bottom")
            lline = d["line"] + (-wy if horiz else -wx)
            dp = drip_path(e, lline, d["c"] + (-wx if horiz else -wy), max(0.0, d["r"].x))
            if not dp.isEmpty():
                path = path.united(dp)
        path.setFillRule(Qt.FillRule.WindingFill)

        old = self.path.boundingRect().toAlignedRect()
        self.path = path
        self.body = lbody
        if self.gpu_view is not None:
            if self._native_gpu:
                self.gpu_view.sync_geometry()
            else:
                gpu_rect = path.boundingRect().toAlignedRect().adjusted(-2, -2, 2, 2)
                if gpu_rect != self.gpu_view.geometry():
                    self.gpu_view.setGeometry(gpu_rect)
        new = path.boundingRect().toAlignedRect()
        dirty = old.united(new).adjusted(-16, -16, 16, 16)

        # ---- 内容区 ----
        if self.content.isVisible() and self.expanded:   # 收起淡出时保持原尺寸，不再挤压内容
            tw, th = self.target_size()
            cr = self._content_rect(tw, th, lbody)
            if cr != self.content.geometry():
                self.content.setGeometry(cr)
            vis = lbody.toAlignedRect().intersected(cr).translated(-cr.topLeft())
            # 只在遮罩真正变化时设置：每帧 setMask/clearMask 会让内容单独重绘一遍，出现没有玻璃底的帧
            want = vis if vis.size() != cr.size() else None
            if want != self._mask_rect:
                self._mask_rect = want
                if want is None:
                    self.content.clearMask()
                else:
                    self.content.setMask(QtGui.QRegion(want))

        # ---- 毛玻璃采样（后台线程）：覆盖当前形状 + 目标形状，一次截图够整段展开动画用 ----
        self._request_backdrop()
        # 整块重绘（而不是只脏区）：拖动时窗口本身也在移动，只重绘脏区会留下上一帧的残影
        # 直接 GPU 静止时只重绘 OpenGL 画布；形状改变才让父窗口重画阴影。
        if self.gpu_view is not None and self.gpu_view.isVisible() and self.mode != "drag":
            self.gpu_view.update()
            # 形状不变也要重绘 Qt 前景：歌词扫光 / 呼吸 / 流光 / 跟手高光都是形状不变的
            # 前景动画。轻量帧在 _tick 里已提前 return，到不了这里，故不破坏 2/3 节流。
            if old != new or self._foreground_animating():
                self.update()
        else:
            self.update()

    def _content_rect(self, tw, th, lbody: QtCore.QRectF | None = None) -> QtCore.QRect:
        """内容区：贴着吸附边、沿边居中（窗口坐标）。"""
        if lbody is None:
            c = self._center_on_edge(self.edge, self._anchor_along(tw, th), 0, tw, th) - QtCore.QPointF(self._win_origin)
            return QtCore.QRect(round(c.x() - tw / 2), round(c.y() - th / 2), round(tw), round(th))
        cr = QtCore.QRect(round(lbody.center().x() - tw / 2), round(lbody.top()), round(tw), round(th))
        if self.edge == "bottom" and self.mode == "anchored":
            cr.moveBottom(round(lbody.bottom()))
        return cr

    def _place_nav(self):
        """吸附在屏幕底边时，导航栏放到面板最下方（靠近吸附边），其余位置放在最上方。"""
        bottom = self.edge == "bottom"
        if bottom == self._nav_bottom:
            return
        self._nav_bottom = bottom
        lay = self._content_lay
        lay.removeWidget(self.nav)
        lay.removeWidget(self.stack)
        # 液态主题：内容落在内卡片里，边距 = 卡片与玻璃的距离 + 卡片内边距 + 页面卡片内缩，
        # 让页面内容卡片整体比最外层液态玻璃小一圈
        m = CARD_MARGIN + CARD_INNER + PAGE_CARD_INSET if theme.liquid else PAD
        if bottom:
            lay.setContentsMargins(m, m, m, m - 2)
            lay.addWidget(self.stack, 1)
            lay.addWidget(self.nav)
        else:
            lay.setContentsMargins(m, m - 2, m, m)
            lay.addWidget(self.nav)
            lay.addWidget(self.stack, 1)

    def _theme_changed(self):
        """换主题：液态玻璃会影响背景图本身的处理，所以立刻重取一次背景。"""
        self.backdrop.liquid = theme.liquid
        self._nav_bottom = None                # 强制按新主题重算内容边距（内卡片）
        self._place_nav()
        self._request_backdrop()
        self.update()

    def _request_backdrop(self):
        animating = self.mode == "anchored" and not (self.sw.rest and self.sh.rest)
        if self.mode == "anchored":
            tw, th = self.target_size()
            tc = self._center_on_edge(self.edge, self._anchor_along(tw, th), 0, tw, th)
            g = QtCore.QRectF(tc.x() - tw / 2, tc.y() - th / 2, tw, th).toAlignedRect()
            # 始终预先覆盖展开尺寸：收起时打开第一帧就有玻璃，展开/收起动画全程区域固定，
            # 后台线程不会因为 g 每帧变化被反复唤醒（那会和折射重算叠加成明显掉帧）。
            ew, eh = self.expanded_size()
            ec = self._center_on_edge(self.edge, self._anchor_along(ew, eh), 0, ew, eh)
            g = g.united(QtCore.QRectF(ec.x() - ew / 2, ec.y() - eh / 2, ew, eh).toAlignedRect())
            pad = 40                      # 覆盖两侧表面张力圆角
            if theme.liquid:
                pad = 150                 # 液态玻璃：折射取样朝外最多约 80px，需要足够宽的真实像素环
        else:
            g = self.path.boundingRect().toAlignedRect().translated(self._win_origin)
            pad = 90 if not theme.liquid else 150
        # 自家窗口里"面板本体"这块在截图里是自画像（外面那圈透明边距仍是真背景），
        # 把面板轮廓（含自绘阴影）让 Backdrop 用四周颜色扩散补掉；再往外 30px 留给折射取样。
        self.backdrop.hole = self.path.boundingRect().toAlignedRect().translated(
            self._win_origin).adjusted(-30, -30, 30, 30)
        g = g.adjusted(-pad, -pad, pad, pad)
        q = 16                            # 对齐网格：区域不随轮廓的细微变化而抖动
        x0, y0 = (g.left() // q) * q, (g.top() // q) * q
        x1, y1 = -((-(g.right() + 1)) // q) * q, -((-(g.bottom() + 1)) // q) * q
        g = QtCore.QRect(x0, y0, x1 - x0, y1 - y0)
        if self.mode != "anchored":
            interval = 1 / 40           # 拖动：窗口真的在移动，背景要跟上
        else:
            fps = max(2.0, float(cfg.get("island.blur_fps", 90)))
            # 大岛一直按 blur_fps 抓；小岛 / 中岛原先被 min(fps, 12) 限到 12fps，
            # NativeGlassWindow 的 live 背景纹理跟手性差。液态 + 原生 GPU 可用时放行到
            # 同一高帧档（背景抓屏本身由 DXCam 90fps 供给，不会额外增加折射计算）。
            # 非液态主题 / GPU 初始化失败的 CPU / offscreen 回退保持原 12fps 省电；
            # 全屏隐藏时也没有必要高频抓屏。
            hi_fps = self.expanded or self._gpu_active()
            base = fps if hi_fps else min(fps, 12.0)
            if self._bg_relaxed():
                # 无交互（收起静止 / 光标离岛 120px 外）：背景 30fps 足够。
                # 实测这一档是最大浪费点——90/60fps 抓屏 + 每帧裁切合成常驻吃掉一整核。
                base = min(base, 30.0)
            interval = 1 / base
            if animating and not theme.liquid:
                # 展开 / 收起只是形状在变，身后的画面并没有变。原来这里按 1/40 抓屏，
                # 每次抓屏还会触发一次全窗口重绘，和折射重算叠加就是掉帧的主因。
                interval = max(interval, 1 / 8)
        need = self.path.boundingRect().toAlignedRect().translated(self._win_origin).intersected(self.scr.geometry())
        self.backdrop.liquid = theme.liquid
        # 收起静止、鼠标离岛 200px 以外时，才允许重拍快照（换壁纸 / 关窗口后画面能跟上）。
        # 鼠标在附近或正在悬停展开时一律不动窗口，否则会把悬停打断。
        if (theme.liquid and self.backdrop.live is None and not self.expanded and not animating and self.isVisible()
                and time.perf_counter() - self._plate_at > 60.0
                and self._mouse_far(200.0)):
            self._snap_plate()
        # DWM 亚克力实测模糊半径只有 ~10px，挡不住背后窗口的硬直边（竖条色带还在），
        # 所以不用它，中间那块真模糊改成"藏窗口抓一张整屏快照"再自己糊（见 _snap_plate）。
        want_acr = False
        if want_acr != self.backdrop.acrylic:
            self.backdrop.acrylic = want_acr
            set_acrylic(int(self.winId()), want_acr, ACRYLIC_TINT)
        # 材质分级：收起态是常规面，展开后是浮起卡片，模糊更深一档，层级关系才立得住
        self.backdrop.material = "elevated" if self.expanded else "regular"
        self.backdrop.request(self.scr, g, interval, urgent=not self.backdrop.covers(need))

    def _on_backdrop(self, changed: bool):
        theme.feed_luminance(self.backdrop.luminance)
        # 玻璃边缘定形：背景越亮越依赖"厚度暗侧"。纯白背景下加白高光与背景 1:1 完全不可见，
        # 只有背光侧的压暗能勾出岛体边界。0.40 以下沿用原白刃口观感，0.70 以上暗侧主导，
        # 中间连续过渡（shader 内是乘性压暗，不会跳）。用 theme.lum（EMA 平滑）而非瞬时
        # 采样，避免边缘灰度随抓屏噪声抖动。
        prev = self._light_bg
        self._light_bg = clamp((theme.lum - 0.40) / 0.30, 0.0, 1.0)
        if abs(self._light_bg - prev) > 0.004:
            self.update()
            if self.gpu_view is not None:
                self.gpu_view.update()
        # 背景换了（壁纸 / 切到纯白页面）：导航栏重新判一次亮底反色。
        # 这个方法内部会比对状态，只有真的需要翻色才重绘，高频调用也安全。
        nav = getattr(self, "nav", None)
        if nav is not None:
            nav.refresh_light()
        if not changed:
            return
        if self.gpu_view is not None and self.gpu_view.isVisible():
            self._bd_prev = None
            self._bd_shown = (self.backdrop.state[0], self.backdrop.state[1])
        elif self._bd_shown is not None and self._bd_shown[0] is not self.backdrop.state[0]:
            self._bd_prev = self._bd_shown            # 旧背景淡出、新背景淡入
            self._bd_fade_t0 = time.perf_counter()
        if self.gpu_view is not None and self.gpu_view.isVisible():
            self.gpu_view.update()
        else:
            self._kick()

    # ================================================================ 绘制
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        path = self.path
        if path.isEmpty():
            return
        # 每帧先把上一帧画过的地方清成透明：拖动时本体在窗口内快速移动，上一帧的形状
        # 如果留在透明区域就会变成一串"残影"（Qt 不会替我们擦掉这些像素）。
        # 只清「上一帧 + 这一帧」的外接框，比整块 900×680 省很多。
        box = path.boundingRect().adjusted(-90, -90, 90, 90)
        if self._clear_box is not None:
            box = box.united(self._clear_box)
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(box, QtGui.QColor(0, 0, 0, 0))
        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
        self._clear_box = path.boundingRect().adjusted(-90, -90, 90, 90)
        # 0) iOS 拖动悬浮：整体略微放大 + 上浮 + 随速度轻微倾斜
        p.save()
        lift = clamp(self.lift.x, 0.0, 1.15)
        tilt = self.tilt.x
        if lift > 0.004 or abs(tilt) > 0.02:
            c = self.body.center()
            p.translate(c.x(), c.y() - 4.0 * lift)
            p.rotate(tilt)
            p.scale(1.0 + 0.06 * lift, 1.0 + 0.05 * lift)
            p.translate(-c.x(), -c.y())
        # 1) 柔和阴影（几层半透明描边，廉价近似）：抬起时阴影更大更软
        #    对齐沉浸光感那版：radius 20 / rgba(0,0,0,0.15) / offsetY -4（阴影往上飘一点，
        #    玻璃才像被光从下方托起来的，而不是贴在地上）。
        #    液态主题不再叠加这三层描边阴影：外折射环本身已提供脱离感，再叠阴影反而会在
        #    岛外多出一圈柔和黑边（用户要消除的那种观感）；非液态主题保持原样不变。
        if not theme.liquid:
            sp = path.translated(0, -4.0 + 6.0 * lift)
            k = 1.0                                 # 非液态：维持原有阴影强度（液态分支已关闭）
            for wdt, a in ((20, 9), (12, 13), (6, 22)):
                p.strokePath(sp, QtGui.QPen(QtGui.QColor(0, 0, 0, min(90, int(a * k * (1.0 + 2.4 * lift)))),
                                            wdt * (1.0 + 0.8 * lift)))
        if self.gpu_view is not None and self.gpu_view.isVisible() and self.mode != "drag":
            if self._native_gpu:
                # 玻璃由原生 OpenGL 窗口直接画，主窗这层只剩文字/图标，其余像素是全透明。
                # layered 窗口里 alpha==0 的像素不参与命中测试，于是点击会从岛的正中央
                # 直接穿到下面的 Finder 栏 / 浏览器，表现为"点了没反应"。
                # 在 body 范围铺一层 alpha=1 的极淡底（肉眼不可见），只为了让它能接住点击。
                p.fillPath(path, QtGui.QColor(0, 0, 0, 1))
                self._paint_foreground(p, path)
                # 原生 GPU 路径只走 _paint_foreground，CPU 的 _paint_liquid 那两层
                # （双光源刃口 + 跟手镜面高光）不会执行；在这里补回，对齐菜单的玻璃观感。
                if theme.liquid and self.expanded:
                    self._gpu_liquid_accents(p, path, self.body)
            p.restore()
            p.end()
            return
        self._paint_glass(p, path)
        self._paint_foreground(p, path)
        p.restore()
        p.end()

    def _paint_foreground(self, p: QtGui.QPainter, path: QtGui.QPainterPath):
        bb = self.body
        # 3.5) 液态玻璃大岛：乳白底铺满整个玻璃轮廓，面板本身就是包裹全部组件的那张卡
        if theme.liquid and self.expanded:
            from .liquid import paint_body_fill
            paint_body_fill(p, path, bb)
            # 3.6) 导航条的高斯模糊玻璃胶囊（画在乳白底之上，图标仍由子控件画在最上层）
            self._paint_nav_glass(p)
        # 4) 轮廓：按 Liquid Glass 规范做的「1px Inside 描边 + 135° 对角渐变」
        #    起点（左上迎光角）白 75% → 中点 14% → 终点（右下反光角）38%，
        #    再叠一条 Y=1 / 2px 的白内阴影（35%），在顶部压出一条液态高光线。
        self._paint_edge(p, path, bb)
        self._paint_rest(p, path, bb)

    def _gpu_liquid_accents(self, p: QtGui.QPainter, path: QtGui.QPainterPath,
                            bb: QtCore.QRectF):
        """原生 GPU 前景路径专属：补回 CPU _paint_liquid 里的双光源刃口 + 跟手镜面高光。

        这两层本来只在 _paint_glass → _paint_liquid（CPU 回退）里绘制，原生 GPU 路径
        只调 _paint_foreground，所以展开大岛的菜单级「果冻感」在前景上缺席。这里只叠加
        这两层 2D 前景：不碰 shader / 背景纹理 / 抓屏，且全程裁在轮廓内。惯性跟随复用
        _paint_liquid 的 gp/home/tgt 逻辑——光标离开面板时高光自然回落到 home 点。
        """
        from .liquid import dual_edge, paint_corner_spec, paint_spec
        gp = QtCore.QPointF(QtGui.QCursor.pos()) - QtCore.QPointF(self._win_origin)
        # 光源钉在左下：跟手高光离开面板后回落到左下角（原来是左上，方向与刃口相反）。
        home = QtCore.QPointF(bb.left() + bb.width() * 0.16, bb.bottom() - bb.height() * 0.22)
        tgt = gp if self.body.contains(gp) else home
        prev = getattr(self, "_spec_pt", None)
        self._spec_pt = tgt if prev is None else prev + (tgt - prev) * 0.34
        p.save()
        p.setClipPath(path)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # 刃口：左下最强（124）、右上只留弱轮廓（up_right=0.45），单向光才有"左下打光"的方向感。
        # 只用白色亮边，不按亮底改墨色——那会绕岛一整圈，真机上就是一条黑边。
        p.strokePath(path, QtGui.QPen(QtGui.QBrush(
            dual_edge(bb, 124, 52, up_right=0.45)), 1.3))
        p.restore()
        # 左下角固定高光：跟手光离开后这里仍留一块被照到的亮斑（暗底上是直接亮斑，
        # 亮底上配合 shader 的"左下亮、右上暗"梯度把高光衬出来）。
        paint_corner_spec(p, path, bb)
        # 镜面高光：paint_spec 内部自带 setClipPath，叠在刃口之上
        paint_spec(p, path, bb, self._spec_pt)

    def _paint_glass(self, p: QtGui.QPainter, path: QtGui.QPainterPath, crossfade: bool = True):
        """毛玻璃底 + 色调 + 光泽（灵动岛本体与内容渐显面纱共用）。"""
        base_opacity = p.opacity()
        # 2) 毛玻璃底（新截图与上一张交叉淡入，避免跳变）
        state = self.backdrop.state
        drawn = False
        if theme.liquid and state[0] is not None:
            # 液态玻璃：不是把背景糊上来，而是沿形状边缘做一次位移折射（真折射，不是磨砂）
            # 尺寸动画 / 拖动期间形状每帧都变：不向后台提交精确形状，沿用上一张折射图，
            # 等稳定下来再提交一次（否则后台会被每帧一个新形状压满）。
            animating = self.mode != "anchored" or not (self.sw.rest and self.sh.rest)
            # 圆角必须传真实面板圆角（body_path 用的是 PANEL_R）。
            # 这里原来传 min(w,h)*0.5，SDF 会被算成一个胶囊 / 椭圆，玻璃中间就会冒出一道半圆弧。
            # 形状用**轮廓 bbox** 而不是 body：绘制出来的玻璃边比 body 左右各宽 13px
            # （body_path 的描边外沿），用 body 算 SDF 时折射带整条都缩在里面，看上去
            # 就是"扭曲发生在一个内框里、没贴到最外沿"。注意要和 rect 一样用全局坐标。
            shape = self.path.boundingRect().translated(QtCore.QPointF(self._win_origin))
            got = self.backdrop.liquid_image(
                shape, panel_radius(shape.width(), shape.height()), self._win_origin,
                animate=animating)
            br = None
            if got is not None:
                # 不能用纹理画刷铺折射图：QBrush 是"图案"，图没盖住的区域会被平铺/留空。
                # 这里直接按矩形 1:1 画图并裁到轮廓（不拉伸，理由见下面 tgt 那段）。
                img, grect = got
                p.save()
                p.setClipPath(path)
                tgt = QtCore.QRectF(grect.x() - self._win_origin.x(), grect.y() - self._win_origin.y(),
                                    grect.width(), grect.height())
                need = path.boundingRect()
                # 图盖不住面板时**绝对不能**把图拉伸成 need 去凑满：面板贴着屏幕顶边，
                # 抓屏矩形被裁到 y>=0，grect 的上边比轮廓 bbox 差 1~2px，这段判断就永远成立，
                # 于是 960x592 的图被硬压成 666x335 —— 横向挤 1.44 倍、纵向挤 1.77 倍，
                # 背景跟着放大错位，折射带也按同一比例被缩放、整体缩进面板内部。
                # 改成 1:1 落图：差出来的那几像素在面板最外沿，还被轮廓裁掉，根本看不见。
                if tgt.width() >= need.width() * 0.55 and tgt.height() >= need.height() * 0.55:
                    # 1) 底层：全分辨率背景 1:1 落图（Source 写死 alpha，玻璃层不透明，
                    #    否则 DWM 会把"玻璃层 + 背后真实窗口"再混一次）。
                    hi, hirect = self.backdrop.hi, self.backdrop.hi_rect
                    p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Source)
                    if hi is not None and not hi.isNull() and not hirect.isEmpty():
                        hi_tgt = QtCore.QRectF(hirect.x() - self._win_origin.x(),
                                               hirect.y() - self._win_origin.y(),
                                               hirect.width(), hirect.height())
                        p.drawImage(hi_tgt, hi)
                        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
                        # 2) 折射带：只有那一圈有 alpha，叠上去以后中间仍是原像素
                        p.drawImage(tgt, img)
                    else:
                        # 没有全分辨率副本（抓屏兜底路径）就只能整张铺
                        p.drawImage(tgt, img)
                        p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
                    drawn = True
                p.restore()
            else:
                shape = self.path.boundingRect()
                br = self.backdrop.brush_liquid(
                    shape.translated(QtCore.QPointF(self._win_origin)),
                    panel_radius(shape.width(), shape.height()), self._win_origin,
                    animate=animating)
            fade = 1.0
        else:
            br = self.backdrop.brush_for(state, self._win_origin)
            fade = (time.perf_counter() - self._bd_fade_t0) / 0.25 if self._bd_prev is not None else 1.0
        if fade < 1.0:
            prev = self.backdrop.brush_for(self._bd_prev, self._win_origin)
            if prev is not None:
                p.fillPath(path, prev)
            if br is not None:
                p.setOpacity(base_opacity * max(0.0, fade))
                p.fillPath(path, br)
                p.setOpacity(base_opacity)
        else:
            if crossfade:
                self._bd_prev = None
            if br is not None:
                p.fillPath(path, br)
            elif not drawn:
                p.fillPath(path, QtGui.QColor(128, 128, 128, 200))
        if crossfade:
            self._bd_shown = state
        # 2.5) 沉浸光感：材质膜 + 主题色晕 + 顶部反射 + 底部微光分割线
        if theme.liquid and drawn:
            self._paint_immersive(p, path, self.body)
        # 3) 色调 + 纵向光泽
        p.fillPath(path, theme.tint_brush(self.body))
        bb = self.body
        if not theme.liquid:
            # 液态玻璃的霜层已在 tint 里，不再叠纵向白光，避免发灰
            g = QtGui.QLinearGradient(0, bb.top(), 0, bb.bottom())
            g.setColorAt(0, QtGui.QColor(255, 255, 255, 26 if not theme.dark else 14))
            g.setColorAt(0.5, QtGui.QColor(255, 255, 255, 0))
            g.setColorAt(1, QtGui.QColor(255, 255, 255, 10))
            p.fillPath(path, g)
        if theme.liquid:
            self._paint_liquid(p, path, bb)

    EDGE_STOPS = ((0.0, 0.76), (0.5, 0.14), (1.0, 0.38))   # 135° 对角：左上 76% → 中点 14% → 右下 38%
    EDGE_TOP_GLOW = 35                                     # 顶部液态高光线（白 35%）

    def _paint_edge(self, p: QtGui.QPainter, path: QtGui.QPainterPath, bb: QtCore.QRectF):
        """Liquid Glass 的立体边缘：1px Inside 描边 + 135° 对角渐变 + 顶部液态高光。

        Qt 没有 Figma 那种 blur 内阴影，这里用「轮廓下移 1/2/3px、alpha 递减」三层描边
        近似 Y=1 / Blur=2 的效果，再裁在路径内，所以只在顶部压出一条丝滑的高光线。
        """
        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        if theme.liquid:
            p.setClipPath(path)
            # 保持原来的白刃口。这里不再按背景亮度改成墨色：那会绕岛一整圈，真机上读起来
            # 就是一条黑边。亮底上的定形交给 shader 的方向性受光（左下高光 / 背光侧轻压暗），
            # 2D 层只负责玻璃的亮面高光。
            p.strokePath(path.translated(0, 0.8), QtGui.QPen(QtGui.QColor(255, 255, 255, 46), 0.8))
            p.restore()
            return
        g = QtGui.QLinearGradient(bb.topLeft(), bb.bottomRight())      # 左上 → 右下 = 135°
        for pos, a in self.EDGE_STOPS:
            g.setColorAt(pos, QtGui.QColor(255, 255, 255, int(round(255 * a))))
        p.strokePath(path, QtGui.QPen(QtGui.QBrush(g), 1.0))
        p.setClipPath(path)
        for dy, wid, alpha in ((1.0, 1.2, self.EDGE_TOP_GLOW), (2.0, 2.4, 16), (3.2, 3.6, 7)):
            p.strokePath(path.translated(0, dy),
                         QtGui.QPen(QtGui.QColor(255, 255, 255, alpha), wid))
        p.restore()

    def _nav_strip_rect(self) -> QtCore.QRectF | None:
        """导航条玻璃胶囊的矩形（窗口内坐标）：两端贴紧最左页签与最右按钮，不铺满整条。"""
        nav = getattr(self, "nav", None)
        if nav is None or not nav.isVisible() or nav.width() < 40:
            return None
        cap = nav.capsule_rect()
        o = nav.mapTo(self, QtCore.QPoint(0, 0))
        return QtCore.QRectF(o.x() + cap.x(), o.y() + cap.y(), cap.width(), cap.height())

    def _paint_nav_glass(self, p: QtGui.QPainter):
        """导航条的高斯模糊玻璃条。

        取样用的是全分辨率快照 `backdrop.hi`（不是把已经画好的自己再糊一遍），
        模糊只作用在图标**下面**那层像素；图标是子控件绘制的，始终清晰。
        半径 = 半高，整条是胶囊，和 18% 的面板圆角形成一大一小。
        """
        if not theme.liquid:
            return
        r = self._nav_strip_rect()
        if r is None:
            return
        hi, hr = self.backdrop.hi, self.backdrop.hi_rect
        if hi is None or hi.isNull() or hr.isEmpty():
            return
        s = hi.width() / max(1.0, float(hr.width()))          # 每逻辑像素几个物理像素
        g = r.translated(QtCore.QPointF(self._win_origin))
        sub = QtCore.QRectF((g.x() - hr.x()) * s, (g.y() - hr.y()) * s,
                            g.width() * s, g.height() * s).toAlignedRect()
        sub = sub.intersected(QtCore.QRect(0, 0, hi.width(), hi.height()))
        if sub.isEmpty() or sub.width() < 8:
            return
        src = hi.copy(sub)
        k = NAV_GLASS_BLUR
        mid = src.scaled(max(2, int(src.width() / 3)), max(2, int(src.height() / 3)),
                         QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                         QtCore.Qt.TransformationMode.SmoothTransformation)
        small = mid.scaled(max(2, int(src.width() / k)), max(2, int(src.height() / k)),
                           QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                           QtCore.Qt.TransformationMode.SmoothTransformation)
        cap = QtGui.QPainterPath()
        cap.addRoundedRect(r, r.height() / 2, r.height() / 2)
        p.save()
        p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
        p.setClipPath(cap)
        p.setOpacity(0.93)
        p.drawImage(r, small)                                  # 放大回去 = 高斯雾化
        p.setOpacity(1.0)
        p.fillPath(cap, QtGui.QColor(255, 255, 255, NAV_GLASS_TINT))
        p.setClipping(False)
        rr = r.height() / 2
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 84), 1.4))
        top = QtGui.QPainterPath()
        top.moveTo(r.x() + rr, r.y() + 0.8)
        top.lineTo(r.right() - rr, r.y() + 0.8)
        p.drawPath(top)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 30), 1.0))
        p.drawPath(cap)
        p.restore()

    def _paint_immersive(self, p: QtGui.QPainter, path: QtGui.QPainterPath, bb: QtCore.QRectF):
        """沉浸光感（HarmonyOS `systemMaterialEffect.IMMERSIVE` 的三层合成）。

        ArkUI 那边是「backgroundBlurStyle 磨砂底 + 主题色微光晕染 + 顶部线性高光」叠出来的，
        再配一条底部微光分割线。Windows 上没有系统级 backdropBlur，所以磨砂底由
        `glass._frost` 自己算（见 `_capture`），这里只负责它上面那三层。
        """
        pal = theme.pal
        gp = QtCore.QPointF(QtGui.QCursor.pos()) - QtCore.QPointF(self._win_origin)
        hovered = self.body.contains(gp)
        # 1) 材质膜：三档通透感（强 0.85 / 平衡 0.70 / 弱 0.55，配置 island.mat_level）。
        #    鼠标进面板时上浮一档，对应文章里 onHover 把透明度 +0.1 —— 玻璃"被摸到"时更实。
        lvl = str(cfg.get("island.mat_level", "balanced"))
        film = {"strong": 76, "balanced": 48, "weak": 20}.get(lvl, 48)
        if hovered:
            film = min(76, film + 12)
        p.fillPath(path, QtGui.QColor(255, 255, 255, film))
        # 2) 主题色晕：从面板上部中心往外散，展开态（焦点）更亮
        hot = self.expanded
        c = QtGui.QColor(*(pal.get("bloom" if hot else "bloom_idle", (120, 170, 255, 20))))
        # 展开瞬间的光脉冲：300ms 内从峰值线性回落到常态（对应 triggerLightPulse）
        dt = time.perf_counter() - getattr(self, "_pulse_t0", -9.0)
        pulse = 0.0 if dt <= 0.0 or dt >= 0.30 else 1.0 - dt / 0.30
        if pulse > 0.0:
            c = QtGui.QColor(c.red(), c.green(), c.blue(),
                             min(255, c.alpha() + int(30 * pulse)))
        rad = QtGui.QRadialGradient(
            QtCore.QPointF(bb.center().x(), bb.top() + bb.height() * 0.18),
            max(bb.width(), bb.height()) * 0.8)
        rad.setColorAt(0.0, c)
        rad.setColorAt(1.0, QtGui.QColor(c.red(), c.green(), c.blue(), 0))
        p.fillPath(path, rad)
        # 3) 顶部反射渐变：改成左下 / 右上对角双光（两端亮、中间暗）
        from .liquid import dual_edge
        t = QtGui.QColor(*pal.get("reflect", (255, 255, 255, 38)))
        p.fillPath(path, dual_edge(bb, t.alpha(), int(t.alpha() * 0.35)))

    def _paint_liquid(self, p: QtGui.QPainter, path: QtGui.QPainterPath, bb: QtCore.QRectF):
        """液态玻璃的光学层：6 层静态渐变预渲染成一张透明图，每帧只贴图 + 画跟手高光。

        展开大岛时这 6 层（多次复杂路径的渐变描边）要 6~7ms，鼠标在面板里转圈每帧重画
        就会把 60fps 的预算吃光；形状 / 主题不变时它们其实是完全静止的。
        """
        from .liquid import paint_spec, paint_static_layers
        gp = QtCore.QPointF(QtGui.QCursor.pos()) - QtCore.QPointF(self._win_origin)
        # 光源钉在左下，与刃口方向一致（原来回落到左上，光会从两个角分别打）。
        home = QtCore.QPointF(bb.left() + bb.width() * 0.16, bb.bottom() - bb.height() * 0.22)
        tgt = gp if self.body.contains(gp) else home
        prev = getattr(self, "_spec_pt", None)
        self._spec_pt = tgt if prev is None else prev + (tgt - prev) * 0.34
        br = path.boundingRect()
        r = br.adjusted(-10, -10, 10, 10).toAlignedRect().intersected(self.rect())
        if r.isEmpty():
            from .liquid import paint_layers
            paint_layers(p, path, bb, self._spec_pt)
            return
        key = (theme.pal_name, r.x(), r.y(), r.width(), r.height(),
               round(bb.x(), 1), round(bb.y(), 1), round(bb.width(), 1), round(bb.height(), 1),
               round(br.x(), 1), round(br.y(), 1), round(br.width(), 1), round(br.height(), 1))
        if key != self._lg_key or self._lg_img is None:
            img = QtGui.QImage(r.size(), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            img.fill(Qt.GlobalColor.transparent)
            qp = QtGui.QPainter(img)
            qp.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            qp.translate(-r.x(), -r.y())
            # 刃口保持白色：不按亮底改墨色，否则绕岛一整圈会变成黑边。
            paint_static_layers(qp, path, bb)
            qp.end()
            self._lg_img = img
            self._lg_key = key
        # 缓存图按 r 拉满贴：缓存图若是上一帧的尺寸，按原点贴会露出一块硬边
        p.drawImage(QtCore.QRectF(r), self._lg_img)
        # 轮廓高光：由位移向量场推导的非对称刃光（左上强 / 右下弱），比均匀描边更接近苹果的原味
        glow = self.backdrop.glow
        if glow is not None:
            state = self.backdrop.state
            if state[0] is not None:
                rect = state[1]
                p.save()
                p.setClipPath(path)
                tr = QtGui.QTransform()
                tr.translate(rect.x() - self._win_origin.x(), rect.y() - self._win_origin.y())
                tr.scale(rect.width() / glow.width(), rect.height() / glow.height())
                p.setTransform(tr, True)
                p.drawImage(0, 0, glow)
                p.restore()
        paint_spec(p, path, bb, self._spec_pt)

    def _paint_rest(self, p: QtGui.QPainter, path: QtGui.QPainterPath, bb: QtCore.QRectF):
        # 5) 常态动画：沿边缘缓慢游走的流光
        t = time.perf_counter() - self._t0
        if not self.expanded:
            ph = (math.sin(t * 0.55) * 0.5 + 0.5)
            far_y = bb.bottom() if self.edge != "bottom" else bb.top()
            pt = QtCore.QPointF(bb.left() + bb.width() * ph, far_y)
            if self.edge in ("left", "right"):
                pt = QtCore.QPointF(bb.right() if self.edge == "left" else bb.left(), bb.top() + bb.height() * ph)
            rad = QtGui.QRadialGradient(pt, max(60.0, bb.width() * 0.35))
            rad.setColorAt(0, QtGui.QColor(255, 255, 255, 80 if not theme.dark else 55))
            rad.setColorAt(1, QtGui.QColor(255, 255, 255, 0))
            p.strokePath(path, QtGui.QPen(QtGui.QBrush(rad), 1.0))
        # 6) 收起状态内容
        if self.compact_a.x > 0.01:
            pk = clamp(self.poke.x, -0.5, 1.2) if (self.mode == "anchored" and not self.expanded) else 0.0
            _horiz = self.edge in ("top", "bottom")
            _cu = bb.center().x() if _horiz else bb.center().y()
            _half = max(1.0, (bb.width() if _horiz else bb.height()) / 2)
            _pp = self._poke_sm - QtCore.QPointF(self._win_origin)
            _rel = clamp(((_pp.x() if _horiz else _pp.y()) - _cu) / _half, -1.0, 1.0) if pk > 0.005 else 0.0
            self.compact.press = (max(0.0, pk), _rel)
            horiz = self.edge in ("top", "bottom")
            self.compact.squash = ((1 + 0.05 * pk, 1 - 0.16 * pk) if horiz else (1 - 0.16 * pk, 1 + 0.05 * pk))
            p.save()
            p.setClipPath(path)               # 内容（含表情）不超出灵动岛
            s = self.compact.ui_scale
            c = bb.center()
            if abs(s - 1.0) > 0.001:
                # 内部仍按原始坐标绘制，整体放大后正好填满已缩放的 body
                p.translate(c.x(), c.y())
                p.scale(s, s)
                p.translate(-c.x(), -c.y())
                raw = QtCore.QRectF(c.x() - bb.width() / (2 * s), c.y() - bb.height() / (2 * s),
                                    bb.width() / s, bb.height() / s)
            else:
                raw = bb
            self.compact.paint(p, raw, self.compact_a.x,
                               self._pk() if self.compact.mode() == "media" else 0.0)
            p.restore()
            # 播放键命中区是 compact 用原始坐标记的，映射回窗口坐标才能点中
            pr = self.compact.play_rect
            if pr is not None and abs(s - 1.0) > 0.001:
                self.compact.play_rect = QtCore.QRectF(
                    c.x() + (pr.x() - c.x()) * s, c.y() + (pr.y() - c.y()) * s,
                    pr.width() * s, pr.height() * s)

    # ================================================================ 鼠标
    def _pk(self) -> float:
        """音乐律动强度（0..1）：瞬时峰值包络 + 自动增益。

        系统 meter 的 GetPeakValue 是线性值，普通音乐大多只到 0.05~0.4，
        直接乘系数会让柱条"跳不起来"。这里取 attack 瞬时 / release 慢衰，
        再用近 2.5 秒的最大值做归一，使任意音量下都能跳到满幅。
        """
        try:
            raw = float(self.peak_fn())
        except Exception:  # noqa: BLE001
            raw = 0.0
        raw = max(0.0, min(1.0, raw))
        now = time.monotonic()
        dt = now - self._pk_t if self._pk_t else 0.0
        dt = max(0.0, min(dt, 0.05))
        self._pk_t = now
        if dt > 0.0:
            self._pk_env = max(raw, self._pk_env * math.exp(-dt / 0.30))
            self._pk_hi = max(self._pk_env, self._pk_hi * math.exp(-dt / 2.5))
        else:
            self._pk_env = max(raw, self._pk_env)
        self._pk_hi = max(self._pk_hi, 0.05)
        if self._pk_env < 0.012:          # 静音时不要放大底噪
            return 0.0
        return clamp(self._pk_env / self._pk_hi, 0.0, 1.0) ** 0.85

    def _inside(self, gp: QtCore.QPoint) -> bool:
        lp = QtCore.QPointF(gp - self._win_origin)
        if self.path.contains(lp):
            return True
        # 拖动抬起时本体被放大，命中区跟着放宽，避免边缘"抓不住"
        m = 4.0 + 12.0 * clamp(self.lift.x, 0.0, 1.0)
        return self.body.adjusted(-m, -m, m, m).contains(lp)

    def _mouse_far(self, gap: float) -> bool:
        """光标是否离整个窗口（含透明边距）至少 gap 个逻辑像素之外。"""
        gp = QtGui.QCursor.pos()
        r = self.geometry().adjusted(-gap, -gap, gap, gap)
        return not r.contains(gp)

    def _popup_open(self) -> bool:
        """是否有本应用弹出的二级层正在显示（QMenu / CCPanel / LookupPopup）。

        这些弹层本来就该盖在岛上面。若此时还把岛抬到置顶组最前，岛上的一级按钮就会
        反过来压住菜单 —— 表现正是「二级菜单碰到一级按钮，一级按钮又透出来了」。
        """
        try:
            if QtWidgets.QApplication.activePopupWidget() is not None:
                return True
            for w in QtWidgets.QApplication.topLevelWidgets():
                if w is self or not w.isVisible():
                    continue
                if isinstance(w, QtWidgets.QMenu):
                    return True
                if type(w).__name__ in ("CCPanel", "LookupPopup"):
                    return True
        except Exception:  # noqa: BLE001
            pass
        return False

    def _raise_topmost(self):
        """把自己提到置顶窗口组的最前面。

        MyDockFinder 的顶栏也是置顶窗口：用户点一下 Finder 栏后它会被提到我们前面，
        灵动岛就被压住、点不动也不再展开。这里不动焦点、不改尺寸，只把 z-order 拉回来。
        """
        # 有二级弹层时绝不能抬岛：否则会把本该盖在岛上的菜单压回去，一级按钮透出。
        if self._popup_open():
            return
        hwnd = int(self.winId())
        try:
            # 关键：HWND_TOPMOST 是 64 位 (HWND)-1（见常量定义）。之前传裸 -1 被 ctypes
            # 截成 0xFFFFFFFF，SetWindowPos 一直静默失败，于是 Finder 栏压住后点不动。
            # SetWindowPos 一次就放回 topmost 组最前；SWP_NOACTIVATE 保证不抢焦点。
            ok = user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
            if not ok:
                user32.BringWindowToTop(hwnd)
            # 原生 OpenGL 背景窗是独立顶层窗口，只抬 self 会让玻璃层留在 Finder 栏下面：
            # 收起态看着"顶部被 Finder 盖住"，点击也像没反应。把它紧跟插到 self 之后，
            # 两者都在 topmost 组里、Finder 之上。
            gpu = getattr(self, "gpu_view", None)
            if gpu is not None:
                try:
                    user32.SetWindowPos(int(gpu.winId()), hwnd, 0, 0, 0, 0,
                                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER)
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass

    def _covered(self, gp: QtCore.QPoint | None = None) -> bool:
        """光标当前是否命中了别人（而不是灵动岛本身）。

        WindowFromPoint 收的是**物理**像素，QCursor.pos()/QWidget.mapToGlobal 给的是
        逻辑坐标；高 DPI 缩放下直接把逻辑坐标传进去会命中屏幕上的错误位置，遮挡检测
        因此失效。不传坐标时用 Win32 GetCursorPos 直接拿物理坐标（多屏异 DPI 也准）。
        """
        try:
            hwnd = int(self.winId())
            if gp is None:
                pt = wintypes.POINT()
                if not user32.GetCursorPos(ctypes.byref(pt)):
                    return False
            else:
                scr = QtGui.QGuiApplication.screenAt(gp) or self.scr
                dpr, g = scr.devicePixelRatio(), scr.geometry()
                pt = wintypes.POINT(round(g.x() + (gp.x() - g.x()) * dpr),
                                    round(g.y() + (gp.y() - g.y()) * dpr))
            hit = user32.WindowFromPoint(pt)
            if not hit:
                return False
            return int(hit) != hwnd and int(user32.GetAncestor(hit, 2)) != hwnd
        except Exception:  # noqa: BLE001
            return False

    def _poll_hover(self):
        # 输入框的键盘焦点：切到别的窗口后立即释放，否则会一直保持展开
        if "focus" in self.locks and user32.GetForegroundWindow() != int(self.winId()):
            self._prev_fg = None
            self.release_focus()
        if self._fs_hidden or self.mode != "anchored":
            self._hover_since = self._out_since = None
            return
        if self._snapping:
            # 抓整屏快照的那 30ms 窗口被挪出了屏幕，这一帧的"在不在岛上"不可信，直接跳过
            self._hover_since = self._out_since = None
            return
        inside = self._inside(QtGui.QCursor.pos())
        now = time.monotonic()
        if theme.liquid and self.expanded and inside:
            gp = QtGui.QCursor.pos()
            if gp != self._spec_pos:
                self._spec_pos = gp
                self._spec_until = time.perf_counter() + 0.30
                self._kick()                 # 停稳 0.3s 后 _needs_frames 自动放回空闲
        if inside and not self.passthrough():
            # 光标刚进入岛：先无条件抬一次，保证紧接着的点击不会赶在 Finder 栏置顶之后被吞。
            # 之后靠命中测试兜底：Finder 栏每次把自己置顶，最多 150ms 就拉回来。
            if not getattr(self, "_was_inside", False):
                self._raise_t = now
                self._raise_topmost()
            self._was_inside = True
            if now - getattr(self, "_raise_t", 0.0) > 0.15 and self._covered():
                self._raise_t = now
                self._raise_topmost()
        else:
            self._was_inside = False
        if self.expanded and not self.passthrough():
            # 展开态还要盯住整块面板：豆包 / 编辑器这类自己也置顶的窗口被拉到前面时，
            # 会把面板下半截盖住，看起来就是"玻璃没铺满 + 一块清晰的脏背景"。
            gp2 = self.mapToGlobal(QtCore.QPoint(int(self.body.center().x()), int(self.body.center().y())))
            if now - getattr(self, "_raise_t2", 0.0) > 0.3 and self._covered(gp2):
                self._raise_t2 = now
                self._raise_topmost()
        if self.compact.bar_mode and not self.expanded:
            # 栏内单行：鼠标一进来先向下展开成三行歌词（给即时反馈），
            # 停留超过 hover_expand_ms 仍然照常弹出整个面板——悬停展开不能再被栏模式吃掉。
            want = inside and not self.passthrough()
            if want != self.compact.bar_open:
                self.compact.bar_open = want
                self._kick()
        if not self.expanded and self.mode == "anchored" and not self._fs_hidden:
            # 收起时（任何展开方式）：鼠标靠近就把水滴"挤"一下，离开后带回弹地恢复
            # 只有鼠标进入灵动岛范围才挤压；越靠近中心挤压越强（边缘处几乎不变形）。
            # 靠近但没碰到时只有表情变化（由小形象自己处理），不挤压。
            gp = QtCore.QPointF(QtGui.QCursor.pos())
            lp = gp - QtCore.QPointF(self._win_origin)
            b = self.body
            if b.contains(lp):
                nx = (lp.x() - b.center().x()) / max(1.0, b.width() / 2)
                ny = (lp.y() - b.center().y()) / max(1.0, b.height() / 2)
                depth = 1.0 - min(1.0, math.hypot(nx, ny))           # 0 = 边缘，1 = 中心
                target = depth ** 1.4
                self._poke_pt = gp
                if abs(self.poke.target - target) > 0.01:
                    self.poke.to(target, 260, 0.75)
                    self._kick()
            elif self.poke.target != 0.0:
                self.poke.to(0.0, 300, 0.22)          # 欠阻尼：弹回时会外鼓几下
                self._kick()
        on_btn = inside and self._on_play_button(QtCore.QPointF(QtGui.QCursor.pos()) - QtCore.QPointF(self._win_origin))
        hv = 1.0 if on_btn and not self.passthrough() else 0.0
        if abs(self.compact.play_hover - hv) > 0.01:
            self.compact.play_hover += (hv - self.compact.play_hover) * 0.5
            self._kick()
        if on_btn and not self.expanded:
            self._hover_since = None              # 在播放键上停留不展开
            return
        if inside and self.passthrough():
            inside = False                        # 可穿透：鼠标视为不在灵动岛上（只响应右键）
            self._hover_since = None
            if not self.expanded:
                return
        if inside:
            self._out_since = None
            if not self.expanded and self.expand_mode() != "never":
                # hover_expand_ms <= 0：关闭「悬停 N 秒自动放大岛」，只有点击才展开
                ms = int(cfg.get("island.hover_expand_ms", 5000) or 0)
                if ms <= 0:
                    self._hover_since = None
                elif self._hover_since is None:
                    self._hover_since = now
                elif (now - self._hover_since) * 1000 >= ms \
                        and not (user32.GetAsyncKeyState(0x01) & 0x8000):
                    self._hover_since = None
                    self.expand()
        else:
            self._hover_since = None
            if self.expanded:
                if self.locks or self.pinned():
                    self._out_since = None
                    return
                if self._out_since is None:
                    self._out_since = now
                elif (now - self._out_since) * 1000 >= cfg.get("island.collapse_delay_ms", 450):
                    self._out_since = None
                    self.collapse()

    def mousePressEvent(self, e):
        if not self._inside(e.globalPosition().toPoint()):
            e.ignore()
            return
        if e.button() == Qt.MouseButton.LeftButton:
            self._press = e.position()
            self._press_g = e.globalPosition()      # 判拖动用屏幕坐标：窗口自己会动，局部坐标不可靠
        elif e.button() == Qt.MouseButton.RightButton:
            self.menu_requested.emit(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        # 按住并移动即开始拖动（不需要长按）；固定时不允许拖动。
        # 用全局坐标 + 10px 阈值：鼠标抖动不该被当成拖动，而且灵动岛收起/展开时
        # 窗口本身会移动，局部坐标会跟着跳，会把一次普通点击误判成拖动。
        gd = e.globalPosition() - (self._press_g if self._press_g is not None
                                   else e.globalPosition())
        if self._press is not None and gd.manhattanLength() > 10:
            self.lp_timer.stop()
            self._press = None
            self._press_g = None
            self.begin_drag(QtGui.QCursor.pos())

    def _on_play_button(self, local: QtCore.QPointF) -> bool:
        r = self.compact.play_rect
        return (r is not None and not self.expanded and self.compact.mode() == "media"
                and r.adjusted(-6, -8, 6, 8).contains(local))

    _CLICK_WIDGETS = (QtWidgets.QAbstractButton, QtWidgets.QSlider, QtWidgets.QLineEdit,
                      QtWidgets.QTextEdit, QtWidgets.QComboBox, QtWidgets.QScrollArea)

    def _on_control(self, local: QtCore.QPointF) -> bool:
        """落点是不是面板里的控件（按钮 / 滑块 / 输入框）。控件自己处理点击时不能顺手收起。"""
        w = self.childAt(local.toPoint())
        while w is not None and w is not self:
            if isinstance(w, self._CLICK_WIDGETS):
                return True
            w = w.parentWidget()
        return False

    def mouseReleaseEvent(self, e):
        self._press_g = None
        self.lp_timer.stop()
        if self._press is not None and self._on_play_button(e.position()) and self._on_play_button(self._press):
            self._press = None
            self.play_pause_requested.emit()
            return
        if self._press is not None and self.expanded and not self.pinned() \
                and self._inside(e.globalPosition().toPoint()) and not self._on_control(e.position()) \
                and time.monotonic() - self._expanded_at > 0.25:
            # 已展开时再点空白处：收回去（刚由单击展开的这 0.25s 不算，避免同一下点击又收起）
            self._press = None
            self.collapse()
            return
        if self._press is not None and self.mode == "anchored" and not self.expanded \
                and self.expand_mode() == "never":
            # 长关状态下单击没有反应，给一句提示，避免以为程序卡死
            self.activity({"glyph": G.CHECK, "title": "已关闭自动展开", "sub": "双击灵动岛恢复"}, 2.6)
        elif self._press is not None and self.mode == "anchored" and not self.expanded \
                and self.expand_mode() != "never":
            self._single_click()          # 单击立刻放大，不再等双击判定窗口（等 500ms 会像"没反应"）
        self._press = None

    def _single_click(self):
        if self.mode == "anchored" and not self.expanded and self.expand_mode() != "never":
            self.expand()
            self._expanded_at = time.monotonic()   # 记录"刚放大"，用来挡掉紧随其后的双击判定
            self.locks.add("pin")
            QtCore.QTimer.singleShot(600, lambda: self.locks.discard("pin"))

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._on_play_button(e.position()):
            self.play_pause_requested.emit()       # 快速连点播放键：当作第二次点击，不切换长关
            return
        if e.button() == Qt.MouseButton.LeftButton and self._inside(e.globalPosition().toPoint()):
            self._click_timer.stop()
            self._press = None
            if self.expand_mode() == "never":
                # 长关状态下双击 = 恢复悬停展开（收起态单击不会再展开，没有这个出口就只能去托盘改）
                self.set_expand_mode("hover")
                self.expand()
                self.activity({"glyph": G.CHECK, "title": "已恢复悬停展开"}, 2.2)
                return
            if not self.expanded:
                return                             # 收起态的双击只是"打开"，不改展开模式
            if time.monotonic() - getattr(self, "_expanded_at", -10.0) < 1.2:
                return                             # 刚由单击放大，这一下只是手快点快了，别切长关
            self.toggle_long_off()

    def toggle_long_off(self):
        """双击：悬停展开 ↔ 长关（常驻展开时双击也切到长关）。"""
        new = "hover" if self.expand_mode() == "never" else "never"
        self.set_expand_mode(new)
        if new == "never" and self.expanded:
            # 双击长关：立即收起，不等鼠标移出；也不显示任何提示文字
            self.locks.discard("pin")
            self.release_focus()
            self.collapse()
        if new == "never":
            # 明确提示一下，否则收起态点击没反应会像"程序坏了"
            self.activity({"glyph": G.CHECK, "title": "已关闭自动展开", "sub": "双击灵动岛恢复"}, 3.0)

    def _long_press(self):
        pass

    # ---------------- 穿透模式 ----------------
    def passthrough(self) -> bool:
        return bool(cfg.get("island.passthrough", False))

    def set_passthrough(self, on: bool):
        cfg.set("island.passthrough", bool(on))
        self._apply_passthrough()
        if on and self.expanded and not self.pinned():
            self.collapse()
        self.passthrough_changed.emit(bool(on))

    def _apply_passthrough(self):
        """穿透 = 鼠标完全穿过（WS_EX_TRANSPARENT），只靠钩子响应右键。"""
        hwnd = int(self.winId())
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        on = self.passthrough()
        transparent = on
        ex = (ex | WS_EX_TRANSPARENT) if transparent else (ex & ~WS_EX_TRANSPARENT)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)
        if on:
            self._rhook.install()
        else:
            self._rhook.remove()

    def capture_visible(self) -> bool:
        return not bool(cfg.get("island.exclude_from_capture", False))

    def set_capture_visible(self, on: bool):
        cfg.set("island.exclude_from_capture", not on)
        self.apply_capture_mode()

    def apply_capture_mode(self):
        """参与屏幕捕获：截图 / 录屏里能看到灵动岛；不参与：永远排除（截图里看不到）。

        注意：取背景时**不再**临时排除自己。实测（Win11）排除期间 GDI 截屏会把整块窗口
        矩形拍成纯黑 —— 连透明边距也一起黑掉，背景就只剩一圈死黑。现在改成"不排除"，
        拍到的是自家上一帧，但窗口外那一圈像素是真的：`Backdrop.hole` 会把自家矩形用
        四周颜色扩散补掉，折射取样点朝外、正好落在真实像素上。
        """
        hwnd = int(self.winId())
        visible = self.capture_visible()
        # WGC honors WDA_EXCLUDEFROMCAPTURE, giving the lens the real pixels
        # behind the island instead of a stale self-portrait. Other themes
        # retain the user's screen-recording visibility preference.
        # island.capture_self=True：液态主题下也解除排除，方便截图/录屏展示界面
        # （代价是玻璃背景会取到自家上一帧，只在需要出图时打开）。
        allow_shot = bool(cfg.get("island.capture_self", False))
        exclude_from_capture(hwnd, not visible or (theme.liquid and not allow_shot))
        self.backdrop.hwnd = hwnd
        self.backdrop.self_exclude = False
        # 玻璃层是独立窗口，捕获属性要单独同步一次，否则切换后它还留在旧状态
        gpu = getattr(self, "gpu_view", None)
        if gpu is not None:
            try:
                gpu.sync_geometry()
            except Exception:  # noqa: BLE001
                pass

    def expand_mode(self) -> str:
        m = cfg.get("island.expand_mode")
        if m not in ("hover", "always", "never"):
            m = "always" if cfg.get("island.pinned", False) else "hover"
        return m

    def set_expand_mode(self, mode: str):
        """hover = 鼠标悬停展开、离开收起；always = 一直展开；never = 一直收起（悬停 / 单击都不展开）。"""
        if mode not in ("hover", "always", "never"):
            return
        cfg.set("island.expand_mode", mode, save=False)
        cfg.set("island.pinned", mode == "always")
        if mode == "always":
            self.expand()
        elif mode == "never":
            # 不立即收起：鼠标离开灵动岛后才收起（之后悬停 / 单击都不再展开）
            self.locks.discard("pin")
            if not self._inside(QtGui.QCursor.pos()):
                self.collapse()
        self.mode_changed.emit(mode)
        self.pin_changed.emit(mode == "always")

    def pinned(self) -> bool:
        return self.expand_mode() == "always"

    def set_pinned(self, on: bool):
        self.set_expand_mode("always" if on else "hover")
        return

    def _set_pinned_old(self, on: bool):
        """图钉：保持展开（不会因鼠标移开而收起），仍可拖动。"""
        cfg.set("island.pinned", bool(on))
        if on and not self.expanded:
            self.expand()
        self.pin_changed.emit(bool(on))

    def wheelEvent(self, e):
        if not self.expanded:
            self.wheel_compact.emit(1 if e.angleDelta().y() > 0 else -1)

    # ================================================================ 焦点（输入框需要键盘）
    def request_focus(self):
        hwnd = int(self.winId())
        fg = user32.GetForegroundWindow()
        if fg and fg != hwnd:
            self._prev_fg = fg
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex & ~WS_EX_NOACTIVATE)
        cur = user32.GetCurrentThreadId() if hasattr(user32, "GetCurrentThreadId") else ctypes.windll.kernel32.GetCurrentThreadId()
        fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        if fg_tid and fg_tid != cur:
            user32.AttachThreadInput(cur, fg_tid, True)
        user32.SetForegroundWindow(hwnd)
        self.activateWindow()
        if fg_tid and fg_tid != cur:
            user32.AttachThreadInput(cur, fg_tid, False)
        self.locks.add("focus")

    def release_focus(self):
        if "focus" not in self.locks:
            return
        self.locks.discard("focus")
        hwnd = int(self.winId())
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE)
        fw = QtWidgets.QApplication.focusWidget()
        if fw is not None:
            fw.clearFocus()
        if self._prev_fg and user32.IsWindow(self._prev_fg):
            user32.SetForegroundWindow(self._prev_fg)
        self._prev_fg = None

    # ================================================================ 原生：热键、闪烁、样式
    def showEvent(self, e):
        # 第一次显示之前先把桌面拍下来：此刻我们的窗口还没进合成，画面本来就是干净的，
        # 不需要挪窗口，也就完全不会干扰悬停。
        if self.backdrop._plate is None:
            self._snap_plate(force=True, move=False)
        super().showEvent(e)
        hwnd = int(self.winId())
        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE)
        self.apply_capture_mode()
        if not self._shell_msg:
            self._shell_msg = user32.RegisterWindowMessageW("SHELLHOOK")
            user32.RegisterShellHookWindow(hwnd)
        if not self._registered_hotkeys:
            self.register_hotkeys()
        self._apply_passthrough()
        if self.pinned():
            QtCore.QTimer.singleShot(600, self.expand)
        self.poll.start()
        self.backdrop.start()
        self._kick()

    def register_hotkeys(self):
        hwnd = int(self.winId())
        for hid in list(self._registered_hotkeys):
            user32.UnregisterHotKey(hwnd, hid)
        self._registered_hotkeys.clear()
        for i, (name, spec) in enumerate((cfg.get("hotkeys") or {}).items()):
            hk = parse_hotkey(spec)
            if not hk:
                continue
            hid = 0xB000 + i
            if user32.RegisterHotKey(hwnd, hid, hk[0], hk[1]):
                self._registered_hotkeys[hid] = name
            else:
                print(f"热键注册失败（可能被占用）：{name} = {spec}")

    def nativeEvent(self, etype, message):
        try:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                name = self._registered_hotkeys.get(int(msg.wParam))
                if name:
                    self.hotkey.emit(name)
                    return True, 0
            elif self._shell_msg and msg.message == self._shell_msg:
                if int(msg.wParam) == HSHELL_FLASH:
                    self.flash.emit(int(msg.lParam or 0))
            elif msg.message == WM_DEVICECHANGE:
                # 只发信号，防抖和重扫交给调用方（插一个复合设备会连发好几条）
                self.devices_changed.emit()
        except Exception:  # noqa: BLE001
            pass
        return False, 0

    def set_fullscreen_hidden(self, hidden: bool):
        if hidden == self._fs_hidden:
            return
        self._fs_hidden = hidden
        if hidden:
            self.collapse()
            self.hide()
        else:
            self.show()
            self._kick()

    def closeEvent(self, e):
        hwnd = int(self.winId())
        for hid in self._registered_hotkeys:
            user32.UnregisterHotKey(hwnd, hid)
        try:
            user32.DeregisterShellHookWindow(hwnd)
        except Exception:  # noqa: BLE001
            pass
        self.backdrop.stop()
        self._rhook.remove()
        cfg.save()
        super().closeEvent(e)



_ = G




