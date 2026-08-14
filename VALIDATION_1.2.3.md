# SignalDojo 1.2.3 validation

## Scope

SignalDojo 1.2.3 redesigns the **Create New Test Campaign** dialog without changing campaign persistence, execution, metric, requirement or report schemas.

## Automated validation

- 228 cross-platform automated tests passed.
- The PySide6 UI smoke-test module remains enabled for the Windows build environment and was skipped on this Linux validation host because PySide6 is unavailable.
- Python 3.11 grammar validation passed for 70 source files.
- All Python files compiled successfully.
- Packaging configuration tests passed for version 1.2.3.

## UI regression coverage

The source and Windows UI suites verify:

- Screen-aware setup-dialog sizing and a minimum size below 1366×768.
- Five guided setup steps with independent scrolling.
- Always-visible Back, Next, Cancel and Save Campaign actions.
- Separate input mapping and metadata extraction panels.
- Separate execution, report and campaign-information panels.
- Dedicated dark/light styling and validation-banner styling.
- Existing automatic Publish Metric detection.
- Existing campaign-model read/write behaviour.

## Windows release gate

Run `build_scripts\build_windows.ps1` on 64-bit Windows with Python 3.11 and Inno Setup 6. The script runs the real PySide6 UI tests, builds the portable application, verifies packaged imports and produces:

- `release\SignalDojo-1.2.3-win64-portable.zip`
- `release\SignalDojo-1.2.3-win64-setup.exe`
- `release\SHA256SUMS.txt`
