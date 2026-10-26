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
"""The windows: a borderless transparent splash (the portal) and a frameless main window with its own title bar.
All the HTML/CSS/JS is in ui/; all the logic is in api.py and core.py. Needs the `pywebview` package."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional, Tuple

from . import core

UI_DIR = Path(__file__).resolve().parent / "ui"
INSTALL_HINT = "rSimpLone's window needs the pywebview package.\n\nInstall it with:\n    python -m pip install pywebview\n\n(Linux also needs GTK or Qt WebKit; see https://pywebview.flowrl.com/guide/installation.html)"


def _fatal(message: str) -> int:
    sys.stderr.write(message + "\n")
    try:
        import tkinter
        from tkinter import messagebox
        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("rSimpLone", message)
        root.destroy()
    except Exception:  # noqa: BLE001  (no tkinter: the message on stderr is all we can do)
        pass
    return 1


def centered(width: int, height: int, screen: Any = None) -> Tuple[int, int, Optional[int], Optional[int]]:
    """(width, height, x, y) that centres a window on the primary screen, shrunk to fit small screens."""
    try:
        if screen is None:
            import webview
            screen = webview.screens[0]
        w, h = min(width, int(screen.width * 0.94)), min(height, int(screen.height * 0.92))
        return w, h, screen.x + (screen.width - w) // 2, screen.y + (screen.height - h) // 2
    except Exception:  # noqa: BLE001
        return width, height, None, None


def screen_center(screen: Any = None) -> Optional[Tuple[float, float]]:
    """Centre of the primary screen in window coordinates, read BEFORE the GUI loop starts."""
    try:
        if screen is None:
            import webview
            screen = webview.screens[0]
        return screen.x + screen.width / 2, screen.y + screen.height / 2
    except Exception:  # noqa: BLE001
        return None


def recenter(window: Any, center: Optional[Tuple[float, float]]):
    """A frameless window ends up smaller than requested, so centre it by its REAL size once it exists."""
    def go() -> None:
        if center is None:
            return
        try:
            window.move(int(center[0] - window.width / 2), int(center[1] - window.height / 2))
        except Exception:  # noqa: BLE001
            pass
    return go


class Tray:
    """Optional tray icon (needs pystray + Pillow). Without them 'hide' simply minimises the window."""

    def __init__(self, window: Any, api: Any) -> None:
        self.window, self.api, self.icon = window, api, None

    def hide(self) -> None:
        try:
            import pystray
            from PIL import Image
        except ImportError:
            self.window.minimize()
            return
        if self.icon is None:
            image = Image.open(UI_DIR / "brand" / "emblem.png").convert("RGBA").resize((64, 64))
            menu = pystray.Menu(pystray.MenuItem("Open rSimpLone", self._show, default=True), pystray.MenuItem("Quit", self._quit))
            self.icon = pystray.Icon("rsimplone", image, "rSimpLone", menu)
            import threading
            threading.Thread(target=self.icon.run, daemon=True).start()
        self.window.hide()

    def _show(self, *_: Any) -> None:
        self.window.show()
        if self.icon is not None:
            self.icon.stop()
            self.icon = None

    def _quit(self, *_: Any) -> None:
        if self.icon is not None:
            self.icon.stop()
            self.icon = None
        self.api.shutdown()
        self.window.destroy()


def main(driver: Optional[Any] = None) -> int:
    """Open the windows. `driver(window, splash, api)` is for tests: it runs in a thread once the GUI loop is up."""
    if sys.stdout is None or sys.stderr is None:      # started by pythonw (double-click): no console
        log = open(core.config_dir() / "gui.log", "a", encoding="utf-8", buffering=1) if core.config_dir().exists() else open(
            __import__("os").devnull, "w")
        sys.stdout = sys.stdout or log
        sys.stderr = sys.stderr or log
    try:
        import webview
    except ImportError:
        return _fatal(INSTALL_HINT)
    from .api import Api

    holder: dict = {}
    api = Api(window_getter=lambda: holder.get("window"))
    mw, mh, mx, my = centered(1360, 860)
    sw, sh, sx, sy = centered(560, 680)
    # The main window is created first (it keeps the app alive) and stays hidden until the splash has finished
    # the real start-up steps; both open centred on the screen.
    window = webview.create_window(
        "rSimpLone by blessedevil", url=str(UI_DIR / "index.html"), js_api=api, width=mw, height=mh, x=mx, y=my,
        min_size=(min(980, mw), min(600, mh)), frameless=True, easy_drag=False, hidden=True, background_color="#1a0b10")
    splash = webview.create_window(
        "rSimpLone", url=str(UI_DIR / "splash.html"), js_api=api, width=sw, height=sh, x=sx, y=sy,
        frameless=True, easy_drag=True, transparent=True, on_top=True, resizable=False, shadow=False)
    holder["window"] = window
    center = screen_center()
    splash.events.loaded += recenter(splash, center)
    api._attach_windows(splash, window, recenter(window, center))
    api.on_hide = Tray(window, api).hide
    window.events.closed += api.shutdown
    splash.events.closed += lambda: None if api.booted and api._ui_ready.is_set() else window.destroy()
    if driver is not None:
        webview.start(lambda: driver(window, splash, api))
    else:
        webview.start()
    api.shutdown()
    return 0
