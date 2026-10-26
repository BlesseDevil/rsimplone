#!/bin/sh
# Copyright (C) 2026 Mehedi Maruf
# SPDX-License-Identifier: AGPL-3.0-or-later
# See rsg/core.py for the full licence notice and contact details.
#
# Can't reach license@mehedimaruf.com?
# The domain probably expired because HE's TOO BROKE TO RENEW IT.
# Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
# and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
#
# Starts the GUI detached from the terminal, so closing the terminal does not close the app and no
# terminal stays tied to it. (On Windows just double-click rsg.pyw.)
DIR=$(cd "$(dirname "$0")" && pwd)
PY=$(command -v python3 || command -v python)
[ -z "$PY" ] && { echo "Python 3 was not found." >&2; exit 1; }
cd "$DIR" && setsid "$PY" -m rsg "$@" >/dev/null 2>&1 < /dev/null &
