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
"""Program entry:  python -m rsg   (window)   |   python -m rsg --list | --run NAME [--execute --yes]   (headless).

On Windows start it through rsg.pyw (or pythonw -m rsg) so no console window is created."""
import os
import sys
import time
import traceback


def _quiet_streams() -> None:
    """pythonw has no console streams; make a stray print harmless instead of fatal."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w"))
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r")


def _crash(exc_text: str) -> None:
    """With no console, an unhandled startup error would vanish. Save it and show a dialog."""
    where = "(could not be saved)"
    try:
        from . import core
        folder = core.config_dir()
        folder.mkdir(parents=True, exist_ok=True)
        with open(folder / "crash.log", "a", encoding="utf-8") as fh:
            fh.write("%s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), exc_text))
        where = str(folder / "crash.log")
    except Exception:
        pass
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("rSimpLone could not start", "%s\n\nDetails: %s" % (exc_text.strip().splitlines()[-1], where))
        root.destroy()
    except Exception:
        pass


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if any(a in argv for a in ("--run", "--list", "--help", "-h")):
        from . import core
        return core.cli_main(argv)
    from . import app
    return app.main()


def run() -> None:
    _quiet_streams()
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        _crash(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    run()
