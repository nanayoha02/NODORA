"""Punto de entrada de la interfaz."""
from __future__ import annotations

import os
import sys

from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from .core.config import APP_NAME
from .ui import theme
from .ui.main_window import MainWindow
from .ui.state import AppState


def resource(*parts: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, *parts)


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)
    icon_path = resource("assets", "nodora.ico")
    icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon(resource("assets", "nodora.png"))
    app.setWindowIcon(icon)
    state = AppState()
    hints = QGuiApplication.styleHints()
    dark = hasattr(hints, "colorScheme") and hints.colorScheme() == hints.colorScheme().Dark
    theme.set_theme(state.cfg.theme, dark)
    app.setStyleSheet(theme.stylesheet())
    win = MainWindow(state, icon)
    if "--minimized" in argv and win.tray:
        pass  # arranca en la bandeja
    else:
        win.show()
    return app.exec()
