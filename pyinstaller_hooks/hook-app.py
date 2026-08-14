# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Ensure every first-party SignalDojo package module is frozen.

SignalDojo registers many blocks and optional UI components at import time.
Collecting the full first-party package prevents a valid source tree from
producing an executable with an incomplete PYZ archive.
"""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("app")
