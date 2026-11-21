# Project Changelog

## 2026-11-21

- Lyrics service (`mybalcony/services/lyrics.py`) now uses a two-source cascade: NetEase Cloud Music first, then LRCLIB (`https://lrclib.net/api`) when NetEase has no lyric. LRCLIB synced LRC is parsed with the existing `parse_lrc`; exact `/get` match is attempted before `/search`, with duration-based ranking.
- Network failures are no longer cached as a permanent "no lyric" result. A failure cooldown (`FAIL_COOLDOWN = 60s`) suppresses repeat requests, after which the track is retried. Confirmed-empty results remain cached for the process lifetime.
- Verified: NetEase regression unchanged (synchronous lyrics still resolve); unreachable LRCLIB raises `ConnectError` and enters the cooldown path; `py_compile` passes.
