# -*- coding: utf-8 -*-
"""Native OpenGL implementation of the rounded-SDF liquid lens."""
from __future__ import annotations

from PySide6 import QtCore, QtGui

from .glass import REFRACT_BAND_SCALE

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
uniform sampler2D sourceTex;
uniform vec2 textureSize;
uniform vec2 lensCenter;
uniform vec2 halfSize;
uniform float cornerRadius;
uniform float thickness;
uniform float bandWidth;
uniform float amplitude;
uniform float lensScale;
uniform float ringFade;

void main() {
    vec2 pos = uv * textureSize - vec2(0.5);
    vec2 p = pos - lensCenter;
    vec2 q = abs(p) - (halfSize - vec2(cornerRadius));
    vec2 outer = max(q, 0.0);
    float outside = length(outer);
    float sd = outside + min(max(q.x, q.y), 0.0) - cornerRadius;
    float band = clamp(1.0 - max(-sd, 0.0) / bandWidth, 0.0, 1.0);
    float circleMap = 1.0 - sqrt(max(1.0 - band * band, 0.0));
    vec2 gradient = vec2(
        q.x > 0.0 ? outer.x / max(outside, 0.000001) * sign(p.x) : (q.x > q.y ? sign(p.x) : 0.0),
        q.y > 0.0 ? outer.y / max(outside, 0.000001) * sign(p.y) : (q.y > q.x ? sign(p.y) : 0.0)
    );
    float displacement = -thickness * amplitude * circleMap;
    vec2 samplePos = lensCenter + p * lensScale + gradient * displacement;
    samplePos = clamp(samplePos, vec2(0.0), textureSize - vec2(0.001));
    vec4 color = texture(sourceTex, (samplePos + vec2(0.5)) / textureSize);
    float coverage = clamp(circleMap * ringFade, 0.0, 1.0);
    outColor = vec4(color.rgb * coverage, color.a * coverage);
}
"""


class GpuRefractor:
    """Offscreen OpenGL 3.3 renderer owned by one worker thread."""

    def __init__(self):
        self.surface = QtGui.QOffscreenSurface()
        fmt = QtGui.QSurfaceFormat()
        fmt.setRenderableType(QtGui.QSurfaceFormat.RenderableType.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QtGui.QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        self.surface.setFormat(fmt)
        self.surface.create()
        if not self.surface.isValid():
            raise RuntimeError("QOffscreenSurface is unavailable")
        self.context = QtGui.QOpenGLContext()
        self.context.setFormat(fmt)
        if not self.context.create():
            raise RuntimeError("OpenGL 3.3 context creation failed")
        if not self.context.makeCurrent(self.surface):
            raise RuntimeError("Cannot activate OpenGL context")

        from OpenGL.GL import shaders
        self.program = shaders.compileProgram(
            shaders.compileShader(_VERTEX, shaders.GL_VERTEX_SHADER),
            shaders.compileShader(_FRAGMENT, shaders.GL_FRAGMENT_SHADER),
        )
        self._init_buffers()
        self._size = None
        self._uniforms = {}

    def _init_buffers(self):
        from OpenGL import GL
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        self.input_texture = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.input_texture)
        for name, value in ((GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR),
                            (GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR),
                            (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE),
                            (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, name, value)
        self.output_texture = GL.glGenTextures(1)
        self.fbo = GL.glGenFramebuffers(1)
        GL.glDisable(GL.GL_BLEND)
        GL.glDisable(GL.GL_DEPTH_TEST)

    def _resize(self, width: int, height: int):
        if self._size == (width, height):
            return
        from OpenGL import GL
        self._size = (width, height)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.input_texture)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, width, height, 0,
                        GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.output_texture)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, width, height, 0,
                        GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
        for name, value in ((GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR),
                            (GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR),
                            (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE),
                            (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, name, value)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
        GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0,
                                  GL.GL_TEXTURE_2D, self.output_texture, 0)
        if GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) != GL.GL_FRAMEBUFFER_COMPLETE:
            raise RuntimeError("OpenGL framebuffer is incomplete")

    def _uniform(self, name: str):
        from OpenGL import GL
        if name not in self._uniforms:
            self._uniforms[name] = GL.glGetUniformLocation(self.program, name)
        return self._uniforms[name]

    def render(self, sharp: QtGui.QImage, rect: QtCore.QRect, body: QtCore.QRectF,
               radius: float, amp_k: float = 0.68, flat: float = 0.90,
               lens: float = 1.0, ring_fade: float = 1.25) -> QtGui.QImage:
        from OpenGL import GL
        if self.context.currentContext() is not self.context:
            self.context.makeCurrent(self.surface)
        width, height = sharp.width(), sharp.height()
        self._resize(width, height)
        rgba = sharp.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.input_texture)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, 0, 0, width, height,
                           GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, bytes(rgba.constBits()))

        scale = width / max(1.0, float(rect.width()))
        hw = max(1.0, body.width() * scale / 2.0)
        hh = max(1.0, body.height() * scale / 2.0)
        corner = max(1.0, min(radius * scale, hw - 0.5, hh - 0.5))
        cx = (body.center().x() - rect.x()) * scale
        cy = (body.center().y() - rect.y()) * scale
        thickness = max(2.0, min(hw, hh) * (1.0 - flat))

        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
        GL.glViewport(0, 0, width, height)
        GL.glUseProgram(self.program)
        GL.glUniform1i(self._uniform("sourceTex"), 0)
        GL.glUniform2f(self._uniform("textureSize"), width, height)
        GL.glUniform2f(self._uniform("lensCenter"), cx, cy)
        GL.glUniform2f(self._uniform("halfSize"), hw, hh)
        GL.glUniform1f(self._uniform("cornerRadius"), corner)
        GL.glUniform1f(self._uniform("thickness"), thickness)
        GL.glUniform1f(self._uniform("bandWidth"), max(2.0, thickness * REFRACT_BAND_SCALE))
        GL.glUniform1f(self._uniform("amplitude"), amp_k)
        GL.glUniform1f(self._uniform("lensScale"), lens)
        GL.glUniform1f(self._uniform("ringFade"), ring_fade)
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        data = GL.glReadPixels(0, 0, width, height, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE)
        return QtGui.QImage(data, width, height, width * 4,
                            QtGui.QImage.Format.Format_RGBA8888_Premultiplied).copy()
