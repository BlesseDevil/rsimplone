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
"""Portable logic for rSimpLone, the rclone copy/sync/move manager. Standard library only, no GUI imports."""
from __future__ import annotations

import contextlib
import json
import os
import queue
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import flags as flagmod

APP_NAME = "rSimpLone"
LEGACY_APP_NAME = "rclone-sync-gui"
IS_WIN = sys.platform.startswith("win")
MODES = ("copy", "sync", "move")
MODE_HELP = {
    "copy": "Adds new and changed files. Never deletes anything (a changed file replaces the old copy: set a backup folder to keep it).",
    "sync": "Mirrors the source. Anything replaced or removed goes into the backup folder, never lost.",
    "move": "Transfers files, then removes the originals. Always preview with a dry run first.",
}

EXIT_MEANINGS = {
    0: "success - finished without errors",
    1: "error - a usage/syntax problem or file errors; see the log",
    2: "uncategorised error - see the errors listed in the log",
    3: "directory not found - the source or destination folder does not exist",
    4: "file not found",
    5: "temporary error - retries ran out (network or Drive rate limit?); running again usually fixes it",
    6: "less serious errors - some items failed; check the log",
    7: "fatal error - retrying will not help; see the log",
    8: "transfer limit exceeded (--max-transfer)",
    9: "successful, but no files were transferred",
}


def exit_meaning(code: Optional[int]) -> str:
    if code is None:
        return "no exit code"
    return EXIT_MEANINGS.get(code, "unknown exit code - see the log")


# --------------------------------------------------------------------------------------------
# storage
# --------------------------------------------------------------------------------------------
def config_dir() -> Path:
    override = os.environ.get("RSG_HOME")
    if override:
        return Path(override)
    if IS_WIN:
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    folder = Path(base) / APP_NAME
    legacy = Path(base) / LEGACY_APP_NAME
    if not folder.exists() and legacy.exists():      # the app was renamed: carry the saved jobs over, once
        try:
            legacy.rename(folder)
        except OSError:
            pass
    return folder


def log_dir() -> Path:
    return config_dir() / "logs"


@dataclass
class Job:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = "New job"
    dest_kind: str = "remote"     # remote: a cloud remote; local: another folder on this computer
    mode: str = "sync"            # sync: mirror + keep removed/replaced files; copy: add/update only, never delete
    source: str = ""
    remote: str = ""              # rclone remote name, without the colon
    target: str = ""              # folder on the remote
    backup_root: str = ""         # folder on the remote; required for sync, optional for copy
    label: str = ""               # sub-folder inside backup_root; default: name of the source folder
    skip_existing: bool = False   # copy only: leave files that already exist on the remote untouched
    api_low: bool = True          # use as few Drive API calls as practical
    no_dir_modtime: bool = False  # tick to skip copying local folder dates onto remote folders (one call per differing folder)
    disk: str = "hdd"             # hdd | ssd
    bw_mbps: float = 30.0
    bw_percent: int = 85
    no_bw_limit: bool = False
    checkers: int = 0             # 0 = profile default
    transfers: int = 0
    list_depth: int = 1
    flags: Dict[str, Any] = field(default_factory=dict)       # rclone flag tweaks that differ from rclone's defaults
    extra: str = ""               # further flags typed by hand (app-owned flags are refused)
    schedule: Dict[str, Any] = field(default_factory=dict)    # see schedule.py
    dry_sig: str = ""             # fingerprint of the last good dry run; a real MOVE needs a matching one
    dry_ts: float = 0.0
    last_run: str = ""
    last_mode: str = ""
    last_code: Optional[int] = None
    last_summary: str = ""


@dataclass
class Store:
    jobs: List[Job] = field(default_factory=list)
    settings: Dict[str, Any] = field(default_factory=dict)


def _jobs_file() -> Path:
    return config_dir() / "jobs.json"


def load_store() -> Store:
    path = _jobs_file()
    store = Store()
    if not path.exists():
        return store
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # keep the unreadable file around instead of silently overwriting it on the next save
        try:
            path.replace(path.with_suffix(".broken.json"))
        except OSError:
            pass
        return store
    known = {f.name for f in fields(Job)}
    for raw in data.get("jobs", []):
        if isinstance(raw, dict):
            store.jobs.append(Job(**{k: v for k, v in raw.items() if k in known}))
    store.settings = data.get("settings", {}) if isinstance(data.get("settings"), dict) else {}
    return store


def save_store(store: Store) -> None:
    path = _jobs_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "jobs": [asdict(j) for j in store.jobs], "settings": store.settings}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------------------------
# paths and verification
# --------------------------------------------------------------------------------------------
def norm_remote_path(text: str) -> str:
    return text.replace("\\", "/").strip().strip("/")


def source_leaf(source: str) -> str:
    cleaned = os.path.normpath(source) if source else ""
    leaf = os.path.basename(cleaned.rstrip("\\/"))
    return leaf


def job_label(job: Job) -> str:
    label = job.label.strip() or source_leaf(job.source) or norm_remote_path(job.target).split("/")[-1] or "root"
    label = re.sub(r'[\\/:*?"<>|]', "_", label)
    return label if label.strip(". ") else "_"        # '.' and '..' would point out of the backup folder


def backup_path(job: Job, stamp: str) -> str:
    return "/".join(p for p in (norm_remote_path(job.backup_root), job_label(job), stamp) if p)


def needs_backup(job: Job) -> bool:
    """Sync and Move may not run without a backup folder: both can replace or remove files for good otherwise."""
    return job.mode in ("sync", "move")


def uses_backup(job: Job) -> bool:
    return needs_backup(job) or bool(job.backup_root.strip())


def is_local(job: Job) -> bool:
    return job.dest_kind == "local"


def dest_spec(job: Job) -> str:
    """What rclone gets as the destination: a plain folder path, or 'remote:folder'."""
    if is_local(job):
        return os.path.normpath(job.target.strip())
    return "%s:%s" % (job.remote, norm_remote_path(job.target))


def backup_spec(job: Job, stamp: str) -> str:
    if is_local(job):
        return os.path.join(os.path.normpath(job.backup_root.strip()), job_label(job), stamp)
    return "%s:%s" % (job.remote, backup_path(job, stamp))


def paths_overlap(a: str, b: str) -> bool:
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _real(path: str) -> str:
    """A comparable form of a local path: absolute, symlinks/junctions/8.3 names resolved, no \\\\?\\ prefix."""
    p = os.path.realpath(os.path.abspath(path))
    for prefix in ("\\\\?\\UNC\\", "\\\\?\\"):
        if p.startswith(prefix):
            p = ("\\\\" + p[len(prefix):]) if "UNC" in prefix else p[len(prefix):]
            break
    return os.path.normcase(p)


def is_drive_root(path: str) -> bool:
    p = os.path.abspath(path)
    return os.path.dirname(p) == p


def local_overlap(a: str, b: str) -> bool:
    a, b = _real(a), _real(b)
    ap, bp = (a if a.endswith(os.sep) else a + os.sep), (b if b.endswith(os.sep) else b + os.sep)    # 'C:\' already ends in a separator
    return ap.startswith(bp) or bp.startswith(ap)


@dataclass
class PathVerdict:
    path: str
    state: str          # exists | missing | unverified
    duplicate: bool = False
    near: str = ""


def check_path(path: str, dirs: List[str], depth: int) -> PathVerdict:
    """Check a remote folder path against ONE earlier listing; no API calls."""
    segments = path.split("/")
    verdict = PathVerdict(path=path, state="unverified")
    for k in range(1, min(len(segments), depth) + 1):
        prefix = "/".join(segments[:k])
        hits = [d for d in dirs if d == prefix]
        if not hits:
            verdict.state = "missing"
            verdict.near = next((d for d in dirs if d.lower() == prefix.lower()), "")
            return verdict
        if len(hits) > 1:
            verdict.duplicate = True
    if len(segments) <= depth:
        verdict.state = "exists"
    return verdict


MOVE_UNSAFE = {"--update", "--size-only", "--ignore-size", "--no-check-dest", "--ignore-checksum", "--compare-dest", "--copy-dest"}


def _move_unsafe(job: Job) -> List[str]:
    """Look at the FINAL command line of a Move (not at how the flags were typed): the checksum verification must be
    on, and nothing that skips or weakens it may be present, whichever way it got there (flags, extra, a flag value)."""
    try:
        args = build_args(job, False, "STAMP")
    except ValueError:
        return []
    bad = set()
    for t in args[3:]:
        if not t.startswith("-"):
            continue
        name = t.split("=", 1)[0]
        if name in MOVE_UNSAFE:
            bad.add(name)
        elif re.match(r"^-[A-Za-z]+$", name) and "u" in name[1:]:
            bad.add("--update")
    if "--checksum" not in args or any(t.split("=", 1)[0] == "--checksum" and "=" in t for t in args):
        bad.add("--checksum (off)")
    return sorted(bad)


def _is_empty_dir(path: str) -> bool:
    try:
        with os.scandir(path) as it:
            return next(it, None) is None
    except OSError:
        return False


def validate_job(job: Job, rclone: Optional[str]) -> List[str]:
    errors: List[str] = []
    if not rclone:
        errors.append("rclone was not found. Install it or set its path in Settings.")
    if job.mode not in MODES:
        errors.append("Choose Copy, Sync or Move.")
    try:
        build_args(job, False, "stamp")
    except ValueError as exc:
        errors.append(str(exc))
    if job.mode == "move":
        unsafe = _move_unsafe(job)
        if unsafe:
            errors.append("%s can make Move delete a source file whose copy is not verified; remove it for Move jobs." % ", ".join(unsafe))
    if job.source and os.path.isabs(job.source) and is_drive_root(job.source):
        errors.append("Choose a folder inside the drive as the source, not the whole drive.")
    if job.mode in ("sync", "move") and job.source and os.path.isdir(job.source) and _is_empty_dir(job.source):
        errors.append("The source folder is empty. %s would treat everything at the destination as removed. "
                      "If a drive is disconnected, reconnect it; otherwise use Copy." % job.mode.capitalize())
    if not is_local(job) and re.search(r"[:,/\\]", job.remote or ""):
        errors.append("Pick the remote from the list (names with ':' or ',' are not accepted).")
    if not job.source:
        errors.append("Choose the local folder.")
    elif not os.path.isdir(job.source):
        errors.append("Local folder not found: " + job.source)
    if is_local(job):
        return errors + _validate_local(job)
    if not job.remote:
        errors.append("Choose a remote.")
    target = norm_remote_path(job.target)
    backup = norm_remote_path(job.backup_root)
    if not target:
        errors.append("Choose a target folder on the remote (not the remote root).")
    if needs_backup(job) and not backup:
        errors.append("%s needs a backup folder on the remote (replaced and removed files are kept there)." % job.mode.capitalize())
    if target and backup and paths_overlap(target, backup):
        errors.append("The target folder and the backup folder must be separate, non-nested folders.")
    if job.bw_mbps <= 0 and not job.no_bw_limit:
        errors.append("Line speed must be above zero (or tick 'No limit').")
    return errors


def _validate_local(job: Job) -> List[str]:
    """Checks for a job whose destination is another folder on this computer."""
    errs: List[str] = []
    target, backup = job.target.strip(), job.backup_root.strip()
    if not target:
        errs.append("Choose the destination folder.")
    elif not os.path.isabs(target):
        errs.append("The destination must be a full folder path, for example D:\\Backups\\Photos.")
    elif os.path.dirname(os.path.normpath(target)) == os.path.normpath(target):
        errs.append("Choose a folder inside the drive, not the whole drive.")
    if needs_backup(job) and not backup:
        errs.append("%s needs a backup folder (replaced and removed files are kept there)." % job.mode.capitalize())
    if backup and not os.path.isabs(backup):
        errs.append("The backup folder must be a full folder path.")
    t_ok = bool(target) and os.path.isabs(target)
    b_ok = bool(backup) and os.path.isabs(backup)
    if job.source and t_ok and local_overlap(job.source, target):
        errs.append("The source and the destination must be separate folders (neither may be inside the other).")
    if job.source and b_ok and local_overlap(job.source, backup):
        errs.append("The backup folder must not be inside, or contain, the source folder.")
    if t_ok and b_ok and local_overlap(target, backup):
        errs.append("The destination and the backup folder must be separate, non-nested folders.")
    return errs


def check_local_path(path: str) -> PathVerdict:
    """Local folders can be checked directly; there is no listing and no API call involved."""
    return PathVerdict(path=path, state="exists" if os.path.isdir(path) else "missing")


def verify_against_listing(job: Job, dirs: List[str], depth: int) -> Tuple[PathVerdict, Optional[PathVerdict], List[str]]:
    """Returns (target verdict, backup verdict or None, blocking problems)."""
    target = check_path(norm_remote_path(job.target), dirs, depth)
    backup = check_path(norm_remote_path(job.backup_root), dirs, depth) if uses_backup(job) else None
    problems: List[str] = []
    for label, verdict in (("target", target), ("backup", backup)):
        if verdict and verdict.duplicate:
            problems.append(
                "There are two folders with the same name on the remote along the %s path '%s'. "
                "Google Drive allows that but rclone cannot tell them apart; rename one in Drive first." % (label, verdict.path)
            )
    return target, backup, problems


# --------------------------------------------------------------------------------------------
# rclone
# --------------------------------------------------------------------------------------------
class RcloneError(Exception):
    pass


def find_rclone(custom: str = "") -> Optional[str]:
    if custom and os.path.isfile(custom):
        return custom
    return shutil.which("rclone")


def _popen_flags() -> Dict[str, Any]:
    """rclone runs in its own, hidden console on Windows (not CREATE_NO_WINDOW): a console is what lets it receive
    Ctrl+C, so a stop cleans up half-copied files. The app itself never shows or keeps a console."""
    if IS_WIN:
        si = subprocess.STARTUPINFO()  # type: ignore[attr-defined]
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # type: ignore[attr-defined]
        si.wShowWindow = 0
        return {"creationflags": subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP, "startupinfo": si}  # type: ignore[attr-defined]
    return {"start_new_session": True}


_WIN_CTRL_C = """
import ctypes, sys, time
k = ctypes.windll.kernel32
k.FreeConsole()
if k.AttachConsole(int(sys.argv[1])):
    k.SetConsoleCtrlHandler(None, True)
    k.GenerateConsoleCtrlEvent(1, int(sys.argv[1]))      # CTRL_BREAK to rclone's own process group (Go treats it as an interrupt)
    time.sleep(0.6)
    k.FreeConsole()
"""


def interrupt(proc: "subprocess.Popen") -> None:
    """Send rclone the equivalent of Ctrl+C. On Windows a small helper attaches to rclone's hidden console for a
    moment (this process may have no console of its own). Raises on failure so the caller can fall back."""
    if IS_WIN:
        subprocess.run([sys.executable, "-c", _WIN_CTRL_C, str(proc.pid)], creationflags=subprocess.CREATE_NO_WINDOW,  # type: ignore[attr-defined]
                       timeout=10, check=True)
    else:
        os.killpg(proc.pid, signal.SIGINT)


def run_capture(rclone: str, args: List[str], timeout: int = 120, stdin_text: Optional[str] = None) -> Tuple[int, str, str]:
    flags: Dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if IS_WIN else {}
    stdin: Dict[str, Any] = {"stdin": subprocess.DEVNULL} if stdin_text is None else {"input": stdin_text}
    try:
        proc = subprocess.run(
            [rclone] + args, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, **stdin, **flags,
        )
    except subprocess.TimeoutExpired:
        raise RcloneError("rclone did not answer within %d seconds" % timeout)
    except OSError as exc:
        raise RcloneError("could not start rclone: %s" % exc)
    return proc.returncode, proc.stdout, proc.stderr


def rclone_version(rclone: str) -> str:
    try:
        code, out, _ = run_capture(rclone, ["version"], timeout=20)
    except RcloneError:
        return ""
    return out.splitlines()[0].strip() if code == 0 and out else ""


def list_remotes(rclone: str) -> List[Tuple[str, str]]:
    code, out, err = run_capture(rclone, ["listremotes", "--long"], timeout=30)
    if code != 0:
        raise RcloneError(err.strip() or "rclone listremotes failed")
    remotes = []
    for line in out.splitlines():
        m = re.match(r"^(\S+?):\s*(\S*)\s*$", line)
        if m:
            remotes.append((m.group(1), m.group(2)))
    return remotes


_WRAPPING_TYPES = ("alias", "crypt", "compress", "chunker", "hasher", "cache")
_UPSTREAM_TAG = re.compile(r":(ro|nc|writeback)$")


def _spec_roots(rclone: str, config: Dict[str, Any], spec: str, depth: int) -> List[str]:
    spec = _UPSTREAM_TAG.sub("", spec.strip())
    m = re.match(r"^:local(?:,[^:]*)?:(.*)$", spec)
    if m:
        return [m.group(1)]
    if re.match(r"^[A-Za-z]:[\\/]", spec) or spec.startswith(("/", "\\")):
        return [spec]
    if ":" in spec and depth < 8:
        inner, sub = spec.split(":", 1)
        return [os.path.join(r, sub) if r else sub for r in _remote_roots(rclone, config, inner, depth + 1)]
    return []


def _remote_roots(rclone: str, config: Dict[str, Any], name: str, depth: int) -> List[str]:
    entry = config.get(name)
    if not isinstance(entry, dict):
        return []
    kind = entry.get("type", "")
    if kind == "local":
        return [""]
    if kind in _WRAPPING_TYPES:
        return _spec_roots(rclone, config, str(entry.get("remote", "")), depth)
    if kind in ("union", "combine"):
        roots: List[str] = []
        for tok in str(entry.get("upstreams", "")).split():
            roots += _spec_roots(rclone, config, tok.split("=", 1)[1] if kind == "combine" and "=" in tok else tok, depth)
        return roots
    return []


def remote_local_roots(rclone: str, name: str) -> List[str]:
    """When a remote is only a window onto folders of THIS computer (type local, or alias / crypt / union / combine /
    ... over them, or a ':local:' connection string), return those folders ('' for a plain local remote, whose paths
    are real paths). Raises RcloneError when the rclone configuration cannot be read (fail closed)."""
    code, out, err = run_capture(rclone, ["config", "dump"], timeout=30)
    if code != 0:
        raise RcloneError("could not read the rclone configuration to check the destination")
    try:
        config = json.loads(out)
    except ValueError:
        raise RcloneError("could not read the rclone configuration to check the destination")
    return _remote_roots(rclone, config, name, 0)


def resolved_places(rclone: Optional[str], job: Job) -> List[Tuple[str, str]]:
    """[(label, absolute local path)] for the destination / backup of a job whose remote is really a local folder."""
    if not rclone or is_local(job) or not job.remote:
        return []
    places: List[Tuple[str, str]] = []
    for base in remote_local_roots(rclone, job.remote):
        for label, rel in (("destination", job.target), ("backup folder", job.backup_root)):
            if not rel.strip():
                continue
            path = os.path.join(base, norm_remote_path(rel)) if base else norm_remote_path(rel).replace("/", os.sep)
            if os.path.isabs(path):
                places.append((label, path))
    return places


def remote_inside_local(rclone: Optional[str], job: Job) -> Optional[str]:
    """A message when the job's destination/backup, reached through a remote that is really a local folder, overlaps
    the source (or each other); None when fine. Also None when the remote is a genuine cloud remote."""
    try:
        places = resolved_places(rclone, job)
    except RcloneError as exc:
        return "%s. Fix your rclone configuration and try again." % exc
    for label, path in places:
        if local_overlap(job.source, path):
            return ("The %s is, through the remote '%s', a folder inside (or around) your source folder. "
                    "Choose a separate place." % (label, job.remote))
    dests = [p for lab, p in places if lab == "destination"]
    backs = [p for lab, p in places if lab == "backup folder"]
    if any(local_overlap(d, b) for d in dests for b in backs):
        return "Through the remote '%s' the destination and the backup folder overlap." % job.remote
    return None


def footprint(job: Job, rclone: Optional[str] = None) -> List[Tuple[str, str, bool]]:
    """(place kind, place, writes) for everything a job touches. Remote places are 'remote:path'."""
    out: List[Tuple[str, str, bool]] = []
    if is_local(job):
        for p in (job.target, job.backup_root):
            if p.strip():
                out.append(("local", _real(p), True))
    else:
        for p in (job.target, job.backup_root):
            if p.strip():
                out.append(("remote", job.remote + ":" + norm_remote_path(p), True))
        try:
            for _label, path in resolved_places(rclone, job):
                out.append(("local", _real(path), True))
        except RcloneError:
            pass
    if job.source.strip():
        out.append(("local", _real(job.source), job.mode == "move"))
    return out


def same_place(a: Tuple[str, str, bool], b: Tuple[str, str, bool]) -> bool:
    if a[0] != b[0]:
        return False
    if a[0] == "local":
        return local_overlap(a[1], b[1])
    ra, pa = a[1].split(":", 1)
    rb, pb = b[1].split(":", 1)
    return ra == rb and (not pa or not pb or paths_overlap(pa, pb))


_REMOTE_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.+-]*$")


def _obscure(rclone: str, secret: str) -> str:
    """rclone's reversible obscuring of a password. The secret goes in on stdin, never on a command line."""
    code, out, _ = run_capture(rclone, ["obscure", "-"], timeout=20, stdin_text=secret)
    if code != 0 or not out.strip():
        raise RcloneError("rclone could not prepare the password")
    return out.strip()


def create_crypt_remote(rclone: str, name: str, base: str, password: str, salt: str = "",
                        filename_encryption: str = "standard", dir_encryption: bool = True) -> None:
    """Create a crypt remote `name:` that encrypts into `base` (a remote or remote:folder).
    The passwords are obscured through stdin first; only the obscured text reaches rclone's command line
    (briefly visible to other users of this computer, which is how `rclone config create` works).
    They are never written to jobs.json, logs, previews or exported scripts."""
    if not _REMOTE_NAME.match(name or ""):
        raise RcloneError("Use letters, digits, '.', '_', '+' or '-' for the new remote's name.")
    if not base or ":" not in base:
        raise RcloneError("Choose the remote (or remote:folder) the encrypted data will live in.")
    if not password:
        raise RcloneError("Enter a password.")
    if filename_encryption not in ("standard", "obfuscate", "off"):
        raise RcloneError("Unknown file name encryption.")
    if name in [n for n, _ in list_remotes(rclone)]:
        raise RcloneError("A remote called '%s' already exists." % name)
    args = ["config", "create", name, "crypt", "remote", base, "password", _obscure(rclone, password),
            "filename_encryption", filename_encryption, "directory_name_encryption", "true" if dir_encryption else "false",
            "--no-obscure", "--non-interactive"]
    if salt:
        args[args.index("filename_encryption"):args.index("filename_encryption")] = ["password2", _obscure(rclone, salt)]
    code, _out, err = run_capture(rclone, args, timeout=60)
    if code != 0:
        raise RcloneError(("could not create the remote: " + " ".join(err.strip().splitlines()[-2:])) if err.strip() else "could not create the remote")


def list_dirs(rclone: str, remote: str, depth: int) -> List[str]:
    """One recursive, directories-only listing. At depth 1 this is a single list call on the remote."""
    code, out, err = run_capture(
        rclone, ["lsf", remote + ":", "--dirs-only", "-R", "--max-depth", str(depth)], timeout=300
    )
    if code != 0:
        tail = " ".join(err.strip().splitlines()[-2:]) if err.strip() else "exit code %d" % code
        raise RcloneError("could not list %s: %s" % (remote + ":", tail))
    return [line.rstrip("/").rstrip("\r") for line in out.splitlines() if line.strip()]


# --------------------------------------------------------------------------------------------
# command line
# --------------------------------------------------------------------------------------------
def tuning(job: Job) -> Dict[str, Any]:
    if job.disk == "ssd":
        t: Dict[str, Any] = {"checkers": 8, "transfers": 4, "buffer": "16M", "check_first": False}
    else:
        # few parallel readers, and finish all hash checks before uploads so the disk is not seeking between them
        t = {"checkers": 2, "transfers": 2, "buffer": "32M", "check_first": True}
    if job.checkers > 0:
        t["checkers"] = job.checkers
    if job.transfers > 0:
        t["transfers"] = job.transfers
    if job.no_bw_limit:
        t["bwlimit"] = ""
        fast_line = True
    else:
        mib = round(job.bw_mbps * 1e6 / 8 * (job.bw_percent / 100.0) / 1048576, 2)
        t["bwlimit"] = "%sM" % mib
        fast_line = job.bw_mbps > 100
    if job.api_low:
        t["chunk"] = "128M" if fast_line else "64M"
    else:
        t["chunk"] = "64M" if fast_line else "32M"
    return t


def build_args(job: Job, real: bool, stamp: str, *, for_script: bool = False, log_file: str = "") -> List[str]:
    """Arguments after the rclone executable. for_script=True gives human output instead of JSON."""
    t = tuning(job)
    local = is_local(job)
    args = [job.mode, job.source, dest_spec(job)]
    m: Dict[str, Any] = {}      # flags derived from the job; the job's own tweaks are merged over them below
    if uses_backup(job):
        m["--backup-dir"] = backup_spec(job, stamp)
    if t["check_first"]:
        m["--check-first"] = None
    m.update({"--checkers": str(t["checkers"]), "--transfers": str(t["transfers"]), "--buffer-size": t["buffer"]})
    if not local:
        m["--drive-chunk-size"] = t["chunk"]
        m["--fast-list"] = None
    m["--retries"] = "3"
    if job.mode == "move":
        m["--checksum"] = None             # never delete a source file just because size and time look equal
        m["--disable"] = "DirMove"         # otherwise a missing destination makes rclone rename the whole source folder away
    if job.api_low and not local:
        # fewer Drive calls: a steady request rate so rate limiting does not force wasted retries, and fewer
        # low-level retries (bigger upload chunks and --fast-list are set above)
        m.update({"--tpslimit": "8", "--tpslimit-burst": "1", "--low-level-retries": "5"})
    else:
        m["--low-level-retries"] = "10"
    if job.no_dir_modtime and not local:
        # independent of the option above: by default rclone sets a remote folder's date to the local folder's,
        # one metadata call per differing folder. File checking and hashing are not affected either way.
        # (A local destination has no API calls to save, so its folder dates are always kept.)
        m["--no-update-dir-modtime"] = None
    if job.mode == "copy" and job.skip_existing:
        m["--ignore-existing"] = None
    if t["bwlimit"] and not local:    # the line-speed limit is about the internet, not a copy between local folders
        m["--bwlimit"] = t["bwlimit"]
    args += flagmod.merge(m, job.flags, job.extra)
    if for_script:
        args += ["-v", "-P"]
        if log_file:
            args += ["--log-file", log_file]
    else:
        args += ["-v", "--use-json-log", "--stats", "1s"]
    if not real:
        args.append("--dry-run")
    return args


def job_signature(job: Job) -> str:
    """A fingerprint of everything that decides what a run would do (not the run's time stamp). A real MOVE and a
    scheduled real run are only allowed while the job still matches the dry run / typed confirmation they were given for."""
    import hashlib
    try:
        blob = "\0".join(build_args(job, True, "STAMP"))
    except ValueError:
        blob = "invalid"
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


DRY_RUN_VALID_SECONDS = 24 * 3600


def move_gate(job: Job) -> Optional[str]:
    """Why a REAL Move may not start yet (None when it may). Shared by the window and the headless mode."""
    if job.mode != "move":
        return None
    fresh = time.time() - float(job.dry_ts or 0) < DRY_RUN_VALID_SECONDS
    if job.dry_sig and job.dry_sig == job_signature(job) and fresh:
        return None
    return ("A real Move removes the source files. Run a dry run of this exact job first "
            "(it stays valid for 24 hours, for one real run, and until you change the job).")


def command_text(rclone: str, args: List[str]) -> str:
    parts = [rclone] + args
    return subprocess.list2cmdline(parts) if IS_WIN else " ".join(shlex.quote(p) for p in parts)


_STAMP = "__RSG_STAMP__"


def export_script(job: Job, rclone: str = "rclone") -> Tuple[str, str]:
    """A standalone script that runs this job with the same arguments, without this app.
    Returns (file name, text). Dry run by default; pass -Execute (PowerShell) or --execute (sh) to run for real."""
    args = build_args(job, True, _STAMP, for_script=True)
    args = [a for a in args if a != "--dry-run"]
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", job.name).strip("_") or "job"
    if IS_WIN:
        def q(a: str) -> str:
            lit = "'" + a.replace("'", "''") + "'"
            return "('" + a.split(_STAMP)[0].replace("'", "''") + "' + $stamp + '" + a.split(_STAMP)[1].replace("'", "''") + "')" if _STAMP in a else lit
        body = [
            "# Generated by rSimpLone. Dry run unless -Execute is given.",
            "param([switch]$Execute)",
            "$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'",
            "$a = @(",
            ",\n".join("    " + q(a) for a in args),
            ")",
            "if (-not $Execute) { $a += '--dry-run' }",
            "& %s @a" % ("'" + rclone.replace("'", "''") + "'"),
            "exit $LASTEXITCODE",
        ]
        return "Run-%s.ps1" % name, "\r\n".join(body) + "\r\n"

    def qs(a: str) -> str:
        if _STAMP in a:
            pre, post = a.split(_STAMP)
            return shlex.quote(pre) + '"$STAMP"' + shlex.quote(post)
        return shlex.quote(a)
    body = [
        "#!/bin/sh",
        "# Generated by rSimpLone. Dry run unless --execute is given.",
        "STAMP=$(date +%Y%m%d-%H%M%S)",
        "EXTRA=--dry-run",
        '[ "$1" = "--execute" ] && EXTRA=',
        "exec %s \\" % shlex.quote(rclone),
        " \\\n".join("    " + qs(a) for a in args) + ' $EXTRA',
    ]
    return "run-%s.sh" % name, "\n".join(body) + "\n"


# --------------------------------------------------------------------------------------------
# reading rclone's JSON log
# --------------------------------------------------------------------------------------------
def classify(msg: str, level: str) -> Optional[str]:
    """Map an rclone log message to an activity kind, or None when it is only noise."""
    low = msg.lower()
    if level in ("error", "critical", "fatal"):
        return "error"
    if "directory modification time" in low:
        return None
    if low.startswith("updated modification time") or low.startswith("skipped update modification time"):
        return "modtime"
    if low.startswith("moved into backup dir") or low.startswith("skipped move into backup dir"):
        return "backup"
    if low.startswith("skipped move as") or low.startswith("moved (server-side)"):
        return "replace"
    if low.startswith("copied") or low.startswith("skipped copy as"):
        return "upload"
    if low.startswith("deleted") or low.startswith("skipped delete as"):
        return "delete"
    return None


@dataclass
class RunResult:
    code: Optional[int]
    real: bool
    stopped: bool
    elapsed: float
    counts: Dict[str, int]
    errors: List[str]
    log_path: str
    meaning: str
    summary: str


def _summary(real: bool, counts: Dict[str, int], errors: List[str], mode: str) -> str:
    up, mt = counts.get("upload", 0), counts.get("modtime", 0)
    moved = counts.get("backup", 0)
    dele = counts.get("delete", 0)
    if mode == "move":      # the deleted files are the SOURCE copies of what was just transferred
        parts = ["%d %s" % (up, "moved" if real else "would move")]
        if errors:
            parts.append("%d errors" % len(errors))
        return ", ".join(parts)
    verb = ("uploaded", "timestamps fixed", "moved to backup", "deleted") if real else (
        "would upload", "would fix timestamps on", "would move to backup", "would delete")
    parts = ["%d %s" % (up, verb[0])]
    if mt:
        parts.append("%d %s" % (mt, verb[1]) if real else "%s %d" % (verb[1], mt))
    if mode == "sync" or moved:
        parts.append("%d %s" % (moved, verb[2]))
    if dele:
        parts.append("%d %s" % (dele, verb[3]))
    if errors:
        parts.append("%d errors" % len(errors))
    return ", ".join(parts)


class RunBusy(Exception):
    pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if IS_WIN:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return bool(ok) and code.value == 259
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_lock(path: Path) -> Tuple[int, List[Tuple[str, str, bool]], str]:
    try:
        text = path.read_text().strip()
    except OSError:
        return 0, [], ""
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return int(data.get("pid", 0)), [tuple(x) for x in data.get("foot", [])], str(data.get("name", ""))  # type: ignore[misc]
    except ValueError:
        pass
    try:
        return int(text or "0"), [], ""
    except ValueError:
        return 0, [], ""


def _acquire_lock(job: Job, rclone: Optional[str] = None) -> Path:
    folder = config_dir() / "locks"
    path = folder / ("%s.lock" % job.id)
    folder.mkdir(parents=True, exist_ok=True)
    mine = footprint(job, rclone)
    for other_path in folder.glob("*.lock"):       # another process may be running a job that touches the same places
        if other_path == path or other_path.name == "store.lock":
            continue
        pid, foot, name = _read_lock(other_path)
        if pid and pid != os.getpid() and _pid_alive(pid):
            for a in mine:
                for b in foot:
                    if (a[2] or b[2]) and same_place(a, b):
                        raise RunBusy("'%s' is running in another rSimpLone process and works on the same place." % (name or "another job"))
    for _ in range(2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            other, _foot, _name = _read_lock(path)
            try:
                fresh = time.time() - path.stat().st_mtime < 5
            except OSError:
                fresh = False
            if other == 0 and fresh:
                raise RunBusy("This job is starting in another process.")
            if _pid_alive(other):
                raise RunBusy("This job is already running (process %d)." % other)
            try:
                path.unlink()
            except OSError:
                pass
            continue
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps({"pid": os.getpid(), "name": job.name, "foot": mine}))
        return path
    raise RunBusy("Could not take the run lock for this job.")


@contextlib.contextmanager
def _store_lock(timeout: float = 8.0):
    """A short-lived lock around read-modify-write of jobs.json, so the window and the headless mode cannot interleave."""
    path = config_dir() / "locks" / "store.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    end = time.time() + timeout
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > 15:       # a crashed holder
                    path.unlink()
                    continue
            except OSError:
                pass
            if time.time() > end:
                raise RunBusy("jobs.json is busy; try again.")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            path.unlink()
        except OSError:
            pass


def consume_move_unlock(job: Job) -> Optional[str]:
    """Use up the dry-run unlock of a Move, atomically across processes (what is on disk is the truth, not this
    process's memory). Returns a refusal message, or None when the real Move may start NOW. Call it right before starting."""
    refusal = ("A real Move removes the source files. Run a dry run of this exact job first "
               "(it stays valid for 24 hours, for one real run, and until you change the job).")
    sig = job_signature(job)
    with _store_lock():
        store = load_store()
        disk = next((j for j in store.jobs if j.id == job.id), None)
        if disk is None or not disk.dry_sig or disk.dry_sig != sig or time.time() - float(disk.dry_ts or 0) >= DRY_RUN_VALID_SECONDS:
            job.dry_sig, job.dry_ts = "", 0.0
            return refusal
        disk.dry_sig, disk.dry_ts = "", 0.0
        save_store(store)
    job.dry_sig, job.dry_ts = "", 0.0
    return None


_stamp_lock = threading.Lock()
_last_stamp = [""]


def _unique_stamp() -> str:
    """YYYYMMDD-HHMMSS, never the same twice in this process: two runs must not share (and overwrite) a backup folder."""
    with _stamp_lock:
        while True:
            stamp = time.strftime("%Y%m%d-%H%M%S")
            if stamp != _last_stamp[0]:
                _last_stamp[0] = stamp
                return stamp
            time.sleep(0.2)


class SyncRun:
    """Runs rclone for a job in the background and reports through a queue of (kind, payload) tuples:
    started, stats, activity, log, done."""

    def __init__(self, rclone: str, job: Job, real: bool, events: "queue.Queue[Tuple[str, Any]]") -> None:
        self.rclone, self.job, self.real, self.events = rclone, job, real, events
        self.proc: Optional[subprocess.Popen] = None
        self.stopping = False
        self.log_path = ""
        self.backup_dir = ""
        self._lock: Optional[Path] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        job = self.job
        stamp = _unique_stamp()      # seconds: two runs in one minute must not share (and overwrite) a backup folder
        args = build_args(job, self.real, stamp)
        self._lock = _acquire_lock(job, self.rclone)
        try:
            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", job.name).strip("_") or job.id
            folder = log_dir() / safe
            folder.mkdir(parents=True, exist_ok=True)
            self.log_path = str(folder / ("%s_%s.log" % (time.strftime("%Y%m%d-%H%M%S"), "run" if self.real else "dryrun")))
            self.backup_dir = backup_spec(job, stamp) if uses_backup(job) else ""
            self._log = open(self.log_path, "w", encoding="utf-8")
            self._log.write("# %s\n# mode: %s (%s)\n# command: %s\n\n" % (
                time.strftime("%Y-%m-%d %H:%M:%S"), job.mode, "REAL" if self.real else "dry run",
                command_text(self.rclone, args)))
            self.proc = subprocess.Popen(
                [self.rclone] + args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", **_popen_flags(),
            )
        except Exception:
            self._release()
            raise
        self.events.put(("started", {"log": self.log_path, "backup_dir": self.backup_dir, "args": args}))
        self._thread = threading.Thread(target=self._reader, name="rclone-reader", daemon=True)
        self._thread.start()

    def _release(self) -> None:
        if self._lock:
            try:
                self._lock.unlink()
            except OSError:
                pass
            self._lock = None

    def _w(self, text: str) -> None:
        try:
            self._log.write(text)
        except (OSError, ValueError):       # disk full or closed log: the run itself must still finish and be reported
            pass

    def _reader(self) -> None:
        job = self.job
        started = time.time()
        counts: Dict[str, int] = {}
        seen: Dict[str, set] = {}
        errors: List[str] = []
        last_stats: Dict[str, Any] = {}
        assert self.proc is not None and self.proc.stderr is not None
        for line in self.proc.stderr:
            try:
                line = line.rstrip("\r\n")
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    self._w(line + "\n")
                    self.events.put(("log", {"level": "info", "text": line}))
                    continue
                if not isinstance(rec, dict):
                    continue
                stats = rec.get("stats")
                if isinstance(stats, dict):
                    last_stats = stats
                    self.events.put(("stats", stats))
                    continue
                msg, level, obj = str(rec.get("msg", "")), str(rec.get("level", "info")), str(rec.get("object", ""))
                stamp = str(rec.get("time", ""))[:19].replace("T", " ").replace("-", "/")
                text = "%s %-5s : %s%s" % (stamp, level.upper(), (obj + ": ") if obj else "", msg)   # rclone's own layout
                self._w(text + "\n")
                self.events.put(("log", {"level": level, "text": text}))
                kind = classify(msg, level)
                if job.mode == "move" and kind in ("replace", "backup"):
                    kind = "upload"         # in a Move the same 'Moved' line is the transfer itself; do not call it a backup
                if kind:
                    # a replaced file logs one 'moved' line, a deleted file logs two: count each path once
                    bucket_name = "backup" if kind in ("backup", "replace") else kind
                    bucket = seen.setdefault(bucket_name, set())
                    key = obj or msg
                    if kind == "error":
                        errors.append(("%s: %s" % (obj, msg)) if obj else msg)
                        counts["error"] = counts.get("error", 0) + 1
                    elif key not in bucket:
                        bucket.add(key)
                        counts[bucket_name] = counts.get(bucket_name, 0) + 1
                    self.events.put(("activity", {"kind": kind, "path": obj, "detail": msg}))
            except Exception:       # one odd line must not end the reader (that would hang the run)
                continue
        code = self.proc.wait()
        self.proc.stderr.close()
        elapsed = time.time() - started
        # rclone ends with a final stats block; keep the last numbers in the log so the file is self-contained
        if last_stats:
            self._w("\n# final stats: %s\n" % json.dumps({k: last_stats.get(k) for k in (
                "bytes", "totalBytes", "transfers", "totalTransfers", "checks", "totalChecks", "errors", "elapsedTime")}))
        self._w("# exit code %s (%s)\n" % (code, exit_meaning(code)))
        try:
            self._log.close()
        except OSError:
            pass
        self._release()
        meaning = "stopped by you; files that were already finished are kept" if self.stopping else exit_meaning(code)
        result = RunResult(
            code=code, real=self.real, stopped=self.stopping, elapsed=elapsed, counts=counts, errors=errors[:50],
            log_path=self.log_path, meaning=meaning, summary=_summary(self.real, counts, errors, job.mode),
        )
        self.events.put(("done", {"result": result, "stats": last_stats}))

    def stop(self) -> None:
        """Ask rclone to stop. It is killed if it has not exited after a few seconds."""
        proc = self.proc
        if proc is None or proc.poll() is not None:
            return
        self.stopping = True

        def _go() -> None:
            try:
                interrupt(proc)
            except Exception:
                proc.terminate()

        threading.Thread(target=_go, name="rclone-stop", daemon=True).start()
        timer = threading.Timer(10.0, self.kill)
        timer.daemon = True
        timer.start()

    def kill(self) -> None:
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass


# --------------------------------------------------------------------------------------------
# helpers shared by the GUI and the headless mode
# --------------------------------------------------------------------------------------------
def human_bytes(n: float) -> str:
    n = float(n or 0)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "%d B" % n


def human_eta(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)) or seconds < 0:
        return "-"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return "%dh %02dm" % (h, m) if h else ("%dm %02ds" % (m, s) if m else "%ds" % s)


def detect_disk_kind(path: str) -> Optional[str]:
    """'ssd' or 'hdd' for the disk holding this folder, or None when it cannot be told reliably. Never raises.

    USB-attached drives return None on Windows: many USB enclosures report the wrong thing (a spinning laptop drive
    in an enclosure can claim to be an SSD), and a wrong guess would pick the wrong tuning."""
    try:
        if not path or not path.strip():
            return None
        path = os.path.abspath(path)
        if IS_WIN:
            return _detect_windows(path)
        if sys.platform == "darwin":
            return _detect_macos(path)
        return _detect_linux(path)
    except Exception:
        return None


def _detect_windows(path: str) -> Optional[str]:
    import ctypes
    from ctypes import wintypes

    drive = os.path.splitdrive(path)[0]
    if len(drive) != 2 or drive[1] != ":":       # network (UNC) paths: nothing to ask
        return None
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID,
                                    wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k32.CreateFileW("\\\\.\\" + drive, 0, 3, None, 3, 0, None)     # access 0: ask questions, read nothing
    if handle in (None, wintypes.HANDLE(-1).value):
        return None

    class Query(ctypes.Structure):
        _fields_ = [("PropertyId", wintypes.DWORD), ("QueryType", wintypes.DWORD), ("Extra", ctypes.c_ubyte * 1)]

    def ask(property_id: int, size: int) -> Optional[bytes]:
        query = Query(property_id, 0, (ctypes.c_ubyte * 1)(0))
        out = (ctypes.c_ubyte * size)()
        got = wintypes.DWORD(0)
        ok = k32.DeviceIoControl(handle, 0x002D1400, ctypes.byref(query), ctypes.sizeof(query), out, size, ctypes.byref(got), None)
        return bytes(out[:got.value]) if ok else None

    try:
        adapter = ask(1, 64)                       # StorageAdapterProperty: the bus type is the byte at offset 24
        if adapter is not None and len(adapter) > 24 and adapter[24] in (7, 4):    # USB, IEEE 1394
            return None
        penalty = ask(7, 12)                       # StorageDeviceSeekPropertyProperty: IncursSeekPenalty at offset 8
        if penalty is None or len(penalty) < 9:
            return None
        return "hdd" if penalty[8] else "ssd"
    finally:
        k32.CloseHandle(handle)


def _detect_linux(path: str) -> Optional[str]:
    st = os.stat(path)
    sysdir = os.path.realpath("/sys/dev/block/%d:%d" % (os.major(st.st_dev), os.minor(st.st_dev)))
    while sysdir not in ("/", "/sys"):
        flag = os.path.join(sysdir, "queue", "rotational")      # a partition has no queue; its parent disk does
        if os.path.exists(flag):
            with open(flag) as fh:
                return "hdd" if fh.read().strip() == "1" else "ssd"
        sysdir = os.path.dirname(sysdir)
    return None


def _detect_macos(path: str) -> Optional[str]:
    mount = path
    while not os.path.ismount(mount) and os.path.dirname(mount) != mount:
        mount = os.path.dirname(mount)
    out = subprocess.run(["diskutil", "info", mount], capture_output=True, text=True, timeout=10).stdout
    for line in out.splitlines():
        if line.strip().startswith("Solid State:"):
            return "ssd" if "yes" in line.lower() else "hdd"
    return None


def open_path(path: str) -> None:
    """Open a file or folder with the system's default handler, without leaving a console behind."""
    if IS_WIN:
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cli_main(argv: List[str]) -> int:
    """Headless mode:  --list | --run NAME [--execute --yes]. Dry run unless both --execute and --yes are given."""
    import argparse

    ap = argparse.ArgumentParser(prog="rsg", description="rclone sync/copy manager (headless mode)")
    ap.add_argument("--list", action="store_true", help="list saved jobs")
    ap.add_argument("--run", metavar="JOB", help="run a saved job by name or id")
    ap.add_argument("--execute", action="store_true", help="really run (default is a dry run)")
    ap.add_argument("--yes", action="store_true", help="confirm --execute; there is no prompt in headless mode")
    ns = ap.parse_args(argv)
    out = sys.stdout.write if sys.stdout else (lambda s: None)
    store = load_store()
    if ns.list or not ns.run:
        for job in store.jobs:
            out("%s\t%s\t%s -> %s\n" % (job.id, job.name, job.source, dest_spec(job)))
        return 0
    matches = [j for j in store.jobs if j.id == ns.run or j.name == ns.run]
    if len(matches) != 1:
        out("No unique job called '%s'.\n" % ns.run)
        return 2
    job = matches[0]
    real = ns.execute
    if real and not ns.yes:
        out("Refusing to execute without --yes. Running a dry run instead.\n")
        real = False
    rclone = find_rclone(str(store.settings.get("rclone", "")))
    problems = validate_job(job, rclone)
    if problems:
        out("\n".join(problems) + "\n")
        return 2
    if real and move_gate(job):
        out(str(move_gate(job)) + "\n")
        return 2
    why = remote_inside_local(rclone, job)
    if why:
        out(why + "\n")
        return 2
    if real and job.mode == "move":
        refusal = consume_move_unlock(job)
        if refusal:
            out(refusal + "\n")
            return 2
    events: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
    run = SyncRun(rclone or "rclone", job, real, events)
    try:
        run.start()
    except RunBusy as exc:
        out(str(exc) + "\n")
        return 3
    code: Optional[int] = None
    while True:
        kind, payload = events.get()
        if kind == "log":
            out(payload["text"] + "\n")
        elif kind == "done":
            res: RunResult = payload["result"]
            out("\n%s\nexit code %s - %s\nlog: %s\n" % (res.summary, res.code, res.meaning, res.log_path))
            code = res.code
            with _store_lock():
                fresh = load_store()        # re-read: the window may have saved changes while this ran
                target = next((j for j in fresh.jobs if j.id == job.id), None)
                if target is not None:
                    target.last_run, target.last_mode, target.last_code, target.last_summary = (
                        time.strftime("%Y-%m-%d %H:%M"), "run" if real else "dry run", res.code, res.summary)
                    if not real and not res.stopped and res.code in (0, 9):
                        # the signature of the job AS IT WAS DRY-RUN: if it was edited meanwhile the gate stays closed
                        target.dry_sig, target.dry_ts = job_signature(job), time.time()
                    save_store(fresh)
            break
    return code if code is not None else 1
