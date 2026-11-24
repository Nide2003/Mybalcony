# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（onedir）。

用法：在仓库根目录执行
    pyinstaller packaging/mybalcony.spec --noconfirm --clean
产物：dist/Mybalcony/Mybalcony.exe
"""
import os

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

PROJECT = os.path.abspath(os.path.join(SPECPATH, ".."))

# pywinrt 是 namespace 包，自动分析容易漏；显式列出项目实际用到的子模块
winrt_modules = [
    "winrt.windows.foundation",
    "winrt.windows.foundation.collections",
    "winrt.windows.storage.streams",
    "winrt.windows.media.control",
    "winrt.windows.devices.radios",
    "winrt.windows.devices.bluetooth",
    "winrt.windows.devices.bluetooth.genericattributeprofile",
    "winrt.windows.devices.enumeration",
    "winrt.windows.networking.connectivity",
    "winrt.windows.networking.networkoperators",
]

hiddenimports = winrt_modules + [
    "dxcam",
    "sherpa_onnx",
    "soundcard",
    "soxr",
    "fugashi",
    "unidic_lite",
    "genanki",
    "pycaw",
    "comtypes",
    "comtypes.gen",
    # PyOpenGL 动态加载后端，静态分析看不到
    "OpenGL.platform.win32",
    "OpenGL.arrays.numpymodule",
    "OpenGL.arrays.ctypesarrays",
    "OpenGL.arrays.lists",
    "OpenGL.arrays.strings",
    "OpenGL.arrays.numbers",
    "OpenGL.arrays.formathandler",
    "OpenGL.GL.shaders",
]

try:
    hiddenimports += collect_submodules("winrt", on_error="ignore")
except Exception:
    pass

_icon = os.path.join(SPECPATH, "mybalcony.ico")

datas = []
# 日语分词词典（约 50 MB），不打包就无法查词 / 字幕分词
datas += collect_data_files("unidic_lite")
datas += collect_data_files("sherpa_onnx")
if os.path.exists(_icon):
    # 程序运行时从这里取窗口 / 托盘图标
    datas.append((_icon, "."))

binaries = []
binaries += collect_dynamic_libs("sherpa_onnx")
binaries += collect_dynamic_libs("dxcam")
binaries += collect_dynamic_libs("soundcard")

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[PROJECT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "IPython",
        "pytest",
        "pandas",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQuick",
        "PySide6.QtQml",
        "PySide6.Qt3DCore",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtDesigner",
        "PySide6.QtTest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Mybalcony",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=_icon if os.path.exists(_icon) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Mybalcony",
)
