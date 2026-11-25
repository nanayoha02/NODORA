"""Paletas, tipografía y hoja de estilos de NODORA.

Temas: «plum» (Ciruela, predeterminado: fondo ciruela, pasteles y botones en píldora), «light» (claro, del
prototipo de Figma), «dark» (oscuro neutro) y «system»."""
from __future__ import annotations

_BASE = dict(radius=16, btn_r=10, input_r=10, rail=False, shell_margin=0, shell_radius=0,
             primary_fg="#1E1E1E", on_pastel="#1E1E1E", pastel=("#FFF1CC", "#E3F1E8", "#EDE6F7"))

LIGHT = {**_BASE, "bg": "#F3F0EA", "surface": "#FFFFFF", "sidebar": "#FFFFFF", "text": "#1E1E1E", "muted": "#7B7B7B",
         "border": "#E6E2DA", "accent": "#FFC22E", "accent_soft": "#FFF1CC", "accent_text": "#1E1E1E",
         "ok": "#2F7D52", "ok_bg": "#E3F1E8", "warn": "#B7791F", "warn_bg": "#FFF3D6",
         "err": "#B83A3A", "err_bg": "#FBE5E5", "info": "#4B6B8A", "row_alt": "#FAF8F4", "chart2": "#5E8071",
         "primary_bg": "#FFC22E"}
DARK = {**_BASE, "bg": "#161616", "surface": "#212121", "sidebar": "#1B1B1B", "text": "#F2F2F2", "muted": "#A0A0A0",
        "border": "#333333", "accent": "#FFC22E", "accent_soft": "#3A3220", "accent_text": "#FFC22E",
        "ok": "#6CC596", "ok_bg": "#1F3A2B", "warn": "#E6B04C", "warn_bg": "#3A3220",
        "err": "#E57A7A", "err_bg": "#3F2323", "info": "#8FB1D1", "row_alt": "#262626", "chart2": "#7FA895",
        "primary_bg": "#FFC22E"}
PLUM = {**_BASE, "bg": "#3A2F46", "backdrop": "#B9A7DA", "surface": "#4A4057", "sidebar": "#3A2F46", "text": "#F4F0FA",
        "muted": "#ABA1BA", "border": "#5D5270", "accent": "#D6C9FA", "accent_soft": "#FFFFFF", "accent_text": "#2A2433",
        "ok": "#8EE0B5", "ok_bg": "#2F4A42", "warn": "#F0C77A", "warn_bg": "#54452F",
        "err": "#FF9A9A", "err_bg": "#573038", "info": "#B7C6E6", "row_alt": "#53486A", "chart2": "#9FDCC4",
        "primary_bg": "#FFFFFF", "primary_fg": "#2A2433", "on_pastel": "#2A2433",
        "pastel": ("#CFC8EC", "#C9E8DD", "#EBDDC0"),
        "radius": 24, "btn_r": 18, "input_r": 16, "rail": True, "shell_margin": 18, "shell_radius": 38}

THEMES = {"light": LIGHT, "dark": DARK, "plum": PLUM}
FONT = '"Unbounded", "Syne", "Space Grotesk", "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif'
_current = dict(PLUM)
_current.setdefault("backdrop", _current["bg"])


def palette() -> dict:
    return _current


def set_theme(name: str, system_is_dark: bool = False) -> dict:
    if name == "system":
        name = "dark" if system_is_dark else "light"
    base = THEMES.get(name, PLUM)
    _current.clear()
    _current.update(base)
    _current.setdefault("backdrop", _current["bg"])
    return _current


def stylesheet() -> str:
    c = _current
    r, br, ir = c["radius"], c["btn_r"], c["input_r"]
    return f"""
* {{ font-family: {FONT}; font-size: 13px; color: {c['text']}; }}
QMainWindow, QWidget#root {{ background: {c['backdrop']}; }}
QFrame#shell, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {c['bg']}; }}
QFrame#shell {{ border-radius: {c['shell_radius']}px; }}
QWidget#sidebar {{ background: {c['sidebar']}; {'' if c['rail'] else 'border-right: 1px solid ' + c['border'] + ';'} }}
QLabel {{ background: transparent; }}
QLabel#pageTitle {{ font-size: 22px; font-weight: 600; }}
QLabel#pageSub, QLabel.muted, QLabel#muted {{ color: {c['muted']}; }}
QLabel#hero {{ font-size: 22px; font-weight: 600; }}
QLabel#bigNumber {{ font-size: 34px; font-weight: 600; }}
QLabel#cardTitle {{ font-size: 15px; font-weight: 600; }}
QLabel#eyebrow {{ color: {c['muted']}; font-size: 10px; letter-spacing: 1px; font-weight: 600; }}
QLabel#brand {{ font-size: 24px; font-weight: 700; letter-spacing: 1px; }}
QLabel#tagline {{ color: {c['muted']}; font-size: 14px; }}
QFrame#card {{ background: {c['surface']}; border: {'none' if c['rail'] else '1px solid ' + c['border']}; border-radius: {r}px; }}
QFrame#topbar {{ background: {c['surface']}; border: none; border-radius: {r}px; }}
QPushButton {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: {br}px;
               padding: 8px 18px; font-weight: 500; }}
QPushButton:hover {{ border-color: {c['accent']}; }}
QPushButton:disabled {{ color: {c['muted']}; background: {c['bg']}; }}
QPushButton#primary {{ background: {c['primary_bg']}; border-color: {c['primary_bg']}; color: {c['primary_fg']}; font-weight: 600; }}
QPushButton#primary:disabled {{ background: {c['border']}; color: {c['muted']}; border-color: {c['border']}; }}
QPushButton#danger {{ color: {c['err']}; border-color: {c['err']}; }}
QPushButton#nav {{ text-align: left; border: none; border-radius: 12px; padding: 11px 14px; background: transparent; }}
QPushButton#nav:hover {{ background: {c['row_alt']}; }}
QPushButton#nav:checked {{ background: {c['accent_soft']}; font-weight: 600; color: {c['accent_text']}; }}
QPushButton#rail {{ border: none; border-radius: 26px; padding: 0; background: transparent; font-size: 19px;
               color: {c['muted']}; min-width: 52px; max-width: 52px; min-height: 52px; max-height: 52px; }}
QPushButton#rail:hover {{ background: {c['row_alt']}; color: {c['text']}; }}
QPushButton#rail:checked {{ background: {c['accent_soft']}; color: {c['accent_text']}; }}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{ background: {c['surface']}; border: 1px solid {c['border']};
               border-radius: {ir}px; padding: 8px 12px; selection-background-color: {c['accent']}; selection-color: #1E1E1E; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border-color: {c['accent']}; }}
QComboBox QAbstractItemView {{ background: {c['surface']}; selection-background-color: {c['accent_soft']}; selection-color: {c['accent_text']}; }}
QTableWidget, QTreeWidget, QListWidget {{ background: {c['surface']}; border: none; border-radius: {r}px; gridline-color: {c['border']};
               alternate-background-color: {c['row_alt']}; selection-background-color: {c['accent_soft']}; selection-color: {c['accent_text']}; }}
QHeaderView::section {{ background: {c['row_alt']}; border: none; border-bottom: 1px solid {c['border']}; padding: 8px 10px;
               color: {c['muted']}; font-size: 10px; font-weight: 600; }}
QProgressBar {{ background: {c['border']}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 38px; height: 22px; border-radius: 11px; background: {c['border']}; }}
QCheckBox::indicator:checked {{ background: {c['accent']}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; }}
QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QToolTip {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; }}
QDialog, QMessageBox {{ background: {c['bg']}; }}
"""


def pill_style(kind: str) -> str:
    c = _current
    fg, bg = {"ok": (c["ok"], c["ok_bg"]), "warn": (c["warn"], c["warn_bg"]),
              "err": (c["err"], c["err_bg"]), "info": (c["muted"], c["row_alt"])}[kind]
    return f"background:{bg}; color:{fg}; border-radius:12px; padding:4px 12px; font-size:12px; font-weight:600;"
