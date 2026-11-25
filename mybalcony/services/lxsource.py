"""洛雪音乐助手（LX Music）桌面版「开放 API 服务」的最小只读客户端。

LX Music v2.7.0+ 在设置里启用「开放 API 服务」后，会在本地起一个 HTTP 服务
（默认 http://127.0.0.1:23330），本模块只用其中两个只读接口：

    GET /status     播放器状态 + 当前歌曲 name / singer / albumName / duration / progress
    GET /lyric-all  {"lyric": LRC, "tlyric": 翻译, "rlyric": 罗马音, "lxlyric": 逐字}

洛雪自己聚合了酷我 / 酷狗 / QQ / 网易 / 咪咕等歌词源，命中率与逐字歌词质量
都比单一公开接口高，所以把它排在第一优先；它不可用（没装、没开服务、正在放的
不是同一首）时调用方静默回退到网易云 / LRCLIB，不影响原有行为。
"""
from __future__ import annotations

import time

import httpx

from ..core.config import cfg

DEFAULT_URL = "http://127.0.0.1:23330"
_DOWN_COOLDOWN = 25.0       # 服务不可用时静默这么久再探测，避免每次歌词请求都卡几百毫秒


class LxSource:
    def __init__(self):
        self._client = httpx.Client(timeout=httpx.Timeout(0.6, connect=0.4))
        self._down_until = 0.0

    def enabled(self) -> bool:
        return bool((cfg.get("media.lx_api", DEFAULT_URL) or "").strip())

    def base(self) -> str:
        return (cfg.get("media.lx_api", DEFAULT_URL) or "").strip().rstrip("/")

    def _get(self, path: str):
        base = self.base()
        if not base or time.monotonic() < self._down_until:
            return None
        try:
            r = self._client.get(base + path)
        except Exception:  # noqa: BLE001
            self._down_until = time.monotonic() + _DOWN_COOLDOWN
            return None
        if r.status_code != 200:
            self._down_until = time.monotonic() + _DOWN_COOLDOWN
            return None
        return r

    def status(self) -> dict | None:
        r = self._get("/status")
        if r is None:
            return None
        try:
            j = r.json()
        except Exception:  # noqa: BLE001
            return None
        return j if isinstance(j, dict) else None

    def lyric_all(self) -> dict:
        r = self._get("/lyric-all")
        if r is None:
            return {}
        try:
            j = r.json()
        except Exception:  # noqa: BLE001
            return {}
        return j if isinstance(j, dict) else {}

    def playing(self) -> dict | None:
        """正在播放时返回 status，否则 None。"""
        st = self.status()
        if st and st.get("status") == "playing" and st.get("name"):
            return st
        return None


_source: LxSource | None = None


def source() -> LxSource:
    global _source
    if _source is None:
        _source = LxSource()
    return _source
