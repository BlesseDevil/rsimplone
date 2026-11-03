<!-- SPDX-License-Identifier: AGPL-3.0-or-later. Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence) -->
# Changelog

## 2.1.0
- **Fixed:** the console never showed anything (its bridge method name hangs in pywebview). Finished runs showed no stats. The Schedule tab printed "null".
- **Live run view:** progress, speed, time left and the files being copied right now, per job; previews show files found, would copy, would back up.
- **Jobs:** duplicate and delete from the job header; export all or selected jobs to a file and import them (schedules and Move unlocks are never exported). Stop all.
- **Safety:** a Move's single-use unlock is now kept on disk and cannot be revived by a later save; a damaged or missing job file cannot bring it back; a Move must keep `--disable DirMove`; imports are size-limited, refuse control characters and skip bad jobs instead of breaking the list; failed saves roll back.
- **Tests can never touch real data** (they refuse to run without a throwaway data folder).
- **Look and wording:** plain-language labels ("Preview" instead of "Dry run"), new tagline, dual-tone taskbar icon, splash portal no longer cut off by a circle.
- **Launchers renamed:** `rsl.pyw` and `launch-rsl.sh`.
- **Packaging:** Windows installer with uninstaller, portable single files for Windows and Linux, SHA-256 hashes. (macOS packaging is planned for 2.1.1.)

## 2.0.0
- New pywebview interface, Move jobs with a dry-run gate, encrypted remotes, mounts, scheduler, console.
