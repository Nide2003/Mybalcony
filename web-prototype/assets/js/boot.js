/*
 * 原型引导：舞台生命周期、两级展开交互、页面组件映射。
 * 时序严格按文档「场景 C」：先 append 进已在 DOM 的容器，再设 mode，最后调 JS API 配置。
 */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const island = $("#island");
  const stage = $("#stage");
  const navMount = $("#navMount");

  // ---------- 可变 mock 状态 ----------
  const state = {
    current: "home",
    clips: MOCK.clips.slice(),
    tiles: MOCK.controls.tiles.map((t) => ({ ...t })),
    sliders: MOCK.controls.sliders.map((s) => ({ ...s })),
  };

  // ---------- 媒体信息填充 ----------
  const media = MOCK.media;
  $("#coverImg").src = media.cover;
  $("#midCover").src = media.cover;
  $("#capsuleTitle").textContent = media.title;
  $("#capsuleLyric").textContent = media.lyric[1] || "";
  $("#midTitle").textContent = media.title;
  $("#midArtist").textContent = media.artist;
  $("#midLyric").textContent = media.lyric.join(" · ");

  // ---------- 概览条（中岛） ----------
  const w = MOCK.weather.now;
  const b = MOCK.battery.system;
  const unread = MOCK.messages.tiles.reduce((n, t) => n + t.count, 0);
  $("#midOverview").innerHTML = `
    <span class="ov-chip">天气 <b>${w.city} ${w.temp} ${w.desc}</b></span>
    <span class="ov-chip">电量 <b>${b.level}%</b>${b.plugged ? " · 接通电源" : ""}</span>
    <span class="ov-chip">未读 <b>${unread}</b> 条</span>
  `;

  // ---------- WebGL 组件挂载 ----------
  const EVENT_MAP = {
    state: "lg-statechange",
    button: "lg-buttontap",
    dialog: "lg-dialogtap",
    link: "lg-linktap",
  };

  function applyConfig(el, mode, config) {
    if (!config) return;
    if (config.tabs && el.setTabs) el.setTabs(config.tabs);
    if (config.buttons && el.setButtons) el.setButtons(config.buttons);
    if (config.dialog && el.setDialog) el.setDialog(config.dialog);
    if (config.scroll && el.setScroll) el.setScroll(config.scroll);
    if (config.state && el.setState) el.setState(config.state);
  }

  // 已挂载组件及其事件回调，切页时先解绑再移除，避免拆卸过程中的状态事件回流触发递归
  const live = [];

  function createGlass(parent, opts) {
    const el = document.createElement("liquid-glass");
    el.style.width = "100%";
    el.style.height = "100%";
    if (opts.attrs) Object.entries(opts.attrs).forEach(([k, v]) => el.setAttribute(k, v));
    parent.appendChild(el); // 先进 DOM，触发 connectedCallback
    if (opts.mode) el.setAttribute("mode", opts.mode); // 再设 mode 触发 rebuild
    const handlers = {};
    if (opts.hooks) {
      Object.entries(EVENT_MAP).forEach(([key, evt]) => {
        const handler = opts.hooks[key];
        if (handler) {
          const wrapped = (e) => handler(e.detail, el);
          handlers[evt] = wrapped;
          el.addEventListener(evt, wrapped);
        }
      });
    }
    live.push({ el, handlers });
    // 与官方 demo 一致：等一帧组件完成首次 rebuild 后再下发配置，避免配置被丢弃
    requestAnimationFrame(() => applyConfig(el, opts.mode, opts.config));
    return el;
  }

  function detachMount(m) {
    Object.entries(m.handlers).forEach(([evt, fn]) => m.el.removeEventListener(evt, fn));
    m.el.remove();
  }

  function clearStage() {
    live.filter((m) => stage.contains(m.el)).forEach(detachMount);
    stage.innerHTML = "";
  }

  // 轻提示：按钮点击后在挂载点内临时显示文案
  function flash(mount, text) {
    const old = mount.querySelector(".flash-tip");
    if (old) old.remove();
    const tip = document.createElement("div");
    tip.className = "flash-tip";
    tip.textContent = text;
    tip.style.cssText = "position:absolute;inset:auto 0 8px;text-align:center;font-size:12px;color:var(--ink-2);pointer-events:none";
    mount.style.position = "relative";
    mount.appendChild(tip);
    setTimeout(() => tip.remove(), 1200);
  }

  // ---------- 中岛快捷按钮（懒挂载：中岛可见后再建，避免隐藏容器 0 尺寸） ----------
  let midBuilt = false;
  function ensureMidActions() {
    if (midBuilt) return;
    midBuilt = true;
    const mount = $("#midActions");
    createGlass(mount, {
      mode: "buttons",
      config: { buttons: MOCK.homeActions },
      hooks: { button: ({ id }) => {
        const act = MOCK.homeActions.find((a) => a.id === id);
        if (act) flash(mount, act.label);
      } },
    });
  }

  // ---------- 导航（懒挂载：完整岛可见后再建） ----------
  let navEl = null;
  let navBuilt = false;

  function ensureNav() {
    if (navBuilt) return;
    navBuilt = true;
    navEl = createGlass(navMount, {
      mode: "single-bottom-tabs",
      config: { tabs: [MOCK.tabs.map((t) => ({ icon: t.icon, label: t.label, viewport: t.viewport }))] },
      hooks: {
        state: (detail) => {
          const idx = detail.selectedTab;
          if (idx == null) return;
          const key = MOCK.tabs[idx].key;
          if (key === state.current) return; // 避免 setState 回流造成递归
          switchPage(key);
        },
      },
    });
  }

  function syncNav() {
    const idx = MOCK.tabs.findIndex((t) => t.key === state.current);
    if (navEl && navEl.setState && navEl.__tab !== idx) {
      navEl.__tab = idx;
      navEl.setState({ selectedTab: idx });
    }
  }

  // ---------- 页面映射 ----------
  function entry(title, subtitle, side, sideCls) {
    return { title, subtitle, ...(side ? { link: { text: side } } : {}), _cls: sideCls };
  }

  const pages = {
    home() {
      const wrap = document.createElement("div");
      wrap.className = "panel-glass";
      wrap.innerHTML = `
        <div class="entry">
          <div class="cover lg"><img src="${media.cover}" alt="封面" /></div>
          <div class="e-main">
            <div class="e-title">${media.title}</div>
            <div class="e-sub">${media.artist}</div>
            <div class="e-sub">${media.lyric.join(" · ")}</div>
          </div>
        </div>`;
      stage.appendChild(wrap);

      const btnMount = document.createElement("div");
      btnMount.className = "btn-row";
      btnMount.style.height = "76px";
      stage.appendChild(btnMount);
      createGlass(btnMount, {
        mode: "buttons",
        config: { buttons: MOCK.homeActions },
        hooks: {
          button: ({ id }) => {
            const act = MOCK.homeActions.find((a) => a.id === id);
            if (act) flash(btnMount, act.label);
          },
        },
      });
    },

    msg() {
      const tiles = MOCK.messages.tiles.map((t) =>
        entry(t.name, `${t.count} 条未读 · ${t.last}`, `${t.count}`, t.count ? "up" : "")
      );
      const history = MOCK.messages.history.map((h) =>
        entry(h.name, h.desc, h.time)
      );
      createGlass(stage, {
        mode: "scroll-container",
        attrs: { class: "scroll-tall" },
        config: { scroll: [...tiles, ...history] },
      });
    },

    stock() {
      const row = document.createElement("div");
      row.className = "row";
      const seg = document.createElement("div");
      seg.style.height = "64px";
      row.appendChild(seg);
      stage.appendChild(row);
      createGlass(seg, {
        mode: "buttons",
        config: { buttons: MOCK.stocks.markets.map((m) => ({ id: m.id, label: m.label, style: "surface" })) },
      });

      const list = MOCK.stocks.list.map((s) =>
        entry(s.name, `${s.code} · ${s.price}`, s.change, s.up ? "up" : "down")
      );
      createGlass(stage, { mode: "scroll-container", config: { scroll: list } });
    },

    weather() {
      const row = document.createElement("div");
      row.className = "row";
      const chips = document.createElement("div");
      chips.style.height = "64px";
      row.appendChild(chips);
      stage.appendChild(row);
      createGlass(chips, {
        mode: "buttons",
        config: { buttons: MOCK.weather.cities.map((c) => ({ id: c, label: c, style: "surface" })) },
      });

      const hourly = MOCK.weather.hourly.map((h) => entry(h.time, h.desc, h.temp));
      const daily = MOCK.weather.daily.map((d) => entry(d.day, d.desc, `${d.low}° / ${d.high}°`));
      createGlass(stage, { mode: "scroll-container", config: { scroll: [...hourly, ...daily] } });
    },

    ctl() {
      const row = document.createElement("div");
      row.className = "row";
      const v = document.createElement("div"); v.style.height = "120px";
      const b = document.createElement("div"); b.style.height = "120px";
      row.append(v, b);
      stage.appendChild(row);
      const mkSlider = (parent, idx) => ({
        mode: idx === 0 ? "single-slider" : "slider-card",
        config: { state: { sliderValue: state.sliders[idx].value } },
        hooks: { state: (detail) => { if (detail.sliderValue != null) state.sliders[idx].value = detail.sliderValue; } },
      });
      createGlass(v, mkSlider(0));
      createGlass(b, mkSlider(1));

      const scale = document.createElement("div");
      scale.style.height = "120px";
      stage.appendChild(scale);
      createGlass(scale, mkSlider(2));

      const tiles = document.createElement("div");
      tiles.className = "btn-row";
      tiles.style.height = "76px";
      stage.appendChild(tiles);
      const tintStyle = { blue: "blue", green: "green", orange: "orange", red: "red", purple: "purple" };
      createGlass(tiles, {
        mode: "buttons",
        config: {
          buttons: state.tiles.map((t) => ({
            id: t.id,
            label: `${t.name} ${t.on ? "开" : "关"}`,
            style: t.on ? tintStyle[t.tint] || "surface" : "surface",
          })),
        },
        hooks: {
          button: ({ id }) => {
            const t = state.tiles.find((x) => x.id === id);
            if (t) { t.on = !t.on; renderPage(); }
          },
        },
      });
    },

    bat() {
      const ring = document.createElement("div");
      ring.style.height = "180px";
      stage.appendChild(ring);
      createGlass(ring, {
        mode: "ring-progress",
        config: { state: { ringProgressValue: MOCK.battery.system.level } },
      });
      const dev = MOCK.battery.devices.map((d) =>
        entry(d.name, d.connected ? "已连接" : "未连接", `${d.level}%`, d.level > 20 ? "up" : "down")
      );
      createGlass(stage, { mode: "scroll-container", config: { scroll: dev } });
    },

    clip() {
      const head = document.createElement("div");
      head.className = "row";
      head.innerHTML = `<div></div>`;
      const clearBtn = document.createElement("div");
      clearBtn.style.height = "56px";
      head.appendChild(clearBtn);
      stage.appendChild(head);
      createGlass(clearBtn, {
        mode: "buttons",
        config: { buttons: [{ id: "clear", label: "清空", style: "red" }] },
        hooks: { button: () => openClearDialog() },
      });

      const list = state.clips.map((c) =>
        entry(c.text, c.pinned ? "已置顶" : "点击复制", c.pinned ? "置顶" : "")
      );
      createGlass(stage, { mode: "scroll-container", config: { scroll: list } });
    },

    trans() {
      const row = document.createElement("div");
      row.className = "btn-row";
      row.style.height = "64px";
      stage.appendChild(row);
      createGlass(row, {
        mode: "buttons",
        config: {
          buttons: [
            { id: "go", label: "翻译", style: "blue" },
            { id: "clip", label: "翻译剪贴板", style: "surface" },
            { id: "copy", label: "复制译文", style: "transparent" },
          ],
        },
      });

      const out = document.createElement("div");
      out.className = "panel-glass";
      out.innerHTML = `
        <div class="e-sub">${MOCK.translate.source}</div>
        <div class="e-title" style="margin-top:6px">${MOCK.translate.result}</div>`;
      stage.appendChild(out);

      const sub = MOCK.translate.subtitles.map((s) => entry(s.src, s.dst));
      createGlass(stage, { mode: "scroll-container", config: { scroll: sub } });

      const words = MOCK.translate.words.map((w) => entry(w.word, w.meaning));
      createGlass(stage, { mode: "scroll-container", config: { scroll: words } });
    },
  };

  function renderPage() {
    clearStage();
    pages[state.current]();
    syncNav();
  }

  function switchPage(key) {
    state.current = key;
    renderPage();
  }

  // ---------- 清空确认弹窗 ----------
  function openClearDialog() {
    clearStage();
    const dlg = document.createElement("div");
    dlg.style.height = "260px";
    stage.appendChild(dlg);
    createGlass(dlg, {
      mode: "dialog",
      config: {
        dialog: { title: "清空剪贴板", body: "将删除全部剪贴板记录，此操作不可撤销。", cancelText: "取消", okayText: "确认清空" },
      },
      hooks: {
        dialog: ({ action }) => {
          if (action === "okay") state.clips = [];
          renderPage();
        },
      },
    });
  }

  // ---------- 两级展开状态机 ----------
  let enterTimer = null;
  let leaveTimer = null;

  function setLevel(level) {
    island.className = `island state-${level}`;
    if (level === "mid" || level === "full") ensureMidActions();
    if (level === "full") {
      ensureNav();
      renderPage();
    }
  }

  function enterIsland() {
    clearTimeout(leaveTimer);
    clearTimeout(enterTimer);
    if (island.classList.contains("state-full")) return;
    enterTimer = setTimeout(() => setLevel("mid"), 220);
  }

  function leaveIsland() {
    clearTimeout(enterTimer);
    clearTimeout(leaveTimer);
    leaveTimer = setTimeout(() => {
      if (island.classList.contains("state-full")) setLevel("mid");
      else setLevel("compact");
    }, 360);
  }

  $("#capsule").addEventListener("click", () => setLevel("full"));
  $("#midPanel").addEventListener("click", () => setLevel("full"));
  island.addEventListener("mouseenter", enterIsland);
  island.addEventListener("mouseleave", leaveIsland);

  // ---------- 小形象：siri-wave orb ----------
  createGlass($("#petMount"), {
    mode: "siri-wave",
    config: { state: { variant: "orb", speed: 1, scale: 1 } },
  });

  // ---------- 启动 ----------
  // 导航 / 中岛按钮 / 页面组件均在对应面板可见后懒挂载，避免隐藏容器 0 尺寸
})();
