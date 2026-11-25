"""Widgets reutilizables: tarjetas, gráficas, estados, ejecución en segundo plano."""
from __future__ import annotations

import traceback
from typing import Callable, Optional, Sequence

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath, QBrush, QLinearGradient
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QAbstractItemView,
                               QMessageBox)

from . import theme


# ----------------------------------------------------------------------------- segundo plano
class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Job(QRunnable):
    def __init__(self, fn: Callable):
        super().__init__()
        self.fn, self.sig = fn, _Signals()
        self.setAutoDelete(True)

    def run(self):
        try:
            self.sig.done.emit(self.fn())
        except Exception as e:  # noqa: BLE001 — se muestra al usuario; nunca congela la interfaz
            traceback.print_exc()
            self.sig.failed.emit(str(e) or e.__class__.__name__)


_pool = QThreadPool.globalInstance()
_pool.setMaxThreadCount(8)
_keep: set = set()


def run_async(fn: Callable, on_done: Optional[Callable] = None, on_error: Optional[Callable] = None) -> None:
    """Ejecuta `fn` en un hilo del pool y entrega el resultado en el hilo de la interfaz."""
    job = _Job(fn)
    _keep.add(job.sig)

    def _fin(*_):
        _keep.discard(job.sig)

    if on_done:
        job.sig.done.connect(on_done)
    job.sig.failed.connect(on_error or (lambda m: QMessageBox.warning(None, "NODORA", m)))
    job.sig.done.connect(_fin)
    job.sig.failed.connect(_fin)
    _pool.start(job)


# ----------------------------------------------------------------------------- tarjetas
class Card(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(20, 18, 20, 18)
        self.v.setSpacing(10)
        if title:
            t = QLabel(title)
            t.setObjectName("cardTitle")
            self.v.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setObjectName("muted")
            s.setWordWrap(True)
            self.v.addWidget(s)

    def add(self, w) -> None:
        self.v.addWidget(w)

    def addl(self, layout) -> None:
        self.v.addLayout(layout)


def eyebrow(text: str) -> QLabel:
    l = QLabel(text.upper())
    l.setObjectName("eyebrow")
    return l


def muted(text: str, wrap: bool = True) -> QLabel:
    l = QLabel(text)
    l.setObjectName("muted")
    l.setWordWrap(wrap)
    return l


class Pill(QLabel):
    def __init__(self, text="", kind="info", parent=None):
        super().__init__(text, parent)
        self.set(text, kind)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(self.sizePolicy().horizontalPolicy(), self.sizePolicy().verticalPolicy())

    def set(self, text: str, kind: str) -> None:
        self.setText(("● " if kind in ("ok", "warn", "err") else "") + text)
        self.setStyleSheet(theme.pill_style(kind))


def _fmt(n: float) -> str:
    for u in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(n) < 1024 or u == "TiB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return str(n)


fmt_bytes = _fmt


def fmt_uptime(sec: Optional[int]) -> str:
    if sec is None:
        return "No disponible"
    d, r = divmod(int(sec), 86400)
    h, r = divmod(r, 3600)
    return f"{d} d {h} h" if d else f"{h} h {r // 60} min"


# ----------------------------------------------------------------------------- gráfica
class Sparkline(QWidget):
    """Línea con área; datos reales (0-100 por defecto)."""

    def __init__(self, color: str = "", maxv: float = 100.0, parent=None, axes: bool = False, ink: str = ""):
        super().__init__(parent)
        self.data: list[float] = []
        self.color, self.maxv, self.axes, self.ink = color, maxv, axes, ink
        self.setMinimumHeight(150 if axes else 40)

    def push(self, v: float, limit: int = 60) -> None:
        self.data.append(v)
        self.data = self.data[-limit:]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = theme.palette()
        col = QColor(self.color or c["accent"])
        r = QRectF(self.rect()).adjusted(34 if self.axes else 0, 6, -4, -18 if self.axes else -4)
        if self.axes:
            p.setPen(QPen(QColor(c["border"]), 1))
            for frac, label in ((0, "100%"), (0.5, "50%"), (1, "0%")):
                y = r.top() + r.height() * frac
                p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
                p.setPen(QColor(c["muted"]))
                p.drawText(QRectF(0, y - 8, 30, 16), Qt.AlignRight | Qt.AlignVCenter, label)
                p.setPen(QPen(QColor(c["border"]), 1))
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(r.left(), self.height() - 16, 120, 14), Qt.AlignLeft, "Últimos 60 muestras")
            p.drawText(QRectF(r.right() - 60, self.height() - 16, 60, 14), Qt.AlignRight, "Ahora")
        if len(self.data) < 2:
            p.setPen(QColor(self.ink or c["muted"]))
            p.drawText(r, Qt.AlignCenter, "Calculando…")
            return
        n = len(self.data)
        pts = [QPointF(r.left() + r.width() * i / (n - 1), r.bottom() - r.height() * min(v, self.maxv) / self.maxv)
               for i, v in enumerate(self.data)]
        path = QPainterPath(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        area = QPainterPath(path)
        area.lineTo(QPointF(pts[-1].x(), r.bottom()))
        area.lineTo(QPointF(pts[0].x(), r.bottom()))
        g = QLinearGradient(0, r.top(), 0, r.bottom())
        top = QColor(col)
        top.setAlpha(90)
        bot = QColor(col)
        bot.setAlpha(8)
        g.setColorAt(0, top)
        g.setColorAt(1, bot)
        p.fillPath(area, QBrush(g))
        p.setPen(QPen(col, 2))
        p.drawPath(path)


class BarChart(QWidget):
    """Barras agrupadas (dos series) por etiqueta; para 'Actividad de los últimos 7 días'."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.labels: list[str] = []
        self.a: list[int] = []
        self.b: list[int] = []
        self.setMinimumHeight(170)

    def set(self, labels, a, b):
        self.labels, self.a, self.b = labels, a, b
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = theme.palette()
        if not self.labels:
            return
        top = max(max(self.a + self.b, default=1), 1)
        w, h = self.width(), self.height() - 22
        slot = w / len(self.labels)
        bw = min(26, slot / 3.2)
        for i, lab in enumerate(self.labels):
            x0 = slot * i + slot / 2
            for j, (val, col) in enumerate(((self.a[i], c["accent"]), (self.b[i], c["chart2"]))):
                bh = (h - 8) * val / top
                p.setBrush(QColor(col))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(QRectF(x0 - bw - 1 + j * (bw + 2), h - bh, bw, max(bh, 2 if val else 0)), 4, 4)
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(slot * i, h + 4, slot, 16), Qt.AlignCenter, lab)


# ----------------------------------------------------------------------------- tablas
def make_table(headers: Sequence[str], stretch_last: bool = True) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels([h.upper() for h in headers])
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setShowGrid(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(stretch_last)
    t.verticalHeader().setDefaultSectionSize(34)
    return t


def fill_table(t: QTableWidget, rows: Sequence[Sequence], data_col: int | None = None) -> None:
    t.setRowCount(0)
    t.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            it = QTableWidgetItem("" if val is None else str(val))
            if c == data_col:
                it.setData(Qt.UserRole, val)
            t.setItem(r, c, it)


class Msg:
    @staticmethod
    def info(parent, text): QMessageBox.information(parent, "NODORA", text)

    @staticmethod
    def warn(parent, text): QMessageBox.warning(parent, "NODORA", text)

    @staticmethod
    def ask(parent, text) -> bool:
        return QMessageBox.question(parent, "NODORA", text) == QMessageBox.Yes


# ----------------------------------------------------------------------------- tasas de tráfico
def fmt_rate(bps: float) -> str:
    for u in ("B/s", "KiB/s", "MiB/s", "GiB/s"):
        if bps < 1024 or u == "GiB/s":
            return f"{bps:.0f} {u}" if u == "B/s" else f"{bps:.1f} {u}"
        bps /= 1024
    return str(bps)


def _nice_max(v: float) -> float:
    if v <= 0:
        return 1024.0
    import math
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 5, 10):
        if v <= m * e:
            return m * e
    return 10 * e


class RateChart(QWidget):
    """Dos líneas (recibido / enviado) con escala automática. Datos reales en bytes por segundo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rx: list[float] = []
        self.tx: list[float] = []
        self.setMinimumHeight(190)

    def clear(self) -> None:
        self.rx, self.tx = [], []
        self.update()

    def push(self, rx: float, tx: float, limit: int = 90) -> None:
        self.rx = (self.rx + [rx])[-limit:]
        self.tx = (self.tx + [tx])[-limit:]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = theme.palette()
        r = QRectF(self.rect()).adjusted(74, 8, -6, -22)
        top = _nice_max(max(self.rx + self.tx + [0]))
        p.setPen(QPen(QColor(c["border"]), 1))
        for frac in (0, 0.5, 1):
            y = r.top() + r.height() * frac
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(0, y - 8, 70, 16), Qt.AlignRight | Qt.AlignVCenter, fmt_rate(top * (1 - frac)))
            p.setPen(QPen(QColor(c["border"]), 1))
        p.setPen(QColor(c["muted"]))
        p.drawText(QRectF(r.left(), self.height() - 18, 160, 14), Qt.AlignLeft, "Últimos 90 s")
        p.drawText(QRectF(r.right() - 60, self.height() - 18, 60, 14), Qt.AlignRight, "Ahora")
        if len(self.rx) < 2:
            p.drawText(r, Qt.AlignCenter, "Calculando…")
            return
        n = len(self.rx)
        for data, col in ((self.rx, c["accent"]), (self.tx, c["chart2"])):
            pts = [QPointF(r.left() + r.width() * i / (n - 1), r.bottom() - r.height() * v / top) for i, v in enumerate(data)]
            path = QPainterPath(pts[0])
            for pt in pts[1:]:
                path.lineTo(pt)
            p.setPen(QPen(QColor(col), 2))
            p.drawPath(path)


# ----------------------------------------------------------------------------- tarjeta pastel con muesca
class PastelTile(QWidget):
    """Tarjeta de color pastel con una muesca suave en el borde superior (estilo Ciruela).
    El texto interior usa tinta oscura para mantener el contraste sobre el pastel."""

    def __init__(self, idx: int = 0, parent=None):
        super().__init__(parent)
        pal = theme.palette()
        self.fill = QColor(pal["pastel"][idx % len(pal["pastel"])])
        self.ink = pal["on_pastel"]
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(20, 34, 20, 18)
        self.v.setSpacing(6)
        self.setStyleSheet(f"QLabel {{ color: {self.ink}; background: transparent; }} "
                           f"QLabel#eyebrow {{ color: {self.ink}; }} QLabel#muted {{ color: {self.ink}; }} "
                           f"QProgressBar {{ background: rgba(42,36,51,45); }} "
                           f"QProgressBar::chunk {{ background: {self.ink}; }}")

    def add(self, w) -> None:
        self.v.addWidget(w)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        body = QPainterPath()
        body.addRoundedRect(r, 24, 24)
        w = min(150.0, r.width() * 0.5)
        cut = QPainterPath()
        cut.addRoundedRect(QRectF(r.center().x() - w / 2, r.top() - 30, w, 52), 24, 24)   # muesca superior
        p.fillPath(body.subtracted(cut), QBrush(self.fill))
