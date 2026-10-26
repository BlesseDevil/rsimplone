# Copyright (C) 2026 Mehedi Maruf
# SPDX-License-Identifier: AGPL-3.0-or-later
# Part of rclone-sync-gui; see rsg_core.py for the full licence notice and contact details.
#
# Dev helper: runs tests/smoke_gui.py with the window held open and saves a screenshot of it.
#   powershell -File tests\shot.ps1 -Theme dark -Options 1 -Out C:\temp\shot.png
param([string]$Theme = "light", [string]$Options = "0", [string]$Out = "$env:TEMP\rsg-shot.png")
Add-Type -AssemblyName System.Drawing
$root = Split-Path -Parent $PSScriptRoot
$geom = Join-Path $env:TEMP "rsg-geom-$Theme.txt"
if (Test-Path $geom) { [IO.File]::Delete($geom) }
$p = Start-Process -FilePath python -ArgumentList @("$root\tests\smoke_gui.py", "--theme", $Theme, "--tab", $Options, "--hold", "9", "--geometry-file", $geom) `
    -PassThru -RedirectStandardOutput "$env:TEMP\rsg-smoke-$Theme.out" -RedirectStandardError "$env:TEMP\rsg-smoke-$Theme.err" -WindowStyle Hidden
$t = 0
while (-not (Test-Path $geom) -and $t -lt 160) { Start-Sleep -Milliseconds 500; $t++ }
Start-Sleep -Seconds 2
if (Test-Path $geom) {
    $g = (Get-Content $geom).Split(",")
    $bmp = New-Object System.Drawing.Bitmap ([int]$g[2]), ([int]$g[3])
    $gr = [System.Drawing.Graphics]::FromImage($bmp)
    $gr.CopyFromScreen([int]$g[0], [int]$g[1], 0, 0, $bmp.Size)
    $bmp.Save($Out)
    $gr.Dispose(); $bmp.Dispose()
    "screenshot: $Out"
}
$p.WaitForExit(120000) | Out-Null
"smoke: " + (Get-Content "$env:TEMP\rsg-smoke-$Theme.out" | Select-Object -Last 1)
Get-Content "$env:TEMP\rsg-smoke-$Theme.out" | Where-Object { $_ -match "^FAIL" }
Get-Content "$env:TEMP\rsg-smoke-$Theme.err" | Select-Object -First 8
