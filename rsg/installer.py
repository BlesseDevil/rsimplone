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
"""Guided rclone install. The app never downloads rclone itself: it offers the machine's own package manager
(winget or scoop on Windows, Homebrew on macOS and Linux) after the user says yes, and shows the exact command first.
Where no such manager exists (or the official script would need a password) it only shows the command to copy.
The command list is fixed in this file; nothing the page sends is ever part of a command."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
from typing import Any, Dict, List, Optional

from . import core

IS_WIN = os.name == "nt"
INSTALL_PAGE = "https://rclone.org/install/"
LINUX_SCRIPT = "sudo -v ; curl https://rclone.org/install.sh | sudo bash"
_TIMEOUT = 900  # seconds; a package manager that is still going after this is stuck

_lock = threading.Lock()
_state: Dict[str, Any] = {"state": "idle", "tail": [], "found": ""}


def _which(name: str) -> Optional[str]:
    found = shutil.which(name)
    if found:
        return found
    # a window started from the desktop often has a short PATH: look where these managers put their programs
    extra = [r"%LOCALAPPDATA%\Microsoft\WindowsApps", r"~\scoop\shims"] if IS_WIN else \
        ["/opt/homebrew/bin", "/usr/local/bin", "/home/linuxbrew/.linuxbrew/bin"]
    for d in extra:
        d = os.path.expandvars(os.path.expanduser(d))
        for ext in ((".exe", ".cmd", ".bat") if IS_WIN else ("",)):
            p = os.path.join(d, name + ext)
            if os.path.isfile(p):
                return p
    return None


def plan() -> Dict[str, Any]:
    """What this machine can do. `command` is the exact argument list that Install would run (empty when the user has to
    run something themselves); `text` is what is shown and copied."""
    out: Dict[str, Any] = {"os": "windows" if IS_WIN else ("macos" if sys.platform == "darwin" else "linux"),
                           "method": "", "label": "", "command": [], "text": "", "can_run": False, "page": INSTALL_PAGE}
    if IS_WIN:
        winget, scoop = _which("winget"), _which("scoop")
        if winget:
            out.update(method="winget", label="Windows Package Manager (winget)",
                       command=[winget, "install", "--id", "Rclone.Rclone", "--exact", "--silent",
                                "--accept-source-agreements", "--accept-package-agreements"])
        elif scoop:
            out.update(method="scoop", label="Scoop", command=[scoop, "install", "rclone"])
    else:
        brew = _which("brew")
        if brew:
            out.update(method="brew", label="Homebrew", command=[brew, "install", "rclone"])
    if out["command"]:
        out["can_run"] = True
        out["text"] = " ".join(["winget" if out["method"] == "winget" else os.path.basename(out["command"][0])] + out["command"][1:])
    elif not IS_WIN and out["os"] == "linux":
        out.update(method="script", label="rclone's official install script", text=LINUX_SCRIPT)
    return out


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_CLEAN = re.compile(r"[^\x20-\x7e]")


def _tidy(line: str) -> str:
    return _CLEAN.sub("", _ANSI.sub("", line).split("\r")[-1]).strip()[:200]


def status() -> Dict[str, Any]:
    with _lock:
        return {"state": _state["state"], "tail": list(_state["tail"]), "found": _state["found"]}


def _set(**kw: Any) -> None:
    with _lock:
        _state.update(kw)


def _run(command: List[str]) -> None:
    tail: List[str] = []
    try:
        kw: Dict[str, Any] = {}
        if IS_WIN:
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        proc = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, errors="replace", **kw)
        timer = threading.Timer(_TIMEOUT, proc.kill)
        timer.start()
        try:
            assert proc.stdout is not None
            for raw in proc.stdout:
                line = _tidy(raw)
                if line:
                    tail = (tail + [line])[-8:]
                    _set(tail=tail)
            proc.wait()
        finally:
            timer.cancel()
        path = core.find_rclone("")
        version = core.rclone_version(path) if path else ""
        if version:
            _set(state="done", found=version)
        else:
            _set(state="failed", tail=tail + ["The installer finished but rclone was not found afterwards."])
    except Exception as exc:  # noqa: BLE001
        _set(state="failed", tail=tail + ["Could not start the installer: %s" % type(exc).__name__])


def start() -> Dict[str, Any]:
    """Run the planned command, once at a time. The caller must already have the user's yes."""
    p = plan()
    if not p["can_run"]:
        raise ValueError("This computer has no package manager rSimpLone can use. Copy the command shown and run it yourself.")
    with _lock:
        if _state["state"] == "running":
            raise ValueError("The install is already running.")
        _state.update(state="running", tail=[], found="")
    threading.Thread(target=_run, args=(list(p["command"]),), daemon=True).start()
    return status()
