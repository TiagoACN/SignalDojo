# SignalDojo 1.2.6 Validation Report

## Release purpose

SignalDojo 1.2.6 is a production-hardening and attribution release built on the GPLv3+ SignalDojo 1.2.5 codebase. It preserves application behaviour while finalising creator credit, installer/legal metadata, production-facing URLs and automated release-readiness checks.

## Automated validation

- **248 tests collected and passed** in the available cross-platform environment.
- Python 3.11 grammar validation passed for **74 source files**.
- `compileall` passed for application code, tests, build helpers and launcher code.
- A Python wheel for `signaldojo-1.2.6` built successfully with the installed build toolchain using build isolation disabled because this execution environment has no internet access.
- Production-readiness tests reject TODO/FIXME/HACK/XXX/placeholder markers in production-facing code, example domains in runtime/installer files, debug PyInstaller releases, missing creator attribution and obvious secret-bearing files.
- The built-in registry remains at **119 blocks**; no block identifiers or project schema behaviours were changed by this release.

No existing tests were deleted, skipped or weakened for this release.

## Attribution and open-source packaging

The release now consistently credits **Tiago Alvarez Calderon Newton** as SignalDojo's creator and maintainer, together with the SignalDojo contributor community. Attribution is present in:

- `COPYRIGHT`
- `CREDITS.md`
- `pyproject.toml`
- Windows executable version metadata
- Inno Setup publisher and copyright metadata
- installer open-source notice
- application About dialog
- project source SPDX headers

SignalDojo remains licensed under **GPL-3.0-or-later**. The installer continues to present an informational open-source notice rather than a conventional acceptance-based EULA. The complete GPL, corresponding-source information, third-party notices, previous MIT notice and separate trademark policy remain bundled.

## Production-hardening audit

The release audit confirmed:

- No unfinished TODO, FIXME, HACK, XXX, stub or placeholder markers are present in `app/`, `installer/` or release build scripts.
- No `example.org` or `example.com` URLs remain in runtime or installer code.
- PyInstaller remains configured with `debug=False`.
- Project saves retain atomic staging-and-replace behaviour.
- Application resources resolve consistently from source checkouts and packaged runtimes.
- Release metadata points to `https://signaldojo.org`.
- The package includes `CREDITS.md` alongside the licence and trademark documents.
- No obvious credential, token or private-key files are present in the distributable source tree.

## Windows packaging boundary

A native Windows `.exe` and Inno Setup installer cannot be built or executed on this Linux validation host. The included Windows release pipeline remains responsible for the final platform-specific gate. It creates an isolated 64-bit Python 3.11 environment, installs pinned dependencies, runs compatibility checks and the full test suite, freezes SignalDojo with PyInstaller, verifies packaged imports, smoke-tests the executable, builds the installer and produces release checksums.

Expected Windows outputs:

```text
dist\SignalDojo\SignalDojo.exe
release\SignalDojo-1.2.6-win64-portable.zip
release\SignalDojo-1.2.6-win64-setup.exe
release\SignalDojo-1.2.6-source.zip
release\SHA256SUMS.txt
```

The actual Windows installer must still be built and smoke-tested on Windows before publication.
