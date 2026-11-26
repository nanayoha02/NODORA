"""Cálculo puro (sin Qt) para personalizar el estilo: validación de colores, contraste y escala de esquinas."""
from __future__ import annotations

import re

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
CORNERS = {"square": 0.3, "soft": 1.0, "round": 1.5}
FONTS = ["", "Segoe UI", "Inter", "Arial", "Calibri", "Verdana", "Trebuchet MS", "Georgia", "Consolas"]


def valid_hex(s) -> bool:
    return isinstance(s, str) and bool(_HEX.match(s))


def rgb(h: str) -> tuple[int, int, int]:
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def to_hex(r: float, g: float, b: float) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(round(v)))) for v in (r, g, b)))


def mix(a: str, b: str, t: float) -> str:
    """Mezcla a→b (t=0 devuelve a, t=1 devuelve b)."""
    ra, rb = rgb(a), rgb(b)
    return to_hex(*(x * (1 - t) + y * t for x, y in zip(ra, rb)))


def shade(h: str, k: float) -> str:
    """k>0 aclara hacia blanco, k<0 oscurece hacia negro."""
    return mix(h, "#FFFFFF", k) if k >= 0 else mix(h, "#000000", -k)


def luminance(h: str) -> float:
    def ch(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_fg(bg: str) -> str:
    """Texto negro o blanco, el que mejor se lea sobre `bg`."""
    return "#111111" if luminance(bg) > 0.36 else "#FFFFFF"


def apply_custom(pal: dict, accent: str = "", text: str = "", corners: str = "soft") -> dict:
    """Devuelve una copia de la paleta con el acento, el color de letra y las esquinas del usuario."""
    p = dict(pal)
    if valid_hex(accent):
        dark_bg = luminance(p["bg"]) < 0.25
        p["accent"] = accent
        p["primary_bg"] = accent
        p["primary_fg"] = contrast_fg(accent)
        p["accent_soft"] = mix(accent, p["surface"], 0.80)
        p["accent_text"] = shade(accent, 0.35) if dark_bg else shade(accent, -0.30)
        if p.get("tabs"):
            p["nav_active_fg"] = shade(accent, -0.35)
    if valid_hex(text):
        p["text"] = text
        p["muted"] = mix(text, p["bg"], 0.45)
    f = CORNERS.get(corners, 1.0)
    if f != 1.0:
        for k in ("radius", "btn_r", "input_r"):
            p[k] = max(2, int(round(p[k] * f)))
    return p
