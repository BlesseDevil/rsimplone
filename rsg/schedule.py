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
"""In-app job scheduler: pure timing rules plus a small ticking thread. It only runs while the app is open.
A schedule is a plain dict stored on the job:
  {enabled, kind: interval|daily|weekly, every_min, time: 'HH:MM', days: [0..6, Monday=0],
   real: bool, real_sig: str, last_fired: float}
A scheduled REAL run needs `real` plus a `real_sig` that still matches the job (the user typed EXECUTE for exactly
this configuration); otherwise the scheduler does a dry run instead."""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional

KINDS = ("interval", "daily", "weekly")
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
GRACE = timedelta(hours=2)      # a fixed-time slot missed by more than this (app was closed) is skipped, not run late


def normalize(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    s = dict(raw or {})
    kind = s.get("kind") if s.get("kind") in KINDS else "daily"
    try:
        every = int(s.get("every_min", 60))
    except (TypeError, ValueError):
        every = 60
    hh, mm = 2, 0
    try:
        hh, mm = [int(p) for p in str(s.get("time", "02:00")).split(":")[:2]]
        hh, mm = max(0, min(23, hh)), max(0, min(59, mm))
    except ValueError:
        hh, mm = 2, 0
    days = sorted({int(d) for d in (s.get("days") or []) if str(d).isdigit() and 0 <= int(d) <= 6}) or [0, 1, 2, 3, 4, 5, 6]
    return {
        "enabled": bool(s.get("enabled")), "kind": kind, "every_min": max(5, min(7 * 24 * 60, every)),
        "time": "%02d:%02d" % (hh, mm), "days": days, "real": bool(s.get("real")),
        "real_sig": str(s.get("real_sig", "")), "last_fired": float(s.get("last_fired") or 0.0),
    }


def _slots(s: Dict[str, Any], around: datetime) -> List[datetime]:
    hh, mm = [int(p) for p in s["time"].split(":")]
    allowed = s["days"] if s["kind"] == "weekly" else list(range(7))
    out = []
    for back in range(-8, 9):
        d = around + timedelta(days=-back)
        if d.weekday() in allowed:
            out.append(d.replace(hour=hh, minute=mm, second=0, microsecond=0))
    return sorted(out)


def next_run(raw: Optional[Dict[str, Any]], now: datetime) -> Optional[datetime]:
    """When the schedule will next fire after `now`, or None if it is off."""
    s = normalize(raw)
    if not s["enabled"]:
        return None
    if s["kind"] == "interval":
        last = datetime.fromtimestamp(s["last_fired"]) if s["last_fired"] else now
        due = last + timedelta(minutes=s["every_min"])
        return due if due > now else now
    for slot in _slots(s, now + timedelta(days=0)):
        if slot > now:
            return slot
    return None


def is_due(raw: Optional[Dict[str, Any]], now: datetime) -> bool:
    s = normalize(raw)
    if not s["enabled"]:
        return False
    last = s["last_fired"]
    if s["kind"] == "interval":
        if not last:
            return False        # the first interval starts counting when the schedule is switched on (it stamps last_fired)
        return now.timestamp() >= last + s["every_min"] * 60
    past = [slot for slot in _slots(s, now) if slot <= now]
    if not past:
        return False
    slot = past[-1]
    return slot.timestamp() > last and now - slot <= GRACE


def describe(raw: Optional[Dict[str, Any]]) -> str:
    s = normalize(raw)
    if not s["enabled"]:
        return "Off"
    if s["kind"] == "interval":
        m = s["every_min"]
        return "Every %s" % ("%d min" % m if m < 60 else ("%g h" % (m / 60.0)))
    when = "daily at " + s["time"] if s["kind"] == "daily" else "%s at %s" % (", ".join(DAY_NAMES[d] for d in s["days"]), s["time"])
    return when[0].upper() + when[1:]


class Scheduler:
    """Ticks every few seconds; for each due job calls fire(job, real). `jobs()` returns the current jobs and
    `save()` persists a changed last_fired. Never fires a job that is already running (`busy(job_id)`)."""

    def __init__(self, jobs: Callable[[], Iterable[Any]], fire: Callable[[Any, bool], None],
                 busy: Callable[[str], bool], save: Callable[[], None], signature: Callable[[Any], str],
                 interval: float = 15.0) -> None:
        self.jobs, self.fire, self.busy, self.save, self.signature, self.interval = jobs, fire, busy, save, signature, interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="rsg-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick(datetime.now())
            except Exception:  # noqa: BLE001  (a bad schedule must not kill the ticker)
                pass

    def tick(self, now: datetime) -> List[str]:
        fired: List[str] = []
        changed = False
        for job in list(self.jobs()):
            s = normalize(getattr(job, "schedule", None))
            if not s["enabled"]:
                continue
            raw = getattr(job, "schedule")
            if s["kind"] == "interval" and not s["last_fired"]:
                raw["last_fired"] = now.timestamp()     # start counting from now
                changed = True
                continue
            if not is_due(s, now) or self.busy(job.id):
                continue
            real = bool(s["real"] and s["real_sig"] and s["real_sig"] == self.signature(job))
            raw["last_fired"] = now.timestamp()
            changed = True
            try:
                self.fire(job, real)
                fired.append(job.id)
            except Exception:  # noqa: BLE001
                pass
        if changed:
            self.save()
        return fired
