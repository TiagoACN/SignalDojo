# Packaging Guide

## Prerequisites

- 64-bit Windows 10 or 11
- Python 3.11 available through the `py` launcher
- Inno Setup 6

## Complete build

```powershell
powershell -ExecutionPolicy Bypass -File .\build_scripts\build_windows.ps1
```

The script creates a clean isolated build environment, installs pinned dependencies, validates and compiles every source file under Python 3.11, runs pytest, builds with PyInstaller, verifies the frozen executable, requires Inno Setup for the full installer, and writes SHA-256 checksums. It stops immediately if any stage or expected output fails.

## Staged commands

```powershell
.\build_scripts\create_environment.ps1
.\build_scripts\run_tests.ps1
.\build_scripts\build_executable.ps1
.\build_scripts\verify_packaged_imports.ps1
.\build_scripts\smoke_test.ps1
.\build_scripts\build_installer.ps1
```

Validate the installer on clean Windows 10 and Windows 11 virtual machines. Test installation without Python, file association, Start menu launch, all three examples, export permissions, uninstall, upgrade preservation and non-administrator installation.

## Packaged-module verification

The PyInstaller specification analyses `signaldojo_launcher.py`, explicitly collects every `app.*` submodule and applies `pyinstaller_hooks/hook-app.py`. After freezing, `verify_packaged_imports.ps1` runs `SignalDojo.exe --packaging-self-test`. The build stops before installer creation if any startup-critical module—such as `app.core.blocks`—is absent.

Always build from a clean tree. The complete build script removes `build`, `dist`, `release` and `.venv-build`; do not copy files from an older `dist` folder into the new package.

## Portable-only build

When Inno Setup is intentionally unavailable, build the tested portable package without an installer:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_scripts\build_windows.ps1 -PortableOnly
```

A normal build without `-PortableOnly` treats a missing installer compiler or missing setup executable as a release failure.

## SignalDojo 1.2 release outputs

A complete 1.2.6 build must produce:

```text
dist\SignalDojo\SignalDojo.exe
release\SignalDojo-1.2.6-win64-portable.zip
release\SignalDojo-1.2.6-win64-setup.exe
release\SignalDojo-1.2.6-source.zip
release\SHA256SUMS.txt
```

The packaged-import self-test includes `app.campaign`, `app.ui.campaign` and `app.exporters.campaign_report`. The Windows test stage executes the campaign Qt model/view smoke tests before freezing.

The Inno Setup AppId is intentionally unchanged so installing 1.2 upgrades SignalDojo 1.1 in place. User projects/campaigns, `%USERPROFILE%\.signaldojo\settings`, recovery data and user plugins are outside the installation directory and are not removed during a normal upgrade or uninstall.

## GPL release obligations

SignalDojo 1.2.6 is licensed under `GPL-3.0-or-later`. Publish the complete corresponding source archive beside every official installer and portable archive. The source must match the binary release and include the PyInstaller specification, dependency pins, Inno Setup script and build scripts.

The installer uses `InfoBeforeFile=OPEN_SOURCE_NOTICE.txt` rather than treating the GPL as a conventional EULA that must be accepted merely to run the software. The packaged distribution includes `LICENSE`, `COPYING`, `COPYRIGHT`, `LICENSES.md`, `PREVIOUS_MIT_NOTICE.txt`, `TRADEMARK_POLICY.md` and `SOURCE_CODE.md`.

Do not remove third-party notices. Unofficial modified distributions should use distinct primary branding and clearly identify themselves, while retaining all GPL rights. See `OPEN_SOURCE_DISTRIBUTION.md`.
