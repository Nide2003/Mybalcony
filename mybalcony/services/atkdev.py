# -*- coding: utf-8 -*-
"""ATK 外设型号库。

数据来自 ATK HUB 网页版（hub.atk.pro v3.2.34）前端 `useDevice` 模块里的 HID 过滤器表：
每台设备都以 `vendorId: 14139 (0x373b)` + `productId` 注册，并在 `custom.name / title /
model / productName` 里写明型号；接收器（dongle）用另一组 PID，名字里带 "Dongle"。

本机实测：373b:1262 报 "ATK N9V2 ULTIMATE dongle"，表中 0x1261/0x1262 即
"ATK N9 V2 Ultimate"（耳机），所以按 PID 就能把「一个 U 盘」还原成具体型号与类别。
"""
from __future__ import annotations

ATK_VID = 0x373B

# pid -> (显示名, 类别)
# 类别取值：keyboard / mouse / headset / dongle / monitor / tablet / handheld /
#          aiGlasses / speaker / webcam / dock / microphone / tv
_MODELS: dict[int, tuple[str, str]] = {
    # ---- 键盘
    0x1005: ("ATK68 Air", "keyboard"),
    0x1012: ("ATK Z87 Series", "keyboard"),
    0x1013: ("ATK Z87 Pro", "keyboard"),
    0x1022: ("YOGO Q75", "keyboard"),
    0x1023: ("YOGO Q75 2.4G Dongle", "dongle"),
    0x1028: ("VGN S87", "keyboard"),
    0x1029: ("VGN S87 Dongle", "dongle"),
    0x1044: ("ATK68 V2 Pro", "keyboard"),
    0x1048: ("ATK A87 PRO", "keyboard"),
    0x105E: ("ATK68 V2 S", "keyboard"),
    0x105F: ("ATK V100", "keyboard"),
    0x1060: ("ATK V100 Pro", "keyboard"),
    0x107C: ("ATK Mercury I", "keyboard"),
    0x10B0: ("EDGE 60HE ULTIMATE", "keyboard"),
    0x109C: ("ATK RS6", "keyboard"),
    0x10C2: ("ATK68 V2 S", "keyboard"),
    0x111E: ("ATK A87 Ultra", "keyboard"),
    0x111F: ("ATK A87 Ultra", "keyboard"),
    0x1176: ("ATK x QK Hex80", "keyboard"),
    0x1177: ("ATK x QK Hex80", "keyboard"),
    0x118C: ("ATK S99", "keyboard"),
    0x118D: ("ATK S99 2.4G Dongle", "dongle"),
    0x118E: ("ATK S87", "keyboard"),
    0x118F: ("ATK S87 Dongle", "dongle"),
    0x119B: ("YOGO 75 PRO", "keyboard"),
    0x119C: ("YOGO 75", "keyboard"),
    0x11FF: ("YOGO 75 PRO 2.4G", "dongle"),
    0x1200: ("YOGO 75 2.4G", "dongle"),
    0x1206: ("ATK EDGE75", "keyboard"),
    0x120C: ("ATK Horizon", "keyboard"),
    0x1231: ("ATK A87 Ultra", "keyboard"),
    0x129F: ("ATK Horizon", "keyboard"),
    0x114D: ("ATK A98 Pro", "keyboard"),
    0x114E: ("ATK A98 Pro", "keyboard"),
    0x1151: ("ATK A98 Pro", "keyboard"),
    0x1152: ("ATK A98 Pro", "keyboard"),
    0x305F: ("ATK V100 2.4G Dongle", "dongle"),
    0x3060: ("ATK V100 Pro 2.4G Dongle", "dongle"),

    # ---- 鼠标
    0x108B: ("ATK X1 Nearlink 8K", "mouse"),
    0x10D8: ("ATK X1", "mouse"),
    0x10EC: ("ATK U2 Pro", "mouse"),
    0x112D: ("ATK A9 Pro", "mouse"),
    0x1147: ("ATK A9 PRO MAX", "mouse"),
    0x11B5: ("ATK A9 Ultimate Nearlink", "mouse"),
    0x11E4: ("ATK F1 Ultimate 2.0", "mouse"),
    0x1156: ("ATK F1 Nearlink", "mouse"),
    0x1282: ("ATK Duckbill ELITE", "mouse"),

    # ---- 耳机
    0x11CA: ("ATK N9 Pro", "headset"),
    0x11CB: ("ATK N9 Pro", "headset"),
    0x1203: ("ATK N9 Ultra", "headset"),
    0x1204: ("ATK N9 Ultra", "headset"),
    0x1261: ("ATK N9 V2 Ultimate", "headset"),
    0x1262: ("ATK N9 V2 Ultimate", "headset"),
    0x12D3: ("ATK N9 V2 PRO", "headset"),
    0x12D4: ("ATK N9 V2 PRO", "headset"),
    0x12D5: ("ATK N9 V2 ULTRA", "headset"),
    0x12D6: ("ATK N9 V2 ULTRA", "headset"),

    # ---- 接收器（单独售卖/单独注册的 dongle）
    0x108C: ("ATK 8K Dongle Nearlink", "dongle"),
    0x1179: ("ATK 8K Dongle Nearlink", "dongle"),
    0x10F0: ("ATK Mouse 1K Dongle", "dongle"),
    0x10F1: ("ATK Mouse 8K Dongle", "dongle"),
    0x1178: ("ATK 8K Nano Dongle", "dongle"),
    0x1148: ("ATK Mouse 1K Dongle", "dongle"),
    0x1196: ("ATK Mouse 8K Dongle", "dongle"),
    0x1283: ("ATK Mouse 8K Dongle", "dongle"),

    # ---- 显示器 / 平板 / 掌机 / 眼镜 / 音箱 / 摄像头 / 扩展坞 / 麦克风
    0x3010: ("ATK Prism Monitor 27", "monitor"),
    0x3028: ("ATK Prism Monitor Pro 27", "monitor"),
    0x3045: ("ATK Prism Monitor Ultra 32", "monitor"),
    0x3062: ("ATK Prism Monitor ULTIMATE 32", "monitor"),
    0x3180: ("ATK Horizon Monitor 34", "monitor"),
    0x3198: ("ATK Horizon Monitor Pro 34", "monitor"),
    0x31B0: ("ATK Horizon Monitor Ultra 34", "monitor"),
    0x3280: ("ATK Nova Monitor 27", "monitor"),
    0x3298: ("ATK Nova Monitor Pro 32", "monitor"),
    0x32B0: ("ATK Nova Monitor ULTIMATE 32", "monitor"),
    0x4010: ("ATK Slate Tablet 11", "tablet"),
    0x4028: ("ATK Slate Tablet Pro 11", "tablet"),
    0x4045: ("ATK Slate Tablet Air 11", "tablet"),
    0x4062: ("ATK Slate Tablet Ultra 13", "tablet"),
    0x4180: ("ATK Vertex Tablet 12.9", "tablet"),
    0x4198: ("ATK Vertex Tablet Pro 12.9", "tablet"),
    0x41B0: ("ATK Vertex Tablet Pro Max 13", "tablet"),
    0x41C8: ("ATK Vertex Tablet ULTIMATE 14", "tablet"),
    0x5010: ("ATK Blade Handheld", "handheld"),
    0x5028: ("ATK Blade Handheld Pro", "handheld"),
    0x5045: ("ATK Blade Handheld Ultra", "handheld"),
    0x5062: ("ATK Blade Handheld ULTIMATE", "handheld"),
    0x5180: ("ATK Titan Handheld Pro", "handheld"),
    0x5198: ("ATK Titan Handheld Pro Max", "handheld"),
    0x51B0: ("ATK Titan Handheld ULTIMATE", "handheld"),
    0x6010: ("ATK Insight Glasses", "aiGlasses"),
    0x6028: ("ATK Insight Glasses Pro", "aiGlasses"),
    0x6045: ("ATK Insight Glasses Ultra", "aiGlasses"),
    0x6062: ("ATK Insight Glasses ULTIMATE", "aiGlasses"),
    0x6180: ("ATK Muse Glasses Pro", "aiGlasses"),
    0x6198: ("ATK Muse Glasses Pro Max", "aiGlasses"),
    0x61B0: ("ATK Muse Glasses ULTIMATE", "aiGlasses"),
    0x7010: ("ATK Harmony Speaker", "speaker"),
    0x7028: ("ATK Harmony Speaker Pro", "speaker"),
    0x7045: ("ATK Harmony Speaker Ultra", "speaker"),
    0x7180: ("ATK Cadence Speaker Pro", "speaker"),
    0x7198: ("ATK Cadence Speaker Pro Max", "speaker"),
    0x71B0: ("ATK Cadence Speaker ULTIMATE", "speaker"),
    0x8010: ("ATK Focus Webcam 1080P", "webcam"),
    0x8028: ("ATK Focus Webcam Pro 2K", "webcam"),
    0x8045: ("ATK Focus Webcam Ultra 4K", "webcam"),
    0x8180: ("ATK Capture Webcam Pro 2K", "webcam"),
    0x8198: ("ATK Capture Webcam Pro Max 4K", "webcam"),
    0x81B0: ("ATK Capture Webcam ULTIMATE 4K", "webcam"),
    0x9010: ("ATK Nexus Dock", "dock"),
    0x9028: ("ATK Nexus Dock Pro", "dock"),
    0x9045: ("ATK Nexus Dock Ultra", "dock"),
    0x9180: ("ATK Port Dock Pro", "dock"),
    0x9198: ("ATK Port Dock Pro Max", "dock"),
    0x91B0: ("ATK Port Dock ULTIMATE", "dock"),
    0xA010: ("ATK Vocal Microphone", "microphone"),
    0xA045: ("ATK Vocal Microphone Ultra", "microphone"),
    0xA180: ("ATK Stage Microphone Pro", "microphone"),
    0xA198: ("ATK Stage Microphone Pro Max", "microphone"),
    0xA1B0: ("ATK Stage Microphone ULTIMATE", "microphone"),

    # ---- 电视 / 盒子
    0x10D9: ("ATK TV88", "tv"),
    0x10DA: ("ATK TV88 2.4G", "tv"),
    0x11FA: ("ATK TV99", "tv"),
    0x11FB: ("ATK TV99 2.4G", "tv"),
    0x4287: ("ATK TV108", "tv"),
    0x4288: ("ATK TV108 2.4G", "tv"),
}

# 型号表没覆盖到的新 PID：用产品名里的关键字猜类别
# 除了通用词，还收了雷蛇这类没有公开 PID 库的常见系列名（开阳、毒蝰、黑寡妇…）
_NAME_HINTS: tuple[tuple[str, str], ...] = (
    ("N9", "headset"),
    ("HEADSET", "headset"),
    ("EARPHONE", "headset"),
    ("MOUSE", "mouse"),
    ("KEYBOARD", "keyboard"),
    ("DONGLE", "dongle"),
    ("RECEIVER", "dongle"),
    ("MONITOR", "monitor"),
    ("TABLET", "tablet"),
    ("SPEAKER", "speaker"),
    ("WEBCAM", "webcam"),
    ("MICROPHONE", "microphone"),
    # --- Razer 系列
    ("DEATHADDER", "mouse"),
    ("VIPER", "mouse"),
    ("BASILISK", "mouse"),
    ("MAMBA", "mouse"),
    ("NAGA", "mouse"),
    ("COBRA", "mouse"),
    ("LANCESHEAD", "mouse"),
    ("HUNTSMAN", "keyboard"),
    ("BLACKWIDOW", "keyboard"),
    ("ORNATA", "keyboard"),
    ("KRAKEN", "headset"),
    ("BLACKSHARK", "headset"),
    ("GOLIATHUS", "mousemat"),
    ("STRIDER", "mousemat"),
    ("FIREFLY", "mousemat"),
    ("TARTARUS", "keypad"),
    ("ORBWEAVER", "keypad"),
    ("LEVIATHAN", "speaker"),
    ("NOMMO", "speaker"),
    ("SEIREN", "microphone"),
    ("RAPTOR", "monitor"),
    ("RYUJIN", "monitor"),
)


def guess_type(name: str) -> str | None:
    """按产品名关键字猜类别（型号表外的设备 / 其他品牌也能用）。"""
    up = (name or "").upper()
    for key, kind in _NAME_HINTS:
        if key in up:
            return kind
    return None


def identify(vid: int, pid: int, name: str = "") -> tuple[str, str] | None:
    """-> (标准型号名, 类别)；不是 ATK 设备（或认不出）返回 None。

    PID 命中表就用表里的名字（比 HID 字符串干净：去掉了 "dongle" 后缀的大小写混乱），
    表里没有才退回用名字猜类别。
    """
    if vid != ATK_VID:
        return None
    hit = _MODELS.get(pid)
    if hit:
        return hit
    kind = guess_type(name)
    return (name, kind) if kind else None
