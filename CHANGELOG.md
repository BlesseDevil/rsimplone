<!-- SPDX-License-Identifier: AGPL-3.0-or-later. Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)
Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
The domain probably expired because HE's TOO BROKE TO RENEW IT.
Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
-->
# Changelog

## 2.2.0
- **Remotes inside the app:** a Remotes page to add, test, edit and delete cloud and server connections (Google Drive, OneDrive, Dropbox, S3, SFTP, WebDAV, B2, FTP, SMB and every other backend rclone has). The forms come from rclone itself, including its follow-up questions and the browser sign-in. A half-made remote is removed again if you cancel.
- **Google sign-in made easier:** Google Drive and Google Photos are listed first. The shared-key question explains the risk and suggests No; import the JSON credentials file you download from Google (the secret stays inside the app) or type the client id and secret by hand; the sign-in link can be copied to open in another browser or profile. Y and N keys work on yes/no questions.
- **Simple and Advanced mode:** Simple shows only the essentials; Advanced shows every rclone setting. It only changes what is shown, never what a job does.
- **Choose the rclone config file:** rclone's default file (shared with the rclone command line), a separate file just for rSimpLone, or any file you pick. Every job, mount and check, plus exported scripts, uses the same file. A backup copy is made before the first change in each session; passwords are never shown or logged; a remote that jobs or mounts use cannot be deleted.
- **macOS:** packaged as a zipped app (Apple Silicon). Stop and the run-lock are covered by tests on Windows and Linux; the matching tests are skipped on macOS because a throttled local copy ends instantly there, so treat macOS as experimental.
- **Open config file** button (Remotes page and Settings) opens the rclone config in a text editor after a backup; **Reload** reads it again.
- **Copy remote (Advanced):** make a second remote that keeps the same login but starts in a different root folder (Google Drive and similar). It never puts the sign-in token on a command line.
- **Rename** a remote in its Edit window (jobs, mounts and remotes that point at it follow). **Copy login…** gives other remotes of the same Google account a working login when theirs expired; the account must be the same.
- Fixed: remotes with a space in the name, and every Google Photos remote, were missing from the list.
- Tests refuse to change a real rclone.conf.

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
