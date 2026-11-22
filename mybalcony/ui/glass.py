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
# 液态玻璃只对贴边折射带降采样；中央背景始终保留完整分辨率。
LIQUID_PX_BUDGET = 120000
LIQUID_DOWN_MIN = 1.4
LIQUID_DOWN_MAX = 2.6

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


SW_HIDE, SW_SHOWNA = 0, 8
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_NOACTIVATE, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x10, 0x20
_set_window_pos = _u32.SetWindowPos


def set_visible(hwnd: int, on: bool) -> bool:
    """不抢焦点地显示 / 隐藏窗口（SW_SHOWNA / SW_HIDE）。抓干净背景靠它。"""
    try:
        return bool(_u32.ShowWindow(hwnd, SW_SHOWNA if on else SW_HIDE))
    except Exception:  # noqa: BLE001
        return False


class _ACCENT_POLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class _WCADATA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_ulong)]


_u32.SetWindowCompositionAttribute.argtypes = [W.HWND, ctypes.POINTER(_WCADATA)]
WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ACRYLIC = 4            # ACCENT_ENABLE_ACRYLICBLURBEHIND


def set_acrylic(hwnd: int, on: bool = True, tint: int = 0x00FFFFFF) -> bool:
    """给窗口开 DWM 亚克力（真·实时背景模糊）。

    为什么非要它：自家窗口在 GDI 截屏里永远只能是黑块或上一帧（见 `_heal`），所以
    "面板中间那块真实的模糊"根本抓不到；但 DWM 自己知道身后是什么，亚克力就是它替我们
    糊好的结果。分工因此变成 —— 中间交给亚克力（实时、有真实结构），四周一圈交给截屏
    折射（真像素的透镜挤压）。

    tint 是叠在模糊之上的底色（ARGB，alpha 越低越通透）。开亚克力后窗口里 alpha=0 的
    地方才会露出模糊，所以折射图中心要被抠成透明（见 `refract(..., ring_only=True)`）。
    """
    try:
        ap = _ACCENT_POLICY(ACCENT_ACRYLIC if on else ACCENT_DISABLED, 2, tint, 0)
        wd = _WCADATA(WCA_ACCENT_POLICY, ctypes.cast(ctypes.pointer(ap), ctypes.c_void_p),
                      ctypes.sizeof(ap))
        return bool(_u32.SetWindowCompositionAttribute(hwnd, ctypes.byref(wd)))
    except Exception:  # noqa: BLE001
        return False


def _blur(img: QtGui.QImage, step: float = 1.0) -> QtGui.QImage:
    """3x3 平均：第 k 张以 1/k 不透明度叠加（SourceOver），结果正好是平均值，不会变亮。

    step 是每个采样点在小图里的偏移。小图的缩小倍数不再固定（见 LIQUID_PX_BUDGET），
    所以同一个"遍数"在不同倍率下对应的屏幕模糊半径会差一倍，这里按 1/3 的基准把偏移
    按 3/down 折算回来，磨砂手感才跟调参时一致。step 可以是小数：平移时走平滑插值，
    等于做了一次亚像素模糊。
    """
    out = img.copy()
    p = QtGui.QPainter(out)
    p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    k = 1
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
        k += 1
        p.setOpacity(1 / k)
        p.drawImage(QtCore.QPointF(dx * step, dy * step), img)
    p.end()
    return out


# 材质分级：模糊强度随层级递增，不要所有面都用同一档（否则层级关系就没了）。
# 我们把一遍 3x3 均值算作一档；小图本身已缩到 1/3，等效半径并不小，所以按遍数分级就够。
#   plain    只有霜 + 高光，不模糊 —— 玻璃小块 / 按钮（它们叠在面板上，没有自己的背景采样）
#   regular  常规面板 —— 收起态胶囊
#   elevated 浮起卡片 —— 展开的大岛
#   focused  当前焦点 / 浮层 —— 二级菜单、弹出卡片
MATERIAL = {"plain": 0, "regular": 1, "elevated": 2, "focused": 3}
# 每种材质的模糊半径系数：展开的大岛要把身后的窗口边缘彻底糊掉（否则会出现硬直边的
# "竖条"色带），收起胶囊保持原来的清透手感，二级浮层取中间值。
FROST_STEP = {"plain": 1.0, "regular": 1.15, "elevated": 12.0, "focused": 2.4}


def _frost(img: QtGui.QImage, passes: int, down: float = 3.0,
           step_k: float = 1.0) -> QtGui.QImage:
    """按材质档位做 N 遍模糊，最后统一覆一层薄霜。

    down 是这张小图的缩小倍数：模糊偏移按 3/down 折算，保证不同采样倍率下面板看起来
    是同一个磨砂强度（原来的遍数是按 1/3 调出来的）。

    step_k 是模糊半径的放大系数：3x3 均值只能把背景边缘软掉几个像素，背后只要有窗口、
    对话框这类硬直边，就会透出一条条"色带"，看着像玻璃上有道竖条。展开的大岛必须把
    step_k 拉大（等效模糊半径 25~30 屏幕像素），背后的结构才会化成一团柔和的色晕。
    """
    out = img
    # 缩到 1/f 再插值回原尺寸 = 一次干净的（近似高斯）大半径模糊：
    # 不会出现"8 个位移副本叠加"那种周期性残影，也不会把文字糊成一排排横向色带。
    f = max(2.0, (3.0 / max(1.0, down)) * max(1.0, float(step_k)))
    for _ in range(max(1, int(passes))):
        w, h = out.width(), out.height()
        sw = max(2, int(round(w / f)))
        sh = max(2, int(round(h / f)))
        out = out.scaled(sw, sh, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                         QtCore.Qt.TransformationMode.SmoothTransformation)
        out = out.scaled(w, h, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                         QtCore.Qt.TransformationMode.SmoothTransformation)
    return _polish(out)


def _polish(img: QtGui.QImage) -> QtGui.QImage:
    """液态玻璃：透镜不改变身后画面的饱和度，只覆一层薄霜（iOS 风格，兼顾文字可读性）。
    只作用在小图上，开销可以忽略。"""
    p = QtGui.QPainter(img)
    p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
    p.fillRect(img.rect(), QtGui.QColor(255, 255, 255, 4))
    p.end()
    return img


def _flatten(img: QtGui.QImage, radius: float = 36.0, keep: float = 0.42) -> QtGui.QImage:
    """削平低空间频率的明暗，玻璃才是一整片均匀乳面。

    磨砂只杀细节：背后"白窗口 vs 深色壁纸"这种几百像素尺度的大块明暗，模糊完会原样留在
    玻璃上 —— 面板一半发白、一半发灰，中间还有几团散景光斑，看上去就是"背景很脏"。
    这里取一张大半径模糊当低频底，只把 keep 比例的残差叠回去，大块明暗被压平，
    细节（已经糊掉的那些）本来就不剩什么，于是整块面板变成同一种乳白。
    """
    import numpy as np
    if img.isNull() or radius < 2 or keep >= 1.0:
        return img
    w, h = img.width(), img.height()
    mode = QtCore.Qt.AspectRatioMode.IgnoreAspectRatio
    smooth = QtCore.Qt.TransformationMode.SmoothTransformation
    sw, sh = max(2, int(round(w / radius))), max(2, int(round(h / radius)))
    lo = img.scaled(sw, sh, mode, smooth).scaled(w, h, mode, smooth)
    a = _numpy_of(img).astype(np.float32)
    b = _numpy_of(lo).astype(np.float32)
    out = b + (a - b) * float(keep)
    out[..., 3] = a[..., 3]
    np.clip(out, 0.0, 255.0, out=out)
    return _image_of(out.astype(np.uint8), img)


def _downscale(img: QtGui.QImage, tw: int, th: int) -> QtGui.QImage:
    """逐级减半再落到目标尺寸。

    Qt 的 SmoothTransformation 只做 2x2 双线性：一次缩小 2 倍以上等于隔点取样，
    细笔画（窗口里的 1~2px 文字）会被抽成一层规律的网格/斜纹，再过一遍磨砂就成了
    "很脏"的花纹。逐级减半每次都严格 2x2 均值，等价于 mipmap，画面是干净的。
    """
    w, h = img.width(), img.height()
    mode = QtCore.Qt.AspectRatioMode.IgnoreAspectRatio
    smooth = QtCore.Qt.TransformationMode.SmoothTransformation
    while w >= max(2, tw) * 2 and h >= max(2, th) * 2:
        w //= 2
        h //= 2
        img = img.scaled(w, h, mode, smooth)
    if (w, h) != (tw, th):
        img = img.scaled(max(2, tw), max(2, th), mode, smooth)
    return img


def _numpy_of(img: QtGui.QImage):
    """QImage -> float32 数组，通道顺序 BGRA。按 bytesPerLine 取行，避免行尾填充导致 reshape 失败。"""
    import numpy as np
    img = img.convertToFormat(QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    w, h = img.width(), img.height()
    stride = img.bytesPerLine()
    buf = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(h, stride)[:, :w * 4]
    return buf.reshape(h, w, 4).astype(np.float32)


def _numpy_u8(img: QtGui.QImage):
    """Zero-copy BGRA byte view for native OpenCV sampling."""
    import numpy as np
    if img.format() != QtGui.QImage.Format.Format_ARGB32_Premultiplied:
        img = img.convertToFormat(QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    w, h = img.width(), img.height()
    buf = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(h, img.bytesPerLine())
    return buf[:, :w * 4].reshape(h, w, 4)


def _image_of(arr, like: QtGui.QImage) -> QtGui.QImage:
    import numpy as np
    data = np.clip(arr, 0, 255).astype(np.uint8)
    out = QtGui.QImage(data.tobytes(), like.width(), like.height(), like.width() * 4,
                       QtGui.QImage.Format.Format_ARGB32_Premultiplied)
    return out.copy()


def _rgb_image(arr) -> QtGui.QImage:
    """(H, W, 3) float 数组 -> RGB32 QImage。"""
    import numpy as np
    data = np.clip(arr, 0, 255).astype(np.uint8)
    h, w = data.shape[:2]
    return QtGui.QImage(data.tobytes(), w, h, w * 3, QtGui.QImage.Format.Format_RGB888).copy()


def _heal(img: QtGui.QImage, hole: QtCore.QRect, coarsen: int = 8,
          iters: int = 10, feather: int = 10, dark: float = 26.0) -> QtGui.QImage:
    """把自家窗口挡住的那块（截图里只能是黑脸或上一帧）用四周真实像素补掉。

    为什么必须这么做：Windows 对「分层半透明窗口」的 GDI 截屏有两条死路 ——
      1) 开着 WDA_EXCLUDEFROMCAPTURE：整块窗口矩形被拍成纯黑（连透明边距一起黑）；
      2) 关着：拍到自家上一帧的自画像。
    两种都拿不到「身后」。但窗口之外那一圈像素是真的，所以这里：
      · 坏像素 = hole 内的像素 ∪ 近黑像素（自家窗口在截屏里就是黑，frost 还会把这圈黑往
        外糊出十几像素），一并当成"没有信息"；
      · 粗尺度上做**加权平均下采样**（坏像素权重 0），于是每个格子拿到的是附近真实像素的
        平均色 —— 等价于一块只认真背景的极重模糊场，不会把黑色拉进来；
      · 上采样回原尺寸，按羽化后的 hole 掩膜混合，边界不留硬接缝。
    之后 `_frost` 会把扩散场糊匀，`refract` 再在边缘朝外取样（落点正好是真实的像素环）。
    """
    import numpy as np
    w, h = img.width(), img.height()
    r = hole.intersected(QtCore.QRect(0, 0, w, h))
    if w < 16 or h < 16 or r.width() < 4 or r.height() < 4:
        return img
    src = _numpy_of(img)
    rgb = src[:, :, :3]
    bad = np.zeros((h, w), dtype=bool)
    bad[r.y():r.bottom() + 1, r.x():r.right() + 1] = True
    bad |= rgb.mean(axis=2) < dark
    good = (~bad).astype(np.float32)
    if good.mean() < 0.02:
        return img
    cw, ch = max(8, w // coarsen), max(8, h // coarsen)
    H, W = ch * coarsen, cw * coarsen
    g = good[:H, :W].reshape(ch, coarsen, cw, coarsen)
    c = rgb[:H, :W] * good[:H, :W][..., None]
    gw = g.sum(axis=(1, 3))                                    # 每格的真实像素数
    cs = c.reshape(ch, coarsen, cw, coarsen, 3).sum(axis=(1, 3))
    cs = cs / np.maximum(gw, 1.0)[..., None]
    empty = gw < 1.0
    if empty.any():                                            # 全坏格：先给个全局均值做种子，再向邻居扩散
        cs[empty] = cs[~empty].mean(axis=0) if (~empty).any() else 0.0
        vi = (~empty).astype(np.float32)[..., None]
        for _ in range(max(8, iters)):
            acc = np.zeros_like(cs)
            cnt = np.zeros((ch, cw, 1), np.float32)
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                acc += np.roll(np.roll(cs, dy, 0), dx, 1) * np.roll(np.roll(vi, dy, 0), dx, 1)
                cnt += np.roll(np.roll(vi, dy, 0), dx, 1)
            cs[empty] = acc[empty] / np.maximum(cnt[empty], 1.0)
    up = _rgb_image(cs).scaled(w, h, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio,
                               QtCore.Qt.TransformationMode.SmoothTransformation)
    healed = _numpy_of(up)[:, :, :3]
    # 羽化：把 hole 的硬边软掉，避免回填区和真实像素之间出现一条亮/暗的接缝
    a = np.zeros((h, w), np.float32)
    a[r.y():r.bottom() + 1, r.x():r.right() + 1] = 1.0
    for _ in range(max(2, feather)):
        a = (a + np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1)) / 5.0
    a = np.clip(a * 1.6, 0.0, 1.0)[..., None]
    out = src.copy()
    out[:, :, :3] = rgb * (1.0 - a) + healed * a
    return _image_of(out, img)


def refract(img: QtGui.QImage, rect: QtCore.QRect, body: QtCore.QRectF, radius: float,
            amp_k: float = 1.05, lens: float = 1.0,
            flat: float = 0.72, gamma: float = 1.7,
            ring_only: bool = False, ring_fade: float = 3.0,
            sharp: QtGui.QImage | None = None, _cache: dict | None = None) -> QtGui.QImage:
    """文档 WebGL 上游的 SDF 圆头透镜，独立实现。

    厚度带参数 x 从中央 0 增长到外沿 1；位移沿圆头曲线
    circleMap(x) = 1-sqrt(1-x*x)，方向只取圆角矩形 SDF 的解析梯度。
    中央位移恒为零，完整周长使用同一连续光场，不使用切线扰动或方向掩膜。
    """
    import numpy as np

    tiny_w, tiny_h = img.width(), img.height()
    if tiny_w < 4 or tiny_h < 4 or body.isEmpty():
        return img

    field_key = (tiny_w, tiny_h, rect.x(), rect.y(), rect.width(), rect.height(),
                 body.x(), body.y(), body.width(), body.height(), radius,
                 flat, amp_k, lens, ring_fade)
    field = _cache.get(field_key) if _cache is not None else None
    if field is None:
        scale = tiny_w / max(1.0, float(rect.width()))
        hw = max(1.0, body.width() * scale / 2.0)
        hh = max(1.0, body.height() * scale / 2.0)
        corner = max(1.0, min(radius * scale, hw - 0.5, hh - 0.5))
        cx = (body.center().x() - rect.x()) * scale
        cy = (body.center().y() - rect.y()) * scale
        thickness = max(2.0, min(hw, hh) * (1.0 - flat))

        xs = np.arange(tiny_w, dtype=np.float32)[None, :]
        ys = np.arange(tiny_h, dtype=np.float32)[:, None]
        px, py = xs - cx, ys - cy
        qx = np.abs(px) - (hw - corner)
        qy = np.abs(py) - (hh - corner)
        ox, oy = np.maximum(qx, 0.0), np.maximum(qy, 0.0)
        outside = np.sqrt(ox * ox + oy * oy)
        sd = outside + np.minimum(np.maximum(qx, qy), 0.0) - corner
        band = np.clip(1.0 - np.maximum(-sd, 0.0) / thickness, 0.0, 1.0)
        circle_map = 1.0 - np.sqrt(np.maximum(1.0 - band * band, 0.0))

        safe = np.maximum(outside, 1e-6)
        gx = np.where(qx > 0.0, ox / safe * np.sign(px),
                      np.where(qx > qy, np.sign(px), 0.0))
        gy = np.where(qy > 0.0, oy / safe * np.sign(py),
                      np.where(qy > qx, np.sign(py), 0.0))
        map_x = np.clip(cx + px * lens + gx * (-thickness * amp_k * circle_map),
                        0.0, tiny_w - 1.0).astype(np.float32)
        map_y = np.clip(cy + py * lens + gy * (-thickness * amp_k * circle_map),
                        0.0, tiny_h - 1.0).astype(np.float32)
        coverage = np.clip(circle_map * ring_fade, 0.0, 1.0)
        field = map_x, map_y, coverage
        if _cache is not None:
            _cache.clear()
            _cache[field_key] = field

    map_x, map_y, coverage = field
    source = sharp if sharp is not None and sharp.width() == tiny_w and sharp.height() == tiny_h else img
    src = _numpy_u8(source)
    base = _numpy_u8(img)
    import cv2
    out = cv2.remap(src, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REPLICATE)

    if ring_only:
        # QImage is premultiplied: reducing alpha without applying the same
        # coverage to RGB creates invalid RGB>A pixels and rainbow fringes.
        out[:, :, :3] = out[:, :, :3] * coverage[..., None]
        out[:, :, 3] = base[:, :, 3] * coverage
    return _image_of(out, img)


def _sdf(tiny_w: int, tiny_h: int, rect: QtCore.QRect, body: QtCore.QRectF, radius: float):
    """圆角矩形有向距离场（小图坐标系）。返回 (d, depth, gx, gy, n, cx, cy, hw, hh)。

    d < 0 在形状内、> 0 在形状外；gx / gy 是 d 的梯度，方向朝形状外，即这一点的"外法线"。
    """
    import numpy as np
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
    d = (np.minimum(np.maximum(qx, qy), 0.0)
         + np.sqrt(np.maximum(qx, 0.0) ** 2 + np.maximum(qy, 0.0) ** 2) - r)
    gy, gx = np.gradient(d)
    n = np.sqrt(gx * gx + gy * gy) + 1e-6
    return d, np.maximum(-d, 0.0), gx, gy, n, cx, cy, hw, hh


# 轮廓高光：**双光源**，一路从左下 45°、一路从右上 45°。外法线与光线方向越对齐越亮，
# 于是左下角和右上角同时被点亮，左上 / 右下自然熄灭 —— 斜向对角打光，比单光源更像
# 真实玻璃被两侧环境光照到。
HL_LIGHT_X = -0.7071
HL_LIGHT_Y = 0.7071          # 左下：x 负、y 正（屏幕 y 向下）
HL_LIGHT2_X = 0.7071         # 右上
HL_LIGHT2_Y = -0.7071


def highlight_field(tiny_w: int, tiny_h: int, rect: QtCore.QRect, body: QtCore.QRectF,
                    radius: float, flat: float = 0.90, gamma: float = 2.2,
                    peak: int = 158, soft: float = 1.6) -> QtGui.QImage | None:
    """从位移向量场推导边缘高光（不是描边框）。

    同一个 SDF 法线场既决定折射方向，也决定受光量：`亮 = Σ max(0, n · L)`，
    L 取左下与右上两个 45° 方向。乘上边缘衰减 t，就只在贴边的一圈出现；
    左上 / 右下因为背光自然归零。
    """
    import numpy as np
    if tiny_w < 4 or tiny_h < 4 or body.isEmpty():
        return None
    d, depth, gx, gy, n, cx, cy, hw, hh = _sdf(tiny_w, tiny_h, rect, body, radius)
    band = max(2.0, min(hw, hh) * (1.0 - flat))
    t = np.clip(1.0 - depth / band, 0.0, 1.0) ** gamma
    ux = gx / n                                        # 外法线：左半边 ux < 0，右半边 ux > 0
    uy = gy / n
    # 两路光源各自取 max(0, n·L) 再相加，取 0.72 归一，避免两个角都顶到饱和
    lit = 0.72 * (np.clip(ux * HL_LIGHT_X + uy * HL_LIGHT_Y, 0.0, 1.0)
                  + np.clip(ux * HL_LIGHT2_X + uy * HL_LIGHT2_Y, 0.0, 1.0))
    lit = np.clip(lit, 0.0, 1.0) ** soft
    alpha = np.clip(lit * (t ** 0.55) * peak, 0.0, 255.0).astype(np.uint8)
    if not alpha.any():
        return None
    rgba = np.empty((tiny_h, tiny_w, 4), dtype=np.uint8)
    rgba[:, :, 0] = alpha                               # B（预乘：白 = (a, a, a, a)）
    rgba[:, :, 1] = alpha                               # G
    rgba[:, :, 2] = alpha                               # R
    rgba[:, :, 3] = alpha
    return QtGui.QImage(rgba.tobytes(), tiny_w, tiny_h, tiny_w * 4,
                        QtGui.QImage.Format.Format_ARGB32_Premultiplied).copy()


def capture_region(grect: QtCore.QRect, down: int = 3,
                   material: str = "focused", liquid: bool = False) -> QtGui.QImage | None:
    """同步抓一块屏幕区域（UI 线程用，弹层这类一开就抓一次的小场景）：
    缩小 + 按材质档位模糊 + 提纯。窗口必须先还没画自己，否则会把自己的半透明内容抓进去。"""
    if grect.width() < 4 or grect.height() < 4:
        return None
    if liquid:
        # 弹层也走折射，采样倍率跟主面板用同一套规则，否则位移场粗一档，边缘立刻见台阶
        down = Backdrop._liquid_down(grect.width(), grect.height())
    tw, th = max(2, int(round(grect.width() / down))), max(2, int(round(grect.height() / down)))
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
    return _frost(img, MATERIAL.get(material, 3), down)


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


class LiveDesktop:
    """GPU desktop duplication with zero-copy frame views and QImage upload."""

    def __init__(self, monitor_index: int = 1):
        self.monitor_index = monitor_index
        self._lock = threading.Lock()
        self._region = None
        self._image = None
        self._phys = None
        self._serial = 0
        self._capture = None
        self._active_region = None

    def start(self):
        pass

    def set_region(self, phys):
        with self._lock:
            self._region = tuple(phys)

    def latest(self):
        with self._lock:
            region = self._region
        if region is None:
            return self.peek()
        if self._capture is None:
            import dxcam
            self._capture = dxcam.create(output_idx=self.monitor_index - 1, output_color="BGRA")
        if region != self._active_region:
            if self._active_region is not None:
                self._capture.stop()
            x, y, w, h = region
            self._capture.start(region=(x, y, x + w, y + h), target_fps=90, video_mode=True)
            self._active_region = region
        frame = self._capture.get_latest_frame_view()
        ticks = self._capture.latest_frame_ticks
        if frame is not None and ticks != self._serial:
            height, width = frame.shape[:2]
            image = QtGui.QImage(frame.data, width, height, width * 4,
                                 QtGui.QImage.Format.Format_ARGB32_Premultiplied).copy()
            with self._lock:
                self._image = image
                self._phys = region
                self._serial = ticks
        return self.peek()

    def peek(self):
        with self._lock:
            return self._image, self._phys, self._serial

    def stop(self):
        if self._capture is not None and self._active_region is not None:
            self._capture.stop()
            self._active_region = None


class Backdrop(QtCore.QObject):
    """后台截取 + 模糊。主线程调用 request() 告知要覆盖的区域，结果通过 ready 信号回到主线程。"""
    ready = QtCore.Signal(bool)          # changed

    def __init__(self):
        super().__init__()
        # (模糊小图, 对应的全局逻辑区域, 亮度)；整体替换，主线程读到的总是一致的一组
        self.state: tuple = (None, QtCore.QRect(), 0.5)
        self.hi: QtGui.QImage | None = None     # 同一区域的全分辨率背景（玻璃中间 1:1 落图）
        self.hi_rect: QtCore.QRect = QtCore.QRect()
        self.version = 0                    # 每产出一张新背景图 +1（QImage 的 id 会被复用，不能当缓存键）
        self.rfx: QtGui.QImage | None = None   # 后台线程算好的折射图，主线程只负责铺
        self.glow: QtGui.QImage | None = None  # 由同一张位移向量场推导的轮廓高光（白色+alpha）
        self._rfx_key = None
        self._optics_cache = {}
        self._glow_cache_key = None
        self._glow_cached = None
        self._shape: tuple | None = None    # 主线程提交的形状 (x, y, w, h, radius, ox, oy)
        self._shape_dirty = False
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
        self.acrylic = False                # 由 Island 按主题决定：液态玻璃开 DWM 亚克力
        self.hole = QtCore.QRect()          # 自家窗口在屏幕上的矩形（这块截图里拿不到真背景）
        self._plate = None                  # 整屏快照（窗口隐藏时抓的干净桌面）
        self._plate_rect = QtCore.QRect()
        self._plate_t = 0.0
        self._sharp = None                  # 未磨砂的那一版，只给边缘折射取样
        self.liquid = False                 # 液态玻璃：背后画面提对比 / 提饱和，折射感更强
        self.direct_gpu = False
        self.material = "regular"           # 材质档位：regular / elevated / focused（见 MATERIAL）
        self._started = False
        self.live = None
        self.live_error = None
        self._live_serial = -1
        self.gpu = None
        self.gpu_error = None
        self.gpu_enabled = True

    def start(self):
        if not self._started:
            self._started = True
            self._thread.start()
        if self.liquid:
            self.start_live()

    def start_live(self):
        if self.live is not None or self.live_error is not None:
            return
        try:
            self.live = LiveDesktop()
            self.live.start()
        except Exception as exc:  # noqa: BLE001
            self.live = None
            self.live_error = str(exc)
            print("实时背景采集不可用，回退到静态快照:", exc)

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
        if self.live is not None:
            self.live.stop()

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
        if self.liquid:
            self.start_live()
            if self.live is not None:
                self.live.set_region(phys)
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
            # 直接 GPU 合成路径不再限制 45 Hz；采集器自身仍按 target_fps 调度。
            gap = time.perf_counter() - last
            if gap < 1 / 120:
                time.sleep(1 / 120 - gap)
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

    @staticmethod
    def _liquid_down(w: float, h: float) -> float:
        """液态玻璃的采样倍率：按面积落在像素预算上，小面板更细、大面板略粗。"""
        px = max(1.0, float(w) * float(h))
        down = (px / LIQUID_PX_BUDGET) ** 0.5
        return max(LIQUID_DOWN_MIN, min(LIQUID_DOWN_MAX, down))

    def set_plate(self, img: QtGui.QImage, rect: QtCore.QRect):
        """主线程：交一张"窗口隐藏时抓到的整屏干净快照"，后台按它裁背景。

        窗口自己不参与截屏是不可能的（排除 → 整块窗口变纯黑；不排除 → 拍到自家上一帧）。
        唯一干净的做法是：抓的那一瞬间把自己的窗口藏起来（见 `Island._snap_plate`）。
        藏一次、抓一张，之后每帧只是从这张快照上裁一块，几乎零成本。
        """
        with self._lock:
            self._plate = img
            self._plate_rect = QtCore.QRect(rect)
            self._plate_t = time.perf_counter()

    def _capture(self, r: QtCore.QRect, phys):
        down = self._liquid_down(r.width(), r.height()) if self.liquid else DOWN
        tw, th = max(2, int(round(r.width() / down))), max(2, int(round(r.height() / down)))
        plate, prt = self._plate, self._plate_rect
        img = None
        hi = None
        hi_rect = QtCore.QRect()
        live_serial = None
        from_live = False
        if self.liquid and self.live is not None:
            live_img, live_phys, live_serial = self.live.latest()
            if live_img is not None and live_phys == phys:
                img = live_img
                hi = live_img.copy()
                hi_rect = QtCore.QRect(r)
                from_live = True
        if img is None and plate is not None and not prt.isEmpty() and prt.contains(r):
            # 快照里有完整的真背景（我们自己不在里面），只裁不抓。
            sc = plate.width() / max(1.0, float(prt.width()))
            sub = QtCore.QRect(int((r.x() - prt.x()) * sc), int((r.y() - prt.y()) * sc),
                               max(2, int(round(r.width() * sc))), max(2, int(round(r.height() * sc)))
                               ).intersected(plate.rect())
            if sub.width() >= 2 and sub.height() >= 2:
                img = plate.copy(sub)
                # 同一块的全分辨率副本：玻璃的**中间**用它 1:1 落图（不再经过 1.69 倍缩小
                # 再放大，背景就是屏幕上那块像素本身），折射带才用下面那张缩略图。
                hi = img.copy()
                hi_rect = QtCore.QRect(prt.x() + int(round(sub.x() / sc)),
                                       prt.y() + int(round(sub.y() / sc)),
                                       max(2, int(round(sub.width() / sc))),
                                       max(2, int(round(sub.height() / sc))))
        if img is None:
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
            # 自家窗口挡住的那块，截图里只能是纯黑 / 自家前一帧；先用四周颜色扩散补掉，
            # 再做磨砂。顺序不能反：先扩散再磨砂，接缝才会被糊掉。
            hole = self.hole
            if not hole.isEmpty():
                sx = tw / max(1.0, float(r.width()))
                sy = th / max(1.0, float(r.height()))
                hl = QtCore.QRect(int((hole.x() - r.x()) * sx), int((hole.y() - r.y()) * sy),
                                  int(hole.width() * sx), int(hole.height() * sy))
                img = _heal(img, hl)
        img = _downscale(img, tw, th)
        img = img.convertToFormat(QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        # 留一张「没磨砂」的：只给边缘折射用，边上一圈才看得清被挤压的结构（中间照样是雾面）
        sharp = img.copy()
        if self.liquid:
            # 磨砂底取消：液态玻璃中间不再做背景模糊，直接铺**真实背景**（只经过小图
            # 放大的一次柔化），磨砂只留在贴边那一圈由 refract 做的位移折射里。
            pass
        else:
            img = _blur(_blur(img))
        mode = QtCore.Qt.TransformationMode.SmoothTransformation
        sig = bytes(img.scaled(8, 4, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio, mode).constBits())
        c = img.scaled(1, 1, QtCore.Qt.AspectRatioMode.IgnoreAspectRatio, mode).pixelColor(0, 0)
        lum = 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
        changed = (from_live and live_serial != self._live_serial) or sig != self._sig or r != self.rect
        if from_live:
            self._live_serial = live_serial
        self._sig = sig
        if changed:
            self._sharp = sharp
            self.hi = hi
            self.hi_rect = hi_rect
            # 内容没变时保留上一张 QImage：省掉一次折射，也不会凭空造出新对象让缓存失效。
            # QImage 的 Python 包装对象会被 pymalloc 立刻复用（id 恒定），所以缓存键只能用
            # 自增的 version，不能用 id(tiny) —— 否则背景刷新了却一直命中第一张折射图。
            self.version += 1
            self.state = (img, QtCore.QRect(r), lum)
        if self.direct_gpu:
            self.ready.emit(changed)
            return
        rfx_changed = self._refract()
        self.ready.emit(changed or rfx_changed)

    def set_shape(self, gb: QtCore.QRect, radius: float, origin: QtCore.QPoint):
        """主线程：形状稳定后提交一次精确形状，后台据此重算折射。

        展开动画期间不提交（形状每帧都在变），沿用上一张折射图即可；动画结束提交一次，
        后台算好后下一次重绘自动生效，UI 线程一次 numpy 都不跑。
        """
        shape = (gb.x(), gb.y(), gb.width(), gb.height(), int(round(radius)), origin.x(), origin.y())
        with self._lock:
            if self._shape == shape and not self._shape_dirty:
                return
            self._shape = shape
            self._shape_dirty = True
        self._wake.set()

    def _refract(self) -> bool:
        """后台线程：按当前背景图 + 提交的形状算一张折射图。返回是否换了新图。"""
        with self._lock:
            shape = self._shape
            dirty = self._shape_dirty
            self._shape_dirty = False
        if shape is None or self.state[0] is None:
            return False
        key = (self.version, shape)
        if key == self._rfx_key and not dirty:
            return False
        tiny, rect, _ = self.state
        x, y, w, h, radius, ox, oy = shape
        # shape 里存的已经是**全局坐标**的 body（调用方传的是 body.translated(origin)）。
        # 这里再 translate 一次就整体偏移一个窗口原点的距离，SDF 会把整块面板判成"形状外面"，
        # 于是每个像素都走 sharp 分支（t=1）：中间那一片就变成了没磨砂的原始截图 —— 又脏又没铺满。
        gb = QtCore.QRectF(x, y, w, h)
        img = None
        if self.gpu_enabled and self.gpu_error is None:
            try:
                if self.gpu is None:
                    from .gpu_glass import GpuRefractor
                    self.gpu = GpuRefractor()
                img = self.gpu.render(self._sharp or tiny, rect, gb, radius,
                                      amp_k=0.68, flat=0.90, ring_fade=1.25)
            except Exception as exc:  # noqa: BLE001
                self.gpu = None
                self.gpu_error = str(exc)
                print("GPU 折射不可用，回退到 CPU:", exc)
        try:
            if img is None:
                img = refract(tiny, rect, gb, radius, amp_k=0.68, flat=0.90, gamma=1.65,
                              ring_only=True, ring_fade=1.25, sharp=self._sharp, _cache=self._optics_cache)
            glow_key = (tiny.width(), tiny.height(), rect.getRect(), shape)
            if glow_key != self._glow_cache_key:
                self._glow_cached = highlight_field(tiny.width(), tiny.height(), rect, gb, radius)
                self._glow_cache_key = glow_key
            glow = self._glow_cached
        except Exception:  # noqa: BLE001
            img, glow = tiny, None
        self.rfx = img
        self.glow = glow
        self._rfx_key = key
        return True

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

    def liquid_image(self, body: QtCore.QRectF, radius: float, window_origin: QtCore.QPoint,
                     animate: bool = False):
        """液态玻璃用：返回 (折射图, 抓屏矩形)，调用方自己按矩形画图。

        比 brush_liquid 返回纹理画刷稳妥：QBrush 的图案在没盖住的区域会平铺/露底，
        面板比抓屏区大时就会露出一条硬直边的色带。

        动画期间（形状每帧都在变）不能用旧折射图：它是按上一版形状算的 SDF，
        铺到已经长大的面板上，中间就只有一小条被判成"形状内"，其余全是"边/外"，
        画面变成"中间一小块磨砂、四周透出清晰背景"，而且这块会跟着面板长大到处移动。
        与其贴一张错形状的，不如这一帧直接用磨砂底，等形状稳定再上折射。
        """
        tiny, rect, _ = self.state
        if tiny is None:
            return None
        if not animate:
            self.set_shape(body.toAlignedRect(), radius, window_origin)
            return (self.rfx if self.rfx is not None else tiny), rect
        shape = self._shape
        if shape is not None:
            gw, gh = abs(shape[2]), abs(shape[3])
            if (abs(gw - body.width()) > max(8.0, body.width() * 0.06)
                    or abs(gh - body.height()) > max(8.0, body.height() * 0.06)):
                return tiny, rect
        return (self.rfx if self.rfx is not None else tiny), rect

    def brush_liquid(self, body: QtCore.QRectF, radius: float, window_origin: QtCore.QPoint,
                     animate: bool = False) -> QtGui.QBrush | None:
        """液态玻璃用：直接铺后台线程算好的折射图，主线程只做一次画刷变换。

        折射（numpy 位移采样，大岛 12~20ms）整个放在截图线程里：背景有变化 / 形状稳定后
        后台重算一张，主线程每帧命中现成的 QImage。animate=True 是展开/收起动画，形状每帧
        都在变，不提交新形状、沿用上一张即可；动画结束后提交一次精确形状。
        """
        tiny, rect, _ = self.state
        if tiny is None:
            return None
        if not animate:
            self.set_shape(body.toAlignedRect(), radius, window_origin)
        img = self.rfx if self.rfx is not None else tiny
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
