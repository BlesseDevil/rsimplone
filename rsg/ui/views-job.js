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
  copy: "Adds new and changed files to the destination. Nothing is ever deleted there.",
  sync: "Makes the destination match the source. Files that are replaced or removed are moved to the backup folder first, not lost.",
  move: "Copies files to the destination, then deletes the originals. Run a preview first.",
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
    h("div", { class: "row tools" },
      h("button", { class: "ghost icon", title: "Duplicate this job", "aria-label": "Duplicate this job", onclick: () => duplicateJob(job) }, icon("dup")),
      h("button", { class: "ghost icon", title: "Export this job to a file", "aria-label": "Export this job", onclick: () => exportDialog([job.id]) }, icon("export")),
      h("button", { class: "ghost icon", title: "Delete this job", "aria-label": "Delete this job", onclick: () => deleteJob(job) }, icon("trash"))),
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
  if (S.tab === "run") updateRunTab(true);      // the page must be in the document before it can be filled
  refreshDerived();
}
function fillActions(box, job) {
  const live = isLive(lastRun(job.id)) || job.busy;
  const blocked = (job.problems || []).length > 0;
  const real = { copy: "Copy now…", sync: "Sync now…", move: "Move now…" }[job.mode];
  box.replaceChildren(...(live ? [h("button", { class: "danger", onclick: () => stopLatest(job) }, icon("stop"), "Stop")]
    : [h("button", { class: "safe", disabled: blocked, title: blocked ? "Fix the problems listed on the Setup tab first." : "Preview what would happen. Nothing is changed.", onclick: () => startJob(job, false) }, icon("play"), "Preview"),
       h("button", { class: "danger", disabled: blocked, title: blocked ? "Fix the problems listed on the Setup tab first." : "Changes real files. You will be asked to type " + S.confirmWord + " to confirm.", onclick: () => startJob(job, true) }, real)]));
}

// ── actions ──────────────────────────────────────────────────────────────────────────────
async function newJob(mode) {
  const job = await must("new_job", mode); if (!job) return;
  S.jobs.push(job); S.sel = job.id; S.view = "job"; S.tab = "setup"; lsSet("rsg-sel", job.id); renderAll();
}
async function duplicateJob(job) {
  const copy = await must("duplicate_job", job.id); if (!copy) return;
  S.jobs.push(copy); S.sel = copy.id; S.view = "job"; S.tab = "setup"; lsSet("rsg-sel", copy.id); renderAll();
  toast(`Duplicated as “${copy.name}”. Its schedule is off.`, "ok");
}
async function deleteJob(job) {
  if (job.busy || isLive(lastRun(job.id))) return toast("Stop this job before deleting it.", "bad");
  const ok = await confirmBox("Delete this job?", h("p", {}, `“${job.name}” will be removed from rSimpLone. Your files and remotes are not touched, and its logs stay on disk.`), "Delete job", true);
  if (!ok) return;
  dirty.delete(job.id);        // a pending autosave of a deleted job would only produce an error
  if (!(await must("delete_job", job.id))) return;
  const i = S.jobs.findIndex((j) => j.id === job.id);
  if (i >= 0) S.jobs.splice(i, 1);
  delete S.watch[job.id];
  S.sel = (S.jobs[i] || S.jobs[i - 1] || {}).id || null; S.tab = "setup"; lsSet("rsg-sel", S.sel || "");
  renderAll(); toast("Job deleted.", "ok");
}
async function stopLatest(job) {
  const r = lastRun(job.id); if (r) { await must("stop", r.id); toast("Stopping… finished files are kept."); }
}
async function startJob(job, real) {
  if ((job.problems || []).length) return toast(job.problems[0], "bad");
  let confirm = "";
  if (real) {
    const body = h("div", {}, h("p", {}, `${MODE_LABEL[job.mode]} “${job.name}” will change real files.`),
      job.mode === "move" ? h("div", { class: "warnbox" }, h("b", {}, "Move deletes the originals "), "after they have been copied. Files replaced at the destination go to the backup folder.") : null,
      h("p", { class: "note mono-sel" }, `${job.source} → ${job.dest_text}`));
    const word = await typedConfirm("Run for real?", body, S.confirmWord, "Run now");
    if (!word) return; confirm = word;
  }
  const id = await must("start", job.id, real, confirm); if (!id) return;
  S.watch[job.id] = id; S.tab = "run"; S.bottomSel = id;
  await pollNow(); renderAll();
}

// ── export / import of job definitions ────────────────────────────────────────────────────
function exportDialog(pre) {
  if (!S.jobs.length) return toast("There are no jobs to export yet.", "bad");
  return dialog((close) => {
    const picked = new Set(pre && pre.length ? pre : S.jobs.map((j) => j.id));
    const boxes = [];
    const count = h("span", { class: "note grow" });
    const ok = h("button", { class: "primary" }, icon("export"), "Export…");
    const sync = () => { ok.disabled = !picked.size; count.textContent = `${picked.size} of ${S.jobs.length} selected`; };
    const list = h("div", { class: "pick-list" }, S.jobs.map((j) => {
      const cb = h("input", { type: "checkbox", checked: picked.has(j.id) }); boxes.push([j.id, cb]);
      cb.addEventListener("change", () => { cb.checked ? picked.add(j.id) : picked.delete(j.id); sync(); });
      return h("label", { class: "chk pickrow" }, cb, h("span", {}, h("b", {}, j.name), h("small", {}, `${MODE_LABEL[j.mode]} · ${j.source || "no source yet"}`)));
    }));
    const toggle = h("button", { class: "ghost sm", onclick: () => { const all = picked.size < S.jobs.length; for (const [id, cb] of boxes) { cb.checked = all; all ? picked.add(id) : picked.delete(id); } sync(); } }, "Select all / none");
    ok.addEventListener("click", async () => {
      ok.disabled = true;
      const r = await must("export_jobs", [...picked]);
      sync(); if (!r || !r.path) return;
      toast(`Saved ${r.count} job${r.count === 1 ? "" : "s"} to ${r.path}`, "ok"); close(true);
    });
    sync();
    return h("div", {}, h("h2", {}, "Export jobs"),
      h("p", { class: "note" }, "Saves the chosen jobs to a file you can import on another computer or keep as a backup. Schedules are not included, and Move jobs need a new preview after importing. rSimpLone never stores passwords itself, but anything you type into a job's extra options is saved and exported exactly as typed."),
      list, h("div", { class: "row", style: "margin-top:.5rem" }, toggle, count),
      h("div", { class: "btns" }, h("button", { onclick: () => close(false) }, "Cancel"), ok));
  });
}
async function importJobs() {
  const r = await must("import_jobs"); if (!r || r.cancelled) return;
  for (const j of r.jobs) S.jobs.push(j);
  if (r.jobs.length) { S.sel = r.jobs[0].id; S.view = "job"; S.tab = "setup"; lsSet("rsg-sel", S.sel); renderAll(); }
  if (r.jobs.length) toast(`Imported ${r.jobs.length} job${r.jobs.length === 1 ? "" : "s"}. Check the folders, then run a preview.`, "ok");
  if (r.skipped.length) await confirmBox(`${r.skipped.length} job${r.skipped.length === 1 ? " was" : "s were"} skipped`, h("ul", { class: "note" }, r.skipped.slice(0, 12).map((t) => h("li", {}, t))), "OK");
  else if (!r.jobs.length) toast("That file has no jobs in it.", "bad");
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
  stack.append(h("div", { class: "card" }, h("header", {}, h("h2", {}, "What should it do?"), seg),
    h("div", { class: "note" }, MODE_TEXT[job.mode]),
    job.mode === "move" ? h("div", { class: "warnbox", style: "margin-top:.6rem" }, icon("alert"), " Move deletes the originals after copying. The real run unlocks only after a preview of this exact job, and stays unlocked for 24 hours.",
      job.move_ready ? h("span", { class: "chip ok", style: "margin-left:.4rem" }, "preview done") : null) : null));

  // source
  const srcIn = inputFor(job, "source", { placeholder: "Folder to copy from", after: debounce(() => checkSource(job), 600) });
  stack.append(h("div", { class: "card" }, h("header", {}, h("h2", {}, "Copy from")),
    h("div", { class: "row" }, h("div", { class: "grow" }, srcIn),
      h("button", { onclick: async () => { const p = await must("pick_folder", job.source); if (p) { srcIn.value = p; patch(job, { source: p }); checkSource(job); } } }, icon("folder"), "Browse…")),
    verdictLine("v-source"), h("div", { class: "row", id: "disk-row", style: "margin-top:.3rem" })));

  // destination
  const where = h("div", { class: "seg" },
    h("button", { "aria-pressed": String(!local), onclick: () => patch(job, { dest_kind: "remote" }, true) }, icon("cloud"), "Cloud remote"),
    h("button", { "aria-pressed": String(local), onclick: () => patch(job, { dest_kind: "local" }, true) }, icon("folder"), "Local folder"));
  const dest = h("div", { class: "card" }, h("header", {}, h("h2", {}, "Copy to"), where));
  if (!local) {
    const sel = h("select", {}, h("option", { value: "" }, "Choose a remote…"),
      S.remotes.map((r) => h("option", { value: r.name, selected: r.name === job.remote }, (r.crypt ? "🔒 " : "") + r.name + "  ·  " + r.type)));
    sel.addEventListener("change", () => patch(job, { remote: sel.value, target: "", backup_root: "" }, true));
    dest.append(h("div", { class: "row" }, h("div", { class: "grow" }, sel),
      h("button", { class: "ghost", title: "Connect a new cloud or server", onclick: () => addRemoteDialog() }, icon("plus"), "Add remote…"),
      h("button", { class: "ghost", title: "Re-read the remote list", onclick: async () => { const r = await must("reload_remotes"); if (r) { S.remotes = r; renderJobBody(); toast("Remotes refreshed"); } } }, "Refresh"),
      h("button", { onclick: () => cryptDialog(job) }, icon("lock"), "New encrypted remote…")));
    if (job.crypt) dest.append(h("div", { class: "note", style: "margin-top:.4rem" }, icon("lock"), " Encrypted remote: file names and contents are scrambled before upload. Encrypted files can't be compared by checksum, so size and modified time are used."));
  }
  const pickBtn = (key) => h("button", { onclick: () => pickFolder(job, key) }, icon("folder"), "Pick…");
  const tgt = inputFor(job, "target", { placeholder: local ? "Full path, e.g. E:\\Backups\\Photos" : "Folder on the remote, e.g. Backups/Photos", after: debounce(() => checkDest(job), 600) });
  dest.append(h("div", { class: "grid2", style: "margin-top:.7rem" },
    h("div", { class: "stack", style: "gap:.3rem" }, h("label", { class: "f" }, "Folder"), h("div", { class: "row" }, h("div", { class: "grow" }, tgt), pickBtn("target")), verdictLine("v-target")),
    h("div", { class: "stack", style: "gap:.3rem" }, h("label", { class: "f" }, job.mode === "copy" ? "Backup folder (optional)" : "Backup folder (required)"),
      h("div", { class: "row" }, h("div", { class: "grow" }, inputFor(job, "backup_root", { placeholder: local ? "Full path, e.g. E:\\Backups\\_old" : "e.g. Backups/_old", after: debounce(() => checkDest(job), 600) })), pickBtn("backup_root")), verdictLine("v-backup"))));
  dest.append(h("div", { class: "note", style: "margin-top:.5rem" }, "Replaced or removed files are moved to ", h("code", {}, "<backup>/<source name>/<date-time>/"), local ? " on the same drive." : " on the same remote. That is a server-side move, so nothing is uploaded twice."));
  if (!local) dest.append(h("div", { class: "row", style: "margin-top:.5rem" }, h("button", { class: "sm", title: "Lists the remote once to see whether these folders exist.", onclick: () => checkFolders(job) }, icon("search"), "Check that these folders exist"), h("span", { class: "note" }, "Uses one API call.")));
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
    info.exists ? `Found${info.free ? " · " + info.free + " free of " + info.total : ""}` : "This folder doesn't exist.");
  const row = $("#disk-row"); if (!row) return;
  row.replaceChildren();
  if (info.disk && info.disk !== job.disk) { patch(job, { disk: info.disk }); toast(`Detected ${info.disk.toUpperCase()} for this folder; tuning updated.`); }
  if (info.disk) row.append(h("span", { class: "chip ok" }, `Detected ${info.disk.toUpperCase()}`));
  else if (info.exists) row.append(h("span", { class: "chip" }, "Disk type unknown"), h("span", { class: "note" }, `Couldn't detect the disk type, so ${job.disk.toUpperCase()} settings are used. Change it on the Config tab if that is wrong.`));
}
async function checkFolders(job) {
  const v = await must("check_job", job.id, true);
  if (!v) return;
  job._verdict = v; checkDest(job);
  toast("Folders checked with one listing of the remote.", "ok");
}
async function checkDest(job) {
  if (job.id !== S.sel || !$("#v-target")) return;
  if (job.dest_kind === "local") {
    for (const [key, vid] of [["target", "v-target"], ["backup_root", "v-backup"]]) {
      const p = (job[key] || "").trim();
      if (!p) { setVerdict(vid, "", null, key === "backup_root" && job.mode === "copy" ? "No backup folder: replaced files are overwritten." : ""); continue; }
      const info = await must("path_info", p); if (!info) continue;
      setVerdict(vid, info.exists ? "ok" : "warn", info.exists ? "check" : "alert",
        (info.exists ? "Found" : "Doesn't exist yet. It will be created") + (info.free ? ` · ${info.free} free of ${info.total}` : ""));
    }
  } else {
    const v = job._verdict;
    for (const [key, vid] of [["target", "v-target"], ["backup_root", "v-backup"]]) {
      const x = v && v[key === "target" ? "target" : "backup"];
      if (!x) setVerdict(vid, "", null, job[key] ? "Not checked yet." : "");
      else setVerdict(vid, x.state === "exists" ? "ok" : x.state === "missing" ? "warn" : "", x.state === "exists" ? "check" : "alert",
        x.state === "exists" ? "Found on the remote." : x.state === "missing" ? "Doesn't exist yet. It will be created." + (x.near ? ` Did you mean ${x.near}?` : "") : "Too deep to check without extra calls.");
    }
  }
}
function fillProblems(box, job) {
  const p = job.problems || [];
  box.replaceChildren();
  if (!p.length) return;
  box.className = "problems";
  box.append(h("b", {}, "Fix these before running"), h("ul", {}, p.map((t) => h("li", {}, t))));
}
function previewCard(job) {
  const pre = h("div", { class: "pre", hidden: true });
  const btn = h("button", { class: "ghost sm" }, icon("code"), "Show the rclone command");
  btn.addEventListener("click", async () => {
    if (!pre.hidden) { pre.hidden = true; return; }
    const r = await must("preview", job.id); if (!r) return;
    pre.textContent = r.dry + "\n\n# the real run is the same command without --dry-run"; pre.hidden = false;
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
  stack.append(h("div", { class: "card" }, h("header", {}, h("h2", {}, "Speed")),
    h("div", { class: "grid2" },
      field("Type of source disk", disk, job.disk === "hdd" ? "Hard disk: reads one thing at a time and finishes all checks before copying, so the disk is not forced to jump around." : "SSD: reads and copies many files in parallel."),
      num2("checkers", "Parallel checks", "How many files are compared at once. 0 picks a value for you."), num2("transfers", "Parallel copies", "How many files are copied at once. 0 picks a value for you.")),
    local ? h("div", { class: "note", style: "margin-top:.6rem" }, "Internet speed limits only apply when the destination is a cloud remote.") :
      h("div", { class: "grid2", style: "margin-top:.7rem" },
        num2("bw_mbps", "Your upload speed (Mbit/s)", "Check it with a speed test."), num2("bw_percent", "Share to use (%)", "Leaves the rest for other things on your network."),
        sw(job.no_bw_limit, (v) => patch(job, { no_bw_limit: v }), "Don't limit the speed", "Uses all of your upload bandwidth."))));
  // behaviour
  const beh = [];
  if (!local) beh.push(sw(job.api_low, (v) => patch(job, { api_low: v }), "Use as few Google Drive requests as possible", "Lists folders in one go and uploads in large chunks at a steady rate, to stay under Drive's request limits."),
    sw(job.no_dir_modtime, (v) => patch(job, { no_dir_modtime: v }), "Don't update folder dates on the remote", "Saves one request per changed folder. Files are still compared normally."));
  if (job.mode === "copy") beh.push(sw(job.skip_existing, (v) => patch(job, { skip_existing: v }), "Skip files that already exist", "Files already at the destination are left alone, even if the source version changed."));
  stack.append(h("div", { class: "card" }, h("header", {}, h("h2", {}, "Options")), h("div", { class: "stack" }, beh,
    field("Name of the backup sub-folder", inputFor(job, "label", { placeholder: "Leave empty to use the source folder's name" }), "Backed-up files are stored in <backup folder>/<this name>/<date-time>/."))));
  // tools
  const tools = [h("button", { onclick: async () => { const r = await must("preview", job.id); if (r) { try { await navigator.clipboard.writeText(r.dry); toast("Command copied to the clipboard.", "ok"); } catch { toast(r.dry); } } } }, icon("copy"), "Copy rclone command"),
    h("button", { onclick: async () => { const r = await must("export_script", job.id); if (r) toast("Script saved to " + r.path, "ok"); } }, icon("code"), "Save as script")];
  if (!local) tools.unshift(h("button", { title: "Lists the remote once to see whether the destination and backup folders exist.", onclick: () => checkFolders(job) }, icon("search"), "Check folders on the remote"));
  const depth = h("input", { type: "number", min: 1, max: 6, value: job.list_depth || 1 }); depth.addEventListener("input", () => patch(job, { list_depth: Math.max(1, Number(depth.value) || 1) }));
  stack.append(h("div", { class: "card" }, h("header", {}, h("h2", {}, "Tools")), h("div", { class: "row" }, tools, local ? null : h("label", { class: "f", style: "width:9rem" }, "How deep to list", depth))));
  // flags
  if (isAdvanced() || Object.keys(job.flags || {}).length || (job.extra || "").trim()) stack.append(flagsCard(job));
  else stack.append(h("div", { class: "card" }, h("header", {}, h("h2", {}, "Advanced rclone options")), h("div", { class: "row" }, h("span", { class: "note grow" }, "Hidden in Simple mode. Every rclone option is available in Advanced mode."), h("button", { onclick: () => setAdvanced(true) }, "Show advanced options"))));
  return stack;
}

function flagsCard(job) {
  const cat = S.catalogue.filter((f) => !f.denied);
  const groups = ["Common", ...new Set(cat.map((f) => f.group))];
  const COMMON = new Set(["--bwlimit", "--transfers", "--checkers", "--exclude", "--include", "--filter", "--max-age", "--min-age", "--max-size", "--min-size", "--checksum", "--size-only", "--ignore-times", "--update", "--immutable",
    "--max-transfer", "--max-duration", "--retries", "--low-level-retries", "--timeout", "--contimeout", "--tpslimit", "--buffer-size", "--multi-thread-streams", "--fast-list", "--no-traverse", "--delete-empty-src-dirs", "--order-by", "--metadata", "--links", "--exclude-from", "--include-from", "--files-from",
    "--ignore-existing", "--no-check-dest", "--modify-window", "--use-server-modtime", "--drive-chunk-size", "--drive-upload-cutoff", "--drive-acknowledge-abuse", "--drive-skip-gdocs", "--drive-use-trash"]);
  const wrap = h("div", { class: "card" });
  const search = h("input", { placeholder: "Search all rclone options by name or description…", value: fl.q });
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
    if (!shown.length) list.append(h("div", { class: "empty" }, S.catalogue.length ? "No options match your search." : "rclone's option list is not available. Is rclone installed?"));
    if (rows.length > shown.length) list.append(h("div", { class: "note", style: "padding:.6rem .8rem" }, `Showing ${shown.length} of ${rows.length}. Type in the search box to narrow it down.`));
  };
  search.addEventListener("input", () => { fl.q = search.value; paint(); });
  const extra = h("input", { value: job.extra || "", placeholder: "e.g. --exclude '*.tmp' --max-age 30d", spellcheck: "false" });
  extra.addEventListener("input", () => patch(job, { extra: extra.value }));
  wrap.append(h("header", {}, h("h2", {}, "Advanced rclone options"), h("span", { class: "note" }, `${cat.length} options from ${S.rcloneVersion || "rclone"}. Only the ones you change are saved.`)),
    h("div", { class: "stack" }, search, chips, list, field("Extra options (typed by hand)", extra, "Options that rSimpLone manages itself (preview, backup folder, logging, progress) are refused.")));
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
    h("div", { class: "note", style: "margin-top:.4rem" }, "A value set here overrides what rSimpLone would choose from the Speed settings.")), 500);
  return row;
}

// ═════════════════════════════════════════════════════════════════════════════════════
// Schedule
// ═════════════════════════════════════════════════════════════════════════════════════
function tabSchedule(job) {
  const s = { ...job.schedule };
  let changed = false;
  const stack = h("div", { class: "stack" });
  const card = h("div", { class: "card" }, h("header", {}, h("h2", {}, "Run on a schedule"), h("span", { class: "chip " + (job.schedule && job.schedule.enabled ? "ok" : "") }, job.schedule_text || "Off")));
  const touch = () => { if (!changed) { changed = true; const b = $("#sched-save"); if (b) { b.disabled = false; b.textContent = "Save schedule"; } } };
  const kind = h("div", { class: "seg" }, [["interval", "Every few minutes"], ["daily", "Daily"], ["weekly", "Weekly"]].map(([k, l]) => h("button", { "aria-pressed": String(s.kind === k), onclick: () => { s.kind = k; changed = true; rebuild(); } }, l)));
  const every = h("input", { type: "number", min: 5, value: s.every_min || 60 }); every.addEventListener("input", () => { s.every_min = Number(every.value) || 60; touch(); });
  const time = h("input", { type: "time", value: s.time || "02:00" }); time.addEventListener("input", () => { s.time = time.value; touch(); });
  const days = h("div", { class: "days" }, ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d, i) =>
    h("button", { class: "sm", "aria-pressed": String((s.days || []).includes(i)), onclick: (e) => { const set = new Set(s.days || []); set.has(i) ? set.delete(i) : set.add(i); s.days = [...set].sort(); e.currentTarget.setAttribute("aria-pressed", String(set.has(i))); touch(); } }, d)));
  const real = h("input", { type: "checkbox", checked: !!s.real && job.mode !== "move", disabled: job.mode === "move" }); real.addEventListener("change", () => { s.real = real.checked; touch(); });
  const body = h("div", { class: "stack" });
  const rebuild = () => {
    body.replaceChildren(...[
      sw(s.enabled, (v) => { s.enabled = v; touch(); }, "Run this job on a schedule", "Runs only while rSimpLone is open. To keep it running with the window closed, turn on background mode in Settings."),
      h("div", { class: "row" }, kind),
      s.kind === "interval" ? field("Repeat every (minutes, at least 5)", every) : h("div", { class: "grid2" }, field("At", time), s.kind === "weekly" ? field("On", days) : null),
      h("label", { class: "chk" }, real, h("span", {}, "Make real changes, not just a preview",
        h("small", {}, job.mode === "move" ? "Move jobs can only be scheduled as previews. Run a real Move yourself after a preview." : `You type ${S.confirmWord} once to allow it. If you edit the job later, scheduled runs go back to previews until you confirm again.`))),
      job.next_run ? h("div", { class: "note" }, icon("clock"), " Next run: ", job.next_run) : null,
      h("div", { class: "row" }, h("button", { class: "primary", id: "sched-save", disabled: !changed, onclick: save }, "Save schedule")),
    ].filter(Boolean));
  };
  const save = async () => {
    let confirm = "";
    if (s.enabled && s.real) {
      const word = await typedConfirm("Allow scheduled real runs?", h("p", {}, `“${job.name}” will make real changes on its schedule without asking each time.`), S.confirmWord, "Allow");
      if (!word) return; confirm = word;
    }
    const r = await must("set_schedule", job.id, s, confirm); if (!r) return;
    for (const k of Object.keys(r)) if (DERIVED.includes(k) || k === "schedule") job[k] = r[k];
    toast(s.enabled ? "Schedule saved: " + r.schedule_text : "Schedule is off.", "ok"); renderRail(); renderJobBody();
  };
  rebuild();
  card.append(body); stack.append(card);
  return stack;
}

// ═════════════════════════════════════════════════════════════════════════════════════
// Run: a live view that is updated in place, so buttons never move while you click them
// ═════════════════════════════════════════════════════════════════════════════════════
const STATE_TEXT = { running: "Running", stopping: "Stopping…", done: "Finished", failed: "Failed", stopped: "Stopped" };
function tabRun(job) {
  const run = (S.watch[job.id] && S.runs.find((r) => r.id === S.watch[job.id])) || lastRun(job.id);
  const stack = h("div", { class: "stack" });
  if (!run) {
    stack.append(h("div", { class: "empty" }, h("h2", {}, "Nothing has run yet"), h("p", {}, "Press Preview to see what this job would do. A preview changes nothing."),
      job.last_run ? h("p", { class: "note" }, `Last run: ${job.last_run} (${job.last_mode}). ${job.last_summary}`) : null));
    return stack;
  }
  stack.id = "runtab"; stack.dataset.run = run.id;
  const tile = (id, label) => h("div", { class: "stat" }, h("b", { id: "t-" + id }, "–"), h("span", {}, label));
  const tiles = run.real
    ? [["pct", "Done"], ["xfer", "Copied"], ["speed", "Speed"], ["eta", "Time left"], ["files", "Files copied"], ["checks", "Files checked"], ["errors", "Errors"]]
    : [["found", "Files found"], ["copy", "Would copy"], ["size", "Data to copy"], ["backup", "Would move to backup"], ...(job.mode === "copy" ? [] : [["delete", "Would delete"]]), ["errors", "Errors"]];
  stack.append(
    h("div", { class: "card" },
      h("header", {}, h("h2", { id: "run-title" }), h("span", { class: "chip", id: "run-state" }), h("span", { class: "chip", id: "run-time", title: "Time elapsed", style: "text-transform:none" }),
        h("span", { class: "grow" }),
        h("button", { class: "ghost sm", title: "Show rclone's own output", onclick: () => { S.bottomOpen = true; S.bottomTab = "console"; S.bottomSel = run.id; cons.run = ""; renderBottom(); } }, icon("term"), "Console"),
        h("button", { class: "ghost sm", onclick: () => must("open_path", "log", run.id) }, icon("open"), "Open log file"),
        h("button", { class: "danger sm", id: "run-stop", onclick: () => must("stop", run.id) }, icon("stop"), "Stop")),
      run.real ? h("div", { class: "bigbar" }, h("i", { id: "run-bar" })) : null,
      h("div", { class: "stats" + (run.real ? "" : " dry"), style: "margin-top:.7rem" }, tiles.map(([id, l]) => tile(id, l)))),
    h("div", { id: "run-banner" }),
    h("div", { class: "card", id: "run-now-card", hidden: true }, h("header", {}, h("h2", {}, "Copying now")), h("div", { class: "nowlist", id: "run-now" })),
    h("div", { class: "card" }, h("header", {}, h("h2", {}, "Activity"), h("div", { class: "chips", id: "run-filter" }), h("span", { class: "note", id: "run-feedcount" })), h("div", { class: "feed", id: "run-feed" })));
  return stack;
}
const feedFilter = { kind: "all" };
const KIND_TEXT = { upload: ["copied", "would copy"], replace: ["replaced", "would replace"], backup: ["to backup", "would back up"], delete: ["deleted", "would delete"], modtime: ["date fixed", "date would be fixed"], error: ["error", "error"] };
const kindText = (k, real) => (KIND_TEXT[k] || [k, k])[real ? 0 : 1];
const setText = (id, v) => { const el = $("#" + id); v = String(v); if (el && el.textContent !== v) el.textContent = v; };
function updateRunTab(force) {
  const root = $("#runtab"); if (!root) return;
  const job = curJob(); const run = S.runs.find((r) => r.id === root.dataset.run); if (!run || !job) return;
  const live = isLive(run);
  const pct = run.total ? Math.min(100, Math.round((run.bytes / run.total) * 100)) : (run.state === "done" ? 100 : 0);
  const c = run.counts || {};
  setText("run-title", run.real ? `${MODE_LABEL[job.mode]}: real run` : `${MODE_LABEL[job.mode]}: preview`);
  const st = $("#run-state"); if (st) { st.textContent = STATE_TEXT[run.state] || run.state; st.className = "chip " + (live ? "gold" : run.state === "done" ? "ok" : run.state === "failed" ? "bad" : ""); }
  setText("run-time", dur((live ? Date.now() / 1000 : run.ended || Date.now() / 1000) - run.started));
  const stop = $("#run-stop"); if (stop) stop.hidden = !live;
  if (run.real) {
    const bar = $("#run-bar"); if (bar) bar.style.width = pct + "%";
    setText("t-pct", pct + "%"); setText("t-xfer", `${bytes(run.bytes)} / ${bytes(run.total)}`); setText("t-speed", live ? bytes(run.speed) + "/s" : "–"); setText("t-eta", live && run.eta != null ? dur(run.eta) : "–");
    setText("t-files", `${run.transfers} of ${Math.max(run.total_transfers, run.transfers)}`); setText("t-checks", `${run.checks} of ${Math.max(run.total_checks, run.checks)}`);
  } else {
    setText("t-found", Math.max(run.checks, (c.upload || 0) + (c.backup || 0) + (c.delete || 0))); setText("t-copy", c.upload || 0); setText("t-size", bytes(run.total)); setText("t-backup", c.backup || 0); setText("t-delete", c.delete || 0);
  }
  setText("t-errors", run.errors || 0);
  const now = $("#run-now-card"), list = run.transferring || [];
  if (now) { now.hidden = !(live && list.length); if (!now.hidden) $("#run-now").replaceChildren(...list.map((t) => {
    const p = t.size ? Math.min(100, Math.round((t.bytes / t.size) * 100)) : 0;
    return h("div", { class: "nowrow" }, h("span", { class: "nm", title: t.name }, t.name), h("div", { class: "bar" }, h("i", { style: `width:${p}%` })), h("span", { class: "mono muted" }, `${p}%  ${bytes(t.bytes)} / ${bytes(t.size)}`));
  })); }
  const ban = $("#run-banner");
  if (ban.dataset.s !== run.state) {
    ban.dataset.s = run.state; ban.replaceChildren();
    if (!live && run.summary) {
      const ok = run.code === 0 || run.code === 9;
      ban.append(h("div", { class: "banner " + (ok ? "ok" : "bad") }, h("b", {}, (run.real ? "" : "Preview result: ") + run.summary), h("span", { class: "note" }, `rclone exit code ${run.code}: ${run.meaning}`),
        run.backup_dir ? h("span", { class: "note mono-sel" }, "Backup folder: " + run.backup_dir) : null,
        !run.real && ok ? h("span", { class: "note" }, job.mode === "move" ? "Looks right? A real Move is now unlocked for 24 hours, as long as you don't edit this job." : "Looks right? Press the run button at the top to do it for real.") : null));
    }
  }
  const acts = S.activity[run.id] || [];
  const kinds = ["all", ...new Set(acts.map((a) => a.kind))];
  const fkey = kinds.join(",") + feedFilter.kind;
  const fbox = $("#run-filter");
  if (force || fbox.dataset.k !== fkey) { fbox.dataset.k = fkey; fbox.replaceChildren(...kinds.map((k) => h("button", { "aria-pressed": String(feedFilter.kind === k), onclick: () => { feedFilter.kind = k; updateRunTab(true); } }, k === "all" ? "All" : kindText(k, run.real)))); }
  const shown = acts.filter((a) => feedFilter.kind === "all" || a.kind === feedFilter.kind);
  const feed = $("#run-feed");
  if (force || feed.dataset.n !== String(shown.length) + feedFilter.kind) {
    feed.dataset.n = String(shown.length) + feedFilter.kind;
    feed.replaceChildren(...shown.slice(-300).reverse().map((a) => h("div", { class: "it" }, h("span", { class: "k " + a.kind }, kindText(a.kind, run.real)), h("span", { class: "p" }, a.path || a.detail, a.path ? h("span", { class: "muted" }, "  " + a.detail) : null))));
    if (!shown.length) feed.append(h("div", { class: "empty" }, live ? "Waiting for rclone…" : run.real ? "No file activity was reported." : "Nothing would change."));
  }
  setText("run-feedcount", `${shown.length} item${shown.length === 1 ? "" : "s"}`);
}
