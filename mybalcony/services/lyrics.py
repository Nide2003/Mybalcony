# -*- coding: utf-8 -*-
"""歌词：从网易云音乐公开接口获取 LRC 歌词（含翻译），按播放进度给出当前行。

- 网易云（读本地日志得到歌曲 id）：直接按 id 取歌词
- 其它播放器（QQ 音乐、Spotify、浏览器等）：按「歌名 + 歌手」搜索，取时长最接近的一首

信号 ready(key)：某首歌的歌词取到了（或确认没有），界面收到后重新查询 line()。
"""
from __future__ import annotations

import bisect
import json
import os
import re
import subprocess
import threading
import urllib.parse

import httpx
from PySide6 import QtCore

from mybalcony.core.bg import run_bg, ui
from mybalcony.core.config import cfg
from mybalcony.services import catalog

API = "https://music.163.com/api"
HEADERS = {"Referer": "https://music.163.com/", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
_CREATE_NO_WINDOW = 0x08000000      # 调 curl 时不要弹黑框
_TS = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
# 开头的制作信息（作词 / 作曲 / 编曲 …）不当作歌词显示
_CREDIT = re.compile(r"^\s*[^\s:：]{1,12}\s*[:：]")
# 歌词站常把「歌手 - 歌名」当第一行写进 LRC，别让它顶在正中间当歌词
_TITLE_LINE = re.compile(r"^\s*\S.{0,20}\s[-–—]\s.{1,30}\s*$")
# 歌名里的版本说明：爱错(Live)、Hello (Remastered 2011)、shape of you [feat. …]
_BRACKETS = re.compile(r"\s*[\(（\[【][^\)）\]】]*[\)）\]】]\s*")
# 歌手字段里的分隔：「王力宏 — 心中的日月」(Apple Music 把专辑拼进来了)、「A / B」、「A、B」
_ARTIST_SPLIT = re.compile(r"\s+[—–]\s+|\s*[、，,;；]\s*|\s*[/／]\s*|\s+&\s+")
_FEAT = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s+.*$", re.I)


def title_core(title: str) -> str:
    """去掉括号里的版本说明，用于搜索与比较。"""
    t = _BRACKETS.sub(" ", title or "")
    return re.sub(r"\s+", " ", t).strip()


def primary_artist(artist: str) -> str:
    """Apple Music 的歌手字段是「歌手 — 专辑」，只取第一个名字去搜索。"""
    a = _FEAT.sub("", artist or "")
    a = re.split(r"\s+[—–]\s+", a)[0]
    return (_ARTIST_SPLIT.split(a)[0] or "").strip()


def _curl_json(url: str, params: dict | None) -> dict | None:
    """httpx 连不上时（系统代理 / TLS 异常）改用 Windows 自带的 curl 再试一次。

    先带系统代理试，不行再直连——公司网络和受限环境两种情形都能覆盖。
    """
    exe = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "curl.exe")
    if not os.path.isfile(exe):
        return None
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    cmd = [exe, "-sS", "--max-time", "12"]
    for k, v in HEADERS.items():
        cmd += ["-H", f"{k}: {v}"]
    for extra in ([], ["--noproxy", "*"]):
        try:
            p = subprocess.run(cmd + extra + [full], capture_output=True, timeout=20,
                               creationflags=_CREATE_NO_WINDOW)
        except Exception:  # noqa: BLE001
            continue
        if p.returncode == 0 and p.stdout:
            try:
                return json.loads(p.stdout)
            except Exception:  # noqa: BLE001
                continue
    return None




def parse_lrc(text: str) -> list[tuple[float, str]]:
    out = []
    for raw in (text or "").splitlines():
        stamps = list(_TS.finditer(raw))
        if not stamps:
            continue
        body = raw[stamps[-1].end():].strip()
        for m in stamps:
            frac = m.group(3) or "0"
            t = int(m.group(1)) * 60 + int(m.group(2)) + int(frac) / (10 ** len(frac))
            out.append((t, body))
    out.sort(key=lambda x: x[0])
    # 去掉开头连续的制作信息行 / 「歌手 - 歌名」标题行
    i = 0
    while i < len(out) and (
        not out[i][1]
        or (out[i][0] < 40 and _CREDIT.match(out[i][1]))
        or (i < 8 and out[i][0] < 40 and _TITLE_LINE.match(out[i][1]))
    ):
        i += 1
    return out[i:]


class Lyrics:
    def __init__(self, lines: list[tuple[float, str]], trans: list[tuple[float, str]]):
        self.times = [t for t, _ in lines]
        self.lines = [s for _, s in lines]
        tmap = {round(t, 1): s for t, s in trans if s}
        self.trans = [tmap.get(round(t, 1), "") for t in self.times]

    def __bool__(self):
        return bool(self.lines)

    def at(self, pos: float) -> tuple[int, str, str]:
        """-> (行号, 歌词, 翻译)；还没到第一行时行号为 -1。"""
        # 提前量统一放在调用方（compact.LYR_LEAD），这里只做"这一秒已经进到哪一行"
        i = bisect.bisect_right(self.times, pos + 1e-4) - 1
        if i < 0:
            return -1, "", ""
        return i, self.lines[i], self.trans[i]

    def progress(self, i: int, pos: float, tail: float = 4.0) -> float:
        """这一句唱到哪儿了（0..1）：用来让扫光跟着音轨走。"""
        if i < 0 or i >= len(self.times):
            return 0.0
        start = self.times[i]
        end = self.times[i + 1] if i + 1 < len(self.times) else start + tail
        span = max(0.35, end - start)
        return min(1.0, max(0.0, (pos - start) / span))


class LyricsService(QtCore.QObject):
    ready = QtCore.Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        ui(lambda: None)
        self._client = httpx.Client(timeout=httpx.Timeout(8.0, connect=4.0), headers=HEADERS)
        self._cache: dict[str, Lyrics | None] = {}
        self._pending: set[str] = set()
        self._lock = threading.Lock()

    @staticmethod
    def key(m: dict) -> str:
        if m.get("song_id"):
            return "id:" + str(m["song_id"])
        return "q:" + (m.get("title") or "") + "|" + (m.get("artist") or "")

    def get(self, m: dict) -> Lyrics | None:
        """返回已缓存的歌词；没有时在后台获取，取到后发 ready(key)。"""
        if not cfg.get("media.lyrics", True) or not m.get("title"):
            return None
        k = self.key(m)
        with self._lock:
            if k in self._cache:
                return self._cache[k]
            if k in self._pending:
                return None
            self._pending.add(k)
        run_bg(self._fetch, dict(m), on_done=lambda res, k=k: self._done(k, res),
               on_error=lambda e, k=k: self._done(k, None))
        return None

    def _done(self, k: str, res):
        with self._lock:
            self._pending.discard(k)
            self._cache[k] = res
            if len(self._cache) > 200:
                self._cache.pop(next(iter(self._cache)))
        self.ready.emit(k)

    # ---------------- 网络 ----------------
    def _json(self, url: str, params: dict):
        """先走 httpx（正常情况），失败再交给系统 curl 兜底。"""
        try:
            r = self._client.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            return _curl_json(url, params)

    def _fetch(self, m: dict) -> Lyrics | None:
        sid = str(m.get("song_id") or "") or self._search(m)
        if not sid:
            return None
        j = self._json(API + "/song/lyric", {"id": sid, "lv": 1, "tv": -1})
        if not j or j.get("nolyric") or j.get("uncollected"):
            return None
        lines = parse_lrc((j.get("lrc") or {}).get("lyric", ""))
        trans = parse_lrc((j.get("tlyric") or {}).get("lyric", ""))
        lyr = Lyrics(lines, trans)
        return lyr if lyr else None

    def _search(self, m: dict) -> str:
        dur = float(m.get("duration") or 0)
        if not (30 <= dur <= 15 * 60):
            return ""            # 不知道时长 / 时长不像一首歌（视频、番剧等）：不按歌名猜歌词
        title = (m.get("title") or "").strip()
        core = title_core(title)
        if not core:
            return ""
        artist = primary_artist(m.get("artist"))
        queries = []
        if artist:
            queries.append(f"{core} {artist}")
        queries.append(core)
        raw = (m.get("artist") or "").strip()
        if raw and raw != artist:
            queries.append(f"{core} {raw}")
        for q in dict.fromkeys(x for x in queries if x.strip()):
            try:
                songs = self._query(q)
            except Exception:  # noqa: BLE001
                continue
            sid = match_song(songs, title, core, artist, dur)
            if sid:
                return sid
        return self._search_catalog(title, core, artist, dur, raw)

    def _search_catalog(self, title: str, core: str, artist: str, dur: float, raw: str) -> str:
        """最后一轮：先用 Apple Music 曲库（iTunes）校正成官方曲目，再搜一次。

        有的歌在歌词库里挂着外文名 / 官方写法，按播放器报的中文名搜不到；
        Apple 曲库给的歌手和曲名通常就是上架时的标准写法，换它再搜能兜住这类。
        顺带用它的精确时长做判定，比播放器报的更靠谱。
        """
        try:
            cat = catalog.lookup(title, raw or artist, dur)
        except Exception:  # noqa: BLE001
            return ""
        if not cat:
            return ""
        nice_title = (cat.get("trackName") or "").strip()
        nice_art = primary_artist(cat.get("artistName") or "")
        nd = float(cat.get("trackTimeMillis") or 0) / 1000.0
        want = title_core(nice_title) or core
        for q in dict.fromkeys(x for x in (f"{want} {nice_art}".strip(), want,
                                           f"{core} {nice_art}".strip()) if x):
            try:
                songs = self._query(q)
            except Exception:  # noqa: BLE001
                continue
            sid = match_song(songs, want, want, nice_art, nd or dur)
            if sid:
                return sid
        return ""

    def _query(self, q: str) -> list[dict]:
        j = self._json(API + "/search/get/web", {"s": q, "type": 1, "limit": 15}) or {}
        return ((j.get("result") or {}).get("songs")) or []


def _names(song: dict) -> list[str]:
    out = []
    for key in ("artists", "ar"):
        for a in song.get(key) or []:
            n = (a.get("name") or "").strip()
            if n:
                out.append(n)
    return out


def match_song(songs: list[dict], title: str, core: str, artist: str, dur: float) -> str:
    """在搜索结果里挑最可能是同一首的一首。

    排序先看歌手是否对得上，再看歌名，最后看时长差——Apple Music 里没有版权的歌，
    列表里往往挤着一堆同名翻唱，只看歌名 + 时长会挑到翻唱（对不上时长就干脆不显示了）。
    """
    if not songs:
        return ""
    want = core.lower()
    raw_want = title.lower().strip()
    art = artist.lower().strip()

    def score(s: dict):
        name = (s.get("name") or "").strip()
        nm = name.lower()
        n_core = title_core(name).lower()
        if nm == raw_want:
            name_rank = 0
        elif n_core == want:
            name_rank = 1
        elif want and (want in n_core or n_core in want):
            name_rank = 2
        else:
            name_rank = 3
        names = [x.lower() for x in _names(s)]
        artist_rank = 0 if (art and any(art in x or x in art for x in names)) else 1
        dd = abs((s.get("duration") or 0) / 1000.0 - dur)
        # 时长优先于"歌名是否一字不差"：同名不等于同版本（剪辑版 / 翻唱常差几十秒），
        # 而 Live 版名字多了尾巴、时长却几乎一致。名对不上的结果整体排后面。
        return (artist_rank, 0 if name_rank <= 2 else 1, dd, name_rank)

    best = min(songs, key=score)
    a_rank, _sane, dd, n_rank = score(best)
    if n_rank >= 3:
        return ""
    if dd <= 6:                                  # 时长几乎一致：认
        return str(best.get("id") or "")
    if a_rank == 0 and n_rank <= 1 and dd <= 30:  # 歌手和歌名都对：可能是现场版 / 剪辑版
        return str(best.get("id") or "")
    if n_rank == 0 and dd <= 12:
        return str(best.get("id") or "")
    return ""

