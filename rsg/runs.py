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
"""Several runs at once: one registry for job runs and mounts, with the safety checks that only make sense
across runs (two jobs writing the same place, a real MOVE without a matching dry run)."""
from __future__ import annotations

import collections
import os
import queue
import threading
import time
import uuid
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from . import core, mounts

DRY_RUN_VALID_SECONDS = core.DRY_RUN_VALID_SECONDS
CONSOLE_LINES = 5000


class RunRefused(Exception):
    """A run was not started because it would be unsafe or impossible; the message says why."""


class _Tagged:
    """Looks like a queue to SyncRun, but tags every event with its run id."""

    def __init__(self, run_id: str, sink: "queue.Queue[Tuple[str, str, Any]]") -> None:
        self.run_id, self.sink = run_id, sink

    def put(self, item: Tuple[str, Any]) -> None:
        self.sink.put((self.run_id, item[0], item[1]))


def _footprint(job: core.Job) -> List[Tuple[str, str, bool]]:
    """(place kind, place, writes) for everything a job touches. Remote places are 'remote:path'."""
    out: List[Tuple[str, str, bool]] = []
    if core.is_local(job):
        if job.target.strip():
            out.append(("local", os.path.normcase(os.path.abspath(job.target)), True))
        if job.backup_root.strip():
            out.append(("local", os.path.normcase(os.path.abspath(job.backup_root)), True))
    else:
        if job.target.strip():
            out.append(("remote", job.remote + ":" + core.norm_remote_path(job.target), True))
        if job.backup_root.strip():
            out.append(("remote", job.remote + ":" + core.norm_remote_path(job.backup_root), True))
    if job.source.strip():
        out.append(("local", os.path.normcase(os.path.abspath(job.source)), job.mode == "move"))
    return out


def _same_place(a: Tuple[str, str, bool], b: Tuple[str, str, bool]) -> bool:
    if a[0] != b[0]:
        return False
    if a[0] == "local":
        return core.local_overlap(a[1], b[1])
    ra, pa = a[1].split(":", 1)
    rb, pb = b[1].split(":", 1)
    return ra == rb and (not pa or not pb or core.paths_overlap(pa, pb))


def conflicts(job: core.Job, running: List[core.Job]) -> Optional[str]:
    """Why `job` must not start next to the jobs already running, or None."""
    mine = _footprint(job)
    for other in running:
        if other.id == job.id:
            return "This job is already running."
        for a in mine:
            for b in _footprint(other):
                if (a[2] or b[2]) and _same_place(a, b):
                    return "'%s' is running and works on the same place (%s). Wait for it to finish." % (other.name, b[1])
    return None


class Record:
    def __init__(self, run_id: str, kind: str, name: str, job: Optional[core.Job] = None, real: bool = False,
                 spec: Optional[mounts.MountSpec] = None) -> None:
        self.id, self.kind, self.name, self.job, self.real, self.spec = run_id, kind, name, job, real, spec
        self.state = "running"
        self.started = time.time()
        self.ended = 0.0
        self.stats: Dict[str, Any] = {}
        self.counts: Dict[str, int] = {}
        self.result: Optional[core.RunResult] = None
        self.console: Deque[str] = collections.deque(maxlen=CONSOLE_LINES)
        self.console_total = 0
        self.errors = 0
        self.backup_dir = ""
        self.log_path = ""
        self.sync: Optional[core.SyncRun] = None
        self.mount: Optional[mounts.MountRun] = None

    def view(self) -> Dict[str, Any]:
        st = self.stats or {}
        total, done = st.get("totalBytes", 0) or 0, st.get("bytes", 0) or 0
        r = self.result
        return {
            "id": self.id, "kind": self.kind, "name": self.name, "job_id": self.job.id if self.job else "",
            "mode": self.job.mode if self.job else "mount", "real": self.real, "state": self.state,
            "started": self.started, "ended": self.ended, "bytes": done, "total": total,
            "speed": st.get("speed", 0) or 0, "eta": st.get("eta"), "transfers": st.get("transfers", 0),
            "checks": st.get("checks", 0), "errors": self.errors, "counts": dict(self.counts),
            "backup_dir": self.backup_dir, "log_path": self.log_path,
            "summary": r.summary if r else "", "code": r.code if r else None, "meaning": r.meaning if r else "",
            "mountpoint": self.spec.mountpoint if self.spec else "",
        }


class RunManager:
    def __init__(self, rclone_getter: Callable[[], Optional[str]], on_done: Optional[Callable[[Record], None]] = None) -> None:
        self.rclone_getter = rclone_getter
        self.on_done = on_done
        self.records: Dict[str, Record] = {}
        self.order: List[str] = []
        self._q: "queue.Queue[Tuple[str, str, Any]]" = queue.Queue()
        self._out: Deque[Dict[str, Any]] = collections.deque(maxlen=20000)
        self._lock = threading.RLock()
        self._pump_thread = threading.Thread(target=self._pump, name="rsg-runs", daemon=True)
        self._pump_thread.start()

    # ---- starting and stopping ---------------------------------------------------------------
    def running_jobs(self) -> List[core.Job]:
        with self._lock:
            return [r.job for r in self.records.values() if r.kind == "job" and r.job and r.state in ("running", "stopping")]

    def job_busy(self, job_id: str) -> bool:
        return any(j.id == job_id for j in self.running_jobs())

    def start_job(self, job: core.Job, real: bool) -> str:
        rclone = self.rclone_getter()
        problems = core.validate_job(job, rclone)
        if problems:
            raise RunRefused(" ".join(problems))
        if real and core.move_gate(job):
            raise RunRefused(str(core.move_gate(job)))
        why = self._remote_inside_local(rclone, job)
        if why:
            raise RunRefused(why)
        with self._lock:
            why = conflicts(job, self.running_jobs())
            if why:
                raise RunRefused(why)
            run_id = uuid.uuid4().hex[:10]
            rec = Record(run_id, "job", job.name, job=job, real=real)
            run = core.SyncRun(rclone or "rclone", job, real, _Tagged(run_id, self._q))   # type: ignore[arg-type]
            rec.sync = run
            self.records[run_id] = rec          # registered first: the pump must know the run before its first event
            self.order.append(run_id)
            try:
                run.start()
            except Exception as exc:  # noqa: BLE001
                self.records.pop(run_id, None)
                self.order.remove(run_id)
                raise RunRefused(str(exc))
            rec.log_path, rec.backup_dir = run.log_path, run.backup_dir
        self._emit(run_id, "state", rec.view())
        return run_id

    @staticmethod
    def _remote_inside_local(rclone: Optional[str], job: core.Job) -> Optional[str]:
        """A remote can secretly be a folder on this computer (local, alias, crypt over a local folder...). If so the
        usual folder-overlap rules apply to it as well."""
        if not rclone or core.is_local(job) or not job.remote:
            return None
        base = core.remote_local_root(rclone, job.remote)
        if base is None:
            return None
        places = []
        for label, rel in (("destination", job.target), ("backup folder", job.backup_root)):
            if not rel.strip():
                continue
            path = os.path.join(base, core.norm_remote_path(rel)) if base else core.norm_remote_path(rel).replace("/", os.sep)
            if os.path.isabs(path):
                places.append((label, path))
        for label, path in places:
            if core.local_overlap(job.source, path):
                return "The %s is, through the remote '%s', a folder inside (or around) your source folder. Choose a separate place." % (label, job.remote)
        if len(places) == 2 and core.local_overlap(places[0][1], places[1][1]):
            return "Through the remote '%s' the destination and the backup folder overlap." % job.remote
        return None

    def start_mount(self, spec: mounts.MountSpec) -> str:
        rclone = self.rclone_getter()
        if not rclone:
            raise RunRefused("rclone was not found.")
        with self._lock:
            for r in self.records.values():
                if r.kind == "mount" and r.spec and r.spec.id == spec.id and r.state in ("running", "stopping"):
                    raise RunRefused("This mount is already active.")
            run_id = uuid.uuid4().hex[:10]
            rec = Record(run_id, "mount", spec.name, spec=spec)
            rec.state = "mounting"
            mrun = mounts.MountRun(rclone, spec, lambda kind, payload, rid=run_id: self._q.put((rid, "m" + kind, payload)))
            rec.mount = mrun
            self.records[run_id] = rec
            self.order.append(run_id)
            try:
                mrun.start()
            except Exception as exc:  # noqa: BLE001
                self.records.pop(run_id, None)
                self.order.remove(run_id)
                raise RunRefused(str(exc))
        self._emit(run_id, "state", rec.view())
        return run_id

    def stop(self, run_id: str) -> bool:
        rec = self.records.get(run_id)
        if not rec:
            return False
        if rec.sync and rec.sync.running:
            rec.state = "stopping"
            rec.sync.stop()
        elif rec.mount and rec.mount.running:
            rec.mount.stop()
        else:
            return False
        self._emit(run_id, "state", rec.view())
        return True

    def stop_all(self) -> int:
        n = 0
        for rid in list(self.records):
            n += 1 if self.stop(rid) else 0
        return n

    def active(self) -> int:
        return sum(1 for r in self.records.values() if r.state in ("running", "stopping", "mounting", "mounted"))

    def clear_finished(self) -> None:
        with self._lock:
            for rid in [r.id for r in self.records.values() if r.state in ("done", "failed", "stopped")]:
                self.records.pop(rid, None)
                if rid in self.order:
                    self.order.remove(rid)

    # ---- reading ---------------------------------------------------------------------------------
    def snapshot(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [self.records[i].view() for i in self.order if i in self.records]

    def console(self, run_id: str, since: int = 0) -> Dict[str, Any]:
        """Console lines with sequence number >= since. 'next' is what to ask for next time."""
        rec = self.records.get(run_id)
        if not rec:
            return {"lines": [], "next": since, "reset": True}
        first = rec.console_total - len(rec.console)
        start = max(since, first)
        lines = list(rec.console)[start - first:]
        return {"lines": lines, "next": rec.console_total, "reset": since < first}

    def drain(self, limit: int = 600) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        while self._out and len(out) < limit:
            out.append(self._out.popleft())
        return out

    # ---- internals -------------------------------------------------------------------------------
    def _emit(self, run_id: str, kind: str, payload: Any) -> None:
        self._out.append({"run": run_id, "kind": kind, "data": payload})

    def _pump(self) -> None:
        while True:
            run_id, kind, payload = self._q.get()
            rec = self.records.get(run_id)
            if rec is None:
                continue
            try:
                self._apply(rec, kind, payload)
            except Exception:  # noqa: BLE001  (never let one odd event stop the pump)
                pass

    def _apply(self, rec: Record, kind: str, payload: Any) -> None:
        if kind in ("log", "mlog"):
            rec.console.append(payload["text"])
            rec.console_total += 1
            self._emit(rec.id, "log", {"n": rec.console_total})
        elif kind == "stats":
            rec.stats = payload
            rec.errors = int(payload.get("errors", 0) or 0)
            self._emit(rec.id, "state", rec.view())
        elif kind == "activity":
            rec.counts[payload["kind"]] = rec.counts.get(payload["kind"], 0) + 1
            self._emit(rec.id, "activity", payload)
        elif kind == "done":
            res: core.RunResult = payload["result"]
            rec.result = res
            rec.stats = payload.get("stats") or rec.stats
            rec.counts = dict(res.counts) or rec.counts
            rec.errors = len(res.errors)
            rec.ended = time.time()
            rec.state = "stopped" if res.stopped else ("done" if res.code in (0, 9) else "failed")
            if self.on_done:
                try:
                    self.on_done(rec)
                except Exception:  # noqa: BLE001
                    pass
            self._emit(rec.id, "state", rec.view())
        elif kind == "mstate":
            st = payload.get("state", "")
            rec.state = {"mounting": "mounting", "mounted": "mounted", "stopping": "stopping",
                         "stopped": "stopped", "failed": "failed"}.get(st, rec.state)
            if st in ("stopped", "failed"):
                rec.ended = time.time()
                if st == "failed":
                    rec.counts["error"] = 1
                    rec.console.append("mount ended: %s" % (payload.get("meaning") or "see the lines above"))
                    rec.console_total += 1
            self._emit(rec.id, "state", rec.view())
        elif kind == "started":
            self._emit(rec.id, "state", rec.view())
