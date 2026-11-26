"""Paletas, tipografía y hoja de estilos de NODORA.

Temas: «plum» (Ciruela, predeterminado: fondo ciruela, pasteles y botones en píldora), «light» (claro, del
prototipo de Figma), «dark» (oscuro neutro) y «system»."""
from __future__ import annotations

from ..core.style_math import apply_custom

_BASE = dict(radius=16, btn_r=10, input_r=10, rail=False, shell_margin=0, shell_radius=0, notch=False, tile_border=None, tabs=False, float=False,
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
        "radius": 24, "btn_r": 18, "input_r": 16, "rail": True, "notch": True, "shell_margin": 18, "shell_radius": 38}

# «Lima»: negro profundo, tarjetas oscuras tipo cristal y acento verde lima (barra lateral con etiquetas).
LIME = {**_BASE, "bg": "#080A08", "surface": "#121512", "sidebar": "#0B0D0B", "text": "#F2F5EE", "muted": "#8C938A",
        "border": "#232823", "accent": "#A3E635", "accent_soft": "#1E2A12", "accent_text": "#B8F24D",
        "ok": "#A3E635", "ok_bg": "#1E2A12", "warn": "#F0C77A", "warn_bg": "#3A3220",
        "err": "#FF8A8A", "err_bg": "#3F2323", "info": "#9FB8A0", "row_alt": "#171B17", "chart2": "#4D7C0F",
        "primary_bg": "#A3E635", "primary_fg": "#0B1204", "on_pastel": "#F2F5EE",
        "pastel": ("#161A16", "#141914", "#191E17"),
        "radius": 20, "btn_r": 18, "input_r": 12, "tile_border": "#232823"}

# «Noche»: azul marino profundo, tarjetas con borde fino y acento índigo (barra lateral con etiquetas).
NIGHT = {**_BASE, "bg": "#070A1A", "surface": "#0D1230", "sidebar": "#080C22", "text": "#F1F3FF", "muted": "#8E95B8",
         "border": "#1C2350", "accent": "#5B5BF0", "accent_soft": "#1B1F5A", "accent_text": "#AEB2FF",
         "ok": "#34D399", "ok_bg": "#10382E", "warn": "#FBA94C", "warn_bg": "#3A2A14",
         "err": "#FF8A9A", "err_bg": "#3F1F2B", "info": "#7FA8FF", "row_alt": "#111737", "chart2": "#34D399",
         "primary_bg": "#5B5BF0", "primary_fg": "#FFFFFF", "on_pastel": "#F1F3FF",
         "pastel": ("#101638", "#0F1535", "#121839"),
         "radius": 18, "btn_r": 12, "input_r": 10, "tile_border": "#1C2350"}

# «iPhone»: estilo iOS claro: fondo gris agrupado, tarjetas blancas muy redondeadas y azul del sistema.
IOS = {**_BASE, "bg": "#F2F2F7", "surface": "#FFFFFF", "sidebar": "#F9F9FB", "text": "#111111", "muted": "#8E8E93",
       "border": "#E3E3E8", "accent": "#007AFF", "accent_soft": "#E5F1FF", "accent_text": "#007AFF",
       "ok": "#248A3D", "ok_bg": "#E3F6E8", "warn": "#B26A00", "warn_bg": "#FFF1D6",
       "err": "#D70015", "err_bg": "#FFE5E8", "info": "#5856D6", "row_alt": "#F7F7FA", "chart2": "#34C759",
       "primary_bg": "#007AFF", "primary_fg": "#FFFFFF", "on_pastel": "#111111",
       "pastel": ("#E5F1FF", "#E3F6E8", "#FFF1D6"),
       "radius": 22, "btn_r": 18, "input_r": 12, "tile_border": "#E3E3E8"}

# «Salvia»: kit suave en verde salvia sobre gris cálido, botones muy redondeados y brillo lavanda.
SAGE = {**_BASE, "bg": "#D9D6D1", "surface": "#ECEAE6", "sidebar": "#E3E0DB", "text": "#2F3A35", "muted": "#7C867F",
        "border": "#C9C6C0", "accent": "#8FAE97", "accent_soft": "#D3E0D5", "accent_text": "#3F6B52",
        "ok": "#4E8B66", "ok_bg": "#D3E5D8", "warn": "#A67C2E", "warn_bg": "#F0E4C8",
        "err": "#B5524F", "err_bg": "#F1D9D6", "info": "#6F8FA0", "row_alt": "#E1DEDA", "chart2": "#7E97A0",
        "primary_bg": "#7F9F89", "primary_fg": "#FFFFFF", "on_pastel": "#2F3A35",
        "pastel": ("#9DB8A3", "#C5D3C6", "#8DA3AD"),
        "radius": 22, "btn_r": 20, "input_r": 16}

# «Peluche»: rosa y crema suaves, esquinas muy redondeadas.
PLUSH = {**_BASE, "bg": "#FCEEEE", "surface": "#FFFAF6", "sidebar": "#F8DDE1", "text": "#3B2A2E", "muted": "#9A7F85",
         "border": "#F0CFD4", "accent": "#F4A6B8", "accent_soft": "#FBD9E0", "accent_text": "#C2446A",
         "ok": "#3E9B6E", "ok_bg": "#DDF2E6", "warn": "#B7791F", "warn_bg": "#FFF0CF",
         "err": "#D2455A", "err_bg": "#FFE0E4", "info": "#7D8FC4", "row_alt": "#FFF3F2", "chart2": "#F28BA4",
         "primary_bg": "#F28BA4", "primary_fg": "#FFFFFF", "on_pastel": "#3B2A2E",
         "pastel": ("#F9C9D3", "#FFEBD6", "#E6DDF5"),
         "radius": 28, "btn_r": 22, "input_r": 18}

# «Smart»: marco redondeado flotante sobre fondo azul, menú azul con pestaña activa que se funde con el contenido.
SMART = {**_BASE, "bg": "#E6E9F3", "backdrop": "#3F55A5", "surface": "#FFFFFF", "sidebar": "#4A63CF", "text": "#12141F",
         "muted": "#8A90A6", "border": "#E1E4EF", "accent": "#5671E6", "accent_soft": "#DDE3FB", "accent_text": "#3547A8",
         "ok": "#2E8B57", "ok_bg": "#DDF1E5", "warn": "#B7791F", "warn_bg": "#FFF1D6",
         "err": "#C23B4B", "err_bg": "#FBE1E4", "info": "#5671E6", "row_alt": "#F1F3FA", "chart2": "#3547A8",
         "primary_bg": "#5671E6", "primary_fg": "#FFFFFF", "on_pastel": "#12141F",
         "pastel": ("#FFFFFF", "#FFFFFF", "#FFFFFF"), "tile_border": None, "float": True, "brand_bg": "#3D52AB",
         "radius": 22, "btn_r": 14, "input_r": 14, "shell_margin": 26, "shell_radius": 30, "tabs": True,
         "nav_fg": "#E4E9FF", "nav_hover": "#5C74D8", "nav_hover_fg": "#FFFFFF", "nav_active_bg": "#E6E9F3",
         "nav_active_fg": "#3547A8", "brand_fg": "#FFFFFF", "brand_dot": "#9BF0C8", "side_muted": "#C5CFFA"}

THEMES = {"smart": SMART, "light": LIGHT, "dark": DARK, "plum": PLUM, "lime": LIME, "night": NIGHT, "ios": IOS, "sage": SAGE, "plush": PLUSH}
FONT = '"Unbounded", "Syne", "Space Grotesk", "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif'
_current = dict(PLUM)
_current.setdefault("backdrop", _current["bg"])


def palette() -> dict:
    return _current


_font = {"family": "", "size": 13}


def font_stack() -> str:
    return (f'"{_font["family"]}", ' if _font["family"] else "") + FONT


def apply_config(cfg, system_is_dark: bool = False) -> dict:
    """Aplica tema + personalización del usuario (acento, letras, fuente, tamaño y esquinas)."""
    _font["family"], _font["size"] = cfg.font_family, cfg.font_size
    return set_theme(cfg.theme, system_is_dark, dict(accent=cfg.custom_accent, text=cfg.custom_text, corners=cfg.corners))


def set_theme(name: str, system_is_dark: bool = False, custom: dict | None = None) -> dict:
    if name == "system":
        name = "dark" if system_is_dark else "light"
    base = THEMES.get(name, PLUM)
    if custom:
        base = apply_custom(base, **custom)
    _current.clear()
    _current.update(base)
    _current.setdefault("backdrop", _current["bg"])
    return _current


def stylesheet() -> str:
    c = _current
    r, br, ir = c["radius"], c["btn_r"], c["input_r"]
    return f"""
* {{ font-family: {font_stack()}; font-size: {_font['size']}px; color: {c['text']}; }}
QMainWindow, QWidget#root {{ background: {c['backdrop']}; }}
QFrame#shell, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {c['bg']}; }}
QFrame#shell {{ border-radius: {c['shell_radius']}px; }}
QWidget#sidebar {{ background: {c['sidebar']}; {'' if c['rail'] or c.get('tabs') else 'border-right: 1px solid ' + c['border'] + ';'}
               {('border-top-left-radius: ' + str(c['shell_radius']) + 'px; border-bottom-left-radius: ' + str(c['shell_radius']) + 'px;') if c.get('tabs') else ''} }}
QLabel {{ background: transparent; }}
QLabel#pageTitle {{ font-size: 22px; font-weight: 600; }}
QLabel#pageSub, QLabel.muted, QLabel#muted {{ color: {c['muted']}; }}
QLabel#hero {{ font-size: 22px; font-weight: 600; }}
QLabel#bigNumber {{ font-size: 34px; font-weight: 600; }}
QLabel#cardTitle {{ font-size: 15px; font-weight: 600; }}
QLabel#eyebrow {{ color: {c['muted']}; font-size: 10px; letter-spacing: 1px; font-weight: 600; }}
QLabel#brand {{ font-size: 24px; font-weight: 700; letter-spacing: 1px; }}
QLabel#tagline {{ color: {c['muted']}; font-size: 14px; }}
QFrame#card {{ background: {c['surface']}; border: {'none' if c['rail'] or c.get('float') else '1px solid ' + c['border']}; border-radius: {r}px; }}
QFrame#brandblock {{ background: {c.get('brand_bg') or c['sidebar']}; border-top-left-radius: {c['shell_radius']}px; border-bottom-right-radius: 30px; }}
QFrame#topbar {{ background: {c['surface']}; border: none; border-radius: {r}px; }}
QPushButton {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: {br}px;
               padding: 9px 20px; min-height: 18px; font-weight: 500; }}
QPushButton:hover {{ border-color: {c['accent']}; background: {c['row_alt']}; }}
QPushButton:pressed {{ background: {c['accent_soft']}; }}
QPushButton:disabled {{ color: {c['muted']}; background: {c['bg']}; }}
QPushButton#primary:hover {{ background: {c['primary_bg']}; border-color: {c['accent_text']}; }}
QPushButton#primary {{ background: {c['primary_bg']}; border-color: {c['primary_bg']}; color: {c['primary_fg']}; font-weight: 600; }}
QPushButton#primary:disabled {{ background: {c['border']}; color: {c['muted']}; border-color: {c['border']}; }}
QPushButton#danger {{ color: {c['err']}; border-color: {c['err']}; }}
QPushButton#nav {{ text-align: left; border: none; border-radius: {br}px; padding: 12px 16px; min-height: 20px; background: transparent; color: {c.get('nav_fg') or c['muted']}; font-weight: 500; }}
QPushButton#nav:hover {{ background: {c.get('nav_hover') or c['row_alt']}; color: {c.get('nav_hover_fg') or c['text']}; }}
QPushButton#nav:checked {{ background: {c.get('nav_active_bg') or c['accent_soft']}; font-weight: 700; color: {c.get('nav_active_fg') or c['accent_text']}; }}
{('QPushButton#nav, QPushButton#nav:hover, QPushButton#nav:checked { border-top-right-radius: 0; border-bottom-right-radius: 0; border-top-left-radius: 24px; border-bottom-left-radius: 24px; padding-left: 20px; }' if c.get('tabs') else '')}
{('QWidget#sidebar QLabel#brand { color: ' + c['brand_fg'] + '; } QWidget#sidebar QLabel#eyebrow, QWidget#sidebar QLabel#tagline { color: ' + c['side_muted'] + '; }' if c.get('tabs') else '')}
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
