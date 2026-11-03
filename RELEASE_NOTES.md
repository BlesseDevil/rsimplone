<!-- SPDX-License-Identifier: AGPL-3.0-or-later. Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence) -->
**rClone, made simple.** Copy, sync and move with rclone, in a window.

## Downloads (pick one)
| File | For |
|---|---|
| `rSimpLone-<version>-windows-x64-setup.exe` | Windows installer with an uninstaller (no admin rights needed) |
| `rSimpLone-<version>-windows-x64-portable.exe` | Windows, single file, nothing to install |
| `rSimpLone-<version>-linux-x64-portable` | Linux, single file |
| `SHA256SUMS.txt` | SHA-256 hash of every file above |

**Verify a download** (compare with `SHA256SUMS.txt`): Windows `Get-FileHash <file> -Algorithm SHA256`, macOS/Linux `sha256sum <file>`.

## What you still need
- **rclone** itself, on your PATH or set in Settings. It is not bundled.
- Nothing else. The portable files and the installer contain Python and the one library the app needs (pywebview).
  Windows needs the WebView2 runtime (already in Windows 11 and current Windows 10). Linux needs a desktop session.

## Heads-up
- The files are not code-signed yet, so Windows SmartScreen or macOS Gatekeeper may warn on first start. Check the hash above, then choose "more info / run anyway" (macOS: right-click, Open).
- Uninstalling asks whether to also delete your jobs, logs and settings. The default is to keep them.
- **macOS has no packaged build in this release.** It can run from source (`python -m rsg`), but Stop and the disk-type check are not verified there yet. A macOS build is planned for 2.1.1.
- The Linux build is produced by the release pipeline and has had less hands-on testing than Windows.

See `CHANGELOG.md` for what changed.
