# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Run create_environment.ps1 first." }

Set-Location $Root
& $Python build_scripts\check_python311_compatibility.py
if ($LASTEXITCODE -ne 0) { throw "Python 3.11 compatibility validation failed." }
& $Python -m compileall -q app tests build_scripts pyinstaller_hooks signaldojo_launcher.py
if ($LASTEXITCODE -ne 0) { throw "Source compilation failed." }
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
& $Python -m PyInstaller --noconfirm --clean SignalDojo.spec
$ExitCode = $LASTEXITCODE
if ($null -eq $ExitCode) { $ExitCode = 0 }
if ($ExitCode -ne 0) { throw ("PyInstaller failed with exit code {0}." -f $ExitCode) }

$Exe = Join-Path $Root "dist\SignalDojo\SignalDojo.exe"
if (-not (Test-Path $Exe)) { throw "Executable build failed: $Exe was not produced." }

& (Join-Path $PSScriptRoot "verify_packaged_imports.ps1")
Write-Host "Executable build complete: $Exe" -ForegroundColor Green
