# SignalDojo 1.2.4 validation

SignalDojo 1.2.4 adds controlled workflow-result display and lazy result-dock creation.

## Results

- 236 automated tests passed in the available cross-platform environment.
- Python 3.11 grammar compatibility passed for 72 source files.
- All Python sources compiled successfully.
- Result policy tests cover Smart, keep-closed and open-all modes, selected-result prioritisation, preservation of user-visible tabs, and execution-summary fallback.
- Packaging-version consistency tests passed for application, PyInstaller resources, PowerShell build scripts, Inno Setup and documentation.
- The bundled motor-current campaign reopened and reused all eight unchanged persisted runs.

## Windows-only release gate

The included Windows pipeline additionally installs PySide6, runs the UI smoke suite, freezes the application with PyInstaller, verifies packaged imports, smoke-tests the executable and builds the Inno Setup installer. Those Windows-only stages cannot be executed on this Linux validation host.
