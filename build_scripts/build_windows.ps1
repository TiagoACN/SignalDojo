# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

[CmdletBinding()]
param(
    [switch]$PortableOnly
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
$Version = "1.2.6"
$Venv = Join-Path $Root ".venv-build"
$Release = Join-Path $Root "release"

function Invoke-Checked {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter()][string[]]$ArgumentList = @()
    )

    & $FilePath @ArgumentList
    $ExitCode = $LASTEXITCODE
    if ($null -eq $ExitCode) {
        $ExitCode = 0
    }
    if ($ExitCode -ne 0) {
        $RenderedArguments = $ArgumentList -join " "
        throw ("Command failed with exit code {0}: {1} {2}" -f $ExitCode, $FilePath, $RenderedArguments)
    }
}

function Find-InnoSetupCompiler {
    $Candidates = @()
    $ProgramFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $ProgramFiles64 = [Environment]::GetEnvironmentVariable("ProgramFiles")
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
    return $Candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

Write-Host "== SignalDojo clean Windows build ==" -ForegroundColor Cyan

$PyLauncher = Get-Command "py.exe" -ErrorAction SilentlyContinue
if (-not $PyLauncher) {
    $PyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
}
if (-not $PyLauncher) {
    throw "The Windows Python launcher ('py') was not found. Install 64-bit Python 3.11 and enable the Python launcher."
}

$Iscc = Find-InnoSetupCompiler
if ((-not $PortableOnly) -and (-not $Iscc)) {
    throw "Inno Setup 6 was not found. Install Inno Setup 6, or rerun this script with -PortableOnly to build only the portable application."
}

$PathsToClean = @(
    (Join-Path $Root "build"),
    (Join-Path $Root "dist"),
    $Release,
    $Venv
)
foreach ($PathToClean in $PathsToClean) {
    if (Test-Path $PathToClean) {
        Remove-Item -Recurse -Force $PathToClean
    }
}
New-Item -ItemType Directory -Force -Path $Release | Out-Null

Invoke-Checked -FilePath $PyLauncher.Source -ArgumentList @("-3.11", "-m", "venv", $Venv)

$Python = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Python 3.11 virtual environment creation did not produce: $Python"
}

Invoke-Checked -FilePath $Python -ArgumentList @("-c", "import struct,sys; assert sys.version_info[:2] == (3,11), sys.version; assert struct.calcsize('P') * 8 == 64, 'SignalDojo requires 64-bit Python'")
Invoke-Checked -FilePath $Python -ArgumentList @("-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip")
Invoke-Checked -FilePath $Python -ArgumentList @("-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements-dev.txt")

Write-Host "== Validating Python 3.11 source compatibility ==" -ForegroundColor Cyan
Invoke-Checked -FilePath $Python -ArgumentList @("build_scripts\check_python311_compatibility.py")
Invoke-Checked -FilePath $Python -ArgumentList @("-m", "compileall", "-q", "app", "tests", "build_scripts", "pyinstaller_hooks", "signaldojo_launcher.py")

Write-Host "== Running tests ==" -ForegroundColor Cyan
Invoke-Checked -FilePath $Python -ArgumentList @("-m", "pytest", "-q")

Write-Host "== Building application ==" -ForegroundColor Cyan
Invoke-Checked -FilePath $Python -ArgumentList @("-m", "PyInstaller", "--noconfirm", "--clean", "SignalDojo.spec")

$Distribution = Join-Path $Root "dist\SignalDojo"
$Exe = Join-Path $Distribution "SignalDojo.exe"
if (-not (Test-Path $Exe)) {
    throw "PyInstaller did not produce the expected executable: $Exe"
}

Write-Host "== Verifying packaged imports ==" -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "verify_packaged_imports.ps1")

Write-Host "== Smoke-testing packaged executable ==" -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "smoke_test.ps1")

Write-Host "== Creating portable archive ==" -ForegroundColor Cyan
$PortableArchive = Join-Path $Release "SignalDojo-$Version-win64-portable.zip"
Compress-Archive -Path (Join-Path $Distribution "*") -DestinationPath $PortableArchive -CompressionLevel Optimal -Force
if (-not (Test-Path $PortableArchive)) {
    throw "Portable archive creation failed: $PortableArchive"
}

$Installer = Join-Path $Release "SignalDojo-$Version-win64-setup.exe"
if (-not $PortableOnly) {
    Write-Host "== Building installer ==" -ForegroundColor Cyan
    Invoke-Checked -FilePath $Iscc -ArgumentList @((Join-Path $Root "installer\SignalDojo.iss"))
    if (-not (Test-Path $Installer)) {
        throw "Inno Setup completed without producing the expected installer: $Installer"
    }
}

Write-Host "== Creating corresponding source archive ==" -ForegroundColor Cyan
$SourceArchive = Join-Path $Release "SignalDojo-$Version-source.zip"
$SourceStageParent = Join-Path ([IO.Path]::GetTempPath()) ("SignalDojo-source-" + [Guid]::NewGuid().ToString("N"))
$SourceStage = Join-Path $SourceStageParent "SignalDojo-$Version"
New-Item -ItemType Directory -Force -Path $SourceStage | Out-Null
try {
    $ExcludedTopLevel = @(
        ".git", ".venv", ".venv-build", ".pytest_cache", ".mypy_cache", ".ruff_cache",
        "build", "dist", "release"
    )
    Get-ChildItem -LiteralPath $Root -Force | Where-Object { $ExcludedTopLevel -notcontains $_.Name } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $SourceStage -Recurse -Force
    }
    Get-ChildItem -LiteralPath $SourceStage -Directory -Recurse -Force | Where-Object {
        $_.Name -in @("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")
    } | Sort-Object FullName -Descending | Remove-Item -Recurse -Force
    Compress-Archive -Path $SourceStage -DestinationPath $SourceArchive -CompressionLevel Optimal -Force
}
finally {
    Remove-Item -LiteralPath $SourceStageParent -Recurse -Force -ErrorAction SilentlyContinue
}
if (-not (Test-Path $SourceArchive)) {
    throw "Corresponding source archive creation failed: $SourceArchive"
}

Write-Host "== Creating checksums ==" -ForegroundColor Cyan
$ChecksumFile = Join-Path $Release "SHA256SUMS.txt"
Remove-Item -Force -ErrorAction SilentlyContinue $ChecksumFile
Get-ChildItem $Release -File | Where-Object { $_.Name -ne "SHA256SUMS.txt" } | Sort-Object Name | ForEach-Object {
    $Hash = Get-FileHash $_.FullName -Algorithm SHA256
    $ChecksumLine = "{0}  {1}" -f $Hash.Hash.ToLowerInvariant(), $_.Name
    $ChecksumLine | Add-Content -Encoding ascii $ChecksumFile
}
if (-not (Test-Path $ChecksumFile)) {
    throw "Checksum creation failed: $ChecksumFile"
}

Write-Host "Build complete." -ForegroundColor Green
Write-Host "Application: $Exe"
Write-Host "Portable archive: $PortableArchive"
Write-Host "Corresponding source: $SourceArchive"
if (-not $PortableOnly) {
    Write-Host "Installer: $Installer"
}
Write-Host "Checksums: $ChecksumFile"
