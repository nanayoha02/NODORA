"""Inicio con Windows (clave HKCU\\...\\Run del usuario actual; no requiere administrador)."""
from __future__ import annotations

import sys

_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_NAME = "NODORA"


def supported() -> bool:
    return sys.platform.startswith("win")


def command() -> str:
    exe = sys.executable
    if getattr(sys, "frozen", False):
        return f'"{exe}" --minimized'
    return f'"{exe}" -m nodora --minimized'


def set_enabled(on: bool) -> bool:
    if not supported():
        return False
    import winreg  # noqa: WPS433
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, _NAME, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(k, _NAME)
            except FileNotFoundError:
                pass
    return True
