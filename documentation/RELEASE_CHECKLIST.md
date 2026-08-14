# Release Checklist

- [ ] Version updated in `app/application.py`, `pyproject.toml`, Inno Setup and Windows version resource.
- [ ] Pinned dependencies install from a clean Python 3.11 environment.
- [ ] `build_scripts\check_python311_compatibility.py` passes in the clean Python 3.11 environment.
- [ ] `python -m compileall -q app tests build_scripts pyinstaller_hooks signaldojo_launcher.py` passes.
- [ ] Full automated test suite passes.
- [ ] All three workflow examples and the eight-run motor-current campaign execute and export expected files.
- [ ] PyInstaller executable passes `verify_packaged_imports.ps1`.
- [ ] PyInstaller executable passes `smoke_test.ps1`.
- [ ] Installer tested on clean 64-bit Windows 10 and Windows 11.
- [ ] `.sdojo` association opens projects and 1.1 projects migrate without modification.
- [ ] Motor-current campaign acceptance: classifications, reference comparison, PDF/XLSX/CSV, reopen/reuse and selective invalidation pass.
- [ ] Dashboard sorting/filtering remains responsive with 1,000 run records.
- [ ] Campaign cancellation, retry and report cancellation tested on Windows.
- [ ] Upgrade preserves `%USERPROFILE%\.signaldojo`, projects and settings.
- [ ] HTML/PDF reports and PNG/SVG/PDF plot exports reviewed.
- [ ] Logs and diagnostics contain no source-data values unless explicitly exported.
- [ ] Third-party licence notice reviewed.
- [ ] SHA-256 checksums generated and verified.

## Open-source release

- [ ] Root `LICENSE` and `COPYING` contain the unmodified GNU GPLv3 text.
- [ ] Package metadata declares `GPL-3.0-or-later`.
- [ ] Installer displays `OPEN_SOURCE_NOTICE.txt` through `InfoBeforeFile`.
- [ ] Full licence, copyright, third-party notices, trademark policy and source notice are present in the portable and installed distributions.
- [ ] Exact corresponding source archive is published beside every binary download.
- [ ] Source archive contains build scripts and dependency pins for the released binaries.
- [ ] Modified/unofficial build guidance does not restrict GPL redistribution rights.
- [ ] SignalDojo name/logo usage is reviewed separately under `TRADEMARK_POLICY.md`.

## Production-readiness audit

- [ ] No TODO, FIXME, HACK, XXX, stub, mock-success or placeholder production behaviour remains in `app/`, `installer/` or release build scripts.
- [ ] Production URLs use `https://signaldojo.org` or another explicitly approved project endpoint; example domains are restricted to clearly named documentation examples only.
- [ ] Windows file metadata and installer attribution credit Tiago Alvarez Calderon Newton and SignalDojo Contributors.
- [ ] PyInstaller `debug=False` remains enabled for release builds.
- [ ] Installer open-source notice, GPL files, copyright notice, credits and trademark policy are bundled.
- [ ] No secrets, private keys, tokens or local developer paths are present in the source or packaged runtime.
