# -*- coding: utf-8 -*-
"""PyInstaller 打包入口：无控制台运行，日志写 exe 同目录的 data\\mybalcony.log。"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
os.chdir(BASE)
sys.path.insert(0, str(BASE))

data_dir = BASE / "data"
data_dir.mkdir(exist_ok=True)


class _Tee:
    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, text):
        for s in self.streams:
            try:
                s.write(text)
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


_log = open(data_dir / "mybalcony.log", "a", encoding="utf-8", buffering=1)
sys.stdout = _Tee(sys.stdout, _log)
sys.stderr = _Tee(sys.stderr, _log)

try:
    from mybalcony.app import main

    sys.exit(main())
except SystemExit:
    raise
except Exception:
    traceback.print_exc()
    _log.flush()
    if getattr(sys, "frozen", False):
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            "Mybalcony 启动失败。\n\n详细信息见程序目录下的 data\\mybalcony.log。",
            "Mybalcony",
            0x10,
        )
    sys.exit(1)
