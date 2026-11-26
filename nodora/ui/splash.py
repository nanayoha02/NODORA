"""Pantalla de carga: el logo de NODORA con un anillo giratorio, barra de progreso y desvanecimiento al terminar."""
from __future__ import annotations

import math
import os
import time

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from ..core.style_math import contrast_fg, mix
from . import theme


class Splash(QWidget):
    W, H = 420, 340

    def __init__(self, logo_path: str = ""):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)
        scr = QGuiApplication.primaryScreen()
        if scr:
            g = scr.availableGeometry()
            self.move(g.center().x() - self.W // 2, g.center().y() - self.H // 2)
        self.logo = QPixmap(logo_path) if logo_path and os.path.exists(logo_path) else QPixmap()
        self.target, self.shown, self.status = 0.0, 0.0, "Iniciando…"
        self.angle = 0.0
        self._t0 = time.monotonic()
        self._fading = False
        self._on_done = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def set_progress(self, frac: float, text: str = "") -> None:
        self.target = max(self.target, min(1.0, frac))
        if text:
            self.status = text
        self.update()

    def finish(self, on_done=None) -> None:
        """Completa la barra y desvanece la pantalla de carga."""
        self.set_progress(1.0, "¡Listo!")
        self._on_done = on_done
        QTimer.singleShot(260, self._begin_fade)

    def _begin_fade(self):
        self._fading = True

    def _tick(self):
        now = time.monotonic() - self._t0
        self.angle = (now * 300.0) % 360.0                       # giro del anillo
        self.shown += (self.target - self.shown) * 0.12            # la barra se acerca suavemente
        if self._fading:
            o = self.windowOpacity() - 0.09
            if o <= 0.02:
                self.timer.stop()
                self.close()
                if self._on_done:
                    self._on_done()
                return
            self.setWindowOpacity(o)
        self.update()

    def paintEvent(self, _):
        c = theme.palette()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        fill = c.get("backdrop") if c.get("tabs") or c.get("rail") else c["surface"]
        fill = fill or c["bg"]
        fg = contrast_fg(fill)
        card = QPainterPath()
        card.addRoundedRect(QRectF(6, 6, self.W - 12, self.H - 12), 30, 30)
        p.fillPath(card, QColor(fill))
        cx, cy, rx, ry = self.W / 2, 116.0, 104.0, 66.0
        ring = QRectF(cx - rx, cy - ry, 2 * rx, 2 * ry)
        # anillo base + arco giratorio con cola que se desvanece
        base = QPen(QColor(mix(fill, fg, 0.14)), 5)
        p.setPen(base)
        p.drawEllipse(ring)
        accent = QColor(c["accent"] if abs(_lum(fill) - _lum(c["accent"])) > 0.15 else fg)
        for i in range(14):
            col = QColor(accent)
            col.setAlphaF(1.0 - i / 14.0)
            pen = QPen(col, 5)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            start = -(self.angle - i * 6.0)
            p.drawArc(ring, int(start * 16), int(-6 * 16))
        # logo con un leve «latido»
        pulse = 1.0 + 0.04 * math.sin((time.monotonic() - self._t0) * 5.0)
        side = 132 * pulse
        if not self.logo.isNull():
            pm = self.logo.scaled(int(side), int(side), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(int(cx - pm.width() / 2), int(cy - pm.height() / 2), pm)
        else:
            p.setPen(QColor(fg))
            f = p.font()
            f.setBold(True)
            f.setPointSizeF(34)
            p.setFont(f)
            p.drawText(ring, Qt.AlignCenter, "N")
        # nombre, lema, estado y progreso
        p.setPen(QColor(fg))
        f = p.font()
        f.setBold(True)
        f.setPointSizeF(22)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 3)
        p.setFont(f)
        p.drawText(QRectF(0, 202, self.W, 36), Qt.AlignCenter, "NODORA")
        f.setBold(False)
        f.setPointSizeF(8.5)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 1.5)
        p.setFont(f)
        p.setPen(QColor(mix(fill, fg, 0.62)))
        p.drawText(QRectF(0, 238, self.W, 20), Qt.AlignCenter, "REMOTE SYSTEM MANAGEMENT")
        f.setLetterSpacing(QFont.AbsoluteSpacing, 0)
        f.setPointSizeF(9)
        p.setFont(f)
        p.drawText(QRectF(0, 266, self.W, 18), Qt.AlignCenter, self.status)
        bar = QRectF(60, 292, self.W - 120, 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(mix(fill, fg, 0.14)))
        p.drawRoundedRect(bar, 3, 3)
        p.setBrush(accent)
        p.drawRoundedRect(QRectF(bar.left(), bar.top(), max(6.0, bar.width() * self.shown), bar.height()), 3, 3)


def _lum(h: str) -> float:
    from ..core.style_math import luminance
    return luminance(h)
