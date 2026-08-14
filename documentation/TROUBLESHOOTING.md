# Troubleshooting

## A cut-off exceeds Nyquist

The maximum representable frequency is half the sample rate. Reduce the cut-off or explicitly resample to a higher rate when scientifically justified.

## Signals have incompatible time vectors

SignalDojo never silently truncates or resamples. Use Synchronise Signals, Resample or Interpolate.

## Zero-phase filter says the signal is too short

Reduce filter order/taps, crop less aggressively, or disable zero-phase processing.

## TDMS or HDF5 import fails

The installer includes `nptdms` and PyTables. In a development environment, reinstall `requirements.txt`. Some HDF5 files contain several keys; convert or select an unambiguous table.

## A source file moved

Opening a project prompts to relink missing Import Data files. Keeping datasets beside the `.sdojo` file enables portable relative references.

## Application fails to start

Open `%USERPROFILE%\.signaldojo\logs\signaldojo.log`, then run the packaged smoke test. The Diagnostics dialog lists package and OS versions when the UI opens.

## Packaged build reports `No module named app.core.blocks`

Use SignalDojo 1.0.2 or newer. Delete `build`, `dist`, `.venv-build` and any older installer output, then rebuild with `build_scripts\build_windows.ps1`. The corrected specification explicitly collects every `app.*` module and runs a packaged-import verification before creating the installer. Do not reuse the old `dist` directory.

## Source launch reports `SyntaxError` in an f-string

Use SignalDojo 1.0.2 or newer and extract it into a new folder rather than overwriting an older source tree. Run `py -3.11 build_scripts\check_python311_compatibility.py` from the project root before launch. Version 1.0.2 removes a Python 3.12-only f-string that was invalid under the documented Python 3.11 runtime.


## Ports leave blue afterimages while moving a block

This was fixed in SignalDojo 1.0.3. The ports extend beyond the node rectangle, so older builds using bounding-rectangle viewport updates could leave the outer halves of ports on screen until the next full redraw. Upgrade to 1.0.3 or replace `app/ui/node_editor.py` with the 1.0.3 version. As a temporary workaround in older source trees, change `BoundingRectViewportUpdate` to `FullViewportUpdate`; this is reliable but redraws the whole canvas during movement.
