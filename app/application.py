# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Application creation, logging, resources and plugin startup."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QSettings, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.version import APP_NAME, ORGANISATION, VERSION


def user_data_dir() -> Path:
    root = Path.home() / ".signaldojo"
    root.mkdir(parents=True, exist_ok=True)
    return root


def resource_path(relative: str) -> Path:
    """Resolve a bundled resource from either a source checkout or packaged runtime."""
    bundle_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return bundle_root / relative


def configure_logging() -> Path:
    log_dir = user_data_dir() / "logs"; log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "signaldojo.log"
    root = logging.getLogger(); root.setLevel(logging.INFO); root.handlers.clear()
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    rotating = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8"); rotating.setFormatter(formatter)
    console = logging.StreamHandler(); console.setFormatter(formatter)
    root.addHandler(rotating); root.addHandler(console)
    return log_path


def load_application_plugins() -> list[str]:
    from app.core.blocks import load_plugins
    return load_plugins([resource_path("app/plugins"), user_data_dir() / "plugins"])


def create_application(argv: list[str] | None = None) -> QApplication:
    configure_logging()
    QCoreApplication.setOrganizationName(ORGANISATION); QCoreApplication.setApplicationName(APP_NAME); QCoreApplication.setApplicationVersion(VERSION)
    app = QApplication(argv or sys.argv)
    app.setApplicationDisplayName(APP_NAME)
    icon_path = resource_path("resources/signaldojo.ico")
    if icon_path.exists(): app.setWindowIcon(QIcon(str(icon_path)))
    app.setStyle("Fusion")
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    load_application_plugins()
    return app


def settings() -> QSettings:
    return QSettings(ORGANISATION, APP_NAME)
