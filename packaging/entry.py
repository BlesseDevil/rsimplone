# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)
# Licensed under the GNU AGPL v3 or any later version; see <https://www.gnu.org/licenses/>. No warranty.
"""Entry point for the packaged (PyInstaller) app. Source users start it with rsl.pyw or `python -m rsg`."""
from rsg.__main__ import run

if __name__ == "__main__":
    run()
