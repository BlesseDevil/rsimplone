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
# Contact: license@mehedimaruf.com
# Can't reach license@mehedimaruf.com?
# The domain probably expired because HE's TOO BROKE TO RENEW IT.
# Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
# and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
"""tkinter GUI for the rclone sync/copy manager. Standard library only (drag and drop needs the optional
tkinterdnd2 package; everything else works without it)."""
from __future__ import annotations

import atexit
import copy
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import traceback
import uuid
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple

from . import __version__, core
from .theme import PALETTES, Theme

try:  # optional: drag a folder from the file manager onto the "Local folder" box
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    HAVE_DND = True
except Exception:  # pragma: no cover - depends on the environment
    HAVE_DND = False

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

MODE_TEXT = {
    "sync": "Makes the remote folder match your local folder. Files you changed or deleted locally are moved "
            "into the backup folder, never destroyed.",
    "copy": "Adds new and changed files to the remote and never deletes anything. A backup folder is optional "
            "and only keeps the old versions of files that get replaced.",
}
APP_TITLE = "rSimpLone"
TAGLINE = "rClone fear is at a stake! Sync/Copy via rclone made easy...."
COPYRIGHT = "Copyright (C) 2026 blessedevil | Mehedi Maruf"
CONTACT = "rsimplone@mehedimaruf.com"
LICENSE_CONTACT = "license@mehedimaruf.com"
LICENSE_TEXT = ("Licensed under the GNU Affero General Public License, version 3 or (at your option) any later version.\n"
                "https://www.gnu.org/licenses/")
JOKE = ("Can't reach %s or %s?\n"
        "The domain probably expired because HE's TOO BROKE TO RENEW IT.\n"
        "Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,\n"
        "and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')" % (CONTACT, LICENSE_CONTACT))


HINT = "Don't click the logo! A series of bad things will happen. Also not the copyright."
SITE = "https://mehedimaruf.com"


def _float(text: str, default: float) -> float:
    try:
        return float(str(text).replace(",", ".").strip())
    except ValueError:
        return default


def _int(text: str, default: int) -> int:
    try:
        return int(float(str(text).strip()))
    except ValueError:
        return default


def system_prefers_dark() -> bool:
    try:
        if core.IS_WIN:
            import winreg  # type: ignore
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
                return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
        if sys.platform == "darwin":
            out = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True, text=True, timeout=3)
            return "dark" in out.stdout.lower()
        return "dark" in os.environ.get("GTK_THEME", "").lower()
    except Exception:
        return False


class ScrollFrame(ttk.Frame):
    """A frame that scrolls vertically when its content is taller than the window, so the window can be any height."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0, width=1, height=1)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.inner.bind("<Configure>", self._resize)
        self.canvas.bind("<Configure>", self._resize)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):      # Button-4/5 are the wheel on Linux
            self.bind_all(seq, self._wheel, add="+")

    def _resize(self, _e: Any = None) -> None:
        # content is at least as tall as the window (so rows can stretch) and scrolls once it is taller
        height = max(self.canvas.winfo_height(), self.inner.winfo_reqheight())
        self.canvas.itemconfigure(self._win, width=self.canvas.winfo_width(), height=height)
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), height))

    def _on_scroll(self, lo: str, hi: str) -> None:
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.vsb.grid_remove()
        else:
            self.vsb.grid(row=0, column=1, sticky="ns")
        self.vsb.set(lo, hi)

    def _wheel(self, event: Any) -> None:
        widget = event.widget
        if str(widget.winfo_class()) in ("Treeview", "Text", "Listbox", "TCombobox"):
            return                                   # these scroll themselves
        while widget is not None and widget is not self:    # only react to the wheel over this frame's own content
            widget = getattr(widget, "master", None)
        if widget is self and self.vsb.winfo_ismapped():
            step = -1 if (getattr(event, "num", 0) == 4 or getattr(event, "delta", 0) > 0) else 1
            self.canvas.yview_scroll(step * 3, "units")


class Dialog(tk.Toplevel):
    """A themed pop-up centred over the main window."""

    def __init__(self, app: "App", title: str, modal: bool = True) -> None:
        super().__init__(app.root)
        self.app = app
        self.configure(bg=app.pal["bg"])
        self.title(title)
        self.transient(app.root)
        self.resizable(False, False)
        self.body = ttk.Frame(self, padding=app.theme.px(20))
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda e: self.destroy())
        self._modal = modal

    def present(self) -> None:
        self.update_idletasks()
        root = self.app.root
        x = root.winfo_rootx() + (root.winfo_width() - self.winfo_width()) // 2
        y = root.winfo_rooty() + (root.winfo_height() - self.winfo_height()) // 3
        self.geometry("+%d+%d" % (max(x, 0), max(y, 0)))
        if self._modal:
            self.grab_set()


class ExecuteDialog(Dialog):
    """Real runs are confirmed by typing EXECUTE. Closing the dialog or pressing Cancel is the default."""

    def __init__(self, app: "App", text: str) -> None:
        super().__init__(app, "Confirm real run")
        self.result = False
        ttk.Label(self.body, text="Run for real?", style="Head.TLabel").pack(anchor="w")
        ttk.Label(self.body, text=text, wraplength=app.theme.px(480), justify="left").pack(anchor="w", pady=(8, 0))
        ttk.Label(self.body, text="Type EXECUTE to confirm", style="Muted.TLabel").pack(anchor="w", pady=(16, 4))
        self.var = tk.StringVar()
        self.entry = ttk.Entry(self.body, textvariable=self.var, width=26)
        self.entry.pack(anchor="w")
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(18, 0))
        self.ok = ttk.Button(row, text="Run for real", style="Danger.TButton", command=self._ok, state="disabled")
        self.ok.pack(side="right")
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.var.trace_add("write", lambda *_: self.ok.configure(state="normal" if self.var.get() == "EXECUTE" else "disabled"))
        self.bind("<Return>", lambda e: self._ok() if self.var.get() == "EXECUTE" else None)
        self.present()
        self.entry.focus_set()

    def _ok(self) -> None:
        if self.var.get() == "EXECUTE":
            self.result = True
            self.destroy()


class FolderPicker(Dialog):
    """Pick a folder from the remote's folder listing (one list call, reused for 15 minutes)."""

    def __init__(self, app: "App", which: str) -> None:
        super().__init__(app, "Pick a folder on the remote", modal=False)
        self.which = which
        self.paths: Dict[str, str] = {}
        remote = app.v_remote.get().strip()
        ttk.Label(self.body, text="Backup folder" if which == "backup" else "Target folder", style="Head.TLabel").pack(anchor="w")
        ttk.Label(self.body, text="on %s:" % remote, style="Muted.TLabel").pack(anchor="w")
        top = ttk.Frame(self.body)
        top.pack(fill="x", pady=(12, 8))
        self.btn = ttk.Button(top, text="List folders again", command=lambda: app.list_folders(force=True))
        self.btn.pack(side="left")
        ttk.Label(top, text="depth", style="Muted.TLabel").pack(side="left", padx=(12, 4))
        ttk.Spinbox(top, from_=1, to=6, width=3, textvariable=app.v_depth).pack(side="left")
        self.note = ttk.Label(self.body, text="Depth 1 is one list call; each extra level costs about one call per folder.",
                              style="Muted.TLabel", wraplength=app.theme.px(420), justify="left")
        self.note.pack(anchor="w", pady=(0, 8))
        card = ttk.Frame(self.body, style="Card.TFrame", padding=app.theme.px(10))
        card.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(card, show="tree", selectmode="browse", height=9, style="Card.Treeview")
        sb = ttk.Scrollbar(card, command=self.tree.yview, style="Card.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-1>", lambda e: self.use())
        row = ttk.Frame(self.body)
        row.pack(fill="x", pady=(14, 0))
        ttk.Button(row, text="Use this folder", style="Accent.TButton", command=self.use).pack(side="right")
        ttk.Button(row, text="Cancel", command=self.destroy).pack(side="right", padx=8)
        self.refresh()
        self.present()

    def refresh(self) -> None:
        app = self.app
        self.tree.delete(*self.tree.get_children())
        self.paths = {}
        if app.dirs_remote != app.v_remote.get().strip() or not app.dirs_time:
            self.note.configure(text="Listing the remote...")
            return
        nodes: Dict[str, str] = {}
        for path in sorted(app.dirs, key=lambda p: p.lower()):
            parent = "/".join(path.split("/")[:-1])
            iid = self.tree.insert(nodes.get(parent, ""), "end", text=path.split("/")[-1], open=True)
            nodes[path] = iid
        self.paths = {iid: p for p, iid in nodes.items()}
        self.note.configure(text="%d folder(s) listed, depth %d. Double-click or press 'Use this folder'." % (len(app.dirs), app.dirs_depth))

    def use(self) -> None:
        sel = self.tree.selection()
        path = self.paths.get(sel[0]) if sel else None
        if not path:
            return
        (self.app.v_backup if self.which == "backup" else self.app.v_target).set(path)
        self.destroy()


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.store = core.load_store()
        self.rclone = core.find_rclone(str(self.store.settings.get("rclone", "")))
        self.events: "queue.Queue[Tuple[str, Any]]" = queue.Queue()
        self.run: Optional[core.SyncRun] = None
        self.cur: Optional[core.Job] = None
        self.loading = False
        self.dirs: List[str] = []
        self.dirs_remote = ""
        self.dirs_depth = 0
        self.dirs_time = 0.0
        self.pending: Optional[bool] = None       # a run waiting for the folder listing: real or dry
        self.remotes: List[Tuple[str, str]] = []
        self.run_started = 0.0
        self.last_result: Optional[core.RunResult] = None
        self.closing = False
        self.activity_rows = 0
        self.log_lines = 0
        self.banner_kind = "idle"
        self.note_kind = "muted"
        self.picker: Optional[FolderPicker] = None
        self.opts_open = False
        self._poll_id: Optional[str] = None
        self._images: List[tk.PhotoImage] = []

        root.title("%s by blessedevil" % APP_TITLE)
        width = min(1240, max(root.winfo_screenwidth() - 60, 900))
        height = min(1000, max(root.winfo_screenheight() - 110, 480))
        root.geometry("%dx%d+30+20" % (width, height))
        root.minsize(900, 420)
        self.rclone_ver = ""
        self._disk_timer: Optional[str] = None
        self.logo_clicks = 0
        self.theme = Theme(root)
        self.scale = self.theme.scale
        self.pal = self.theme.pal
        self.theme_choice = str(self.store.settings.get("theme", "auto"))
        self.theme.apply(self._resolve_theme(self.theme_choice))
        self.pal = self.theme.pal
        self._vars()
        self._window_icons()
        self._build()
        self._menu()
        self._recolor()
        self._fit_height()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.report_callback_exception = self._callback_exception
        atexit.register(self._kill_child)
        root.bind("<F5>", lambda e: self.list_folders())

        self.refresh_jobs()
        if not self.store.jobs:
            self.new_job()
        elif self.jobs.get_children():
            self.jobs.selection_set(self.jobs.get_children()[0])
        self.act.insert("", "end", text=HINT, values=("", ""), tags=("hint",))
        self.refresh_remotes()
        self._load_version()
        self._status_bar()
        self.poll()

    # ---------------------------------------------------------------------------------------- theme
    def _resolve_theme(self, choice: str) -> str:
        if choice in ("light", "dark"):
            return choice
        return "dark" if system_prefers_dark() else "light"

    def set_theme(self, choice: str, save: bool = True) -> None:
        if choice not in ("auto", "light", "dark"):
            choice = "auto"
        self.theme_choice = choice
        self.v_theme.set(choice)
        self.theme.apply(self._resolve_theme(choice))
        self.pal = self.theme.pal
        self._recolor()
        if save:
            self.store.settings["theme"] = choice
            self._save()

    def _logo_click(self) -> None:
        """Three clicks change the theme (system, light, dark); the fourth opens the website."""
        self.logo_clicks += 1
        if self.logo_clicks % 4 == 0:
            self.open_site()
        else:
            self.cycle_theme()

    def open_site(self) -> None:
        self.status.configure(text="Opening mehedimaruf.com ...", foreground=self._tone("muted"))
        self.root.after(2500, self._status_bar)
        try:
            webbrowser.open(SITE)
        except Exception:
            pass

    def _hint(self) -> None:
        self.status.configure(text=HINT, foreground=self._tone("muted"))

    THEME_CYCLE = ("auto", "light", "dark")
    THEME_NAMES = {"auto": "match system", "light": "light", "dark": "dark"}

    def cycle_theme(self) -> None:
        """The logo is the theme button: system -> light -> dark -> system."""
        cur = self.theme_choice if self.theme_choice in self.THEME_CYCLE else "auto"
        nxt = self.THEME_CYCLE[(self.THEME_CYCLE.index(cur) + 1) % len(self.THEME_CYCLE)]
        self.set_theme(nxt)
        self.status.configure(text="Theme: %s   (click the logo to change it)" % self.THEME_NAMES[nxt], foreground=self._tone("muted"))
        self.root.after(2500, self._status_bar)

    def _window_icons(self) -> None:
        icons = []
        for name in ("icon-16.png", "icon-32.png", "icon-48.png", "icon-64.png"):
            path = os.path.join(ASSETS, name)
            if os.path.exists(path):
                try:
                    icons.append(tk.PhotoImage(file=path))
                except tk.TclError:
                    pass
        if icons:
            self._images.extend(icons)
            try:
                self.root.iconphoto(True, *icons)
            except tk.TclError:
                pass

    def _emblem(self) -> Optional[tk.PhotoImage]:
        """Full-colour emblem on the light theme, the gold one on the dark theme (as the brand notes advise)."""
        prefix = "emblem-gold" if self.theme.name == "dark" else "emblem"
        want = 46 * self.scale
        best: Optional[Tuple[int, str]] = None
        for size in (48, 64, 96, 128):
            path = os.path.join(ASSETS, "%s-%d.png" % (prefix, size))
            if os.path.exists(path) and (best is None or abs(size - want) < abs(best[0] - want)):
                best = (size, path)
        if not best:
            return None
        try:
            img = tk.PhotoImage(file=best[1])
        except tk.TclError:
            return None
        self._images.append(img)
        return img

    def _recolor(self) -> None:
        """Re-apply colours to the widgets ttk styles do not reach."""
        p = self.pal
        self.root.configure(bg=p["bg"])
        self.logo = self._emblem()
        self.logo_label.configure(image=self.logo if self.logo else "", bg=p["bg"])
        self.log.configure(bg=p["surface"], fg=p["text"], insertbackground=p["text"], selectbackground=p["select"],
                           font=self.theme.f_mono, highlightthickness=0, relief="flat", padx=6, pady=4)
        self.log.tag_configure("error", foreground=p["error"])
        self.log.tag_configure("notice", foreground=p["warn"])
        self.jobs.tag_configure("ok", foreground=p["success"])
        self.jobs.tag_configure("bad", foreground=p["error"])
        self.jobs.tag_configure("never", foreground=p["muted"])
        for tag, color in (("upload", p["link"]), ("backup", p["warn"]), ("replace", p["warn"]), ("hint", p["muted"]),
                           ("modtime", p["muted"]), ("delete", p["error"]), ("error", p["error"])):
            self.act.tag_configure(tag, foreground=color)
        self.banner_wrap.configure(bg=p["bg"])
        self.scroll.canvas.configure(bg=p["bg"])
        self._banner(self.banner_kind, self.banner.cget("text"))
        self.refresh_verdicts()
        self._set_note(self.list_hint_text, self.note_kind)
        self._status_bar()

    def _tone(self, kind: str) -> str:
        return {"ok": self.pal["success"], "warn": self.pal["warn"], "bad": self.pal["error"],
                "muted": self.pal["muted"], "link": self.pal["link"]}[kind]

    # ---------------------------------------------------------------------------------------- setup
    def _vars(self) -> None:
        sv = tk.StringVar
        self.v_name, self.v_source, self.v_remote = sv(), sv(), sv()
        self.v_target, self.v_backup, self.v_label = sv(), sv(), sv()
        self.v_mode, self.v_disk, self.v_theme = sv(value="sync"), sv(value="hdd"), sv(value=self.theme_choice)
        self.v_dest = sv(value="remote")
        self.v_mbps, self.v_pct = sv(value="30"), sv(value="85")
        self.v_checkers, self.v_transfers, self.v_depth = sv(value="0"), sv(value="0"), sv(value="1")
        self.v_runtab = sv(value="activity")
        self.v_nolimit, self.v_skip = tk.BooleanVar(), tk.BooleanVar()
        self.v_low, self.v_nodirtime = tk.BooleanVar(value=True), tk.BooleanVar(value=False)
        self.v_source.trace_add("write", self._source_edited)
        for var in (self.v_name, self.v_source, self.v_remote, self.v_target, self.v_backup, self.v_label,
                    self.v_mode, self.v_dest, self.v_disk, self.v_mbps, self.v_pct, self.v_checkers, self.v_transfers,
                    self.v_depth, self.v_nolimit, self.v_skip, self.v_low, self.v_nodirtime):
            var.trace_add("write", self._form_changed)
        self.v_runtab.trace_add("write", lambda *_: self._show_runtab())

    def _menu(self) -> None:
        bar = tk.Menu(self.root)
        filem = tk.Menu(bar, tearoff=False)
        filem.add_command(label="Settings...", command=self.open_settings)
        filem.add_command(label="Open data folder", command=lambda: self._open(str(core.config_dir())))
        filem.add_separator()
        filem.add_command(label="Quit", command=self.on_close)
        bar.add_cascade(label="File", menu=filem)
        viewm = tk.Menu(bar, tearoff=False)
        for label, value in (("Match system", "auto"), ("Light", "light"), ("Dark", "dark")):
            viewm.add_radiobutton(label=label, value=value, variable=self.v_theme, command=lambda v=value: self.set_theme(v))
        bar.add_cascade(label="Theme", menu=viewm)
        helpm = tk.Menu(bar, tearoff=False)
        helpm.add_command(label="About", command=self.about)
        bar.add_cascade(label="Help", menu=helpm)
        self.root.config(menu=bar)

    def about(self) -> None:
        dlg = Dialog(self, "About %s" % APP_TITLE)
        wrap = self.theme.px(520)
        row = ttk.Frame(dlg.body)
        row.pack(anchor="w")
        if self.logo:
            tk.Label(row, image=self.logo, bg=self.pal["bg"], bd=0).pack(side="left", padx=(0, 14))
        col = ttk.Frame(row)
        col.pack(side="left")
        ttk.Label(col, text=APP_TITLE, style="Title.TLabel").pack(anchor="w")
        ttk.Label(col, text="by blessedevil   |   version %s" % __version__, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(dlg.body, text=TAGLINE, wraplength=wrap, justify="left").pack(anchor="w", pady=(14, 0))
        ttk.Label(dlg.body, text="Contact the developer", style="Head.TLabel").pack(anchor="w", pady=(16, 0))
        ttk.Label(dlg.body, text=CONTACT, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(dlg.body, text="Licence questions", style="Head.TLabel").pack(anchor="w", pady=(10, 0))
        ttk.Label(dlg.body, text=LICENSE_CONTACT, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(dlg.body, text=JOKE, justify="left", wraplength=wrap).pack(anchor="w", pady=(14, 0))
        ttk.Label(dlg.body, text="%s\n%s" % (COPYRIGHT, LICENSE_TEXT), style="Muted.TLabel", justify="left",
                  wraplength=wrap).pack(anchor="w", pady=(14, 0))
        buttons = ttk.Frame(dlg.body)
        buttons.pack(fill="x", pady=(16, 0))
        ttk.Button(buttons, text="Close", command=dlg.destroy).pack(side="right")
        ttk.Button(buttons, text="Website", command=self.open_site).pack(side="right", padx=8)
        ttk.Button(buttons, text="Email the developer", style="Accent.TButton", command=self.email_dev).pack(side="right")
        dlg.present()

    def email_dev(self) -> None:
        try:
            webbrowser.open("mailto:%s?subject=%s" % (CONTACT, APP_TITLE))
        except Exception:
            pass

    def card(self, parent: tk.Misc, pad: float = 16) -> ttk.Frame:
        return ttk.Frame(parent, style="Card.TFrame", padding=self.theme.px(pad))

    def _build(self) -> None:
        px = self.theme.px
        outer = ttk.Frame(self.root, padding=(px(22), px(14), px(22), px(6)))
        outer.pack(fill="both", expand=True)
        self.status = ttk.Label(self.root, anchor="w", padding=(px(22), px(4)), style="Muted.TLabel")
        self.status.pack(fill="x", side="bottom")

        head = ttk.Frame(outer)
        head.pack(fill="x", pady=(0, px(12)))
        self.logo_label = tk.Label(head, bd=0, cursor="hand2")
        self.logo_label.pack(side="left", padx=(0, px(14)))
        self.logo_label.bind("<Button-1>", lambda e: self._logo_click())
        self.logo_label.bind("<Enter>", lambda e: self._hint())
        self.logo_label.bind("<Leave>", lambda e: self._status_bar())
        titles = ttk.Frame(head)
        titles.pack(side="left")
        name_row = ttk.Frame(titles)
        name_row.pack(anchor="w")
        ttk.Label(name_row, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        ttk.Label(name_row, text="by blessedevil", style="Muted.TLabel").pack(side="left", padx=(px(10), 0), pady=(px(10), 0))
        ttk.Label(titles, text=TAGLINE, style="Muted.TLabel").pack(anchor="w")
        # the right-hand side of the header: copyright and a way to reach the developer
        right = ttk.Frame(head)
        right.pack(side="right", anchor="n")
        self.copyright_label = ttk.Label(right, text=COPYRIGHT, style="Muted.TLabel", cursor="hand2")
        self.copyright_label.pack(anchor="e")
        self.copyright_label.bind("<Button-1>", lambda e: self.open_site())
        self.copyright_label.bind("<Enter>", lambda e: self._hint())
        self.copyright_label.bind("<Leave>", lambda e: self._status_bar())
        ttk.Button(right, text="Contact dev", style="Ghost.TButton", command=self.about).pack(anchor="e", pady=(px(8), 0))

        self.scroll = ScrollFrame(outer)           # the whole work area scrolls if the window is made short
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll.inner
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # jobs -------------------------------------------------------------------------------------
        jc = self.card(body, 14)
        jc.grid(row=0, column=0, sticky="ns", padx=(0, px(16)))
        jc.configure(width=px(280))
        jc.pack_propagate(False)          # keep the list narrow instead of letting the table decide
        ttk.Label(jc, text="Jobs", style="Card.Head.TLabel").pack(anchor="w", pady=(0, px(8)))
        inner = ttk.Frame(jc, style="CardPlain.TFrame")
        inner.pack(fill="both", expand=True)
        self.jobs = ttk.Treeview(inner, columns=("mode", "last"), show="tree", selectmode="browse", height=12, style="Card.Treeview")
        self.jobs.column("#0", width=px(120), stretch=True)
        self.jobs.column("mode", width=px(46), stretch=False)
        self.jobs.column("last", width=px(100), stretch=False)
        self.jobs.pack(fill="both", expand=True)
        self.jobs.bind("<<TreeviewSelect>>", self._job_selected)
        self.jobs.bind("<Delete>", lambda e: self.delete_job())
        row = ttk.Frame(jc, style="CardPlain.TFrame")
        row.pack(fill="x", pady=(px(10), 0))
        for col in range(3):
            row.columnconfigure(col, weight=1, uniform="jobbtn")
        ttk.Button(row, text="+ New", style="CardBtn.TButton", command=self.new_job).grid(row=0, column=0, sticky="ew", padx=(0, 3))
        ttk.Button(row, text="Duplicate", style="CardBtn.TButton", command=self.duplicate_job).grid(row=0, column=1, sticky="ew", padx=3)
        ttk.Button(row, text="Delete", style="CardBtn.TButton", command=self.delete_job).grid(row=0, column=2, sticky="ew", padx=(3, 0))
        ttk.Label(jc, text="Deleting a job removes only its\nsaved settings, never files.", style="Card.Muted.TLabel").pack(anchor="w", pady=(px(10), 0))

        # right column --------------------------------------------------------------------------------
        rc = ttk.Frame(body)
        rc.grid(row=0, column=1, sticky="nsew")
        rc.columnconfigure(0, weight=1)
        rc.rowconfigure(3, weight=1)
        self._build_editor(rc)
        self._build_run(rc)

    def _build_editor(self, rc: ttk.Frame) -> None:
        px = self.theme.px
        top = ttk.Frame(rc)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Radiobutton(top, text="Sync", value="sync", variable=self.v_mode, style="Seg.Toolbutton").pack(side="left")
        ttk.Radiobutton(top, text="Copy", value="copy", variable=self.v_mode, style="Seg.Toolbutton").pack(side="left", padx=(6, 0))
        # the three buttons that start and stop a run live up here so they never scroll out of view
        self.btn_stop = ttk.Button(top, text="Stop", style="Ghost.TButton", command=self.stop, state="disabled")
        self.btn_stop.pack(side="right")
        self.btn_exec = ttk.Button(top, text="Execute...", style="Danger.TButton", command=lambda: self.start(True))
        self.btn_exec.pack(side="right", padx=px(8))
        self.btn_dry = ttk.Button(top, text="Dry run", style="Accent.TButton", command=lambda: self.start(False))
        self.btn_dry.pack(side="right")
        self.mode_text = ttk.Label(rc, text="", style="Muted.TLabel", justify="left")
        self.mode_text.grid(row=1, column=0, sticky="w", pady=(px(8), px(10)))
        rc.bind("<Configure>", lambda e: self.mode_text.configure(wraplength=max(e.width - px(20), 240)))

        setup = self.card(rc, 16)
        setup.grid(row=2, column=0, sticky="ew")
        setup.columnconfigure(1, weight=1)
        self.setup = setup

        def label(r: int, text: str) -> ttk.Label:
            lab = ttk.Label(setup, text=text, style="Card.TLabel")
            lab.grid(row=r, column=0, sticky="w", pady=px(3), padx=(0, px(14)))
            return lab

        label(0, "Job name")
        ttk.Entry(setup, textvariable=self.v_name, style="Card.TEntry").grid(row=0, column=1, columnspan=2, sticky="ew")
        label(1, "Local folder")
        self.e_source = ttk.Entry(setup, textvariable=self.v_source, style="Card.TEntry")
        self.e_source.grid(row=1, column=1, sticky="ew")
        ttk.Button(setup, text="Browse...", style="CardBtn.TButton", command=self.browse_source).grid(row=1, column=2, padx=(px(8), 0))
        if HAVE_DND:
            try:
                self.e_source.drop_target_register(DND_FILES)
                self.e_source.dnd_bind("<<Drop>>", self._dropped)
            except Exception:
                pass
        self.space_var = tk.StringVar()
        sp = ttk.Frame(setup, style="CardPlain.TFrame")
        sp.grid(row=2, column=1, columnspan=2, sticky="ew")
        self.space_bar = ttk.Progressbar(sp, maximum=100, length=px(130))
        self.space_bar.pack(side="left")
        ttk.Label(sp, textvariable=self.space_var, style="Card.Muted.TLabel").pack(side="left", padx=px(10))

        label(3, "Send to")
        sendto = ttk.Frame(setup, style="CardPlain.TFrame")
        sendto.grid(row=3, column=1, columnspan=2, sticky="w", pady=px(3))
        ttk.Radiobutton(sendto, text="Cloud remote", value="remote", variable=self.v_dest, style="CardSeg.Toolbutton").pack(side="left")
        ttk.Radiobutton(sendto, text="Local folder", value="local", variable=self.v_dest, style="CardSeg.Toolbutton").pack(side="left", padx=(6, 0))

        self.lab_remote = label(4, "Remote")
        self.c_remote = ttk.Combobox(setup, textvariable=self.v_remote, state="readonly", values=[], style="Card.TCombobox")
        self.c_remote.grid(row=4, column=1, sticky="ew")
        self.btn_refresh = ttk.Button(setup, text="Refresh", style="CardBtn.TButton", command=self.refresh_remotes)
        self.btn_refresh.grid(row=4, column=2, padx=(px(8), 0))

        self.lab_target = label(5, "Target folder")
        ttk.Entry(setup, textvariable=self.v_target, style="Card.TEntry").grid(row=5, column=1, sticky="ew")
        ttk.Button(setup, text="Pick...", style="CardBtn.TButton", command=lambda: self.pick("target")).grid(row=5, column=2, padx=(px(8), 0))
        self.verdict_t = ttk.Label(setup, text="", style="Card.TLabel")
        self.verdict_t.grid(row=6, column=1, columnspan=2, sticky="w")
        self.space_t = ttk.Label(setup, text="", style="Card.Muted.TLabel")      # free space, on the same row, local only
        self.space_t.grid(row=6, column=1, columnspan=2, sticky="e")
        self.lab_backup = label(7, "Backup folder")
        ttk.Entry(setup, textvariable=self.v_backup, style="Card.TEntry").grid(row=7, column=1, sticky="ew")
        ttk.Button(setup, text="Pick...", style="CardBtn.TButton", command=lambda: self.pick("backup")).grid(row=7, column=2, padx=(px(8), 0))
        self.verdict_b = ttk.Label(setup, text="", style="Card.TLabel")
        self.verdict_b.grid(row=8, column=1, columnspan=2, sticky="w")
        self.space_b = ttk.Label(setup, text="", style="Card.Muted.TLabel")
        self.space_b.grid(row=8, column=1, columnspan=2, sticky="e")
        foot = ttk.Frame(setup, style="CardPlain.TFrame")
        foot.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(px(4), 0))
        self.list_hint_text = "Depth 1 = one list call"
        self.btn_opts = ttk.Button(foot, text="⚙", style="CardBtn.TButton", command=self.toggle_options)   # gear
        self.btn_opts.pack(side="right")
        self.btn_opts.bind("<Enter>", lambda e: self.status.configure(
            text="Options: sub-folder, tuning, folder check, export", foreground=self._tone("muted")))
        self.btn_opts.bind("<Leave>", lambda e: self._status_bar())
        # collapsible options ---------------------------------------------------------------------------
        self.opts = ttk.Frame(setup, style="CardPlain.TFrame")
        self.opts.grid(row=11, column=0, columnspan=3, sticky="ew", pady=(px(10), 0))
        self.opts.columnconfigure(1, weight=1)
        ttk.Separator(self.opts, style="Card.TSeparator").grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, px(10)))
        # listing the remote's folders costs an API call, so the button lives here and not in plain sight
        self.chk_row = ttk.Frame(self.opts, style="CardPlain.TFrame")
        self.chk_row.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, px(10)))
        self.btn_check = ttk.Button(self.chk_row, text="Check folders", style="CardBtn.TButton", command=lambda: self.list_folders(force=True))
        self.btn_check.pack(side="left")
        self.list_note = ttk.Label(self.chk_row, text="", style="Card.Muted.TLabel")
        self.list_note.pack(side="left", padx=px(12))
        ttk.Label(self.opts, text="Sub-folder name", style="Card.TLabel").grid(row=2, column=0, sticky="w", padx=(0, px(14)))
        ttk.Entry(self.opts, textvariable=self.v_label, style="Card.TEntry").grid(row=2, column=1, columnspan=3, sticky="ew")
        self.layout_hint = ttk.Label(self.opts, text="", style="Card.Muted.TLabel", wraplength=px(560), justify="left")
        self.layout_hint.grid(row=3, column=1, columnspan=3, sticky="w", pady=(px(2), 0))
        self.chk_skip = ttk.Checkbutton(self.opts, text="Skip files that already exist on the remote (copy only; changed files are not updated)",
                                        variable=self.v_skip, style="Card.TCheckbutton")
        self.chk_skip.grid(row=4, column=0, columnspan=4, sticky="w", pady=(px(8), 0))
        tune = ttk.Frame(self.opts, style="CardPlain.TFrame")
        tune.grid(row=5, column=0, columnspan=4, sticky="ew", pady=(px(12), 0))
        ttk.Label(tune, text="Source disk", style="Card.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Radiobutton(tune, text="HDD", value="hdd", variable=self.v_disk, style="CardSeg.Toolbutton").grid(row=0, column=1, padx=(px(10), 0))
        ttk.Radiobutton(tune, text="SSD", value="ssd", variable=self.v_disk, style="CardSeg.Toolbutton").grid(row=0, column=2, padx=(6, 0))
        self.disk_note = ttk.Label(tune, text="", style="Card.Muted.TLabel")
        self.disk_note.grid(row=1, column=0, columnspan=9, sticky="w", pady=(px(4), 0))   # spans the row so it cannot widen the columns
        ttk.Label(tune, text="Line speed", style="Card.TLabel").grid(row=0, column=3, padx=(px(22), px(6)))
        sp_mbps = ttk.Spinbox(tune, from_=1, to=10000, increment=5, width=6, textvariable=self.v_mbps, style="Card.TSpinbox")
        sp_mbps.grid(row=0, column=4)
        ttk.Label(tune, text="Mbit/s, use", style="Card.Muted.TLabel").grid(row=0, column=5, padx=6)
        sp_pct = ttk.Spinbox(tune, from_=1, to=100, width=4, textvariable=self.v_pct, style="Card.TSpinbox")
        sp_pct.grid(row=0, column=6)
        ttk.Label(tune, text="%", style="Card.Muted.TLabel").grid(row=0, column=7, padx=(3, px(10)))
        chk_nolimit = ttk.Checkbutton(tune, text="No limit", variable=self.v_nolimit, style="Card.TCheckbutton")
        chk_nolimit.grid(row=0, column=8)
        ttk.Label(tune, text="Checkers", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=(px(10), 0))
        ttk.Spinbox(tune, from_=0, to=64, width=4, textvariable=self.v_checkers, style="Card.TSpinbox").grid(row=2, column=1, columnspan=2, sticky="w", padx=(px(10), 0), pady=(px(10), 0))
        ttk.Label(tune, text="Transfers", style="Card.TLabel").grid(row=2, column=3, sticky="e", pady=(px(10), 0))
        ttk.Spinbox(tune, from_=0, to=64, width=4, textvariable=self.v_transfers, style="Card.TSpinbox").grid(row=2, column=4, sticky="w", padx=(px(6), 0), pady=(px(10), 0))
        ttk.Label(tune, text="0 = automatic", style="Card.Muted.TLabel").grid(row=2, column=5, columnspan=3, sticky="w", padx=6, pady=(px(10), 0))
        chk_low = ttk.Checkbutton(tune, text="Fewest Drive API calls", variable=self.v_low, style="Card.TCheckbutton")
        chk_low.grid(row=3, column=0, columnspan=3, sticky="w", pady=(px(12), 0))
        chk_nodir = ttk.Checkbutton(tune, text="Don't update folder dates on the remote", variable=self.v_nodirtime, style="Card.TCheckbutton")
        chk_nodir.grid(row=3, column=3, columnspan=6, sticky="w", pady=(px(12), 0), padx=(px(22), 0))
        self.cloud_only = [sp_mbps, sp_pct, chk_nolimit, chk_low, chk_nodir]    # meaningless for a local destination
        self.tune_note = ttk.Label(tune, text="", style="Card.Muted.TLabel")
        self.tune_note.grid(row=4, column=0, columnspan=9, sticky="w", pady=(px(6), 0))
        self.opts.grid_remove()

        share = ttk.Frame(self.opts, style="CardPlain.TFrame")
        share.grid(row=6, column=0, columnspan=4, sticky="w", pady=(px(14), 0))
        ttk.Button(share, text="Copy command", style="CardBtn.TButton", command=self.copy_command).pack(side="left")
        ttk.Button(share, text="Export script...", style="CardBtn.TButton", command=self.export_script).pack(side="left", padx=px(8))
        ttk.Label(share, text="Run this job outside the app, for example from a scheduler.", style="Card.Muted.TLabel").pack(side="left", padx=px(8))
        self.opts.grid_remove()

    def _build_run(self, rc: ttk.Frame) -> None:
        px = self.theme.px
        host = ttk.Frame(rc)
        host.grid(row=3, column=0, sticky="nsew", pady=(px(6), 0))
        host.columnconfigure(0, weight=1)
        host.rowconfigure(4, weight=1)
        self.banner_wrap = tk.Frame(host, bd=0)
        self.banner_wrap.grid(row=0, column=0, sticky="ew")
        self.banner_stripe = tk.Frame(self.banner_wrap, width=px(5), bd=0)
        self.banner_stripe.pack(side="left", fill="y")
        self.banner = tk.Label(self.banner_wrap, text="Ready. Pick a job, check the setup, then run a dry run first.", anchor="w",
                               justify="left", padx=px(14), pady=px(10), bd=0)
        self.banner.pack(side="left", fill="x", expand=True)
        host.bind("<Configure>", lambda e: self.banner.configure(wraplength=max(e.width - px(60), 200)))
        prog = ttk.Frame(host)
        prog.grid(row=1, column=0, sticky="ew", pady=(px(10), 0))
        self.progress = ttk.Progressbar(prog, maximum=100, mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True)
        ttk.Button(prog, text="Logs folder", style="Small.TButton", command=lambda: self._open(str(core.log_dir()))).pack(side="right", padx=(px(8), 0))
        self.btn_log = ttk.Button(prog, text="This run's log", style="Small.TButton", command=self.open_log, state="disabled")
        self.btn_log.pack(side="right", padx=(px(8), 0))
        self.btn_execute_now = ttk.Button(prog, text="Execute now...", style="Danger.TButton", command=lambda: self.start(True))
        statrow = ttk.Frame(host)
        statrow.grid(row=2, column=0, sticky="ew", pady=(px(4), 0))
        self.stats_var = tk.StringVar()
        self.now_var = tk.StringVar()
        ttk.Label(statrow, textvariable=self.stats_var, style="Muted.TLabel").pack(side="left")
        ttk.Label(host, textvariable=self.now_var).grid(row=3, column=0, sticky="w")

        panel = self.card(host, 12)
        panel.grid(row=4, column=0, sticky="nsew", pady=(px(6), 0))
        panel.columnconfigure(0, weight=1)
        panel.rowconfigure(1, weight=1)
        seg = ttk.Frame(panel, style="CardPlain.TFrame")
        seg.grid(row=0, column=0, sticky="w", pady=(0, px(8)))
        ttk.Radiobutton(seg, text="Activity", value="activity", variable=self.v_runtab, style="CardSeg.Toolbutton").pack(side="left")
        ttk.Radiobutton(seg, text="Log", value="log", variable=self.v_runtab, style="CardSeg.Toolbutton").pack(side="left", padx=(6, 0))
        self.run_body = ttk.Frame(panel, style="CardPlain.TFrame")
        self.run_body.grid(row=1, column=0, sticky="nsew")
        self.run_body.columnconfigure(0, weight=1)
        self.run_body.rowconfigure(0, weight=1)
        self.act_frame = ttk.Frame(self.run_body, style="CardPlain.TFrame")
        self.act = ttk.Treeview(self.act_frame, columns=("what", "detail"), show="tree", selectmode="browse", style="Card.Treeview", height=4)
        self.act.column("#0", width=px(380))
        self.act.column("what", width=px(150), stretch=False)
        self.act.column("detail", width=px(320))
        sb = ttk.Scrollbar(self.act_frame, command=self.act.yview, style="Card.Vertical.TScrollbar")
        self.act.configure(yscrollcommand=sb.set)
        self.act.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.log_frame = ttk.Frame(self.run_body, style="CardPlain.TFrame")
        self.log = tk.Text(self.log_frame, height=4, wrap="none", state="disabled")
        lsb = ttk.Scrollbar(self.log_frame, command=self.log.yview, style="Card.Vertical.TScrollbar")
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side="left", fill="both", expand=True)
        lsb.pack(side="right", fill="y")
        self.act_frame.grid(row=0, column=0, sticky="nsew")

    def _show_runtab(self) -> None:
        if self.v_runtab.get() == "log":
            self.act_frame.grid_remove()
            self.log_frame.grid(row=0, column=0, sticky="nsew")
        else:
            self.log_frame.grid_remove()
            self.act_frame.grid(row=0, column=0, sticky="nsew")

    def toggle_options(self) -> None:
        self.set_options_open(not self.opts_open)

    def _fit_height(self) -> None:
        """Open tall enough to show everything (up to the screen). The window can still be made shorter at any time:
        the work area then scrolls."""
        root = self.root
        root.update_idletasks()
        need = root.winfo_reqheight() - self.scroll.canvas.winfo_reqheight() + self.scroll.inner.winfo_reqheight()
        limit = max(root.winfo_screenheight() - 80, 480)
        have = root.winfo_height() if root.winfo_ismapped() else 0
        if have < need:
            width = root.winfo_width() if root.winfo_ismapped() else min(1240, max(root.winfo_screenwidth() - 60, 900))
            root.geometry("%dx%d" % (width, min(need, limit)))

    def set_options_open(self, show: bool) -> None:
        self.opts_open = show
        if show:
            self.opts.grid()
        else:
            self.opts.grid_remove()
        self._fit_height()

    # ---------------------------------------------------------------------------------------- jobs
    def _save(self) -> None:
        try:
            core.save_store(self.store)
        except OSError as exc:
            messagebox.showerror("Could not save", "Your settings could not be saved:\n%s" % exc, parent=self.root)

    def _job_row(self, job: core.Job) -> Tuple[str, Tuple[str, str], str]:
        if job.last_run:
            ok = job.last_code in (0, 9)
            return job.name, (job.mode, "%s %s" % ("OK" if ok else "FAILED", job.last_run[5:])), "ok" if ok else "bad"
        return job.name, (job.mode, "never run"), "never"

    def refresh_jobs(self, select: str = "") -> None:
        self.jobs.delete(*self.jobs.get_children())
        for job in self.store.jobs:
            name, vals, tag = self._job_row(job)
            self.jobs.insert("", "end", iid=job.id, text=name, values=vals, tags=(tag,))
        if select and self.jobs.exists(select):
            self.jobs.selection_set(select)
            self.jobs.see(select)

    def _job_selected(self, _e: Any = None) -> None:
        sel = self.jobs.selection()
        if not sel or (self.cur and sel[0] == self.cur.id):
            return
        self.commit_form()
        job = next((j for j in self.store.jobs if j.id == sel[0]), None)
        if job:
            self.load_form(job)

    def new_job(self) -> None:
        self.commit_form()
        job = core.Job(name="New job %d" % (len(self.store.jobs) + 1))
        if self.cur:                      # new jobs start with the tuning you used last
            for f in ("disk", "bw_mbps", "bw_percent", "no_bw_limit", "api_low", "no_dir_modtime", "remote"):
                setattr(job, f, getattr(self.cur, f))
        self.store.jobs.append(job)
        self._save()
        self.refresh_jobs(job.id)
        self.load_form(job)

    def duplicate_job(self) -> None:
        if not self.cur:
            return
        self.commit_form()
        dup = copy.deepcopy(self.cur)
        dup.id, dup.name = uuid.uuid4().hex[:12], self.cur.name + " copy"
        dup.last_run = dup.last_mode = dup.last_summary = ""
        dup.last_code = None
        self.store.jobs.append(dup)
        self._save()
        self.refresh_jobs(dup.id)
        self.load_form(dup)

    def delete_job(self) -> None:
        if not self.cur:
            return
        if self.run and self.run.running and self.run.job.id == self.cur.id:
            messagebox.showinfo("Job is running", "Stop the run before deleting this job.", parent=self.root)
            return
        if not messagebox.askyesno("Delete job", "Delete the saved job '%s'?\n\nThis removes only the saved settings. "
                                   "No files are touched, locally or on the remote." % self.cur.name,
                                   default="no", icon="warning", parent=self.root):
            return
        self.store.jobs = [j for j in self.store.jobs if j.id != self.cur.id]
        self.cur = None
        self._save()
        self.refresh_jobs()
        if self.store.jobs:
            self.jobs.selection_set(self.store.jobs[0].id)
        else:
            self.new_job()

    def load_form(self, job: core.Job) -> None:
        self.loading = True
        self.cur = job
        self.v_name.set(job.name)
        self.v_mode.set(job.mode)
        self.v_dest.set(job.dest_kind if job.dest_kind in ("remote", "local") else "remote")
        self.v_source.set(job.source)
        self.v_remote.set(job.remote)
        self.v_target.set(job.target)
        self.v_backup.set(job.backup_root)
        self.v_label.set(job.label)
        self.v_skip.set(job.skip_existing)
        self.v_low.set(job.api_low)
        self.v_nodirtime.set(job.no_dir_modtime)
        self.v_disk.set(job.disk)
        self.v_mbps.set("%g" % job.bw_mbps)
        self.v_pct.set(str(job.bw_percent))
        self.v_nolimit.set(job.no_bw_limit)
        self.v_checkers.set(str(job.checkers))
        self.v_transfers.set(str(job.transfers))
        self.v_depth.set(str(job.list_depth))
        self.loading = False
        self._form_changed()

    def commit_form(self) -> None:
        job = self.cur
        if job is None or self.loading:
            return
        job.name = self.v_name.get().strip() or "Unnamed job"
        job.mode = self.v_mode.get() if self.v_mode.get() in core.MODES else "sync"
        job.source = self.v_source.get().strip().strip('"')
        job.dest_kind = self.v_dest.get() if self.v_dest.get() in ("remote", "local") else "remote"
        job.remote = self.v_remote.get().strip()
        if job.dest_kind == "local":      # full folder paths on this computer, kept as typed
            job.target = self.v_target.get().strip().strip('"')
            job.backup_root = self.v_backup.get().strip().strip('"')
        else:
            job.target = core.norm_remote_path(self.v_target.get())
            job.backup_root = core.norm_remote_path(self.v_backup.get())
        job.label = self.v_label.get().strip()
        job.skip_existing = bool(self.v_skip.get()) and job.mode == "copy"
        job.api_low = bool(self.v_low.get())
        job.no_dir_modtime = bool(self.v_nodirtime.get())
        job.disk = self.v_disk.get() if self.v_disk.get() in ("hdd", "ssd") else "hdd"
        job.bw_mbps = max(_float(self.v_mbps.get(), 30.0), 0.0)
        job.bw_percent = min(max(_int(self.v_pct.get(), 85), 1), 100)
        job.no_bw_limit = bool(self.v_nolimit.get())
        job.checkers = max(_int(self.v_checkers.get(), 0), 0)
        job.transfers = max(_int(self.v_transfers.get(), 0), 0)
        job.list_depth = min(max(_int(self.v_depth.get(), 1), 1), 6)
        self._save()
        if self.jobs.exists(job.id):
            name, vals, tag = self._job_row(job)
            self.jobs.item(job.id, text=name, values=vals, tags=(tag,))

    # ---------------------------------------------------------------------------------------- form
    def _form_changed(self, *_a: Any) -> None:
        if self.loading:
            return
        mode = self.v_mode.get()
        local = self.v_dest.get() == "local"
        self.mode_text.configure(text=MODE_TEXT.get(mode, ""))
        if mode == "sync":
            self.lab_backup.configure(text="Backup folder")
            self.chk_skip.state(["disabled"])
        else:
            self.lab_backup.configure(text="Keep old versions")
            self.chk_skip.state(["!disabled"])
        # a local destination needs no remote, no folder listing and none of the cloud-only tuning
        for widget in (self.lab_remote, self.c_remote, self.btn_refresh):
            if local:
                widget.grid_remove()
            else:
                widget.grid()
        if local:
            self.chk_row.grid_remove()
        else:
            self.chk_row.grid()
            self.space_t.configure(text="")
            self.space_b.configure(text="")
        self.lab_target.configure(text="Destination folder" if local else "Target folder")
        for widget in self.cloud_only:
            widget.state(["disabled"] if local else ["!disabled"])
        self.tune_note.configure(text=("Line speed, API-call and folder-date options apply to cloud remotes only; "
                                       "a local copy keeps folder dates and is not throttled.") if local else
                                 "Folder dates: skips one small call per folder whose date differs; file checking is not affected.")
        label = core.job_label(core.Job(source=self.v_source.get(), label=self.v_label.get(), target=self.v_target.get()))
        if mode == "sync" or self.v_backup.get().strip():
            self.layout_hint.configure(text="Changed or removed files go to  <backup>/%s/<YYYYMMDD-HHMM>/..." % label)
        else:
            self.layout_hint.configure(text="No backup folder: replaced files are overwritten in place.")
        self.btn_exec.configure(text="Execute..." if mode == "sync" else "Copy for real...")
        self._free_space()
        self.refresh_verdicts()

    def _free_space(self) -> None:
        path = self.v_source.get().strip().strip('"')
        try:
            usage = shutil.disk_usage(path) if os.path.isdir(path) else None
        except OSError:
            usage = None
        if usage:
            self.space_bar["value"] = 100.0 * usage.used / max(usage.total, 1)
            self.space_var.set("%s free of %s" % (core.human_bytes(usage.free), core.human_bytes(usage.total)))
        else:
            self.space_bar["value"] = 0
            self.space_var.set("folder not found" if path else "")

    def _set_note(self, text: str, kind: str) -> None:
        self.note_kind = kind
        self.list_hint_text = text
        self.list_note.configure(text=text, foreground=self._tone(kind))

    def _set_verdict(self, label: ttk.Label, verdict: Optional[core.PathVerdict]) -> None:
        if verdict is None or not verdict.path:
            label.configure(text="")
            return
        if verdict.duplicate:
            label.configure(text="✗ two folders with this name exist - rename one in Drive", foreground=self._tone("bad"))
        elif verdict.state == "exists":
            label.configure(text="✓ exists on the remote", foreground=self._tone("ok"))
        elif verdict.state == "missing":
            near = "  (similar name: '%s' - typo?)" % verdict.near if verdict.near else ""
            label.configure(text="⚠ not found - will be created on the first run%s" % near, foreground=self._tone("warn"))
        else:
            label.configure(text="• deeper than the listing - raise the depth and check again", foreground=self._tone("muted"))

    def refresh_verdicts(self) -> None:
        remote = self.v_remote.get().strip()
        mode = self.v_mode.get()
        if self.v_dest.get() == "local":
            self._refresh_local_verdicts(mode)
            return
        target = core.norm_remote_path(self.v_target.get())
        backup = core.norm_remote_path(self.v_backup.get())
        if not remote or self.dirs_remote != remote or not self.dirs_time:
            note = "• not checked yet (press Check folders)" if (target or backup) and remote else ""
            self.verdict_t.configure(text=note if target else "", foreground=self._tone("muted"))
            self.verdict_b.configure(text=note if backup else "", foreground=self._tone("muted"))
            return
        self._set_verdict(self.verdict_t, core.check_path(target, self.dirs, self.dirs_depth) if target else None)
        if backup and (mode == "sync" or backup):
            self._set_verdict(self.verdict_b, core.check_path(backup, self.dirs, self.dirs_depth))
        else:
            self.verdict_b.configure(text="")
        if target and backup and core.paths_overlap(target, backup):
            self.verdict_b.configure(text="✗ must be separate from the target folder (not inside it, not the same)",
                                     foreground=self._tone("bad"))

    def _refresh_local_verdicts(self, mode: str) -> None:
        source = self.v_source.get().strip().strip('"')
        target = self.v_target.get().strip().strip('"')
        backup = self.v_backup.get().strip().strip('"')

        def verdict(label: ttk.Label, path: str, what: str) -> None:
            if not path:
                label.configure(text="")
            elif not os.path.isabs(path):
                label.configure(text="✗ needs a full folder path", foreground=self._tone("bad"))
            elif source and core.local_overlap(source, path):
                label.configure(text="✗ must not be inside, or contain, the source folder", foreground=self._tone("bad"))
            elif what == "backup" and target and os.path.isabs(target) and core.local_overlap(target, path):
                label.configure(text="✗ must be separate from the destination (not inside it, not the same)", foreground=self._tone("bad"))
            elif os.path.isdir(path):
                label.configure(text="✓ exists", foreground=self._tone("ok"))
            else:
                label.configure(text="⚠ not found - will be created on the first run", foreground=self._tone("warn"))
        verdict(self.verdict_t, target, "target")
        verdict(self.verdict_b, backup if (mode == "sync" or backup) else "", "backup")
        self.space_t.configure(text=self._free_text(target))
        self.space_b.configure(text=self._free_text(backup) if (mode == "sync" or backup) else "")

    @staticmethod
    def _free_text(path: str) -> str:
        """Free space of the drive that holds this folder (or the folder it would be created in)."""
        if not path or not os.path.isabs(path):
            return ""
        probe = path
        while probe and not os.path.exists(probe):
            parent = os.path.dirname(probe)
            if parent == probe:
                return ""
            probe = parent
        try:
            usage = shutil.disk_usage(probe)
        except OSError:
            return ""
        return "%s free of %s" % (core.human_bytes(usage.free), core.human_bytes(usage.total))

    # ---------------------------------------------------------------------------------------- disk type
    def _source_edited(self, *_a: Any) -> None:
        """The source folder changed: after a short pause, find out whether it lives on an SSD or an HDD."""
        if self.loading:
            return
        if self._disk_timer is not None:
            try:
                self.root.after_cancel(self._disk_timer)
            except tk.TclError:
                pass
        self._disk_timer = self.root.after(700, self._detect_disk)

    def _detect_disk(self) -> None:
        self._disk_timer = None
        path = self.v_source.get().strip().strip('"')
        if not path or not os.path.isdir(path):
            return

        def work() -> None:        # opening a sleeping disk can take a moment, so never on the window's thread
            self.events.put(("disk", (path, core.detect_disk_kind(path))))
        threading.Thread(target=work, daemon=True).start()

    def pick(self, which: str) -> None:
        """'Pick...' next to a folder box: a folder dialog for a local destination, the remote's folder list otherwise."""
        if self.v_dest.get() != "local":
            self.open_picker(which)
            return
        var = self.v_backup if which == "backup" else self.v_target
        start = var.get().strip()
        chosen = filedialog.askdirectory(parent=self.root, title="Choose the %s folder" % ("backup" if which == "backup" else "destination"),
                                         initialdir=start if os.path.isdir(start) else None)
        if chosen:
            var.set(os.path.normpath(chosen))

    def browse_source(self) -> None:
        start = self.v_source.get().strip()
        picked = filedialog.askdirectory(parent=self.root, title="Choose the local folder",
                                         initialdir=start if os.path.isdir(start) else None, mustexist=True)
        if picked:
            self.v_source.set(os.path.normpath(picked))

    def _dropped(self, event: Any) -> None:
        items = self.root.tk.splitlist(event.data)
        if items:
            path = items[0]
            self.v_source.set(os.path.normpath(path if os.path.isdir(path) else os.path.dirname(path)))

    # ---------------------------------------------------------------------------------------- remote
    def refresh_remotes(self) -> None:
        if not self.rclone:
            self.c_remote.configure(values=[])
            return
        rclone = self.rclone

        def work() -> None:
            try:
                self.events.put(("remotes", core.list_remotes(rclone)))
            except core.RcloneError as exc:
                self.events.put(("remotes_err", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def list_folders(self, force: bool = False) -> None:
        remote = self.v_remote.get().strip()
        if not self.rclone:
            messagebox.showerror("rclone not found", "Install rclone or set its path under File > Settings.", parent=self.root)
            return
        if not remote:
            messagebox.showinfo("Choose a remote", "Choose a remote first.", parent=self.root)
            return
        depth = min(max(_int(self.v_depth.get(), 1), 1), 6)
        self.btn_check.state(["disabled"])
        self._set_note("Listing %s: ..." % remote, "muted")
        rclone = self.rclone

        def work() -> None:
            try:
                self.events.put(("dirs", (remote, depth, core.list_dirs(rclone, remote, depth), "")))
            except core.RcloneError as exc:
                self.events.put(("dirs", (remote, depth, [], str(exc))))
        threading.Thread(target=work, daemon=True).start()

    def open_picker(self, which: str) -> Optional[FolderPicker]:
        if not self.v_remote.get().strip():
            messagebox.showinfo("Choose a remote", "Choose a remote first.", parent=self.root)
            return None
        if self.picker is not None and self.picker.winfo_exists():
            self.picker.destroy()
        fresh = (self.dirs_remote == self.v_remote.get().strip() and self.dirs_time and time.time() - self.dirs_time < 900)
        self.picker = FolderPicker(self, which)
        if not fresh:
            self.list_folders(force=True)
        return self.picker

    # ---------------------------------------------------------------------------------------- running
    def _banner(self, kind: str, text: str) -> None:
        self.banner_kind = kind
        bg, fg = self.pal["b_" + kind].split("|")
        stripe = {"idle": self.pal["border_strong"], "run": self.pal["gold"], "ok": self.pal["success"],
                  "warn": self.pal["warn"], "bad": self.pal["error"]}[kind]
        self.banner.configure(text=text, bg=bg, fg=fg, font=self.theme.f_ui)
        self.banner_stripe.configure(bg=stripe)

    def _set_running(self, running: bool) -> None:
        for btn in (self.btn_dry, self.btn_exec):
            btn.state(["disabled"] if running else ["!disabled"])
        self.btn_stop.state(["!disabled"] if running else ["disabled"])

    def start(self, real: bool) -> None:
        if self.run and self.run.running:
            return
        self.commit_form()
        job = self.cur
        if job is None:
            return
        problems = core.validate_job(job, self.rclone)
        if problems:
            messagebox.showwarning("Check the setup", "\n\n".join(problems), parent=self.root)
            return
        self.btn_execute_now.pack_forget()
        if core.is_local(job):                      # local folders are checked directly: no listing, no remote
            self._confirm_and_launch(real, self._local_notes(job))
            return
        # one listing verifies target and backup folders; reuse a recent one to spare the API
        fresh = (self.dirs_remote == job.remote and self.dirs_time and time.time() - self.dirs_time < 900)
        if fresh:
            self._continue_start(real)
        else:
            self.pending = real
            self._banner("run", "Checking the folders on the remote (one listing)...")
            self._set_running(True)
            self.btn_stop.state(["disabled"])
            self.list_folders(force=True)

    def _continue_start(self, real: bool) -> None:
        job = self.cur
        assert job is not None
        target, backup, blocking = core.verify_against_listing(job, self.dirs, self.dirs_depth)
        if blocking:
            self._set_running(False)
            self._banner("bad", "Not started: " + blocking[0])
            messagebox.showerror("Cannot continue", "\n\n".join(blocking), parent=self.root)
            return
        notes = []
        for what, verdict in (("target folder", target), ("backup folder", backup)):
            if verdict and verdict.state == "missing":
                near = " (there is a similar name '%s' - check for a typo)" % verdict.near if verdict.near else ""
                notes.append("The %s '%s' does not exist on the remote yet%s. It will be created." % (what, verdict.path, near))
        self._confirm_and_launch(real, notes)

    def _local_notes(self, job: core.Job) -> List[str]:
        notes = []
        for what, path in (("destination folder", job.target), ("backup folder", job.backup_root if core.uses_backup(job) else "")):
            if path.strip() and not os.path.isdir(path):
                notes.append("The %s '%s' does not exist yet. It will be created." % (what, path))
        return notes

    def _confirm_and_launch(self, real: bool, notes: List[str]) -> None:
        job = self.cur
        assert job is not None
        if notes and not messagebox.askyesno("Folder not found", "\n\n".join(notes) + "\n\nContinue?",
                                             default="no", icon="warning", parent=self.root):
            self._set_running(False)
            self._banner("idle", "Cancelled. Nothing was changed.")
            return
        if real:
            where = "the destination folder" if core.is_local(job) else "the remote"
            what = ("This will make %s match your source folder. Changed and deleted files are moved into the "
                    "backup folder first." % where if job.mode == "sync" else
                    "This will copy new and changed files. Nothing in %s is deleted." % where)
            dlg = ExecuteDialog(self, "%s\n\n%s  ->  %s" % (what, job.source, core.dest_spec(job)))
            self.root.wait_window(dlg)
            if not dlg.result:
                self._set_running(False)
                self._banner("idle", "Cancelled. Nothing was changed.")
                return
        self._launch(real)

    def _launch(self, real: bool) -> None:
        job = self.cur
        assert job is not None and self.rclone
        self.act.delete(*self.act.get_children())
        self.activity_rows = self.log_lines = 0
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(14)
        self.stats_var.set("")
        self.now_var.set("")
        self.btn_log.state(["disabled"])
        run = core.SyncRun(self.rclone, job, real, self.events)
        try:
            run.start()
        except core.RunBusy as exc:
            self._set_running(False)
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
            self._banner("warn", str(exc))
            return
        except Exception as exc:  # could not start rclone at all
            self._set_running(False)
            self.progress.stop()
            self.progress.configure(mode="determinate", value=0)
            self._banner("bad", "Could not start rclone: %s" % exc)
            return
        self.run = run
        self.run_started = time.time()
        self._set_running(True)
        self._banner("run", "%s running..." % ("REAL RUN" if real else "Dry run (nothing is changed)"))

    def stop(self) -> None:
        if self.run and self.run.running:
            self._banner("warn", "Stopping...")
            self.run.stop()

    def open_log(self) -> None:
        if self.run and self.run.log_path and os.path.exists(self.run.log_path):
            self._open(self.run.log_path)

    def _open(self, path: str) -> None:
        try:
            if not os.path.splitext(path)[1]:
                os.makedirs(path, exist_ok=True)
            core.open_path(path)
        except OSError as exc:
            messagebox.showerror("Could not open", str(exc), parent=self.root)

    def copy_command(self) -> None:
        self.commit_form()
        job = self.cur
        if not job or not self.rclone:
            return
        text = core.command_text(self.rclone, core.build_args(job, False, time.strftime("%Y%m%d-%H%M"), for_script=True))
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self._banner("idle", "Copied the dry-run command to the clipboard. Remove --dry-run to run it for real.")

    def export_script(self) -> None:
        self.commit_form()
        job = self.cur
        if not job:
            return
        problems = [p for p in core.validate_job(job, self.rclone) if "rclone was not found" not in p]
        if problems:
            messagebox.showwarning("Check the setup", "\n\n".join(problems), parent=self.root)
            return
        name, text = core.export_script(job, self.rclone or "rclone")
        ext = os.path.splitext(name)[1]
        path = filedialog.asksaveasfilename(parent=self.root, title="Export script", initialfile=name, defaultextension=ext,
                                            filetypes=[("Script", "*" + ext), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "wb") as fh:
                fh.write(text.encode("utf-8"))
            if not core.IS_WIN:
                os.chmod(path, 0o755)
        except OSError as exc:
            messagebox.showerror("Could not write", str(exc), parent=self.root)
            return
        self._banner("ok", "Exported %s. It does a dry run unless you add %s." % (path, "-Execute" if core.IS_WIN else "--execute"))

    # ---------------------------------------------------------------------------------------- events
    def poll(self) -> None:
        try:
            for _ in range(400):
                kind, payload = self.events.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        try:
            self._poll_id = self.root.after(100, self.poll)
        except tk.TclError:   # window already destroyed
            pass

    def _handle(self, kind: str, payload: Any) -> None:
        if kind == "remotes":
            self.remotes = payload
            names = [n for n, _t in payload]
            self.c_remote.configure(values=names)
            if self.v_remote.get() not in names and names and not self.v_remote.get():
                self.v_remote.set(names[0])
            self._status_bar()
        elif kind == "version":
            self.rclone_ver = payload
            self._status_bar()
        elif kind == "disk":
            path, found = payload
            if path != self.v_source.get().strip().strip('"'):
                return                          # the folder changed again while we were asking
            if found in ("ssd", "hdd"):
                self.v_disk.set(found)
                self.disk_note.configure(text="Detected automatically: %s" % ("SSD" if found == "ssd" else "HDD (gentle reads)"))
            else:
                self.disk_note.configure(text="Could not tell (external USB drives often hide it): choose HDD or SSD yourself")
        elif kind == "remotes_err":
            self.status.configure(text="Could not read the remotes list: %s" % payload, foreground=self._tone("bad"))
        elif kind == "dirs":
            remote, depth, dirs, err = payload
            self.btn_check.state(["!disabled"])
            if err:
                self._set_note(err, "bad")
                if self.pending is not None:
                    self.pending = None
                    self._set_running(False)
                    self._banner("bad", "Not started: " + err)
                return
            self.dirs, self.dirs_remote, self.dirs_depth, self.dirs_time = dirs, remote, depth, time.time()
            self._set_note("%d folder(s) listed, depth %d" % (len(dirs), depth), "muted")
            if self.picker is not None and self.picker.winfo_exists():
                self.picker.refresh()
            self.refresh_verdicts()
            if self.pending is not None:
                real, self.pending = self.pending, None
                self._set_running(False)
                if self.v_remote.get().strip() == remote:
                    self._continue_start(real)
        elif kind == "started":
            self.btn_log.state(["!disabled"])
        elif kind == "stats":
            self._stats(payload)
        elif kind == "activity":
            self._activity(payload)
        elif kind == "log":
            self._log(payload)
        elif kind == "done":
            self._done(payload["result"], payload.get("stats") or {})

    def _stats(self, s: Dict[str, Any]) -> None:
        total, done = s.get("totalBytes") or 0, s.get("bytes") or 0
        if total > 0:
            if str(self.progress.cget("mode")) != "determinate":
                self.progress.stop()
                self.progress.configure(mode="determinate")
            self.progress["value"] = min(100.0, 100.0 * done / total)
        self.stats_var.set("%s / %s   %s/s   ETA %s   |   checks %s/%s   transfers %s/%s   errors %s   |   elapsed %s" % (
            core.human_bytes(done), core.human_bytes(total), core.human_bytes(s.get("speed") or 0),
            core.human_eta(s.get("eta")), s.get("checks", 0), s.get("totalChecks", 0), s.get("transfers", 0),
            s.get("totalTransfers", 0), s.get("errors", 0), core.human_eta(s.get("elapsedTime", 0))))
        moving = s.get("transferring") or []
        checking = s.get("checking") or []
        if moving:
            first = moving[0]
            extra = " (+%d more)" % (len(moving) - 1) if len(moving) > 1 else ""
            self.now_var.set("Uploading: %s  %s%%%s" % (first.get("name", ""), first.get("percentage", 0), extra))
        elif checking:
            extra = " (+%d more)" % (len(checking) - 1) if len(checking) > 1 else ""
            self.now_var.set("Checking: %s%s   (large files are hashed here; no byte progress is reported)" % (checking[0], extra))
        else:
            self.now_var.set("")

    def _activity(self, a: Dict[str, Any]) -> None:
        if self.activity_rows >= 20000:
            return
        self.activity_rows += 1
        names = {"upload": "upload", "backup": "to backup", "replace": "old version to backup",
                 "modtime": "timestamp fix", "delete": "delete", "error": "ERROR"}
        self.act.insert("", "end", text=a["path"] or "(general)", values=(names.get(a["kind"], a["kind"]), a["detail"]),
                        tags=(a["kind"],))
        self.act.yview_moveto(1.0)

    def _log(self, rec: Dict[str, str]) -> None:
        self.log_lines += 1
        if self.log_lines > 6000:
            return
        self.log.configure(state="normal")
        self.log.insert("end", rec["text"] + "\n", (rec.get("level", "info"),))
        self.log.configure(state="disabled")
        self.log.yview_moveto(1.0)

    def _done(self, res: core.RunResult, stats: Dict[str, Any]) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress["value"] = 100 if res.code in (0, 9) and not res.stopped else self.progress["value"]
        self.now_var.set("")
        self._set_running(False)
        self.last_result = res
        job = self.run.job if self.run else self.cur
        if job:
            job.last_run = time.strftime("%Y-%m-%d %H:%M")
            job.last_mode = "run" if res.real else "dry run"
            job.last_code = res.code
            job.last_summary = res.summary
            self._save()
            if self.jobs.exists(job.id):
                name, vals, tag = self._job_row(job)
                self.jobs.item(job.id, text=name, values=vals, tags=(tag,))
        took = core.human_eta(res.elapsed)
        tail = "\nexit code %s: %s   |   %s" % (res.code, res.meaning, took)
        if res.stopped:
            self._banner("warn", "Stopped by you. Whatever finished before that is kept; unfinished uploads are redone next run." + tail)
        elif res.code in (0, 9):
            if res.real:
                self._banner("ok", "Finished: %s.%s" % (res.summary, tail))
            else:
                self._banner("ok", "Dry run finished, nothing was changed. Would do: %s.%s" % (res.summary, tail))
                self.btn_execute_now.pack(side="left", padx=(10, 0))
        elif res.code in (5, 6):
            self._banner("warn", "Finished with problems: %s.%s" % (res.summary, tail))
        else:
            first = ("\n" + res.errors[0]) if res.errors else ""
            self._banner("bad", "Failed: %s.%s%s" % (res.summary, tail, first))

    # ---------------------------------------------------------------------------------------- misc
    def _load_version(self) -> None:
        """`rclone version` starts a program, which can take a moment: never do it on the window's own thread."""
        if not self.rclone:
            return
        rclone = self.rclone

        def work() -> None:
            self.events.put(("version", core.rclone_version(rclone)))
        threading.Thread(target=work, daemon=True).start()

    def _status_bar(self) -> None:
        if self.rclone:
            self.status.configure(text="%s   |   %d remote(s)   |   data: %s" % (self.rclone_ver or self.rclone, len(self.remotes), core.config_dir()),
                                  foreground=self._tone("muted"))
        else:
            self.status.configure(text="rclone was not found. Install it, or set its path under File > Settings.",
                                  foreground=self._tone("bad"))

    def open_settings(self) -> None:
        dlg = Dialog(self, "Settings")
        ttk.Label(dlg.body, text="rclone program", style="Head.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(dlg.body, text="Leave empty to find it automatically.", style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w")
        var = tk.StringVar(value=str(self.store.settings.get("rclone", "")))
        ttk.Entry(dlg.body, textvariable=var, width=58).grid(row=2, column=0, columnspan=2, sticky="ew", pady=8)

        def browse() -> None:
            p = filedialog.askopenfilename(parent=dlg, title="Choose the rclone program")
            if p:
                var.set(p)
        ttk.Button(dlg.body, text="Browse...", command=browse).grid(row=2, column=2, padx=(8, 0))
        info = ttk.Label(dlg.body, text="", style="Muted.TLabel")
        info.grid(row=3, column=0, columnspan=3, sticky="w")

        def apply() -> None:
            found = core.find_rclone(var.get().strip())
            if not found:
                info.configure(text="rclone not found there.", foreground=self._tone("bad"))
                return
            self.store.settings["rclone"] = var.get().strip()
            self._save()
            self.rclone = found
            self.rclone_ver = ""
            self.refresh_remotes()
            self._load_version()
            self._status_bar()
            dlg.destroy()
        row = ttk.Frame(dlg.body)
        row.grid(row=4, column=0, columnspan=3, sticky="e", pady=(16, 0))
        ttk.Button(row, text="Cancel", command=dlg.destroy).pack(side="right", padx=8)
        ttk.Button(row, text="Save", style="Accent.TButton", command=apply).pack(side="right")
        dlg.present()

    def _callback_exception(self, exc: Any, val: Any, tb: Any) -> None:
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            core.config_dir().mkdir(parents=True, exist_ok=True)
            with open(core.config_dir() / "crash.log", "a", encoding="utf-8") as fh:
                fh.write("%s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text))
        except OSError:
            pass
        messagebox.showerror("Unexpected error", "Something went wrong:\n\n%s\n\nDetails were saved to crash.log in the data folder." % val,
                             parent=self.root)

    def _kill_child(self) -> None:
        if self.run:
            self.run.kill()

    def on_close(self) -> None:
        if self.closing:
            return
        if self.run and self.run.running:
            if not messagebox.askyesno("A job is running", "A run is still in progress. Stop it and quit?",
                                       default="no", icon="warning", parent=self.root):
                return
            self.closing = True
            self._banner("warn", "Stopping rclone before closing...")
            self.run.stop()
            self._wait_then_quit(time.time())
            return
        self.commit_form()
        self._destroy()

    def _wait_then_quit(self, since: float) -> None:
        if self.run and self.run.running and time.time() - since < 10:
            self.root.after(200, lambda: self._wait_then_quit(since))
            return
        self._kill_child()
        self.commit_form()
        self._destroy()

    def _destroy(self) -> None:
        for timer in (self._poll_id, self._disk_timer):
            if timer:
                try:
                    self.root.after_cancel(timer)
                except tk.TclError:
                    pass
        self.root.destroy()


def make_root() -> tk.Tk:
    if core.IS_WIN:
        try:  # crisp text on high-DPI screens
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # type: ignore[attr-defined]
        except Exception:
            pass
    return TkinterDnD.Tk() if HAVE_DND else tk.Tk()  # type: ignore[name-defined]


def main() -> None:
    root = make_root()
    root.withdraw()              # build off screen; Tk's first paint of ~100 widgets takes a moment
    App(root)
    root.update_idletasks()
    root.deiconify()             # ...and show the window only when it is complete
    root.mainloop()
