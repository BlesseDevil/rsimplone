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
"""rclone's own flag list (read from `rclone help flags`), the flags this app refuses to let a job override,
and the merge of a job's tweaks into the command line. Standard library only; knows nothing about jobs."""
from __future__ import annotations

import json
import re
import shlex
from typing import Any, Dict, List, Optional

# Flags the app owns. Letting a job set them would silently break the progress reader, the dry run,
# the per-run backup folder or the way the app reads rclone's configuration.
DENIED_EXACT = {
    "--dry-run", "--backup-dir", "--use-json-log", "--progress", "--verbose", "--quiet", "--interactive",
    "--config", "--ask-password", "--password-command", "--no-console", "--help", "--version", "--dump",
    "--auto-confirm", "--log-file", "--log-level", "--log-format", "--syslog", "--syslog-facility",
}
DENIED_PREFIX = ("--stats", "--log-", "--suffix", "--rc", "--metrics", "--dump", "--human-readable-stats")
DENIED_SHORT = set("Pvqin")       # -P progress, -v verbose, -q quiet, -i interactive, -n dry run

# What the flag does in plain words for the ones people reach for; everything else shows rclone's own text.
KIND_BOOL = "bool"


def is_denied(name: str) -> bool:
    n = name.split("=", 1)[0]
    return n in DENIED_EXACT or n.startswith(DENIED_PREFIX)


def denied_in_tokens(tokens: List[str]) -> List[str]:
    """Return the app-owned flags found in a free-form token list."""
    bad: List[str] = []
    for tok in tokens:
        if tok.startswith("--"):
            if is_denied(tok):
                bad.append(tok.split("=", 1)[0])
        elif re.match(r"^-[A-Za-z]+$", tok):
            for ch in tok[1:]:
                if ch in DENIED_SHORT:
                    bad.append("-" + ch)
    return bad


# --------------------------------------------------------------------------------------------
# the catalogue
# --------------------------------------------------------------------------------------------
_LONG = re.compile(r"^\s{2}(-\w), (--[\w.-]+)(?: (\S+))?\s{2,}(.*)$")
_LONG_ONLY = re.compile(r"^\s{6}(--[\w.-]+)(?: (\S+))?\s{2,}(.*)$")
_GROUP = re.compile(r"^Flags.*\(flag group ([^)]+)\):\s*$")
_DEFAULT = re.compile(r"\(default ([^)]*)\)\s*$")


def parse_help_flags(text: str) -> List[Dict[str, Any]]:
    """Turn the output of `rclone help flags` into [{name, short, type, default, help, group, denied}].
    A flag with no value type is a switch (type 'bool')."""
    out: List[Dict[str, Any]] = []
    group = ""
    for line in text.splitlines():
        m = _GROUP.match(line)
        if m:
            group = m.group(1).strip()
            continue
        if not group:
            continue
        short, name, typ, desc = "", "", "", ""
        a = _LONG.match(line)
        if a:
            short, name, typ, desc = a.group(1), a.group(2), a.group(3) or "", a.group(4)
        else:
            b = _LONG_ONLY.match(line)
            if not b:
                continue
            name, typ, desc = b.group(1), b.group(2) or "", b.group(3)
        default = ""
        d = _DEFAULT.search(desc)
        if d:
            default = d.group(1)
            desc = desc[: d.start()].rstrip()
        out.append({
            "name": name, "short": short, "type": typ or KIND_BOOL, "default": default,
            "help": desc.strip(), "group": group, "denied": is_denied(name),
        })
    return out


def cache_valid(path: Any, version: str) -> Optional[List[Dict[str, Any]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") == version and isinstance(data.get("flags"), list):
            return data["flags"]
    except (OSError, ValueError, AttributeError):
        pass
    return None


# --------------------------------------------------------------------------------------------
# merging a job's tweaks into the command line
# --------------------------------------------------------------------------------------------
def clean_overrides(overrides: Dict[str, Any], catalogue: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Keep only what differs from the default, drop the app-owned flags, and make types sane."""
    known = {f["name"]: f for f in catalogue}
    out: Dict[str, Any] = {}
    for name, value in (overrides or {}).items():
        if not isinstance(name, str) or not name.startswith("--") or is_denied(name):
            continue
        spec = known.get(name)
        if value is None or value == "":
            continue
        if spec and spec["type"] == KIND_BOOL:
            out[name] = bool(value)
            continue
        if isinstance(value, list):
            vals = [str(v) for v in value if str(v).strip()]
            if vals:
                out[name] = vals
            continue
        if spec and spec["default"] and str(value).strip() == spec["default"]:
            continue
        out[name] = str(value).strip()
    return out


def merge(managed: Dict[str, Any], overrides: Dict[str, Any], extra: str = "") -> List[str]:
    """managed: flags the app derived from the job (value None = a switch). overrides: the user's tweaks:
    True switches a flag on, False removes one the app would have added, text or a list sets a value.
    extra: a free-form line of further flags. Raises ValueError for a flag the app owns."""
    result: Dict[str, Any] = dict(managed)
    for name, value in (overrides or {}).items():
        if is_denied(name):
            raise ValueError("%s is managed by rSimpLone and cannot be changed here." % name)
        if value is False or value is None or value == "":
            result.pop(name, None)
        elif value is True:
            result[name] = None
        elif isinstance(value, list):
            result[name] = [str(v) for v in value]
        else:
            result[name] = str(value)
    args: List[str] = []
    for name, value in result.items():
        if value is None:
            args.append(name)
        elif isinstance(value, list):
            for v in value:
                args += [name, v]
        else:
            args += [name, str(value)]
    if extra and extra.strip():
        try:
            tokens = shlex.split(extra, posix=True)
        except ValueError as exc:
            raise ValueError("The extra flags line could not be read: %s" % exc)
        bad = denied_in_tokens(tokens)
        if bad:
            raise ValueError("%s is managed by rSimpLone and cannot be set in the extra flags." % ", ".join(sorted(set(bad))))
        args += tokens
    return args
