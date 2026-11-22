# -*- coding: utf-8 -*-
"""Native top-level OpenGL background window, below the Qt foreground island."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtOpenGL

from .gpu_widget import _VERTEX, _FRAGMENT


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

    def initializeGL(self):
        from OpenGL import GL
        from OpenGL.GL import shaders
        self.program = shaders.compileProgram(
            shaders.compileShader(_VERTEX, shaders.GL_VERTEX_SHADER),
            shaders.compileShader(_FRAGMENT, shaders.GL_FRAGMENT_SHADER),
        )
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        self._textures = {"hi": GL.glGenTextures(1), "tiny": GL.glGenTextures(1)}
        for texture in self._textures.values():
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
        if not getattr(self, "_capture_excluded", False):
            _u32.SetWindowDisplayAffinity(int(self.winId()), WDA_EXCLUDEFROMCAPTURE)
            self._capture_excluded = True
        shape = self.island.path.boundingRect().translated(QtCore.QPointF(self.island._win_origin))
        rect = shape.toAlignedRect().adjusted(-2, -2, 2, 2)
        if rect != self.geometry():
            self.setGeometry(rect)

    def paintGL(self):
        from OpenGL import GL
        GL.glClearColor(0, 0, 0, 0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        backdrop = self.island.backdrop
        tiny, rect, _ = backdrop.state
        hi, hi_rect, sharp = backdrop.hi, backdrop.hi_rect, backdrop._sharp
        if tiny is None or hi is None or sharp is None or hi_rect.isEmpty():
            return
        self._upload("hi", hi)
        self._upload("tiny", sharp)
        self._draw_lens(tiny, rect, hi_rect)

    def _draw_lens(self, tiny, rect, hi_rect):
        from OpenGL import GL
        from .island import panel_radius
        island = self.island
        shape = island.path.boundingRect()
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
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._textures["hi"])
        GL.glActiveTexture(GL.GL_TEXTURE1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self._textures["tiny"])
        GL.glUniform1i(self._uniform("hiTex"), 0)
        GL.glUniform1i(self._uniform("tinyTex"), 1)
        GL.glUniform1f(self._uniform("useForeground"), 0.0)
        GL.glUniform2f(self._uniform("viewportSize"), width, height)
        GL.glUniform1f(self._uniform("deviceRatio"), dpr)
        GL.glUniform2f(self._uniform("bodyCenter"), center.x(), center.y())
        GL.glUniform2f(self._uniform("bodyGlobal"), global_center.x(), global_center.y())
        GL.glUniform2f(self._uniform("halfSize"), hw, hh)
        GL.glUniform1f(self._uniform("cornerRadius"), panel_radius(shape.width(), shape.height()))
        GL.glUniform1f(self._uniform("thickness"), max(2.0, min(hw, hh) * 0.10))
        GL.glUniform1f(self._uniform("amplitude"), 0.68)
        GL.glUniform1f(self._uniform("lensScale"), 1.0)
        GL.glUniform1f(self._uniform("ringFade"), 1.25)
        GL.glUniform4f(self._uniform("tinyRect"), rect.x(), rect.y(), rect.width(), rect.height())
        GL.glUniform4f(self._uniform("hiRect"), hi_rect.x(), hi_rect.y(), hi_rect.width(), hi_rect.height())
        GL.glUniform2f(self._uniform("tinyTexel"), 1.0 / tiny.width(), 1.0 / tiny.height())
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
