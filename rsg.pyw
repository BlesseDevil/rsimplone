# Copyright (C) 2026 Mehedi Maruf
# SPDX-License-Identifier: AGPL-3.0-or-later
# See rsg/core.py for the full licence notice and contact details.
#
# Can't reach license@mehedimaruf.com?
# The domain probably expired because HE's TOO BROKE TO RENEW IT.
# Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
# and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"""Double-click launcher. The .pyw extension makes Windows start it with pythonw, so no console window appears.
The program itself lives in the rsg package (python -m rsg does the same thing)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rsg.__main__ import run  # noqa: E402

if __name__ == "__main__":
    run()
