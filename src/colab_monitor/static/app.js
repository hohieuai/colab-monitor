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
    chip: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="3.5" y="3.5" width="9" height="9" rx="1.5"/><path d="M6 1.5v2M10 1.5v2M6 12.5v2M10 12.5v2M1.5 6h2M1.5 10h2M12.5 6h2M12.5 10h2"/></svg>',
  };

  /* ---------- State ---------- */
  let state = null;
  let lastUsage = null;
  let route = "overview";
  // Usage rate is the default: Colab only updates the balance every so often, the rate moves at once.
  let measure = store.get("measure") === "balance" ? "balance" : "rate";
  let range = ["1h", "24h", "7d", "30d"].includes(store.get("range")) ? store.get("range") : "24h";
  let statusFilter = "all";
  let selectedLog = store.get("log");
  let selectedHistory = store.get("history");

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

  /* ---------- Copy buttons ---------- */
  function flashCheck(btn, restore) { btn.innerHTML = ICON.check; setTimeout(() => (btn.innerHTML = restore), 1200); }
  for (const btn of document.querySelectorAll(".copy")) {
    btn.innerHTML = ICON.copy;
    btn.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(btn.parentElement.querySelector("code").textContent); flashCheck(btn, ICON.copy); } catch {}
    });
  }

  /* ---------- Router ---------- */
  const ROUTES = ["overview", "sessions", "logs", "history", "settings"];
  function onRoute() {
    const r = (location.hash.match(/^#\/(\w+)/) || [])[1];
    route = ROUTES.includes(r) ? r : "overview";
    for (const p of document.querySelectorAll("[data-page]")) p.hidden = p.dataset.page !== route;
    for (const a of document.querySelectorAll("[data-route]")) {
      if (a.dataset.route === route) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    }
    $("app").classList.remove("nav-open");
    document.title = `${route[0].toUpperCase()}${route.slice(1)} · Colab Monitor`;
    window.scrollTo(0, 0);
    tick(true);
  }
  window.addEventListener("hashchange", onRoute);
  $("menu-btn").addEventListener("click", () => $("app").classList.add("nav-open"));
  $("scrim").addEventListener("click", () => $("app").classList.remove("nav-open"));

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

  function renderShell() {
    renderApiNotice(state.api);
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
    for (const id of ["conn-dot", "mobile-dot", "checked-dot"]) $(id).className = cls;
    $("conn-title").textContent = title;
    $("conn-sub").textContent = sub;
    $("conn-sub").parentElement.title = api.error ?? "";
    $("checked-text").textContent = api.enabled ? (api.error ? "Colab check failed" : `Updated ${checked}`) : "Local files only";
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

    $("s-balance").replaceChildren(u ? fmt(u.balance) : "–");
    $("s-rate").replaceChildren(...(u ? [fmt(u.rate_per_hour), el("span", { className: "unit", textContent: "/ hr" })] : ["–"]));
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
      runway.replaceChildren(u ? "No burn" : "–");
      $("s-runway-foot").textContent = u ? "Nothing is billing right now" : "At the current rate";
    }
    $("s-machines").textContent = api.enabled && u ? String(live.length) : "–";
    $("s-machines-foot").textContent = live.length
      ? [counts.busy && `${counts.busy} running`, counts.idle && `${counts.idle} idle`, counts.orphan && `${counts.orphan} orphan`, counts.stopping && `${counts.stopping} stopping`].filter(Boolean).join(" · ")
      : "On your account";

    const list = $("ov-sessions");
    if (!live.length) {
      list.replaceChildren(el("li", { className: "empty", style: "display:block" },
        el("div", { className: "empty-title", textContent: "No machines running" }),
        el("div", { className: "empty-desc", textContent: "Start a job and it appears here within a minute." })));
    } else {
      list.replaceChildren(...live.map((s) => el("li", {},
        el("span", { className: `ev-icon ${s.status === "busy" ? "run" : s.status === "orphan" ? "bad" : ""}` }, icon(ICON.chip)),
        el("div", { className: "grow" },
          el("div", { className: `title${s.name ? "" : " faint"}`, textContent: s.name ?? "Unknown machine" }),
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
    $("attention-list").replaceChildren(...items.map((a) => el("li", { dataset: { kind: a.kind } },
      el("span", { className: `sev ${a.severity}` }), el("span", { textContent: a.message }))));
    $("orphan-hint").hidden = !items.some((a) => a.kind === "orphan");
    // The colab CLI signs in with OAuth unless told otherwise; with ADC, the plain command would wait for a code.
    const adc = state.config.auth === "adc";
    $("orphan-command").textContent = `uvx --from google-colab-cli python -c "${adc ? "from colab_cli.auth import AuthProvider; " : ""}from colab_cli.common import state; ${adc ? "state.auth_provider = AuthProvider.ADC; " : ""}state.client.unassign('ENDPOINT')"`;
  }

  const openLog = (path) => { selectedLog = path; store.set("log", path); };
  function renderJobs(jobs) {
    const list = $("ov-jobs");
    if (!jobs.length) {
      list.replaceChildren(el("li", { className: "empty", style: "display:block" },
        el("div", { className: "empty-title", textContent: "No job logs" }),
        el("div", { className: "empty-desc", textContent: `Send a job's output to ${shortDir(state.log_dirs[0] ?? "~/colab-runs")} to follow it here.` })));
      return;
    }
    const newest = [...jobs].sort((a, b) => (a.silent_s ?? Infinity) - (b.silent_s ?? Infinity)).slice(0, 6);
    replaceKeepingFocus(list, newest.map((j) => {
      const pct = j.progress != null ? Math.floor(j.progress * 100) : null;  // rounded down, like tqdm
      const readings = [j.speed, ...Object.entries(j.metrics ?? {}).slice(0, 3).map(([k, v]) => `${k} ${String(Number(Number(v).toPrecision(4)))}`)];
      const facts = [
        j.session && `on ${j.session}`,
        ...(pct == null && !readings.some(Boolean) ? ["No progress printed yet"] : readings),
        j.silent_s != null && !j.stalled && `updated ${j.silent_s < 5 ? "just now" : `${dur(j.silent_s)} ago`}`,
      ].filter(Boolean);
      const name = el("a", { className: "job-name", href: "#/logs", textContent: j.name, title: tildify(j.path), dataset: { key: j.path } });
      name.addEventListener("click", () => openLog(j.path));
      return el("li", { dataset: { job: j.name } },
        el("span", { className: `ev-icon ${j.last_error ? "bad" : j.stalled ? "" : "run"}` }, icon(j.last_error ? ICON.err : ICON.file)),
        el("div", { className: "grow" },
          el("div", { className: "job-top" },
            el("div", { className: "title" }, name),
            j.stalled ? el("span", { className: "badge warn", textContent: `Silent ${dur(j.silent_s)}` }) : null,
            pct != null ? el("span", { className: "job-pct", textContent: j.eta_s ? `${pct}% · ${dur(j.eta_s)} left` : `${pct}%` }) : null),
          el("div", { className: "meta", textContent: facts.join(" · ") }),
          pct != null ? el("div", { className: "bar", attrs: { role: "progressbar", "aria-valuenow": String(pct), "aria-valuemin": "0", "aria-valuemax": "100", "aria-label": `${j.name} progress` } },
            el("span", { style: `width:${Math.min(100, Math.max(0, pct))}%` })) : null,
          j.last_error ? el("div", { className: "job-err", textContent: j.last_error, title: j.last_error }) : null));
    }));
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
    $("spend-since").textContent = since && since * 1000 > Date.now() - 29 * 86400e3 ? `Measured since ${when(since * 1000)}` : "";
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
        list.replaceChildren(el("li", { className: "empty", style: "display:block" },
          el("div", { className: "empty-title", textContent: "No activity yet" }),
          el("div", { className: "empty-desc", textContent: "Events appear as you use the colab CLI." })));
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
    const lastP = points.at(-1);
    const end = sv("circle", { class: "chart-end", cx: X(lastP.t), cy: Y(lastP.v), r: 4 });
    const endLabel = sv("text", { class: "chart-end-label", x: X(lastP.t) + 10, y: Y(lastP.v) + 4 }, fmt(lastP.v));
    const cross = sv("line", { class: "chart-cross", y1: m.t, y2: base, visibility: "hidden" });
    const hoverDot = sv("circle", { class: "chart-end", r: 4, visibility: "hidden" });
    const hit = sv("rect", { class: "chart-hit", x: m.l, y: m.t, width: iw, height: ih + 1 });
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("aria-label", `${measure === "rate" ? "Usage rate" : "Compute unit balance"} over ${span}; latest ${valueFmt(lastP.v)}`);
    svg.replaceChildren(grid, area, line, axis, cross, end, endLabel, hoverDot, hit);

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
      tip.replaceChildren(
        el("div", { className: "tv" }, el("span", { className: "key" }), valueFmt(best.v)),
        el("div", { textContent: `${measure === "rate" ? "Usage rate" : "Balance"} · ${fullTime(best.t)}` }));
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
  window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => route === "overview" && drawChart(), 120); });

  /* ---------- Sessions page ---------- */
  function renderSessions() {
    const counts = { all: state.sessions.length, busy: 0, idle: 0, orphan: 0, gone: 0 };
    for (const s of state.sessions) if (s.status in counts) counts[s.status]++;
    for (const n of document.querySelectorAll("#status-seg [data-n]")) n.textContent = String(counts[n.dataset.n] ?? 0);
    const q = $("session-search").value.trim().toLowerCase();
    const rows = state.sessions.filter((s) =>
      (statusFilter === "all" || s.status === statusFilter) &&
      (!q || [s.name, s.accelerator, hardware(s), s.endpoint, s.running].some((v) => (v ?? "").toLowerCase().includes(q))));
    $("sessions-body").replaceChildren(...rows.map((s) => {
      const t = lastRun(s);
      const hint = (STATUS[s.status] ?? [])[1];
      return el("tr", {},
        el("td", { className: `name${s.name ? "" : " unknown"}`, title: [s.name, s.endpoint].filter(Boolean).join("\n") },
          el("div", { textContent: s.name ?? "Unknown" }),
          el("div", { className: "ep", textContent: s.endpoint ?? "" })),
        el("td", { className: "st", title: hint ?? "" }, statusPill(s.status), hint ? el("span", { className: "status-hint", textContent: hint }) : null),
        el("td", { className: "meta-cell", dataset: { label: "Hardware" } }, hardware(s) ? el("span", { className: "tag", textContent: hardware(s) }) : "–"),
        el("td", { className: `num meta-cell${s.metrics?.uptime_s != null ? "" : " empty-val"}`, dataset: { label: "Uptime" }, textContent: dur(s.metrics?.uptime_s),
          title: s.metrics?.idle_s ? `Idle for ${dur(s.metrics.idle_s)}` : "" }),
        el("td", { className: `num meta-cell${s.metrics?.rate != null ? "" : " empty-val"}`, dataset: { label: "Rate" } }, ...rateParts(s.metrics)),
        el("td", { className: `job meta-cell${s.running ? "" : " empty-val"}`, dataset: { label: "Job" }, textContent: s.running ?? "–", title: s.running ?? "" }),
        el("td", { className: `sub meta-cell${t ? "" : " empty-val"}`, dataset: { label: "Last run" }, textContent: t ? `${baseName(s.last_execution.source) || "code"} · ${rel(t)}` : "–", title: t ? `${s.last_execution.source ?? ""}\n${s.last_execution.time}` : "" }));
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
      pane.replaceChildren(el("div", { className: "empty", style: "padding:24px 8px" },
        el("div", { className: "empty-title", textContent: "No log files" }),
        el("div", { className: "empty-desc", textContent: `Send a job's output to ${dirs[0] ?? "~/colab-runs"}.` })));
      return;
    }
    replaceKeepingFocus(pane, state.logs.map((l) => {
      const b = el("button", { type: "button", dataset: { key: l.path }, attrs: { "aria-current": String(l.path === selectedLog) } },
        el("div", { className: "pl-title", textContent: l.name }),
        el("div", { className: "pl-meta", textContent: l.exists ? `${bytes(l.size)} · ${rel(l.mtime * 1000)}` : "missing" }));
      b.addEventListener("click", () => {
        if (selectedLog === l.path) return;
        selectedLog = l.path; store.set("log", l.path); logKey = null; logLines = [];
        $("log-view").replaceChildren(el("div", { className: "term-empty", textContent: "Loading…" }));
        renderLogList(); refreshLog(true);
      });
      return b;
    }));
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
    if ($("follow").checked || forceBottom) pinLog();
    const errs = logLines.filter((l) => isErrorLine(l)).length;
    $("term-left").textContent = selectedLog ? `${plural(logLines.length, "line")}${q ? ` · ${shown.length} shown` : ""}${errs ? ` · ${plural(errs, "error line")}` : ""}` : "";
    logStatusRight();
  }
  async function refreshLog(forceBottom = false) {
    const file = $("term-file");
    file.title = selectedLog ?? "";
    if (selectedLog) {
      const cut = selectedLog.lastIndexOf("/") + 1;
      file.replaceChildren(el("span", { className: "dir", textContent: `${shortDir(selectedLog.slice(0, cut))}/` }), selectedLog.slice(cut));
    } else file.textContent = "No log selected";
    if (!selectedLog) { logLines = []; paintLog(); return; }
    const requested = selectedLog;
    try {
      const data = await getJSON(`/api/log?lines=2000&path=${encodeURIComponent(requested)}`);
      if (requested !== selectedLog) return;  // another log was chosen while this one loaded
      const key = selectedLog + "\n" + data.lines.join("\n");
      if (key === logKey && !forceBottom) { logStatusRight(); return; }
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
    try { await navigator.clipboard.writeText(logLines.filter((l) => !q || l.toLowerCase().includes(q)).join("\n")); flashCheck($("log-copy"), ICON.copy); } catch {}
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
      pane.replaceChildren(el("div", { className: "empty", style: "padding:24px 8px" }, el("div", { className: "empty-title", textContent: "No sessions yet" })));
      return;
    }
    const byName = Object.fromEntries(state.sessions.filter((s) => s.name).map((s) => [s.name, s]));
    replaceKeepingFocus(pane, state.history.map((name) => {
      const s = byName[name];
      const b = el("button", { type: "button", dataset: { key: name }, attrs: { "aria-current": String(name === selectedHistory) } },
        el("div", { className: "pl-title", textContent: name }),
        el("div", { className: "pl-meta", textContent: s && LIVE.has(s.status) ? `${STATUS[s.status][0]} · ${hardware(s)}` : "Ended" }));
      b.addEventListener("click", () => {
        if (selectedHistory === name) return;
        selectedHistory = name; store.set("history", name); historyKey = null;
        $("timeline").replaceChildren(el("li", { className: "empty" }, el("div", { className: "empty-desc", textContent: "Loading…" })));
        renderHistoryList(); refreshHistory();
      });
      return b;
    }));
  }
  async function refreshHistory() {
    const list = $("timeline");
    if (!selectedHistory) {
      list.replaceChildren(el("li", { className: "empty" }, el("div", { className: "empty-title", textContent: "No history yet" }), el("div", { className: "empty-desc", textContent: "Sessions appear here after you use the colab CLI." })));
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
      if (!events.length) { list.replaceChildren(el("li", { className: "empty" }, el("div", { className: "empty-title", textContent: "No events" }))); return; }
      list.replaceChildren(...events.map((ev) => {
        const [title, tone] = eventInfo(ev);
        const t = ev.timestamp ? Date.parse(ev.timestamp) : null;
        const item = el("li", { className: `tli ${tone}` },
          el("span", { className: "node" }),
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

  /* ---------- Loop ---------- */
  async function refreshState() {
    try {
      state = await getJSON("/api/state");
      renderShell();
      if (route === "overview") renderOverview();
      if (route === "sessions") renderSessions();
      if (route === "logs") renderLogList();
      if (route === "history") renderHistoryList();
      if (route === "settings") renderSettings();
    } catch {
      for (const id of ["conn-dot", "mobile-dot", "checked-dot"]) $(id).className = "dot bad";
      $("conn-title").textContent = "Dashboard offline";
      $("conn-sub").textContent = "Is colab-monitor still running?";
      $("checked-text").textContent = "Dashboard server offline";
    }
  }

  let ticks = 0;
  async function tick(routeChanged = false) {
    if (routeChanged) { logKey = null; historyKey = null; activityKey = null; }
    await refreshState();
    if (!state) return;
    if (route === "overview") {
      if (routeChanged || ticks % 10 === 0) refreshUsage();
      if (routeChanged || ticks % 2 === 0) refreshActivity();
    }
    if (route === "logs") refreshLog(routeChanged);
    if (route === "history" && (routeChanged || ticks % 2 === 0)) refreshHistory();
    ticks++;
  }

  applyTheme(store.get("theme") || "system");
  onRoute();
  setInterval(() => tick(false), 3000);
})();
