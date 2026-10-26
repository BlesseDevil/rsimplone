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
"""Mounting a remote (or one of its folders) as a drive / folder with `rclone mount`. Standard library only."""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Callable, Dict, List, Optional

from . import core, flags as flagmod

CACHE_MODES = ("off", "minimal", "writes", "full")


@dataclass
class MountSpec:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = "New mount"
    remote: str = ""            # remote name without the colon
    path: str = ""              # folder on the remote ("" mounts the whole remote)
    mountpoint: str = ""        # a drive letter like X: (Windows) or an empty folder
    vfs_cache_mode: str = "writes"
    read_only: bool = True      # safest default: browse and copy out, nothing can be changed or deleted by accident
    flags: Dict[str, Any] = field(default_factory=dict)
    extra: str = ""
    auto_mount: bool = False    # mount again whenever the app starts


def spec_from_dict(raw: Dict[str, Any]) -> MountSpec:
    known = {f.name for f in fields(MountSpec)}
    return MountSpec(**{k: v for k, v in raw.items() if k in known})


def fuse_status() -> Dict[str, Any]:
    """Is the system driver that `rclone mount` needs installed? Nothing is bundled or installed by this app."""
    if core.IS_WIN:
        roots = [os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")]
        found = any(r and os.path.isdir(os.path.join(r, "WinFsp")) for r in roots)
        return {"ok": found, "name": "WinFsp", "url": "https://winfsp.dev",
                "message": "" if found else "Mounting on Windows needs WinFsp. Install it from winfsp.dev, then try again."}
    if sys.platform == "darwin":
        found = any(os.path.exists(p) for p in ("/Library/Filesystems/macfuse.fs", "/Library/Filesystems/fuse-t.fs", "/usr/local/lib/libfuse-t.dylib"))
        return {"ok": found, "name": "macFUSE or FUSE-T", "url": "https://macfuse.io",
                "message": "" if found else "Mounting on macOS needs macFUSE (or FUSE-T). Install one, then try again."}
    found = bool(shutil.which("fusermount3") or shutil.which("fusermount"))
    return {"ok": found, "name": "FUSE", "url": "https://github.com/libfuse/libfuse",
            "message": "" if found else "Mounting on Linux needs FUSE. Install fuse3 with your package manager, then try again."}


def validate_mount(spec: MountSpec) -> List[str]:
    errs: List[str] = []
    if not spec.remote:
        errs.append("Choose a remote to mount.")
    mp = spec.mountpoint.strip()
    if not mp:
        errs.append("Choose where to mount it.")
    elif core.IS_WIN:
        if re.fullmatch(r"[A-Za-z]:", mp):
            if os.path.exists(mp + "\\"):
                errs.append("Drive %s is already in use. Pick a free letter." % mp.upper())
        elif not os.path.isabs(mp):
            errs.append("Use a drive letter like X: or a full folder path that does not exist yet.")
        elif os.path.exists(mp):
            errs.append("On Windows the mount folder must not exist yet (rclone creates it). Pick a new name inside an existing folder.")
    else:
        if not os.path.isabs(mp):
            errs.append("Use a full folder path for the mount point.")
        elif os.path.isdir(mp) and os.listdir(mp):
            errs.append("The mount folder is not empty.")
    if spec.vfs_cache_mode not in CACHE_MODES:
        errs.append("Unknown cache mode.")
    try:
        mount_args(spec)
    except ValueError as exc:
        errs.append(str(exc))
    return errs


def mount_args(spec: MountSpec) -> List[str]:
    """Arguments after the rclone executable."""
    src = "%s:%s" % (spec.remote, core.norm_remote_path(spec.path))
    m: Dict[str, Any] = {"--vfs-cache-mode": spec.vfs_cache_mode, "--volname": spec.name or spec.remote}
    if spec.read_only:
        m["--read-only"] = None
    if core.IS_WIN:
        m["--network-mode"] = None      # shows as a network drive; far fewer permission and Explorer oddities
    args = ["mount", src, spec.mountpoint.strip()]
    args += flagmod.merge(m, spec.flags, spec.extra)
    args += ["-v", "--use-json-log"]
    return args


class MountRun:
    """One running `rclone mount`. Reports through `emit(kind, payload)`: state, log."""

    def __init__(self, rclone: str, spec: MountSpec, emit: Callable[[str, Any], None]) -> None:
        self.rclone, self.spec, self.emit = rclone, spec, emit
        self.proc: Optional[subprocess.Popen] = None
        self.state = "idle"       # mounting | mounted | stopping | stopped | failed
        self.tail: List[str] = []
        self.stopping = False

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        errs = validate_mount(self.spec)
        if errs:
            raise core.RcloneError(" ".join(errs))
        fuse = fuse_status()
        if not fuse["ok"]:
            raise core.RcloneError(fuse["message"])
        if not core.IS_WIN:
            os.makedirs(self.spec.mountpoint, exist_ok=True)
        args = mount_args(self.spec)
        self.proc = subprocess.Popen(
            [self.rclone] + args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", **core._popen_flags())
        self._set("mounting")
        threading.Thread(target=self._reader, name="rclone-mount", daemon=True).start()
        threading.Thread(target=self._watch_ready, name="rclone-mount-ready", daemon=True).start()

    def _set(self, state: str) -> None:
        self.state = state
        self.emit("state", {"state": state, "tail": self.tail[-5:]})

    def _watch_ready(self) -> None:
        mp = self.spec.mountpoint.strip()
        probe = mp + "\\" if core.IS_WIN and re.fullmatch(r"[A-Za-z]:", mp) else mp
        for _ in range(60):
            time.sleep(0.5)
            if not self.running:
                return
            if os.path.exists(probe) and self.state == "mounting":
                self._set("mounted")
                return

    def _reader(self) -> None:
        assert self.proc is not None and self.proc.stderr is not None
        for line in self.proc.stderr:
            line = line.rstrip("\r\n")
            if not line:
                continue
            text = line
            try:
                rec = json.loads(line)
                if isinstance(rec, dict) and "msg" in rec:
                    stamp = str(rec.get("time", ""))[:19].replace("T", " ").replace("-", "/")
                    obj = str(rec.get("object", ""))
                    text = "%s %-5s : %s%s" % (stamp, str(rec.get("level", "info")).upper(), (obj + ": ") if obj else "", rec["msg"])
            except ValueError:
                pass
            self.tail.append(text)
            del self.tail[:-200]
            self.emit("log", {"level": "info", "text": text})
        code = self.proc.wait()
        self.state = "stopped" if self.stopping or code == 0 else "failed"
        self.emit("state", {"state": self.state, "code": code, "tail": self.tail[-5:],
                            "meaning": "" if self.state == "stopped" else core.exit_meaning(code)})

    def stop(self) -> None:
        """Unmount: rclone unmounts cleanly when interrupted; kill it if it has not left after a few seconds."""
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        self.stopping = True
        self._set("stopping")
        try:
            if core.IS_WIN:
                proc.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            else:
                os.killpg(proc.pid, signal.SIGINT)
        except Exception:  # noqa: BLE001
            proc.terminate()
        timer = threading.Timer(8.0, self._force)
        timer.daemon = True
        timer.start()

    def _force(self) -> None:
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
            if not core.IS_WIN:
                for tool in ("fusermount3", "fusermount"):
                    if shutil.which(tool):
                        subprocess.run([tool, "-u", self.spec.mountpoint], capture_output=True)
                        break
