# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Exe = Join-Path $Root "dist\SignalDojo\SignalDojo.exe"
if (-not (Test-Path $Exe)) { throw "Build the executable first: $Exe" }

$ErrorFile = Join-Path (Split-Path $Exe -Parent) "packaging-self-test-error.txt"
Remove-Item -Force -ErrorAction SilentlyContinue $ErrorFile

$Process = Start-Process -FilePath $Exe -ArgumentList "--packaging-self-test" -Wait -PassThru
if ($Process.ExitCode -ne 0) {
    $Detail = ""
    if (Test-Path $ErrorFile) {
        $Detail = "`n" + (Get-Content $ErrorFile -Raw)
    }
    throw "Packaged import verification failed with exit code $($Process.ExitCode).$Detail"
}

Write-Host "Packaged import verification passed." -ForegroundColor Green
