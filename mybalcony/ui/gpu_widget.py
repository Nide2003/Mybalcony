# -*- coding: utf-8 -*-
"""Direct OpenGL liquid-glass canvas with a Qt-painted foreground.

液态玻璃分层光学：边缘一圈用 SDF 折射带（circleMap / 解析梯度）做清晰扭曲，中心用一层
透亮的 5x5 高斯模糊（2-pass 可分离 5-tap、sigma≈1，仅 ±2 逻辑像素）轻微柔化背景。
coverage = circleMap 把两者平滑混合：中心走模糊、边缘走折射。色散默认关闭（无色）。
"""
from __future__ import annotations

import math

from PySide6 import QtCore, QtGui, QtOpenGLWidgets

# 中心 5x5 透亮高斯：5-tap 一维核，采样偏移为整数步长 -2..2，权重 exp(-0.5*(t/sigma)^2)。
# sigma 小 → 模糊极轻、背景透亮可辨，不会像 33-tap/sigma9 那样糊成磨砂。
# sigma 与采样步长同步放大：5-tap 的空间覆盖是 ±2×步长，只调 sigma 不改步长的话核
# 只会变"平"、不会变"糊"。两者同为 1.5 → 覆盖 ±3 逻辑像素，模糊感正好 +50%。
_GAUSSIAN_TAPS = 5
_GAUSSIAN_SIGMA = 1.5
_GAUSSIAN_STEP = 1.5


def _gaussian_kernel_1d(tap_count: int = _GAUSSIAN_TAPS):
    """5-tap 一维高斯核；offset 为整数采样步长，两 pass 组合成 5x5。"""
    if tap_count <= 1:
        return [(0.0, 1.0)]
    taps = []
    half = tap_count // 2
    total = 0.0
    for i in range(tap_count):
        t = (i - half) if tap_count % 2 else (i - half + 0.5)
        weight = math.exp(-0.5 * (t / _GAUSSIAN_SIGMA) ** 2)
        taps.append((float(t), weight))
        total += weight
    return [(offset, weight / total) for offset, weight in taps]


def center_blur_radius(hi_image, hi_rect) -> float:
    """5x5 高斯的采样步长（纹素）：_GAUSSIAN_STEP 逻辑像素 × 实测纹素密度。

    5 taps × 步长覆盖 ±2×1.5=±3 逻辑像素。hi 在 live 路径是全物理分辨率、
    plate 路径是整屏快照裁片，密度不同，必须由 hi.width / hiRect.width 实测推导，
    不能写死 dpr。两 GL 视图共用。
    """
    texels_per_logical_px = hi_image.width() / max(1.0, float(hi_rect.width()))
    return max(1.0, _GAUSSIAN_STEP * texels_per_logical_px)


_VERTEX = """#version 330 core
out vec2 uv;
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    uv = p;
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}
"""


def _make_blur_fragment() -> str:
    """生成 5-tap 一维高斯模糊片元 shader（水平/垂直共用，两 pass 合成 5x5）。"""
    lines = []
    for offset, weight in _gaussian_kernel_1d():
        lines.append(
            "    { vec4 s = texture(uTexture, uv + uDir * %.6f * uRadius / uTexSize); "
            "float aw = s.a * %.8f; rgbSum += s.rgb * aw; rgbW += aw; }" % (offset, weight)
        )
    samples = "\n".join(lines)
    return """#version 330 core
in vec2 uv;
out vec4 outColor;
uniform sampler2D uTexture;
uniform vec2 uTexSize;
uniform float uRadius;
uniform vec2 uDir;
void main() {
    if (uRadius < 0.5) { outColor = texture(uTexture, uv); return; }
    vec3 rgbSum = vec3(0.0);
    float rgbW = 0.0;
%s
    float origA = texture(uTexture, uv).a;
    outColor = vec4(rgbW > 0.001 ? rgbSum / rgbW : vec3(0.0), origA);
}
""" % samples


_BLUR_FRAGMENT = _make_blur_fragment()

_FRAGMENT = """#version 330 core
in vec2 uv;
out vec4 outColor;
// bgTex = 清晰背景（折射带用）；blurredTex = 2-pass 高斯后的背景（中心 base 用）。
uniform sampler2D bgTex;
uniform sampler2D blurredTex;
uniform sampler2D fgTex;
uniform vec2 viewportSize;
uniform float deviceRatio;
uniform vec2 bodyCenter;
uniform vec2 bodyGlobal;
uniform vec2 halfSize;
uniform float cornerRadius;
uniform float thickness;
uniform float bandWidth;
uniform float amplitude;
uniform float dispersion;
uniform float lensScale;
uniform float ringFade;
uniform float useForeground;
uniform float lightBg;       // 背景亮度 0..1：0=暗底（白刃口为主），1=亮底（靠厚度暗侧定形）
uniform vec4 hiRect;

vec4 sampleBg(vec2 coord) {
    return texture(bgTex, clamp(coord, 0.0, 1.0));
}
vec4 sampleBlur(vec2 coord) {
    return texture(blurredTex, clamp(coord, 0.0, 1.0));
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
    // 外圈折射带：bandWidth 控制折射带往内铺多宽（最外沿钉在 sd=0 的边框上）。
    // circleMap 在边缘=1、中心=0，是外圈清晰扭曲与中心模糊的分层权重。
    float band = clamp(1.0 - max(-sd, 0.0) / bandWidth, 0.0, 1.0);
    float circleMap = 1.0 - sqrt(max(1.0 - band * band, 0.0));
    // 位移在最外 8px 内平滑收敛到 0：折射带的最外沿不再被扭曲，纹素不会被
    // "顶"到轮廓线外（底部尤其明显，看起来像折射带溢出了岛体）。用 smoothstep 让
    // 起点导数为 0，边缘与轮廓外的真实背景自然衔接、不出现可见的过渡缝。
    // coverage 仍用 circleMap，所以边缘照旧是清晰背景、只是不再有位移，不会露模糊边。
    float dispEase = smoothstep(0.0, 8.0, -sd);
    // 圆角矩形 SDF 的解析梯度：折射位移方向，边缘指向外侧、中心为 0。
    vec2 gradient = vec2(
        q.x > 0.0 ? outer.x / max(outside, 0.000001) * sign(p.x) : (q.x > q.y ? sign(p.x) : 0.0),
        q.y > 0.0 ? outer.y / max(outside, 0.000001) * sign(p.y) : (q.y > q.x ? sign(p.y) : 0.0)
    );
    float displacement = -thickness * amplitude * circleMap * dispEase;
    vec2 globalCenter = bodyGlobal + p;
    // 色散随 circleMap 从中心(0)到边缘(1)；dispersion=0 时三通道重合（无色）。
    float split = dispersion * circleMap;
    vec2 sampleG = bodyGlobal + p * lensScale + gradient * displacement;
    vec2 sampleR = bodyGlobal + p * lensScale + gradient * displacement * (1.0 + split);
    vec2 sampleB = bodyGlobal + p * lensScale + gradient * displacement * (1.0 - split);
    vec2 uvG0 = (globalCenter - hiRect.xy) / hiRect.zw;
    vec2 uvG = (sampleG - hiRect.xy) / hiRect.zw;
    vec2 uvR = (sampleR - hiRect.xy) / hiRect.zw;
    vec2 uvB = (sampleB - hiRect.xy) / hiRect.zw;
    // 中心 base = 透亮 5x5 高斯模糊；边缘 refracted = 清晰背景 + 折射位移扭曲。
    vec4 base = sampleBlur(uvG0);
    vec4 refracted = sampleBg(uvG);
    refracted.r = sampleBg(uvR).r;
    refracted.b = sampleBg(uvB).b;
    // coverage=circleMap：中心走 5x5 模糊（透亮），外圈走清晰折射扭曲，平滑过渡。
    float coverage = clamp(circleMap * ringFade, 0.0, 1.0);
    vec4 color = mix(base, refracted, coverage);
    // demo 内部：纯饱和度提升（saturate 1.5），不往 alpha 混色导致中心发灰。
    float luma = dot(color.rgb, vec3(0.2126, 0.7152, 0.0722));
    color.rgb = mix(vec3(luma), color.rgb, 1.5);
    // 光源钉在左下：对角梯度给整体方向，再叠一块聚焦在左下角的径向受光，让左下角本身
    // 成为亮斑——只靠对角梯度时整条左直边一样亮，左下角并不突出，读不出"打了个高光"。
    // 纯白底上白光与背景 1:1，高光只能靠"其余边缘被压暗"衬托，所以压暗方向必须与光源一致。
    // 0.354 = 0.5/sqrt(2)：在单位对角方向上正好把对角梯度的范围铺满 0..1。
    float litW = clamp(0.5 + 0.354 * (gradient.y - gradient.x), 0.0, 1.0);
    vec2 dLL = p - vec2(-halfSize.x, halfSize.y);          // y 向下为正 → 左下角是 (-hw, +hh)
    float cornerLit = 1.0 - smoothstep(
        0.0, max(40.0, min(halfSize.x, halfSize.y) * 1.5), length(dLL));
    litW = clamp(0.42 * litW + 0.75 * cornerLit, 0.0, 1.0);
    float bandW = pow(band, 1.2);
    // 左下高光：只提亮、不压暗。之前为了在纯白背景上"看见"岛体加过一整圈背光压暗，
    // 真机上就是一整条黑边，已全部移除。现在边缘只有迎光侧的白刃口——左下最强，
    // 背光侧保持背景本色，没有任何描边感。亮底时把刃口提亮幅度加大一点，让左下
    // 那圈高光在浅色背景上也能顶到纯白。
    float brightAmt = mix(0.12, 0.22, lightBg);
    color.rgb += vec3(brightAmt * pow(litW, 1.6) * bandW * color.a);
    // glBlendFunc(ONE, ONE_MINUS_SRC_ALPHA) 要求预乘 alpha 合法：0<=rgb<=a。
    color.rgb = max(color.rgb, vec3(0.0));
    color.rgb = min(color.rgb, vec3(color.a));
    outColor = vec4(color.rgb * shapeAlpha, color.a * shapeAlpha);
    if (useForeground > 0.5) {
        vec4 foreground = texture(fgTex, vec2(uv.x, 1.0 - uv.y));
        outColor = vec4(foreground.rgb + outColor.rgb * (1.0 - foreground.a),
                        foreground.a + outColor.a * (1.0 - foreground.a));
    }
}
"""


class SeparableBlur:
    """2-pass 可分离 5x5 高斯模糊。输入 hi 纹理，输出透亮模糊纹理供 lens 中心采样。"""

    def __init__(self):
        self.program = None
        self.vao = None
        self.textures = []
        self.fbos = []
        self._size = None
        self._uniforms = {}

    def initialize(self):
        from OpenGL import GL
        from OpenGL.GL import shaders
        self.program = shaders.compileProgram(
            shaders.compileShader(_VERTEX, shaders.GL_VERTEX_SHADER),
            shaders.compileShader(_BLUR_FRAGMENT, shaders.GL_FRAGMENT_SHADER),
        )
        self.vao = GL.glGenVertexArrays(1)
        self.textures = [GL.glGenTextures(1), GL.glGenTextures(1)]
        self.fbos = [GL.glGenFramebuffers(1), GL.glGenFramebuffers(1)]
        for tex in self.textures:
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
            for name, value in ((GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR),
                                (GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR),
                                (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE),
                                (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)):
                GL.glTexParameteri(GL.GL_TEXTURE_2D, name, value)

    def _uniform(self, name):
        from OpenGL import GL
        if name not in self._uniforms:
            self._uniforms[name] = GL.glGetUniformLocation(self.program, name)
        return self._uniforms[name]

    def _ensure_size(self, width, height):
        from OpenGL import GL
        if self._size == (width, height):
            return
        self._size = (width, height)
        for tex, fbo in zip(self.textures, self.fbos):
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, width, height, 0,
                            GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, None)
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
            GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0,
                                      GL.GL_TEXTURE_2D, tex, 0)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, 0)

    def blur(self, src_texture, width, height, sigma):
        """H: src -> tex[0], V: tex[0] -> tex[1]；返回 tex[1]。"""
        from OpenGL import GL
        width, height = max(2, int(width)), max(2, int(height))
        self._ensure_size(width, height)
        previous_fbo = GL.glGetIntegerv(GL.GL_FRAMEBUFFER_BINDING)
        previous_viewport = GL.glGetIntegerv(GL.GL_VIEWPORT)
        GL.glDisable(GL.GL_BLEND)
        GL.glUseProgram(self.program)
        GL.glBindVertexArray(self.vao)
        GL.glViewport(0, 0, width, height)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glUniform1i(self._uniform("uTexture"), 0)
        GL.glUniform2f(self._uniform("uTexSize"), float(width), float(height))
        GL.glUniform1f(self._uniform("uRadius"), float(sigma))
        # H pass
        GL.glBindTexture(GL.GL_TEXTURE_2D, src_texture)
        GL.glUniform2f(self._uniform("uDir"), 1.0, 0.0)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbos[0])
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        # V pass
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.textures[0])
        GL.glUniform2f(self._uniform("uDir"), 0.0, 1.0)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbos[1])
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, previous_fbo)
        GL.glViewport(*previous_viewport)
        GL.glEnable(GL.GL_BLEND)
        return self.textures[1]


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
        self._textures = {"bg": GL.glGenTextures(1), "fg": GL.glGenTextures(1)}
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
        hi, hi_rect = backdrop.hi, backdrop.hi_rect
        if hi is not None and not hi_rect.isEmpty():
            self._upload("bg", hi)
            if cached and self._foreground_dirty:
                self._upload("fg", self._foreground)
                self._foreground_dirty = False
            radius = center_blur_radius(hi, hi_rect)
            blurred = self.blur.blur(self._textures["bg"], hi.width(), hi.height(), radius)
            self._draw_lens(hi_rect, blurred, cached)
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

    def _draw_lens(self, hi_rect, blurred_texture, cached):
        from OpenGL import GL
        from .island import panel_radius
        island = self.island
        # 与 gpu_window.py 一致：SDF 用本体矩形，不让液桥的左右外扩把折射带撑出边框。
        shape = island.body
        if shape.isEmpty():
            return
        dpr = self.devicePixelRatioF()
        width, height = self.width() * dpr, self.height() * dpr
        global_shape = shape.translated(QtCore.QPointF(island._win_origin))
        center = shape.center() - self.geometry().topLeft()
        global_center = global_shape.center()
        hw, hh = shape.width() / 2.0, shape.height() / 2.0
        corner = panel_radius(shape.width(), shape.height())
        thickness = min(12.0, max(2.0, min(hw, hh) * 0.30))
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
        GL.glUniform1f(self._uniform("bandWidth"), min(45.0, max(9.0, thickness * 3.6)))
        GL.glUniform1f(self._uniform("amplitude"), 1.2)
        GL.glUniform1f(self._uniform("dispersion"), 0.0)
        GL.glUniform1f(self._uniform("lensScale"), 1.0)
        GL.glUniform1f(self._uniform("ringFade"), 1.25)
        # 背景亮度：亮底时边缘从"加白刃口"切换成"厚度暗侧"定形，纯白背景才看得出岛体边界。
        GL.glUniform1f(self._uniform("lightBg"), float(getattr(self.island, "_light_bg", 0.0)))
        GL.glUniform4f(self._uniform("hiRect"), hi_rect.x(), hi_rect.y(), hi_rect.width(), hi_rect.height())
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
