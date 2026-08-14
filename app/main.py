# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""SignalDojo executable entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QSplashScreen

from app.application import create_application, resource_path
from app.ui.main_window import MainWindow


def main() -> int:
    app = create_application(sys.argv)
    splash_path = resource_path("resources/signaldojo.png")
    splash = QSplashScreen(QPixmap(str(splash_path))) if splash_path.exists() else None
    if splash:
        splash.showMessage("Loading SignalDojo…", alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter); splash.show(); app.processEvents()
    window = MainWindow()
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        if candidate.suffix.lower() == ".sdojo" and candidate.exists(): window.open_project_path(candidate, confirm_discard=False)
    window.show()
    if splash: splash.finish(window)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
