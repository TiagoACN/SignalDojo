# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & (Join-Path $PSScriptRoot "create_environment.ps1")
}
$Python = Join-Path $Root ".venv\Scripts\python.exe"
& $Python -m pip install --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Failed to install runtime dependencies." }
& $Python build_scripts\check_python311_compatibility.py
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 compatibility validation failed." }
& $Python -m app.main
$ExitCode = $LASTEXITCODE
if ($null -eq $ExitCode) { $ExitCode = 0 }
if ($ExitCode -ne 0) { throw ("SignalDojo exited with code {0}." -f $ExitCode) }
