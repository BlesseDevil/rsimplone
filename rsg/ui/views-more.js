// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)
// Licensed under the GNU AGPL v3 or any later version; see <https://www.gnu.org/licenses/>. No warranty.
// Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
// The domain probably expired because HE's TOO BROKE TO RENEW IT.
// Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
// and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"use strict";
// Everything that is not the job page: mounts, schedules overview, settings, About, and the bottom pane
// (running tasks + the real console).

const CONTACT = "rsimplone@mehedimaruf.com", LICENSE_CONTACT = "license@mehedimaruf.com";
const COPYRIGHT = "© 2026 blessedevil | Mehedi Maruf";

// ═══ About ═════════════════════════════════════════════════════════════════════════
function aboutDialog() {
  return dialog((close) => h("div", {},
    h("h2", {}, "rSimpLone by blessedevil"),
    h("p", {}, "rClone, made simple."),
    h("p", { class: "note" }, `Version ${S.version} · ${S.rcloneVersion || "rclone not found"} · AGPL-3.0-or-later`),
    h("dl", { style: "display:grid;grid-template-columns:auto 1fr;gap:.2rem .9rem;margin:.6rem 0" },
      h("dt", { class: "muted" }, "Developer"), h("dd", { style: "margin:0" }, h("a", { href: "#", onclick: (e) => { e.preventDefault(); must("open_url", "mailto:" + CONTACT); } }, CONTACT)),
      h("dt", { class: "muted" }, "Licence"), h("dd", { style: "margin:0" }, LICENSE_CONTACT),
      h("dt", { class: "muted" }, "Website"), h("dd", { style: "margin:0" }, h("a", { href: "#", onclick: (e) => { e.preventDefault(); must("open_url", SITE); } }, "mehedimaruf.com"))),
    h("p", { class: "joke" }, `Can't reach ${CONTACT} or ${LICENSE_CONTACT}? The domain probably expired because HE's TOO BROKE TO RENEW IT. Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead, and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')`),
    h("div", { class: "btns" }, h("button", { onclick: () => must("open_url", "mailto:" + CONTACT) }, icon("mail"), "Email the developer"), h("button", { class: "primary", onclick: () => close() }, "Close"))));
}

// ═══ Mounts ═════════════════════════════════════════════════════════════════════════
async function loadMounts() { const m = await must("mounts"); if (m) S.mounts = m; }
function pageMounts() {
  const page = $("#page");
  const stack = h("div", { class: "stack" });
  const fuse = S.fuse || {};
  if (!fuse.ok) stack.append(h("div", { class: "warnbox" }, icon("alert"), ` ${fuse.message || "Mounting needs an extra driver on this computer."} `, fuse.url ? h("a", { href: "#", onclick: (e) => { e.preventDefault(); must("open_url", fuse.url); } }, fuse.url) : null));
  if (!S.mounts.length) stack.append(h("div", { class: "empty" }, h("h2", {}, "No mounts yet"), h("p", {}, "A mount shows a cloud remote (or one folder of it) as a normal drive or folder on this computer."), h("p", { class: "note" }, "Press New mount to add one.")));
  for (const m of S.mounts) stack.append(mountCard(m));
  page.style.gridTemplateRows = "auto minmax(0, 1fr)";
  page.replaceChildren(
    h("div", { class: "jobhead" }, h("h2", { style: "font-size:1.35rem" }, "Mounts"), h("span", { class: "grow" }),
      h("button", { class: "primary", onclick: async () => { const m = await must("new_mount"); if (m) { await loadMounts(); pageMounts(); } } }, icon("plus"), "New mount")),
    h("div", { class: "view" }, stack));
}
function mountCard(m) {
  const save = debounce(async () => { await must("save_mount", m); await loadMounts(); const cur = S.mounts.find((x) => x.id === m.id); if (cur) { m.problems = cur.problems; } fillMountBtn(); }, 500);
  const set = (k, v) => { m[k] = v; save(); };
  const inp = (k, ph) => { const el = h("input", { value: m[k] || "", placeholder: ph || "", spellcheck: "false" }); el.addEventListener("input", () => set(k, el.value)); return el; };
  const remote = h("select", {}, h("option", { value: "" }, "Choose a remote…"), S.remotes.map((r) => h("option", { value: r.name, selected: r.name === m.remote }, (r.crypt ? "🔒 " : "") + r.name)));
  remote.addEventListener("change", () => { m.path = ""; set("remote", remote.value); pageMounts(); });
  const cache = h("select", {}, ["off", "minimal", "writes", "full"].map((c) => h("option", { value: c, selected: c === m.vfs_cache_mode }, c)));
  cache.addEventListener("change", () => set("vfs_cache_mode", cache.value));
  const pathIn = inp("path", "Leave empty for the whole remote, or e.g. Photos/2024");
  const mpIn = inp("mountpoint", S.platform.startsWith("win") ? "A free drive letter such as X:, or a new folder" : "An empty folder, e.g. /home/you/mnt/drive");
  const active = m.state && m.state !== "idle";
  const btn = h("button", { class: active ? "danger" : "primary" });
  const fillMountBtn = () => {
    btn.className = m.state && m.state !== "idle" ? "danger" : "primary";
    btn.replaceChildren(icon(m.state && m.state !== "idle" ? "stop" : "drive"), m.state === "mounting" ? "Mounting…" : m.state === "stopping" ? "Unmounting…" : m.state === "mounted" ? "Unmount" : "Mount");
    btn.disabled = (m.state === "idle" && ((m.problems || []).length > 0 || !(S.fuse || {}).ok)) || m.state === "stopping";
    btn.title = m.problems && m.problems.length && m.state === "idle" ? m.problems.join(" ") : "";
  };
  btn.addEventListener("click", async () => {
    if (m.state && m.state !== "idle") { await must("stop", m.run); }
    else { const r = await must("mount", m.id); if (r) { S.bottomOpen = true; S.bottomTab = "console"; S.bottomSel = r; } }
    await pollNow(); await loadMounts(); pageMounts();
  });
  fillMountBtn();
  const ro = sw(m.read_only, (v) => set("read_only", v), "Read-only", "Recommended. You can browse and copy files out, but nothing can be changed or deleted through the mount.");
  const auto = sw(m.auto_mount, (v) => set("auto_mount", v), "Mount again when rSimpLone starts");
  const pickPath = h("button", { onclick: async () => {
    if (!m.remote) return toast("Choose a remote first.", "bad");
    const dirs = await must("folders", m.remote, 2); if (!dirs) return;
    const c = await folderPicker(m.remote, dirs); if (c != null) { m.path = c; pathIn.value = c; save(); }
  } }, icon("folder"), "Pick…");
  const pickMp = S.platform.startsWith("win") ? null : h("button", { onclick: async () => { const p = await must("pick_folder", ""); if (p) { mpIn.value = p; set("mountpoint", p); } } }, icon("folder"), "Pick…");
  return h("div", { class: "card mcard" }, h("header", {}, h("input", { class: "name", style: "font:650 1.05rem var(--font-body);background:none;border-color:transparent;max-width:22rem", value: m.name, spellcheck: "false", oninput: (e) => set("name", e.target.value) }),
    m.state && m.state !== "idle" ? h("span", { class: "chip " + (m.state === "mounted" ? "ok" : "warn") }, m.state) : null, h("span", { class: "grow" }), btn,
    h("button", { class: "ghost icon", title: "Delete this mount", "aria-label": "Delete this mount", disabled: active, onclick: async () => { if (await confirmBox("Delete mount?", h("p", {}, `“${m.name}” will be removed from rSimpLone. The remote and its files are not touched.`), "Delete", true)) { await must("delete_mount", m.id); await loadMounts(); pageMounts(); } } }, icon("trash"))),
    h("div", { class: "grid2" }, field("Remote", remote), field("Folder on the remote (optional)", h("div", { class: "row" }, h("div", { class: "grow" }, pathIn), pickPath)),
      field(S.platform.startsWith("win") ? "Mount at (drive letter or new folder)" : "Mount at (empty folder)", h("div", { class: "row" }, h("div", { class: "grow" }, mpIn), pickMp)), field("Cache mode", cache, "“writes” suits most people. “full” also caches what you read, which needs more disk space.")),
    h("div", { class: "grid2" }, ro, auto), field("Extra options", inp("extra", "e.g. --dir-cache-time 5m"), "Options that rSimpLone manages itself (logging and similar) are refused."),
    (m.problems || []).length && m.state === "idle" ? h("div", { class: "note", style: "color:var(--bad)" }, m.problems.join(" ")) : null);
}

// ═══ Schedules overview ═══════════════════════════════════════════════════════════
function pageSchedules() {
  const page = $("#page");
  const rows = S.jobs.filter((j) => j.schedule && j.schedule.enabled);
  const list = rows.length ? h("div", { class: "stack" }, rows.map((j) => h("div", { class: "card row" }, icon(j.mode), h("b", { class: "grow" }, j.name),
    h("span", { class: "chip" }, j.schedule_text), h("span", { class: "chip " + (j.schedule.real ? "bad" : "gold") }, j.schedule.real ? "real runs" : "previews only"),
    h("span", { class: "note" }, j.next_run ? "next " + j.next_run : ""), h("button", { class: "sm", onclick: () => { S.sel = j.id; S.view = "job"; S.tab = "schedule"; renderAll(); } }, "Edit")))) :
    h("div", { class: "empty" }, h("h2", {}, "Nothing is scheduled"), h("p", {}, "Open a job and use its Schedule tab to run it automatically."));
  page.style.gridTemplateRows = "auto minmax(0, 1fr)";
  page.replaceChildren(h("div", { class: "jobhead" }, h("h2", { style: "font-size:1.35rem" }, "Schedules")), h("div", { class: "view" },
    list, h("p", { class: "note" }, "Schedules only run while rSimpLone is open. To keep it running with the window closed, turn on background mode in Settings. Running when the app is fully closed is not supported yet.")));
}

// ═══ Settings ═══════════════════════════════════════════════════════════════════════
function pageSettings() {
  const page = $("#page"); const st = S.settings;
  const save = debounce(async () => { await must("save_settings", st); }, 400);
  const rc = h("input", { value: st.rclone || "", placeholder: "Leave empty to use the rclone found on your PATH", spellcheck: "false" });
  rc.addEventListener("input", () => { st.rclone = rc.value; save(); });
  const theme = h("div", { class: "seg" }, THEMES.map((t) => h("button", { "aria-pressed": String(S.theme === t), onclick: async () => { applyTheme(t); await must("set_theme", t); pageSettings(); } }, t[0].toUpperCase() + t.slice(1))));
  const disk = h("div", { class: "seg" }, ["hdd", "ssd"].map((d) => h("button", { "aria-pressed": String((st.default_disk || "hdd") === d), onclick: () => { st.default_disk = d; save(); pageSettings(); } }, d.toUpperCase())));
  page.style.gridTemplateRows = "auto minmax(0, 1fr)";
  page.replaceChildren(h("div", { class: "jobhead" }, h("h2", { style: "font-size:1.35rem" }, "Settings")), h("div", { class: "view" }, h("div", { class: "stack" },
    h("div", { class: "card" }, h("header", {}, h("h2", {}, "Appearance")), h("div", { class: "row" }, theme), h("div", { class: "note", style: "margin-top:.4rem" }, "You can also click the logo in the top-left corner to switch between these.")),
    h("div", { class: "card" }, h("header", {}, h("h2", {}, "Simple or Advanced")), h("div", { class: "row" }, modeSwitch()),
      h("div", { class: "note", style: "margin-top:.4rem" }, "Simple shows what most people need. Advanced shows every rclone option. It only changes what is shown, never what a job does.")),
    h("div", { id: "cfg-slot" }),
    h("div", { class: "card" }, h("header", {}, h("h2", {}, "rclone"), h("span", { class: "chip " + (S.rcloneVersion ? "ok" : "bad") }, S.rcloneVersion || "not found")),
      field("Path to rclone", rc, "Press Re-detect after changing this."), h("div", { class: "row", style: "margin-top:.5rem" },
        h("button", { onclick: async () => { await must("save_settings", st); const r = await must("reload_remotes"); if (r) { S.remotes = r; const s = await must("app_state"); if (s) { S.rcloneVersion = s.rclone_version; } toast("rclone detected again.", "ok"); pageSettings(); } } }, "Re-detect"))),
    h("div", { class: "card" }, h("header", {}, h("h2", {}, "Background")),
      sw(st.tray_on_close, (v) => { st.tray_on_close = v; save(); }, "Keep running in the background when the window is closed", "Only while at least one schedule is on. A tray icon is shown if the optional pystray package is installed; otherwise the window just minimises.")),
    h("div", { class: "card" }, h("header", {}, h("h2", {}, "New jobs")), field("Disk type to assume for new jobs", disk)),
    h("div", { class: "card" }, h("header", {}, h("h2", {}, "Encrypted remotes"), h("button", { onclick: () => cryptDialog().then(pageSettings) }, icon("lock"), "New encrypted remote…")),
      h("div", { class: "row" }, S.remotes.filter((r) => r.crypt).map((r) => h("span", { class: "chip gold" }, icon("lock"), r.name)), S.remotes.some((r) => r.crypt) ? null : h("span", { class: "note" }, "None yet."))),
    h("div", { class: "card" }, h("header", {}, h("h2", {}, "Your data")),
      h("div", { class: "row" }, h("button", { onclick: importJobs }, icon("import"), "Import jobs…"), h("button", { onclick: () => exportDialog() }, icon("export"), "Export jobs…")),
      h("div", { class: "row", style: "margin-top:.5rem" }, h("button", { onclick: () => must("open_path", "data") }, icon("folder"), "Open data folder"), h("button", { onclick: () => must("open_path", "logs") }, icon("list"), "Open logs folder"), h("button", { onclick: aboutDialog }, icon("mail"), "About / Contact dev"))))));
  configCard().then((c) => $("#cfg-slot")?.replaceWith(c));
}

// ═══ Bottom pane: running tasks and the console ════════════════════════════════════
const cons = { run: "", next: 0, lines: 0 };
function renderBottom() {
  const b = $("#bottom");
  b.classList.toggle("collapsed", !S.bottomOpen);
  if (S.bottomOpen) b.style.setProperty("--bottom-h", lsGet("rsg-bottom-h", "230") + "px");
  const live = S.runs.filter((r) => ["running", "stopping", "mounting", "mounted"].includes(r.state)).length;
  const sel = h("select", { "aria-label": "Run shown in the console" }, S.runs.length ? S.runs.slice().reverse().map((r) => h("option", { value: r.id, selected: r.id === S.bottomSel }, `${r.name} · ${r.real ? "real run" : r.kind === "mount" ? "mount" : "preview"} · ${STATE_TEXT[r.state] || r.state}`)) : h("option", {}, "No runs yet"));
  sel.addEventListener("change", () => { S.bottomSel = sel.value; cons.run = ""; renderBottom(); });
  const tab = (id, label, extra) => h("button", { class: "t", role: "tab", "aria-selected": String(S.bottomTab === id), onclick: () => { S.bottomTab = id; S.bottomOpen = true; renderBottom(); } }, label, extra);
  const head = h("div", { class: "bhead" }, tab("runs", "Tasks", live ? h("span", { class: "chip gold", style: "margin-left:.4rem" }, live) : null), tab("console", "Console"),
    S.bottomTab === "console" && S.bottomOpen ? sel : null, h("span", { class: "grow" }),
    S.bottomTab === "console" && S.bottomOpen ? h("button", { class: "ghost sm", title: "Stop the selected run (same as pressing Ctrl+C in the console)", onclick: () => interrupt() }, icon("stop"), "Ctrl+C") : null,
    live > 1 ? h("button", { class: "ghost sm", title: "Stop every running task", onclick: async () => { if (await confirmBox("Stop all tasks?", h("p", {}, `${live} tasks are running. They will all be stopped. Files that are already finished are kept.`), "Stop all", true)) { await must("stop_all"); await pollNow(); } } }, icon("stop"), "Stop all") : null,
    S.bottomOpen && S.runs.some((r) => !["running", "stopping", "mounting", "mounted"].includes(r.state)) ? h("button", { class: "ghost sm", onclick: async () => { await must("clear_finished"); await pollNow(); } }, "Clear finished") : null,
    h("button", { class: "ghost icon sm", title: S.bottomOpen ? "Collapse" : "Expand", "aria-label": S.bottomOpen ? "Collapse" : "Expand", onclick: () => { S.bottomOpen = !S.bottomOpen; renderBottom(); } }, icon(S.bottomOpen ? "chev" : "up")));
  const grip = h("div", { class: "grip", title: "Drag to resize" });
  grip.addEventListener("pointerdown", (e) => {
    grip.setPointerCapture(e.pointerId); const y0 = e.clientY, h0 = b.getBoundingClientRect().height;
    const move = (ev) => { const nh = Math.max(120, Math.min(innerHeight * .7, h0 + (y0 - ev.clientY))); b.style.setProperty("--bottom-h", nh + "px"); lsSet("rsg-bottom-h", String(Math.round(nh))); };
    const up = () => { grip.removeEventListener("pointermove", move); grip.removeEventListener("pointerup", up); };
    grip.addEventListener("pointermove", move); grip.addEventListener("pointerup", up);
  });
  const body = h("div", { class: "bbody" });
  if (S.bottomOpen) body.append(S.bottomTab === "runs" ? runsList() : consolePane());
  b.replaceChildren(S.bottomOpen ? grip : "", head, body);
  if (S.bottomOpen && S.bottomTab === "console") pullConsole(true);
}
function runCard(r) {
  const pct = r.total ? Math.min(100, Math.round((r.bytes / r.total) * 100)) : (r.state === "done" ? 100 : 0);
  const live = ["running", "stopping", "mounting", "mounted"].includes(r.state);
  const chipCls = r.state === "done" ? "ok" : r.state === "failed" ? "bad" : live ? "gold" : "";
  const card = h("div", { class: "rcard" + (r.id === S.bottomSel ? " sel" : "") },
    h("div", { class: "top" }, icon(r.kind === "mount" ? "drive" : r.mode), h("b", {}, r.name), h("span", { class: "chip " + chipCls }, r.kind === "mount" ? r.state : (r.real ? "" : "preview ") + (STATE_TEXT[r.state] || r.state).toLowerCase()),
      live ? h("button", { class: "ghost icon sm", title: "Stop", onclick: (e) => { e.stopPropagation(); must("stop", r.id); } }, icon("stop")) : null),
    r.kind === "mount" ? h("div", { class: "meta" }, h("span", {}, r.mountpoint)) : (r.real ? [h("div", { class: "bar" }, h("i", { style: `width:${pct}%` })),
      h("div", { class: "meta" }, h("span", {}, `${pct}%`), h("span", {}, `${bytes(r.bytes)} / ${bytes(r.total)}`), live ? h("span", {}, `${bytes(r.speed)}/s`) : null, live && r.eta != null ? h("span", {}, "left " + dur(r.eta)) : null, !live ? h("span", {}, r.summary || "") : null, r.errors ? h("span", { style: "color:var(--bad)" }, r.errors + " errors") : null)]
      : [h("div", { class: "meta" }, h("span", {}, `${r.checks} checked`), h("span", {}, `${(r.counts || {}).upload || 0} would copy`), !live ? h("span", {}, r.summary || "") : null, r.errors ? h("span", { style: "color:var(--bad)" }, r.errors + " errors") : null)]));
  card.addEventListener("click", () => { S.bottomSel = r.id; S.bottomTab = "console"; cons.run = ""; renderBottom(); });
  card.addEventListener("dblclick", () => { if (r.job_id) { S.sel = r.job_id; S.view = "job"; S.tab = "run"; S.watch[r.job_id] = r.id; renderAll(); } });
  return card;
}
function runsList() {
  if (!S.runs.length) return h("div", { class: "empty" }, "Nothing is running. Tasks you start appear here, and several can run at the same time.");
  return h("div", { class: "runs", id: "runs-list" }, S.runs.slice().reverse().map(runCard));
}
function consolePane() {
  const run = S.runs.find((r) => r.id === S.bottomSel);
  const pre = h("pre", { class: "console", id: "console", tabindex: "0", "aria-label": "rclone console" });
  pre.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c" && !String(getSelection()).length) { e.preventDefault(); interrupt(); }
  });
  const foot = h("div", { class: "bfoot", id: "cfoot" }, run ? statsLine(run) : "Choose a run above to see rclone's own output. Press Ctrl+C here to stop it.");
  return h("div", { class: "cwrap" }, pre, foot);
}
function statsLine(r) {
  const pct = r.total ? Math.round((r.bytes / r.total) * 100) : 0;
  if (r.kind !== "mount" && !r.real) return `Preview: ${r.checks} files checked, ${(r.counts || {}).upload || 0} would be copied, ${r.errors} errors`;
  return `Copied ${bytes(r.bytes)} of ${bytes(r.total)} (${pct}%), ${bytes(r.speed)}/s, ${r.transfers} files copied, ${r.checks} checked, ${r.errors} errors`;
}
async function interrupt() {
  const r = S.runs.find((x) => x.id === S.bottomSel);
  if (!r || !["running", "mounted", "mounting"].includes(r.state)) return toast("Nothing is running in this console.");
  await must("stop", r.id); toast("Stopping “" + r.name + "”…");
}
let pulling = null;
function pullConsole(reset) {
  pulling = (pulling || Promise.resolve()).then(() => pullConsoleNow(reset)).catch(() => {});
  return pulling;
}
async function pullConsoleNow(reset) {
  const pre = $("#console"); if (!pre || !S.bottomSel) return;
  if (reset || cons.run !== S.bottomSel) { cons.run = S.bottomSel; cons.next = 0; pre.replaceChildren(); }
  const r = await call("console_lines", S.bottomSel, cons.next);
  if (!r.ok || cons.run !== S.bottomSel) return;
  if (r.data.reset) pre.replaceChildren();
  const stick = pre.scrollHeight - pre.scrollTop - pre.clientHeight < 40;
  const frag = document.createDocumentFragment();
  for (const line of r.data.lines) {
    const m = /^\d{4}\/\d\d\/\d\d \d\d:\d\d:\d\d (\w+)/.exec(line);
    frag.append(h("span", { class: "l " + (m ? m[1] : "") }, line));
  }
  pre.append(frag);
  while (pre.childElementCount > 3000) pre.firstElementChild.remove();
  cons.next = r.data.next;
  if (stick) pre.scrollTop = pre.scrollHeight;
}
