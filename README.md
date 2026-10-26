# rSimpLone

**by blessedevil** — *rClone fear is at a stake! Sync/Copy via rclone made easy....*

A small desktop app for backing a folder up with [rclone](https://rclone.org/). You pick the folders in a window,
run a **dry run** to see exactly what would happen, and then run it for real. Nothing is hard-coded: every folder,
remote and setting is yours to choose, and your jobs are saved so you can run them again. The destination can be a
cloud remote (built and used with Google Drive) or just another folder on your computer.

It was built for one specific situation: a big backup folder on a slow USB hard drive, a modest home internet
line, a Google Drive on the other end, and a strong wish not to re-read or re-upload anything that doesn't need it.

## Two kinds of job

| | **Sync** | **Copy** |
|---|---|---|
| What it does | Makes the destination match your source folder | Adds new and changed files to the destination |
| Files you deleted locally | Moved to a backup folder | Left alone |
| Files you changed locally | Old version moved to the backup folder, new one copied | New version copied; old one kept in the backup folder if you chose one |
| Backup folder | Required | Optional |
| Deletes anything for good? | Never. Removed files go to the backup folder. | Never. |

Both skip anything that hasn't changed, and both keep one folder per run so you can always find what a run moved:

```
<backup folder> / <source folder name> / <YYYYMMDD-HHMM> / <path of the file>
```

## Requirements

- **Python 3.9 or newer** with tkinter (it ships with the Windows and macOS installers; on Linux install
  `python3-tk`). No extra packages are needed.
- **rclone** on your `PATH` (or point the app at it under *File > Settings*). For a cloud destination you also need a
  remote set up with `rclone config`.

## Starting it

- **Windows:** double-click `rsg.pyw`. The `.pyw` extension starts it without a console window, so nothing is left
  open behind the app.
- **Linux / macOS:** run `./launch-rsg.sh`. It starts the app detached from the terminal.
- Any system: `python3 -m rsg` (or `python3 rsg.pyw`). `pip install .` also works and adds an `rsimplone` command.

If it cannot start, an error dialog explains why and the details go to `crash.log` in the data folder (below).

## Using it

1. Press **+ New** and choose **Sync** or **Copy** at the top.
2. **Local folder:** type or paste a path, press *Browse...*, or drag a folder onto the box if you have installed the
   optional `tkinterdnd2` package. The app shows how much space is free on that drive, and works out by itself whether
   it is an SSD or an HDD (see *Disk type* below).
3. **Send to:** *Cloud remote* or *Local folder*.
4. For a cloud remote pick the **Remote**; then type the target and backup folders or press **Pick...** to choose them
   from the remote's folder list. For a local destination, press **Pick...** to choose a folder; the free space of its
   drive is shown on the same line as the check mark.
5. Press **Dry run**. The Activity tab lists everything that would be copied or moved. Nothing is changed.
6. Happy with it? Press **Execute now...** (or **Execute...** / **Copy for real...**) and type `EXECUTE` to confirm.

The gear button opens **Options**: the check-the-remote-folders button, the sub-folder name, "skip existing" (copy
only), all tuning, and *Copy command* / *Export script*. The work area scrolls, so the window can be any height.
**Theme** (File menu or the Theme menu) switches between light, dark and matching your system; the choice is
remembered. **Contact dev** (top right) opens the About window.

Closing the window while a job runs asks first and stops rclone cleanly. **Stop** does the same without closing.

## How it decides what to copy

rclone's defaults are used on purpose:

| Situation | What happens |
|---|---|
| Same size and same modified time | Skipped. The file is not read at all. |
| Different size | Copied again. No hash needed. |
| Same size, different modified time | The file is hashed (the only case that reads your disk). If the hashes match, only the destination's modified time is corrected and nothing is copied. |

So a first run can spend a while hashing a few large files whose times differ. Once their times are aligned, later
runs skip them. A dry run hashes just like a real run, and rclone doesn't remember hashes between runs.

## Fewest Drive API calls

Tick **Fewest Drive API calls** (on by default, cloud only) to make the job as frugal as practical:

- one recursive listing instead of a listing per folder (`--fast-list`)
- larger upload chunks (64 MiB, or 128 MiB on a fast line), so big files need fewer requests
- a steady cap of 8 requests per second, so Google's rate limiting doesn't force wasted retries
- fewer low-level retries

The app itself is frugal too: nothing is listed until you ask (**Check folders** lives in Options so it isn't clicked
by accident), a run lists the remote's folders at depth 1 in a single call, and the result is reused for 15 minutes.
These are the expected savings from the settings; I haven't measured actual call counts on a real Drive.

## Folder dates (its own option)

**Don't update folder dates on the remote** (off by default, separate from the option above) passes
`--no-update-dir-modtime`. By default rclone copies a local folder's modified time onto the matching remote folder
whenever the two differ, one small metadata call per such folder. Ticking this skips those calls; the only effect is
that Drive's folder dates won't mirror your local ones. It never affects how files are compared, hashed or copied.

## Sending to another folder instead of the cloud

In the **Send to** row choose **Local folder** to copy or sync between two folders on this computer, for example to a
second drive. Everything else works the same: dry run first, a backup folder for replaced and removed files, one
timestamped folder per run, and the same comparison rules. For a local destination the cloud-only options (line
speed, fewest API calls, folder dates) are switched off, and folder dates are always kept. The app refuses setups that
could damage data: a destination inside the source (or the other way round), a backup folder inside the source, or a
whole drive as the destination.

## Disk type

When you choose a source folder the app asks the operating system whether it lives on an SSD or an HDD and sets the
tuning to match (an HDD gets few parallel readers and finishes all hash checks before copying starts). It never reads
your files to find out, and it asks in the background. **External USB drives are deliberately reported as "can't
tell"**: many USB enclosures give wrong answers (a spinning laptop drive can claim to be an SSD), so for those the app
leaves your choice alone and says so. You can always set HDD or SSD yourself under Options.

## Tuning

These settings live under the gear button.

- **Source disk:** *HDD* uses few parallel readers and finishes all hash checks before copying starts, so a slow
  external drive isn't jumping between the two. *SSD* allows more parallelism.
- **Line speed:** your connection speed in Mbit/s. rclone is limited to the percentage you choose (85% by default)
  so the rest of the household can still use the line. *No limit* removes it. Cloud only.
- **Checkers / Transfers:** override the automatic values (0 means automatic).

## Running without the window

- `python3 -m rsg --list` lists saved jobs.
- `python3 -m rsg --run "My job"` does a dry run. Add `--execute --yes` to run for real.
- **Export script...** writes a standalone script (PowerShell on Windows, shell elsewhere) that runs the same rclone
  command without this app. It does a dry run unless you pass `-Execute` (or `--execute`). **Copy command** puts the
  dry-run command on the clipboard.

Use these to schedule a job with Task Scheduler or cron.

## Where things are stored

| What | Windows | Linux | macOS |
|---|---|---|---|
| Jobs, logs, crash log | `%APPDATA%\rSimpLone` | `~/.config/rSimpLone` | `~/Library/Application Support/rSimpLone` |

*File > Open data folder* opens it. Each run writes a log under `logs/<job name>/`. Set the `RSG_HOME` environment
variable to use a different folder. If you used an earlier build that stored its data under `rclone-sync-gui`, that
folder is renamed to `rSimpLone` on first start so your jobs carry over.

## Exit codes

The result banner explains rclone's exit code in plain words. The table, for reference:

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Usage or syntax error |
| 2 | Uncategorised error, see the log |
| 3 | Folder not found |
| 4 | File not found |
| 5 | Temporary error, retries ran out; running again usually fixes it |
| 6 | Less serious errors, some items failed |
| 7 | Fatal error, retrying won't help |
| 8 | Transfer limit exceeded |
| 9 | Finished, but nothing needed copying |

## Good to know

- It copies from your source folder **to** the destination. It never changes your source files.
- Only one run per job can happen at a time.
- Two runs of the same job inside the same minute would share a backup folder.
- **Stop** asks rclone to stop and kills it after a few seconds if it hasn't. Files that were already finished are
  kept; a copy that was in progress is simply redone on the next run.
- Drag and drop needs the optional `tkinterdnd2` package; that path is untested.
- Your saved jobs and logs contain folder and remote names. They live in the data folder, not in this project, and
  the included `.gitignore` keeps logs out of version control.
- Startup is about half a second: the rounded buttons, fields and cards are small images drawn when the app starts,
  the window is shown only once it is complete, and `rclone version` is read in the background.

## Tests

```
python -m unittest discover -s tests -v     # core logic against real rclone and a throwaway local remote
python tests/smoke_gui.py                   # drives the real window; opens it on screen for a few seconds
```

Neither touches your real remotes or files.

## Project layout

```
rsg.pyw            double-click launcher (no console on Windows)
launch-rsg.sh      detached launcher for Linux and macOS
rsg/core.py        everything that is not a window: jobs, rclone command lines, runs, verification, disk detection
rsg/theme.py       colours, fonts and the rounded look
rsg/gui.py         the tkinter window
rsg/assets/        logo and icon images
tests/             unit tests (real rclone, throwaway data) and a window smoke test
pyproject.toml     packaging; the app needs only the standard library
WinPSObsolete/     the first, PowerShell-only version, kept for reference
```

## Look and feel

Colours follow the mehedimaruf.com design tokens (warm cream by day, wine-black by night) with the blessedevil emblem;
gold marks the safe action (dry run) and crimson the real one. Plain ttk styling on top of tkinter, so there is
nothing extra to install.

## The old PowerShell version

The first version was a pair of PowerShell scripts (a generator plus the scripts it wrote). It is kept in
`WinPSObsolete/` for reference. It is Windows-only and no longer maintained.

## Licence and contact

Copyright (C) 2026 blessedevil | Mehedi Maruf. Licensed under the GNU Affero General Public License, version 3 or
(at your option) any later version (SPDX: `AGPL-3.0-or-later`). See <https://www.gnu.org/licenses/>.

- Contact the developer: rsimplone@mehedimaruf.com
- Licence questions: license@mehedimaruf.com
- Website: <https://mehedimaruf.com>

**Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
The domain probably expired because HE's TOO BROKE TO RENEW IT.
Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')**
