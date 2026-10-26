# Copyright (C) 2026 Mehedi Maruf
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify it under the terms of the
# GNU Affero General Public License as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
# even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License along with this program.
# If not, see <https://www.gnu.org/licenses/>.
#
# Contact: rsimplone@mehedimaruf.com (developer), license@mehedimaruf.com (licence)
# Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
# The domain probably expired because HE's TOO BROKE TO RENEW IT.
# Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
# and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"""The bridge between the window (HTML/JS) and the logic. Every public method returns {ok, data} or {ok: false,
error}, never raises into the page. No file names or log text are sent anywhere except to the window."""
from __future__ import annotations

import collections
import functools
import json
import shutil
import threading
import time
from dataclasses import asdict, fields
from datetime import datetime
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from . import __version__, core, flags as flagmod, mounts, runs, schedule

CONFIRM_WORD = "EXECUTE"
LISTING_TTL = 15 * 60
THEMES = ("system", "light", "dark")
BOOT = [
    ("settings", "Reading your jobs…"),
    ("rclone", "Finding rclone…"),
    ("remotes", "Reading your remotes…"),
    ("flags", "Loading rclone's flag list…"),
    ("scheduler", "Starting the scheduler…"),
    ("ready", "Ready"),
]


def _api(fn: Callable[..., Any]) -> Callable[..., Dict[str, Any]]:
    @functools.wraps(fn)
    def wrapper(self: "Api", *a: Any, **kw: Any) -> Dict[str, Any]:
        try:
            return {"ok": True, "data": fn(self, *a, **kw)}
        except (runs.RunRefused, core.RcloneError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
    return wrapper


def _job_from(d: Dict[str, Any], base: Optional[core.Job] = None) -> core.Job:
    known = {f.name: f for f in fields(core.Job)}
    job = base or core.Job()
    for k, v in d.items():
        if k in known and k not in ("id", "last_run", "last_mode", "last_code", "last_summary", "dry_sig", "dry_ts"):
            setattr(job, k, v)
    if job.mode not in core.MODES:
        job.mode = "copy"
    job.dest_kind = "local" if job.dest_kind == "local" else "remote"
    return job


class Api:
    def __init__(self, window_getter: Callable[[], Any] = lambda: None) -> None:
        self._window = window_getter
        self.lock = threading.RLock()
        self.store = core.Store()
        self.rclone: Optional[str] = None
        self.version = ""
        self.remotes: List[Dict[str, Any]] = []
        self.catalogue: List[Dict[str, Any]] = []
        self.listings: Dict[Tuple[str, int], Tuple[float, List[str]]] = {}
        self.notes: Deque[Dict[str, str]] = collections.deque(maxlen=100)
        self.mgr = runs.RunManager(lambda: self.rclone, on_done=self._run_done)
        self.scheduler = schedule.Scheduler(lambda: list(self.store.jobs), self._fire, self.mgr.job_busy, self._save, core.job_signature)
        self._splash: Any = None
        self._main: Any = None
        self._recenter: Optional[Callable[[], None]] = None
        self._maximized = False
        self._ui_ready = threading.Event()
        self.booted = False
        self.on_hide: Optional[Callable[[], None]] = None      # set by the app: tray / minimise handler

    # ---- plumbing ------------------------------------------------------------------------------
    def _save(self) -> None:
        with self.lock:
            core.save_store(self.store)

    def _job(self, job_id: str) -> core.Job:
        for j in self.store.jobs:
            if j.id == job_id:
                return j
        raise ValueError("That job no longer exists.")

    def _note(self, level: str, text: str) -> None:
        self.notes.append({"level": level, "text": text})

    def _run_done(self, rec: runs.Record) -> None:
        job, res = rec.job, rec.result
        if not job or not res:
            return
        with self.lock:
            job.last_run = time.strftime("%Y-%m-%d %H:%M")
            job.last_mode = "run" if rec.real else "dry run"
            job.last_code, job.last_summary = res.code, res.summary
            if not rec.real and not res.stopped and res.code in (0, 9):
                job.dry_sig, job.dry_ts = core.job_signature(job), time.time()
            self._save()
        word = "finished" if res.code in (0, 9) else "ended with errors"
        self._note("ok" if res.code in (0, 9) else "bad", "%s %s: %s" % (job.name, word, res.summary))

    def _fire(self, job: core.Job, real: bool) -> None:
        try:
            self.mgr.start_job(job, real)
            self._note("info", "Scheduled %s of %s started." % ("run" if real else "dry run", job.name))
        except runs.RunRefused as exc:
            self._note("bad", "Scheduled run of %s skipped: %s" % (job.name, exc))

    # ---- window / boot ----------------------------------------------------------------------------
    def _attach_windows(self, splash: Any, main: Any, recenter: Optional[Callable[[], None]] = None) -> None:
        self._splash, self._main, self._recenter = splash, main, recenter

    @_api
    def boot_steps(self) -> List[Dict[str, str]]:
        return [{"name": n, "label": label} for n, label in BOOT]

    @_api
    def boot_step(self, name: str) -> Dict[str, str]:
        detail = ""
        if name == "settings":
            self.store = core.load_store()
            detail = "%d jobs" % len(self.store.jobs)
        elif name == "rclone":
            self.rclone = core.find_rclone(str(self.store.settings.get("rclone", "")))
            self.version = core.rclone_version(self.rclone) if self.rclone else ""
            detail = self.version or "rclone not found"
        elif name == "remotes":
            self._load_remotes()
            detail = "%d remotes" % len(self.remotes)
        elif name == "flags":
            self._load_catalogue()
            detail = "%d flags" % len(self.catalogue)
        elif name == "scheduler":
            self.scheduler.start()
            detail = "on while this window is open"
            for spec in self.store.settings.get("mounts", []):
                if isinstance(spec, dict) and spec.get("auto_mount"):
                    try:
                        self.mgr.start_mount(mounts.spec_from_dict(spec))
                    except runs.RunRefused as exc:
                        self._note("bad", "Could not auto-mount %s: %s" % (spec.get("name", ""), exc))
        elif name == "ready":
            self.booted = True
        return {"detail": detail}

    @_api
    def is_booted(self) -> bool:
        return self.booted

    @_api
    def ui_ready(self) -> bool:
        self._ui_ready.set()
        return True

    @_api
    def open_url(self, url: str) -> bool:
        """Open a web page or a mail draft in the user's own browser / mail app. Nothing else is allowed."""
        import webbrowser
        if not (url.startswith("https://mehedimaruf.com") or url.startswith("https://winfsp.dev") or url.startswith("https://macfuse.io")
                or url.startswith("https://github.com/libfuse/") or url.startswith("mailto:rsimplone@mehedimaruf.com")):
            raise ValueError("That link is not allowed.")
        webbrowser.open(url)
        return True

    @_api
    def boot_complete(self) -> bool:
        self._ui_ready.wait(timeout=6)       # the main window is hidden until it has drawn its first page
        if self._main is not None:
            if self._recenter:
                self._recenter()
            self._main.show()
        if self._splash is not None:
            try:
                self._splash.destroy()
            except Exception:  # noqa: BLE001
                pass
        return True

    @_api
    def theme(self) -> str:
        t = self.store.settings.get("theme", "system")
        return t if t in THEMES else "system"

    @_api
    def set_theme(self, mode: str) -> str:
        if mode not in THEMES:
            mode = "system"
        self.store.settings["theme"] = mode
        self._save()
        return mode

    @_api
    def win_minimize(self) -> bool:
        if self._main is not None:
            self._main.minimize()
        return True

    @_api
    def win_toggle_max(self) -> bool:
        if self._main is not None:
            if self._maximized:
                self._main.restore()
            else:
                self._main.maximize()
            self._maximized = not self._maximized
        return self._maximized

    @_api
    def win_resize(self, width: int, height: int) -> bool:
        if self._main is not None and not self._maximized:
            self._main.resize(max(900, int(width)), max(560, int(height)))
        return True

    @_api
    def win_size(self) -> List[int]:
        return [int(self._main.width), int(self._main.height)] if self._main is not None else [1200, 800]

    @_api
    def win_close(self, force: bool = False) -> Dict[str, Any]:
        """Close the app. Returns {"confirm": n} when n runs are active and force is false; hides to the tray (or
        minimises) instead of quitting when that option is on and a schedule is enabled."""
        active = self.mgr.active()
        if active and not force:
            return {"confirm": active}
        has_schedule = any(schedule.normalize(j.schedule)["enabled"] for j in self.store.jobs)
        if self.store.settings.get("tray_on_close") and has_schedule and self.on_hide and not force:
            self.on_hide()
            return {"hidden": True}
        self.shutdown()
        if self._main is not None:
            self._main.destroy()
        return {"closed": True}

    def shutdown(self) -> None:
        self.scheduler.stop()
        self.mgr.stop_all()
        deadline = time.time() + 8
        while self.mgr.active() and time.time() < deadline:
            time.sleep(0.2)

    # ---- settings / remotes / flags -------------------------------------------------------------------
    def _load_remotes(self) -> None:
        self.remotes = []
        if not self.rclone:
            return
        try:
            self.remotes = [{"name": n, "type": t, "crypt": t == "crypt"} for n, t in core.list_remotes(self.rclone)]
        except core.RcloneError as exc:
            self._note("bad", str(exc))

    def _load_catalogue(self) -> None:
        if not self.rclone:
            return
        path = core.config_dir() / "flags-cache.json"
        cached = flagmod.cache_valid(path, self.version)
        if cached is None:
            _code, out, _err = core.run_capture(self.rclone, ["help", "flags"], timeout=60)
            cached = flagmod.parse_help_flags(out)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"version": self.version, "flags": cached}), encoding="utf-8")
            except OSError:
                pass
        self.catalogue = cached

    @_api
    def app_state(self) -> Dict[str, Any]:
        return {
            "version": __version__, "rclone": self.rclone or "", "rclone_version": self.version,
            "remotes": self.remotes, "settings": {k: v for k, v in self.store.settings.items() if k != "mounts"},
            "modes": {m: core.MODE_HELP[m] for m in core.MODES}, "platform": core.sys.platform,
            "confirm_word": CONFIRM_WORD, "fuse": mounts.fuse_status(),
        }

    @_api
    def save_settings(self, d: Dict[str, Any]) -> bool:
        allowed = {"rclone": str, "tray_on_close": bool, "default_disk": str}
        for k, typ in allowed.items():
            if k in d:
                self.store.settings[k] = typ(d[k])
        self._save()
        return True

    @_api
    def reload_remotes(self) -> List[Dict[str, Any]]:
        self.rclone = core.find_rclone(str(self.store.settings.get("rclone", "")))
        self.version = core.rclone_version(self.rclone) if self.rclone else ""
        self._load_remotes()
        return self.remotes

    @_api
    def flag_catalogue(self) -> List[Dict[str, Any]]:
        return self.catalogue

    @_api
    def create_crypt(self, name: str, base: str, password: str, salt: str, filename_encryption: str, dir_encryption: bool) -> List[Dict[str, Any]]:
        if not self.rclone:
            raise core.RcloneError("rclone was not found.")
        core.create_crypt_remote(self.rclone, name.strip(), base.strip(), password, salt, filename_encryption, bool(dir_encryption))
        self._load_remotes()
        return self.remotes

    # ---- jobs ---------------------------------------------------------------------------------------------
    def _job_view(self, job: core.Job) -> Dict[str, Any]:
        d = asdict(job)
        d["problems"] = core.validate_job(job, self.rclone)
        d["schedule"] = schedule.normalize(job.schedule)
        d["schedule_text"] = schedule.describe(job.schedule)
        nxt = schedule.next_run(job.schedule, datetime.now())
        d["next_run"] = nxt.strftime("%Y-%m-%d %H:%M") if nxt else ""
        d["dest_text"] = core.dest_spec(job) if (job.target or job.dest_kind == "remote" and job.remote) else ""
        d["crypt"] = any(r["name"] == job.remote and r["crypt"] for r in self.remotes) and job.dest_kind == "remote"
        d["busy"] = self.mgr.job_busy(job.id)
        d["move_ready"] = bool(job.dry_sig and job.dry_sig == core.job_signature(job) and time.time() - job.dry_ts < runs.DRY_RUN_VALID_SECONDS)
        return d

    @_api
    def jobs(self) -> List[Dict[str, Any]]:
        return [self._job_view(j) for j in self.store.jobs]

    @_api
    def new_job(self, mode: str = "copy") -> Dict[str, Any]:
        with self.lock:
            job = core.Job(name=self._unique_name("New %s job" % mode), mode=mode if mode in core.MODES else "copy",
                           disk=str(self.store.settings.get("default_disk", "hdd")))
            self.store.jobs.append(job)
            self._save()
        return self._job_view(job)

    def _unique_name(self, base: str) -> str:
        names = {j.name for j in self.store.jobs}
        name, n = base, 2
        while name in names:
            name, n = "%s %d" % (base, n), n + 1
        return name

    @_api
    def save_job(self, d: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            job = self._job(str(d.get("id", "")))
            if self.mgr.job_busy(job.id):
                raise ValueError("Stop this job before changing it.")
            _job_from(d, job)
            job.name = (job.name or "").strip() or "Untitled job"
            job.flags = flagmod.clean_overrides(job.flags, self.catalogue)
            job.schedule = schedule.normalize(job.schedule) if job.schedule else {}
            job.checkers, job.transfers = max(0, int(job.checkers or 0)), max(0, int(job.transfers or 0))
            self._save()
        return self._job_view(job)

    @_api
    def delete_job(self, job_id: str) -> bool:
        with self.lock:
            job = self._job(job_id)
            if self.mgr.job_busy(job.id):
                raise ValueError("Stop this job before deleting it.")
            self.store.jobs.remove(job)
            self._save()
        return True

    @_api
    def duplicate_job(self, job_id: str) -> Dict[str, Any]:
        with self.lock:
            src = self._job(job_id)
            data = asdict(src)
            for k in ("id", "last_run", "last_mode", "last_code", "last_summary", "dry_sig", "dry_ts"):
                data.pop(k, None)
            data["schedule"] = {}
            copy = _job_from(data, core.Job())
            copy.name = self._unique_name(src.name + " copy")
            self.store.jobs.append(copy)
            self._save()
        return self._job_view(copy)

    @_api
    def preview(self, job_id: str) -> Dict[str, str]:
        job = self._job(job_id)
        args = core.build_args(job, False, time.strftime("%Y%m%d-%H%M"))
        return {"dry": core.command_text(self.rclone or "rclone", args),
                "real": core.command_text(self.rclone or "rclone", [a for a in args if a != "--dry-run"])}

    @_api
    def export_script(self, job_id: str) -> Dict[str, str]:
        name, text = core.export_script(self._job(job_id), self.rclone or "rclone")
        out = core.config_dir() / "scripts"
        out.mkdir(parents=True, exist_ok=True)
        path = out / name
        path.write_text(text, encoding="utf-8", newline="")
        return {"path": str(path)}

    # ---- checking folders -------------------------------------------------------------------------------------
    @_api
    def path_info(self, path: str) -> Dict[str, Any]:
        """Local folder facts for the setup page: exists, free space, SSD/HDD guess. One cheap disk query."""
        path = (path or "").strip()
        info: Dict[str, Any] = {"exists": False, "free": "", "total": "", "disk": None}
        if not path:
            return info
        info["exists"] = core.check_local_path(path).state == "exists"
        probe = path
        while probe and not core.os.path.exists(probe):
            parent = core.os.path.dirname(probe)
            if parent == probe:
                break
            probe = parent
        try:
            usage = shutil.disk_usage(probe)
            info["free"], info["total"] = core.human_bytes(usage.free), core.human_bytes(usage.total)
        except OSError:
            pass
        info["disk"] = core.detect_disk_kind(path) if info["exists"] else None
        return info

    @_api
    def check_job(self, job_id: str, force: bool = False) -> Dict[str, Any]:
        """Verify the destination (and backup) folders. Remote jobs use ONE directory listing, reused for 15 minutes."""
        job = self._job(job_id)
        if core.is_local(job):
            res: Dict[str, Any] = {"target": asdict(core.check_local_path(job.target))}
            if core.uses_backup(job):
                res["backup"] = asdict(core.check_local_path(job.backup_root))
            res["problems"], res["listed"] = [], False
            return res
        if not self.rclone or not job.remote:
            raise ValueError("Choose a remote first.")
        key = (job.remote, job.list_depth)
        hit = self.listings.get(key)
        listed = False
        if force or not hit or time.time() - hit[0] > LISTING_TTL:
            dirs = core.list_dirs(self.rclone, job.remote, job.list_depth)
            self.listings[key] = (time.time(), dirs)
            listed = True
        else:
            dirs = hit[1]
        target, backup, problems = core.verify_against_listing(job, dirs, job.list_depth)
        return {"target": asdict(target), "backup": asdict(backup) if backup else None, "problems": problems, "listed": listed}

    @_api
    def folders(self, remote: str, depth: int = 1, force: bool = False) -> List[str]:
        """Folder list of a remote for the folder picker (shares the 15-minute cache with check_job)."""
        if not self.rclone:
            raise core.RcloneError("rclone was not found.")
        key = (remote, depth)
        hit = self.listings.get(key)
        if force or not hit or time.time() - hit[0] > LISTING_TTL:
            self.listings[key] = (time.time(), core.list_dirs(self.rclone, remote, depth))
        return self.listings[key][1]

    @_api
    def pick_folder(self, start: str = "") -> str:
        import webview
        win = self._main or (webview.windows[0] if webview.windows else None)
        if win is None:
            return ""
        dialog = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
        if dialog is None:
            dialog = webview.FOLDER_DIALOG
        res = win.create_file_dialog(dialog, directory=start if start and core.os.path.isdir(start) else "")
        return res[0] if res else ""

    # ---- running ---------------------------------------------------------------------------------------------------
    @_api
    def start(self, job_id: str, real: bool = False, confirm: str = "") -> str:
        job = self._job(job_id)
        if real and confirm.strip() != CONFIRM_WORD:
            raise ValueError("Type %s to confirm a real run." % CONFIRM_WORD)
        return self.mgr.start_job(job, bool(real))

    @_api
    def stop(self, run_id: str) -> bool:
        return self.mgr.stop(run_id)

    @_api
    def stop_all(self) -> int:
        return self.mgr.stop_all()

    @_api
    def runs(self) -> List[Dict[str, Any]]:
        return self.mgr.snapshot()

    @_api
    def clear_finished(self) -> bool:
        self.mgr.clear_finished()
        return True

    @_api
    def poll(self) -> Dict[str, Any]:
        notes = []
        while self.notes:
            notes.append(self.notes.popleft())
        return {"events": self.mgr.drain(), "runs": self.mgr.snapshot(), "notes": notes}

    @_api
    def console(self, run_id: str, since: int = 0) -> Dict[str, Any]:
        return self.mgr.console(run_id, int(since))

    @_api
    def open_path(self, what: str, run_id: str = "") -> bool:
        rec = self.mgr.records.get(run_id)
        if what == "log" and rec and rec.log_path:
            core.open_path(rec.log_path)
        elif what == "logs":
            core.open_path(str(core.log_dir()))
        elif what == "data":
            core.open_path(str(core.config_dir()))
        else:
            return False
        return True

    # ---- schedules ---------------------------------------------------------------------------------------------------
    @_api
    def set_schedule(self, job_id: str, sched: Dict[str, Any], confirm: str = "") -> Dict[str, Any]:
        with self.lock:
            job = self._job(job_id)
            s = schedule.normalize(sched)
            if s["enabled"] and s["real"]:
                if confirm.strip() != CONFIRM_WORD:
                    raise ValueError("Type %s to allow scheduled real runs of this job." % CONFIRM_WORD)
                problems = core.validate_job(job, self.rclone)
                if problems:
                    raise ValueError(" ".join(problems))
                s["real_sig"] = core.job_signature(job)
            else:
                s["real_sig"], s["real"] = "", False
            old = schedule.normalize(job.schedule)
            s["last_fired"] = old["last_fired"] if old["enabled"] else 0.0
            job.schedule = s
            self._save()
        return self._job_view(job)

    # ---- mounts ----------------------------------------------------------------------------------------------------------
    def _mount_specs(self) -> List[Dict[str, Any]]:
        return self.store.settings.setdefault("mounts", [])

    @_api
    def mounts(self) -> List[Dict[str, Any]]:
        out = []
        for raw in self._mount_specs():
            spec = mounts.spec_from_dict(raw)
            d = asdict(spec)
            active = next((r for r in self.mgr.snapshot() if r["kind"] == "mount" and r["name"] == spec.name and
                           r["state"] in ("mounting", "mounted", "stopping")), None)
            d["run"], d["state"] = (active["id"], active["state"]) if active else ("", "idle")
            d["problems"] = [] if active else mounts.validate_mount(spec)
            out.append(d)
        return out

    @_api
    def new_mount(self) -> Dict[str, Any]:
        spec = mounts.MountSpec(name="Mount %d" % (len(self._mount_specs()) + 1))
        self._mount_specs().append(asdict(spec))
        self._save()
        return asdict(spec)

    @_api
    def save_mount(self, d: Dict[str, Any]) -> bool:
        specs = self._mount_specs()
        spec = mounts.spec_from_dict(d)
        spec.flags = flagmod.clean_overrides(spec.flags, self.catalogue)
        for i, raw in enumerate(specs):
            if raw.get("id") == spec.id:
                specs[i] = asdict(spec)
                break
        else:
            specs.append(asdict(spec))
        self._save()
        return True

    @_api
    def delete_mount(self, mount_id: str) -> bool:
        specs = self._mount_specs()
        specs[:] = [s for s in specs if s.get("id") != mount_id]
        self._save()
        return True

    @_api
    def mount(self, mount_id: str) -> str:
        raw = next((s for s in self._mount_specs() if s.get("id") == mount_id), None)
        if not raw:
            raise ValueError("That mount no longer exists.")
        return self.mgr.start_mount(mounts.spec_from_dict(raw))

    @_api
    def about(self) -> Dict[str, str]:
        return {"version": __version__, "rclone": self.version}
