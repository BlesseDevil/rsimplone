# Copyright (C) 2026 Mehedi Maruf
# SPDX-License-Identifier: AGPL-3.0-or-later
# Part of rclone-sync-gui; see rsg_core.py for the full licence notice and contact details.
"""Drives the real window against a throwaway local remote and checks the files afterwards.
    python tests/smoke_gui.py [--hold SECONDS] [--geometry-file PATH]
It opens a window on screen for a few seconds."""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rsg import core  # noqa: E402

tmp = tempfile.TemporaryDirectory()
root_dir = Path(tmp.name)
os.environ["RSG_HOME"] = str(root_dir / "home")
(root_dir / "remote" / "dest").mkdir(parents=True)
(root_dir / "remote" / "bk").mkdir()
os.environ["RCLONE_CONFIG_SMOKE_TYPE"] = "alias"
os.environ["RCLONE_CONFIG_SMOKE_REMOTE"] = str(root_dir / "remote")
src = root_dir / "src"
(src / "sub").mkdir(parents=True)
(src / "new.txt").write_text("new")
(src / "changed.txt").write_text("changed-new-content")
(src / "sub" / "in.txt").write_text("in")
(root_dir / "remote" / "dest" / "changed.txt").write_text("old")
(root_dir / "remote" / "dest" / "gone.txt").write_text("gone")

import tkinter as tk  # noqa: E402
from rsg import gui as rsg_gui  # noqa: E402

fails = []


def check(cond, what):
    print(("ok    " if cond else "FAIL  ") + what)
    if not cond:
        fails.append(what)


answers = []
rsg_gui.messagebox.askyesno = lambda *a, **k: (answers.append(a[:2]) or True)
rsg_gui.messagebox.showwarning = lambda *a, **k: answers.append(("warning", a[1]))
rsg_gui.messagebox.showerror = lambda *a, **k: answers.append(("error", a[1]))


class AutoDialog:
    def __init__(self, parent, text, pal=None):
        self.result = True
        self.text = text


rsg_gui.ExecuteDialog = AutoDialog
rsg_gui.tk.Toplevel  # sanity: attribute exists

root = rsg_gui.make_root()
root.wait_window = lambda w: None   # the fake confirmation dialog above is not a real window
app = rsg_gui.App(root)
hold = 0.0
geom_file = ""
if "--theme" in sys.argv:
    app.set_theme(sys.argv[sys.argv.index("--theme") + 1], save=False)
check(app.logo is not None, "brand logo loaded from assets")
first_row = app.act.get_children()[0] if app.act.get_children() else ""
check(first_row and app.act.item(first_row, "text") == rsg_gui.HINT, "the startup activity box carries the hint")
check(not app.btn_check.winfo_ismapped(), "the Check folders button is tucked away in the options")
check(root.minsize()[1] < 600, "the window can be made short (the work area scrolls)")
check("rSimpLone" in root.title(), "the window carries the rSimpLone brand")
check(rsg_gui.CONTACT in rsg_gui.JOKE and rsg_gui.LICENSE_CONTACT in rsg_gui.JOKE, "the joke names both contact addresses")
check(str(app.btn_dry.cget("style")) == "Accent.TButton" and str(app.btn_exec.cget("style")) == "Danger.TButton",
      "dry run is the gold action, execute the crimson one")
if "--hold" in sys.argv:
    hold = float(sys.argv[sys.argv.index("--hold") + 1])
if "--geometry-file" in sys.argv:
    geom_file = sys.argv[sys.argv.index("--geometry-file") + 1]


def pump(seconds, until=None):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        if until and until():
            return True
        time.sleep(0.03)
    return until() if until else True


# --- fill the form like a user would -----------------------------------------------------------
check(pump(15, lambda: any(n == "smoke" for n, _t in app.remotes)), "remotes list contains the test remote")
app.v_name.set("Smoke job")
app.v_source.set(str(src))
app.v_remote.set("smoke")
app.v_target.set("dest")
app.v_backup.set("bk")
pump(0.3)
check("not checked" in app.verdict_t.cget("text"), "verdict says not checked before listing")
app.list_folders(force=True)
check(pump(20, lambda: app.dirs_time > 0), "folder listing arrived")
check(sorted(app.dirs) == ["bk", "dest"], "listing content is bk + dest")
check("exists" in app.verdict_t.cget("text") and "exists" in app.verdict_b.cget("text"), "both folders verified as existing")
pk = app.open_picker("target")
check(pk is not None and pump(5, lambda: len(pk.tree.get_children()) == 2), "folder picker shows the two folders")
dest_iid = next(i for i, pth in pk.paths.items() if pth == "dest")
pk.tree.selection_set(dest_iid)
app.v_target.set("")
pk.use()
pump(0.3)
check(app.v_target.get() == "dest", "picking a folder fills the target field")
check(not pk.winfo_exists(), "picker closes after choosing")
app.v_target.set("DEST")
pump(0.3)
check("similar name" in app.verdict_t.cget("text") or "not found" in app.verdict_t.cget("text"), "wrong-case target flagged")
app.v_target.set("dest")
pump(0.3)

# --- dry run -----------------------------------------------------------------------------------
before = (root_dir / "remote" / "dest" / "changed.txt").read_text()
app.start(False)
check(pump(40, lambda: app.last_result is not None), "dry run finished")
res = app.last_result
check(res.code == 0 and not res.real, "dry run exit code 0")
check((root_dir / "remote" / "dest" / "changed.txt").read_text() == before, "dry run left the remote untouched")
check("Dry run finished" in app.banner.cget("text"), "banner reports the dry run")
check(app.activity_rows >= 3, "activity table was filled")
check(str(app.btn_execute_now.winfo_manager()) == "pack", "'Execute now' button appears after a dry run")

# --- real sync ---------------------------------------------------------------------------------
app.last_result = None
app.start(True)
check(pump(40, lambda: app.last_result is not None), "real sync finished")
check(app.last_result.code == 0 and app.last_result.real, "real sync exit code 0")
check((root_dir / "remote" / "dest" / "changed.txt").read_text() == "changed-new-content", "changed file replaced")
check(not (root_dir / "remote" / "dest" / "gone.txt").exists(), "deleted file gone from destination")
kept = {p.name: p.read_text() for p in (root_dir / "remote" / "bk").rglob("*") if p.is_file()}
check(kept == {"changed.txt": "old", "gone.txt": "gone"}, "old and deleted files kept with their old content")
check(app.cur.last_code == 0 and app.cur.last_mode == "run", "job remembers its last run")
check(core.load_store().jobs[0].last_code == 0, "last run saved to disk")
check("Finished" in app.banner.cget("text"), "banner reports success")

# --- switch to copy mode, add a file, make sure nothing is deleted ----------------------------------
(src / "another.txt").write_text("another")
(src / "changed.txt").unlink()
app.v_mode.set("copy")
pump(0.3)
check(str(app.chk_skip.state()) .find("disabled") == -1, "skip-existing checkbox enabled in copy mode")
app.last_result = None
app.start(True)
check(pump(40, lambda: app.last_result is not None), "real copy finished")
check((root_dir / "remote" / "dest" / "another.txt").read_text() == "another", "copy uploaded the new file")
check((root_dir / "remote" / "dest" / "changed.txt").exists(), "copy did NOT delete a file removed locally")

# --- options panel and theme toggle ----------------------------------------------------------------------
check(not app.opts.winfo_ismapped(), "options are collapsed by default")
app.set_options_open(True)
pump(0.3)
check(app.opts.winfo_ismapped(), "options expand on request")
check(app.btn_check.winfo_ismapped(), "Check folders is available inside the options")
root.geometry("1240x520")
pump(0.6)
check(app.scroll.vsb.winfo_ismapped(), "a scrollbar appears when the window is made short")
app.scroll.canvas.yview_moveto(1.0)
pump(0.3)
check(app.scroll.canvas.yview()[0] > 0, "the work area scrolls")
app.scroll.canvas.yview_moveto(0.0)
app.set_options_open(False)
root.geometry("1240x%d" % min(1000, root.winfo_screenheight() - 110))
pump(0.5)

# --- contact dev / about ------------------------------------------------------------------------------------
before_windows = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
app.about()
pump(0.3)
shown = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w not in before_windows]
check(len(shown) == 1 and "About rSimpLone" in shown[0].title(), "the About window opens")
for w in shown:
    w.destroy()
rsg_gui.webbrowser.open = lambda url, *a, **k: opened_urls.append(url)
opened_urls = []
app.email_dev()
check(opened_urls and opened_urls[0].startswith("mailto:rsimplone@mehedimaruf.com"), "the e-mail button writes to the developer")

# --- disk type detection -------------------------------------------------------------------------------------
src_text = app.v_source.get().strip()
app._handle("disk", (src_text, "hdd"))
check(app.v_disk.get() == "hdd" and "HDD" in app.disk_note.cget("text"), "a detected HDD selects the HDD tuning")
app._handle("disk", (src_text, "ssd"))
check(app.v_disk.get() == "ssd" and "SSD" in app.disk_note.cget("text"), "a detected SSD selects the SSD tuning")
app._handle("disk", (src_text, None))
check(app.v_disk.get() == "ssd" and "Could not tell" in app.disk_note.cget("text"), "an unknown disk leaves your choice alone and says so")
app._handle("disk", ("somewhere-else", "hdd"))
check(app.v_disk.get() == "ssd", "an answer for a folder you already moved away from is ignored")
app.v_disk.set("hdd")
want_theme = sys.argv[sys.argv.index("--theme") + 1] if "--theme" in sys.argv else "auto"
app.set_theme("auto", save=False)
seq = []
t0 = time.time()
for _ in range(4):
    app.cycle_theme()
    pump(0.1)
    seq.append(app.theme_choice)
check(seq == ["light", "dark", "auto", "light"], "clicking the logo cycles light, dark, system")
check(time.time() - t0 < 4.0, "theme switching is quick (%.2fs for four switches)" % (time.time() - t0))
check(core.load_store().settings.get("theme") == "light", "chosen theme is remembered")
check(app.pal["bg"] == rsg_gui.PALETTES[app.theme.name]["bg"], "palette follows the chosen theme")
app.set_theme(want_theme, save=False)
pump(0.2)
check(app.logo_label.cget("cursor") == "hand2", "the logo is the (unlabelled) theme button")

# --- the logo and the copyright line ---------------------------------------------------------------------
opened = []
rsg_gui.webbrowser.open = lambda url, *a, **k: opened.append(url)
app.set_theme("auto", save=False)
app.logo_clicks = 0
for _ in range(3):
    app._logo_click()
    pump(0.1)
check(app.theme_choice == "auto" and not opened, "three logo clicks go round the themes and open nothing")
app._logo_click()
pump(0.1)
check(opened == ["https://mehedimaruf.com"], "the fourth logo click opens the website")
app.open_site()
check(len(opened) == 2, "clicking the copyright line opens the website")
app._hint()
check(app.status.cget("text") == rsg_gui.HINT, "hovering the logo or the copyright shows the hint")
app.set_theme(want_theme, save=False)
pump(0.2)

# --- local destination: a folder on this computer instead of a cloud remote ----------------------------------
(src / "changed.txt").write_text("changed-new-content")    # it was deleted from the source in the copy test above
(root_dir / "ldest").mkdir()
(root_dir / "ldest" / "changed.txt").write_text("old-local")
(root_dir / "ldest" / "stale.txt").write_text("stale-local")
app.v_mode.set("sync")
app.v_dest.set("local")
pump(0.3)
check(not app.c_remote.winfo_ismapped(), "remote picker is hidden for a local destination")
app.v_target.set(str(root_dir / "ldest"))
app.v_backup.set(str(root_dir / "lbk"))
pump(0.3)
check("exists" in app.verdict_t.cget("text"), "existing local destination shows as existing")
check("not found" in app.verdict_b.cget("text"), "missing local backup folder shows it will be created")
check("free of" in app.space_t.cget("text") and "free of" in app.space_b.cget("text"), "free space is shown on the destination and backup rows")
app.v_target.set(str(src / "inside"))
pump(0.3)
check("inside" in app.verdict_t.cget("text") or "contain" in app.verdict_t.cget("text"), "destination inside the source is flagged")
app.start(False)
check(answers and answers[-1][0] == "warning", "destination inside the source is refused")
app.v_target.set(str(root_dir / "ldest"))
pump(0.3)
app.last_result = None
app.start(False)
check(pump(40, lambda: app.last_result is not None) and app.last_result.code == 0, "local dry run finished")
check((root_dir / "ldest" / "changed.txt").read_text() == "old-local", "local dry run changed nothing")
app.last_result = None
app.start(True)
check(pump(40, lambda: app.last_result is not None) and app.last_result.code == 0, "local sync finished")
check((root_dir / "ldest" / "changed.txt").read_text() == "changed-new-content", "local sync replaced the changed file")
check((root_dir / "ldest" / "sub" / "in.txt").read_text() == "in", "local sync copied a nested file")
check(not (root_dir / "ldest" / "stale.txt").exists(), "local sync removed the file that is gone from the source")
kept_local = {p.name: p.read_text() for p in (root_dir / "lbk").rglob("*") if p.is_file()}
check(kept_local.get("stale.txt") == "stale-local" and kept_local.get("changed.txt") == "old-local", "old and removed files kept in the local backup folder")
check(core.load_store().jobs[0].dest_kind == "local", "destination type is saved with the job")
app.v_dest.set("remote")
pump(0.3)
check(app.c_remote.winfo_ismapped(), "remote picker comes back for a cloud destination")
app.v_target.set("dest")
app.v_backup.set("bk")
pump(0.2)

# --- folder-date option is its own checkbox and is saved ------------------------------------------------
check(app.cur.no_dir_modtime is False, "folder dates option is off by default")
app.v_nodirtime.set(True)
app.v_low.set(True)
app.commit_form()
saved = core.load_store().jobs[0]
check(saved.no_dir_modtime is True and saved.api_low is True, "folder dates option saved independently of 'fewest API calls'")
app.v_nodirtime.set(False)

# --- validation messages ------------------------------------------------------------------------
app.v_target.set("")
app.start(False)
check(answers and answers[-1][0] == "warning", "empty target refused with a warning")
app.v_target.set("dest")

# --- closing leaves no rclone child behind -----------------------------------------------------------
if hold:
    if "--tab" in sys.argv:
        app.set_options_open(sys.argv[sys.argv.index("--tab") + 1] == "1")
    root.attributes("-topmost", True)   # keep other windows from covering the window while it is photographed
    root.lift()
    root.update()
    must_fit = [app.btn_dry, app.btn_exec, app.btn_stop] + ([] if app.opts_open else [app.banner, app.btn_log])
    clipped = [w for w in must_fit if w.winfo_rooty() + w.winfo_height() > root.winfo_rooty() + root.winfo_height()]
    check(not clipped, "run buttons%s fit inside the window" % ("" if app.opts_open else " and the result banner"))
    right_edge = root.winfo_rootx() + root.winfo_width()
    off = [w for w in (app.btn_dry, app.btn_exec, app.btn_stop, app.btn_log) if w.winfo_rootx() + w.winfo_width() > right_edge]
    check(not off, "every action button fits inside the window horizontally")
    check(all(w.winfo_width() >= w.winfo_reqwidth() for w in (app.btn_dry, app.btn_exec, app.btn_stop, app.btn_log)),
          "no button is squeezed below its natural width")
    if geom_file:
        Path(geom_file).write_text("%d,%d,%d,%d" % (root.winfo_rootx(), root.winfo_rooty(), root.winfo_width(), root.winfo_height()))
    pump(hold)
app.on_close()
try:
    root.update()
except tk.TclError:
    pass
check(not (app.run and app.run.running), "no run left after closing")
print("\nFAILED: %d" % len(fails) if fails else "\nALL OK")
tmp.cleanup()
sys.exit(1 if fails else 0)
