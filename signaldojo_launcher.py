# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""PyInstaller-safe root entry point for SignalDojo.

Keeping the executable launcher outside the :mod:`app` package avoids ambiguity
when PyInstaller analyses a package module as a script.  It also provides a
non-interactive packaged-import test used by the Windows build pipeline.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path


CRITICAL_MODULES: tuple[str, ...] = (
    "app",
    "app.application",
    "app.version",
    "app.campaign.models",
    "app.campaign.discovery",
    "app.campaign.execution",
    "app.campaign.requirements",
    "app.campaign.comparison",
    "app.core",
    "app.core.blocks",
    "app.core.expression",
    "app.core.models",
    "app.core.workflow",
    "app.exporters.project_report",
    "app.exporters.campaign_report",
    "app.project.io",
    "app.ui.dialogs",
    "app.ui.campaign",
    "app.ui.main_window",
    "app.ui.node_editor",
    "app.ui.properties",
    "app.ui.results",
    "app.ui.scope",
    "app.update.service",
)


def verify_packaged_imports() -> int:
    """Import modules required at startup and return a process exit code.

    The error is written beside the executable where possible so a windowed
    PyInstaller build still leaves a useful diagnostic if an import is absent.
    """

    try:
        for module_name in CRITICAL_MODULES:
            importlib.import_module(module_name)
    except Exception as exc:  # pragma: no cover - exercised by packaged build
        try:
            executable_dir = Path(sys.executable).resolve().parent
            (executable_dir / "packaging-self-test-error.txt").write_text(
                f"Failed while importing {module_name}: {exc!r}\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        return 2
    return 0


def main() -> int:
    if "--packaging-self-test" in sys.argv:
        return verify_packaged_imports()

    from app.main import main as application_main

    return application_main()


if __name__ == "__main__":
    raise SystemExit(main())
