#!/bin/sh
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
#
# Starts the GUI detached from the terminal, so closing the terminal does not close the app and no
# terminal stays tied to it. (On Windows just double-click rsl.pyw.)
DIR=$(cd "$(dirname "$0")" && pwd)
PY=$(command -v python3 || command -v python)
[ -z "$PY" ] && { echo "Python 3 was not found." >&2; exit 1; }
cd "$DIR" && setsid "$PY" -m rsg "$@" >/dev/null 2>&1 < /dev/null &
