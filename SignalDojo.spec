# -*- mode: python ; coding: utf-8 -*-
# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""PyInstaller definition for the SignalDojo Windows onedir distribution."""

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve()
# Make the local ``app`` package unambiguous during analysis, even if the build
# environment happens to contain a third-party top-level package also named app.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


datas = [
    (str(ROOT / "examples"), "examples"),
    (str(ROOT / "resources"), "resources"),
    (str(ROOT / "documentation"), "documentation"),
    (str(ROOT / "README.md"), "."),
    (str(ROOT / "LICENSE"), "."),
    (str(ROOT / "COPYING"), "."),
    (str(ROOT / "COPYRIGHT"), "."),
    (str(ROOT / "CREDITS.md"), "."),
    (str(ROOT / "LICENSES.md"), "."),
    (str(ROOT / "PREVIOUS_MIT_NOTICE.txt"), "."),
    (str(ROOT / "TRADEMARK_POLICY.md"), "."),
    (str(ROOT / "SOURCE_CODE.md"), "."),
]

for distribution in (
    "PySide6",
    "numpy",
    "scipy",
    "pandas",
    "pyqtgraph",
    "matplotlib",
    "openpyxl",
    "nptdms",
    "tables",
):
    try:
        datas += copy_metadata(distribution)
    except Exception:
        # Missing optional package metadata does not prevent the packaged application from being analysed.
        pass

# These explicit names document the startup-critical modules and provide a
# fallback if automatic package discovery changes in a future PyInstaller.
project_hiddenimports = [
    "app",
    "app.application",
    "app.version",
    "app.campaign",
    "app.campaign.models",
    "app.campaign.discovery",
    "app.campaign.execution",
    "app.campaign.metrics",
    "app.campaign.requirements",
    "app.campaign.comparison",
    "app.campaign.workflow_adapter",
    "app.core",
    "app.core.blocks",
    "app.core.expression",
    "app.core.models",
    "app.core.workflow",
    "app.exporters",
    "app.exporters.project_report",
    "app.exporters.campaign_report",
    "app.plugins",
    "app.project",
    "app.project.io",
    "app.ui",
    "app.ui.dialogs",
    "app.ui.campaign",
    "app.ui.main_window",
    "app.ui.node_editor",
    "app.ui.properties",
    "app.ui.results",
    "app.ui.scope",
    "app.update",
    "app.update.service",
]

third_party_hiddenimports = [
    "PySide6.QtSvg",
    "PySide6.QtPrintSupport",
    "pyqtgraph.graphicsItems.PlotItem",
    "pyqtgraph.exporters",
    "matplotlib.backends.backend_agg",
    "matplotlib.backends.backend_pdf",
    "openpyxl",
    "nptdms",
    "tables",
    "scipy.signal",
    "scipy.stats",
    "scipy.integrate",
]

hiddenimports = sorted(
    set(project_hiddenimports + collect_submodules("app") + third_party_hiddenimports)
)

analysis = Analysis(
    [str(ROOT / "signaldojo_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(ROOT / "pyinstaller_hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SignalDojo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "resources" / "signaldojo.ico"),
    version=str(ROOT / "resources" / "version_info.txt"),
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SignalDojo",
)
