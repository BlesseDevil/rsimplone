// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)
// Licensed under the GNU AGPL v3 or any later version; see <https://www.gnu.org/licenses/>. No warranty.
// Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
// The domain probably expired because HE's TOO BROKE TO RENEW IT.
// Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
// and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"use strict";
// Design preview only: open index.html?mock in any browser to see the window with fake data. The real app never loads this.
(() => {
  const ok = (data) => ({ ok: true, data });
  const bad = (error) => ({ ok: false, error });
  const job = (o) => Object.assign({ id: Math.random().toString(16).slice(2, 14), name: "Job", dest_kind: "remote", mode: "copy", source: "", remote: "", target: "", backup_root: "", label: "", skip_existing: false, api_low: true, no_dir_modtime: false,
    disk: "hdd", bw_mbps: 30, bw_percent: 85, no_bw_limit: false, checkers: 0, transfers: 0, list_depth: 1, flags: {}, extra: "", schedule: { enabled: false, kind: "daily", every_min: 60, time: "02:00", days: [0,1,2,3,4,5,6], real: false },
    last_run: "", last_mode: "", last_code: null, last_summary: "", problems: [], schedule_text: "Off", next_run: "", dest_text: "", crypt: false, busy: false, move_ready: false }, o);
  let jobs = [
    job({ id: "j1", name: "Photos to Drive", mode: "sync", source: "D:\\Photos", remote: "gdrive", target: "Backups/Photos", backup_root: "Backups/_old", dest_text: "gdrive:Backups/Photos", last_run: "2026-10-26 22:10", last_mode: "run", last_code: 0, last_summary: "12 uploaded, 3 moved to backup", schedule: { enabled: true, kind: "daily", time: "02:00", days: [0,1,2,3,4,5,6], real: false, every_min: 60 }, schedule_text: "Daily at 02:00", next_run: "2026-10-28 02:00" }),
    job({ id: "j2", name: "Documents (encrypted)", mode: "copy", source: "D:\\Docs", remote: "vault", target: "docs", crypt: true, dest_text: "vault:docs" }),
    job({ id: "j3", name: "Archive to NAS", mode: "move", dest_kind: "local", source: "D:\\Inbox", target: "E:\\Archive", backup_root: "E:\\Archive-old", dest_text: "E:\\Archive", problems: ["The destination must be a full folder path."], last_code: 7 }),
  ];
  let mounts = [{ id: "m1", name: "Drive (read-only)", remote: "gdrive", path: "", mountpoint: "X:", vfs_cache_mode: "writes", read_only: true, flags: {}, extra: "", auto_mount: false, state: "idle", run: "", problems: [] }];
  const cat = [["--bwlimit", "", "BwTimetable", "", "Bandwidth limit in KiB/s, or use suffix B|K|M|G|T|P or a full timetable", "Networking"], ["--transfers", "", "int", "4", "Number of file transfers to run in parallel", "Performance"], ["--checkers", "", "int", "8", "Number of checkers to run in parallel", "Performance"],
    ["--exclude", "", "stringArray", "", "Exclude files matching pattern", "Filter"], ["--max-age", "", "Duration", "off", "Only transfer files younger than this in s or suffix ms|s|m|h|d|w|M|y", "Filter"], ["--checksum", "-c", "bool", "", "Check for changes with size & checksum", "Copy"],
    ["--delete-empty-src-dirs", "", "bool", "", "Delete empty source dirs after move", "Sync"], ["--drive-chunk-size", "", "SizeSuffix", "8Mi", "Upload chunk size", "Backend"], ["--dry-run", "-n", "bool", "", "Do a trial run with no permanent changes", "Config"]]
    .map(([name, short, type, def, help, group]) => ({ name, short, type, default: def, help, group, denied: name === "--dry-run" }));
  let runs = [], seq = 0; const consoles = {}; const events = [];
  const tick = () => runs.forEach((r) => { if (r.state !== "running") return; r.bytes = Math.min(r.total, r.bytes + 38e6); r.speed = 4.1e6; r.eta = (r.total - r.bytes) / r.speed; r.checks += 3; r.transfers = Math.floor(r.bytes / 90e6);
    const c = consoles[r.id]; c.push(`2026/10/27 02:00:${String(c.length % 60).padStart(2, "0")} INFO  : IMG_${c.length}.jpg: Copied (new)`); events.push({ run: r.id, kind: "activity", data: { kind: "upload", path: `IMG_${c.length}.jpg`, detail: "Copied (new)" } }); events.push({ run: r.id, kind: "log", data: {} });
    if (r.bytes >= r.total) { r.state = "done"; r.ended = Date.now() / 1000; r.code = 0; r.meaning = "success - finished without errors"; r.summary = (r.real ? "" : "") + "12 would upload, 3 would move to backup"; c.push("2026/10/27 02:03:11 INFO  : Transferred: done"); } }, 0);
  setInterval(tick, 700);
  window.__mock = {
    boot_steps: async () => ok([{ name: "settings", label: "Reading your jobs…" }, { name: "ready", label: "Ready" }]), boot_step: async () => ok({ detail: "mock" }), boot_complete: async () => ok(true), is_booted: async () => ok(true), ui_ready: async () => ok(true),
    theme: async () => ok(localStorage.getItem("rsg-mode") || "system"), set_theme: async (m) => ok(m), app_state: async () => ok({ version: "2.0.0", rclone: "rclone", rclone_version: "rclone v1.75.0", remotes: [{ name: "gdrive", type: "drive", crypt: false }, { name: "vault", type: "crypt", crypt: true }], settings: { theme: "system", tray_on_close: false }, modes: {}, platform: "win32", confirm_word: "EXECUTE", fuse: { ok: false, name: "WinFsp", url: "https://winfsp.dev", message: "Mounting on Windows needs WinFsp. Install it from winfsp.dev, then try again." } }),
    flag_catalogue: async () => ok(cat), jobs: async () => ok(jobs), new_job: async (m) => { const j = job({ name: "New " + m + " job", mode: m }); jobs.push(j); return ok(j); }, save_job: async (j) => { Object.assign(jobs.find((x) => x.id === j.id), j); return ok(jobs.find((x) => x.id === j.id)); },
    delete_job: async () => ok(true), duplicate_job: async () => ok(jobs[0]), preview: async () => ok({ dry: "rclone sync D:\\Photos gdrive:Backups/Photos --backup-dir gdrive:Backups/_old/Photos/20261027-0200 --check-first --checkers 2 --transfers 2 --dry-run", real: "" }),
    export_script: async () => ok({ path: "C:\\data\\scripts\\Run-job.ps1" }), path_info: async (p) => ok({ exists: !!p, free: "412.0 GiB", total: "931.5 GiB", disk: p && p.startsWith("D:") ? null : "ssd" }), check_job: async () => ok({ target: { path: "t", state: "exists" }, backup: { path: "b", state: "missing", near: "" }, problems: [] }),
    folders: async () => ok(["Backups", "Backups/Photos", "Backups/_old", "Work"]), pick_folder: async () => ok("D:\\Picked"), reload_remotes: async () => ok([{ name: "gdrive", type: "drive", crypt: false }]), create_crypt: async () => ok([]), save_settings: async () => ok(true),
    start: async (id, real) => { const j = jobs.find((x) => x.id === id); const r = { id: "r" + ++seq, kind: "job", name: j.name, job_id: id, mode: j.mode, real, state: "running", started: Date.now() / 1000, ended: 0, bytes: 0, total: 900e6, speed: 0, eta: null, transfers: 0, checks: 0, errors: 0, counts: { upload: 0 }, backup_dir: "gdrive:Backups/_old/Photos/20261027-0200", log_path: "C:\\logs\\x.log", summary: "", code: null, meaning: "", mountpoint: "" }; runs.push(r); consoles[r.id] = ["2026/10/27 02:00:00 INFO  : Starting bandwidth limiter at 3.040Mi Byte/s", "2026/10/27 02:00:00 NOTICE: Dry run: nothing is changed"]; return ok(r.id); },
    stop: async (id) => { const r = runs.find((x) => x.id === id); if (r) { r.state = "stopped"; r.ended = Date.now() / 1000; } return ok(true); }, stop_all: async () => ok(0), runs: async () => ok(runs), clear_finished: async () => { runs = runs.filter((r) => r.state === "running"); return ok(true); },
    poll: async () => { const ev = events.splice(0); return ok({ events: ev, runs: JSON.parse(JSON.stringify(runs)), notes: [] }); }, console: async (id, since) => { const c = consoles[id] || []; return ok({ lines: c.slice(since), next: c.length, reset: false }); },
    open_path: async () => ok(true), open_url: async () => ok(true), set_schedule: async (id, s) => { const j = jobs.find((x) => x.id === id); j.schedule = s; j.schedule_text = s.enabled ? "Daily at " + s.time : "Off"; j.next_run = s.enabled ? "2026-10-28 " + s.time : ""; return ok(j); },
    mounts: async () => ok(mounts), new_mount: async () => { mounts.push({ ...mounts[0], id: "m" + Date.now(), name: "Mount " + (mounts.length + 1) }); return ok({}); }, save_mount: async (m) => { Object.assign(mounts.find((x) => x.id === m.id), m); return ok(true); }, delete_mount: async () => ok(true), mount: async () => ok("r0"),
    win_minimize: async () => ok(true), win_toggle_max: async () => ok(true), win_resize: async () => ok(true), win_size: async () => ok([1280, 820]), win_close: async () => ok({ closed: true }), about: async () => ok({ version: "2.0.0", rclone: "" }),
  };
})();
