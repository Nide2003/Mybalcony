"""网易云 eapi 歌词接口：直接拿逐字歌词（yrc）与翻译（tlyric）。

洛雪音乐（lx-music-desktop）的 wy 歌词源就是这条链路：

    POST https://interface3.music.163.com/eapi/song/lyric/v1
    form: params=AES-128-ECB( "<url>-36cd479b6b5-<json>-36cd479b6b5-<md5>" )
    key : e82ckenh8dichen8

响应里 `yrc` 有两种行：
- ``{"t":0,"c":[{"tx":"作词: "},{"tx":"唐恬"}]}``   JSON 头（制作信息）
- ``[1,4890](1,270,0)词(270,270,0)版…``           逐字正文（毫秒起始 + 每字 (起,长)）

本模块把它转成项目已有的 LRC 方言（行内 ``<mm:ss.mmm>`` 字级标签），这样
lyrics.parse_lrc_words() 直接能解析出字级时间轴，扫光按字推进。

不装洛雪也能用：这是它用的公开接口，参数与加密方式照抄它的源码。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess

import httpx

EAPI_URL = "https://interface3.music.163.com/eapi/song/lyric/v1"
EAPI_PATH = "/api/song/lyric/v1"
_KEY = b"e82ckenh8dichen8"
HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://music.163.com",
    "Referer": "https://music.163.com/",
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/60.0.3112.90 Safari/537.36"),
}
_CREATE_NO_WINDOW = 0x08000000

_YRC_LINE = re.compile(r"^\[(\d+),(\d+)\]")
_YRC_WORD = re.compile(r"\((\d+),(\d+),\d+\)")


def _params(obj: dict) -> str:
    from .aes import encrypt_ecb
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.md5(f"nobody{EAPI_PATH}use{text}md5forencrypt".encode()).hexdigest()
    data = f"{EAPI_PATH}-36cd479b6b5-{text}-36cd479b6b5-{digest}"
    return encrypt_ecb(_KEY, data.encode()).hex().upper()


def _curl_post(form: str) -> dict | None:
    """httpx 连不上时（本机 TLS 被重置）改用系统 curl 发 POST。"""
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "curl.exe")
    if not os.path.isfile(exe):
        return None
    cmd = [exe, "-sS", "--max-time", "10", "-X", "POST", EAPI_URL]
    for k, v in HEADERS.items():
        cmd += ["-H", f"{k}: {v}"]
    for extra in ([], ["--noproxy", "*"]):
        try:
            p = subprocess.run(cmd + extra + ["--data", form], capture_output=True,
                               timeout=16, creationflags=_CREATE_NO_WINDOW)
        except Exception:  # noqa: BLE001
            continue
        if p.returncode == 0 and p.stdout:
            try:
                return json.loads(p.stdout)
            except Exception:  # noqa: BLE001
                continue
    return None


def fetch(song_id: str) -> dict | None:
    """取歌词原始文本：{"lrc","tlyric","yrc","ytlrc"}；失败返回 None。"""
    if not song_id:
        return None
    form = "params=" + _params({"id": str(song_id), "cp": False, "tv": 0, "lv": 0,
                                "rv": 0, "kv": 0, "yv": 0, "ytv": 0, "yrv": 0})
    j = None
    try:
        r = httpx.post(EAPI_URL, content=form, headers=HEADERS,
                       timeout=httpx.Timeout(5.0, connect=3.0))
        r.raise_for_status()
        j = r.json()
    except Exception:  # noqa: BLE001
        j = _curl_post(form)
    if not isinstance(j, dict) or j.get("code") != 200:
        return None
    return {
        "lrc": ((j.get("lrc") or {}).get("lyric") or ""),
        "tlyric": ((j.get("tlyric") or {}).get("lyric") or ""),
        "yrc": ((j.get("yrc") or {}).get("lyric") or ""),
        "ytlrc": ((j.get("ytlrc") or {}).get("lyric") or ""),
    }


def _stamp(ms: int) -> str:
    ms = max(0, int(ms))
    return f"[{ms // 60000:02d}:{(ms % 60000) // 1000:02d}.{ms % 1000:03d}]"


def yrc_to_lrc(text: str) -> str:
    """把 yrc（JSON 头 + 逐字正文）转成本项目能解析的 LRC。

    输出行形如 ``[00:01.000]<00:01.000>词<00:01.270>版…``，字级时间保留。
    纯 JSON 头（制作信息）转成普通行，交给上层做"制作信息"过滤。
    """
    out: list[str] = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith('{"'):
            try:
                info = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            txt = "".join(str(c.get("tx") or "") for c in (info.get("c") or []))
            if txt.strip():
                out.append(f"{_stamp(int(info.get('t') or 0))}{txt}")
            continue
        m = _YRC_LINE.match(s)
        if not m:
            continue
        start_ms = int(m.group(1))
        body = s[m.end():]
        words: list[tuple[int, str]] = []
        pos = 0
        pending = None
        for wm in _YRC_WORD.finditer(body):
            seg = body[pos:wm.start()]
            if seg and pending is not None:
                words.append((pending, seg))
            pending = int(wm.group(1))
            pos = wm.end()
        tail = body[pos:]
        if tail and pending is not None:
            words.append((pending, tail))
        if not words:
            continue
        line = _stamp(start_ms) + "".join(f"<{_stamp(t)[1:-1]}>{w}" for t, w in words)
        out.append(line)
    return "\n".join(out)


def yrc_to_plain(text: str) -> str:
    """只取文本（翻译 ytlrc 用）：去掉字级标签，保留行时间。"""
    out: list[str] = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith('{"'):
            try:
                info = json.loads(s)
            except Exception:  # noqa: BLE001
                continue
            txt = "".join(str(c.get("tx") or "") for c in (info.get("c") or []))
            if txt.strip():
                out.append(f"{_stamp(int(info.get('t') or 0))}{txt}")
            continue
        m = _YRC_LINE.match(s)
        if not m:
            if s.startswith("["):
                out.append(s)          # 已经是普通 LRC
            continue
        words = _YRC_WORD.sub("", s[m.end():])
        out.append(_stamp(int(m.group(1))) + words)
    return "\n".join(out)


__all__ = ["fetch", "yrc_to_lrc", "yrc_to_plain", "EAPI_URL"]
