"""Páginas: Historial e informes (24) y Configuración."""
from __future__ import annotations

import os
from collections import Counter
from datetime import datetime, timedelta

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSpinBox, QVBoxLayout)

from ..core import startup
from ..core.config import APP_NAME, APP_VERSION
from ..core.style_math import FONTS, contrast_fg
from ..core.validators import ValidationError, safe_join, validate_port_range
from . import theme
from .pages_a import Page
from .widgets import BarChart, Card, Msg, Pill, fill_table, make_table, muted, run_async

CATEGORY = {"3": "Conexión SSH", "5": "Sistema", "6": "Sistema", "7": "Sistema", "8": "Sistema", "9": "Sistema",
            "10": "Red", "11": "Red", "12": "Red", "13": "Servicios", "14": "Administración", "15": "Administración",
            "16": "Archivos", "17": "Archivos", "18": "Transferencia", "19": "Transferencia", "20": "Archivos",
            "21": "Respaldo", "22": "Respaldo", "23": "Mantenimiento", "24": "Informe", "25": "Transferencia",
            "1": "Configuración", "2": "Identidad", "4": "Archivos"}


def category(action: str, result: str) -> str:
    if result == "error":
        return "Error"
    return CATEGORY.get(action.split(" ", 1)[0], "Otros")


# ======================================================================== Historial
class HistoryPage(Page):
    title, subtitle = "Historial e informes", "Cada acción, en su contexto."

    def __init__(self, state, nav=None):
        super().__init__(state, nav)
        self.hero("La historia de tu sistema.", "Consulta conexiones, acciones y eventos de NODORA.")
        c = Card("Actividad de los últimos 7 días")
        lg = QHBoxLayout()
        lg.addWidget(Pill("Conexiones", "warn"))
        lg.addWidget(Pill("Transferencias", "ok"))
        lg.addStretch()
        c.addl(lg)
        self.chart = BarChart()
        c.add(self.chart)
        self.col.addWidget(c)

        t = Card("Registro de actividad", "Diferencia 'ejecutada' (el comando terminó) de 'verificada' (se comprobó el estado real).")
        f = QHBoxLayout()
        self.day = QComboBox()
        self.cat = QComboBox()
        self.res = QComboBox()
        self.res.addItems(["Todos los resultados", "verificada", "ejecutada", "error", "cancelada"])
        f.addWidget(self.day)
        f.addWidget(self.cat)
        f.addWidget(self.res)
        f.addStretch()
        t.addl(f)
        self.tbl = make_table(["Fecha y hora", "Categoría", "Acción", "Resultado", "Detalle"])
        self.tbl.setMinimumHeight(340)
        t.add(self.tbl)
        b = QHBoxLayout()
        self.b_rep = QPushButton("Generar informe y sincronizar (acción 24)")
        self.b_rep.setObjectName("primary")
        self.b_sync = QPushButton("Sincronizar pendientes")
        self.b_open = QPushButton("Abrir carpeta local")
        for x in (self.b_rep, self.b_sync, self.b_open):
            b.addWidget(x)
        b.addStretch()
        t.addl(b)
        self.status = muted("")
        t.add(self.status)
        self.col.addWidget(t)
        self.col.addStretch()
        for w in (self.day, self.cat, self.res):
            w.currentIndexChanged.connect(self._fill)
        self.b_rep.clicked.connect(self._report)
        self.b_sync.clicked.connect(self._sync)
        self.b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.state.cfg.local_dir)))
        self.rows: list[dict] = []

    def showEvent(self, e):
        super().showEvent(e)
        self.reload()

    def reload(self):
        self.rows = self.state.log.all_rows()
        days = sorted({r["timestamp"][:10] for r in self.rows}, reverse=True)
        cats = sorted({category(r["action"], r["result"]) for r in self.rows})
        for cb, items, first in ((self.day, days, "Todas las fechas"), (self.cat, cats, "Todas las categorías")):
            cb.blockSignals(True)
            cur = cb.currentText()
            cb.clear()
            cb.addItems([first] + items)
            if cur in items:
                cb.setCurrentText(cur)
            cb.blockSignals(False)
        self._chart()
        self._fill()
        n = len(self.state.log.pending())
        self.status.setText(f"{len(self.rows)} registros · {n} pendiente(s) de sincronizar con BOSGAME.")

    def _chart(self):
        today = datetime.now().date()
        keys = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
        con, tra = Counter(), Counter()
        for r in self.rows:
            d = r["timestamp"][:10]
            n = r["action"].split(" ", 1)[0]
            if n == "3" and "Conectar" in r["action"] and r["result"] != "error":
                con[d] += 1
            elif n in ("18", "19", "25"):
                tra[d] += 1
        names = ["Hoy" if k == today else k.strftime("%d %b") for k in keys]
        self.chart.set(names, [con[k.isoformat()] for k in keys], [tra[k.isoformat()] for k in keys])

    def _fill(self):
        d = self.day.currentText()
        c = self.cat.currentText()
        s = self.res.currentText()
        out = []
        for r in reversed(self.rows):
            cat = category(r["action"], r["result"])
            if self.day.currentIndex() > 0 and r["timestamp"][:10] != d:
                continue
            if self.cat.currentIndex() > 0 and cat != c:
                continue
            if self.res.currentIndex() > 0 and r["result"] != s:
                continue
            out.append((r["timestamp"].replace("T", " ")[:19], cat, r["action"], r["result"],
                        (r["error"] or r["evidence"] or r["destination"] or r["params"])[:90]))
        fill_table(self.tbl, out)

    def _report(self):
        self.do(lambda l: l.build_report(), lambda r: (self.status.setText(("✔ " if r.verified else "• ") + r.message), self.reload()),
                self.status, "Generando informe…")

    def _sync(self):
        lab = self.lab()
        if not lab:
            return

        def job():
            return lab.log.sync(lab.s, safe_join(lab.base, "actividad.csv"))
        run_async(job, lambda r: (self.status.setText(f"✔ Sincronizado: {r[0]} nuevas, {r[1]} ya existían."), self.reload()),
                  lambda m: self.status.setText("✖ " + m + " (los registros siguen pendientes)"))


# ======================================================================== Configuración
class SettingsPage(Page):
    title, subtitle = "Configuración", "Un espacio de trabajo a tu medida."
    theme_changed = Signal()

    def __init__(self, state, nav=None):
        super().__init__(state, nav)
        self.hero("Haz que NODORA trabaje a tu manera.", "Preferencias guardadas localmente en tu equipo.")
        c = state.cfg
        a = Card("Apariencia", "Un entorno claro para mantener el foco.")
        row = QHBoxLayout()
        self.grp = QButtonGroup(self)
        for i, (k, lbl) in enumerate((("smart", "Smart"), ("plum", "Ciruela"), ("lime", "Lima"), ("night", "Noche"), ("ios", "iPhone"), ("sage", "Salvia"), ("plush", "Peluche"), ("light", "Claro"), ("dark", "Oscuro"), ("system", "Sistema"))):
            b = QPushButton(lbl)
            b.setCheckable(True)
            b.setChecked(c.theme == k)
            b.setObjectName("nav")
            b.setStyleSheet("text-align:center;")
            self.grp.addButton(b, i)
            b.clicked.connect(lambda _=False, k=k: self._set_theme(k))
            row.addWidget(b)
        a.addl(row)
        self.col.addWidget(a)

        # ---- personalizar: colores, letras y estilo
        pz = Card("Personalizar estilo", "Elige tu color de acento, el color y el tipo de letra, y qué tan redondeado se ve todo.")
        pr = QHBoxLayout()
        pr.addWidget(QLabel("Paletas rápidas:"))
        for name, hexv in (("Índigo", "#5671E6"), ("Lima", "#A3E635"), ("Rosa", "#F28BA4"), ("Salvia", "#7F9F89"),
                           ("Naranja", "#F59E0B"), ("Turquesa", "#14B8A6"), ("Violeta", "#8B5CF6"), ("Rojo", "#E5484D")):
            sw = QPushButton()
            sw.setFixedSize(30, 30)
            sw.setToolTip(name)
            sw.setCursor(Qt.PointingHandCursor)
            sw.setStyleSheet(f"QPushButton {{ background: {hexv}; border: 2px solid transparent; border-radius: 15px; padding: 0; }}"
                             f"QPushButton:hover {{ border-color: #FFFFFF; }}")
            sw.clicked.connect(lambda _=False, h=hexv: self._pick("accent", h))
            pr.addWidget(sw)
        pr.addStretch()
        pz.addl(pr)
        cr = QHBoxLayout()
        self.b_acc = QPushButton()
        self.b_txt = QPushButton()
        self.b_acc.clicked.connect(lambda: self._pick("accent"))
        self.b_txt.clicked.connect(lambda: self._pick("text"))
        b_rst = QPushButton("Restablecer colores")
        b_rst.clicked.connect(self._reset_colors)
        cr.addWidget(self.b_acc)
        cr.addWidget(self.b_txt)
        cr.addWidget(b_rst)
        cr.addStretch()
        pz.addl(cr)
        self.cur_accent, self.cur_text = c.custom_accent, c.custom_text
        self._paint_swatches()
        pf = QFormLayout()
        self.font_cb = QComboBox()
        for fam in FONTS:
            self.font_cb.addItem(fam or "Predeterminada del tema", fam)
        self.font_cb.setCurrentIndex(max(0, self.font_cb.findData(c.font_family)))
        self.font_sz = QSpinBox()
        self.font_sz.setRange(11, 18)
        self.font_sz.setSuffix(" px")
        self.font_sz.setValue(c.font_size)
        self.corn = QComboBox()
        for lbl, v in (("Cuadradas", "square"), ("Suaves (predeterminado)", "soft"), ("Muy redondeadas", "round")):
            self.corn.addItem(lbl, v)
        self.corn.setCurrentIndex(max(0, self.corn.findData(c.corners)))
        pf.addRow("Tipo de letra", self.font_cb)
        pf.addRow("Tamaño de letra", self.font_sz)
        pf.addRow("Esquinas", self.corn)
        pz.addl(pf)
        b_apply = QPushButton("Aplicar estilo")
        b_apply.setObjectName("primary")
        b_apply.clicked.connect(self._apply_style)
        pz.add(b_apply)
        pz.add(muted("Para ver todos los cambios NODORA se reinicia; tus colores quedan guardados en este equipo."))
        self.col.addWidget(pz)

        g = Card("Preferencias generales", "Tu rutina, con menos pasos.")
        self.sw = QCheckBox("Iniciar NODORA con Windows")
        self.sw.setChecked(c.start_with_windows)
        self.sw.setEnabled(startup.supported())
        self.tray = QCheckBox("Minimizar al área de notificación al cerrar la ventana")
        self.tray.setChecked(c.minimize_to_tray)
        self.n1 = QCheckBox("Alertas del sistema (CPU alta sostenida)")
        self.n1.setChecked(c.notify_alerts)
        self.n2 = QCheckBox("Avisar cuando termine una transferencia")
        self.n2.setChecked(c.notify_transfers)
        for w in (self.sw, self.tray, self.n1, self.n2):
            g.add(w)
        self.col.addWidget(g)

        k = Card("Conexión y actualización", "Ajustes para la sesión remota.")
        f = QFormLayout()
        self.timeout = QComboBox()
        self.timeout.addItems(["5", "10", "20", "30"])
        self.timeout.setCurrentText(str(c.connect_timeout))
        self.interval = QComboBox()
        self.interval.addItems(["2", "5", "10", "30"])
        self.interval.setCurrentText(str(c.refresh_seconds))
        self.unit = QComboBox()
        self.unit.addItems(["MiB/s", "MB/s"])
        self.unit.setCurrentText(c.transfer_unit)
        f.addRow("Tiempo de espera SSH (s)", self.timeout)
        f.addRow("Intervalo de actualización (s)", self.interval)
        f.addRow("Unidad de velocidad", self.unit)
        k.addl(f)
        k.add(muted("MiB/s = múltiplos de 1 048 576 bytes · MB/s = millones de bytes por segundo."))
        self.col.addWidget(k)

        lab = Card("Parámetros del laboratorio", "Los define el docente; se aplican sin modificar el código.")
        lf = QFormLayout()
        self.remote_base = QLineEdit(c.remote_base)
        self.local_dir = QLineEdit(c.local_dir)
        self.rng = QLineEdit(c.lab_port_range)
        self.svcs = QLineEdit(c.lab_services)
        self.psvc = QLineEdit(c.practice_service)
        self.pproc = QLineEdit(c.practice_process)
        self.rev = QLineEdit(c.revealed_path)
        lf.addRow("Carpeta base remota", self.remote_base)
        lf.addRow("Carpeta local de trabajo", self.local_dir)
        lf.addRow("Rango TCP autorizado", self.rng)
        lf.addRow("Servicios a consultar (coma)", self.svcs)
        lf.addRow("Servicio de práctica", self.psvc)
        lf.addRow("Proceso de práctica (opcional)", self.pproc)
        lf.addRow("Ruta revelada (acción 25)", self.rev)
        lab.addl(lf)
        self.col.addWidget(lab)

        lg = Card("Registros", "Trazabilidad sin exponer datos sensibles.")
        lg.add(muted("Las contraseñas y claves nunca se guardan ni se registran. Cada operación se anota como 'ejecutada' "
                     "o 'verificada' en actividad.csv (local y en BOSGAME)."))
        self.col.addWidget(lg)

        sv = QHBoxLayout()
        self.b_save = QPushButton("Guardar configuración")
        self.b_save.setObjectName("primary")
        self.msg = muted("")
        sv.addWidget(self.b_save)
        sv.addWidget(self.msg, 1)
        self.col.addLayout(sv)

        ab = Card("Acerca de NODORA", "REMOTE SYSTEM MANAGEMENT")
        t = QLabel(APP_NAME)
        t.setObjectName("brand")
        ab.add(t)
        ab.add(muted(
            f"Versión {APP_VERSION}\n"
            "Autor: " + (c.student_name or "(complete su nombre en Conexión SSH)") + "\n"
            "Propósito: monitorear, administrar y mantener de forma remota el mini PC BOSGAME por SSH/SFTP en una red local, "
            "dejando evidencias verificables de cada operación.\n"
            "Nombre: NODORA — 'nodo' (el equipo remoto) + 'ora' (hora/guardia): vigilancia continua de un nodo.\n"
            "Compatibilidad: cliente Windows 10/11 (64 bits); equipo remoto Windows con OpenSSH Server o Linux con OpenSSH.\n"
            "Créditos y licencias: Qt for Python / PySide6 (LGPL-3.0), paramiko (LGPL-2.1). Logo, icono y gráficos: "
            "diseño original del autor. Tipografía: Inter (SIL OFL 1.1) si está instalada; de lo contrario, Segoe UI del sistema."))
        self.col.addWidget(ab)
        self.col.addStretch()
        self.b_save.clicked.connect(self.save)

    def _paint_swatches(self):
        for b, val, lbl in ((self.b_acc, self.cur_accent, "Color de acento"), (self.b_txt, self.cur_text, "Color de letras")):
            shown = val or "tema"
            b.setText(f"{lbl}: {shown}")
            if val:
                fg = contrast_fg(val)
                b.setStyleSheet(f"QPushButton {{ background: {val}; color: {fg}; border-color: {val}; }}")
            else:
                b.setStyleSheet("")

    def _pick(self, which, hexv=None):
        if hexv is None:
            cur = self.cur_accent if which == "accent" else self.cur_text
            col = QColorDialog.getColor(QColor(cur or "#5671E6"), self, "Elige un color")
            if not col.isValid():
                return
            hexv = col.name().upper()
        if which == "accent":
            self.cur_accent = hexv
        else:
            self.cur_text = hexv
        self._paint_swatches()

    def _reset_colors(self):
        self.cur_accent = self.cur_text = ""
        self._paint_swatches()

    def _apply_style(self):
        c = self.state.cfg
        c.custom_accent, c.custom_text = self.cur_accent, self.cur_text
        c.font_family, c.font_size = self.font_cb.currentData() or "", self.font_sz.value()
        c.corners = self.corn.currentData() or "soft"
        c.sanitize_style()
        c.save()
        self.theme_changed.emit()
        self.msg.setText("✔ Estilo guardado.")

    def _set_theme(self, k):
        self.state.cfg.theme = k
        self.state.cfg.save()
        self.theme_changed.emit()
        self.msg.setText("✔ Estilo guardado. Reinicie NODORA para aplicar barra lateral y tarjetas por completo.")

    def save(self):
        c = self.state.cfg
        try:
            validate_port_range(self.rng.text())
        except ValidationError as e:
            self.msg.setText("✖ " + str(e))
            return
        c.connect_timeout, c.refresh_seconds = int(self.timeout.currentText()), int(self.interval.currentText())
        c.transfer_unit = self.unit.currentText()
        c.remote_base, c.lab_port_range = self.remote_base.text().strip(), self.rng.text().strip()
        c.local_dir = self.local_dir.text().strip() or c.local_dir
        c.lab_services, c.practice_service = self.svcs.text().strip(), self.psvc.text().strip()
        c.practice_process, c.revealed_path = self.pproc.text().strip(), self.rev.text().strip()
        c.minimize_to_tray, c.notify_alerts, c.notify_transfers = self.tray.isChecked(), self.n1.isChecked(), self.n2.isChecked()
        c.start_with_windows = self.sw.isChecked()
        try:
            startup.set_enabled(c.start_with_windows)
        except OSError as e:
            self.msg.setText(f"✖ No se pudo cambiar el inicio con Windows: {e}")
            return
        c.save()
        self.state.log_reload()
        self.msg.setText("✔ Configuración guardada.")
