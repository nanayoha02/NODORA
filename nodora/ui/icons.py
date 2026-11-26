"""Iconos de línea dibujados con QPainter (sin archivos externos): nítidos a cualquier escala y del color del tema."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap


def _pts(*xy):
    return [QPointF(x, y) for x, y in xy]


def _dash(p):
    for x, y in ((3.5, 3.5), (13.5, 3.5), (3.5, 13.5), (13.5, 13.5)):
        p.drawRoundedRect(QRectF(x, y, 7, 7), 2, 2)


def _ssh(p):
    p.drawRoundedRect(QRectF(2.5, 4.5, 19, 15), 3, 3)
    p.drawPolyline(_pts((7, 9.5), (10.5, 12), (7, 14.5)))
    p.drawLine(QPointF(12.5, 15), QPointF(17, 15))


def _monitor(p):
    p.drawPolyline(_pts((3, 12), (7, 12), (10, 5), (14, 19), (17, 12), (21, 12)))


def _network(p):
    p.drawEllipse(QPointF(12, 5.5), 2.5, 2.5)
    p.drawEllipse(QPointF(5, 18), 2.5, 2.5)
    p.drawEllipse(QPointF(19, 18), 2.5, 2.5)
    p.drawLine(QPointF(11, 8), QPointF(6, 15.6))
    p.drawLine(QPointF(13, 8), QPointF(18, 15.6))
    p.drawLine(QPointF(7.6, 18), QPointF(16.4, 18))


def _traffic(p):
    p.drawLine(QPointF(8, 20), QPointF(8, 5))
    p.drawPolyline(_pts((4.5, 8.5), (8, 5), (11.5, 8.5)))
    p.drawLine(QPointF(16, 4), QPointF(16, 19))
    p.drawPolyline(_pts((12.5, 15.5), (16, 19), (19.5, 15.5)))


def _files(p):
    p.drawRoundedRect(QRectF(3, 6.5, 18, 13), 2.5, 2.5)
    p.drawPolyline(_pts((3, 9), (3, 5.5), (9, 5.5), (11, 8)))


def _history(p):
    p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
    p.drawPolyline(_pts((12, 7), (12, 12), (15.5, 14)))


def _settings(p):
    for y, kx in ((7, 15), (12, 9), (17, 16)):
        p.drawLine(QPointF(4, y), QPointF(20, y))
        p.setBrush(QColor(p.pen().color()))
        p.drawEllipse(QPointF(kx, y), 2.2, 2.2)
        p.setBrush(Qt.NoBrush)


DRAW = {"dash": _dash, "ssh": _ssh, "monitor": _monitor, "network": _network, "traffic": _traffic,
        "files": _files, "history": _history, "settings": _settings}


def _pixmap(name: str, color: str, size: int) -> QPixmap:
    px = size * 2                                   # 2x para pantallas de alta densidad
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(px / 24.0, px / 24.0)
    pen = QPen(QColor(color))
    pen.setWidthF(1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    DRAW[name](p)
    p.end()
    return pm


def make_icon(name: str, off_color: str, on_color: str, size: int = 22) -> QIcon:
    """Icono con dos estados: normal (off_color) y seleccionado/«checked» (on_color)."""
    ic = QIcon()
    ic.addPixmap(_pixmap(name, off_color, size), QIcon.Normal, QIcon.Off)
    ic.addPixmap(_pixmap(name, on_color, size), QIcon.Normal, QIcon.On)
    return ic
