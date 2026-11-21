# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class Page(QtWidgets.QWidget):
    key = "page"
    glyph = ""
    title = "页面"
    height = 300

    def __init__(self, ctx=None):
        super().__init__()
        self.ctx = ctx
        self.island = None
        self.active = False
        # 页面是透明的中间层：把底下的岛身玻璃一起参与重绘，避免四角闪白
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def preferred_height(self) -> int:
        return self.height

    def set_height(self, h: int):
        if h != self.height:
            self.height = h
            if self.island is not None:
                self.island.page_size_changed()

    def on_show(self):
        self.active = True

    def on_hide(self):
        self.active = False

    def want_focus(self):
        if self.island is not None:
            self.island.request_focus()
