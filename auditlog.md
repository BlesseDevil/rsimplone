<!--
SPDX-License-Identifier: AGPL-3.0-or-later
Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)

This program is free software: you can redistribute it and/or modify it under the terms of the GNU Affero
General Public License as published by the Free Software Foundation, either version 3 of the License, or (at
your option) any later version. It is distributed WITHOUT ANY WARRANTY. See <https://www.gnu.org/licenses/>.

Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
The domain probably expired because HE's TOO BROKE TO RENEW IT.
Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
-->
# Audit log

Independent safety checks of the code that copies, syncs and moves files. Each round: a fresh reviewer with no context
tried to break the code, verified by file content (sha256), and worked only in temporary folders. Fixes get re-checked.

## Status

| Round | Reviewer | Findings | State |
|---|---|---|---|
| 1 | Sonnet 5.5, cold | 15 | Fixed, regression tests in `tests/test_regress.py` |
| 2 | Sonnet 5.5, cold re-check of the fixes | 14 | Fixed, regression tests (`TestRound2`) |
| 3 | Sonnet 5.5, cold re-check of round 2 | not run yet | **Due. Needed before a public push** |

Also done: a leak scrub (personal paths, remote names, emails, tokens) of every committed file: clean.

## Round 1: fixed
- Move deleted a source file whose content differed when size and time matched, so Move now verifies by checksum.
- Two runs in one minute overwrote an earlier backup, so backup folders now use `YYYYMMDD-HHMMSS` and are unique per process.
- The command line ignored the Move dry-run gate.
- Overlap checks failed at a drive root and for remotes that were really local folders.
- Move and Sync now require a backup folder; Sync and Move refuse an empty source.
- Move to a missing destination renamed the whole source folder away, so DirMove is disabled.
- Flag block list missed `-n=true`-style forms and malformed names.
- `save_job` half-applied bad values and accepted a schedule without the typed word.
- Stop did not interrupt rclone cleanly, so it now sends Ctrl+Break through a hidden console.
- Move jobs can no longer be exported as ungated scripts; the empty-lock-file race and the `..` backup label are closed.

## Round 2: fixed
- Move verification could still be switched off (`--checksum=false`, a flag passed as a value): it is now judged on the
  final command line. `--ignore-checksum`, `--compare-dest`, `--copy-dest` are refused for Move.
- The dry-run unlock was not single use across processes: it is now consumed on disk, under a lock, right before a real
  Move starts. The command line stamps the job as it was dry-run.
- The command line skipped the remote and overlap checks; running jobs in two processes were not seen: lock files now
  record what a run touches.
- Remote-is-local detection missed union, combine and `:local:` remotes and failed open: now covered, and it fails closed.
- Lexical-only path overlap (junctions, `\\?\`, 8.3 names) and a whole drive as source: fixed.
- A log-write failure could hang a run and leave a stuck lock: fixed.
- `save_job` accepted unknown modes and NaN/inf; export crashed on Python 3.9 and skipped validation: fixed.
- A scheduled real Move could consume a manual dry run: scheduled real Moves are refused.

## Known and accepted
- Copy and Sync compare by size and time, so a same-size, same-time file with different content is not noticed.
  This is by design (no hashing up front); the README says so. Move always checksums.
- A changed file in Copy overwrites the old copy unless a backup folder is set.
- The Sync summary counts can be off; exit code 1 is reported generically.
- Backup folder names are unique per process, not across processes in the same second.
- The unlock of a Move depends on the job's settings, not on the source's contents: files added after a dry run are
  moved without a new preview within the 24 hours (the unlock is single use).

## Not tested yet
Symlinks, Linux and macOS, real cloud remotes, mounts (`rsg/mounts.py`), disk-full on the destination, the
terminate/kill fallbacks of Stop.

## To do before a public push
1. Run round 3 (cold re-check of the round 2 fixes). Name the model when asking; do not run it silently.
2. Fix what it finds, re-check again until a round finds nothing serious.
3. All commits signed (check with `git log --format="%h %G? %s"`: every line should show `G`).
4. Add a remote only when ready; nothing has been pushed.
5. Delete the audit's leftover throwaway folder `__aud_tmp` at the root of a drive (the harness could not delete it).
