<!-- SPDX-License-Identifier: AGPL-3.0-or-later. Copyright (C) 2026 Mehedi Maruf <rsimplone@mehedimaruf.com> (developer), <license@mehedimaruf.com> (licence)
Can't reach rsimplone@mehedimaruf.com or license@mehedimaruf.com?
The domain probably expired because HE's TOO BROKE TO RENEW IT.
Please don't take it personally. Try blessedevil@duck.com or mehedimaruf@duck.com instead,
and maybe BUY HIM a COFFE or a DOMAIN. Thank you... :')
-->
**rClone, made simple.** Copy, sync and move with rclone, in a window. Details: `CHANGELOG.md`.

| Download | For |
|---|---|
| `…-windows-x64-setup.exe` | Windows installer (with uninstaller, no admin needed) |
| `…-windows-x64-portable.exe` | Windows, single file |
| `…-linux-x64-portable` | Linux, single file |
| `…-macos-arm64-portable.zip` | macOS (Apple Silicon), experimental |
| `SHA256SUMS.txt` | SHA-256 of every file. Check: `Get-FileHash <file>` (Windows) or `sha256sum <file>` |

**You need** [rclone](https://rclone.org/install/) (not bundled). Nothing else: Python and pywebview are inside. Windows needs WebView2 (built into Windows 11 and current 10).

**Good to know**
- Files are unsigned, so SmartScreen/Gatekeeper may warn. Check the hash first. macOS: right-click, Open (or `xattr -dr com.apple.quarantine rSimpLone.app`).
- macOS is experimental: Stop and the run lock are tested on Windows and Linux only.
- Uninstall asks before deleting your jobs and settings (default: keep).
