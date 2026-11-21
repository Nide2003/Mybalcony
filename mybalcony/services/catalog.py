# -*- coding: utf-8 -*-
"""Apple Music 曲库：用 iTunes Search API 把播放器报上来的曲目校正成官方写法。

Apple Music 经系统媒体控件（SMTC）报上来的歌手字段常是「歌手 — 专辑 - Single」这种
拼接串，歌名也可能带 (Live) / (Remastered) 之类尾巴。直接拿去歌词库搜索会引入噪音
（同名翻唱、剪辑版），所以先用 Apple Music 自己的曲库洗一遍：拿到官方曲名、歌手、
专辑和**精确时长**，再去查歌词。

只做元数据。歌词拿不到 —— Apple Music 的同步歌词在 amp-api.music.apple.com，
需要 MusicKit 开发者 token（未授权的请求一律 401），公开途径取不到。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.parse
import urllib.request

_CREATE_NO_WINDOW = 0x08000000
# 同一首歌在不同区上架情况不同（华语歌常在港台区，日文歌在日区），按顺序试
_REGIONS = ("cn", "hk", "tw", "us", "jp")
_cache: dict[str, dict | None] = {}

_BRACKET = re.compile(r"\s*[\(（\[【].*?[\)）\]】]\s*")
_DASH = re.compile(r"\s+[—–-]\s+")
_SPLIT = re.compile(r"\s*(?:/|&|,|、|feat\.?|ft\.?|with)\s+", re.I)


def core_title(title: str) -> str:
    t = _BRACKET.sub(" ", title or "")
    return re.sub(r"\s+", " ", t).strip()


def first_artist(artist: str) -> str:
    a = _DASH.split(artist or "")[0]
    return (_SPLIT.split(a)[0] or "").strip()


def _get_json(url: str, params: dict) -> dict | None:
    full = url + "?" + urllib.parse.urlencode(params)
    try:
        req = urllib.request.Request(full, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        pass
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "curl.exe")
    if not os.path.isfile(exe):
        return None
    for extra in ([], ["--noproxy", "*"]):
        try:
            p = subprocess.run([exe, "-sS", "--max-time", "10", *extra, full],
                               capture_output=True, timeout=16, creationflags=_CREATE_NO_WINDOW)
        except Exception:  # noqa: BLE001
            continue
        if p.returncode == 0 and p.stdout:
            try:
                return json.loads(p.stdout)
            except Exception:  # noqa: BLE001
                continue
    return None


def lookup(title: str, artist: str, duration: float) -> dict | None:
    """按歌名 + 歌手 + 时长在 Apple Music 曲库里找同一首。

    命中要求时长相差不超过 8 秒（同一首歌的不同版本差得更多，多半不是同一录音）。
    """
    core = core_title(title)
    art = first_artist(artist)
    if not core or not (30 <= float(duration or 0) <= 15 * 60):
        return None
    key = f"{core}|{art}|{round(float(duration))}"
    if key in _cache:
        return _cache[key]

    want = core.lower()
    want_art = art.lower()
    best: dict | None = None
    best_key: tuple | None = None
    for region in _REGIONS:
        d = _get_json("https://itunes.apple.com/search",
                      {"term": f"{core} {art}".strip(), "media": "music", "entity": "song",
                       "limit": 12, "country": region})
        for r in (d or {}).get("results") or []:
            name = core_title(r.get("trackName") or "")
            who = (r.get("artistName") or "").strip()
            ms = int(r.get("trackTimeMillis") or 0)
            if not name or not ms:
                continue
            dd = abs(ms / 1000.0 - float(duration))
            if dd > 8:
                continue
            nm = name.lower()
            name_ok = nm == want or nm in want or want in nm
            art_ok = bool(want_art) and (want_art in who.lower() or who.lower() in want_art)
            rank = (0 if (name_ok and art_ok) else 1 if name_ok else 2, dd)
            if best_key is None or rank < best_key:
                best_key, best = rank, (r, name_ok, art_ok, dd)
        if best_key and best_key[0] == 0 and best_key[1] <= 2:
            break                      # 已经对得很准，不用再翻别的区
    if best is None:
        _cache[key] = None
        return None
    row, name_ok, art_ok, dd = best
    # 同名不等于同一首：歌手对不上时，只有时长几乎分毫不差才认（否则宁可不用曲库，
    # 交给歌词库自己按「歌名 + 歌手」去搜）。
    if not name_ok or (not art_ok and dd > 1.5):
        _cache[key] = None
        return None
    _cache[key] = row
    return row
