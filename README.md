# rSimpLone

**by blessedevil**. *rClone, made simple.*

A modern desktop app for [rclone](https://rclone.org/). Pick folders, press **Preview** (rclone's dry run: nothing is changed), then run it for real.
Jobs are saved, several can run at once, they can run on a schedule, and remotes (or just one folder of them) can be
mounted as drives. Nothing is hard-coded: every folder, remote and setting is yours.

It was built for one situation: a big folder on a slow USB hard drive, a modest home connection, Google Drive on the
other end, and a strong wish not to re-read or re-upload anything that doesn't need it.

## What it does

| Job type | What it does | Deletes anything? |
|---|---|---|
| **Copy** | Adds new and changed files to the destination | Never |
| **Sync** | Mirrors the source; replaced and removed files move to a backup folder | Never for good: they go to the backup folder |
| **Move** | Transfers, then removes the originals from the source (every file is verified by checksum first) | **The source files.** Needs a backup folder, and a real run unlocks only after a preview of the exact same job (24 h, one use) |

Destinations can be a cloud remote, an **encrypted (crypt) remote**, or another local folder. Backups use
`<backup folder>/<source name>/<YYYYMMDD-HHMMSS>/` on the same remote, so nothing is re-uploaded. Sync and Move
refuse to run without a backup folder, refuse an empty source (a disconnected drive would otherwise look like
"everything was deleted"), and refuse flags that skip verification. Copy never deletes, but a changed file
overwrites the old one unless you set a backup folder. Copy and Sync compare by size and time (so a same-size,
same-time file with different content is not noticed, by design: no hashing up front); Move always verifies by checksum.

Other features:

- **Several jobs at once**, each in its own run; two jobs can't write to the same place at the same time. A remote that
  is really a folder on this computer (local, alias, crypt, union, combine, `:local:`) is checked against your source and
  backup folders too, and the window and the command line see each other's running jobs. If your rclone configuration
  can't be read, the check refuses to run rather than guessing.
- **Scheduler** (daily, weekly or every N minutes) while the app is open. Scheduled *real* runs need a one-time typed
  `EXECUTE` and fall back to previews if you later edit the job. Move jobs can only be scheduled as previews. A background mode keeps it alive with the window closed
  (tray icon with the optional `pystray` + `Pillow` packages; otherwise it just minimises). Running with the app fully
  closed (Task Scheduler / cron) is planned, not built.
- **Mounts**: mount a remote or a folder of it (needs WinFsp on Windows, macFUSE/FUSE-T on macOS, fuse3 on Linux; the app
  tells you what is missing and installs nothing). Read-only by default.
- **Remotes**: add, test, edit and delete cloud and server connections without leaving the app (rclone's own guided setup, including the browser sign-in), in **Simple** or **Advanced** mode. Choose which rclone config file is used: rclone's default, a separate one for rSimpLone, or any file. Passwords are never shown or logged, a backup of the config is made before changes, and a remote in use can't be deleted.
- **Jobs**: duplicate or delete a job from its header; **export** all or selected jobs to a JSON file and **import** them elsewhere (New menu or Settings). Schedules, run history and a Move's unlock are never exported, so an imported job starts unscheduled and a Move needs a new preview.
- **Live run view**: progress, speed, time left, the files being copied right now, and an activity list, per job.
- **Config tab**: speed profile (HDD/SSD, line speed), behaviour switches and **every rclone flag**, read from
  `rclone help flags` for your rclone version, with what it does on hover. Only values that differ from the default are
  saved. Flags the app controls itself (dry run, backup folder, logging, progress) are refused.
- **Console**: the bottom pane shows rclone's real log in rclone's own layout. `Ctrl+C` in it stops the selected run
  cleanly, and the window stays in sync. (It's the JSON-log view, not `-P` output.)
- **Disk detection**: choosing a source folder detects SSD vs HDD (USB drives are reported as "can't tell" on purpose:
  many enclosures lie).
- **Encrypted remotes**: use existing crypt remotes (lock icon) or create one in the app. The password is passed through
  `rclone obscure` on stdin and never stored by rSimpLone; encrypted data can't be hashed, so files are compared by
  size and time.
- Light, dark or system theme. The logo is the theme button: hover animates it, click cycles the theme.

## How it decides what to copy

| Situation | What happens |
|---|---|
| Same size and same modified time | Skipped without reading the file |
| Different size | Copied again, no hash |
| Same size, different modified time | Hashed (the only case that reads your disk); if equal, only the remote time is fixed |

A preview hashes just like a real run, and rclone doesn't remember hashes between runs.

## Install

Download from the [Releases](https://github.com/BlesseDevil/rsimplone/releases) page: a Windows **installer** (with an
uninstaller) or a **portable single file** for Windows, Linux, or a zipped app for macOS (experimental), plus `SHA256SUMS.txt` to check them. You still
need **rclone**. The packaged files contain everything else.

## Dependencies (what the app needs)

| Needs | Why | Where it comes from |
|---|---|---|
| **rclone** | does all the copying | you install it; found on `PATH` or set in Settings. Never bundled or downloaded for you |
| **pywebview** (the only Python package) | draws the window | `pip install pywebview`; already inside the installer and portable files |
| Python 3.9+ | runs the code (standard library only otherwise) | only when running from source; inside the packaged files |
| WebView2 (Windows), WebKit (macOS), Qt or GTK web view (Linux) | the page engine pywebview uses | built into Windows 10/11 and macOS; on Linux install `pywebview[qt]` or your distro's GTK WebKit |
| `pystray` + `Pillow` (optional) | tray icon for background mode | `pip install pystray Pillow`; without them the window just minimises |
| WinFsp / macFUSE or FUSE-T / fuse3 (optional) | mounts only | you install it; the app tells you what is missing |

## Requirements and starting it

- **Python 3.9+** and **rclone** on your `PATH` (or set its path in Settings).
- `python -m pip install pywebview` (a Qt/GTK WebKit is needed on Linux; Windows 10/11 uses the built-in WebView2).
- Windows: double-click `rsl.pyw` (no console window). Linux/macOS: `./launch-rsl.sh`. Anywhere: `python -m rsg`.
- Optional: `pip install pystray Pillow` for the tray icon.

Headless (for Task Scheduler / cron): `python -m rsg --list`, `python -m rsg --run "My job"` (dry run), add
`--execute --yes` to run for real (a Move still needs its preview first). **Save as script** in a job's Config tab writes a
standalone script (not offered for Move jobs: a script has no safety gate).

## Where things are stored

`%APPDATA%\rSimpLone` (Windows), `~/.config/rSimpLone` (Linux), `~/Library/Application Support/rSimpLone` (macOS):
jobs, logs, crash log. Set `RSG_HOME` to use another folder. Logs contain folder and remote names, so they live there,
not in this project.

## Tests

```
python -m unittest discover -s tests -v   # logic, move/crypt/schedule/mount rules, the bridge (real rclone, throwaway data)
python tests/smoke_app.py result.json     # opens the real windows against throwaway folders for ~15 s
```

For a quick look at the interface without Python, serve `rsg/ui` and open `index.html?mock` (fake data).

## Project layout

```
rsl.pyw, launch-rsl.sh   launchers
rsg/core.py              jobs, rclone command lines, runs, verification, crypt creation, disk detection
rsg/flags.py             rclone flag catalogue, app-owned flag denylist, merging
rsg/schedule.py          schedule rules + ticker
rsg/mounts.py            rclone mount
rsg/remotes.py           adding, editing, testing, deleting remotes through rclone's own setup
rsg/runs.py              several runs at once, overlap and Move safety checks
rsg/api.py               bridge between the page and the logic
rsg/app.py               the windows (borderless splash + frameless main)
rsg/ui/                  HTML, CSS, JS, fonts, brand images
tests/                   unit tests and the real-window smoke test
```

## Licence and contact

Copyright (C) 2026 blessedevil | Mehedi Maruf. GNU Affero General Public License v3 or later
(`AGPL-3.0-or-later`); the full text is in `LICENSE`. Bundled fonts (Inter, Geist Mono) are under the SIL OFL; see `rsg/ui/fonts`.

**The emblem and logo artwork in `rsg/ui/brand/` is proprietary: all rights reserved by blessedevil | Mehedi Maruf. It is not covered by the AGPL and may not be reused, redistributed or used to brand a fork without written permission.**

- Developer: rsimplone@mehedimaruf.com
- Licence questions: license@mehedimaruf.com
- Website: <https://mehedimaruf.com>

**Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
The domain probably expired because HE's TOO BROKE TO RENEW IT.
Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')**
