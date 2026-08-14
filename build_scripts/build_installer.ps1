# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Version = "1.2.6"
$ProgramFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
$ProgramFiles64 = [Environment]::GetEnvironmentVariable("ProgramFiles")
$Candidates = @()
if ($ProgramFilesX86) {
    $Candidates += Join-Path $ProgramFilesX86 "Inno Setup 6\ISCC.exe"
}
if ($ProgramFiles64) {
    $Candidates += Join-Path $ProgramFiles64 "Inno Setup 6\ISCC.exe"
}
$Command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
if ($Command) {
    $Candidates += $Command.Source
}

$ISCC = $Candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $ISCC) {
    throw "Inno Setup 6 was not found. Install it before building the installer."
}

& (Join-Path $PSScriptRoot "verify_packaged_imports.ps1")
Set-Location $Root
& $ISCC (Join-Path $Root "installer\SignalDojo.iss")
$ExitCode = $LASTEXITCODE
if ($null -eq $ExitCode) { $ExitCode = 0 }
if ($ExitCode -ne 0) {
    throw ("Inno Setup failed with exit code {0}." -f $ExitCode)
}

$Installer = Join-Path $Root "release\SignalDojo-$Version-win64-setup.exe"
if (-not (Test-Path $Installer)) {
    throw "Inno Setup did not produce the expected installer: $Installer"
}
Write-Host "Installer build complete: $Installer" -ForegroundColor Green
