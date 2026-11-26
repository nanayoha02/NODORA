"""Matemática pura (sin Qt) de la «Red viva»: nube de partículas en toro y escala de actividad."""
from __future__ import annotations

import math
import random


def activity(bps: float) -> float:
    """Convierte bytes/s reales en 0..1 (escala logarítmica: 1 KiB/s ≈ 0.07, 1 MiB/s ≈ 0.67, 10 MiB/s ≈ 0.9)."""
    if bps is None or bps <= 0:
        return 0.0
    return max(0.0, min(1.0, math.log10(1 + bps / 1024.0) / 4.5))


def torus_seeds(n: int, seed: int = 7) -> list[tuple[float, float, float]]:
    """(u, v, jitter) por partícula: u recorre el anillo mayor, v la sección; jitter rompe la regularidad."""
    rnd = random.Random(seed)
    return [(rnd.random() * math.tau, rnd.random() * math.tau, rnd.random()) for _ in range(n)]


def torus_point(u: float, v: float, jitter: float, spin: float, tilt: float, wob: float, phase: float):
    """Devuelve (x, y, z) ya rotadas. `wob` (0..1) deforma la sección según la actividad real."""
    big_r = 1.0
    small_r = 0.34 * (1 + wob * 0.55 * math.sin(3 * u + phase * 2.0 + v) + (jitter - 0.5) * 0.22)
    x = (big_r + small_r * math.cos(v)) * math.cos(u)
    y = (big_r + small_r * math.cos(v)) * math.sin(u)
    z = small_r * math.sin(v) * 1.15
    cs, sn = math.cos(spin), math.sin(spin)               # giro alrededor del eje vertical de la pantalla
    x, y = x * cs - y * sn, x * sn + y * cs
    ct, st = math.cos(tilt), math.sin(tilt)               # inclinación hacia el observador
    y, z = y * ct - z * st, y * st + z * ct
    return x, y, z


def project(x: float, y: float, z: float, scale: float, cx: float, cy: float, focal: float = 3.2):
    """Proyección en perspectiva; devuelve (px, py, factor_de_profundidad 0..1 donde 1 = más cerca)."""
    k = focal / (focal + y * 0.0 + z + 1.6)
    depth = max(0.0, min(1.0, (z + 1.4) / 2.8))
    return cx + x * scale * k, cy + y * scale * k * 0.55, depth


def short_label(remote: str, process: str) -> str:
    return f"{process or 'proceso'} · {remote}" if remote else (process or "—")
