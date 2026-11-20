"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch {} },
    del(k) { try { localStorage.removeItem(k); } catch {} },
  };
  const SVGNS = "http://www.w3.org/2000/svg";
  const el = (tag, props = {}, ...children) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "attrs") for (const [a, b] of Object.entries(v)) node.setAttribute(a, b);
      else if (k === "dataset") Object.assign(node.dataset, v);
      else if (k === "style") node.style.cssText = v;
      else node[k] = v;
    }
    for (const c of children) if (c != null && c !== false) node.append(c);
    return node;
  };
  const sv = (tag, attrs = {}, text) => {
    const node = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    if (text != null) node.textContent = text;
    return node;
  };
  // Lists are rebuilt on every refresh; put keyboard focus back on the item with the same data-key.
  const replaceKeepingFocus = (container, children) => {
    const key = container.contains(document.activeElement) ? document.activeElement.dataset.key : undefined;
    container.replaceChildren(...children);
    if (key !== undefined) [...container.querySelectorAll("[data-key]")].find((n) => n.dataset.key === key)?.focus();
  };
  const icon = (html) => { const s = document.createElement("span"); s.innerHTML = html; return s.firstChild; };
  const fmt = (n, d = 2) => (n == null || Number.isNaN(n) ? "–" : Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
  const rel = (ms) => {
    if (ms == null || Number.isNaN(ms)) return "–";
    const s = Math.round((Date.now() - ms) / 1000);
    if (s < 5) return "just now";
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  };
  // Same wording as the status command: "45 s", "42 min", "2 h 10 min", "3 days".
  const dur = (sec) => {
    if (sec == null || Number.isNaN(sec)) return "–";
    const s = Math.max(0, Math.floor(sec));
    if (s < 60) return `${s} s`;
    if (s < 3600) return `${Math.floor(s / 60)} min`;
    if (s < 2 * 86400) { const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60); return m ? `${h} h ${m} min` : `${h} h`; }
    return `${Math.floor(s / 86400)} days`;
  };
  // "Mon 16:29" within six days either way, a date otherwise.
  const when = (ms) => new Date(ms).toLocaleString(undefined, Math.abs(ms - Date.now()) < 6 * 86400e3
    ? { weekday: "short", hour: "2-digit", minute: "2-digit" }
    : { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  // Rates split from the account total are estimates, so label them.
  const estimated = () => el("span", { className: "estimated", textContent: "Estimated", title: "Estimated from the account's usage rate" });
  const withEstimate = (text, isEstimate) => (isEstimate ? [text, " ", estimated()] : [text]);
  const rateParts = (m) => (m?.rate == null ? ["–"] : withEstimate(`${fmt(m.rate)} / hr`, m.rate_estimated));
  const bytes = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`);
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const getJSON = async (url) => {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  };
  const tildify = (p) => (p ?? "").replace(/^\/(Users|home)\/[^/]+/, "~");
  // Numbers as a log prints them: 0.0198, 2.0e-4 → "0.0002", 1234.5 → "1,234.5".
  const num = (v) => (Math.abs(v) >= 1000 ? Number(v.toFixed(1)).toLocaleString() : String(Number(Number(v).toPrecision(4))));
  // Long folders collapse to their last segment so the file name stays visible.
  const shortDir = (p) => {
    const t = tildify(p).replace(/\/$/, "");
    return t.length <= 32 ? t : `…/${t.split("/").pop()}`;
  };

  const ICON = {
    copy: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="5" y="5" width="9" height="9" rx="1.5"/><path d="M11 5V3.5A1.5 1.5 0 009.5 2h-6A1.5 1.5 0 002 3.5v6A1.5 1.5 0 003.5 11H5"/></svg>',
    check: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 8.5l3 3 7-7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    play: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M5 3.5l7 4.5-7 4.5z" stroke-linejoin="round"/></svg>',
    plus: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 3v10M3 8h10" stroke-linecap="round"/></svg>',
    stop: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="4" y="4" width="8" height="8" rx="1.5"/></svg>',
    file: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M4 1.5h5L12.5 5v9.5h-8.5z" stroke-linejoin="round"/><path d="M9 1.5V5h3.5"/></svg>',
    err: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6"/><path d="M8 5v3.5M8 11h.01" stroke-linecap="round"/></svg>',
    dot: '<svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><circle cx="8" cy="8" r="2.5"/></svg>',
    close: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M4 4l8 8M12 4l-8 8"/></svg>',
    chip: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="3.5" y="3.5" width="9" height="9" rx="1.5"/><path d="M6 1.5v2M10 1.5v2M6 12.5v2M10 12.5v2M1.5 6h2M1.5 10h2M12.5 6h2M12.5 10h2"/></svg>',
    clock: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="6"/><path d="M8 4.5V8l2.5 1.5" stroke-linecap="round"/></svg>',
    terminal: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="1.5" y="2.5" width="13" height="11" rx="1.5"/><path d="M4.5 6.5l2 1.5-2 1.5M8 10h3.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    warn: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M8 1.5L15 14H1L8 1.5z" stroke-linejoin="round"/><path d="M8 6v3.5M8 11.5v.5" stroke-linecap="round"/></svg>',
    info: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6.25"/><path d="M8 7.5V11M8 5h.01" stroke-linecap="round"/></svg>',
    ok: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="8" cy="8" r="6.25"/><path d="M5.5 8.25l1.75 1.75 3.25-3.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    spinner: '<svg class="spinner" width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M14 8a6 6 0 11-6-6"/></svg>',
    sun: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="8" cy="8" r="3"/><path d="M8 1v1.5M8 13.5V15M1 8h1.5M13.5 8H15M3 3l1 1M12 12l1 1M3 13l1-1M12 4l1-1" stroke-linecap="round"/></svg>',
    moon: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><path d="M13.5 9.5A5.5 5.5 0 016.5 2.5a5.5 5.5 0 107 7z" stroke-linejoin="round"/></svg>',
    monitor: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="1.5" y="2.5" width="13" height="9" rx="1.5"/><path d="M5 14h6"/></svg>',
  };
  const skel = (cls) => el("span", { className: `skeleton ${cls}`, attrs: { "aria-hidden": "true" } });
  // An empty state: an icon, what is missing, and what to do about it.
  const emptyState = (tag, ic, title, desc, ...more) => el(tag, { className: "empty" },
    ic ? el("div", { className: "empty-icon" }, icon(ic)) : null,
    el("div", { className: "empty-title", textContent: title }),
    desc ? el("div", { className: "empty-desc", textContent: desc }) : null, ...more);
  // ⌘ on a Mac, Ctrl elsewhere; the page accepts either.
  const MAC = /mac|iphone|ipad/i.test(navigator.userAgentData?.platform ?? navigator.platform ?? "");
  const shortcut = (key) => (MAC ? `⌘${key}` : `Ctrl ${key}`);
  for (const k of document.querySelectorAll("[data-shortcut-label]")) k.textContent = shortcut(k.dataset.shortcutLabel);

  /* ---------- State ---------- */
  let state = null;
  let lastUsage = null;
  let lastEvents = [];
  let route = "overview";
  // Usage rate is the default: Colab only updates the balance every so often, the rate moves at once.
  let measure = store.get("measure") === "balance" ? "balance" : "rate";
  let range = ["1h", "24h", "7d", "30d"].includes(store.get("range")) ? store.get("range") : "24h";
  let statusFilter = "all";
  let selectedLog = store.get("log");
  let selectedHistory = store.get("history");
  let selectedSession = null;  // endpoint shown in the details drawer
  let jumpToError = false;  // the next paint of the log scrolls to its last error
  let selectedMetric = store.get("metric");

  /* ---------- Theme ---------- */
  function applyTheme(t) {
    if (t === "light" || t === "dark") { document.documentElement.dataset.theme = t; store.set("theme", t); }
    else { delete document.documentElement.dataset.theme; store.del("theme"); t = "system"; }
    for (const b of document.querySelectorAll("[data-theme-choice]")) b.setAttribute("aria-pressed", String(b.dataset.themeChoice === t));
  }
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-theme-choice]");
    if (b) applyTheme(b.dataset.themeChoice);
  });

  /* ---------- Toasts ---------- */
  // Short messages at the bottom right that go away on their own; hovering one keeps it.
  const TOAST_ICON = { success: ICON.ok, error: ICON.err, warning: ICON.warn, info: ICON.info };
  function toast(title, { description, tone = "default", code = false, action, duration = 4000 } = {}) {
    const box = $("toaster");
    const dismiss = () => {
      clearTimeout(timer);
      if (!node.isConnected || node.classList.contains("leaving")) return;
      node.classList.add("leaving");
      setTimeout(() => node.remove(), 160);
    };
    const node = el("div", { className: `toast ${tone}`, attrs: tone === "error" ? { role: "alert" } : {} },
      TOAST_ICON[tone] ? el("span", { className: "toast-icon" }, icon(TOAST_ICON[tone])) : null,
      el("div", { className: "toast-body" },
        el("div", { className: "toast-title", textContent: title }),
        description ? el("div", { className: `toast-desc${code ? " code" : ""}`, textContent: description }) : null),
      action ? el("button", { className: "btn sm toast-action", type: "button", textContent: action.label, onclick: () => { dismiss(); action.run(); } }) : null,
      el("button", { className: "toast-close", type: "button", innerHTML: ICON.close, onclick: dismiss, attrs: { "aria-label": "Dismiss" } }));
    let timer = setTimeout(dismiss, duration);
    node.addEventListener("pointerenter", () => clearTimeout(timer));
    node.addEventListener("pointerleave", () => { clearTimeout(timer); timer = setTimeout(dismiss, 2000); });
    node.addEventListener("focusin", () => clearTimeout(timer));
    box.append(node);
    while (box.children.length > 3) box.firstElementChild.remove();
    return dismiss;
  }
  const copyFailed = () => toast("Couldn't copy", { tone: "error", description: "The browser blocked the clipboard. Select the text and copy it yourself." });

  /* ---------- Copy buttons ---------- */
  function flashCheck(btn, restore) { btn.innerHTML = ICON.check; setTimeout(() => (btn.innerHTML = restore), 1200); }
  for (const btn of document.querySelectorAll(".copy")) btn.innerHTML = ICON.copy;
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".copy");
    if (!btn) return;
    const text = btn.parentElement.querySelector("code").textContent;
    try { await navigator.clipboard.writeText(text); } catch { copyFailed(); return; }
    flashCheck(btn, ICON.copy);
    toast("Copied to clipboard", { tone: "success", description: text, code: true });
  });
  // A small button that copies a command; the command itself is in its tooltip.
  const copyCommand = (cmd, label, key) => el("button", { className: "btn sm copy-cmd", type: "button", title: cmd, dataset: { cmd, label, key } },
    icon(ICON.copy), el("span", { textContent: label }));
  document.addEventListener("click", async (e) => {
    const btn = e.target.closest(".copy-cmd");
    if (!btn) return;
    try { await navigator.clipboard.writeText(btn.dataset.cmd); } catch { copyFailed(); return; }
    btn.classList.add("done");
    btn.replaceChildren(icon(ICON.check), el("span", { textContent: "Copied" }));
    setTimeout(() => { btn.classList.remove("done"); btn.replaceChildren(icon(ICON.copy), el("span", { textContent: btn.dataset.label })); }, 1500);
    toast("Copied to clipboard", { tone: "success", description: btn.dataset.cmd, code: true });
  });
  // A command with a button that copies it. Colab Monitor shows commands; it never runs them.
  const snippet = (cmd, label = "Copy command", key = cmd) => el("div", { className: "snippet" },
    el("code", { textContent: cmd, title: cmd }),
    el("button", { className: "btn icon copy", type: "button", innerHTML: ICON.copy, dataset: { key, tooltip: label }, attrs: { "aria-label": label } }));

  /* ---------- Router ---------- */
  const ROUTES = ["overview", "sessions", "logs", "history", "settings"];
  // "#/sessions?session=ENDPOINT" opens that machine's details over the page.
  const sessionHref = (endpoint) => `#/${route}?session=${encodeURIComponent(endpoint)}`;
  function onRoute() {
    const r = (location.hash.match(/^#\/(\w+)/) || [])[1];
    const next = ROUTES.includes(r) ? r : "overview";
    const param = new URLSearchParams(location.hash.split("?")[1] ?? "").get("session");
    const pageChanged = next !== route || !state;
    route = next;
    if (pageChanged) {
      for (const p of document.querySelectorAll("[data-page]")) p.hidden = p.dataset.page !== route;
      for (const a of document.querySelectorAll("[data-route]")) {
        if (a.dataset.route === route) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
      }
      $("app").classList.remove("nav-open");
      window.scrollTo(0, 0);
    }
    setDrawer(param);
    updateTitle();
    // Opening or closing the details keeps the page as it is; only a new page reloads its data.
    if (pageChanged) tick(true);
  }
  window.addEventListener("hashchange", onRoute);

  /* ---------- Sidebar ---------- */
  // On a wide window the sidebar collapses off the side and stays that way; on a phone it opens over the page.
  const phone = window.matchMedia("(max-width: 900px)");
  function syncSidebar() {
    const open = phone.matches ? $("app").classList.contains("nav-open") : document.documentElement.dataset.sidebar !== "collapsed";
    $("menu-btn").setAttribute("aria-expanded", String(open));
  }
  function toggleSidebar() {
    if (phone.matches) $("app").classList.toggle("nav-open");
    else {
      const collapsed = document.documentElement.dataset.sidebar !== "collapsed";
      if (collapsed) { document.documentElement.dataset.sidebar = "collapsed"; store.set("sidebar", "collapsed"); }
      else { delete document.documentElement.dataset.sidebar; store.del("sidebar"); }
    }
    syncSidebar();
  }
  $("menu-btn").addEventListener("click", toggleSidebar);
  $("scrim").addEventListener("click", () => { $("app").classList.remove("nav-open"); syncSidebar(); });
  phone.addEventListener("change", syncSidebar);
  new MutationObserver(syncSidebar).observe($("app"), { attributes: true, attributeFilter: ["class"] });
  syncSidebar();
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("app").classList.contains("nav-open")) { $("app").classList.remove("nav-open"); return; }
    if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "b" && !selectedSession) {
      e.preventDefault();
      toggleSidebar();
    }
  });

  const STATUS = {
    busy: ["Running", "job in progress"],
    idle: ["Idle", "still billing"],
    orphan: ["Orphan", "unknown to the CLI"],
    gone: ["Released", ""],
    unknown: ["Unknown", "waiting for Colab"],
    stopping: ["Stopping", "stopped by the CLI; Colab hasn't confirmed yet"],
  };
  const LIVE = new Set(["busy", "idle", "orphan", "stopping"]);
  const hardware = (s) => [s.accelerator === "NONE" ? "CPU" : s.accelerator, s.machine_shape === "HIGH_RAM" ? "High-RAM" : null].filter(Boolean).join(" · ");
  const baseName = (p) => (p ?? "").split("/").pop();
  const lastRun = (s) => (s.last_execution?.time ? Date.parse(s.last_execution.time.replace(" ", "T")) : null);
  const statusPill = (status) => el("span", { className: `status ${status}` }, el("span", { className: "d" }), (STATUS[status] ?? [status])[0]);

  function renderApiNotice(api) {
    const failing = api.enabled && api.error;
    for (const n of document.querySelectorAll(".api-notice")) {
      n.hidden = !failing;
      if (!failing) continue;
      n.querySelector(".notice-title").textContent = api.updated_at
        ? `Can't reach Colab. Showing data from ${rel(Date.parse(api.updated_at))}.`
        : "Can't reach Colab yet.";
      n.querySelector(".notice-body").textContent = `Retrying in ${Math.round(api.next_poll_in ?? 0)}s (waiting longer after each failure). ${api.error}`;
    }
  }

  let favicon = null;
  fetch("/favicon.svg?v=6").then((r) => r.text()).then((t) => { favicon = t; updateTitle(); }).catch(() => {});
  let iconKey = "";
  function updateTitle() {
    const items = state?.insights?.attention ?? [];
    const page = `${route[0].toUpperCase()}${route.slice(1)} · Colab Monitor`;
    document.title = items.length ? `(${items.length}) ${page}` : page;
    // The tab icon gets a red or amber dot, so a background tab still shows that something is wrong.
    const tone = items.some((a) => a.severity === "critical") ? "#e5484d" : items.length ? "#f5a524" : "";
    if (!favicon || tone === iconKey) return;
    iconKey = tone;
    const svg = tone ? favicon.replace("</svg>", `<circle cx="52" cy="12" r="12" fill="${tone}" stroke="#fff" stroke-width="3"/></svg>`) : favicon;
    document.querySelector('link[rel="icon"]').href = `data:image/svg+xml,${encodeURIComponent(svg)}`;
  }

  function renderShell() {
    renderApiNotice(state.api);
    updateTitle();
    const api = state.api;
    const live = state.sessions.filter((s) => LIVE.has(s.status));
    const orphans = live.filter((s) => s.status === "orphan").length;
    const navS = $("nav-sessions");
    navS.hidden = live.length === 0;
    navS.textContent = String(live.length);
    navS.classList.toggle("hot", orphans > 0);
    const navL = $("nav-logs");
    navL.hidden = state.logs.length === 0;
    navL.textContent = String(state.logs.length);

    const checked = api.updated_at ? rel(Date.parse(api.updated_at)) : "never";
    let cls = "dot", title, sub;
    if (!api.enabled) { title = "Local only"; sub = "Started with --no-api"; }
    else if (api.error) { cls = "dot bad"; title = "Colab unreachable"; sub = `Retrying in ${Math.round(api.next_poll_in ?? 0)}s`; }
    else { cls = "dot ok"; title = "Connected"; sub = `Checked ${checked} · every ${Math.round(api.interval)}s`; }
    $("conn-dot").className = cls;
    $("conn-title").textContent = title;
    $("conn-sub").textContent = sub;
    $("conn").title = api.error ?? `${title}. ${sub}`;
    for (const v of document.querySelectorAll(".app-version-only")) v.textContent = `Version ${state.version}`;
  }

  /* ---------- Overview ---------- */
  function renderOverview() {
    const api = state.api;
    const u = api.usage;
    const live = state.sessions.filter((s) => LIVE.has(s.status));
    const counts = { busy: 0, idle: 0, orphan: 0, stopping: 0 };
    for (const s of live) counts[s.status]++;

    let lede;
    if (!api.enabled) lede = "Showing local files only. Start without --no-api to see compute units and machines.";
    else if (!u) lede = "Waiting for the first check of your Colab account…";
    else if (!live.length) lede = `Nothing is running. You have ${fmt(u.balance)} compute units available.`;
    else lede = `${plural(live.length, "machine")} on your account, using ${fmt(u.rate_per_hour)} units an hour.` + (counts.idle ? ` ${counts.idle} ${counts.idle === 1 ? "is" : "are"} idle and still billing.` : "");
    $("lede").textContent = lede;

    renderAttention(state.insights);

    // Before Colab's first answer the numbers are coming, not unknown.
    const waiting = api.enabled && !u && !api.error;
    const none = () => (waiting ? skel("value") : "–");
    $("s-balance").replaceChildren(u ? fmt(u.balance) : none());
    $("s-rate").replaceChildren(...(u ? [fmt(u.rate_per_hour), el("span", { className: "unit", textContent: "/ hr" })] : [none()]));
    const spent = state.insights.spend.today;
    $("s-rate-foot").textContent = spent != null ? `${fmt(spent)} spent today` : "Units per hour, all machines";
    const runway = $("s-runway");
    runway.className = "stat-value";
    const h = state.insights.runway.hours;
    if (u && h != null) {
      runway.replaceChildren(...(h >= 48 ? [fmt(h / 24, 1), el("span", { className: "unit", textContent: "days" })] : [fmt(h, 1), el("span", { className: "unit", textContent: "hours" })]));
      if (h < state.insights.thresholds.runway_hours) runway.classList.add("bad"); else if (h < 48) runway.classList.add("warn");
      const empty = state.insights.runway.empty_at;
      $("s-runway-foot").textContent = empty ? `Runs out ${when(empty * 1000)}` : "At the current rate";
    } else {
      runway.replaceChildren(u ? "No burn" : none());
      $("s-runway-foot").textContent = u ? "Nothing is billing right now" : "At the current rate";
    }
    $("s-machines").replaceChildren(api.enabled && u ? String(live.length) : none());
    $("s-machines-foot").textContent = live.length
      ? [counts.busy && `${counts.busy} running`, counts.idle && `${counts.idle} idle`, counts.orphan && `${counts.orphan} orphan`, counts.stopping && `${counts.stopping} stopping`].filter(Boolean).join(" · ")
      : "On your account";

    const list = $("ov-sessions");
    if (!live.length) {
      list.replaceChildren(emptyState("li", ICON.chip, "No machines running", "Start a job and it appears here within a minute."));
    } else {
      replaceKeepingFocus(list, live.map((s) => el("li", { className: "clickable", dataset: { endpoint: s.endpoint } },
        el("span", { className: `ev-icon ${s.status === "busy" ? "run" : s.status === "orphan" ? "bad" : ""}` }, icon(ICON.chip)),
        el("div", { className: "grow" },
          el("a", { className: `title row-link${s.name ? "" : " faint"}`, href: sessionHref(s.endpoint), textContent: s.name ?? "Unknown machine", dataset: { key: s.endpoint } }),
          el("div", { className: "meta", textContent: machineMeta(s) })),
        s.metrics?.rate != null ? el("span", { className: "rate" }, ...rateParts(s.metrics)) : null,
        statusPill(s.status))));
    }
    renderJobs(state.insights.jobs);
    renderSpend(state.insights, live);
  }

  function machineMeta(s) {
    const m = s.metrics ?? {};
    return [
      hardware(s),
      s.running,
      m.uptime_s != null ? `up ${dur(m.uptime_s)}` : null,
      m.idle_s ? `idle ${dur(m.idle_s)}` : null,
    ].filter(Boolean).join(" · ") || s.endpoint;
  }

  function renderAttention(ins) {
    const items = ins.attention;
    const box = $("attention");
    box.hidden = items.length === 0;
    box.classList.toggle("critical", items.some((a) => a.severity === "critical"));
    $("attention-title").textContent = items.length === 1 ? "1 thing needs attention" : `${items.length} things need attention`;
    replaceKeepingFocus($("attention-list"), items.map((a) => {
      const actions = attentionLinks(a);
      if (a.command) actions.push(copyCommand(a.command, a.kind === "orphan" ? "Copy release command" : a.kind === "idle" ? "Copy stop command" : "Copy command", `cmd|${a.kind}|${a.subject}`));
      return el("li", { dataset: { kind: a.kind, subject: a.subject } },
        el("span", { className: `sev ${a.severity}` }),
        el("div", { className: "att-msg", textContent: a.message }),
        actions.length ? el("div", { className: "att-actions" }, ...actions) : null);
    }));
    $("orphan-hint").hidden = !items.some((a) => a.kind === "orphan");
  }
  // Where to look next for one item: the machine's details, the log, or the history.
  function attentionLinks(a) {
    const links = [];
    const machine = a.endpoint ? state.sessions.find((s) => s.endpoint === a.endpoint)
      : a.session ? state.sessions.find((s) => s.name === a.session && s.status !== "gone") : null;
    const key = (what) => ({ key: `${what}|${a.kind}|${a.subject}` });
    if (machine) links.push(el("a", { className: "btn sm", href: sessionHref(machine.endpoint), textContent: "Details", dataset: key("details") }));
    if (a.path) {
      const open = el("a", { className: "btn sm", href: "#/logs", textContent: a.kind === "failed" ? "Show error" : "Open log", dataset: key("log") });
      open.addEventListener("click", () => { openLog(a.path); jumpToError = a.kind === "failed"; });
      links.push(open);
    } else if (a.kind === "failed" && a.session) {
      const open = el("a", { className: "btn sm", href: "#/history", textContent: "View history", dataset: key("history") });
      open.addEventListener("click", () => { selectedHistory = a.session; store.set("history", a.session); });
      links.push(open);
    }
    return links;
  }

  const openLog = (path) => { selectedLog = path; store.set("log", path); };
  const JOB_STATE = {
    failed: ["Failed", "bad"],
    stalled: ["Silent", "warn"],
    finished: ["Finished", "ok"],
    running: ["Running", "run"],
    quiet: ["No new output", "muted"],
  };
  const jobBadge = (j) => {
    const [label, tone] = JOB_STATE[j.state] ?? [j.state, "muted"];
    return el("span", { className: `badge ${tone}`, textContent: j.state === "stalled" ? `Silent ${dur(j.silent_s)}` : label });
  };
  function renderJobs(jobs) {
    const list = $("ov-jobs");
    if (!jobs.length) {
      list.replaceChildren(emptyState("li", ICON.file, "No job logs", `Send a job's output to ${shortDir(state.log_dirs[0] ?? "~/colab-runs")} to follow it here.`));
      return;
    }
    const newest = [...jobs].sort((a, b) => (a.silent_s ?? Infinity) - (b.silent_s ?? Infinity)).slice(0, 6);
    replaceKeepingFocus(list, newest.map((j) => {
      const pct = j.progress != null ? Math.floor(j.progress * 100) : null;  // rounded down, like tqdm
      const readings = [j.speed, ...Object.entries(j.metrics ?? {}).slice(0, 3).map(([k, v]) => `${k} ${num(v)}`)];
      const facts = [
        j.session && `on ${j.session}`,
        ...(pct == null && !readings.some(Boolean) ? ["No progress printed yet"] : readings),
        j.silent_s != null && !j.stalled && `updated ${j.silent_s < 5 ? "just now" : `${dur(j.silent_s)} ago`}`,
      ].filter(Boolean);
      const name = el("a", { className: "job-name", href: "#/logs", textContent: j.name, title: tildify(j.path), dataset: { key: j.path } });
      name.addEventListener("click", () => openLog(j.path));
      const failed = j.state === "failed";
      let err = null;
      if (j.last_error) {
        // Only an error that ended the job is a link to it; an earlier one the job survived is a note.
        err = el(failed ? "a" : "div", { className: `job-err${failed ? "" : " old"}`, textContent: j.last_error, title: failed ? "Show this error in the log" : `Earlier error: ${j.last_error}` });
        if (failed) { err.href = "#/logs"; err.addEventListener("click", () => { openLog(j.path); jumpToError = true; }); }
      }
      const spark = el("span", { className: "spark", dataset: { path: j.path } });
      paintSpark(spark, j.path);
      return el("li", { dataset: { job: j.name, state: j.state } },
        el("span", { className: `ev-icon ${failed ? "bad" : j.state === "finished" ? "ok" : j.stalled ? "" : "run"}` }, icon(failed ? ICON.err : j.state === "finished" ? ICON.check : ICON.file)),
        el("div", { className: "grow" },
          el("div", { className: "job-top" },
            el("div", { className: "title" }, name),
            spark,
            jobBadge(j),
            pct != null ? el("span", { className: "job-pct", textContent: j.eta_s && j.state === "running" ? `${pct}% · ${dur(j.eta_s)} left` : `${pct}%` }) : null),
          el("div", { className: "meta", textContent: facts.join(" · ") }),
          pct != null ? el("div", { className: `bar ${failed ? "bad" : j.state === "finished" ? "ok" : ""}`, attrs: { role: "progressbar", "aria-valuenow": String(pct), "aria-valuemin": "0", "aria-valuemax": "100", "aria-label": `${j.name} progress` } },
            el("span", { style: `width:${Math.min(100, Math.max(0, pct))}%` })) : null,
          err));
    }));
    refreshSparks(newest.map((j) => j.path));
  }

  function renderSpend(ins, live) {
    const s = ins.spend;
    const hours = Object.entries(ins.machine_hours_7d).sort(([a], [b]) => a.localeCompare(b));
    const runs = ins.runs["24h"];
    const rows = [
      ["Today", fmt(s.today)],
      ["Last 7 days", fmt(s["7d"])],
      ["Last 30 days", fmt(s["30d"])],
      ["Spent while idle", ins.idle_cost ? withEstimate(fmt(ins.idle_cost), live.some((s) => s.metrics?.idle_cost && s.metrics.rate_estimated)) : "–"],
      ["Machine hours, 7 days", hours.length ? hours.map(([k, v]) => `${k} ${fmt(v, 1)}`).join(" · ") : "–"],
      ["Runs, 24 hours", runs.ok + runs.failed ? `${runs.ok} finished · ${runs.failed} failed` : "–"],
    ];
    $("ov-spend").replaceChildren(...rows.flatMap(([k, v]) => [el("dt", { textContent: k }), el("dd", {}, ...[v].flat())]));
    // Spend counts only what the dashboard saw, so say when that started.
    const since = s.measured_since;
    $("spend-since").textContent = since && since * 1000 > Date.now() - 29 * 86400e3 ? `Compute units, measured since ${when(since * 1000)}` : "Compute units used";
  }

  const EVENT = {
    session_created: ["Session created", "ok", ICON.plus],
    session_terminated: ["Session ended", "", ICON.stop],
    execution: ["Code executed", "run", ICON.play],
    automation: ["Automation", "run", ICON.play],
    file_operation: ["File operation", "", ICON.file],
    repl_started: ["REPL started", "run", ICON.play],
    console_started: ["Console started", "run", ICON.play],
    drive_auth_needed: ["Drive sign-in requested", "", ICON.dot],
    drive_auth_success: ["Drive mounted", "ok", ICON.check],
    stdin_request: ["Input requested", "", ICON.dot],
    input_reply: ["Input sent", "", ICON.dot],
  };
  // History details shown as tags, with the CLI's raw values in plain words.
  const TAG_LABELS = {
    accelerator: { NONE: "CPU" },
    machine_shape: { STANDARD: "Standard", HIGH_RAM: "High-RAM" },
    reason: { user_requested: "Stopped", run_completed: "Run finished", run_failed: "Run failed", pruned: "Gone from Colab" },
    via: {},
  };
  const eventInfo = (ev) => {
    const [title, tone, ic] = EVENT[ev.type] ?? [(ev.type ?? "event").replaceAll("_", " "), "", ICON.dot];
    return ev.error ? [title, "bad", ICON.err] : [title, tone, ic];
  };

  let activityKey = null;
  async function refreshActivity() {
    try {
      const data = await getJSON("/api/activity?limit=8");
      const key = JSON.stringify(data.events);
      if (key === activityKey) return;
      activityKey = key;
      const list = $("ov-activity");
      if (!data.events.length) {
        list.replaceChildren(emptyState("li", ICON.clock, "No activity yet", "Events appear as you use the colab CLI."));
        return;
      }
      list.replaceChildren(...data.events.map((ev) => {
        const [title, tone, ic] = eventInfo(ev);
        const t = ev.timestamp ? Date.parse(ev.timestamp) : null;
        return el("li", {},
          el("span", { className: `ev-icon ${tone}` }, icon(ic)),
          el("div", { className: "grow" },
            el("div", { className: "title", textContent: title }),
            el("div", { className: "meta", textContent: ev.error ? `${ev.session} · ${ev.error}` : ev.session })),
          el("span", { className: "time", textContent: t ? rel(t) : "", title: t ? new Date(t).toLocaleString() : "" }));
      }));
    } catch {}
  }

  /* ---------- Metric charts ---------- */
  const seriesCache = new Map();  // "points|path" -> { at, series }
  async function loadSeries(path, points, maxAge = 10e3) {
    const key = `${points}|${path}`;
    const hit = seriesCache.get(key);
    if (hit && Date.now() - hit.at < maxAge) return hit.series;
    const data = await getJSON(`/api/metrics?points=${points}&path=${encodeURIComponent(path)}`);
    seriesCache.set(key, { at: Date.now(), series: data.series });
    return data.series;
  }
  const xLabel = (p) => (p[1] != null ? `step ${p[1].toLocaleString()}` : `line ${p[0].toLocaleString()}`);
  function trend(s) {
    const first = s.points[0][2], last = s.points.at(-1)[2];
    return `${s.name} ${num(first)} → ${num(last)} over ${plural(s.count, "reading")}`;
  }

  // A small line of a job's first metric (loss when there is one), next to its progress.
  function paintSpark(span, path) {
    const s = seriesCache.get(`60|${path}`)?.series?.[0];
    span.hidden = !s;
    if (!s) { span.replaceChildren(); return; }
    const W = 72, H = 18, vs = s.points.map((p) => p[2]);
    const lo = Math.min(...vs), hi = Math.max(...vs), n = s.points.length;
    const d = s.points.map((p, i) => `${i ? "L" : "M"}${((i / (n - 1)) * (W - 4) + 2).toFixed(1)},${(hi === lo ? H / 2 : H - 3 - ((p[2] - lo) / (hi - lo)) * (H - 6)).toFixed(1)}`).join("");
    const svg = sv("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, class: "spark-svg", "aria-hidden": "true" }, null);
    svg.append(sv("path", { d, class: "spark-line" }));
    span.replaceChildren(svg);  // the latest value is already in the job's line; this shows the trend
    span.title = trend(s);
    span.setAttribute("aria-label", trend(s));
    span.setAttribute("role", "img");
  }
  async function refreshSparks(paths) {
    for (const path of paths) {
      try { await loadSeries(path, 60, 15e3); } catch { continue; }
      for (const span of document.querySelectorAll(".spark")) if (span.dataset.path === path) paintSpark(span, path);
    }
  }

  // A metric over the course of a log, with axes and a hover readout.
  function drawMetricChart(box, s, height = 150) {
    const W = box.clientWidth || 600, H = height;
    const m = { t: 12, r: 64, b: 24, l: 52 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const pts = s.points;
    let lo = Math.min(...pts.map((p) => p[2])), hi = Math.max(...pts.map((p) => p[2]));
    if (hi - lo < 1e-12) { hi += Math.abs(hi) * 0.1 || 1; lo -= Math.abs(lo) * 0.1 || 1; }
    const step = niceStep(hi - lo, 3);
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    const x0 = pts[0][0], x1 = Math.max(pts.at(-1)[0], x0 + 1);
    const X = (x) => m.l + ((x - x0) / (x1 - x0)) * iw;
    const Y = (v) => m.t + ih - ((v - lo) / (hi - lo)) * ih;
    const svg = sv("svg", { viewBox: `0 0 ${W} ${H}`, class: "metric-svg", role: "img", "aria-label": trend(s) });
    svg.style.height = `${H}px`;
    const grid = sv("g", { class: "chart-grid" }), axis = sv("g", { class: "chart-axis" });
    for (let v = lo; v <= hi + step / 2; v += step) {
      const y = Math.round(Y(v)) + 0.5;
      grid.append(sv("line", { x1: m.l, x2: m.l + iw, y1: y, y2: y }));
      axis.append(sv("text", { x: m.l - 10, y: y + 4, "text-anchor": "end" }, num(v)));
    }
    axis.append(sv("text", { x: m.l, y: H - 6, "text-anchor": "start" }, xLabel(pts[0])));
    axis.append(sv("text", { x: m.l + iw, y: H - 6, "text-anchor": "end" }, xLabel(pts.at(-1))));
    const d = pts.map((p, i) => `${i ? "L" : "M"}${X(p[0]).toFixed(1)},${Y(p[2]).toFixed(1)}`).join("");
    const last = pts.at(-1);
    const cross = sv("line", { class: "chart-cross", y1: m.t, y2: m.t + ih, visibility: "hidden" });
    const dot = sv("circle", { class: "chart-end", r: 3.5, visibility: "hidden" });
    const hit = sv("rect", { class: "chart-hit", x: m.l, y: m.t, width: iw, height: ih + 1 });
    svg.append(grid, axis, sv("path", { class: "chart-line", d }), sv("circle", { class: "chart-end", cx: X(last[0]), cy: Y(last[2]), r: 3.5 }),
      sv("text", { class: "chart-end-label", x: X(last[0]) + 8, y: Y(last[2]) + 4 }, num(last[2])), cross, dot, hit);
    const tip = el("div", { className: "tooltip", hidden: true });
    box.replaceChildren(svg, tip);
    const show = (evt) => {
      const rect = svg.getBoundingClientRect();
      const x = x0 + ((((evt.clientX - rect.left) / rect.width) * W - m.l) / iw) * (x1 - x0);
      let best = pts[0];
      for (const p of pts) if (Math.abs(p[0] - x) < Math.abs(best[0] - x)) best = p;
      const cx = X(best[0]), cy = Y(best[2]);
      cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
      dot.setAttribute("cx", cx); dot.setAttribute("cy", cy); dot.setAttribute("visibility", "visible");
      tip.replaceChildren(
        el("div", { className: "tip-label", textContent: best[1] != null ? `step ${best[1].toLocaleString()} · line ${best[0].toLocaleString()}` : `line ${best[0].toLocaleString()}` }),
        el("div", { className: "tip-row" }, el("span", { className: "key" }), `${s.name} `, el("span", { className: "tip-val", textContent: num(best[2]) })));
      tip.hidden = false;
      const scale = rect.width / W, half = tip.offsetWidth / 2;
      tip.style.left = `${Math.min(Math.max(cx * scale, half + 4), box.clientWidth - half - 4)}px`;
      const below = cy * scale - tip.offsetHeight - 10 < 0;
      tip.style.top = `${below ? cy * scale + 12 : cy * scale - 6}px`;
      tip.style.transform = below ? "translate(-50%, 0)" : "translate(-50%, -100%)";
    };
    const hide = () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("pointerdown", show);
    hit.addEventListener("pointerleave", hide);
  }

  // Chips to pick a metric, and the chart of the picked one.
  function renderMetricPanel(seg, box, caption, series) {
    const s = series.find((x) => x.name === selectedMetric) ?? series[0];
    seg.hidden = series.length < 2;  // with one metric, the caption names it
    seg.replaceChildren(...series.map((x) => el("button", { type: "button", textContent: x.name, dataset: { metric: x.name }, attrs: { "aria-pressed": String(x === s) } })));
    caption.textContent = trend(s);
    drawMetricChart(box, s);
  }

  /* ---------- Chart ---------- */
  function niceStep(span, count) {
    const raw = span / Math.max(1, count);
    const mag = 10 ** Math.floor(Math.log10(raw));
    const n = raw / mag;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
  }
  const RANGE_MS = { "1h": 3600e3, "24h": 86400e3, "7d": 7 * 86400e3, "30d": 30 * 86400e3 };
  const RANGE_LABEL = { "1h": "the last hour", "24h": "the last 24 hours", "7d": "the last 7 days", "30d": "the last 30 days" };
  let axisSpan = 0;
  const timeFmt = (ms) => {
    const d = new Date(ms);
    return axisSpan < 2 * 86400e3
      ? d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
      : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  };
  const fullTime = (ms) => new Date(ms).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  const valueFmt = (v) => (measure === "rate" ? `${fmt(v)} / hr` : fmt(v));

  function drawChart() {
    const svg = $("chart");
    const interval = state?.config?.interval ?? 60;
    const points = (lastUsage ?? []).map((p) => ({ t: p.t * 1000, v: measure === "rate" ? p.rate : p.balance })).filter((p) => p.v != null);
    const enough = points.length >= 2;
    svg.style.display = enough ? "" : "none";
    $("chart-empty").hidden = enough;
    $("tooltip").hidden = true;
    renderChartTable();

    // When the dashboard hasn't run for the whole range, say what the chart actually covers.
    const partial = points.length > 0 && points[0].t > Date.now() - RANGE_MS[range] + 60e3;
    const span = partial ? `since ${fullTime(points[0].t)}` : RANGE_LABEL[range];
    if (points.length) {
      const first = points[0].v, last = points.at(-1).v;
      if (measure === "balance") {
        const d = last - first;
        const note = Math.abs(d) < 0.005 ? `No change ${partial ? "" : "over "}${span}` : `${d > 0 ? "+" : "−"}${fmt(Math.abs(d))} units ${partial ? "" : "over "}${span}`;
        $("chart-caption").textContent = `${note} · Colab updates the balance periodically`;
      } else {
        $("chart-caption").textContent = `Peak ${fmt(Math.max(...points.map((p) => p.v)))} / hr ${partial ? "" : "over "}${span}`;
      }
      const d = (lastUsage.at(-1).balance ?? 0) - (lastUsage[0].balance ?? 0);
      $("s-balance-foot").replaceChildren(
        Math.abs(d) < 0.005 ? "No change" : el("span", { className: "delta down", textContent: `${d > 0 ? "+" : "−"}${fmt(Math.abs(d))}` }),
        partial ? ` ${span}` : ` over ${span.replace("the last ", "")}`);
    } else {
      $("chart-caption").textContent = `A sample is saved every ${Math.round(interval)}s while the dashboard runs`;
      $("s-balance-foot").textContent = "Balance";
    }
    if (!enough) {
      $("chart-empty-desc").textContent = state?.config?.api_enabled === false
        ? "The chart needs Colab checks. Start the dashboard without --no-api."
        : `A point is saved every ${Math.round(interval)}s. The line appears after the second check.`;
      svg.replaceChildren();
      return;
    }

    const W = svg.clientWidth || 800, H = 300;
    const m = { t: 18, r: 72, b: 30, l: 52 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const now = Date.now();
    // The axis starts at the first sample, so a dashboard started recently still gets a readable chart.
    const x0 = Math.max(points[0].t, now - RANGE_MS[range]), x1 = Math.max(now, points.at(-1).t);
    axisSpan = x1 - x0;
    let lo = Math.min(...points.map((p) => p.v)), hi = Math.max(...points.map((p) => p.v));
    if (measure === "rate") lo = 0;
    if (hi - lo < 1e-9) { hi += 1; lo = measure === "rate" ? 0 : lo - 1; }
    const step = niceStep(hi - lo, 4);
    // As many decimals as the step needs: 0.02 needs 2, 2.5 needs 1, 5 needs none.
    let places = 0;
    while (places < 6 && Math.abs(step * 10 ** places - Math.round(step * 10 ** places)) > 1e-6) places++;
    lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step) * step;
    const X = (t) => m.l + ((t - x0) / (x1 - x0)) * iw;
    const Y = (v) => m.t + ih - ((v - lo) / (hi - lo)) * ih;

    const grid = sv("g", { class: "chart-grid" });
    const axis = sv("g", { class: "chart-axis" });
    for (let v = lo; v <= hi + step / 2; v += step) {
      const y = Math.round(Y(v)) + 0.5;
      grid.append(sv("line", { x1: m.l, x2: m.l + iw, y1: y, y2: y }));
      axis.append(sv("text", { x: m.l - 10, y: y + 4, "text-anchor": "end" }, v.toLocaleString(undefined, { minimumFractionDigits: places, maximumFractionDigits: places })));
    }
    const ticks = Math.max(2, Math.min(6, Math.floor(iw / 120)));
    for (let i = 0; i <= ticks; i++) {
      const t = x0 + ((x1 - x0) * i) / ticks;
      axis.append(sv("text", { x: X(t), y: m.t + ih + 20, "text-anchor": i === 0 ? "start" : i === ticks ? "end" : "middle" }, timeFmt(t)));
    }

    // Break the line where the dashboard wasn't running instead of drawing across the gap.
    const gap = Math.max(3 * interval * 1000, 5 * 60e3);
    const segs = [[points[0]]];
    for (let i = 1; i < points.length; i++) {
      if (points[i].t - points[i - 1].t > gap) segs.push([]);
      segs.at(-1).push(points[i]);
    }
    const base = m.t + ih;
    const area = sv("g"), line = sv("g");
    for (const seg of segs) {
      // The rate holds between checks, so draw it as steps; the balance is drawn point to point.
      const d = seg.map((p, i) => !i ? `M${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`
        : measure === "rate" ? `H${X(p.t).toFixed(1)}V${Y(p.v).toFixed(1)}`
        : `L${X(p.t).toFixed(1)},${Y(p.v).toFixed(1)}`).join("");
      if (seg.length > 1) area.append(sv("path", { class: "chart-area", d: `${d}L${X(seg.at(-1).t).toFixed(1)},${base}L${X(seg[0].t).toFixed(1)},${base}Z` }));
      line.append(sv("path", { class: "chart-line", d: seg.length > 1 ? d : `${d}l0.01,0` }));
    }
    // A mark on the time axis where a machine started or stopped, which explains most rate steps.
    const marks = sv("g", { class: "chart-marks" });
    const events = lastEvents.map((e) => ({ ...e, ms: e.t * 1000 })).filter((e) => e.ms >= x0 && e.ms <= x1);
    for (const e of events) {
      const x = Math.round(X(e.ms)) + 0.5;
      const g = sv("g", { class: `chart-mark ${e.kind}` });
      g.append(sv("title", {}, `${e.name} ${e.kind === "start" ? "started" : "stopped"} (${e.hardware}) · ${fullTime(e.ms)}`),
        sv("line", { x1: x, x2: x, y1: m.t, y2: base }),
        e.kind === "start" ? sv("path", { d: `M${x - 4.5},${base + 1}L${x + 4.5},${base + 1}L${x},${base - 6}Z` })
          : sv("rect", { x: x - 3.5, y: base - 6, width: 7, height: 7, rx: 1 }));
      marks.append(g);
    }
    const lastP = points.at(-1);
    const end = sv("circle", { class: "chart-end", cx: X(lastP.t), cy: Y(lastP.v), r: 4 });
    const endLabel = sv("text", { class: "chart-end-label", x: X(lastP.t) + 10, y: Y(lastP.v) + 4 }, fmt(lastP.v));
    const cross = sv("line", { class: "chart-cross", y1: m.t, y2: base, visibility: "hidden" });
    const hoverDot = sv("circle", { class: "chart-end", r: 4, visibility: "hidden" });
    const hit = sv("rect", { class: "chart-hit", x: m.l, y: m.t, width: iw, height: ih + 1 });
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("aria-label", `${measure === "rate" ? "Usage rate" : "Compute unit balance"} over ${span}; latest ${valueFmt(lastP.v)}`);
    // The area under the line fades to the axis.
    const defs = sv("defs");
    const fade = sv("linearGradient", { id: "usage-fill", x1: 0, y1: 0, x2: 0, y2: 1 });
    fade.append(sv("stop", { offset: "0%", class: "chart-fill-top" }), sv("stop", { offset: "100%", class: "chart-fill-bottom" }));
    defs.append(fade);
    svg.replaceChildren(defs, grid, area, marks, line, axis, cross, end, endLabel, hoverDot, hit);

    const tip = $("tooltip");
    const show = (evt) => {
      const rect = svg.getBoundingClientRect();
      const px = ((evt.clientX - rect.left) / rect.width) * W;
      const t = x0 + ((px - m.l) / iw) * (x1 - x0);
      let best = points[0];
      for (const p of points) if (Math.abs(p.t - t) < Math.abs(best.t - t)) best = p;
      const cx = X(best.t), cy = Y(best.v);
      cross.setAttribute("x1", cx); cross.setAttribute("x2", cx); cross.setAttribute("visibility", "visible");
      hoverDot.setAttribute("cx", cx); hoverDot.setAttribute("cy", cy); hoverDot.setAttribute("visibility", "visible");
      // Machines that started or stopped within a few pixels of the pointer.
      const near = events.filter((e) => Math.abs(X(e.ms) - px) <= 8);
      tip.replaceChildren(
        el("div", { className: "tip-label", textContent: fullTime(best.t) }),
        el("div", { className: "tip-row" }, el("span", { className: "key" }), `${measure === "rate" ? "Usage rate" : "Balance"} `, el("span", { className: "tip-val", textContent: valueFmt(best.v) })),
        ...near.map((e) => el("div", { className: `tip-event ${e.kind}`, textContent: `${e.name} ${e.kind === "start" ? "started" : "stopped"} · ${e.hardware} · ${new Date(e.ms).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}` })));
      tip.hidden = false;
      const scale = rect.width / W;
      // Keep the tooltip inside the card: clamp sideways, and flip below the point near the top.
      const wrap = $("chart-wrap"), off = rect.left - wrap.getBoundingClientRect().left;
      const half = tip.offsetWidth / 2, px2 = cx * scale + off, py = cy * scale + 8;
      tip.style.left = `${Math.min(Math.max(px2, half + 4), wrap.clientWidth - half - 4)}px`;
      const below = py - tip.offsetHeight - 10 < 0;
      tip.style.top = `${below ? py + 12 : py - 6}px`;
      tip.style.transform = below ? "translate(-50%, 0)" : "translate(-50%, -100%)";
    };
    const hide = () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); hoverDot.setAttribute("visibility", "hidden"); };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("pointerdown", show);
    hit.addEventListener("pointerleave", hide);
  }

  function renderChartTable() {
    if ($("chart-table").hidden) return;
    const rows = (lastUsage ?? []).slice(-60).reverse();
    $("chart-table-body").replaceChildren(...(rows.length ? rows.map((p) => el("tr", {},
      el("td", { textContent: fullTime(p.t * 1000) }),
      el("td", { className: "num", textContent: fmt(p.balance) }),
      el("td", { className: "num", textContent: fmt(p.rate) }))) : [el("tr", {}, el("td", { colSpan: 3, className: "faint", textContent: "No samples yet." }))]));
  }
  $("table-toggle").addEventListener("click", () => {
    const t = $("chart-table");
    t.hidden = !t.hidden;
    $("table-toggle").textContent = t.hidden ? "View as table" : "Hide table";
    renderChartTable();
  });

  async function refreshUsage() {
    try {
      const data = await getJSON(`/api/usage?range=${range}`);
      lastUsage = data.points;
      lastEvents = data.events ?? [];
      drawChart();
    } catch {}
  }
  function setPressed(groupId, attr, value) {
    for (const b of $(groupId).querySelectorAll("button")) b.setAttribute("aria-pressed", String(b.dataset[attr] === value));
  }
  $("measure-seg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    measure = b.dataset.measure; store.set("measure", measure); setPressed("measure-seg", "measure", measure); drawChart();
  });
  $("range-seg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    range = b.dataset.range; store.set("range", range); setPressed("range-seg", "range", range); refreshUsage();
  });
  setPressed("measure-seg", "measure", measure);
  setPressed("range-seg", "range", range);
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (route === "overview") drawChart();
      if (route === "logs") refreshLogMetrics();
      if (selectedSession) refreshDrawerData();
    }, 120);
  });

  /* ---------- Sessions page ---------- */
  function renderSessions() {
    const counts = { all: state.sessions.length, busy: 0, idle: 0, orphan: 0, gone: 0 };
    for (const s of state.sessions) if (s.status in counts) counts[s.status]++;
    for (const n of document.querySelectorAll("#status-seg [data-n]")) n.textContent = String(counts[n.dataset.n] ?? 0);
    const q = $("session-search").value.trim().toLowerCase();
    const rows = state.sessions.filter((s) =>
      (statusFilter === "all" || s.status === statusFilter) &&
      (!q || [s.name, s.accelerator, hardware(s), s.endpoint, s.running].some((v) => (v ?? "").toLowerCase().includes(q))));
    replaceKeepingFocus($("sessions-body"), rows.map((s) => {
      const t = lastRun(s);
      const hint = (STATUS[s.status] ?? [])[1];
      const m = s.metrics ?? {};
      return el("tr", { className: "clickable", dataset: { endpoint: s.endpoint } },
        el("td", { className: `name${s.name ? "" : " unknown"}`, title: [s.name, s.endpoint].filter(Boolean).join("\n") },
          el("div", {}, el("a", { className: "row-link", href: sessionHref(s.endpoint), textContent: s.name ?? "Unknown", dataset: { key: s.endpoint } })),
          el("div", { className: "ep", textContent: s.endpoint ?? "" })),
        el("td", { className: "st", title: hint ?? "" }, statusPill(s.status), hint ? el("span", { className: "status-hint", textContent: hint }) : null),
        el("td", { className: "meta-cell", dataset: { label: "Hardware" } }, hardware(s) ? el("span", { className: "tag", textContent: hardware(s) }) : "–"),
        el("td", { className: `num meta-cell${s.metrics?.uptime_s != null ? "" : " empty-val"}`, dataset: { label: "Uptime" }, textContent: dur(s.metrics?.uptime_s),
          title: s.metrics?.idle_s ? `Idle for ${dur(s.metrics.idle_s)}` : "" }),
        el("td", { className: `num meta-cell${m.idle_s ? "" : " empty-val"}${s.status === "idle" && m.idle_s >= state.insights.thresholds.idle_minutes * 60 ? " warn" : ""}`, dataset: { label: "Idle" }, textContent: m.idle_s ? dur(m.idle_s) : "–",
          title: m.idle_cost ? `About ${fmt(m.idle_cost)} units spent while idle` : "" }),
        el("td", { className: `num meta-cell${m.rate != null ? "" : " empty-val"}`, dataset: { label: "Rate" } }, ...rateParts(m)),
        el("td", { className: `num meta-cell${m.cost != null ? "" : " empty-val"}`, dataset: { label: "Cost" }, title: m.cost != null ? "Compute units used since the machine started" : "" },
          ...(m.cost != null ? withEstimate(fmt(m.cost), m.rate_estimated) : ["–"])),
        el("td", { className: `job meta-cell${s.running ? "" : " empty-val"}`, dataset: { label: "Job" }, textContent: s.running ?? "–", title: s.running ?? "" }),
        el("td", { className: `sub meta-cell col-last${t ? "" : " empty-val"}`, dataset: { label: "Last run" }, textContent: t ? `${baseName(s.last_execution.source) || "code"} · ${rel(t)}` : "–", title: t ? `${s.last_execution.source ?? ""}\n${s.last_execution.time}` : "" }));
    }));
    const empty = rows.length === 0;
    $("sessions-table").hidden = empty;
    $("sessions-empty").hidden = !empty;
    const anySessions = state.sessions.length > 0;
    $("sessions-empty-title").textContent = anySessions ? "No matching sessions" : "No machines running";
    $("sessions-empty-desc").textContent = anySessions ? "Try another status filter or search." : "Nothing is using compute units right now.";
    $("sessions-snippet").hidden = anySessions;
  }
  $("status-seg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    statusFilter = b.dataset.status; setPressed("status-seg", "status", statusFilter); renderSessions();
  });
  $("session-search").addEventListener("input", () => state && renderSessions());
  document.addEventListener("keydown", (e) => {
    if (e.key !== "/" || e.metaKey || e.ctrlKey || /input|textarea|select/i.test(document.activeElement?.tagName ?? "")) return;
    const target = route === "sessions" ? $("session-search") : route === "logs" ? $("log-filter") : null;
    if (target) { e.preventDefault(); target.focus(); }
  });

  /* ---------- Logs page ---------- */
  let logLines = [];
  let logKey = null;
  function renderLogList() {
    const pane = $("log-list");
    if (!state.logs.find((l) => l.path === selectedLog)) {
      // Nothing chosen yet: open the most recently updated log.
      const newest = state.logs.reduce((a, b) => ((b.mtime ?? 0) > (a?.mtime ?? 0) ? b : a), null);
      selectedLog = newest?.path ?? null;
    }
    const dirs = state.log_dirs.map(shortDir);
    $("logs-lede").title = state.log_dirs.join("\n");
    $("logs-lede").textContent = `Live output from *.log, *.out and *.err files in ${dirs.join(", ") || "your log folders"}.`;
    if (!state.logs.length) {
      pane.replaceChildren(emptyState("div", ICON.terminal, "No log files", `Send a job's output to ${dirs[0] ?? "~/colab-runs"}.`));
      return;
    }
    const jobs = Object.fromEntries(state.insights.jobs.map((j) => [j.path, j]));
    const statusOf = Object.fromEntries(state.sessions.filter((s) => s.name && s.status !== "gone").map((s) => [s.name, s.status]));
    replaceKeepingFocus(pane, state.logs.map((l) => {
      const j = jobs[l.path];
      const machine = j?.session ? statusOf[j.session] ?? "gone" : null;
      const pct = j?.progress != null ? `${Math.floor(j.progress * 100)}%` : null;
      const b = el("button", { type: "button", dataset: { key: l.path, state: j?.state ?? "" }, attrs: { "aria-current": String(l.path === selectedLog) } },
        el("div", { className: "pl-row" },
          machine ? el("span", { className: `pl-dot ${machine}`, title: `On ${j.session} (${(STATUS[machine] ?? [machine])[0]})` }) : null,
          el("div", { className: "pl-title", textContent: l.name }),
          j && ["failed", "stalled", "finished"].includes(j.state) ? jobBadge(j) : null),
        el("div", { className: "pl-meta", textContent: l.exists ? [pct, j?.session && `on ${j.session}`, bytes(l.size), rel(l.mtime * 1000)].filter(Boolean).join(" · ") : "missing" }));
      b.addEventListener("click", () => { if (selectedLog !== l.path) showLog(l.path); });
      return b;
    }));
  }
  // Switch the Logs page to another file.
  function showLog(path) {
    selectedLog = path; store.set("log", path); logKey = null; logLines = []; errIndex = -1;
    $("log-view").replaceChildren(el("div", { className: "term-empty" }, icon(ICON.spinner), "Loading…"));
    renderLogList(); refreshLog(true);
  }
  // The same rule as the server's metrics.py: exceptions, tracebacks, out of memory, and lines that
  // start with error, fatal, or failed. Metric names such as val_error are not errors.
  const isErrorLine = (line) =>
    /Traceback \(most recent call last\)|\b[A-Z]\w*(?:Error|Exception)\b/.test(line) ||
    /\bout of memory\b|^\s*(?:error|fatal|failed)\b/i.test(line);
  const WARN = /(warn|deprecat)/i;
  function logStatusRight() {
    const entry = state?.logs.find((l) => l.path === selectedLog);
    $("term-right").textContent = entry?.exists ? `${bytes(entry.size)} · updated ${rel(entry.mtime * 1000)}` : "";
  }
  function paintLog(forceBottom = false) {
    const view = $("log-view");
    const q = $("log-filter").value;
    const ql = q.toLowerCase();
    const shown = [];
    logLines.forEach((line, i) => { if (!ql || line.toLowerCase().includes(ql)) shown.push([i + 1, line]); });
    if (!selectedLog) {
      view.replaceChildren(el("div", { className: "term-empty", textContent: "Pick a log file on the left." }));
    } else if (!shown.length) {
      view.replaceChildren(el("div", { className: "term-empty", textContent: logLines.length ? `No lines match “${q}”.` : "Empty file. Waiting for output…" }));
    } else {
      view.replaceChildren(...shown.map(([n, line]) => {
        const row = el("div", { className: `tl${isErrorLine(line) ? " err" : WARN.test(line) ? " warn" : ""}` }, el("span", { className: "ln", textContent: String(n) }));
        const body = el("span");
        if (ql) {
          const low = line.toLowerCase();
          let i = 0;
          for (let j = low.indexOf(ql); j !== -1; j = low.indexOf(ql, i)) {
            body.append(line.slice(i, j), el("mark", { textContent: line.slice(j, j + q.length) }));
            i = j + q.length;
          }
          body.append(line.slice(i));
        } else body.textContent = line || " ";
        row.append(body);
        return row;
      }));
    }
    const errs = logLines.filter((l) => isErrorLine(l)).length;
    $("term-left").textContent = selectedLog ? `${plural(logLines.length, "line")}${q ? ` · ${shown.length} shown` : ""}${errs ? ` · ${plural(errs, "error line")}` : ""}` : "";
    const jump = $("err-jump");
    jump.hidden = !view.querySelector(".tl.err");
    jump.textContent = "Go to error";
    if (jumpToError && !jump.hidden) { jumpToError = false; errIndex = -1; goToError(); }
    else if ($("follow").checked || forceBottom) pinLog();
    logStatusRight();
  }
  // Each press shows the error before the one shown last, starting from the end of the log.
  let errIndex = -1;
  function goToError() {
    const rows = [...$("log-view").querySelectorAll(".tl.err")];
    if (!rows.length) return;
    errIndex = errIndex <= 0 ? rows.length - 1 : errIndex - 1;
    const row = rows[errIndex];
    $("follow").checked = false;  // stay on the error while new lines arrive
    for (const r of rows) r.classList.remove("flash");
    row.classList.add("flash");
    centerError();
    // Lines grow when the log font arrives, and the metric chart can open above the log: center again.
    document.fonts?.ready.then(centerError);
    $("err-jump").textContent = rows.length > 1 ? `Go to error (${errIndex + 1} of ${rows.length})` : "Go to error";
  }
  // Keep the error that was jumped to a third of the way down the view, unless following resumed.
  function centerError() {
    const view = $("log-view"), row = view.querySelector(".tl.flash");
    if (!row || $("follow").checked) return;
    pinning = true;  // not a scroll by the reader
    view.scrollTop += row.getBoundingClientRect().top - view.getBoundingClientRect().top - view.clientHeight / 3;
    requestAnimationFrame(() => { pinning = false; });
  }
  $("err-jump").addEventListener("click", goToError);
  // The log's box changes size when the chart above it opens or the window resizes. Keep what the
  // reader was looking at in view: the end while following, or the error that was jumped to.
  const keepLogPlace = () => { if ($("follow").checked) pinLog(); else centerError(); };
  new ResizeObserver(keepLogPlace).observe($("log-view"));

  async function refreshLogMetrics() {
    const panel = $("log-metrics");
    if (!selectedLog) { panel.hidden = true; return; }
    const path = selectedLog;
    let series;
    try { series = await loadSeries(path, 300, 5e3); } catch { return; }
    if (path !== selectedLog) return;
    const wasHidden = panel.hidden;
    panel.hidden = !series.length;
    if (series.length) renderMetricPanel($("metric-seg"), $("log-metric-chart"), $("metric-caption"), series);
    // Opening or closing the chart resizes the log at once; the observer below would only catch up a
    // frame later, with the error or the end out of view until then.
    if (wasHidden !== panel.hidden) keepLogPlace();
  }
  $("metric-seg").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    selectedMetric = b.dataset.metric; store.set("metric", selectedMetric); refreshLogMetrics();
  });
  async function refreshLog(forceBottom = false) {
    const file = $("term-file");
    file.title = selectedLog ?? "";
    if (selectedLog) {
      const cut = selectedLog.lastIndexOf("/") + 1;
      file.replaceChildren(el("span", { className: "dir", textContent: `${shortDir(selectedLog.slice(0, cut))}/` }), selectedLog.slice(cut));
    } else file.textContent = "No log selected";
    if (!selectedLog) { logLines = []; paintLog(); refreshLogMetrics(); return; }
    refreshLogMetrics();
    const requested = selectedLog;
    try {
      const data = await getJSON(`/api/log?lines=2000&path=${encodeURIComponent(requested)}`);
      if (requested !== selectedLog) return;  // another log was chosen while this one loaded
      const key = selectedLog + "\n" + data.lines.join("\n");
      if (key === logKey && !forceBottom && !jumpToError) { logStatusRight(); return; }
      logKey = key;
      logLines = data.lines;
      paintLog(forceBottom);
    } catch (e) {
      if (requested !== selectedLog) return;
      $("log-view").replaceChildren(el("div", { className: "term-empty", textContent: `Could not read log (${e.message}).` }));
      logKey = null;
    }
  }
  $("log-filter").addEventListener("input", () => paintLog());
  // Follow pins the view to the newest line on every update. Scrolling up yourself turns it off;
  // turning it back on jumps to the end. Programmatic scrolls are ignored when deciding.
  let pinning = false;
  function pinLog() {
    const view = $("log-view");
    pinning = true;
    view.scrollTop = view.scrollHeight;
    requestAnimationFrame(() => { pinning = false; });
  }
  $("log-view").addEventListener("scroll", () => {
    const view = $("log-view");
    const atBottom = view.scrollTop + view.clientHeight >= view.scrollHeight - 8;
    if (!pinning && !atBottom && $("follow").checked) $("follow").checked = false;
  });
  $("follow").addEventListener("change", (e) => { if (e.target.checked) pinLog(); });
  // Fonts that finish loading make lines taller; keep a followed log at the end.
  document.fonts?.ready.then(() => { if ($("follow").checked) pinLog(); });
  $("log-copy").innerHTML = ICON.copy;
  $("log-copy").addEventListener("click", async () => {
    const q = $("log-filter").value.toLowerCase();
    const lines = logLines.filter((l) => !q || l.toLowerCase().includes(q));
    try { await navigator.clipboard.writeText(lines.join("\n")); } catch { copyFailed(); return; }
    flashCheck($("log-copy"), ICON.copy);
    toast(`Copied ${plural(lines.length, "line")}`, { tone: "success", description: selectedLog ? baseName(selectedLog) : undefined });
  });
  $("log-download").addEventListener("click", () => {
    if (!selectedLog) return;
    // The page holds only the end of the file, so the download says so in its name.
    const name = selectedLog.split("/").pop();
    const dot = name.lastIndexOf(".");
    const tail = dot > 0 ? `${name.slice(0, dot)}-tail${name.slice(dot)}` : `${name}-tail`;
    const a = el("a", { href: URL.createObjectURL(new Blob([logLines.join("\n") + "\n"], { type: "text/plain" })), download: tail });
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  });

  /* ---------- History page ---------- */
  let historyKey = null;
  function renderHistoryList() {
    const pane = $("history-list-pane");
    if (!state.history.includes(selectedHistory)) selectedHistory = state.history[0] ?? null;
    if (!state.history.length) {
      pane.replaceChildren(emptyState("div", ICON.clock, "No sessions yet"));
      return;
    }
    const byName = Object.fromEntries(state.sessions.filter((s) => s.name).map((s) => [s.name, s]));
    replaceKeepingFocus(pane, state.history.map((name) => {
      const s = byName[name];
      const b = el("button", { type: "button", dataset: { key: name }, attrs: { "aria-current": String(name === selectedHistory) } },
        el("div", { className: "pl-title", textContent: name }),
        el("div", { className: "pl-meta", textContent: s && LIVE.has(s.status) ? `${STATUS[s.status][0]} · ${hardware(s)}` : "Ended" }));
      b.addEventListener("click", () => { if (selectedHistory !== name) showHistory(name); });
      return b;
    }));
  }
  // Switch the History page to another session.
  function showHistory(name) {
    selectedHistory = name; store.set("history", name); historyKey = null;
    $("timeline").replaceChildren(el("li", { className: "empty" }, el("div", { className: "empty-desc" }, icon(ICON.spinner), " Loading…")));
    renderHistoryList(); refreshHistory();
  }
  async function refreshHistory() {
    const list = $("timeline");
    if (!selectedHistory) {
      list.replaceChildren(emptyState("li", ICON.clock, "No history yet", "Sessions appear here after you use the colab CLI."));
      return;
    }
    const requested = selectedHistory;
    try {
      const data = await getJSON(`/api/history?limit=100&session=${encodeURIComponent(requested)}`);
      if (requested !== selectedHistory) return;  // another session was chosen while this one loaded
      const key = selectedHistory + JSON.stringify(data.events);
      if (key === historyKey) return;
      historyKey = key;
      const events = data.events.slice().reverse();
      if (!events.length) { list.replaceChildren(emptyState("li", ICON.clock, "No events")); return; }
      list.replaceChildren(...events.map((ev) => {
        const [title, tone, ic] = eventInfo(ev);
        const t = ev.timestamp ? Date.parse(ev.timestamp) : null;
        const item = el("li", { className: `tli ${tone}` },
          el("span", { className: "node" }, icon(ic)),
          el("div", { className: "tli-head" },
            el("span", { className: "tli-title", textContent: title }),
            el("span", { className: "time", textContent: t ? new Date(t).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "" })));
        if (ev.details) {
          item.append(el("div", { className: "tli-meta" }, ...Object.entries(ev.details)
            .filter(([k]) => k !== "variant")  // GPU/TPU/DEFAULT repeats what the accelerator says
            .map(([k, v]) => k in TAG_LABELS
              ? el("span", { className: "tag", textContent: TAG_LABELS[k][v] ?? String(v) })
              : el("span", { textContent: `${k}: ${v}` }))));
        }
        if (ev.error) item.append(el("div", { className: "tli-err", textContent: ev.error }));
        if (ev.code) item.append(el("details", {}, el("summary", { textContent: "Code" }), el("pre", { textContent: ev.code })));
        if (ev.output) item.append(el("details", {}, el("summary", { textContent: "Output" }), el("pre", { textContent: ev.output })));
        if (ev.images) item.append(el("div", { className: "tli-meta", textContent: plural(ev.images, "image output") }));
        return item;
      }));
    } catch (e) {
      list.replaceChildren(el("li", { className: "empty" }, el("div", { className: "empty-desc", textContent: `Could not read history (${e.message}).` })));
      historyKey = null;
    }
  }

  /* ---------- Settings page ---------- */
  function kvRows(target, rows) {
    target.replaceChildren(...rows.flatMap(([k, v]) => [el("div", { className: "k", textContent: k }), el("div", { className: "v", textContent: v })]));
  }
  function renderSettings() {
    const c = state.config, api = state.api;
    if (!alertsFilled) fillAlerts();
    renderNotify();
    const st = $("set-api-status");
    st.className = `status ${!c.api_enabled ? "gone" : api.error ? "orphan" : "busy"}`;
    st.replaceChildren(el("span", { className: "d" }), !c.api_enabled ? "Off" : api.error ? "Failing" : "Connected");
    kvRows($("set-api"), [
      ["Checks", c.api_enabled ? `Every ${Math.round(c.interval)}s` : "Off (--no-api)"],
      ["Sign-in", c.auth ? `--auth=${c.auth}` : "–"],
      ["Last success", api.updated_at ? new Date(api.updated_at).toLocaleString() : "–"],
      ["Last error", api.error ?? "None"],
    ]);
    kvRows($("set-sources"), [
      ["Session files", c.sessions_paths.map(tildify).join("\n")],
      ["History folder", tildify(c.history_dir)],
      ["Log folders", c.log_dirs.map(tildify).join("\n") || "–"],
      ["Log files", c.log_files.map(tildify).join("\n") || "–"],
      ["Usage samples", c.usage_log ? tildify(c.usage_log) : "–"],
    ]);
  }

  /* ---------- Session details ---------- */
  let drawerOpener = null;
  let drawerKey = null;
  function setDrawer(endpoint) {
    const was = selectedSession;
    selectedSession = endpoint || null;
    const open = Boolean(selectedSession);
    $("drawer").hidden = !open;
    $("drawer-scrim").hidden = !open;
    document.body.classList.toggle("drawer-open", open);
    if (open && was !== selectedSession) {
      if (!was) drawerOpener = document.activeElement;
      drawerKey = null;
      $("drawer-body").scrollTop = 0;
      renderDrawer();
      refreshDrawerData();
      $("drawer").focus();  // the dialog itself, so a mouse click shows no focus ring; Tab reaches the close button
    } else if (!open && was) {
      // Back to whatever opened it, or to its row if the page was redrawn since.
      const row = [...document.querySelectorAll("[data-endpoint] .row-link")].find((a) => a.closest("[data-endpoint]").dataset.endpoint === was);
      (drawerOpener?.isConnected ? drawerOpener : row)?.focus?.();
      drawerOpener = null;
    }
  }
  function closeDrawer() {
    if (!selectedSession) return;
    history.replaceState(null, "", `#/${route}`);
    onRoute();
  }
  $("drawer-close").addEventListener("click", closeDrawer);
  $("drawer-scrim").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => {
    if (!selectedSession) return;
    if (e.key === "Escape") { e.preventDefault(); closeDrawer(); return; }
    if (e.key !== "Tab") return;
    // Keep keyboard focus inside the open details.
    const items = [...$("drawer").querySelectorAll("a[href], button, summary, [tabindex]:not([tabindex='-1'])")].filter((n) => n.offsetParent !== null);
    if (!items.length) return;
    const first = items[0], last = items.at(-1);
    const outside = !$("drawer").contains(document.activeElement) || document.activeElement === $("drawer");
    if (e.shiftKey && (document.activeElement === first || outside)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && (document.activeElement === last || (outside && document.activeElement !== $("drawer")))) { e.preventDefault(); first.focus(); }
  });
  // A click anywhere on a machine's row opens its details; links and buttons inside keep their own job.
  document.addEventListener("click", (e) => {
    const row = e.target.closest("[data-endpoint].clickable");
    if (!row || e.target.closest("a, button, input, summary") || getSelection()?.toString()) return;
    location.hash = sessionHref(row.dataset.endpoint);
  });

  const section = (title, ...children) => el("section", { className: "d-sec" }, el("h3", { textContent: title }), ...children);
  function renderDrawer() {
    if (!selectedSession || !state) return;
    const s = state.sessions.find((x) => x.endpoint === selectedSession);
    const jobs = s?.name ? state.insights.jobs.filter((j) => j.session === s.name) : [];
    const key = JSON.stringify([s, jobs, state.insights.thresholds]);
    if (key === drawerKey) return;
    const keepScroll = drawerKey !== null;
    drawerKey = key;
    const body = $("drawer-body");
    const scroll = body.scrollTop;
    const kept = new Map([...body.querySelectorAll(".d-chart-cap, .d-chart, .d-term, .d-history")].map((n) => [`${n.className}|${n.dataset.path ?? ""}`, n]));
    const reuse = (made) => { const old = kept.get(`${made.className}|${made.dataset.path ?? ""}`); return old ?? made; };
    if (!s) {
      $("drawer-title").textContent = "Machine not found";
      $("drawer-ep").textContent = selectedSession;
      $("drawer-status").replaceChildren();
      body.replaceChildren(el("div", { className: "empty" },
        el("div", { className: "empty-title", textContent: "No machine with this endpoint" }),
        el("div", { className: "empty-desc", textContent: "Colab no longer lists it and the colab CLI has no record of it." })));
      return;
    }
    $("drawer-title").textContent = s.name ?? "Unknown machine";
    $("drawer-title").classList.toggle("faint", !s.name);
    $("drawer-ep").textContent = s.endpoint;
    $("drawer-status").replaceChildren(statusPill(s.status));
    const m = s.metrics ?? {};
    const t = lastRun(s);
    const tile = (label, value, unit, foot) => el("div", { className: "d-tile", dataset: { tile: label } },
      el("div", { className: "d-tile-label", textContent: label }),
      el("div", { className: "d-tile-value" }, value, value !== "–" && unit ? el("span", { className: "unit", textContent: unit }) : null),
      el("div", { className: "d-tile-foot", textContent: foot ?? "" }));
    const idleFor = m.idle_s ? dur(m.idle_s) : null;
    const facts = [
      ["Hardware", hardware(s) || "–"],
      ["Idle", s.status === "busy" ? "No, running a job" : idleFor ?? "–"],
      ["Job", s.running ?? "–"],
      ["Last run", t ? `${baseName(s.last_execution.source) || "code"} · ${rel(t)}` : "–"],
    ];
    const parts = [
      el("div", { className: "d-tiles" },
        tile("Uptime", dur(m.uptime_s), null, m.uptime_s != null ? `since ${when(Date.now() - m.uptime_s * 1000)}` : "No start in history"),
        tile("Rate", m.rate != null ? fmt(m.rate) : "–", "/ hr", m.rate_estimated && m.rate != null ? "Estimated" : m.rate != null ? "Whole account rate" : "Not known yet"),
        tile("Cost so far", m.cost != null ? fmt(m.cost) : "–", "units",
          [m.cost != null && m.rate_estimated && "Estimated", m.idle_cost && `${fmt(m.idle_cost)} while idle`].filter(Boolean).join(" · "))),
      el("dl", { className: "d-facts" }, ...facts.flatMap(([k, v]) => [el("dt", { textContent: k }), el("dd", { textContent: v })])),
    ];
    if (m.uptime_s == null && s.status === "orphan") parts.push(el("p", { className: "d-note", textContent: "No history names this machine, so its uptime and cost are unknown." }));

    if (s.command) {
      parts.push(section(s.status === "orphan" ? "Release machine" : "Stop machine",
        el("p", { className: "d-note", textContent: s.status === "orphan"
          ? "The colab CLI can't stop an orphan. This command releases it. Run it only if the machine isn't someone's work."
          : s.status === "busy" ? "This stops the machine and the job running in it." : "This machine bills while idle. Stopping it ends the session." }),
        snippet(s.command, s.status === "orphan" ? "Copy release command" : "Copy stop command")));
    }

    if (jobs.length) {
      parts.push(section(jobs.length === 1 ? "Job" : "Jobs", ...jobs.map((j) => {
        const pct = j.progress != null ? Math.floor(j.progress * 100) : null;
        const open = el("a", { className: "link", href: "#/logs", textContent: "Open log", dataset: { key: `open|${j.path}` } });
        open.addEventListener("click", () => { openLog(j.path); jumpToError = j.state === "failed"; });
        return el("div", { className: "d-job", dataset: { job: j.name } },
          el("div", { className: "job-top" }, el("div", { className: "title", textContent: j.name }), jobBadge(j),
            pct != null ? el("span", { className: "job-pct", textContent: j.eta_s && j.state === "running" ? `${pct}% · ${dur(j.eta_s)} left` : `${pct}%` }) : null),
          pct != null ? el("div", { className: `bar ${j.state === "failed" ? "bad" : j.state === "finished" ? "ok" : ""}` }, el("span", { style: `width:${Math.min(100, Math.max(0, pct))}%` })) : null,
          j.last_error ? el("div", { className: `job-err${j.state === "failed" ? "" : " old"}`, textContent: j.last_error, title: j.last_error }) : null,
          reuse(el("div", { className: "d-chart-cap", dataset: { path: j.path } })),
          reuse(el("div", { className: "metric-chart d-chart", dataset: { path: j.path }, hidden: true })),
          reuse(el("div", { className: "d-term", dataset: { path: j.path }, hidden: true })),
          el("div", { className: "d-links" }, open));
      })));
    } else if (s.name) {
      parts.push(section("Job", el("p", { className: "d-note" }, "No log file belongs to this machine. Name its log ",
        el("code", { textContent: `${s.name}.log` }), ` in ${shortDir(state.log_dirs[0] ?? "~/colab-runs")} to follow its output here.`)));
    }

    if (s.name && state.history.includes(s.name)) {
      const all = el("a", { className: "link", href: "#/history", textContent: "View full history", dataset: { key: "history" } });
      all.addEventListener("click", () => { selectedHistory = s.name; store.set("history", s.name); });
      parts.push(section("Recent history", reuse(el("ul", { className: "d-history", id: "d-history" })), el("div", { className: "d-links" }, all)));
    }
    replaceKeepingFocus(body, parts);
    if (keepScroll) body.scrollTop = scroll;
    refreshDrawerData(true);
  }

  // The parts of the details that come from other requests: metric charts, log tails, history.
  const drawerData = { endpoint: null, history: null, logs: new Map(), series: new Map() };
  async function refreshDrawerData(fromCache = false) {
    const ep = selectedSession;
    const s = state?.sessions.find((x) => x.endpoint === ep);
    if (!s) return;
    if (drawerData.endpoint !== ep) {
      // Another machine: forget the last one's data, and load this one's now.
      Object.assign(drawerData, { endpoint: ep, history: null, logs: new Map(), series: new Map() });
      fromCache = false;
    }
    // Redraw a box only when its data changed, so a hovered chart keeps its readout.
    const changed = (box, data) => {
      const sig = JSON.stringify(data ?? null) + box.clientWidth;
      if (box.dataset.sig === sig) return false;
      box.dataset.sig = sig;
      return true;
    };
    const paint = () => {
      for (const cap of document.querySelectorAll("#drawer .d-chart-cap")) {
        const first = drawerData.series.get(cap.dataset.path)?.[0];
        cap.textContent = first ? trend(first) : "";
      }
      for (const box of document.querySelectorAll("#drawer .d-chart")) {
        const series = drawerData.series.get(box.dataset.path);
        box.hidden = !series?.length;
        if (series?.length && changed(box, series[0])) drawMetricChart(box, series[0], 120);
      }
      for (const box of document.querySelectorAll("#drawer .d-term")) {
        const lines = drawerData.logs.get(box.dataset.path);
        box.hidden = !lines?.length;
        if (lines && changed(box, lines)) box.replaceChildren(...lines.map((line) => el("div", { className: `tl${isErrorLine(line) ? " err" : WARN.test(line) ? " warn" : ""}`, textContent: line || " " })));
      }
      const list = $("d-history");
      if (list && drawerData.history && changed(list, drawerData.history)) {
        list.replaceChildren(...drawerData.history.map((ev) => {
          const [title, tone, ic] = eventInfo(ev);
          const at = ev.timestamp ? Date.parse(ev.timestamp) : null;
          return el("li", {}, el("span", { className: `ev-icon ${tone}` }, icon(ic)),
            el("div", { className: "grow" }, el("div", { className: "title", textContent: title }),
              ev.error ? el("div", { className: "meta err", textContent: ev.error, title: ev.error }) : null),
            el("span", { className: "time", textContent: at ? rel(at) : "", title: at ? new Date(at).toLocaleString() : "" }));
        }));
      }
    };
    if (fromCache) { paint(); return; }
    const jobs = s.name ? state.insights.jobs.filter((j) => j.session === s.name) : [];
    await Promise.all([
      ...jobs.map(async (j) => {
        try {
          const [series, log] = await Promise.all([loadSeries(j.path, 200, 5e3), getJSON(`/api/log?lines=12&path=${encodeURIComponent(j.path)}`)]);
          drawerData.series.set(j.path, series);
          drawerData.logs.set(j.path, log.lines);
        } catch {}
      }),
      s.name && state.history.includes(s.name) ? getJSON(`/api/history?limit=6&session=${encodeURIComponent(s.name)}`)
        .then((d) => { drawerData.history = d.events.slice().reverse(); }).catch(() => {}) : null,
    ]);
    if (ep === selectedSession) paint();
  }

  /* ---------- Alerts and notifications ---------- */
  const ALERTS = [["alert-idle", "idle_alert", "idle_minutes"], ["alert-stall", "stall_alert", "stall_minutes"], ["alert-runway", "runway_alert", "runway_hours"]];
  const alertOverrides = () => { try { return JSON.parse(store.get("alerts") ?? "{}") ?? {}; } catch { return {}; } };
  const stateUrl = () => {
    const q = new URLSearchParams(Object.entries(alertOverrides()).filter(([, v]) => Number(v) > 0));
    return q.toString() ? `/api/state?${q}` : "/api/state";
  };
  let alertsFilled = false;
  function fillAlerts() {
    const defaults = state.config.thresholds ?? {}, over = alertOverrides();
    for (const [id, param, field] of ALERTS) $(id).value = String(over[param] ?? defaults[field] ?? "");
    for (const [id, , field] of ALERTS) $(id).placeholder = String(defaults[field] ?? "");
    $("alerts-error").textContent = "";
    alertsFilled = true;
  }
  $("alerts-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const defaults = state?.config.thresholds ?? {};
    const next = {};
    // Mark every value that is wrong on its own field, and go to the first.
    const bad = ALERTS.filter(([id]) => !$(id).value.trim() || !(Number($(id).value) > 0)).map(([id]) => id);
    for (const [id] of ALERTS) setInvalid(id, bad.includes(id));
    if (bad.length) {
      $("alerts-error").textContent = "Each value must be a number above 0.";
      $(bad[0]).focus();
      return;
    }
    for (const [id, param, field] of ALERTS) {
      const v = Number($(id).value);
      if (v !== defaults[field]) next[param] = v;
    }
    if (Object.keys(next).length) store.set("alerts", JSON.stringify(next)); else store.del("alerts");
    $("alerts-error").textContent = "";
    await refreshState();
    const btn = $("alerts-form").querySelector('button[type="submit"]');
    btn.textContent = "Saved";
    setTimeout(() => { btn.textContent = "Save"; }, 1200);
    toast("Alert settings saved", { tone: "success", description: "What needs attention now uses these limits in this browser." });
  });
  function setInvalid(id, invalid) {
    const input = $(id), field = input.closest(".field");
    if (invalid) { input.setAttribute("aria-invalid", "true"); input.setAttribute("aria-errormessage", "alerts-error"); field.dataset.invalid = ""; }
    else { input.removeAttribute("aria-invalid"); input.removeAttribute("aria-errormessage"); delete field.dataset.invalid; }
  }
  for (const [id] of ALERTS) {
    $(id).addEventListener("input", () => {
      setInvalid(id, false);
      if (!$("alerts-form").querySelector("[aria-invalid]")) $("alerts-error").textContent = "";
    });
  }
  $("alerts-reset").addEventListener("click", async () => {
    store.del("alerts");
    for (const [id] of ALERTS) setInvalid(id, false);
    await refreshState();
    fillAlerts();
    toast("Alert settings reset", { description: "Colab Monitor's defaults apply again." });
  });

  const canNotify = () => "Notification" in window;
  function renderNotify() {
    const on = store.get("notify") === "1" && canNotify() && Notification.permission === "granted";
    $("notify-toggle").checked = on;
    $("notify-help").textContent = !canNotify() ? "This browser can't show notifications."
      : Notification.permission === "denied" ? "Notifications are blocked for this page. Allow them in the browser's site settings, then turn this on."
      : "Get a notification when something new needs attention, or a job finishes or fails, while this page is open.";
  }
  $("notify-toggle").addEventListener("change", async (e) => {
    if (!e.target.checked) { store.del("notify"); renderNotify(); return; }
    if (canNotify() && Notification.permission === "default") { try { await Notification.requestPermission(); } catch {} }
    if (canNotify() && Notification.permission === "granted") store.set("notify", "1");
    renderNotify();
  });
  // Tell about what is new since the last refresh: never about what was already there on load.
  // The page shows a toast for each new thing; the browser notifies too when that is turned on.
  const ATTENTION_TOAST = {
    orphan: ["Orphaned machine", "error"],
    runway: ["Compute units running low", "error"],
    idle: ["Idle machine", "warning"],
    stalled: ["Job went silent", "warning"],
    failed: ["Run failed", "error"],
  };
  const goToLog = (path, error) => () => {
    openLog(path); jumpToError = error;
    if (route === "logs") showLog(path); else location.hash = "#/logs";
  };
  function attentionToast(a) {
    if (a.kind === "failed" && a.path) return null;  // the job's own toast says it
    const [title, tone] = ATTENTION_TOAST[a.kind] ?? ["Needs attention", "warning"];
    const machine = a.endpoint && state.sessions.find((s) => s.endpoint === a.endpoint);
    const action = machine ? { label: "Details", run: () => { location.hash = sessionHref(machine.endpoint); } }
      : route !== "overview" ? { label: "View", run: () => { location.hash = "#/overview"; } } : undefined;
    return [title, { tone, description: a.message, action, duration: 8000 }];
  }
  let seen = null;
  function notifyChanges() {
    const now = new Map();
    for (const a of state.insights.attention) {
      now.set(`a|${a.kind}|${a.subject}`, [a.severity === "critical" ? "Needs attention" : "Colab Monitor", a.message, () => attentionToast(a)]);
    }
    for (const j of state.insights.jobs) {
      if (j.state === "failed") {
        now.set(`j|${j.path}|failed`, [`${j.name} failed`, j.last_error ?? "",
          () => [`${j.name} failed`, { tone: "error", description: j.last_error ?? undefined, code: true, action: { label: "Show error", run: goToLog(j.path, true) }, duration: 10000 }]]);
      }
      if (j.state === "finished") {
        now.set(`j|${j.path}|finished`, [`${j.name} finished`, j.session ? `on ${j.session}` : "",
          () => [`${j.name} finished`, { tone: "success", description: j.session ? `on ${j.session}` : undefined, action: { label: "Open log", run: goToLog(j.path, false) }, duration: 8000 }]]);
      }
    }
    const before = seen;
    seen = new Set(now.keys());
    if (!before) return;
    const fresh = [...now].filter(([k]) => !before.has(k));
    for (const [, [, , make]] of fresh.slice(0, 3)) { const t = make(); if (t) toast(...t); }
    if (store.get("notify") !== "1" || !canNotify() || Notification.permission !== "granted") return;
    for (const [k, [title, body]] of fresh) { try { new Notification(title, { body, tag: k, icon: "/icon.svg" }); } catch {} }
  }

  /* ---------- Command menu ---------- */
  // ⌘K or Ctrl K: jump to a page, a machine's details, a log, a session's history, or a theme.
  const PAGES = [
    ["overview", "Overview", "balance usage runway spending jobs attention"],
    ["sessions", "Sessions", "machines status rate cost"],
    ["logs", "Logs", "output errors metrics loss"],
    ["history", "History", "events code output"],
    ["settings", "Settings", "alerts notifications theme connection data sources"],
  ];
  const navIcon = (r) => document.querySelector(`nav a[data-route="${r}"] svg`)?.outerHTML ?? ICON.dot;
  let cmdItems = [], cmdShown = [], cmdActive = 0, cmdOpener = null;
  function commandItems() {
    const items = PAGES.map(([r, label, words]) => ({ group: "Pages", label, words, ic: navIcon(r), run: () => { location.hash = `#/${r}`; } }));
    if (state) {
      for (const s of state.sessions) {
        items.push({ group: "Machines", label: s.name ?? "Unknown machine", sub: [hardware(s), s.running].filter(Boolean).join(" · ") || s.endpoint,
          words: [s.endpoint, (STATUS[s.status] ?? [s.status])[0]].join(" "), ic: ICON.chip, badge: statusPill(s.status),
          run: () => { location.hash = sessionHref(s.endpoint); } });
      }
      for (const l of state.logs) {
        items.push({ group: "Logs", label: l.name, sub: shortDir(l.path.slice(0, l.path.lastIndexOf("/") + 1)), words: l.path, ic: ICON.terminal,
          run: () => { openLog(l.path); if (route === "logs") showLog(l.path); else location.hash = "#/logs"; } });
      }
      for (const name of state.history) {
        items.push({ group: "History", label: name, sub: "Code, output and errors", words: "", ic: ICON.clock,
          run: () => { if (route === "history") showHistory(name); else { selectedHistory = name; store.set("history", name); location.hash = "#/history"; } } });
      }
    }
    for (const [t, label, ic] of [["light", "Light theme", ICON.sun], ["dark", "Dark theme", ICON.moon], ["system", "System theme", ICON.monitor]]) {
      items.push({ group: "Theme", label, words: "appearance mode color", ic, run: () => applyTheme(t) });
    }
    return items;
  }
  function renderCommands() {
    const words = $("cmdk-input").value.toLowerCase().split(/\s+/).filter(Boolean);
    cmdShown = cmdItems.filter((it) => {
      const hay = `${it.label} ${it.sub ?? ""} ${it.words} ${it.group}`.toLowerCase();
      return words.every((w) => hay.includes(w));
    });
    cmdActive = Math.min(cmdActive, Math.max(0, cmdShown.length - 1));
    const groups = [];
    cmdShown.forEach((it, i) => {
      let g = groups.at(-1);
      if (g?.name !== it.group) groups.push(g = { name: it.group, rows: [] });
      g.rows.push(el("div", { className: "cmdk-item", id: `cmdk-opt-${i}`, dataset: { i },
        attrs: { role: "option", "aria-selected": String(i === cmdActive) } },
        icon(it.ic), el("span", { className: "cmdk-label", textContent: it.label }),
        el("span", { className: "cmdk-sub", textContent: it.sub ?? "" }), it.badge ?? null));
    });
    $("cmdk-list").replaceChildren(...groups.map((g, n) => el("div", { className: "cmdk-group", attrs: { role: "group", "aria-labelledby": `cmdk-g-${n}` } },
      el("div", { className: "cmdk-heading", id: `cmdk-g-${n}`, textContent: g.name, attrs: { "aria-hidden": "true" } }), ...g.rows)));
    $("cmdk-empty").hidden = cmdShown.length > 0;
    setActive(cmdActive);
  }
  function setActive(i) {
    cmdActive = i;
    for (const n of $("cmdk-list").querySelectorAll("[role=option]")) n.setAttribute("aria-selected", String(Number(n.dataset.i) === i));
    const row = $(`cmdk-opt-${i}`);
    if (row) { $("cmdk-input").setAttribute("aria-activedescendant", row.id); row.scrollIntoView({ block: "nearest" }); }
    else $("cmdk-input").removeAttribute("aria-activedescendant");
  }
  function openCommands() {
    if (!$("cmdk").hidden) return;
    hideTip();
    cmdOpener = document.activeElement;
    cmdItems = commandItems();
    cmdActive = 0;
    $("cmdk-input").value = "";
    $("cmdk").hidden = false;
    $("cmdk-scrim").hidden = false;
    renderCommands();
    $("cmdk-input").focus();
  }
  function closeCommands(restore = true) {
    if ($("cmdk").hidden) return;
    $("cmdk").hidden = true;
    $("cmdk-scrim").hidden = true;
    if (restore && cmdOpener?.isConnected) cmdOpener.focus();
    cmdOpener = null;
  }
  function runCommand(i) {
    const it = cmdShown[i];
    if (!it) return;
    closeCommands();
    it.run();
  }
  $("cmdk-open").addEventListener("click", openCommands);
  $("cmdk-scrim").addEventListener("click", () => closeCommands());
  $("cmdk-input").addEventListener("input", () => { cmdActive = 0; renderCommands(); });
  $("cmdk-list").addEventListener("pointermove", (e) => {
    const row = e.target.closest("[role=option]");
    if (row && Number(row.dataset.i) !== cmdActive) setActive(Number(row.dataset.i));
  });
  $("cmdk-list").addEventListener("click", (e) => {
    const row = e.target.closest("[role=option]");
    if (row) runCommand(Number(row.dataset.i));
  });
  // Captured on window, so the menu answers Escape and Tab before the details sheet does.
  window.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "k") {
      e.preventDefault();
      e.stopPropagation();
      if ($("cmdk").hidden) openCommands(); else closeCommands();
      return;
    }
    if ($("cmdk").hidden) return;
    const n = cmdShown.length;
    if (e.key === "Escape") closeCommands();
    else if (e.key === "ArrowDown" && n) setActive((cmdActive + 1) % n);
    else if (e.key === "ArrowUp" && n) setActive((cmdActive - 1 + n) % n);
    else if (e.key === "Home" && n && e.ctrlKey) setActive(0);
    else if (e.key === "End" && n && e.ctrlKey) setActive(n - 1);
    else if (e.key === "Enter") runCommand(cmdActive);
    else if (e.key !== "Tab") return;  // typing goes to the input
    e.preventDefault();
    e.stopPropagation();
  }, true);

  /* ---------- Tooltips ---------- */
  // Buttons with only an icon name themselves in a tooltip on hover and on keyboard focus.
  let tipFor = null;
  function showTip(target) {
    const tip = $("tip");
    tipFor = target;
    const key = target.dataset.shortcut;
    tip.replaceChildren(target.dataset.tooltip, key ? el("kbd", { className: "kbd", textContent: key.length === 1 ? shortcut(key) : key }) : "");
    tip.hidden = false;
    const r = target.getBoundingClientRect(), w = tip.offsetWidth, h = tip.offsetHeight;
    const side = r.top - h - 8 < 4 ? "bottom" : "top";
    const left = Math.min(Math.max(r.left + r.width / 2 - w / 2, 4), window.innerWidth - w - 4);
    tip.dataset.side = side;
    tip.style.left = `${left}px`;
    tip.style.top = `${side === "top" ? r.top - h - 8 : r.bottom + 8}px`;
    tip.style.setProperty("--arrow-x", `${Math.min(Math.max(r.left + r.width / 2 - left, 10), w - 10)}px`);
  }
  function hideTip() { tipFor = null; $("tip").hidden = true; }
  document.addEventListener("pointerover", (e) => {
    const t = e.target.closest?.("[data-tooltip]");
    if (t && t !== tipFor && e.pointerType !== "touch") showTip(t);
    else if (!t && tipFor) hideTip();
  });
  document.addEventListener("pointerleave", hideTip);
  document.addEventListener("focusin", (e) => {
    const t = e.target.closest?.("[data-tooltip]");
    if (t && t.matches(":focus-visible")) showTip(t); else if (tipFor) hideTip();
  });
  document.addEventListener("focusout", () => { if (tipFor && !tipFor.matches(":hover")) hideTip(); });
  document.addEventListener("pointerdown", hideTip);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && tipFor) hideTip(); });
  window.addEventListener("scroll", hideTip, true);

  /* ---------- Loop ---------- */
  async function refreshState() {
    try {
      state = await getJSON(stateUrl());
      renderShell();
      notifyChanges();
      if (route === "overview") renderOverview();
      if (route === "sessions") renderSessions();
      if (route === "logs") renderLogList();
      if (route === "history") renderHistoryList();
      if (route === "settings") renderSettings();
      if (selectedSession) renderDrawer();
    } catch {
      $("conn-dot").className = "dot bad";
      $("conn-title").textContent = "Dashboard offline";
      $("conn-sub").textContent = "Is colab-monitor still running?";
    }
  }

  let ticks = 0;
  async function tick(routeChanged = false) {
    if (routeChanged) { logKey = null; historyKey = null; activityKey = null; alertsFilled = false; }
    await refreshState();
    if (!state) return;
    if (route === "overview") {
      if (routeChanged || ticks % 10 === 0) refreshUsage();
      if (routeChanged || ticks % 2 === 0) refreshActivity();
    }
    if (route === "logs") refreshLog(routeChanged);
    if (route === "history" && (routeChanged || ticks % 2 === 0)) refreshHistory();
    if (selectedSession && !routeChanged && ticks % 2 === 0) refreshDrawerData();
    ticks++;
  }

  applyTheme(store.get("theme") || "system");
  onRoute();
  setInterval(() => tick(false), 3000);
})();
