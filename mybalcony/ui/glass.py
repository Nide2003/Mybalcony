# -*- coding: utf-8 -*-
"""毛玻璃背景。

后台线程用 GDI StretchBlt(HALFTONE) 把灵动岛身后的屏幕区域直接缩成很小的图（灵动岛自身已设为
不进入截图），再做一次平均模糊；主线程绘制时用平滑放大的纹理画刷填充形状 —— 边缘抗锯齿、任意形状。
截屏要等 DWM 回读（10~30ms），所以绝不能放在 UI 线程里。
"""
from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes as W

from PySide6 import QtCore, QtGui

WDA_EXCLUDEFROMCAPTURE = 0x11
DOWN = 12  # 缩小倍数（越大越糊）
LIQUID_DOWN = 3  # 液态玻璃：玻璃是透镜不是磨砂，背景要看得清才像玻璃

_u32 = ctypes.WinDLL("user32")
_gdi = ctypes.WinDLL("gdi32")
_u32.GetDC.restype = W.HDC
_u32.GetDC.argtypes = [W.HWND]
_u32.ReleaseDC.argtypes = [W.HWND, W.HDC]
_gdi.CreateCompatibleDC.restype = W.HDC
_gdi.CreateCompatibleDC.argtypes = [W.HDC]
_gdi.CreateDIBSection.restype = W.HBITMAP
_gdi.CreateDIBSection.argtypes = [W.HDC, ctypes.c_void_p, W.UINT, ctypes.POINTER(ctypes.c_void_p), W.HANDLE, W.DWORD]
_gdi.SelectObject.restype = W.HGDIOBJ
_gdi.SelectObject.argtypes = [W.HDC, W.HGDIOBJ]
_gdi.DeleteObject.argtypes = [W.HGDIOBJ]
_gdi.DeleteDC.argtypes = [W.HDC]
_gdi.SetStretchBltMode.argtypes = [W.HDC, ctypes.c_int]
_gdi.SetBrushOrgEx.argtypes = [W.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
_gdi.StretchBlt.argtypes = [W.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            W.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.DWORD]
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
HALFTONE = 4


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD),
                ("biBitCount", W.WORD), ("biCompression", W.DWORD), ("biSizeImage", W.DWORD),
                ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG), ("biClrUsed", W.DWORD),
                ("biClrImportant", W.DWORD)]


def exclude_from_capture(hwnd: int, on: bool = True) -> bool:
    try:
        return bool(_u32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE if on else 0))
    except Exception:  # noqa: BLE001
        return False


def _blur(img: QtGui.QImage) -> QtGui.QImage:
    """3x3 平均：第 k 张以 1/k 不透明度叠加（SourceOver），结果正好是平均值，不会变亮。"""
    out = img.copy()
    p = QtGui.QPainter(out)
    k = 1
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        k += 1
        p.setOpacity(1 / k)
        p.drawImage(dx, dy, img)
    p.end()
    return out


def _polish(img: QtGui.QImage) -> QtGui.QImage:
    """液态玻璃：把小图叠一层自身（Overlay）提对比 / 提饱和，再提一点点亮度。
    只作用在 1/12 的小图上，开销可以忽略。"""
    src = img.copy()
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Overlay)
    p.setOpacity(0.42)
    p.drawImage(0, 0, src)
    p.setOpacity(1.0)
    p.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
    p.fillRect(img.rect(), QtGui.QColor(255, 255, 255, 14))
    p.end()
    return img


def _numpy_of(img: QtGui.QImage):
    """QImage(ARGB32_Premultiplied) -> float32 数组，通道顺序 BGRA。"""
    import numpy as np
    buf = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(img.height(), img.width(), 4)
    return buf.astype(np.float32)


def _image_of(arr, like: QtGui.QImage) -> QtGui.QImage:
    import numpy as np
    data = np.clip(arr, 0, 255).astype(np.uint8)
    out = QtGui.QImage(data.tobytes(), like.width(), like.height(), like.width() * 4,
                       QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    return out.copy()


def refract(img: QtGui.QImage, rect: QtCore.QRect, body: QtCore.QRectF, radius: float,
            amp_k: float = 0.58, lens: float = 0.965) -> QtGui.QImage:
    """圆角矩形 SDF 位移采样：边缘一圈的像素向形状外取样，背景在玻璃边缘被"吸"进来。

    这是 feDisplacementMap 的等价实现（shuding/liquid-glass 的位移贴图思路）：离边越近位移越大，
    到内侧一定深度后归零；R / B 通道各偏一点形成真实色散。只作用在 1/5 的小图上，开销很小。
    """
    import numpy as np
    tiny_w, tiny_h = img.width(), img.height()
    if tiny_w < 4 or tiny_h < 4 or body.isEmpty():
        return img
    s = tiny_w / max(1.0, float(rect.width()))
    hw = max(1.0, body.width() * s / 2)
    hh = max(1.0, body.height() * s / 2)
    r = max(1.0, min(radius * s, hw - 0.5, hh - 0.5))
    cx = (body.center().x() - rect.x()) * s
    cy = (body.center().y() - rect.y()) * s
    xs = np.arange(tiny_w, dtype=np.float32)[None, :]
    ys = np.arange(tiny_h, dtype=np.float32)[:, None]
    qx = np.abs(xs - cx) - (hw - r)
    qy = np.abs(ys - cy) - (hh - r)
    d = np.minimum(np.maximum(qx, qy), 0.0) + np.sqrt(np.maximum(qx, 0.0) ** 2 + np.maximum(qy, 0.0) ** 2) - r
    depth = np.maximum(-d, 0.0)                       # 在形状里的深度（tiny px）
    band = max(2.0, min(hw, hh) * 0.42)               # 折射带宽度
    t = np.clip(1.0 - depth / band, 0.0, 1.0) ** 2
    gy, gx = np.gradient(d)
    n = np.sqrt(gx * gx + gy * gy) + 1e-6
    amp = band * amp_k
    src = _numpy_of(img)
    out = src.copy()
    for ci, k in ((2, 0.93), (1, 1.0), (0, 1.07)):    # R / G / B 各自位移不同 → 色散
        # lens：整块把背景略微放大（透镜感）；t：边缘再往形状外伸一段（折射带）
        base_x = cx + (xs - cx) * lens
        base_y = cy + (ys - cy) * lens
        sx = np.broadcast_to(base_x, (tiny_h, tiny_w)) + gx / n * amp * t * k
        sy = np.broadcast_to(base_y, (tiny_h, tiny_w)) + gy / n * amp * t * k
        x0 = np.clip(np.floor(sx), 0, tiny_w - 1).astype(np.int32)
        y0 = np.clip(np.floor(sy), 0, tiny_h - 1).astype(np.int32)
        x1 = np.minimum(x0 + 1, tiny_w - 1)
        y1 = np.minimum(y0 + 1, tiny_h - 1)
        fx = np.clip(sx - x0, 0.0, 1.0)
        fy = np.clip(sy - y0, 0.0, 1.0)
        v = (src[y0, x0, ci] * (1 - fx) * (1 - fy) + src[y0, x1, ci] * fx * (1 - fy)
             + src[y1, x0, ci] * (1 - fx) * fy + src[y1, x1, ci] * fx * fy)
        out[:, :, ci] = np.where(t > 0.004, v, src[:, :, ci])
    out[:, :, 3] = src[:, :, 3]
    return _image_of(out, img)


def capture_region(grect: QtCore.QRect, down: int = 3) -> QtGui.QImage | None:
    """同步抓一块屏幕区域（UI 线程用，弹层这类一开就抓一次的小场景）：
    缩小 + 单次模糊 + 提纯。窗口必须先还没画自己，否则会把自己的半透明内容抓进去。"""
    if grect.width() < 4 or grect.height() < 4:
        return None
    tw, th = max(2, grect.width() // down), max(2, grect.height() // down)
    scr = QtGui.QGuiApplication.screenAt(grect.center()) or QtGui.QGuiApplication.primaryScreen()
    if scr is None:
        return None
    sg = scr.geometry()
    dpr = scr.devicePixelRatio()
    px = sg.x() + round((grect.x() - sg.x()) * dpr)
    py = sg.y() + round((grect.y() - sg.y()) * dpr)
    img = grab_tiny(px, py, round(grect.width() * dpr), round(grect.height() * dpr), tw, th)
    if img is None:
        return None
    img = img.convertToFormat(QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    return _polish(_blur(img))


def grab_tiny(px: int, py: int, pw: int, ph: int, tw: int, th: int) -> QtGui.QImage | None:
    """物理像素区域 -> tw x th 的缩略图（HALFTONE 面积平均）。线程安全。"""
    sdc = _u32.GetDC(None)
    if not sdc:
        return None
    mdc = _gdi.CreateCompatibleDC(sdc)
    bmi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), tw, -th, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = ctypes.c_void_p()
    hbmp = _gdi.CreateDIBSection(mdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    img = None
    try:
        if hbmp and bits.value:
            old = _gdi.SelectObject(mdc, hbmp)
            _gdi.SetStretchBltMode(mdc, HALFTONE)
            _gdi.SetBrushOrgEx(mdc, 0, 0, None)
            if _gdi.StretchBlt(mdc, 0, 0, tw, th, sdc, px, py, pw, ph, SRCCOPY):   # 不用 CAPTUREBLT：它会让分层窗口闪烁
                buf = ctypes.string_at(bits.value, tw * th * 4)
                img = QtGui.QImage(buf, tw, th, tw * 4, QtGui.QImage.Format.Format_RGB32).copy()
            _gdi.SelectObject(mdc, old)
    finally:
        if hbmp:
            _gdi.DeleteObject(hbmp)
        _gdi.DeleteDC(mdc)
        _u32.ReleaseDC(None, sdc)
    return img


class Backdrop(QtCore.QObject):
    """后台截取 + 模糊。主线程调用 request() 告知要覆盖的区域，结果通过 ready 信号回到主线程。"""
    ready = QtCore.Signal(bool)          # changed

    def __init__(self):
        super().__init__()
        # (模糊小图, 对应的全局逻辑区域, 亮度)；整体替换，主线程读到的总是一致的一组
        self.state: tuple = (None, QtCore.QRect(), 0.5)
        self._sig = None
        self._lock = threading.Lock()
        self._want: tuple | None = None     # (逻辑区域, 物理区域)
        self._interval = 0.1
        self._wake = threading.Event()
        self._stop = False
        self._thread = threading.Thread(target=self._run, name="mybalcony-glass", daemon=True)
        # 参与屏幕捕获时：只在自己截取背景的那一瞬间把灵动岛排除，截完立即恢复
        self.hwnd = 0
        self.self_exclude = False
        self.liquid = False                 # 液态玻璃：背后画面提对比 / 提饱和，折射感更强
        self._rfx: dict = {}                # 折射结果缓存（key = 小图 + 形状）
        self._started = False

    def start(self):
        if not self._started:
            self._started = True
            self._thread.start()

    @property
    def tiny(self):
        return self.state[0]

    @property
    def rect(self):
        return self.state[1]

    @property
    def luminance(self):
        return self.state[2]

    def stop(self):
        self._stop = True
        self._wake.set()

    def request(self, screen: QtGui.QScreen, grect: QtCore.QRect, interval: float, urgent: bool = False):
        """grect：需要覆盖的全局逻辑区域；interval：期望的刷新间隔（秒）。"""
        sg = screen.geometry()
        r = grect.intersected(sg)
        if r.width() < 4 or r.height() < 4:
            return
        dpr = screen.devicePixelRatio()
        # Qt6 在 Windows 上保持屏幕原点不缩放：物理 = 原点 + (逻辑 - 原点) * dpr
        px = sg.x() + round((r.x() - sg.x()) * dpr)
        py = sg.y() + round((r.y() - sg.y()) * dpr)
        phys = (px, py, round(r.width() * dpr), round(r.height() * dpr))
        with self._lock:
            new = (QtCore.QRect(r), phys)
            moved = self._want is None or self._want[0] != new[0]
            self._want = new
            self._interval = interval
        if urgent or moved:
            self._wake.set()

    def _run(self):
        last = 0.0
        while not self._stop:
            with self._lock:
                interval = self._interval
            self._wake.wait(max(0.0, interval - (time.perf_counter() - last)))
            self._wake.clear()
            if self._stop:
                break
            # 两次截图之间至少隔 1/45s，避免被连续唤醒时占满 CPU
            gap = time.perf_counter() - last
            if gap < 1 / 45:
                time.sleep(1 / 45 - gap)
            with self._lock:
                want = self._want
            if want is None:
                continue
            last = time.perf_counter()
            try:
                self._capture(*want)
            except Exception:  # noqa: BLE001
                import traceback
                traceback.print_exc()

    def _capture(self, r: QtCore.QRect, phys):
        down = LIQUID_DOWN if self.liquid else DOWN
        tw, th = max(2, r.width() // down), max(2, r.height() // down)
        toggle = self.self_exclude and self.hwnd
        if toggle:
            _u32.SetWindowDisplayAffinity(self.hwnd, WDA_EXCLUDEFROMCAPTURE)
        try:
            img = grab_tiny(phys[0], phys[1], phys[2], phys[3], tw, th)
        finally:
            if toggle:
                _u32.SetWindowDisplayAffinity(self.hwnd, 0)
        if img is None:
            return
        img = img.convertToFormat(QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        if self.liquid:
            img = _polish(_blur(img))       # 液态玻璃只糊一遍，保留背景的结构
        else:
            img = _blur(_blur(img))
        mode = QtCore.Qt.TransformationMode.SmoothTransformation
        sig = bytes(img.scaled(8, 4, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio, mode).constBits())
        c = img.scaled(1, 1, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio, mode).pixelColor(0, 0)
        lum = 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
        changed = sig != self._sig or r != self.rect
        self._sig = sig
        self.state = (img, QtCore.QRect(r), lum)
        self.ready.emit(changed)

    def covers(self, grect: QtCore.QRect) -> bool:
        tiny, rect, _ = self.state
        return tiny is not None and rect.contains(grect)

    @staticmethod
    def brush_for(state, window_origin: QtCore.QPoint) -> QtGui.QBrush | None:
        if not state or state[0] is None:
            return None
        tiny, rect = state[0], state[1]
        b = QtGui.QBrush(tiny)
        tr = QtGui.QTransform()
        tr.translate(rect.x() - window_origin.x(), rect.y() - window_origin.y())
        tr.scale(rect.width() / tiny.width(), rect.height() / tiny.height())
        b.setTransform(tr)
        return b

    def brush_liquid(self, body: QtCore.QRectF, radius: float, window_origin: QtCore.QPoint) -> QtGui.QBrush | None:
        """液态玻璃用：先把小图按形状边缘做一次位移折射，再铺到窗口坐标（结果按形状缓存）。"""
        tiny, rect, _ = self.state
        if tiny is None:
            return None
        gb = body.toAlignedRect()
        key = (id(tiny), gb.x(), gb.y(), gb.width(), gb.height(), int(round(radius)))
        img = self._rfx.get(key)
        if img is None:
            if len(self._rfx) > 8:
                self._rfx.clear()
            try:
                img = refract(tiny, rect, QtCore.QRectF(gb).translated(window_origin), radius)
            except Exception:  # noqa: BLE001  没有 numpy / 形状退化时退回普通毛玻璃
                img = tiny
            self._rfx[key] = img
        b = QtGui.QBrush(img)
        tr = QtGui.QTransform()
        tr.translate(rect.x() - window_origin.x(), rect.y() - window_origin.y())
        tr.scale(rect.width() / img.width(), rect.height() / img.height())
        b.setTransform(tr)
        return b

    def brush(self, window_origin: QtCore.QPoint) -> QtGui.QBrush | None:
        """返回把模糊小图铺到窗口坐标的画刷。window_origin = 窗口左上角的全局坐标。"""
        tiny, rect, _ = self.state
        if tiny is None:
            return None
        b = QtGui.QBrush(tiny)
        tr = QtGui.QTransform()
        tr.translate(rect.x() - window_origin.x(), rect.y() - window_origin.y())
        tr.scale(rect.width() / tiny.width(), rect.height() / tiny.height())
        b.setTransform(tr)
        return b
