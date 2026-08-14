# Open-Source Distribution Guide

SignalDojo 1.2.6 is licensed under **GNU GPL version 3 or any later version** (`GPL-3.0-or-later`).

## User freedoms

The licence permits users to run, inspect, copy, modify and redistribute SignalDojo. It also permits charging for copies or support. The GPL does not require payment and does not prohibit redistribution.

## Copyleft obligations

Anyone conveying a modified source version must prominently identify the changes and license the covered work under the GPL. Anyone conveying binaries must also provide the corresponding source through one of the methods allowed by GPL section 6.

Official release pages should therefore publish these files together:

```text
SignalDojo-1.2.6-win64-setup.exe
SignalDojo-1.2.6-win64-portable.zip
SignalDojo-1.2.6-source.zip
SHA256SUMS.txt
```

The source archive must correspond to the exact binary release and include the application source, PyInstaller specification, dependency pins, installer script and build/test scripts.

## Official and unofficial builds

The SignalDojo project may publish a trusted, tested official Windows installer. Third parties remain free to compile and redistribute the GPL-covered software. Modified builds should use different primary branding and clearly state that they are unofficial, in accordance with `TRADEMARK_POLICY.md`.

The trademark policy is separate from the GPL and must not be used to prevent lawful copying, modification or redistribution of the code.

## Installer presentation

The installer displays `installer/OPEN_SOURCE_NOTICE.txt` using Inno Setup’s `InfoBeforeFile` page. It intentionally does not present the GPL as a conventional EULA that must be accepted merely to run the program. The full licence and notices are installed with the application.

## Third-party components

SignalDojo includes libraries under their own licences. Preserve `LICENSES.md`, `PREVIOUS_MIT_NOTICE.txt`, package metadata and any required notices. Distributors must independently verify the exact dependency versions they ship.
