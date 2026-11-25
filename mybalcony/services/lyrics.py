# -*- coding: utf-8 -*-
"""歌词：优先取洛雪（LX Music）当前播放的歌词，兜底网易云公开接口与 LRCLIB。

- 洛雪开放 API（本机 23330）：它聚合酷我 / 酷狗 / QQ / 网易 / 咪咕等源，
  命中率与逐字歌词质量最好；只在「洛雪正在播放且与系统媒体会话是同一首」时采用
- 网易云（读本地日志得到歌曲 id）：直接按 id 取歌词
- 其它播放器（QQ 音乐、Spotify、浏览器等）：按「歌名 + 歌手」搜索，取时长最接近的一首

逐字歌词（行内 <mm:ss.xx> 标签）会保留成字级时间轴，扫光按「唱到第几个字」
推进，而不是按整行均分，跟唱更贴。

信号 ready(key)：某首歌的歌词取到了（或确认没有），界面收到后重新查询 line()。
"""
from __future__ import annotations

import bisect
import json
import os
import re
import subprocess
import threading
import time
import urllib.parse

import httpx
from PySide6 import QtCore

from mybalcony.core.bg import run_bg, ui
from mybalcony.core.config import cfg
from mybalcony.services import catalog, lxsource, netease_eapi

API = "https://music.163.com/api"
LRCLIB = "https://lrclib.net/api"
HEADERS = {"Referer": "https://music.163.com/", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
# 网络失败后多久允许重试（确认"没有歌词"的结果仍整次运行缓存，不受这个影响）
FAIL_COOLDOWN = 60.0
EMPTY_TTL = 240.0          # "没歌词"结论的有效期：网络抖动来的空结果不能永久缓存
_CREATE_NO_WINDOW = 0x08000000      # 调 curl 时不要弹黑框
_TS = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
# 行内逐字标签：字<00:03.21>字<00:04.05>（洛雪 lxlyric / Any Listen 与部分 QQ 歌词都用这个）
_WORD_TAG = re.compile(r"<(\d{1,3}):(\d{1,2})(?:[.,:](\d{1,3}))?>")
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




def _split_words(body: str) -> tuple[str, list[tuple[float, str]]]:
    """把「文字<mm:ss.xx>文字…」拆成纯文本与字级时间轴（没有标签时时间轴为空）。"""
    marks = list(_WORD_TAG.finditer(body))
    if not marks:
        return body.strip(), []
    pieces: list[tuple[float | None, str]] = []
    pos = 0
    for m in marks:
        seg = body[pos:m.start()]
        frac = m.group(3) or "0"
        t = int(m.group(1)) * 60 + int(m.group(2)) + int(frac) / (10 ** len(frac))
        pieces.append((None, seg))
        pieces.append((t, ""))
        pos = m.end()
    pieces.append((None, body[pos:]))

    text_parts: list[str] = []
    words: list[tuple[float, str]] = []
    pending: float | None = None
    for t, seg in pieces:
        if t is not None:
            pending = t
            continue
        if not seg:
            continue
        if pending is None:
            text_parts.append(seg)          # 第一个字之前的前缀（正常为空）
        else:
            words.append((pending, seg))
    text = ("".join(text_parts) + "".join(w for _, w in words)).strip()
    if len(words) < 2:
        return text, []                     # 只有一两个标签：不值得按字推
    if any(words[i + 1][0] < words[i][0] for i in range(len(words) - 1)):
        return text, []                     # 时间倒序的脏数据
    return text, words


def parse_lrc_words(text: str) -> tuple[list[tuple[float, str]], list[list[tuple[float, str]]]]:
    """解析 LRC：返回 (行列表, 每行的字级时间轴)。"""
    lines: list[tuple[float, str]] = []
    words: list[list[tuple[float, str]]] = []
    for raw in (text or "").splitlines():
        stamps = list(_TS.finditer(raw))
        if not stamps:
            continue
        body, seg = _split_words(raw[stamps[-1].end():])
        for m in stamps:
            frac = m.group(3) or "0"
            t = int(m.group(1)) * 60 + int(m.group(2)) + int(frac) / (10 ** len(frac))
            lines.append((t, body))
            words.append(seg)
    pairs = sorted(zip(lines, words), key=lambda x: x[0][0])
    lines = [p[0] for p in pairs]
    words = [p[1] for p in pairs]
    # 去掉开头连续的制作信息行 / 「歌手 - 歌名」标题行
    i = 0
    while i < len(lines) and (
        not lines[i][1]
        or (lines[i][0] < 40 and _CREDIT.match(lines[i][1]))
        or (i < 8 and lines[i][0] < 40 and _TITLE_LINE.match(lines[i][1]))
    ):
        i += 1
    return lines[i:], words[i:]


def parse_lrc(text: str) -> list[tuple[float, str]]:
    return parse_lrc_words(text)[0]


class Lyrics:
    def __init__(self, lines: list[tuple[float, str]], trans: list[tuple[float, str]],
                 words: list[list[tuple[float, str]]] | None = None):
        self.times = [t for t, _ in lines]
        self.lines = [s for _, s in lines]
        self.words = list(words or [])
        if len(self.words) < len(self.lines):
            self.words += [[] for _ in range(len(self.lines) - len(self.words))]
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
        seg = self.words[i] if i < len(self.words) else []
        if len(seg) >= 2:
            # 有字级时间轴：扫光按「唱到第几个字」推进，比整行均分贴合得多
            ts = [t for t, _ in seg]
            k = bisect.bisect_right(ts, pos + 1e-4) - 1
            if k < 0:
                return 0.0
            t0 = ts[k]
            t1 = ts[k + 1] if k + 1 < len(ts) else max(end, t0 + 0.6)
            f = (pos - t0) / max(0.08, t1 - t0)
            return min(1.0, (k + min(1.0, max(0.0, f))) / len(ts))
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
        self._fail_at: dict[str, float] = {}
        self._empty_at: dict[str, float] = {}
        self._req: dict[str, dict] = {}      # 最近一次请求参数，用于冷却后自动重试
        self._lock = threading.Lock()
        self._retry = QtCore.QTimer(self)
        self._retry.setInterval(6000)
        self._retry.timeout.connect(self._retry_tick)
        self._retry.start()

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
                res = self._cache[k]
                if res is not None:
                    return res
                # "没歌词"只信 EMPTY_TTL：网络抖动导致的空结果过一会儿要重新取，
                # 否则一首歌整场都会空着（用户只看到标题没有歌词）。
                if time.monotonic() - self._empty_at.get(k, 0.0) < EMPTY_TTL:
                    return None
                self._cache.pop(k, None)
            if k in self._pending:
                return None
            if k in self._fail_at and time.monotonic() - self._fail_at[k] < FAIL_COOLDOWN:
                return None            # 刚网络失败过：冷却期内不重复打请求
            self._pending.add(k)
            self._req[k] = dict(m)
            self._fail_at.pop(k, None)
        run_bg(self._fetch, dict(m), on_done=lambda res, k=k: self._done(k, res),
               on_error=lambda e, k=k: self._fail(k, e))
        return None

    def _retry_tick(self):
        """冷却/等待结束后自动补取：媒体不变化时没人再调 get，光靠冷却会一直空着。"""
        now = time.monotonic()
        for k, m in list(self._req.items()):
            with self._lock:
                if k in self._pending:
                    continue
                cached = self._cache.get(k, "__miss__")
                if cached != "__miss__" and cached is not None:
                    self._req.pop(k, None)
                    continue
                at = self._fail_at.get(k)
                if at is not None and now - at < FAIL_COOLDOWN:
                    continue
            self.get(m)

    def _done(self, k: str, res):
        with self._lock:
            self._pending.discard(k)
            self._cache[k] = res
            if res is None:
                self._empty_at[k] = time.monotonic()
            else:
                self._empty_at.pop(k, None)
                self._req.pop(k, None)
            if len(self._cache) > 200:
                self._cache.pop(next(iter(self._cache)))
        self.ready.emit(k)

    def _fail(self, k: str, err: Exception | None = None):
        """网络/解析异常：不写进永久缓存，只记冷却时间，过一会儿还能自动重试。"""
        if err is not None:
            # 打到日志里：歌词取不到时能直接看出是哪一层（洛雪 / 搜索 / 网络）挂了
            print(f"[lyrics] {k} 取词失败: {type(err).__name__}: {err}", flush=True)
        with self._lock:
            self._pending.discard(k)
            self._fail_at[k] = time.monotonic()

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
        return self._fetch_lx(m) or self._fetch_netease(m) or self._fetch_lrclib(m)

    def _fetch_lx(self, m: dict) -> Lyrics | None:
        """洛雪（LX Music）开放 API：只在「它正在放的就是这首」时采用。

        洛雪聚合了酷我 / 酷狗 / QQ / 网易 / 咪咕的歌词，命中率与逐字质量比单一
        公开接口好；但它的接口只暴露"当前播放那一首"，所以必须核对歌名 / 歌手 /
        时长，否则会把另一首歌的歌词套上来。
        """
        if not lxsource.source().enabled():
            return None
        st = lxsource.source().playing()
        if not st or not lx_same_song(st, m):
            return None
        d = lxsource.source().lyric_all()
        raw_lx = (d.get("lxlyric") or "").strip()
        raw = (d.get("lyric") or "").strip()
        lines, words = parse_lrc_words(raw_lx) if raw_lx else ([], [])
        if not lines and raw:
            lines, words = parse_lrc_words(raw)
        if not lines:
            return None
        trans = parse_lrc(d.get("tlyric") or "")
        lyr = Lyrics(lines, trans, words)
        return lyr if lyr else None

    def _fetch_netease(self, m: dict) -> Lyrics | None:
        sid = str(m.get("song_id") or "") or self._search(m)
        if not sid:
            return None
        # 先走 eapi（洛雪同款链路）：能拿到逐字 yrc，扫光按字推进；老歌没逐字时
        # 返回的 lrc 也直接用，比公开接口多一层过滤（版权/翻译字段更全）。
        d = netease_eapi.fetch(sid) if cfg.get("media.lyric_eapi", True) else None
        if d:
            yrc = d.get("yrc") or ""
            text = netease_eapi.yrc_to_lrc(yrc) if yrc else (d.get("lrc") or "")
            lines, words = parse_lrc_words(text)
            if lines:
                trans = parse_lrc(d.get("tlyric")
                                  or netease_eapi.yrc_to_plain(d.get("ytlrc") or ""))
                lyr = Lyrics(lines, trans, words)
                if lyr:
                    return lyr
        j = self._json(API + "/song/lyric", {"id": sid, "lv": 1, "tv": -1})
        if not j or j.get("nolyric") or j.get("uncollected"):
            return None
        lines = parse_lrc((j.get("lrc") or {}).get("lyric", ""))
        trans = parse_lrc((j.get("tlyric") or {}).get("lyric", ""))
        lyr = Lyrics(lines, trans)
        return lyr if lyr else None

    def _lrclib_json(self, path: str, params: dict):
        """LRCLIB 要求 UA 标明应用；404 当作"没这首"而不是网络错误。"""
        url = LRCLIB + path
        try:
            r = self._client.get(url, params=params,
                                 headers={"User-Agent": "Wisland (desktop lyrics widget)"})
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001
            res = _curl_json(url, params)
            if res is None:
                raise           # httpx 与 curl 都失败：是网络故障，交给上层走冷却重试
            return res

    def _fetch_lrclib(self, m: dict) -> Lyrics | None:
        """网易云没兜住时查 LRCLIB：免费公开、带同步时间轴，欧美/小众曲库更全。"""
        core = title_core(m.get("title") or "")
        if not core:
            return None
        artist = primary_artist(m.get("artist"))
        dur = float(m.get("duration") or 0)
        exact = {"track_name": core}
        if artist:
            exact["artist_name"] = artist
        if m.get("album"):
            exact["album_name"] = m["album"]
        if dur > 0:
            exact["duration"] = int(round(dur))
        rec = self._lrclib_json("/get", exact)
        if not (isinstance(rec, dict) and rec.get("syncedLyrics")):
            q = {"track_name": core}
            if artist:
                q["artist_name"] = artist
            rows = self._lrclib_json("/search", q)
            if not isinstance(rows, list):
                return None
            rows = [r for r in rows if r.get("syncedLyrics")]
            if dur > 0:
                rows.sort(key=lambda r: abs(float(r.get("duration") or 0) - dur))
            rec = rows[0] if rows else None
        if not rec:
            return None
        lines = parse_lrc(rec.get("syncedLyrics") or "")
        return Lyrics(lines, []) if lines else None

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
        qs = [q for q in dict.fromkeys(x for x in queries if x.strip())]
        tried = failed = 0
        for q in qs:
            tried += 1
            try:
                songs = self._query(q)
            except Exception:  # noqa: BLE001
                failed += 1
                continue
            sid = match_song(songs, title, core, artist, dur)
            if sid:
                return sid
        if tried and failed == tried:
            raise RuntimeError("网易云搜索接口不可达")   # 全部查询都失败：让上层冷却后重试
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
        j = self._json(API + "/search/get/web", {"s": q, "type": 1, "limit": 15})
        if not isinstance(j, dict):
            # 网络不可达 ≠ 没有这首歌。抛出去让上层走冷却重试，避免把一次抖动
            # 永久记成"无歌词"（那会让整首歌再也取不到歌词）。
            raise RuntimeError("网易云搜索接口不可达")
        return ((j.get("result") or {}).get("songs")) or []


def lx_same_song(st: dict, m: dict) -> bool:
    """洛雪正在播放的这首，与系统媒体会话报的是不是同一首歌（宁严不松）。"""
    lt = title_core(st.get("name") or "")
    mt = title_core(m.get("title") or "")
    if not lt or not mt or lt.casefold() != mt.casefold():
        return False
    la = primary_artist(st.get("singer") or "")
    ma = primary_artist(m.get("artist") or "")
    if la and ma and la.casefold() == ma.casefold():
        return True
    # 歌手写法不一致（中英文名 / 组合缩写）时用时长兜底：差 3 秒内算同一首
    d1 = float(st.get("duration") or 0)
    d2 = float(m.get("duration") or 0)
    return bool(d1 > 0 and d2 > 0 and abs(d1 - d2) <= 3.0)


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

