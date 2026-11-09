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
"""Update check: ask GitHub for the newest published release and say whether it is newer. Only ever runs when the user
turned it on. It only looks: nothing is downloaded or installed, and any failure (offline, rate limit, odd reply) is
silent. The release page link is built from a tag that passed a strict pattern, never from text in the reply."""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Optional, Tuple

REPO = "BlesseDevil/rsimplone"
API = "https://api.github.com/repos/%s/releases/latest" % REPO
RELEASES = "https://github.com/%s/releases" % REPO
_TAG = re.compile(r"v(\d{1,4})\.(\d{1,5})\.(\d{1,6})")
_MAX_REPLY = 200_000


def parse(tag: object) -> Optional[Tuple[int, int, int]]:
    """'v2.2.1' -> (2, 2, 1); anything else (including pre-release suffixes) -> None."""
    m = _TAG.fullmatch(tag) if isinstance(tag, str) else None
    return tuple(int(g) for g in m.groups()) if m else None  # type: ignore[return-value]


def is_newer(current: str, tag: object) -> bool:
    cur, new = parse("v" + current), parse(tag)
    return bool(cur and new and new > cur)


def release_url(tag: str) -> str:
    return "%s/tag/%s" % (RELEASES, tag) if parse(tag) else RELEASES


def fetch_latest(timeout: float = 8.0) -> Optional[str]:
    """The newest published, non-draft, non-pre-release tag, or None for any problem."""
    try:
        req = urllib.request.Request(API, headers={"User-Agent": "rSimpLone-update-check", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https URL)
            data = json.loads(r.read(_MAX_REPLY).decode("utf-8", "replace"))
        if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
            return None
        tag = data.get("tag_name")
        return tag if parse(tag) else None
    except Exception:  # noqa: BLE001
        return None
