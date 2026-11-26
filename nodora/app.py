"""Punto de entrada de la interfaz."""
from __future__ import annotations

import os
import sys
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from .core.config import APP_NAME, Settings
from .ui import theme
from .ui.main_window import MainWindow
from .ui.splash import Splash
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
    hints = QGuiApplication.styleHints()
    dark = hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark
    theme.apply_config(Settings.load(), dark)          # el tema elegido ya se ve en la pantalla de carga
    quiet = "--minimized" in argv                      # arranque en la bandeja: sin pantalla de carga
    splash = None if quiet else Splash(resource("assets", "nodora_logo.png"))
    t0 = time.monotonic()
    if splash:
        splash.show()
        splash.set_progress(0.12, "Cargando configuración…")
        app.processEvents()
    state = AppState()
    theme.apply_config(state.cfg, dark)
    app.setStyleSheet(theme.stylesheet())
    if splash:
        splash.set_progress(0.45, "Aplicando estilo…")
        app.processEvents()
    win = MainWindow(state, icon)
    app._nodora_refs = (win, splash)                   # evita que se recojan de memoria
    if quiet and win.tray:
        return app.exec()                              # arranca en la bandeja
    if not splash:
        win.show()
        return app.exec()
    splash.set_progress(0.85, "Preparando el panel…")
    wait = max(0, 1900 - int((time.monotonic() - t0) * 1000))     # mínimo ~1,9 s para que se aprecie la animación

    def reveal():
        win.show()
        splash.finish()
    QTimer.singleShot(wait, reveal)
    return app.exec()
