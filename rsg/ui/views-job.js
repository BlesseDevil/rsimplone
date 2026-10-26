// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)
// Licensed under the GNU AGPL v3 or any later version; see <https://www.gnu.org/licenses/>. No warranty.
// Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
// The domain probably expired because HE's TOO BROKE TO RENEW IT.
// Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
// and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"use strict";
// The job page: name + actions on top, then Setup / Config / Schedule / Run tabs.

const MODE_LABEL = { copy: "Copy", sync: "Sync", move: "Move" };
const MODE_TEXT = {
  copy: "Adds new and changed files. Never deletes anything.",
  sync: "Mirrors the source. Anything replaced or removed goes into the backup folder, never lost.",
  move: "Transfers files, then removes the originals. Always preview with a dry run first.",
};
const DERIVED = ["problems", "schedule_text", "next_run", "dest_text", "crypt", "busy", "move_ready", "last_run", "last_mode", "last_code", "last_summary", "dry_sig", "dry_ts"];

const curJob = () => S.jobs.find((j) => j.id === S.sel);
const runsOf = (jobId) => S.runs.filter((r) => r.job_id === jobId);
const lastRun = (jobId) => runsOf(jobId).slice(-1)[0];
const isLive = (r) => r && (r.state === "running" || r.state === "stopping");

// ── saving ─────────────────────────────────────────────────────────────────────────
const dirty = new Set();
const flushSave = debounce(async () => {
  for (const id of [...dirty]) {
    dirty.delete(id);
    const job = S.jobs.find((j) => j.id === id);
    if (!job) continue;
    const r = await call("save_job", job);
    if (!r.ok) { toast(r.error, "bad"); continue; }
    for (const k of DERIVED) job[k] = r.data[k];
    job.flags = r.data.flags; job.schedule = r.data.schedule;
    if (id === S.sel) refreshDerived();
    renderRail();
  }
}, 450);
function patch(job, changes, rerender) {
  Object.assign(job, changes);
  dirty.add(job.id); flushSave(); renderRail();
  if (rerender) renderJobBody();
  else refreshDerived();
}
function refreshDerived() {
  const job = curJob(); if (!job) return;
  const box = $("#problems"); if (box) fillProblems(box, job);
  const run = $("#hdr-actions"); if (run) fillActions(run, job);
}

// ── page shell ────────────────────────────────────────────────────────────────────────
function renderJobPage() {
  const page = $("#page"); const job = curJob();
  if (!job) {
    page.replaceChildren(h("div", { class: "empty", style: "margin:auto;align-self:center" },
      h("img", { class: "logo-big", id: "empty-logo", src: resolvedTheme(S.theme) === "dark" ? "brand/emblem-gold.png" : "brand/emblem.png", alt: "" }),
      h("h2", {}, "No job selected"),
      h("p", {}, "Create one with + New, or pick a job on the left."),
      h("div", { class: "row", style: "justify-content:center" },
        ["copy", "sync", "move"].map((m) => h("button", { class: m === "copy" ? "primary" : "", onclick: () => newJob(m) }, icon("plus"), MODE_LABEL[m])))));
    page.style.gridTemplateRows = "1fr";
    return;
  }
  page.style.gridTemplateRows = "auto auto minmax(0, 1fr)";
  const name = h("input", { class: "name", value: job.name, "aria-label": "Job name", title: "Click to rename", spellcheck: "false" });
  name.addEventListener("input", () => patch(job, { name: name.value }));
  name.addEventListener("keydown", (e) => { if (e.key === "Enter") name.blur(); });
  const head = h("div", { class: "jobhead" }, name, h("span", { class: "chip " + (job.mode === "move" ? "bad" : job.mode === "sync" ? "gold" : "") }, MODE_LABEL[job.mode]),
    h("div", { class: "row", id: "hdr-actions" }));
  const tabs = h("div", { class: "tabs", role: "tablist" });
  for (const [id, label] of [["setup", "Setup"], ["config", "Config"], ["schedule", "Schedule"], ["run", "Run"]]) {
    const live = id === "run" && isLive(lastRun(job.id));
    tabs.append(h("button", { role: "tab", "aria-selected": String(S.tab === id), onclick: () => { S.tab = id; renderJobPage(); } }, label, live ? h("span", { class: "dotlive" }) : null));
  }
  page.replaceChildren(head, tabs, h("div", { class: "view", id: "jobview" }));
  fillActions($("#hdr-actions"), job);
  renderJobBody();
}
function renderJobBody() {
  const job = curJob(); const view = $("#jobview"); if (!job || !view) return;
  const top = view.scrollTop;
  const build = { setup: tabSetup, config: tabConfig, schedule: tabSchedule, run: tabRun }[S.tab] || tabSetup;
  view.replaceChildren(build(job));
  view.scrollTop = top;
  refreshDerived();
}
function fillActions(box, job) {
  const live = isLive(lastRun(job.id)) || job.busy;
  const blocked = (job.problems || []).length > 0;
  const real = job.mode === "move" ? "Move for real…" : job.mode === "sync" ? "Sync for real…" : "Copy for real…";
  box.replaceChildren(...(live ? [h("button", { class: "danger", onclick: () => stopLatest(job) }, icon("stop"), "Stop")]
    : [h("button", { class: "safe", disabled: blocked, title: blocked ? "Fix the problems first" : "Preview only. Nothing is changed.", onclick: () => startJob(job, false) }, icon("play"), "Dry run"),
       h("button", { class: "danger", disabled: blocked, title: blocked ? "Fix the problems first" : "Runs for real. You'll confirm by typing " + S.confirmWord, onclick: () => startJob(job, true) }, real)]));
}

// ── actions ──────────────────────────────────────────────────────────────────────────────
async function newJob(mode) {
  const job = await must("new_job", mode); if (!job) return;
  S.jobs.push(job); S.sel = job.id; S.view = "job"; S.tab = "setup"; renderAll();
}
async function stopLatest(job) {
  const r = lastRun(job.id); if (r) { await must("stop", r.id); toast("Stopping… (Ctrl+C sent)"); }
}
async function startJob(job, real) {
  if ((job.problems || []).length) return toast(job.problems[0], "bad");
  let confirm = "";
  if (real) {
    const body = h("div", {}, h("p", {}, `${MODE_LABEL[job.mode]} "${job.name}" will change real files.`),
      job.mode === "move" ? h("div", { class: "warnbox" }, h("b", {}, "Move removes the originals "), "once they are transferred. Files replaced at the destination go to the backup folder, if you set one.") : null,
      h("p", { class: "note" }, `${job.source} → ${job.dest_text}`));
    const word = await typedConfirm("Run for real?", body, S.confirmWord, "Run now");
    if (!word) return; confirm = word;
  }
  const id = await must("start", job.id, real, confirm); if (!id) return;
  S.watch[job.id] = id; S.tab = "run"; S.bottomSel = id; S.bottomOpen = true;
  await pollNow(); renderAll();
}

// ═════════════════════════════════════════════════════════════════════════════════════
// Setup
// ═════════════════════════════════════════════════════════════════════════════════════
function field(label, ctl, hint) { return h("label", { class: "f" }, label, ctl, hint ? h("span", { class: "note", style: "font-weight:400" }, hint) : null); }
function inputFor(job, key, props) {
  const { after, ...attrs } = props || {};
  const el = h("input", { value: job[key] ?? "", spellcheck: "false", autocomplete: "off", ...attrs });
  el.addEventListener("input", () => { patch(job, { [key]: el.value }); if (after) after(el.value); });
  return el;
}
function verdictLine(id) { return h("div", { class: "verdict", id }); }
function setVerdict(id, cls, iconName, text) {
  const el = $("#" + id); if (!el) return;
  el.className = "verdict " + cls; el.replaceChildren(iconName ? icon(iconName) : "", h("span", {}, text));
}

function tabSetup(job) {
  const local = job.dest_kind === "local";
  const stack = h("div", { class: "stack" });

  // mode
  const seg = h("div", { class: "seg", role: "group" }, ["copy", "sync", "move"].map((m) =>
    h("button", { class: m, "aria-pressed": String(job.mode === m), onclick: () => patch(job, { mode: m }, true) }, icon(m), MODE_LABEL[m])));
  stack.append(h("div", { class: "card" }, h("header", {}, h("h2", {}, "Job type"), seg),
    h("div", { class: "note" }, MODE_TEXT[job.mode]),
    job.mode === "move" ? h("div", { class: "warnbox", style: "margin-top:.6rem" }, icon("alert"), " Move removes the originals after transfer. A real run unlocks only after a dry run of this exact job (good for 24 h).",
      job.move_ready ? h("div", { class: "chip ok", style: "margin-left:.4rem" }, "dry run done") : null) : null));

  // source
  const srcIn = inputFor(job, "source", { placeholder: "Paste or browse to the folder to back up", after: debounce(() => checkSource(job), 600) });
  stack.append(h("div", { class: "card" }, h("header", {}, h("h2", {}, "Source")),
    h("div", { class: "row" }, h("div", { class: "grow" }, srcIn),
      h("button", { onclick: async () => { const p = await must("pick_folder", job.source); if (p) { srcIn.value = p; patch(job, { source: p }); checkSource(job); } } }, icon("folder"), "Browse…")),
    verdictLine("v-source"), h("div", { class: "row", id: "disk-row", style: "margin-top:.3rem" })));

  // destination
  const where = h("div", { class: "seg" },
    h("button", { "aria-pressed": String(!local), onclick: () => patch(job, { dest_kind: "remote" }, true) }, icon("cloud"), "Cloud remote"),
    h("button", { "aria-pressed": String(local), onclick: () => patch(job, { dest_kind: "local" }, true) }, icon("folder"), "Local folder"));
  const dest = h("div", { class: "card" }, h("header", {}, h("h2", {}, "Destination"), where));
  if (!local) {
    const sel = h("select", {}, h("option", { value: "" }, "Choose a remote…"),
      S.remotes.map((r) => h("option", { value: r.name, selected: r.name === job.remote }, (r.crypt ? "🔒 " : "") + r.name + "  ·  " + r.type)));
    sel.addEventListener("change", () => patch(job, { remote: sel.value, target: "", backup_root: "" }, true));
    dest.append(h("div", { class: "row" }, h("div", { class: "grow" }, sel),
      h("button", { class: "ghost", title: "Re-read the remote list", onclick: async () => { const r = await must("reload_remotes"); if (r) { S.remotes = r; renderJobBody(); toast("Remotes refreshed"); } } }, "Refresh"),
      h("button", { onclick: () => cryptDialog(job) }, icon("lock"), "New encrypted remote…")));
    if (job.crypt) dest.append(h("div", { class: "note", style: "margin-top:.4rem" }, icon("lock"), " Encrypted remote: names and contents are scrambled before upload. Encrypted data can't be hashed, so files are compared by size and time."));
  }
  const pickBtn = (key) => h("button", { onclick: () => pickFolder(job, key) }, icon("folder"), "Pick…");
  const tgt = inputFor(job, "target", { placeholder: local ? "Full path of the destination" : "e.g. Backups/Photos", after: debounce(() => checkDest(job), 600) });
  dest.append(h("div", { class: "grid2", style: "margin-top:.7rem" },
    h("div", { class: "stack", style: "gap:.3rem" }, h("label", { class: "f" }, "Destination folder"), h("div", { class: "row" }, h("div", { class: "grow" }, tgt), pickBtn("target")), verdictLine("v-target")),
    h("div", { class: "stack", style: "gap:.3rem" }, h("label", { class: "f" }, job.mode === "copy" || job.mode === "move" ? "Backup folder · optional" : "Backup folder · required"),
      h("div", { class: "row" }, h("div", { class: "grow" }, inputFor(job, "backup_root", { placeholder: local ? "Full path" : "e.g. Backups/_old", after: debounce(() => checkDest(job), 600) })), pickBtn("backup_root")), verdictLine("v-backup"))));
  dest.append(h("div", { class: "note", style: "margin-top:.5rem" }, "Replaced or removed files go to ", h("code", {}, "<backup>/<source name>/<YYYYMMDD-HHMM>/"), " on the same remote: instant, no re-upload."));
  stack.append(dest);

  stack.append(h("div", { id: "problems" }));
  stack.append(previewCard(job));
  setTimeout(() => { checkSource(job); checkDest(job); }, 0);
  return stack;
}

async function checkSource(job) {
  if (job.id !== S.sel || !$("#v-source")) return;
  if (!job.source.trim()) { setVerdict("v-source", "", null, ""); $("#disk-row")?.replaceChildren(); return; }
  const info = await must("path_info", job.source); if (!info || job.id !== S.sel) return;
  setVerdict("v-source", info.exists ? "ok" : "bad", info.exists ? "check" : "alert",
    info.exists ? `Found${info.free ? " · " + info.free + " free of " + info.total : ""}` : "Can't find this folder.");
  const row = $("#disk-row"); if (!row) return;
  row.replaceChildren();
  if (info.disk && info.disk !== job.disk) { patch(job, { disk: info.disk }); toast(`Detected ${info.disk.toUpperCase()} for this folder; tuning updated.`); }
  if (info.disk) row.append(h("span", { class: "chip ok" }, `Detected ${info.disk.toUpperCase()}`));
  else if (info.exists) row.append(h("span", { class: "chip" }, "Disk type: can't tell"), h("span", { class: "note" }, `Using ${job.disk.toUpperCase()} settings. USB drives often misreport their type, so set it in Config if needed.`));
}
async function checkDest(job) {
  if (job.id !== S.sel || !$("#v-target")) return;
  if (job.dest_kind === "local") {
    for (const [key, vid] of [["target", "v-target"], ["backup_root", "v-backup"]]) {
      const p = (job[key] || "").trim();
      if (!p) { setVerdict(vid, "", null, key === "backup_root" && job.mode !== "sync" ? "No backup folder: replaced files are overwritten." : ""); continue; }
      const info = await must("path_info", p); if (!info) continue;
      setVerdict(vid, info.exists ? "ok" : "warn", info.exists ? "check" : "alert",
        (info.exists ? "Found" : "New folder, will be created") + (info.free ? ` · ${info.free} free of ${info.total}` : ""));
    }
  } else {
    const v = job._verdict;
    for (const [key, vid] of [["target", "v-target"], ["backup_root", "v-backup"]]) {
      const x = v && v[key === "target" ? "target" : "backup"];
      if (!x) setVerdict(vid, "", null, job[key] ? "Not checked yet · Config → Check folders" : "");
      else setVerdict(vid, x.state === "exists" ? "ok" : x.state === "missing" ? "warn" : "", x.state === "exists" ? "check" : "alert",
        x.state === "exists" ? "Found on the remote" : x.state === "missing" ? "New folder, will be created" + (x.near ? ` (did you mean ${x.near}?)` : "") : "Too deep to verify cheaply");
    }
  }
}
function fillProblems(box, job) {
  const p = job.problems || [];
  box.replaceChildren();
  if (!p.length) return;
  box.className = "problems";
  box.append(h("b", {}, "Fix before running"), h("ul", {}, p.map((t) => h("li", {}, t))));
}
function previewCard(job) {
  const pre = h("div", { class: "pre", hidden: true });
  const btn = h("button", { class: "ghost sm" }, icon("code"), "Show the rclone command");
  btn.addEventListener("click", async () => {
    if (!pre.hidden) { pre.hidden = true; return; }
    const r = await must("preview", job.id); if (!r) return;
    pre.textContent = r.dry + "\n\n# real run: same without --dry-run"; pre.hidden = false;
  });
  return h("div", { class: "row" }, btn, pre);
}
async function pickFolder(job, key) {
  if (job.dest_kind === "local") {
    const p = await must("pick_folder", job[key]); if (p) { patch(job, { [key]: p }, true); }
    return;
  }
  if (!job.remote) return toast("Choose a remote first.", "bad");
  const dirs = await must("folders", job.remote, Math.max(1, job.list_depth || 1)); if (!dirs) return;
  const chosen = await folderPicker(job.remote, dirs);
  if (chosen != null) patch(job, { [key]: chosen }, true);
}
function folderPicker(remote, dirs) {
  return dialog((close) => {
    const list = h("div", { class: "pick-list" });
    const filter = h("input", { placeholder: "Filter folders…" });
    const paint = () => {
      const q = filter.value.toLowerCase();
      list.replaceChildren(...dirs.filter((d) => d.toLowerCase().includes(q)).slice(0, 400).map((d) => h("button", { onclick: () => close(d) }, icon("folder"), d)));
      if (!list.children.length) list.append(h("div", { class: "empty" }, "No folders match."));
    };
    filter.addEventListener("input", paint); paint(); setTimeout(() => filter.focus(), 30);
    return h("div", {}, h("h2", {}, `Folders on ${remote}:`), filter, list,
      h("p", { class: "note" }, "One listing of the remote, reused for 15 minutes. You can also type any path in the box."),
      h("div", { class: "btns" }, h("button", { onclick: () => close(null) }, "Cancel")));
  }).then((v) => (v === undefined ? null : v));
}
function cryptDialog() {
  return dialog((close) => {
    const name = h("input", { placeholder: "vault", autocomplete: "off" });
    const base = h("select", {}, S.remotes.filter((r) => !r.crypt).map((r) => h("option", { value: r.name + ":" }, r.name)));
    const sub = h("input", { placeholder: "Folder inside it, e.g. Encrypted (optional)" });
    const pw = h("input", { type: "password", autocomplete: "new-password" });
    const salt = h("input", { type: "password", autocomplete: "new-password", placeholder: "optional, recommended" });
    const fn = h("select", {}, h("option", { value: "standard" }, "Encrypt file names (standard)"), h("option", { value: "obfuscate" }, "Obfuscate file names"), h("option", { value: "off" }, "Keep file names readable"));
    const dirs = h("input", { type: "checkbox", checked: true });
    const msg = h("div", { class: "note" });
    const ok = h("button", { class: "primary", onclick: async () => {
      ok.disabled = true; msg.textContent = "Creating…";
      const target = base.value + (sub.value.trim() ? sub.value.trim().replace(/^\/+/, "") : "");
      const r = await call("create_crypt", name.value, target, pw.value, salt.value, fn.value, dirs.checked);
      pw.value = salt.value = "";
      if (!r.ok) { msg.textContent = r.error; msg.style.color = "var(--bad)"; ok.disabled = false; return; }
      S.remotes = r.data; toast(`Encrypted remote "${name.value}" created.`, "ok"); close(true);
    } }, "Create");
    return h("div", { class: "stack" }, h("h2", {}, "New encrypted remote (rclone crypt)"),
      h("p", { class: "note" }, "Files are encrypted here before they reach the remote. Keep the password safe: without it the data is unreadable. rSimpLone never stores it."),
      field("Name", name), field("Store it in", base), sub, field("Password", pw), field("Salt password", salt), fn,
      h("label", { class: "chk" }, dirs, "Encrypt folder names too"), msg,
      h("div", { class: "btns" }, h("button", { onclick: () => close(false) }, "Cancel"), ok));
  }).then(() => renderJobBody());
}

// ═════════════════════════════════════════════════════════════════════════════════════
// Config
// ═════════════════════════════════════════════════════════════════════════════════════
const fl = { q: "", group: "Common", only: false };
function sw(checked, onchange, label, sub) {
  const inp = h("input", { type: "checkbox", checked: !!checked }); inp.addEventListener("change", () => onchange(inp.checked));
  return h("label", { class: "sw" }, h("span", { class: "switch" }, inp, h("i")), h("span", {}, label, sub ? h("small", {}, sub) : null));
}
function tabConfig(job) {
  const local = job.dest_kind === "local";
  const stack = h("div", { class: "stack" });
  // profile
  const disk = h("div", { class: "seg" }, ["hdd", "ssd"].map((d) => h("button", { "aria-pressed": String(job.disk === d), onclick: () => patch(job, { disk: d }, true) }, d.toUpperCase())));
  const num = (key, label, hint, step) => field(label, inputFor(job, key, { type: "number", min: 0, step: step || 1 }), hint);
  const num2 = (key, label, hint) => { const el = h("input", { type: "number", min: 0, value: job[key] }); el.addEventListener("input", () => patch(job, { [key]: Number(el.value) || 0 })); return field(label, el, hint); };
  stack.append(h("div", { class: "card" }, h("header", {}, h("h2", {}, "Speed profile")),
    h("div", { class: "grid2" },
      field("Source disk", disk, job.disk === "hdd" ? "Few readers; every check finishes before copying so the disk never thrashes." : "More parallel readers and transfers. Best for SSDs."),
      num2("checkers", "Checkers (0 = automatic)", "Parallel file checks."), num2("transfers", "Transfers (0 = automatic)", "Parallel file copies.")),
    local ? h("div", { class: "note", style: "margin-top:.6rem" }, "Line speed and Drive options apply to cloud destinations.") :
      h("div", { class: "grid2", style: "margin-top:.7rem" },
        num2("bw_mbps", "Line speed (Mbit/s)", "Your upload speed."), num2("bw_percent", "Use this share of it (%)", "Leaves headroom for everyone else."),
        sw(job.no_bw_limit, (v) => patch(job, { no_bw_limit: v }), "No speed limit"))));
  // behaviour
  const beh = [];
  if (!local) beh.push(sw(job.api_low, (v) => patch(job, { api_low: v }), "Fewest Drive API calls", "One recursive listing, large chunks, a steady request rate."),
    sw(job.no_dir_modtime, (v) => patch(job, { no_dir_modtime: v }), "Don't update folder dates on the remote", "Saves one small call per changed folder. File checks are unaffected."));
  if (job.mode === "copy") beh.push(sw(job.skip_existing, (v) => patch(job, { skip_existing: v }), "Skip files that already exist", "Never touches files already at the destination, even if they changed."));
  stack.append(h("div", { class: "card" }, h("header", {}, h("h2", {}, "Behaviour")), h("div", { class: "stack" }, beh,
    field("Backup sub-folder name", inputFor(job, "label", { placeholder: "Default: name of the source folder" }), "Backups land in <backup>/<this name>/<date-time>/"))));
  // tools
  const tools = [h("button", { onclick: async () => { const r = await must("preview", job.id); if (r) { try { await navigator.clipboard.writeText(r.dry); toast("Dry-run command copied.", "ok"); } catch { toast(r.dry); } } } }, icon("copy"), "Copy command"),
    h("button", { onclick: async () => { const r = await must("export_script", job.id); if (r) toast("Script saved: " + r.path, "ok"); } }, icon("code"), "Export script")];
  if (!local) tools.unshift(h("button", { onclick: async () => {
    job._verdict = await must("check_job", job.id, true); toast(job._verdict ? "Checked with one listing of the remote." : "", "ok"); }}, icon("search"), "Check folders (1 API call)"));
  const depth = h("input", { type: "number", min: 1, max: 6, value: job.list_depth || 1 }); depth.addEventListener("input", () => patch(job, { list_depth: Math.max(1, Number(depth.value) || 1) }));
  stack.append(h("div", { class: "card" }, h("header", {}, h("h2", {}, "Tools")), h("div", { class: "row" }, tools, local ? null : h("label", { class: "f", style: "width:9rem" }, "Folder check depth", depth))));
  // flags
  stack.append(flagsCard(job));
  return stack;
}

function flagsCard(job) {
  const cat = S.catalogue.filter((f) => !f.denied);
  const groups = ["Common", ...new Set(cat.map((f) => f.group))];
  const COMMON = new Set(["--bwlimit", "--transfers", "--checkers", "--exclude", "--include", "--filter", "--max-age", "--min-age", "--max-size", "--min-size", "--checksum", "--size-only", "--ignore-times", "--update", "--immutable",
    "--max-transfer", "--max-duration", "--retries", "--low-level-retries", "--timeout", "--contimeout", "--tpslimit", "--buffer-size", "--multi-thread-streams", "--fast-list", "--no-traverse", "--delete-empty-src-dirs", "--order-by", "--metadata", "--links", "--exclude-from", "--include-from", "--files-from",
    "--ignore-existing", "--no-check-dest", "--modify-window", "--use-server-modtime", "--drive-chunk-size", "--drive-upload-cutoff", "--drive-acknowledge-abuse", "--drive-skip-gdocs", "--drive-use-trash"]);
  const wrap = h("div", { class: "card" });
  const search = h("input", { placeholder: "Search every rclone flag (name or description)…", value: fl.q });
  const chips = h("div", { class: "chips" });
  const list = h("div", { class: "flaglist" });
  const modCount = () => Object.keys(job.flags || {}).length;
  const paint = () => {
    chips.replaceChildren(...groups.map((g) => h("button", { "aria-pressed": String(fl.group === g), onclick: () => { fl.group = g; paint(); } }, g)),
      h("button", { "aria-pressed": String(fl.only), onclick: () => { fl.only = !fl.only; paint(); } }, `Changed (${modCount()})`));
    const q = fl.q.trim().toLowerCase();
    let rows = cat;
    if (fl.only) rows = rows.filter((f) => f.name in (job.flags || {}));
    else if (q.length >= 2) rows = rows.filter((f) => f.name.includes(q) || f.help.toLowerCase().includes(q));
    else if (fl.group === "Common") rows = rows.filter((f) => COMMON.has(f.name));
    else rows = rows.filter((f) => f.group === fl.group);
    const shown = rows.slice(0, 120);
    list.replaceChildren(...shown.map((f) => flagRow(job, f, paint)));
    if (!shown.length) list.append(h("div", { class: "empty" }, S.catalogue.length ? "No flags match." : "rclone's flag list is not available (is rclone installed?)."));
    if (rows.length > shown.length) list.append(h("div", { class: "note", style: "padding:.6rem .8rem" }, `Showing ${shown.length} of ${rows.length}. Search to narrow it down.`));
  };
  search.addEventListener("input", () => { fl.q = search.value; paint(); });
  const extra = h("input", { value: job.extra || "", placeholder: "Anything else, e.g. --exclude '*.tmp' --max-age 30d", spellcheck: "false" });
  extra.addEventListener("input", () => patch(job, { extra: extra.value }));
  wrap.append(h("header", {}, h("h2", {}, "rclone flags"), h("span", { class: "note" }, `${cat.length} flags from ${S.rcloneVersion || "rclone"} · hover a row to see what it does`)),
    h("div", { class: "stack" }, search, chips, list, field("Extra flags (free text)", extra, "Flags rSimpLone controls itself (dry run, backup folder, logging, progress) are refused.")));
  paint();
  return wrap;
}
function flagRow(job, f, repaint) {
  const cur = (job.flags || {})[f.name];
  const set = (v) => {
    const flags = { ...(job.flags || {}) };
    if (v === undefined || v === "" || (Array.isArray(v) && !v.length)) delete flags[f.name]; else flags[f.name] = v;
    patch(job, { flags });
  };
  let ctl;
  if (f.type === "bool") {
    ctl = h("select", {}, h("option", { value: "" }, "default"), h("option", { value: "on", selected: cur === true }, "on"), h("option", { value: "off", selected: cur === false }, "off"));
    ctl.addEventListener("change", () => { set(ctl.value === "on" ? true : ctl.value === "off" ? false : undefined); row.classList.toggle("mod", ctl.value !== ""); });
  } else if (f.type === "stringArray") {
    ctl = h("textarea", { rows: 2, placeholder: "one per line", style: "min-height:2.6rem" }, Array.isArray(cur) ? cur.join("\n") : "");
    ctl.addEventListener("input", () => { set(ctl.value.split("\n").map((s) => s.trim()).filter(Boolean)); row.classList.toggle("mod", !!ctl.value.trim()); });
  } else {
    ctl = h("input", { value: cur ?? "", placeholder: f.default ? "default " + f.default : f.type, spellcheck: "false" });
    ctl.addEventListener("input", () => { set(ctl.value.trim() === "" ? undefined : ctl.value.trim()); row.classList.toggle("mod", ctl.value.trim() !== ""); });
  }
  const row = h("div", { class: "flag" + (cur !== undefined ? " mod" : "") }, h("div", { style: "min-width:0" }, h("code", {}, f.name), f.short ? h("span", { class: "muted mono" }, "  " + f.short) : null, h("div", { class: "hp" }, f.help)), ctl);
  tooltip(row, () => h("div", {}, h("b", {}, f.name + (f.short ? ", " + f.short : "")), h("div", {}, f.help), h("dl", { style: "margin-top:.4rem" },
    h("dt", {}, "Type"), h("dd", {}, f.type === "bool" ? "switch" : f.type), h("dt", {}, "Default"), h("dd", {}, f.default || (f.type === "bool" ? "off" : "none")), h("dt", {}, "Group"), h("dd", {}, f.group)),
    h("div", { class: "note", style: "margin-top:.4rem" }, "Only values that differ from the default are saved. A value here overrides what rSimpLone would set from the speed profile.")), 500);
  return row;
}

// ═════════════════════════════════════════════════════════════════════════════════════
// Schedule
// ═════════════════════════════════════════════════════════════════════════════════════
function tabSchedule(job) {
  const s = { ...job.schedule };
  const stack = h("div", { class: "stack" });
  const card = h("div", { class: "card" }, h("header", {}, h("h2", {}, "Run on a schedule"), h("span", { class: "chip " + (s.enabled ? "ok" : "") }, job.schedule_text || "Off")));
  const kind = h("div", { class: "seg" }, [["interval", "Every…"], ["daily", "Daily"], ["weekly", "Weekly"]].map(([k, l]) => h("button", { "aria-pressed": String(s.kind === k), onclick: () => { s.kind = k; rebuild(); } }, l)));
  const every = h("input", { type: "number", min: 5, value: s.every_min || 60 }); every.addEventListener("input", () => { s.every_min = Number(every.value) || 60; });
  const time = h("input", { type: "time", value: s.time || "02:00" }); time.addEventListener("input", () => { s.time = time.value; });
  const days = h("div", { class: "days" }, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d, i) =>
    h("button", { class: "sm", "aria-pressed": String((s.days || []).includes(i)), onclick: (e) => { const set = new Set(s.days || []); set.has(i) ? set.delete(i) : set.add(i); s.days = [...set].sort(); e.currentTarget.setAttribute("aria-pressed", String(set.has(i))); } }, d)));
  const real = h("input", { type: "checkbox", checked: !!s.real }); real.addEventListener("change", () => { s.real = real.checked; rebuild(); });
  const body = h("div", { class: "stack" });
  const rebuild = () => {
    body.replaceChildren(sw(s.enabled, (v) => { s.enabled = v; }, "Schedule is on", "Fires only while rSimpLone is open. Enable background mode in Settings to close the window."),
      h("div", { class: "row" }, kind), s.kind === "interval" ? field("Every (minutes, 5 or more)", every) : h("div", { class: "grid2" }, field("At", time), s.kind === "weekly" ? field("On", days) : null),
      h("label", { class: "chk" }, real, h("span", {}, "Run for real, not just a preview", h("small", {}, "You'll type " + S.confirmWord + " once. Edit the job later and it falls back to dry runs until you confirm again."))),
      job.next_run ? h("div", { class: "note" }, icon("clock"), " Next run: ", job.next_run) : null,
      job.mode === "move" && s.real ? h("div", { class: "warnbox" }, "Scheduled real Moves remove source files without asking again. Check a dry run first.") : null,
      h("div", { class: "row" }, h("button", { class: "primary", onclick: save }, "Save schedule")));
  };
  const save = async () => {
    let confirm = "";
    if (s.enabled && s.real) {
      const word = await typedConfirm("Allow scheduled real runs?", h("p", {}, `“${job.name}” will run for real on its schedule, without asking.`), S.confirmWord, "Allow");
      if (!word) return; confirm = word;
    }
    const r = await must("set_schedule", job.id, s, confirm); if (!r) return;
    for (const k of Object.keys(r)) if (DERIVED.includes(k) || k === "schedule") job[k] = r[k];
    toast(s.enabled ? "Schedule saved: " + r.schedule_text : "Schedule off", "ok"); renderRail(); renderJobBody();
  };
  rebuild();
  card.append(body); stack.append(card);
  return stack;
}

// ═════════════════════════════════════════════════════════════════════════════════════
// Run
// ═════════════════════════════════════════════════════════════════════════════════════
function tabRun(job) {
  const run = (S.watch[job.id] && S.runs.find((r) => r.id === S.watch[job.id])) || lastRun(job.id);
  const stack = h("div", { class: "stack" });
  if (!run) {
    stack.append(h("div", { class: "empty" }, h("h2", {}, "No runs yet"), h("p", {}, "Start with a dry run. It previews everything and changes nothing."),
      job.last_run ? h("p", { class: "note" }, `Last time: ${job.last_run} (${job.last_mode}): ${job.last_summary}`) : null));
    return stack;
  }
  stack.id = "runtab"; stack.dataset.run = run.id;
  stack.append(h("div", { id: "run-top" }), h("div", { id: "run-banner" }), h("div", { class: "card" }, h("header", {}, h("h2", {}, "Activity"),
    h("div", { class: "chips", id: "run-filter" }), h("span", { class: "note", id: "run-feedcount" })), h("div", { class: "feed", id: "run-feed" })));
  updateRunTab(true);
  return stack;
}
const feedFilter = { kind: "all" };
function updateRunTab(force) {
  const root = $("#runtab"); if (!root) return;
  const job = curJob(); const run = S.runs.find((r) => r.id === root.dataset.run); if (!run || !job) return;
  const pct = run.total ? Math.min(100, Math.round((run.bytes / run.total) * 100)) : (run.state === "done" ? 100 : 0);
  const live = isLive(run);
  $("#run-top").replaceChildren(h("div", { class: "card" }, h("header", {},
    h("h2", {}, (run.real ? "Real run" : "Dry run") + " · " + run.state), h("span", { class: "chip" }, dur((run.ended || Date.now() / 1000) - run.started)),
    h("button", { class: "ghost sm", onclick: () => must("open_path", "log", run.id) }, icon("open"), "Open log"),
    live ? h("button", { class: "danger sm", onclick: () => must("stop", run.id) }, icon("stop"), "Stop") : null),
    h("div", { class: "bigbar" }, h("i", { style: `width:${pct}%` })),
    h("div", { class: "stats", style: "margin-top:.7rem" },
      stat(`${pct}%`, "done"), stat(`${bytes(run.bytes)} / ${bytes(run.total)}`, "transferred"), stat(bytes(run.speed) + "/s", "speed"), stat(live ? dur(run.eta) : "-", "eta"),
      stat(run.checks, "checked"), stat(run.transfers, "transfers"), stat(run.counts.backup || 0, "to backup"), stat(run.errors || 0, "errors"))));
  const ban = $("#run-banner"); ban.replaceChildren();
  if (!live && run.summary) {
    const ok = run.code === 0 || run.code === 9;
    ban.append(h("div", { class: "banner " + (ok ? "ok" : "bad") }, h("b", {}, (run.real ? "" : "Dry run: ") + run.summary), h("span", { class: "note" }, `Exit code ${run.code}: ${run.meaning}`),
      run.backup_dir ? h("span", { class: "note mono-sel" }, "Backup folder: " + run.backup_dir) : null,
      !run.real && ok ? h("span", { class: "note" }, job.mode === "move" ? "A real Move is unlocked for 24 hours, until you edit this job." : "Looks right? Run it for real from the top bar.") : null));
  }
  const acts = S.activity[run.id] || [];
  const kinds = ["all", ...new Set(acts.map((a) => a.kind))];
  $("#run-filter").replaceChildren(...kinds.map((k) => h("button", { "aria-pressed": String(feedFilter.kind === k), onclick: () => { feedFilter.kind = k; updateRunTab(true); } }, k)));
  const shown = acts.filter((a) => feedFilter.kind === "all" || a.kind === feedFilter.kind);
  const feed = $("#run-feed");
  if (force || feed.dataset.n !== String(shown.length) + feedFilter.kind) {
    feed.dataset.n = String(shown.length) + feedFilter.kind;
    feed.replaceChildren(...shown.slice(-300).reverse().map((a) => h("div", { class: "it" }, h("span", { class: "k " + a.kind }, a.kind), h("span", { class: "p" }, a.path || a.detail, a.path ? h("span", { class: "muted" }, "  " + a.detail) : null))));
    if (!shown.length) feed.append(h("div", { class: "empty" }, live ? "Waiting for rclone…" : "Nothing to show."));
  }
  $("#run-feedcount").textContent = `${shown.length} item${shown.length === 1 ? "" : "s"}`;
}
function stat(v, l) { return h("div", { class: "stat" }, h("b", {}, v), h("span", {}, l)); }
