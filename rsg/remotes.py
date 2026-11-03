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
"""Adding, changing, testing and deleting rclone remotes from the window, using rclone's own setup machinery
(`rclone config create/update --non-interactive`, which asks follow-up questions as JSON). Every call goes through
core.rclone_env(), so it edits the same rclone.conf that jobs and mounts read. Passwords are obscured through stdin first
and passed as key=value; nothing secret is ever returned to the page, logged, or left in an error message."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import core

_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.+@ -]{0,63}")
_SECRETISH = re.compile(r"(pass|secret|token|key|credential|sas_url|session)", re.I)
_providers_cache: Dict[str, List[Dict[str, Any]]] = {}
TOP = ("drive", "google photos")      # shown first; everything else follows in rclone's order
_current: List[Optional["subprocess.Popen"]] = [None]
_backed_up = [False]
_AUTH_URL = re.compile(r"https?://(?:127\.0\.0\.1|localhost):\d+/auth\?state=[A-Za-z0-9_-]+")
_auth_url = [""]                   # the sign-in link rclone prints while it waits for the browser
IMPORTED_MARK = "@imported-from-file@"   # stands for a client secret that is held here, never sent to the page
_imported: Dict[str, str] = {}
_lock = threading.Lock()


class RemoteError(ValueError):
    """A remote could not be created, changed, tested or deleted; the message is safe to show."""


def _scrub(text: str, secrets: List[str]) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def _clean_value(v: Any) -> str:
    s = str(v)
    if any(ord(c) < 32 for c in s):
        raise RemoteError("A value contains a control character.")
    return s


def providers(rclone: str) -> List[Dict[str, Any]]:
    """Every backend rclone knows with its options (name, help, required, advanced, password, examples), trimmed for the page."""
    key = core.rclone_version(rclone)
    if key in _providers_cache:
        return _providers_cache[key]
    code, out, err = core.run_capture(rclone, ["config", "providers"], timeout=30)
    if code != 0:
        raise RemoteError("rclone could not list its backends.")
    result = []
    for p in json.loads(out):
        if p.get("Hide"):
            continue
        opts = []
        for o in p.get("Options") or []:
            if o.get("Hide"):
                continue
            opts.append({
                "name": o["Name"], "help": o.get("Help", ""), "required": bool(o.get("Required")), "advanced": bool(o.get("Advanced")),
                "password": bool(o.get("IsPassword")), "type": o.get("Type", "string"), "default": str(o.get("DefaultStr", "")),
                "provider": o.get("Provider", ""), "examples": [{"value": e["Value"], "help": e.get("Help", "")} for e in (o.get("Examples") or [])][:60],
            })
        result.append({"name": p["Name"], "description": p.get("Description", p["Name"]), "options": opts})
    result.sort(key=lambda p: p["description"].lower())        # rclone's own order in its "add a remote" list
    result.sort(key=lambda p: TOP.index(p["name"]) if p["name"] in TOP else len(TOP))       # then Drive and Photos first (stable)
    _providers_cache[key] = result
    return result


def active_config_file(rclone: str) -> str:
    if core.config_path():
        return core.config_path()
    code, out, _ = core.run_capture(rclone, ["config", "file"], timeout=20)
    lines = [l.strip() for l in out.splitlines() if l.strip()]
    return lines[-1] if code == 0 and lines else ""


def backup_config(rclone: str) -> str:
    """Once per session, before the first change: copy the active rclone.conf beside itself (keeps the 5 newest)."""
    with _lock:
        if _backed_up[0]:
            return ""
        path = Path(active_config_file(rclone))
        _backed_up[0] = True
        if not path.is_file():
            return ""
        copy = path.with_name("%s.bak-%s" % (path.name, time.strftime("%Y%m%d-%H%M%S")))
        shutil.copy2(path, copy)
        for old in sorted(path.parent.glob(path.name + ".bak-*"))[:-5]:
            try:
                old.unlink()
            except OSError:
                pass
        return str(copy)


def _step(out: str, secrets: List[str]) -> Dict[str, Any]:
    try:
        d = json.loads(out)
    except ValueError:
        raise RemoteError("rclone gave an answer this app does not understand.")
    if d.get("Error"):
        raise RemoteError(_scrub(str(d["Error"]), secrets)[:300])
    opt = d.get("Option")
    question = None
    if opt:
        question = {"name": opt.get("Name", ""), "help": opt.get("Help", ""), "default": opt.get("Value") if opt.get("Value") is not None else opt.get("Default"),
                    "type": opt.get("Type", "string"), "password": bool(opt.get("IsPassword")), "required": bool(opt.get("Required")),
                    "examples": [{"value": e["Value"], "help": e.get("Help", "")} for e in (opt.get("Examples") or [])][:60]}
    return {"done": not d.get("State"), "state": d.get("State", ""), "question": question}


def _run(rclone: str, args: List[str], timeout: int, secrets: List[str]) -> str:
    core.guard_config_write()
    flags: Dict[str, Any] = {"creationflags": subprocess.CREATE_NO_WINDOW} if core.IS_WIN else {}
    try:
        proc = subprocess.Popen([rclone] + args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", env=core.rclone_env(), **flags)
    except OSError as exc:
        raise RemoteError("could not start rclone: %s" % exc)
    _current[0] = proc
    _auth_url[0] = ""
    out_buf: List[str] = []
    err_buf: List[str] = []

    def pump(stream: Any, buf: List[str], scan: bool) -> None:
        try:
            for line in stream:
                buf.append(line)
                if scan:
                    m = _AUTH_URL.search(line)
                    if m:
                        _auth_url[0] = m.group(0)
        except (OSError, ValueError):
            pass
    pumps = [threading.Thread(target=pump, args=(proc.stdout, out_buf, False), daemon=True),
             threading.Thread(target=pump, args=(proc.stderr, err_buf, True), daemon=True)]
    for t in pumps:
        t.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
        raise RemoteError("Timed out. If a browser sign-in page opened, finish it faster or try again.")
    finally:
        _current[0] = None
        for t in pumps:
            t.join(5)
        for stream in (proc.stdout, proc.stderr):
            try:
                stream.close()
            except OSError:
                pass
        _auth_url[0] = ""
    out, err = "".join(out_buf), "".join(err_buf)
    if proc.returncode != 0:
        if proc.returncode in (-9, -15, 1) and not out.strip() and "cancel" in (err or "").lower():
            raise RemoteError("Cancelled.")
        tail = _scrub(" ".join((err or "").strip().splitlines()[-2:]), secrets)[:300]
        raise RemoteError("rclone could not do that" + (": " + tail if tail else "."))
    return out


def auth_link() -> str:
    """The sign-in link rclone is waiting on right now, or "" (so it can be copied into another browser)."""
    return _auth_url[0]


def clear_imported() -> None:
    _imported.clear()


def _imported_secret() -> str:
    if "client_secret" not in _imported:
        raise RemoteError("The credentials file is no longer loaded. Import it again.")
    return _imported["client_secret"]


def parse_google_credentials(text: str) -> Dict[str, Any]:
    """Read the JSON file Google lets you download for an OAuth client. The secret stays here; the page only learns the
    client id, the project name and which fields the file covers."""
    if len(text) > 20000:
        raise RemoteError("That file is too large to be a Google credentials file.")
    try:
        data = json.loads(text)
    except ValueError:
        raise RemoteError("That is not a JSON file.")
    kind = "installed" if isinstance(data, dict) and isinstance(data.get("installed"), dict) else "web" if isinstance(data, dict) and isinstance(data.get("web"), dict) else ""
    if not kind:
        raise RemoteError("This is not a Google OAuth client file. In Google Cloud, create an OAuth client of type Desktop app and download its JSON.")
    block = data[kind]
    cid, sec = str(block.get("client_id", "")), str(block.get("client_secret", ""))
    if not re.fullmatch(r"[0-9A-Za-z._-]+\.apps\.googleusercontent\.com", cid) or not sec or any(ord(c) < 32 for c in sec):
        raise RemoteError("The file has no usable client id and client secret.")
    _imported.clear()
    _imported["client_secret"] = sec
    fields = [k for k in ("client_id", "client_secret", "project_id", "auth_uri", "token_uri", "redirect_uris") if block.get(k)]
    out: Dict[str, Any] = {"client_id": cid, "project_id": str(block.get("project_id", ""))[:100], "kind": kind, "fields": fields,
                           "covers": ["client_id", "client_secret"], "warning": ""}
    if kind == "web":
        out["warning"] = "This is a Web application client. rclone signs in through http://127.0.0.1:53682/, so that address must be listed as an authorized redirect URI, or create a Desktop app client instead."
    return out


def cancel() -> bool:
    clear_imported()
    proc = _current[0]
    if proc is not None and proc.poll() is None:
        proc.kill()
        return True
    return False


def _pairs(rclone: str, rtype: str, values: Dict[str, Any], schema: Optional[List[Dict[str, Any]]] = None):
    schema = schema if schema is not None else next((p["options"] for p in providers(rclone) if p["name"] == rtype), [])
    secret_names = {o["name"] for o in schema if o["password"]}
    pairs, secrets = [], []
    for k, v in values.items():
        if not re.fullmatch(r"[a-z0-9_]+", str(k)):
            raise RemoteError("Unknown setting name.")
        v = _clean_value(v)
        if v == "":
            continue
        if v == IMPORTED_MARK:
            v = _imported_secret()
            secrets.append(v)
        elif k in secret_names:
            secrets.append(v)
            v = core._obscure(rclone, v)
            secrets.append(v)
        pairs.append("%s=%s" % (k, v))
    return pairs, secrets


def start(rclone: str, name: str, rtype: str, values: Dict[str, Any]) -> Dict[str, Any]:
    name = (name or "").strip()
    if not _NAME.fullmatch(name):
        raise RemoteError("Use letters, numbers, spaces and . _ + @ - for the name (no colon, and do not start with a dash).")
    if name in [n for n, _ in core.list_remotes(rclone)]:
        raise RemoteError("A remote called '%s' already exists." % name)
    if rtype not in {p["name"] for p in providers(rclone)}:
        raise RemoteError("Unknown remote type.")
    core.guard_config_write()
    backup_config(rclone)
    pairs, secrets = _pairs(rclone, rtype, values)
    out = _run(rclone, ["config", "create", name, rtype] + pairs + ["--no-obscure", "--non-interactive"], 90, secrets)
    return _step(out, secrets)


def update(rclone: str, name: str, values: Dict[str, Any]) -> Dict[str, Any]:
    rtype = dict(core.list_remotes(rclone)).get(name)
    if not rtype:
        raise RemoteError("That remote no longer exists.")
    core.guard_config_write()
    backup_config(rclone)
    pairs, secrets = _pairs(rclone, rtype, values)
    out = _run(rclone, ["config", "update", name] + pairs + ["--no-obscure", "--non-interactive"], 90, secrets)
    return _step(out, secrets)


def cont(rclone: str, name: str, state: str, result: str) -> Dict[str, Any]:
    """Answer rclone's follow-up question. May block for minutes while the user signs in in the browser."""
    if name not in [n for n, _ in core.list_remotes(rclone)]:
        raise RemoteError("That remote does not exist.")
    secrets: List[str] = []
    result = _clean_value(result)
    if result == IMPORTED_MARK:
        result = _imported_secret()
        secrets.append(result)
    out = _run(rclone, ["config", "update", name, "--continue", "--state", _clean_value(state), "--result", result, "--non-interactive"], 600, secrets)
    return _step(out, secrets)


def describe(rclone: str, name: str) -> Dict[str, Any]:
    """Current settings of a remote WITHOUT anything secret (passwords, tokens, keys are never sent to the page)."""
    code, out, _ = core.run_capture(rclone, ["config", "dump"], timeout=30)
    if code != 0:
        raise RemoteError("rclone could not read its config.")
    conf = json.loads(out).get(name)
    if conf is None:
        raise RemoteError("That remote no longer exists.")
    schema = {o["name"]: o for p in providers(rclone) if p["name"] == conf.get("type") for o in p["options"]}
    safe = {k: str(v) for k, v in conf.items() if k != "type" and k in schema and not schema[k]["password"] and not _SECRETISH.search(k) and len(str(v)) < 300}
    return {"name": name, "type": conf.get("type", ""), "values": safe}


def delete(rclone: str, name: str) -> None:
    if name not in [n for n, _ in core.list_remotes(rclone)]:
        raise RemoteError("That remote no longer exists.")
    core.guard_config_write()
    backup_config(rclone)
    code, _, err = core.run_capture(rclone, ["config", "delete", name], timeout=30)
    if code != 0:
        raise RemoteError("rclone could not delete it.")


def test(rclone: str, name: str) -> str:
    """A cheap, time-limited look at the top of the remote. Returns a short plain message, never raw rclone output."""
    if name not in [n for n, _ in core.list_remotes(rclone)]:
        raise RemoteError("That remote does not exist.")
    try:
        code, _out, err = core.run_capture(rclone, ["lsd", name + ":", "--max-depth", "1", "--contimeout", "10s", "--timeout", "20s", "--retries", "1", "--low-level-retries", "1"], timeout=45)
    except core.RcloneError as exc:
        raise RemoteError(str(exc))
    if code == 0:
        return "Connected."
    low = (err or "").lower()
    if "token" in low or "oauth" in low or "401" in low or "403" in low:
        raise RemoteError("Sign-in has expired or was refused. Edit the remote and sign in again.")
    if "no such host" in low or "dial" in low or "timeout" in low:
        raise RemoteError("Could not reach the server. Check your internet connection and the address.")
    raise RemoteError("The connection test failed. Check the settings and try again.")


# ---- copy a remote (same login, different root folder) -----------------------------------------------------
COPY_FIELDS = ("root_folder_id", "team_drive")
_FOLDER_ID = re.compile(r"[A-Za-z0-9_-]{1,120}")


def copyable(rclone: str, rtype: str) -> bool:
    """Only backends that have a root folder ID setting (Google Drive and similar) can be copied this way."""
    return any(o["name"] == "root_folder_id" for p in providers(rclone) if p["name"] == rtype for o in p["options"])


def copy_remote(rclone: str, src: str, new_name: str, overrides: Dict[str, Any], copy_token: bool = True) -> None:
    """Duplicate a remote under a new name, keeping its sign-in, and change only its root folder (and shared drive).
    The section is copied inside the config file itself, so the sign-in token never appears on a command line."""
    new_name = (new_name or "").strip()
    if not _NAME.fullmatch(new_name):
        raise RemoteError("Use letters, numbers, spaces and . _ + @ - for the name (no colon, and do not start with a dash).")
    existing = dict(core.list_remotes(rclone))
    if src not in existing:
        raise RemoteError("That remote no longer exists.")
    if new_name in existing:
        raise RemoteError("A remote called '%s' already exists." % new_name)
    if not copyable(rclone, existing[src]):
        raise RemoteError("This kind of remote has no root folder setting to change.")
    changes: Dict[str, str] = {}
    for k, v in (overrides or {}).items():
        if k not in COPY_FIELDS:
            raise RemoteError("Only the root folder and shared drive can be changed in a copy.")
        v = _clean_value(v).strip()
        if v and not _FOLDER_ID.fullmatch(v):
            raise RemoteError("A folder ID has only letters, numbers, dashes and underscores. Copy it from the folder's web address.")
        changes[k] = v
    core.guard_config_write()
    path = Path(active_config_file(rclone))
    if not path.is_file():
        raise RemoteError("The rclone config file was not found.")
    raw = path.read_bytes().decode("utf-8")
    if raw.startswith("RCLONE_ENCRYPT_V0:"):
        raise RemoteError("The config file is password-protected, so it cannot be copied here.")
    backup_config(rclone)
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip() == "[%s]" % src), None)
    if start is None:
        raise RemoteError("Could not find that remote in the config file.")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    drop = list(changes) + ([] if copy_token else ["token"])       # without the token the copy needs its own sign-in
    body = [l for l in lines[start + 1:end] if l.strip() and not any(re.match(r"\s*%s\s*=" % k, l) for k in drop)]
    body += ["%s = %s" % (k, v) for k, v in changes.items() if v]
    text = raw.replace("\r\n", "\n").rstrip("\n") + "\n\n[%s]\n" % new_name + "\n".join(body) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(text.replace("\n", nl).encode("utf-8"))
    os.replace(tmp, path)
    if new_name not in dict(core.list_remotes(rclone)):
        raise RemoteError("The copy was written but rclone does not list it. The backup copy of the config is next to the file.")


# ---- copy a login (token) from one remote to others of the same Google account ----------------------------
GOOGLE_LOGIN = ("drive", "google photos")      # other providers rotate their tokens, so a shared one would break


def login_targets(rclone: str, src: str) -> List[str]:
    """Other remotes of the same Google type that could receive this remote's login."""
    existing = dict(core.list_remotes(rclone))
    t = existing.get(src)
    return [n for n, ty in existing.items() if n != src and ty == t and t in GOOGLE_LOGIN]


def copy_login(rclone: str, src: str, dsts: List[str]) -> List[str]:
    """Replace the sign-in token of each target with the source's (for when a token has expired and one remote still
    works). The Google account must be the same; the page says so. Done inside the config file: the token is never
    put on a command line and never returned to the page."""
    existing = dict(core.list_remotes(rclone))
    if src not in existing:
        raise RemoteError("That remote no longer exists.")
    if existing[src] not in GOOGLE_LOGIN:
        raise RemoteError("Copying a login is only supported between Google Drive / Google Photos remotes.")
    dsts = [d for d in dict.fromkeys(dsts or []) if d != src]
    if not dsts:
        raise RemoteError("Choose at least one remote to copy the login to.")
    for d in dsts:
        if existing.get(d) != existing[src]:
            raise RemoteError("'%s' is not a %s remote like '%s'." % (d, existing[src], src))
    core.guard_config_write()
    path = Path(active_config_file(rclone))
    if not path.is_file():
        raise RemoteError("The rclone config file was not found.")
    raw = path.read_bytes().decode("utf-8")
    if raw.startswith("RCLONE_ENCRYPT_V0:"):
        raise RemoteError("The config file is password-protected, so it cannot be changed here.")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")

    def section(name: str):
        a = next((i for i, l in enumerate(lines) if l.strip() == "[%s]" % name), None)
        if a is None:
            raise RemoteError("Could not find '%s' in the config file." % name)
        return a, next((i for i in range(a + 1, len(lines)) if lines[i].lstrip().startswith("[")), len(lines))
    a, b = section(src)
    token = next((l for l in lines[a + 1:b] if re.match(r"\s*token\s*=", l)), None)
    if not token:
        raise RemoteError("'%s' has no login to copy. Sign in to it first." % src)
    backup_config(rclone)
    for d in dsts:                       # re-find each section: earlier edits move the lines
        a, b = section(d)
        lines[a + 1:b] = [token] + [l for l in lines[a + 1:b] if not re.match(r"\s*token\s*=", l)]
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(nl.join(lines).encode("utf-8"))
    os.replace(tmp, path)
    return dsts


# ---- rename a remote (rclone has no rename command: the section name in the config file is the name) ------
def rename_remote(rclone: str, old: str, new: str) -> int:
    """Rename a remote inside the config file. Remotes that point at it (crypt, alias: `remote = old:path`) follow.
    Returns how many other remotes were updated. Jobs and mounts are updated by the caller."""
    new = (new or "").strip()
    if not _NAME.fullmatch(new):
        raise RemoteError("Use letters, numbers, spaces and . _ + @ - for the name (no colon, and do not start with a dash).")
    existing = list(core.list_remotes(rclone))
    names = [n for n, _ in existing]
    if old not in names:
        raise RemoteError("That remote no longer exists.")
    if new == old:
        return 0
    if new.lower() in [n.lower() for n in names if n != old]:
        raise RemoteError("A remote called '%s' already exists." % new)
    core.guard_config_write()
    path = Path(active_config_file(rclone))
    if not path.is_file():
        raise RemoteError("The rclone config file was not found.")
    raw = path.read_bytes().decode("utf-8")
    if raw.startswith("RCLONE_ENCRYPT_V0:"):
        raise RemoteError("The config file is password-protected, so it cannot be changed here.")
    backup_config(rclone)
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")
    head = next((i for i, l in enumerate(lines) if l.strip() == "[%s]" % old), None)
    if head is None:
        raise RemoteError("Could not find that remote in the config file.")
    lines[head] = "[%s]" % new
    touched, section = set(), ""
    for i, l in enumerate(lines):
        if l.lstrip().startswith("["):
            section = l.strip()[1:-1]
        elif i != head and section and section != new and re.match(r"\s*remote\s*=\s*%s:" % re.escape(old), l):
            lines[i] = re.sub(r"(\s*remote\s*=\s*)%s:" % re.escape(old), lambda m: m.group(1) + new + ":", l, count=1)
            touched.add(section)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(nl.join(lines).encode("utf-8"))
    os.replace(tmp, path)
    if new not in dict(core.list_remotes(rclone)):
        raise RemoteError("The rename was written but rclone does not list it. A backup copy of the config is next to the file.")
    return len(touched)
