# -*- coding: utf-8 -*-
"""空白玻璃页：一个字都不画，只用来看岛身玻璃本身。

调玻璃的时候最烦的就是内容层：卡片、文字、渐变都在面板上面，背景一脏根本分不清
是玻璃的问题还是内容的问题。这一页只保留岛身（阴影 / 玻璃 / 折射 / 刃口），
背景是什么样就原样露出来，验收背景只看这一页。
"""
from __future__ import annotations

from PySide6 import QtCore

from ..theme import G
from .base import Page


class BlankPage(Page):
    key = "blank"
    glyph = G.IMAGE
    title = "玻璃"
    height = 360

    def __init__(self, ctx=None):
        super().__init__(ctx)
        # 除基类已有的透明底，这里不建任何子控件 —— 连布局都不装。
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, ev):  # noqa: N802
        """什么都不画：背景完全交给岛身玻璃。"""
        return
