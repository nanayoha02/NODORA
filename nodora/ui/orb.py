"""«Red viva»: anillo de partículas animado cuya intensidad sale del tráfico REAL de BOSGAME y cuyos nodos son sus
conexiones TCP reales. El anillo resume el tráfico agregado (bytes/s medidos); no es una simulación aleatoria."""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from . import theme
from .orb_math import activity, project, short_label, torus_point, torus_seeds

N_PARTICLES = 900
MAX_NODES = 10


class NetworkOrb(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(360)
        self.seeds = torus_seeds(N_PARTICLES)
        self.rx_act = self.tx_act = 0.0          # suavizadas (para que no «salte» entre lecturas)
        self._rx_t = self._tx_t = 0.0            # objetivo según la última lectura real
        self.rx_bps = self.tx_bps = 0.0
        self.nodes: list[tuple[str, str]] = []   # (remoto, proceso) reales
        self.live = False
        self.spin = 0.0
        self.phase = 0.0
        self._last = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step)

    # ---- datos reales
    def set_rates(self, rx_bps: float, tx_bps: float) -> None:
        self.live = True
        self.rx_bps, self.tx_bps = rx_bps, tx_bps
        self._rx_t, self._tx_t = activity(rx_bps), activity(tx_bps)

    def set_connections(self, rows) -> None:
        seen, out = set(), []
        for c in rows:
            key = (c.get("remote", ""), c.get("process", ""))
            if key not in seen and key[0]:
                seen.add(key)
                out.append(key)
        self.nodes = out[:MAX_NODES]
        self.update()

    def set_idle(self) -> None:
        self.live = False
        self._rx_t = self._tx_t = 0.0

    # ---- animación (solo corre mientras el widget es visible)
    def showEvent(self, e):
        self._last = time.monotonic()
        self.timer.start(33)
        super().showEvent(e)

    def hideEvent(self, e):
        self.timer.stop()
        super().hideEvent(e)

    def _step(self):
        now = time.monotonic()
        dt = min(0.2, now - self._last)
        self._last = now
        k = min(1.0, dt * 3.0)                                 # suavizado exponencial hacia el valor medido
        self.rx_act += (self._rx_t - self.rx_act) * k
        self.tx_act += (self._tx_t - self.tx_act) * k
        act = max(self.rx_act, self.tx_act)
        self.spin += dt * (0.12 + 0.9 * act)                   # más tráfico = gira más rápido
        self.phase += dt * (0.6 + 2.5 * act)
        self.update()

    # ---- dibujo
    def paintEvent(self, _):
        c = theme.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        bg = QPainterPath()
        bg.addRoundedRect(QRectF(0, 0, w, h), c["radius"], c["radius"])
        p.fillPath(bg, QBrush(QColor(c["surface"])))
        cx, cy = w / 2, h / 2
        scale = min(w * 0.28, h * 0.62)
        act = max(self.rx_act, self.tx_act)
        col_rx, col_tx = QColor(c["accent"]), QColor(c["chart2"])

        # nodos reales (conexiones) a ambos lados y sus flujos
        node_pos = []
        for i, (remote, proc) in enumerate(self.nodes):
            left = i % 2 == 0
            row = i // 2
            rows_n = max(1, (len(self.nodes) + 1) // 2)
            y = 34 + (h - 68) * (row + 0.5) / rows_n
            x = 118 if left else w - 118
            node_pos.append((x, y, left, remote, proc))
        t = time.monotonic()
        for i, (x, y, left, remote, proc) in enumerate(node_pos):
            edge = QPointF(cx + (-1 if left else 1) * scale * 1.12, cy + (y - cy) * 0.35)
            path = QPainterPath(QPointF(x + (62 if left else -62), y))
            mid = (x + edge.x()) / 2
            path.cubicTo(QPointF(mid, y), QPointF(mid, edge.y()), edge)
            p.setPen(QPen(QColor(c["border"]), 1))
            p.drawPath(path)
            if self.live:
                for col, val, back in ((col_rx, self.rx_act, False), (col_tx, self.tx_act, True)):
                    for j in range(2):
                        ph = (t * (0.10 + 0.55 * val) + i * 0.173 + j * 0.5) % 1.0
                        pt = path.pointAtPercent(1 - ph if back else ph)
                        cc = QColor(col)
                        cc.setAlphaF(0.25 + 0.75 * val)
                        p.setPen(Qt.NoPen)
                        p.setBrush(QBrush(cc))
                        p.drawEllipse(pt, 2.4 + 1.6 * val, 2.4 + 1.6 * val)
            box = QRectF(x - 62 if left else x - 62, y - 17, 124, 34)
            r = QPainterPath()
            r.addRoundedRect(box, 10, 10)
            p.fillPath(r, QBrush(QColor(c["row_alt"])))
            p.setPen(QPen(QColor(c["border"]), 1))
            p.drawPath(r)
            p.setPen(QColor(c["text"]))
            f = p.font()
            f.setPointSizeF(8.0)
            p.setFont(f)
            lab = short_label(remote, proc)
            p.drawText(box.adjusted(8, 0, -6, 0), Qt.AlignVCenter | Qt.AlignLeft,
                       p.fontMetrics().elidedText(lab, Qt.ElideRight, int(box.width() - 14)))

        # anillo de partículas (3 capas de profundidad: lejos/medio/cerca)
        buckets = ([], [], [])
        wob = min(1.0, act * 1.2)
        tilt = 1.05 + 0.05 * math.sin(self.phase * 0.3)
        for u, v, jit in self.seeds:
            x, y, z = torus_point(u, v, jit, self.spin, tilt, wob, self.phase)
            px, py, d = project(x, y, z, scale, cx, cy)
            buckets[0 if d < 0.38 else (1 if d < 0.68 else 2)].append(QPointF(px, py))
        base_a = 0.35 + 0.65 * (0.35 + 0.65 * act if self.live else 0.25)
        for idx, pts in enumerate(buckets):
            col = QColor(col_rx if idx != 1 else col_tx)
            col.setAlphaF(base_a * (0.35 + 0.3 * idx))
            pen = QPen(col)
            pen.setWidthF(1.2 + idx * 0.9)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawPoints(QPolygonF(pts))

        # textos con datos reales
        p.setPen(QColor(c["muted"]))
        f = p.font()
        f.setPointSizeF(9.0)
        p.setFont(f)
        if self.live:
            from .widgets import fmt_rate
            p.drawText(QRectF(16, 10, w - 32, 18), Qt.AlignLeft,
                       f"↓ {fmt_rate(self.rx_bps)}   ↑ {fmt_rate(self.tx_bps)}   ·   {len(self.nodes)} conexión(es) mostradas")
        else:
            p.drawText(QRectF(0, h - 30, w, 20), Qt.AlignCenter, "Pulsa «Iniciar» para animar la red con el tráfico real de BOSGAME")
