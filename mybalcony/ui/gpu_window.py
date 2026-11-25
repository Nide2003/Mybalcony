# -*- coding: utf-8 -*-
"""Native top-level OpenGL background window, below the Qt foreground island."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtOpenGL

from .glass import REFRACT_BAND_SCALE
from .gpu_widget import _VERTEX, _FRAGMENT, SeparableBlur, center_blur_radius


class NativeGlassWindow(QtOpenGL.QOpenGLWindow):
    def __init__(self, island):
        super().__init__()
        fmt = QtGui.QSurfaceFormat()
        fmt.setRenderableType(QtGui.QSurfaceFormat.RenderableType.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QtGui.QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setAlphaBufferSize(8)
        fmt.setSwapInterval(0)
        self.setFormat(fmt)
        self.island = island
        self.setFlags(QtCore.Qt.WindowType.FramelessWindowHint
                      | QtCore.Qt.WindowType.Tool
                      | QtCore.Qt.WindowType.WindowStaysOnTopHint
                      | QtCore.Qt.WindowType.WindowTransparentForInput
                      | QtCore.Qt.WindowType.WindowDoesNotAcceptFocus)
        self._textures = {}
        self._uniforms = {}
        self.program = None
        self.blur = SeparableBlur()

    def initializeGL(self):
        from OpenGL import GL
        from OpenGL.GL import shaders
        self.program = shaders.compileProgram(
            shaders.compileShader(_VERTEX, shaders.GL_VERTEX_SHADER),
            shaders.compileShader(_FRAGMENT, shaders.GL_FRAGMENT_SHADER),
        )
        self.blur.initialize()
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        self._textures = {"bg": GL.glGenTextures(1)}
        for key, texture in self._textures.items():
            GL.glBindTexture(GL.GL_TEXTURE_2D, texture)
            for name, value in ((GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR),
                                (GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR),
                                (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE),
                                (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)):
                GL.glTexParameteri(GL.GL_TEXTURE_2D, name, value)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDisable(GL.GL_DEPTH_TEST)

    def _uniform(self, name):
        from OpenGL import GL
        if name not in self._uniforms:
            self._uniforms[name] = GL.glGetUniformLocation(self.program, name)
        return self._uniforms[name]

    def _upload(self, key, image):
        from OpenGL import GL
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._textures[key])
        width, height = image.width(), image.height()
        if image.size() != self._textures.get(key + "_size"):
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, width, height, 0,
                            GL.GL_BGRA, GL.GL_UNSIGNED_BYTE, None)
            self._textures[key + "_size"] = image.size()
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glPixelStorei(GL.GL_UNPACK_ROW_LENGTH, image.bytesPerLine() // 4)
        GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, 0, 0, width, height,
                           GL.GL_BGRA, GL.GL_UNSIGNED_BYTE, image.constBits())
        GL.glPixelStorei(GL.GL_UNPACK_ROW_LENGTH, 0)

    def update(self):
        self.requestUpdate()

    def sync_geometry(self):
        from .glass import _u32, WDA_EXCLUDEFROMCAPTURE
        from ..core.config import cfg
        # 玻璃层默认排除在截图外（否则玻璃里会抓到自家上一帧）；
        # island.capture_self=True 时解除，方便截图/录屏出图。
        want = 0 if bool(cfg.get("island.capture_self", False)) else WDA_EXCLUDEFROMCAPTURE
        if getattr(self, "_affinity", None) != want:
            _u32.SetWindowDisplayAffinity(int(self.winId()), want)
            self._affinity = want
        shape = self.island.path.boundingRect().translated(QtCore.QPointF(self.island._win_origin))
        rect = shape.toAlignedRect().adjusted(-2, -2, 2, 2)
        if rect != self.geometry():
            self.setGeometry(rect)

    def paintGL(self):
        from OpenGL import GL
        GL.glClearColor(0, 0, 0, 0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        backdrop = self.island.backdrop
        hi, hi_rect = backdrop.hi, backdrop.hi_rect
        if hi is None or hi_rect.isEmpty():
            return
        self._upload("bg", hi)
        radius = center_blur_radius(hi, hi_rect)
        blurred = self.blur.blur(self._textures["bg"], hi.width(), hi.height(), radius)
        self._draw_lens(hi_rect, blurred)

    def _draw_lens(self, hi_rect, blurred_texture):
        from OpenGL import GL
        from .island import panel_radius
        island = self.island
        # 用本体矩形而不是 path.boundingRect()：贴边时液桥会让后者左右各多出一个
        # fillet（约 13px），SDF 就跟着画到边框外——这正是"左右折射带超出"的来源。
        # body 是纯圆角矩形，四边都精确对齐前景描边的边框。
        shape = island.body
        if shape.isEmpty():
            return
        global_shape = shape.translated(QtCore.QPointF(island._win_origin))
        local_shape = global_shape.translated(-QtCore.QPointF(self.geometry().topLeft()))
        center = local_shape.center()
        global_center = global_shape.center()
        hw, hh = shape.width() / 2.0, shape.height() / 2.0
        dpr = self.devicePixelRatio()
        width, height = self.width() * dpr, self.height() * dpr
        GL.glViewport(0, 0, round(width), round(height))
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glUseProgram(self.program)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._textures["bg"])
        GL.glUniform1i(self._uniform("bgTex"), 0)
        GL.glActiveTexture(GL.GL_TEXTURE1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, blurred_texture)
        GL.glUniform1i(self._uniform("blurredTex"), 1)
        GL.glUniform1f(self._uniform("useForeground"), 0.0)
        GL.glUniform2f(self._uniform("viewportSize"), width, height)
        GL.glUniform1f(self._uniform("deviceRatio"), dpr)
        GL.glUniform2f(self._uniform("bodyCenter"), center.x(), center.y())
        GL.glUniform2f(self._uniform("bodyGlobal"), global_center.x(), global_center.y())
        GL.glUniform2f(self._uniform("halfSize"), hw, hh)
        GL.glUniform1f(self._uniform("cornerRadius"), panel_radius(shape.width(), shape.height()))
        # 位移幅度仍由 thickness 控制（保持原折射手感）；bandWidth 只决定折射带往内铺多宽。
        # 往内扩宽到约 2×：让折射/饱和/彩边在边框内铺得更开，最外沿仍钉在 sd=0 的边框上。
        thickness = min(12.0, max(2.0, min(hw, hh) * 0.30))
        GL.glUniform1f(self._uniform("thickness"), thickness)
        GL.glUniform1f(self._uniform("bandWidth"),
                       min(45.0, max(9.0, thickness * 3.6)) * REFRACT_BAND_SCALE)
        GL.glUniform1f(self._uniform("amplitude"), 1.2)
        GL.glUniform1f(self._uniform("dispersion"), 0.0)
        GL.glUniform1f(self._uniform("lensScale"), 1.0)
        GL.glUniform1f(self._uniform("ringFade"), 1.25)
        # 背景亮度：亮底时边缘从"加白刃口"切换成"厚度暗侧"定形，纯白背景才看得出岛体边界。
        GL.glUniform1f(self._uniform("lightBg"), float(getattr(self.island, "_light_bg", 0.0)))
        GL.glUniform4f(self._uniform("hiRect"), hi_rect.x(), hi_rect.y(), hi_rect.width(), hi_rect.height())
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
