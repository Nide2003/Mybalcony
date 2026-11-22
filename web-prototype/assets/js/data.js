/*
 * Mock 数据层（原型阶段）。
 * 真实桌面服务（音量 / 蓝牙 / 天气 / 股票 / 剪贴板……）在纯 Web 原型里跑不起来，
 * 这里先用格式对齐的示例数据把界面和交互撑起来；回填真实后端时只换本文件的数据来源。
 */
window.MOCK = {
  // 收起态 / 主页媒体卡
  media: {
    cover: "https://picsum.photos/seed/mybalcony/160/160",
    title: "眉间放一字宽",
    artist: "辛晓琪 · 领悟",
    lyric: ["身不由己在天边", "才明白爱恨情仇", "最伤最痛是后悔"],
    playing: true,
  },

  // 导航页签（顺序与现有 island.tab_order 对齐）
  tabs: [
    { key: "home",    label: "主页",   icon: "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z", viewport: 24 },
    { key: "msg",     label: "消息",   icon: "M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z", viewport: 24 },
    { key: "stock",   label: "股票",   icon: "M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z", viewport: 24 },
    { key: "weather", label: "天气",   icon: "M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14h19.5c2.34 0 4.5-2.01 4.5-4.5 0-1.74-.78-3.28-2.15-4.46z", viewport: 24 },
    { key: "ctl",     label: "控制",   icon: "M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v2h8v-2h-8zM13 3v2h8V3h-8zm-6 10h8v-2H7v2zm-4 0h2v-2H3v2zm16 0h2v-2h-2v2z", viewport: 24 },
    { key: "bat",     label: "电量",   icon: "M15.67 4H14V2h-4v2H8.33C7.6 4 7 4.6 7 5.33v15.33C7 21.4 7.6 22 8.33 22h7.33c.74 0 1.34-.6 1.34-1.33V5.33C17 4.6 16.4 4 15.67 4z", viewport: 24 },
    { key: "clip",    label: "剪贴板", icon: "M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z", viewport: 24 },
    { key: "trans",   label: "翻译",   icon: "M12.87 15.07l-2.54-2.51.03-.03c1.02-1.5 1.85-3.17 2.23-4.53h2.24c.24.83.56 1.64.96 2.27l1.59-1.09C16.92 8.44 15.72 7 14 7h-4V5H8v2H4v2h6.94c-.21.58-.48 1.17-.79 1.75L5.37 15 7 16.63l3.5-3.5c.31.57.68 1.13 1.08 1.66l1.29.28zM18 4h-3.5L12 10.5 10.5 7H7l5.25 11.5L17 12h1v8h2V4h-2z", viewport: 24 },
  ],

  // 主页快捷按钮（buttons 组件）
  homeActions: [
    { id: "pin",    label: "保持展开", style: "surface" },
    { id: "pt",     label: "可穿透",   style: "transparent" },
    { id: "mute",   label: "静音",     style: "transparent" },
    { id: "live",   label: "实时字幕", style: "surface" },
    { id: "center", label: "居中显示",  style: "transparent" },
  ],

  // 消息页
  messages: {
    tiles: [
      { kind: "qq",     name: "QQ",   count: 3, last: "群消息 99+" },
      { kind: "wechat", name: "微信", count: 1, last: "文件传输助手" },
      { kind: "mail",   name: "邮件", count: 2, last: "周报提醒" },
    ],
    history: [
      { kind: "mail",   name: "邮件",   desc: "收到两封新邮件", time: "09:42" },
      { kind: "qq",    name: "QQ",     desc: "阿伟 发来消息",   time: "09:15" },
      { kind: "wechat", name: "微信",   desc: "文件传输助手",     time: "08:57" },
      { kind: "mail",  name: "邮件",    desc: "系统安全通知",     time: "昨天" },
    ],
  },

  // 股票页
  stocks: {
    markets: [{ id: "a", label: "A股" }, { id: "hk", label: "港股" }, { id: "us", label: "美股" }],
    list: [
      { name: "宁德时代", code: "300750", price: "187.42", change: "+2.31%", up: true },
      { name: "贵州茅台", code: "600519", price: "1688.00", change: "-0.82%", up: false },
      { name: "纳斯达克", code: "IXIC",   price: "18430.80", change: "+0.54%", up: true },
      { name: "苹果",     code: "AAPL",  price: "227.72",  change: "+1.12%", up: true },
      { name: "腾讯控股", code: "0700",   price: "382.20",   change: "-1.04%", up: false },
    ],
  },

  // 天气页
  weather: {
    cities: ["上海", "安溪", "福鼎", "南京"],
    now: { city: "上海", temp: "22℃", icon: "cloud", desc: "多云", high: "24°", low: "18°" },
    hourly: [
      { time: "现在", temp: "22°", desc: "多云" },
      { time: "14时", temp: "23°", desc: "晴" },
      { time: "15时", temp: "23°", desc: "晴" },
      { time: "16时", temp: "21°", desc: "多云" },
      { time: "17时", temp: "19°", desc: "阴" },
    ],
    daily: [
      { day: "今天", desc: "多云", high: "24°", low: "18°" },
      { day: "周二", desc: "晴",   high: "25°", low: "17°" },
      { day: "周三", desc: "阴",   high: "22°", low: "16°" },
      { day: "周四", desc: "小雨", high: "20°", low: "15°" },
    ],
  },

  // 控制页
  controls: {
    sliders: [
      { id: "vol",    label: "音量",   value: 24, icon: "vol" },
      { id: "bri",    label: "亮度",   value: 100, icon: "sun" },
      { id: "scale",  label: "胶囊大小", value: 130, icon: "monitor" },
    ],
    tiles: [
      { id: "wifi",    name: "无线局域网", on: true,  tint: "blue" },
      { id: "hotspot", name: "个人热点", on: false, tint: "green" },
      { id: "bt",      name: "蓝牙",     on: true,  tint: "blue" },
      { id: "air",     name: "飞行模式", on: false, tint: "orange" },
    ],
  },

  // 电量页
  battery: {
    system: { name: "本机电池", level: 96, plugged: true },
    devices: [
      { name: "ATK N9V2 ULTIMATE dongle", level: 50, connected: true },
      { name: "Razer DeathAdder V3 Pro",  level: 66, connected: true },
      { name: "OPPO Enco Free4",            level: 60, connected: false },
      { name: "Huawei 畅想 60",            level: 80, connected: true },
      { name: "USB Gaming Keyboard",        level: 100, connected: true },
    ],
  },

  // 剪贴板页
  clips: [
    { id: 1, text: "液态玻璃（Liquid Glass）是苹果在 WWDC 推出的界面设计语言。", pinned: true },
    { id: 2, text: "npm install liquid-glass-webgl", pinned: false },
    { id: 3, text: "D:\\download\\Mybalcony", pinned: false },
    { id: 4, text: "今日待办：整理简历、投递工艺工程师岗位。", pinned: false },
  ],

  // 翻译页
  translate: {
    source: "こんにちは、今日はいい天気ですね。",
    result: "你好，今天天气真好呢。",
    subtitles: [
      { src: "こんにちは", dst: "你好" },
      { src: "今日はいい天気", dst: "今天天气真好" },
      { src: "楽しい週末を", dst: "祝你周末愉快" },
    ],
    words: [
      { word: "天気（てんき）", meaning: "天气" },
      { word: "週末（しゅうまつ）", meaning: "周末" },
      { word: "楽しい（たのしい）", meaning: "快乐的" },
    ],
  },
};
