# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Venv = Join-Path $Root ".venv"
if (Test-Path $Venv) { Remove-Item -Recurse -Force $Venv }

$PyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
if (-not $PyLauncher) { $PyLauncher = Get-Command "py" -ErrorAction SilentlyContinue }
if (-not $PyLauncher) { throw "The Windows Python launcher ('py') was not found." }

& $PyLauncher.Source -3.11 -m venv $Venv
if ($LASTEXITCODE -ne 0) { throw "Failed to create the Python 3.11 environment." }

$Python = Join-Path $Venv "Scripts\python.exe"
& $Python -c "import struct,sys; assert sys.version_info[:2] == (3,11), sys.version; assert struct.calcsize('P') * 8 == 64"
if ($LASTEXITCODE -ne 0) { throw "SignalDojo requires 64-bit Python 3.11." }
& $Python -m pip install --disable-pip-version-check --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip." }
& $Python -m pip install --disable-pip-version-check -r "$Root\requirements-dev.txt"
if ($LASTEXITCODE -ne 0) { throw "Failed to install build dependencies." }
Write-Host "Environment ready: $Venv" -ForegroundColor Green
