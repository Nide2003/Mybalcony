# -*- coding: utf-8 -*-
"""把方形图片中心的正圆内容抠成透明底，并生成 Windows 多尺寸 .ico。

用法（在仓库根目录）：
    .venv\\Scripts\\python.exe scripts\\make_icon.py 源图.png ^
        packaging\\mybalcony.ico packaging\\mybalcony.png

不依赖 Pillow：读图、圆形裁切、缩放、ICO 封装都用 PySide6 + 手写 ICONDIR。
圆外区域会变透明，圆边做抗锯齿，避免任务栏/资源管理器里出现四角黑边。
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6 import QtCore, QtGui

SIZES = [256, 128, 96, 64, 48, 32, 24, 16]
INK_THRESHOLD = 30          # 低于它视为黑底
EDGE_INSET = 2.0            # 半径向内收的像素，吃掉圆边缘残留的黑环


def _content_bbox(img: QtGui.QImage) -> QtCore.QRect:
    """找到非黑内容的外接框：逐行/逐列统计非黑像素数量。"""
    import numpy as np

    w, h = img.width(), img.height()
    arr = np.frombuffer(img.constBits(), dtype=np.uint8).reshape(h, img.bytesPerLine() // 4, 4)
    lum = arr[:, :, :3].max(axis=2)
    mask = lum > INK_THRESHOLD
    cols = np.where(mask.sum(axis=0) > h * 0.02)[0]
    rows = np.where(mask.sum(axis=1) > w * 0.02)[0]
    if len(cols) == 0 or len(rows) == 0:
        return QtCore.QRect(0, 0, w, h)
    return QtCore.QRect(int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1))


def circular_icon(src: Path, canvas: int = 1024) -> QtGui.QImage:
    img = QtGui.QImage(str(src))
    if img.isNull():
        raise SystemExit(f"读不到图片：{src}")
    img = img.convertToFormat(QtGui.QImage.Format_ARGB32_Premultiplied)

    box = _content_bbox(img)
    cx = box.x() + box.width() / 2
    cy = box.y() + box.height() / 2
    r = min(box.width(), box.height()) / 2 - EDGE_INSET

    out = QtGui.QImage(canvas, canvas, QtGui.QImage.Format_ARGB32_Premultiplied)
    out.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(out)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)

    clip = QtGui.QPainterPath()
    clip.addEllipse(QtCore.QRectF(0, 0, canvas, canvas))
    painter.setClipPath(clip)

    src_rect = QtCore.QRectF(cx - r, cy - r, r * 2, r * 2)
    painter.drawImage(QtCore.QRectF(0, 0, canvas, canvas), img, src_rect)
    painter.end()
    return out


def _png_bytes(img: QtGui.QImage) -> bytes:
    buf = QtCore.QBuffer()
    buf.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def write_ico(path: Path, base: QtGui.QImage, sizes: list[int]) -> None:
    entries, blobs = b"", b""
    offset = 6 + 16 * len(sizes)
    for size in sizes:
        scaled = base.scaled(
            size, size,
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        data = _png_bytes(scaled)
        dim = 0 if size >= 256 else size          # ICO 里 0 表示 256
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        blobs += data
    header = struct.pack("<HHH", 0, 1, len(sizes))
    path.write_bytes(header + entries + blobs)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = Path(sys.argv[1])
    ico_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("packaging/mybalcony.ico")
    png_path = Path(sys.argv[3]) if len(sys.argv) > 3 else ico_path.with_suffix(".png")

    base = circular_icon(src)
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    write_ico(ico_path, base, SIZES)
    base.scaled(512, 512, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation).save(str(png_path), "PNG")
    print(f"ico: {ico_path} ({ico_path.stat().st_size} bytes, {len(SIZES)} sizes)")
    print(f"png: {png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
