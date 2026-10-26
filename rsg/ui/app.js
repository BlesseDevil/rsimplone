// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)
// Licensed under the GNU AGPL v3 or any later version; see <https://www.gnu.org/licenses/>. No warranty.
// Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
// The domain probably expired because HE's TOO BROKE TO RENEW IT.
// Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
// and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"use strict";
// Shell: title bar, job rail, navigation, polling loop, window controls.

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// ═══ rail ════════════════════════════════════════════════════════════════════════════
function destShort(j) { return j.dest_kind === "local" ? (j.target ? leaf(j.target) : "") : (j.remote ? j.remote + ":" + (j.target || "") : ""); }
function renderRail() {
  const list = $("#joblist"); if (!list) return;
  const top = list.scrollTop;
  list.replaceChildren();
  if (!S.jobs.length) list.append(h("div", { class: "empty" }, "No jobs yet.", h("br"), "Use + New."));
  for (const j of S.jobs) {
    const r = lastRun(j.id); const live = isLive(r);
    const state = live ? "live" : j.last_code == null ? "" : (j.last_code === 0 || j.last_code === 9) ? "ok" : "bad";
    const pct = live && r.total ? Math.min(100, Math.round((r.bytes / r.total) * 100)) : 0;
    const ico = h("span", { class: "ico " + j.mode }, icon(j.mode), h("span", { class: "dot " + state }));
    const badges = h("span", { class: "badges" }, icon(j.dest_kind === "local" ? "folder" : "cloud"), j.crypt ? icon("lock", "lock") : null,
      j.schedule && j.schedule.enabled ? icon("clock") : null, (j.problems || []).length ? icon("alert", "warn") : null);
    const slot = h("button", { class: "slot", "aria-current": String(S.view === "job" && j.id === S.sel), onclick: () => { S.sel = j.id; S.view = "job"; if (S.tab === "run" && !lastRun(j.id)) S.tab = "setup"; lsSet("rsg-sel", j.id); renderAll(); } },
      ico, h("span", { style: "min-width:0" }, h("div", { class: "nm" }, j.name), h("div", { class: "sub" }, live ? (r.real ? "Running…" : "Dry run…") + (pct ? " " + pct + "%" : "") : destShort(j) || "needs setup")), badges,
      live ? h("div", { class: "mini" }, h("i", { style: `width:${pct}%` })) : null);
    tooltip(slot, () => slotTip(j));
    list.append(slot);
  }
  list.scrollTop = top;
}
function slotTip(j) {
  const r = lastRun(j.id);
  const rows = [["Mode", MODE_LABEL[j.mode]], ["From", j.source || "—"], ["To", j.dest_text || "—"], ["Backup", j.backup_root || (j.mode === "sync" ? "required" : "none")],
    ["Last run", j.last_run ? `${j.last_run} · ${j.last_mode}${j.last_summary ? " — " + j.last_summary : ""}` : "never"],
    ["Schedule", j.schedule_text + (j.next_run ? " · next " + j.next_run : "")]];
  if (isLive(r)) rows.unshift(["Now", `${r.real ? "real run" : "dry run"} · ${bytes(r.bytes)} of ${bytes(r.total)} · ${bytes(r.speed)}/s`]);
  const dl = h("dl", {}); for (const [k, v] of rows) dl.append(h("dt", {}, k), h("dd", {}, v));
  return h("div", {}, h("b", {}, j.name + (j.crypt ? "  🔒 encrypted" : "")), dl, (j.problems || []).length ? h("div", { style: "color:var(--bad);margin-top:.4rem" }, j.problems[0]) : null);
}
function renderNav() {
  const nav = $("#railnav"); nav.replaceChildren();
  const live = S.mounts.filter((m) => m.state && m.state !== "idle").length;
  const sch = S.jobs.filter((j) => j.schedule && j.schedule.enabled).length;
  const item = (view, ic, label, count) => h("button", { class: "nav", "aria-current": S.view === view ? "page" : "false", onclick: async () => { S.view = view; if (view === "mounts") await loadMounts(); renderAll(); } },
    icon(ic), label, count ? h("span", { class: "chip count" }, count) : null);
  nav.append(item("mounts", "drive", "Mounts", live), item("schedules", "clock", "Schedules", sch), item("settings", "gear", "Settings"));
  const nm = $("#newmenu"); nm.replaceChildren();
  const pop = h("div", { class: "pop", hidden: true }, ["copy", "sync", "move"].map((m) => h("button", { onclick: () => { pop.hidden = true; newJob(m); } }, icon(m), `${MODE_LABEL[m]} job`)));
  nm.append(h("button", { class: "sm primary", onclick: (e) => { e.stopPropagation(); pop.hidden = !pop.hidden; } }, icon("plus"), "New"), pop);
}
document.addEventListener("click", () => { const p = $("#newmenu .pop"); if (p) p.hidden = true; });

function renderStatus() {
  const live = S.runs.filter((r) => ["running", "stopping", "mounting", "mounted"].includes(r.state)).length;
  const st = $("#status");
  st.replaceChildren(h("span", {}, `${S.jobs.length} job${S.jobs.length === 1 ? "" : "s"}`), h("span", {}, live ? `${live} running` : "idle"), h("span", {}, S.rcloneVersion || "rclone not found"), h("span", { class: "sp" }),
    h("a", { href: "#", title: HINT, onclick: (e) => { e.preventDefault(); must("open_url", SITE); } }, COPYRIGHT));
}
function renderAll() {
  renderRail(); renderNav(); renderStatus();
  if (S.view === "mounts") pageMounts(); else if (S.view === "schedules") pageSchedules(); else if (S.view === "settings") pageSettings(); else renderJobPage();
  renderBottom();
}

// ═══ polling ═════════════════════════════════════════════════════════════════════════
let polling = false, lastSig = "";
async function pollNow() {
  if (polling) return; polling = true;
  try {
    const r = await call("poll"); if (!r.ok) return;
    const { events, runs, notes } = r.data;
    const prevStates = Object.fromEntries(S.runs.map((x) => [x.id, x.state]));
    S.runs = runs;
    let logs = false, finished = false;
    for (const ev of events) {
      if (ev.kind === "activity") { const a = (S.activity[ev.run] = S.activity[ev.run] || []); a.push(ev.data); if (a.length > 2000) a.splice(0, 500); }
      else if (ev.kind === "log") logs = true;
    }
    for (const x of runs) { if (prevStates[x.id] && prevStates[x.id] !== x.state && !["running", "stopping", "mounting", "mounted"].includes(x.state)) finished = true; }
    for (const n of notes) toast(n.text, n.level === "bad" ? "bad" : n.level === "ok" ? "ok" : "");
    if (finished) { const jr = await call("jobs"); if (jr.ok) mergeJobs(jr.data); if (S.view === "mounts") { await loadMounts(); pageMounts(); } }
    const sig = runs.map((x) => `${x.id}:${x.state}:${x.bytes}:${x.errors}:${x.checks}:${x.transfers}`).join("|");
    if (sig !== lastSig || finished) {
      lastSig = sig; renderRail(); renderStatus(); renderNav();
      if (S.view === "job" && S.tab === "run") updateRunTab(); else if (S.view === "job") { const a = $("#hdr-actions"); const j = curJob(); if (a && j) fillActions(a, j); }
      if (S.bottomOpen && S.bottomTab === "runs") { const l = $("#runs-list"); if (l) l.replaceWith(runsList()); else renderBottom(); }
      if (S.bottomOpen && S.bottomTab === "console") { const f = $("#cfoot"); const run = S.runs.find((x) => x.id === S.bottomSel); if (f && run) f.textContent = statsLine(run); }
      if (finished && S.view === "job") renderJobPage();
    }
    if ((logs || finished) && S.bottomOpen && S.bottomTab === "console") await pullConsole(false);
  } finally { polling = false; }
}
function mergeJobs(server) {
  for (const sj of server) {
    const mine = S.jobs.find((j) => j.id === sj.id);
    if (!mine) { S.jobs.push(sj); continue; }
    if (dirty.has(mine.id)) continue;
    for (const k of DERIVED) mine[k] = sj[k];
  }
  S.jobs = S.jobs.filter((j) => server.some((s) => s.id === j.id));
}

// ═══ window chrome ═══════════════════════════════════════════════════════════════════
function bindChrome() {
  $("#win-min").onclick = () => call("win_minimize");
  $("#win-max").onclick = () => call("win_toggle_max");
  $(".titlebar .drag").addEventListener("dblclick", (e) => { if (!e.target.closest("button")) call("win_toggle_max"); });
  $("#win-close").onclick = async () => {
    const r = await must("win_close", false); if (!r) return;
    if (r.confirm) {
      const ok = await confirmBox("Quit with tasks running?", h("p", {}, `${r.confirm} task${r.confirm === 1 ? " is" : "s are"} still running. They will be stopped cleanly first. Finished files are kept.`), "Stop and quit", true);
      if (ok) await must("win_close", true);
    }
  };
  $("#contact-btn").onclick = aboutDialog;
  const logo = $("#logo-btn");
  tipText(logo, "rSimpLone by blessedevil", HINT, 450);
  logo.onclick = async () => {
    S.logoClicks++;
    if (S.logoClicks >= 4) { S.logoClicks = 0; must("open_url", SITE); return; }
    const next = THEMES[(THEMES.indexOf(S.theme) + 1) % THEMES.length];
    logo.classList.remove("spin"); void logo.offsetWidth; logo.classList.add("spin");
    applyTheme(next); await call("set_theme", next);
    const e = $("#empty-logo"); if (e) e.src = resolvedTheme(next) === "dark" ? "brand/emblem-gold.png" : "brand/emblem.png";
    toast("Theme: " + next);
  };
  // edge/corner resize for the frameless window
  for (const grip of $$(".rz")) {
    grip.addEventListener("pointerdown", async (e) => {
      e.preventDefault(); grip.setPointerCapture(e.pointerId);
      const r0 = await call("win_size"); if (!r0.ok) return;
      const [w0, h0] = r0.data, x0 = e.screenX, y0 = e.screenY, dx = grip.classList.contains("b") ? 0 : 1, dy = grip.classList.contains("r") ? 0 : 1;
      let busy = false;
      const move = async (ev) => { if (busy) return; busy = true; await call("win_resize", w0 + dx * (ev.screenX - x0), h0 + dy * (ev.screenY - y0)); busy = false; };
      const up = () => { grip.removeEventListener("pointermove", move); grip.removeEventListener("pointerup", up); };
      grip.addEventListener("pointermove", move); grip.addEventListener("pointerup", up);
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key === "`") { S.bottomOpen = !S.bottomOpen; S.bottomTab = "console"; renderBottom(); }
  });
}

// ═══ start ═══════════════════════════════════════════════════════════════════════════
async function init() {
  const t0 = Date.now();
  while (!bridgeReady()) { if (Date.now() - t0 > 15000) { document.body.textContent = "The app bridge did not start."; return; } await wait(50); }
  for (let i = 0; i < 200; i++) { const b = await call("is_booted"); if (b.ok && b.data) break; await wait(100); }
  const st = await must("app_state");
  if (st) Object.assign(S, { version: st.version, rcloneVersion: st.rclone_version, remotes: st.remotes, settings: st.settings, fuse: st.fuse, confirmWord: st.confirm_word, platform: st.platform });
  const th = await call("theme"); if (th.ok) applyTheme(th.data);
  const cat = await call("flag_catalogue"); if (cat.ok) S.catalogue = cat.data;
  const jobs = await call("jobs"); if (jobs.ok) S.jobs = jobs.data;
  await loadMounts();
  S.sel = (S.jobs.find((j) => j.id === lsGet("rsg-sel", "")) || S.jobs[0] || {}).id || null;
  const ru = await call("runs"); if (ru.ok) S.runs = ru.data;
  bindChrome();
  $("#app").hidden = false;
  renderAll();
  setInterval(pollNow, 450);
  call("ui_ready");
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
