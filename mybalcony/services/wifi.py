# -*- coding: utf-8 -*-
"""可用 Wi-Fi 网络：netsh wlan 的扫描与连接。

Windows 11 24H2 起 `netsh wlan show networks` 算「访问位置」，轮询会一直闪任务栏的位置图标。
所以这里只在用户主动点开二级菜单时跑一次，绝不放进后台轮询。
"""
from __future__ import annotations

import re
import subprocess

_CREATE_NO_WINDOW = 0x08000000


def _decode(raw: bytes) -> str:
    try:
        s = raw.decode("utf-8")
        if "\ufffd" not in s:
            return s
    except UnicodeDecodeError:
        pass
    try:
        return raw.decode("mbcs")
    except Exception:  # noqa: BLE001
        return raw.decode("utf-8", "replace")


def _run(*args: str, timeout: float = 12.0) -> str:
    try:
        r = subprocess.run(["netsh", "wlan", *args], capture_output=True,
                           timeout=timeout, creationflags=_CREATE_NO_WINDOW)
    except Exception:  # noqa: BLE001
        return ""
    return _decode(r.stdout or b"")


def _val(line: str) -> str:
    return re.split(r"[:：]", line, maxsplit=1)[-1].strip()


def scan() -> list[dict]:
    """按信号强度返回可见网络：[{ssid, signal, auth, band, secured}]。"""
    text = _run("show", "networks", "mode=bssid")
    rows: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        m = re.match(r"\s*SSID\s+\d+\s*[:：]\s*(.+?)\s*$", line)
        if m:
            cur = {"ssid": m.group(1).strip(), "signal": 0, "auth": "", "band": ""}
            rows.append(cur)
            continue
        if cur is None:
            continue
        if re.search(r"Authentication|身份验证", line):
            cur["auth"] = _val(line)
        elif re.search(r"\bSignal\b|信号", line):
            s = re.search(r"(\d+)\s*%", line)
            if s:
                cur["signal"] = max(cur["signal"], int(s.group(1)))   # 同名多个 BSSID 取最强
        elif re.search(r"\bBand\b|波段|频段", line):
            cur["band"] = _val(line)

    out: dict[str, dict] = {}
    for r in rows:
        key = r["ssid"]
        if not key:                       # 隐藏网络不广播 SSID，列出来也没法点
            continue
        if key not in out or r["signal"] > out[key]["signal"]:
            r["secured"] = bool(r["auth"]) and not re.search(r"open|开放", r["auth"], re.I)
            out[key] = r
    return sorted(out.values(), key=lambda x: -x["signal"])


def current() -> str:
    text = _run("show", "interfaces")
    m = re.search(r"^\s*SSID\s*[:：]\s*(.+?)\s*$", text, re.M)
    return m.group(1) if m else ""


def profiles() -> set[str]:
    text = _run("show", "profiles")
    out: set[str] = set()
    for line in text.splitlines():
        m = re.search(r"(?:All User Profile|所有用户配置文件)\s*[:：]\s*(.+?)\s*$", line, re.I)
        if m:
            out.add(m.group(1))
    return out


def snapshot() -> dict:
    """面板打开时一次拿齐：可见网络 / 当前连接 / 已保存的网络。"""
    return {"networks": scan(), "current": current(), "profiles": profiles()}


def connect(ssid: str) -> tuple[bool, str]:
    """连接已保存的网络；没保存过的让系统面板去收密码（自造 profile 对 WPA3 不可靠）。"""
    try:
        r = subprocess.run(["netsh", "wlan", "connect", f"name={ssid}"],
                           capture_output=True, timeout=10, creationflags=_CREATE_NO_WINDOW)
    except Exception as e:  # noqa: BLE001
        return False, str(e)
    out = _decode((r.stdout or b"") + (r.stderr or b"")).strip()
    ok = r.returncode == 0 and bool(re.search(r"success|成功|completed", out, re.I))
    return ok, out[-140:] if out else ("已发送连接请求" if ok else "连接失败")
