# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Exe = Join-Path $Root "dist\SignalDojo\SignalDojo.exe"
if (-not (Test-Path $Exe)) { throw "Build the executable first." }
$Process = Start-Process -FilePath $Exe -PassThru
Start-Sleep -Seconds 8
if ($Process.HasExited) { throw "SignalDojo exited during startup with code $($Process.ExitCode)." }
Stop-Process -Id $Process.Id
Write-Host "Packaged executable startup smoke test passed." -ForegroundColor Green
