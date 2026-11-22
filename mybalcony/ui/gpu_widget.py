# -*- coding: utf-8 -*-
"""Direct OpenGL liquid-glass canvas with a Qt-painted foreground."""
from __future__ import annotations

from PySide6 import QtCore, QtGui, QtOpenGLWidgets

_VERTEX = """#version 330 core
out vec2 uv;
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    uv = p;
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""

_FRAGMENT = """#version 330 core
in vec2 uv;
out vec4 outColor;
uniform sampler2D hiTex;
uniform sampler2D tinyTex;
uniform sampler2D fgTex;
uniform vec2 viewportSize;
uniform float deviceRatio;
uniform vec2 bodyCenter;
uniform vec2 bodyGlobal;
uniform vec2 halfSize;
uniform float cornerRadius;
uniform float thickness;
uniform float amplitude;
uniform float lensScale;
uniform float ringFade;
uniform float useForeground;
uniform vec4 tinyRect;
uniform vec4 hiRect;
uniform vec2 tinyTexel;

vec4 sampleTopDown(sampler2D tex, vec2 coord) {
    return texture(tex, coord);
}

vec4 sampleTiny(vec2 coord) {
    return sampleTopDown(tinyTex, clamp(coord, 0.0, 1.0));
}

vec4 gaussianCenter(vec2 coord) {
    float weights[5] = float[5](0.09917, 0.23958, 0.32246, 0.23958, 0.09917);
    vec2 stepUV = tinyTexel * 1.25;
    vec4 color = vec4(0.0);
    for (int y = -2; y <= 2; ++y) {
        for (int x = -2; x <= 2; ++x) {
            vec2 offset = vec2(float(x), float(y)) * stepUV;
            color += sampleTiny(coord + offset) * weights[x + 2] * weights[y + 2];
        }
    }
    return color;
}

void main() {
    vec2 localPos = (vec2(uv.x, 1.0 - uv.y) * viewportSize - vec2(0.5)) / deviceRatio;
    vec2 p = localPos - bodyCenter;
    vec2 q = abs(p) - (halfSize - vec2(cornerRadius));
    vec2 outer = max(q, 0.0);
    float outside = length(outer);
    float sd = outside + min(max(q.x, q.y), 0.0) - cornerRadius;
    float shapeAlpha = clamp(0.5 - sd * deviceRatio, 0.0, 1.0);
    if (shapeAlpha <= 0.0) {
        outColor = vec4(0.0);
        return;
    }
    float band = clamp(1.0 - max(-sd, 0.0) / thickness, 0.0, 1.0);
    float circleMap = 1.0 - sqrt(max(1.0 - band * band, 0.0));
    vec2 gradient = vec2(
        q.x > 0.0 ? outer.x / max(outside, 0.000001) * sign(p.x) : (q.x > q.y ? sign(p.x) : 0.0),
        q.y > 0.0 ? outer.y / max(outside, 0.000001) * sign(p.y) : (q.y > q.x ? sign(p.y) : 0.0)
    );
    float displacement = -thickness * amplitude * circleMap;
    vec2 globalCenter = bodyGlobal + p;
    vec2 globalSample = bodyGlobal + p * lensScale + gradient * displacement;
    vec2 hiUV = (globalCenter - hiRect.xy) / hiRect.zw;
    vec2 tinyUV = (globalSample - tinyRect.xy) / tinyRect.zw;
    vec4 base = gaussianCenter(hiUV);
    vec4 refracted = sampleTiny(tinyUV);
    float coverage = clamp(circleMap * ringFade, 0.0, 1.0);
    vec4 color = mix(base, refracted, coverage);
    float film = 0.035 + 0.025 * clamp(1.0 - localPos.y / max(bodyCenter.y * 2.0, 1.0), 0.0, 1.0);
    color.rgb = mix(color.rgb, vec3(color.a), film);
    float lit = 0.72 * (max(0.0, dot(gradient, normalize(vec2(-1.0, 1.0))))
                      + max(0.0, dot(gradient, normalize(vec2(1.0, -1.0)))));
    float edgeLight = pow(clamp(lit, 0.0, 1.0), 1.6) * pow(band, 1.2) * 0.20;
    color.rgb += vec3(edgeLight * color.a);
    outColor = vec4(color.rgb * shapeAlpha, color.a * shapeAlpha);
    if (useForeground > 0.5) {
        vec4 foreground = texture(fgTex, vec2(uv.x, 1.0 - uv.y));
        outColor = vec4(foreground.rgb + outColor.rgb * (1.0 - foreground.a),
                        foreground.a + outColor.a * (1.0 - foreground.a));
    }
}
"""


class GlassGLWidget(QtOpenGLWidgets.QOpenGLWidget):
    def __init__(self, island):
        super().__init__(island)
        fmt = QtGui.QSurfaceFormat()
        fmt.setRenderableType(QtGui.QSurfaceFormat.RenderableType.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QtGui.QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setAlphaBufferSize(8)
        fmt.setSwapInterval(0)
        self.setFormat(fmt)
        self.island = island
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setUpdateBehavior(QtOpenGLWidgets.QOpenGLWidget.UpdateBehavior.NoPartialUpdate)
        self.setGeometry(island.rect())
        self._textures = {}
        self._uniforms = {}
        self._foreground = None
        self._foreground_key = None
        self._foreground_time = 0.0
        self._foreground_dirty = False
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
        self._textures = {"hi": GL.glGenTextures(1), "tiny": GL.glGenTextures(1), "fg": GL.glGenTextures(1)}
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
        texture = self._textures[key]
        width, height = image.width(), image.height()
        GL.glBindTexture(GL.GL_TEXTURE_2D, texture)
        if image.size() != self._textures.get(key + "_size"):
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, width, height, 0,
                            GL.GL_BGRA, GL.GL_UNSIGNED_BYTE, None)
            self._textures[key + "_size"] = image.size()
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glPixelStorei(GL.GL_UNPACK_ROW_LENGTH, image.bytesPerLine() // 4)
        GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, 0, 0, width, height,
                           GL.GL_BGRA, GL.GL_UNSIGNED_BYTE, bytes(image.constBits()))
        GL.glPixelStorei(GL.GL_UNPACK_ROW_LENGTH, 0)

    def paintGL(self):
        import time
        from OpenGL import GL
        cached = self.island.expanded and self._ensure_foreground(time.perf_counter())
        p = QtGui.QPainter(self)
        p.beginNativePainting()
        GL.glClearColor(0, 0, 0, 0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)
        backdrop = self.island.backdrop
        tiny, rect, _ = backdrop.state
        hi, hi_rect, sharp = backdrop.hi, backdrop.hi_rect, backdrop._sharp
        if tiny is not None and hi is not None and sharp is not None and not hi_rect.isEmpty():
            self._upload("hi", hi)
            self._upload("tiny", sharp)
            if cached and self._foreground_dirty:
                self._upload("fg", self._foreground)
                self._foreground_dirty = False
            self._draw_lens(tiny, rect, hi_rect, cached)
        p.endNativePainting()
        if not cached:
            p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
            p.translate(-self.geometry().topLeft())
            self.island._paint_foreground(p, self.island.path)
        p.end()

    def _ensure_foreground(self, now):
        island = self.island
        shape = island.path.boundingRect()
        page = island.stack.currentWidget()
        spec = island._spec_pos if now < island._spec_until else None
        key = (shape, island.body, page, spec, island.content_a.x, island.compact_a.x)
        if self._foreground is not None and key == self._foreground_key:
            return True
        dpr = self.devicePixelRatioF()
        image = QtGui.QImage(round(self.width() * dpr), round(self.height() * dpr),
                             QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(dpr)
        image.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(-self.geometry().topLeft())
        island._paint_foreground(painter, island.path)
        painter.end()
        self._foreground = image
        self._foreground_key = key
        self._foreground_time = now
        self._foreground_dirty = True
        return True

    def _draw_lens(self, tiny, rect, hi_rect, cached):
        from OpenGL import GL
        from .island import panel_radius
        island = self.island
        shape = island.path.boundingRect()
        if shape.isEmpty():
            return
        dpr = self.devicePixelRatioF()
        width, height = self.width() * dpr, self.height() * dpr
        global_shape = shape.translated(QtCore.QPointF(island._win_origin))
        center = shape.center() - self.geometry().topLeft()
        global_center = global_shape.center()
        hw, hh = shape.width() / 2.0, shape.height() / 2.0
        corner = panel_radius(shape.width(), shape.height())
        thickness = max(2.0, min(hw, hh) * 0.10)
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
        GL.glUniform1f(self._uniform("useForeground"), 1.0 if cached else 0.0)
        if cached:
            GL.glActiveTexture(GL.GL_TEXTURE2)
            GL.glBindTexture(GL.GL_TEXTURE_2D, self._textures["fg"])
            GL.glUniform1i(self._uniform("fgTex"), 2)
        GL.glUniform2f(self._uniform("viewportSize"), width, height)
        GL.glUniform1f(self._uniform("deviceRatio"), dpr)
        GL.glUniform2f(self._uniform("bodyCenter"), center.x(), center.y())
        GL.glUniform2f(self._uniform("bodyGlobal"), global_center.x(), global_center.y())
        GL.glUniform2f(self._uniform("halfSize"), hw, hh)
        GL.glUniform1f(self._uniform("cornerRadius"), corner)
        GL.glUniform1f(self._uniform("thickness"), thickness)
        GL.glUniform1f(self._uniform("amplitude"), 0.68)
        GL.glUniform1f(self._uniform("lensScale"), 1.0)
        GL.glUniform1f(self._uniform("ringFade"), 1.25)
        GL.glUniform4f(self._uniform("tinyRect"), rect.x(), rect.y(), rect.width(), rect.height())
        GL.glUniform4f(self._uniform("hiRect"), hi_rect.x(), hi_rect.y(), hi_rect.width(), hi_rect.height())
        GL.glUniform2f(self._uniform("tinyTexel"), 1.0 / tiny.width(), 1.0 / tiny.height())
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
