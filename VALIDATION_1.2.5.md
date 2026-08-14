# SignalDojo 1.2.6 Validation Report

## Scope

SignalDojo 1.2.6 changes the project licence from MIT to GNU GPL version 3 or any later version (`GPL-3.0-or-later`), updates the Windows installer presentation, adds a separate trademark policy, exposes legal notices in the application and extends the release pipeline to create a corresponding-source archive.

No signal-processing, workflow, campaign, project-format or result-management behaviour was intentionally changed.

## Baseline

The untouched SignalDojo 1.2.4 source archive was extracted independently.

- Existing tests collected: **236**
- Existing test suite result: **passed**

## Final automated validation

- Final tests collected: **243**
- Final test suite result: **passed**
- PySide6 graphical smoke module: **1 module skipped** because this Linux validation environment does not provide the Windows PySide6 build environment expected by that module
- Python 3.11 compatibility validation: **passed for 73 source files**
- Repository-wide Python compilation: **passed**
- Python wheel metadata/build: **passed**
- Built wheel metadata version: **1.2.6**

## Added release-contract tests

The new tests verify that:

- `LICENSE` and `COPYING` contain the complete GNU GPLv3 text.
- Package metadata declares `GPL-3.0-or-later`.
- The installer uses an informational `InfoBeforeFile` page rather than a compulsory `LicenseFile` acceptance page.
- The informational page states the no-warranty and redistribution position.
- PyInstaller includes the full licence, copyright notice, third-party notices, retained historical MIT notice, trademark policy and corresponding-source guidance.
- The trademark policy explicitly preserves GPL copying, modification and redistribution rights.
- The application exposes Open Source Licence and Trademark Policy commands and displays appropriate legal notices.
- The Windows build script is configured to generate `SignalDojo-1.2.6-source.zip` beside the installer and portable package.

## Packaging checks

The following release metadata is aligned to version 1.2.6:

- `app/version.py`
- `pyproject.toml`
- Windows version resources
- PyInstaller specification
- Inno Setup script
- Windows build scripts
- Documentation and release filenames
- Campaign acceptance fixtures that track the running SignalDojo version

Every project-owned Python source/build file in the audited scope contains:

```text
SPDX-License-Identifier: GPL-3.0-or-later
```

## Windows validation boundary

A Windows `.exe` and Inno Setup installer cannot be compiled or executed on this Linux host. The Windows build pipeline remains responsible for:

1. Running the full tests in its Python 3.11/PySide6 environment.
2. Building and smoke-testing the PyInstaller application.
3. Building the Inno Setup installer.
4. Creating the portable archive and exact corresponding-source archive.
5. Producing SHA-256 checksums.

The installer configuration was validated statically, but the final setup executable must still be built and tested on clean Windows 10 and Windows 11 systems.

## Legal review boundary

The GNU GPL text is included verbatim. `TRADEMARK_POLICY.md` is explicitly marked as a draft for legal review. The project maintainer should confirm copyright ownership and obtain legal advice before making trademark-enforcement claims or publishing the policy as final.
