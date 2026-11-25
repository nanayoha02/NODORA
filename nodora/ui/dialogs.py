"""Diálogos: diagnóstico del puerto de práctica (15), temporales (23) y ruta revelada (25)."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QVBoxLayout)

from ..core.validators import ValidationError
from ..ops.portdrill import MENU, PortDrill
from . import theme
from .widgets import Card, Msg, fill_table, fmt_bytes, make_table, muted, run_async


def _checks_text(checks) -> str:
    return "\n".join(f"{'✔' if c.passed else '✖'} {c.name}: {c.detail}" for c in checks)


class PortDrillDialog(QDialog):
    """Acción 15: ciclo completo de diagnóstico, corrección y restauración."""

    def __init__(self, lab, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Diagnóstico del puerto de práctica · Acción 15")
        self.resize(820, 780)
        self.lab = lab
        self.drill: PortDrill | None = None
        v = QVBoxLayout(self)
        v.addWidget(muted("Secuencia: 1) estado inicial → 2) explorar y relacionar → 3) elegir instrucción del menú → "
                          "4) verificar cierre → 5) guardar evidencia → 6) restaurar y verificar. "
                          "La aplicación no elige la solución por usted."))
        # 1-2
        c = Card("1-2 · Estado inicial y exploración")
        r = QHBoxLayout()
        self.b1 = QPushButton("1 · Guardar estado inicial")
        self.b2 = QPushButton("2 · Explorar rango e identificar puerto")
        self.b2.setEnabled(False)
        r.addWidget(self.b1)
        r.addWidget(self.b2)
        c.addl(r)
        self.out12 = QPlainTextEdit()
        self.out12.setReadOnly(True)
        self.out12.setFixedHeight(150)
        c.add(self.out12)
        v.addWidget(c)
        # 3
        m = Card("3 · Instrucción del menú")
        self.menu = QComboBox()
        for k, (t, d, _) in MENU.items():
            self.menu.addItem(f"{k} · {t} — {d}", k)
        self.param = QLineEdit()
        mr = QHBoxLayout()
        mr.addWidget(self.menu, 3)
        mr.addWidget(self.param, 1)
        m.addl(mr)
        br = QHBoxLayout()
        self.b3 = QPushButton("Mostrar instrucción real")
        self.b3x = QPushButton("Ejecutar")
        self.b3x.setObjectName("primary")
        self.b3x.setEnabled(False)
        br.addWidget(self.b3)
        br.addWidget(self.b3x)
        m.addl(br)
        m.add(muted("Instrucción que se enviará a BOSGAME:"))
        self.cmd = QPlainTextEdit()
        self.cmd.setReadOnly(True)
        self.cmd.setFixedHeight(90)
        m.add(self.cmd)
        m.add(muted("Salida:"))
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setFixedHeight(100)
        m.add(self.out)
        v.addWidget(m)
        # 4-6
        f = Card("4-6 · Verificación, evidencia y restauración")
        fr = QHBoxLayout()
        self.b4 = QPushButton("4 · Verificar cierre")
        self.b5 = QPushButton("5 · Guardar evidencia")
        self.b6 = QPushButton("6 · Verificar restauración")
        for b in (self.b4, self.b5, self.b6):
            fr.addWidget(b)
        f.addl(fr)
        self.out46 = QPlainTextEdit()
        self.out46.setReadOnly(True)
        self.out46.setFixedHeight(140)
        f.add(self.out46)
        self.ready = QLabel("")
        self.ready.setStyleSheet("font-weight:600; font-size:15px;")
        f.add(self.ready)
        v.addWidget(f)
        for b in (self.b3, self.b4, self.b5, self.b6):
            b.setEnabled(False)
        self.b1.clicked.connect(self.step1)
        self.b2.clicked.connect(self.step2)
        self.b3.clicked.connect(self.step3)
        self.b3x.clicked.connect(self.step3x)
        self.b4.clicked.connect(self.step4)
        self.b5.clicked.connect(self.step5)
        self.b6.clicked.connect(self.step6)
        self.menu.currentIndexChanged.connect(self._menu_changed)
        self._menu_changed()

    def _err(self, m):
        Msg.warn(self, m)

    def _menu_changed(self):
        k = self.menu.currentData()
        needs = MENU[k][2]
        self.param.setVisible(bool(needs))
        self.param.setPlaceholderText({"pid_o_nombre": "PID o nombre", "servicio": "Servicio", "pid": "PID"}.get(needs[0], "") if needs else "")
        if k in (3, 5):
            self.param.setText(self.lab.cfg.practice_service)
        elif k == 4 and self.drill and self.drill.st.pid:
            self.param.setText(str(self.drill.st.pid))
        self.b3x.setEnabled(False)

    def step1(self):
        def job():
            self.drill = PortDrill(self.lab)
            return self.drill.start()

        def done(d):
            self.out12.setPlainText("Estado inicial guardado en el historial:\n" + "\n".join(f"  {k}: {v}" for k, v in d.items() if k != "escucha")
                                    + f"\n  puertos en escucha dentro del rango: {[(p['port'], p['pid'], p['process']) for p in d['escucha']] or 'ninguno'}")
            self.b2.setEnabled(True)
            self.b3.setEnabled(True)
        run_async(job, done, self._err)

    def step2(self):
        def done(info):
            lines = [f"Puertos que aceptan conexión: {info['abiertos'] or 'ninguno'}",
                     f"Indeterminados (sin respuesta): {info['indeterminados'] or 'ninguno'}"]
            for r in info["relacion"]:
                lines.append(f"  puerto {r['puerto']} ↔ PID {r['pid']} · proceso {r['proceso'] or '?'} · servicio {', '.join(r['servicios']) or '?'}")
            lines.append("✔ Un único puerto abierto: identificado." if info["unico"] else
                         "✖ Se esperaba exactamente un puerto abierto en el rango; revise el escenario con el docente.")
            self.out12.setPlainText("\n".join(lines))
            self._menu_changed()
            self.b3.setEnabled(True)
        run_async(self.drill.scan_and_correlate, done, self._err)

    def step3(self):
        k = self.menu.currentData()
        txt = self.param.text().strip()
        key = {"pid_o_nombre": "pid_o_nombre", "servicio": "servicio", "pid": "pid"}.get(MENU[k][2][0]) if MENU[k][2] else None
        params = {key: txt} if key else {}
        try:
            c = self.drill.prepare(k, **params)
        except ValidationError as e:
            self.cmd.setPlainText("✖ " + str(e))
            self.b3x.setEnabled(False)
            return
        self.cmd.setPlainText(c.display)
        self.b3x.setEnabled(True)

    def step3x(self):
        self.b3x.setEnabled(False)
        self.out.setPlainText("Ejecutando…")

        def done(res):
            rc, out = res
            self.out.setPlainText(f"código de salida: {rc}\n{out}")
            self.b4.setEnabled(True)
            self.b6.setEnabled(True)
        run_async(self.drill.execute, done, lambda m: self.out.setPlainText("✖ " + m))

    def step4(self):
        def done(checks):
            self.out46.setPlainText(_checks_text(checks))
            self.b5.setEnabled(all(c.passed for c in checks))
        run_async(self.drill.verify_closed, done, lambda m: self.out46.setPlainText("✖ " + m))

    def step5(self):
        run_async(self.drill.save_correction_evidence,
                  lambda p: self.out46.appendPlainText(f"\n✔ Evidencia de corrección guardada: {p}"),
                  lambda m: self.out46.appendPlainText("✖ " + m))

    def step6(self):
        self.ready.setText("Verificando…")

        def done(checks):
            self.out46.setPlainText(_checks_text(checks))
            ok = self.drill.st.ready_for_next
            self.ready.setText("✔ Laboratorio listo para el siguiente estudiante" if ok else
                               "✖ Restauración incompleta: el laboratorio NO está listo")
            self.ready.setStyleSheet(f"font-weight:600; font-size:15px; color:{theme.palette()['ok' if ok else 'err']};")
        run_async(self.drill.verify_restored, done, lambda m: self.ready.setText("✖ " + m))


class TempDialog(QDialog):
    """Acción 23: analizar y limpiar Temporales con selección y confirmación."""

    def __init__(self, lab, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Temporales de práctica · Acción 23")
        self.resize(640, 520)
        self.lab = lab
        v = QVBoxLayout(self)
        v.addWidget(muted("Solo se examina la carpeta Temporales del estudiante."))
        self.lst = QListWidget()
        v.addWidget(self.lst)
        self.info = muted("")
        v.addWidget(self.info)
        self.confirm = QCheckBox("Confirmo que deseo borrar de forma permanente los archivos marcados")
        v.addWidget(self.confirm)
        r = QHBoxLayout()
        self.ba = QPushButton("Analizar")
        self.bc = QPushButton("Borrar seleccionados")
        self.bc.setObjectName("danger")
        r.addWidget(self.ba)
        r.addWidget(self.bc)
        v.addLayout(r)
        self.ba.clicked.connect(self.analyze)
        self.bc.clicked.connect(self.clean)
        self.lst.itemChanged.connect(self._tot)
        self.analyze()

    def analyze(self):
        def done(r):
            self.lst.blockSignals(True)
            self.lst.clear()
            if not r.ok:
                self.info.setText("✖ " + r.message)
            for f in (r.data or []):
                it = QListWidgetItem(f"{f['path']}   ({fmt_bytes(f['size'])})")
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Unchecked)
                it.setData(Qt.UserRole, (f["path"], f["size"]))
                self.lst.addItem(it)
            self.lst.blockSignals(False)
            if r.ok:
                self.info.setText(r.message + " Marque los que desea borrar.")
        run_async(self.lab.temp_candidates, done, lambda m: self.info.setText("✖ " + m))

    def _sel(self):
        return [self.lst.item(i).data(Qt.UserRole) for i in range(self.lst.count())
                if self.lst.item(i).checkState() == Qt.Checked]

    def _tot(self, *_):
        s = self._sel()
        self.info.setText(f"{len(s)} seleccionado(s) · {fmt_bytes(sum(x[1] for x in s))} a liberar")

    def clean(self):
        sel = [p for p, _ in self._sel()]
        if not sel:
            Msg.warn(self, "Marque al menos un archivo.")
            return
        if not self.confirm.isChecked():
            Msg.warn(self, "Marque la casilla de confirmación para borrar.")
            return
        if not Msg.ask(self, f"¿Borrar {len(sel)} archivo(s) de BOSGAME? Esta acción no se puede deshacer."):
            return

        def done(r):
            self.info.setText(("✔ " if r.ok else "✖ ") + r.message)
            self.confirm.setChecked(False)
            self.analyze()
        run_async(lambda: self.lab.clean_temp(sel, True), done, lambda m: self.info.setText("✖ " + m))


class RevealedDialog(QDialog):
    """Acción 25: recuperar un archivo desde la ruta que entrega el docente."""

    def __init__(self, lab, start_download, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recuperar desde ruta revelada · Acción 25")
        self.resize(680, 500)
        self.lab, self.start_download = lab, start_download
        v = QVBoxLayout(self)
        v.addWidget(muted("Excepción de lectura autorizada por el docente. El original no se modifica."))
        r = QHBoxLayout()
        self.path = QLineEdit(lab.cfg.revealed_path)
        self.path.setPlaceholderText(r"Ruta absoluta, p. ej. C:\Entrega docente\Archivos  (se admiten espacios)")
        self.bl = QPushButton("Listar archivos")
        r.addWidget(self.path, 1)
        r.addWidget(self.bl)
        v.addLayout(r)
        self.status = muted("")
        v.addWidget(self.status)
        self.tbl = make_table(["Nombre", "Tamaño"])
        v.addWidget(self.tbl)
        self.bd = QPushButton("Descargar seleccionado a Recuperados")
        self.bd.setObjectName("primary")
        v.addWidget(self.bd)
        self.files = []
        self.bl.clicked.connect(self.list_)
        self.bd.clicked.connect(self.download)

    def list_(self):
        def done(r):
            if not r.ok:
                self.status.setText("✖ " + r.message)
                self.files = []
                fill_table(self.tbl, [])
                return
            self.files = r.data["files"]
            self.status.setText("✔ " + r.message)
            fill_table(self.tbl, [(f["name"], fmt_bytes(f["size"])) for f in self.files])
        run_async(lambda: self.lab.revealed_list(self.path.text()), done, lambda m: self.status.setText("✖ " + m))

    def download(self):
        row = self.tbl.currentRow()
        if row < 0 or row >= len(self.files):
            Msg.warn(self, "Seleccione un archivo de la lista.")
            return
        self.start_download(self.files[row]["path"], "Recuperados", "25 Recuperar archivo desde ruta revelada")
        self.status.setText("Transferencia iniciada: siga el avance en Archivos y mantenimiento.")
