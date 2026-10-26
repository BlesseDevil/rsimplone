# rSimpLone

**by blessedevil** — *rClone fear is at a stake! Copy, Sync and Move via rclone made easy....*

A modern desktop app for [rclone](https://rclone.org/). Pick folders, preview with a **dry run**, then run it for real.
Jobs are saved, several can run at once, they can run on a schedule, and remotes (or just one folder of them) can be
mounted as drives. Nothing is hard-coded: every folder, remote and setting is yours.

It was built for one situation: a big folder on a slow USB hard drive, a modest home connection, Google Drive on the
other end, and a strong wish not to re-read or re-upload anything that doesn't need it.

## What it does

| Job type | What it does | Deletes anything? |
|---|---|---|
| **Copy** | Adds new and changed files to the destination | Never |
| **Sync** | Mirrors the source; replaced and removed files move to a backup folder | Never for good: they go to the backup folder |
| **Move** | Transfers, then removes the originals from the source (every file is verified by checksum first) | **The source files.** Needs a backup folder, and a real run unlocks only after a dry run of the exact same job (24 h, one use) |

Destinations can be a cloud remote, an **encrypted (crypt) remote**, or another local folder. Backups use
`<backup folder>/<source name>/<YYYYMMDD-HHMMSS>/` on the same remote, so nothing is re-uploaded. Sync and Move
refuse to run without a backup folder, refuse an empty source (a disconnected drive would otherwise look like
"everything was deleted"), and refuse flags that skip verification. Copy never deletes, but a changed file
overwrites the old one unless you set a backup folder.

Other features:

- **Several jobs at once**, each in its own run; two jobs can't write to the same place at the same time. A remote that
  is really a folder on this computer (local, alias, crypt over a local folder) is checked against your source and backup
  folders too; other cross-job overlaps through such remotes are not detected.
- **Scheduler** (daily, weekly or every N minutes) while the app is open. Scheduled *real* runs need a one-time typed
  `EXECUTE` and fall back to dry runs if you later edit the job. A background mode keeps it alive with the window closed
  (tray icon with the optional `pystray` + `Pillow` packages; otherwise it just minimises). Running with the app fully
  closed (Task Scheduler / cron) is planned, not built.
- **Mounts**: mount a remote or a folder of it (needs WinFsp on Windows, macFUSE/FUSE-T on macOS, fuse3 on Linux; the app
  tells you what is missing and installs nothing). Read-only by default.
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

A dry run hashes just like a real run, and rclone doesn't remember hashes between runs.

## Requirements and starting it

- **Python 3.9+** and **rclone** on your `PATH` (or set its path in Settings).
- `python -m pip install pywebview` (a Qt/GTK WebKit is needed on Linux; Windows 10/11 uses the built-in WebView2).
- Windows: double-click `rsg.pyw` (no console window). Linux/macOS: `./launch-rsg.sh`. Anywhere: `python -m rsg`.
- Optional: `pip install pystray Pillow` for the tray icon.

Headless (for Task Scheduler / cron): `python -m rsg --list`, `python -m rsg --run "My job"` (dry run), add
`--execute --yes` to run for real (a Move still needs its dry run first). **Export script** in a job's Config tab writes a
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
rsg.pyw, launch-rsg.sh   launchers
rsg/core.py              jobs, rclone command lines, runs, verification, crypt creation, disk detection
rsg/flags.py             rclone flag catalogue, app-owned flag denylist, merging
rsg/schedule.py          schedule rules + ticker
rsg/mounts.py            rclone mount
rsg/runs.py              several runs at once, overlap and Move safety checks
rsg/api.py               bridge between the page and the logic
rsg/app.py               the windows (borderless splash + frameless main)
rsg/ui/                  HTML, CSS, JS, fonts, brand images
tests/                   unit tests and the real-window smoke test
```

## Licence and contact

Copyright (C) 2026 blessedevil | Mehedi Maruf. GNU Affero General Public License v3 or later
(`AGPL-3.0-or-later`). Bundled fonts (Inter, Geist Mono) are under the SIL OFL; see `rsg/ui/fonts`.

- Developer: rsimplone@mehedimaruf.com
- Licence questions: license@mehedimaruf.com
- Website: <https://mehedimaruf.com>

**Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
The domain probably expired because HE's TOO BROKE TO RENEW IT.
Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')**
