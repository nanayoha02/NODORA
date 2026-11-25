"""Páginas: Red y servicios (10-15) y Archivos y mantenimiento (16-23, 25)."""
from __future__ import annotations

import dataclasses
import os
import threading
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QProgressBar, QPushButton, QVBoxLayout, QWidget)

from ..core.validators import ValidationError, validate_name, safe_join
from ..core.activity import Record
from ..ops import transfer
from . import theme
from .dialogs import PortDrillDialog, RevealedDialog, TempDialog
from .pages_a import Page
from .widgets import (Card, Msg, Pill, eyebrow, fill_table, fmt_bytes, make_table, muted, run_async)


# ======================================================================== Red y servicios
class NetworkPage(Page):
    title, subtitle = "Red y servicios", "Conectividad y servicios, en un solo lugar."
    scan_prog = Signal(int, int)      # el escaneo corre en un hilo: la barra se actualiza por señal

    def __init__(self, state, nav=None):
        super().__init__(state, nav)
        self.hero("Tu red, bajo control.", "Supervisa la conexión y administra los servicios del sistema.")
        # conectividad (11)
        top = QHBoxLayout()
        c1 = Card()
        c1.add(eyebrow("Conectividad con BOSGAME"))
        self.conn_n = QLabel("—")
        self.conn_n.setObjectName("hero")
        self.conn_s = muted("Acción 11 · método, respuesta y tiempo")
        self.b_conn = QPushButton("Comprobar conectividad")
        c1.add(self.conn_n)
        c1.add(self.conn_s)
        c1.add(self.b_conn)
        c2 = Card()
        c2.add(eyebrow("Latencia"))
        self.lat_n = QLabel("—")
        self.lat_n.setObjectName("hero")
        self.lat_s = muted("ICMP y TCP medidos por separado")
        c2.add(self.lat_n)
        c2.add(self.lat_s)
        top.addWidget(c1, 1)
        top.addWidget(c2, 1)
        self.col.addLayout(top)
        # interfaces (10)
        ci = Card("Interfaz de red", "Acción 10 · admite varias interfaces y campos vacíos")
        self.ifaces = make_table(["Interfaz", "IPv4", "Prefijo", "MAC", "Gateway", "DNS"])
        self.ifaces.setMinimumHeight(140)
        self.b_net = QPushButton("Consultar configuración de red")
        ci.add(self.ifaces)
        ci.add(self.b_net)
        self.col.addWidget(ci)
        # puertos (12)
        cp = Card("Puertos TCP autorizados", "Acción 12 · solo se examina el rango definido por el docente")
        r = QHBoxLayout()
        self.range = QLineEdit(state.cfg.lab_port_range)
        self.b_scan = QPushButton("Examinar rango")
        self.b_scan.setObjectName("primary")
        self.scan_bar = QProgressBar()
        self.scan_bar.setTextVisible(False)
        r.addWidget(QLabel("Rango:"))
        r.addWidget(self.range, 1)
        r.addWidget(self.b_scan)
        cp.addl(r)
        cp.add(self.scan_bar)
        self.scan_s = muted("Aceptada = conexión establecida · Rechazada = el equipo respondió que no hay servicio · "
                            "Sin respuesta = indeterminado (firewall, equipo apagado o filtrado).")
        cp.add(self.scan_s)
        self.ports = make_table(["Puerto", "Resultado"])
        self.ports.setMinimumHeight(150)
        cp.add(self.ports)
        self.col.addWidget(cp)
        # servicios (13, 14)
        cs = Card("Servicios y procesos", "Acción 13 · estado real de los servicios definidos por el docente")
        self.svcs = make_table(["Servicio", "Descripción", "Estado", "Inicio"])
        self.svcs.setMinimumHeight(150)
        sr = QHBoxLayout()
        self.b_svc = QPushButton("Consultar servicios")
        sr.addWidget(self.b_svc)
        sr.addStretch()
        cs.add(self.svcs)
        cs.addl(sr)
        cs.add(eyebrow("Servicio de práctica · acción 14"))
        self.practice = muted("")
        cs.add(self.practice)
        pr = QHBoxLayout()
        self.b_start, self.b_stop, self.b_restart = QPushButton("Iniciar"), QPushButton("Detener"), QPushButton("Reiniciar")
        for b in (self.b_start, self.b_stop, self.b_restart):
            pr.addWidget(b)
        pr.addStretch()
        cs.addl(pr)
        self.svc_out = muted("")
        cs.add(self.svc_out)
        self.col.addWidget(cs)
        # diagnóstico (15)
        cd = Card("Diagnóstico del puerto de práctica", "Acción 15 · diagnosticar, cerrar y restaurar con evidencia")
        self.b_drill = QPushButton("Abrir asistente de diagnóstico…")
        self.b_drill.setObjectName("primary")
        cd.add(self.b_drill)
        self.col.addWidget(cd)
        self.col.addStretch()

        self.scan_prog.connect(self._scan_progress)
        self.b_conn.clicked.connect(self._conn)
        self.b_net.clicked.connect(lambda: self.do(lambda l: l.network(), self._net_done))
        self.b_scan.clicked.connect(self._scan)
        self.b_svc.clicked.connect(lambda: self.do(lambda l: l.services(), self._svc_done, self.svc_out))
        for b, a in ((self.b_start, "start"), (self.b_stop, "stop"), (self.b_restart, "restart")):
            b.clicked.connect(lambda _=False, a=a: self._svc_action(a))
        self.b_drill.clicked.connect(lambda: PortDrillDialog(self.state.lab, self).exec() if self.lab() else None)
        self.refresh_labels()

    def refresh_labels(self):
        self.practice.setText(f"Servicio autorizado: {self.state.cfg.practice_service}")

    def _conn(self):
        self.conn_n.setText("Comprobando…")
        self.do(lambda l: l.connectivity(), self._conn_done, None)

    def _conn_done(self, r):
        d = r.data
        self.conn_n.setText("Conectado" if r.ok else "Sin respuesta")
        self.conn_n.setStyleSheet(f"color:{theme.palette()['ok' if r.ok else 'err']};")
        ic, tc = d["icmp"], d["tcp"]
        self.conn_s.setText(r.message)
        self.lat_n.setText(f"{ic['ms']:.0f} ms (ICMP)" if ic["ms"] is not None else
                           (f"{tc['ms']:.0f} ms (TCP)" if tc["ms"] is not None else "—"))
        self.lat_s.setText(f"ICMP: {ic['text']} · TCP {self.state.cfg.port}: {tc['state']}"
                           + (f" ({tc['ms']:.0f} ms)" if tc["ms"] is not None else ""))

    def _net_done(self, r):
        if not r.ok:
            Msg.warn(self, r.message)
            return
        j = lambda x: ", ".join(map(str, x)) or "—"
        fill_table(self.ifaces, [(n["name"], j(n["ipv4"]), j(n["prefix"]), n["mac"] or "—", j(n["gateway"]), j(n["dns"]))
                                 for n in r.data])

    def _scan(self):
        self.state.cfg.lab_port_range = self.range.text().strip()
        self.scan_bar.setValue(0)
        self.scan_s.setText("Examinando…")
        txt = self.range.text()
        lab = self.lab()
        if not lab:
            return

        def job():
            return lab.scan_ports(txt, progress=lambda d, t: self.scan_prog.emit(d, t))

        def done(r):
            if not r.ok:
                self.scan_s.setText("✖ " + r.message)
                return
            self.scan_s.setText("✔ " + r.message)
            names = {"abierto": "Conexión aceptada", "rechazado": "Conexión rechazada", "sin respuesta": "Sin respuesta (indeterminado)"}
            fill_table(self.ports, [(p, names.get(s, s)) for p, s in sorted(r.data["ports"].items())])
        run_async(job, done, lambda m: self.scan_s.setText("✖ " + m))

    def _scan_progress(self, d, t):
        self.scan_bar.setMaximum(t)
        self.scan_bar.setValue(d)

    def _svc_done(self, r):
        if not r.ok:
            self.svc_out.setText("✖ " + r.message)
            return
        self.svc_out.setText("✔ " + r.message)
        fill_table(self.svcs, [(s["name"], s["display"], s["state"], s["start"]) for s in r.data])

    def _svc_action(self, action):
        verbo = {"start": "iniciar", "stop": "detener", "restart": "reiniciar"}[action]
        if not Msg.ask(self, f"¿Desea {verbo} el servicio de práctica '{self.state.cfg.practice_service}' en BOSGAME?"):
            return
        self.do(lambda l: l.practice_service(action), lambda r: self.svc_out.setText(("✔ " if r.verified else "✖ ") + r.message),
                self.svc_out, "Ejecutando y comprobando…")


# ======================================================================== Transferencias
class TransferRow(QFrame):
    snap = Signal(object)

    def __init__(self, title: str, cancel_ev: threading.Event, unit: str):
        super().__init__()
        self.setObjectName("card")
        self.unit = unit
        v = QVBoxLayout(self)
        top = QHBoxLayout()
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight:600;")
        self.pill = Pill("Conectando", "info")
        self.cancel = QPushButton("Cancelar")
        self.cancel.clicked.connect(cancel_ev.set)
        top.addWidget(self.title, 1)
        top.addWidget(self.pill)
        top.addWidget(self.cancel)
        v.addLayout(top)
        self.paths = muted("")
        v.addWidget(self.paths)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        v.addWidget(self.bar)
        self.metrics = muted("")
        v.addWidget(self.metrics)
        self.integ = muted("")
        v.addWidget(self.integ)
        self.snap.connect(self._upd)

    def _upd(self, p):
        kind = {"Completado y verificado": "ok", "Transfiriendo": "warn", "Verificando": "warn", "Conectando": "info"}.get(p.state, "err")
        self.pill.set(p.state, kind)
        self.paths.setText(f"{p.host} · {p.source}  →  {p.dest}")
        self.bar.setValue(int(p.percent * 10))
        u = self.unit
        self.metrics.setText(
            f"{transfer.fmt_size(p.done, u)} de {transfer.fmt_size(p.total, u)} ({p.percent:.0f} %) · "
            f"actual {transfer.fmt_speed(p.current_bps, u)} · promedio {transfer.fmt_speed(p.avg_bps, u)} · "
            f"transcurrido {transfer.fmt_eta(p.t_transfer_running)} · restante {transfer.fmt_eta(p.eta)}")
        if p.state in ("Completado y verificado",) or p.src_hash:
            self.integ.setText(f"Conexión {p.t_connect:.2f} s · transferencia {p.t_transfer:.2f} s · verificación {p.t_verify:.2f} s\n"
                               f"SHA-256 origen  {p.src_hash}\nSHA-256 destino {p.dst_hash}  "
                               f"{'✔ coinciden' if p.src_hash == p.dst_hash and p.src_hash else '✖ NO coinciden'}")
        if p.error:
            self.integ.setText(("✖ " + p.error) + ("\n" + self.integ.text() if self.integ.text() else ""))
        if p.state in ("Completado y verificado", "Cancelado", "Incompleto", "Error"):
            self.cancel.setEnabled(False)


class TransferPanel(QWidget):
    ask = Signal(str, object)
    finished = Signal()

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(0, 0, 0, 0)
        self.empty = muted("Sin transferencias todavía.")
        self.v.addWidget(self.empty)
        self.ask.connect(self._ask)

    def _ask(self, path, box):
        box["ok"] = Msg.ask(self, f"El destino ya existe:\n{path}\n\n¿Desea sobrescribirlo?")
        box["ev"].set()

    def _overwrite(self, path) -> bool:
        box = {"ev": threading.Event(), "ok": False}
        self.ask.emit(path, box)
        box["ev"].wait(300)
        return box["ok"]

    def start(self, kind: str, src: str, dst: str, action: str):
        lab = self.state.lab
        if not lab:
            Msg.warn(self, "Conecte con BOSGAME primero.")
            return
        cancel = threading.Event()
        unit = self.state.cfg.transfer_unit
        row = TransferRow(f"{'⬆' if kind == 'up' else '⬇'} {os.path.basename(src)}", cancel, unit)
        self.empty.hide()
        self.v.insertWidget(0, row)
        last = {"t": 0.0, "s": ""}

        def on_prog(p):
            now = time.perf_counter()
            if p.state != last["s"] or now - last["t"] > 0.12:
                last["t"], last["s"] = now, p.state
                row.snap.emit(dataclasses.replace(p))

        def job():
            fn = transfer.upload if kind == "up" else transfer.download
            p = fn(lab.s, src, dst, on_exists=self._overwrite, cancel=cancel, on_progress=on_prog)
            res = "verificada" if p.verified else ("cancelada" if p.state == "Cancelado" else "error")
            lab._rec(action, res, source=p.source, destination=p.dest, error=p.error,
                     params={"bytes": p.total, "estado": p.state, "unidad": unit,
                             "vel_prom": transfer.fmt_speed(p.total / p.t_transfer if p.t_transfer > 0 else 0.0, unit),
                             "t_conexion_s": round(p.t_connect, 2), "t_transfer_s": round(p.t_transfer, 2),
                             "t_verif_s": round(p.t_verify, 2), "sha256": p.src_hash[:16]})
            return p

        run_async(job, lambda p: self.finished.emit(), lambda m: row.metrics.setText("✖ " + m))


# ======================================================================== Archivos y mantenimiento
class FilesPage(Page):
    title, subtitle = "Archivos y mantenimiento", "Tus archivos y herramientas, a distancia."

    def __init__(self, state, nav=None):
        super().__init__(state, nav)
        self.hero("Tu espacio remoto, siempre organizado.", "SFTP seguro · carpeta personal en BOSGAME")
        self.rel = ""
        ex = Card("Carpeta personal", "Acciones 16 y 17 · la navegación no puede salir de tu carpeta asignada")
        nav_r = QHBoxLayout()
        self.path = QLabel("—")
        self.path.setStyleSheet("font-weight:600;")
        self.b_up, self.b_refresh, self.b_mk = QPushButton("⬆ Subir nivel"), QPushButton("Actualizar"), QPushButton("Crear carpeta")
        nav_r.addWidget(self.path, 1)
        for b in (self.b_up, self.b_refresh, self.b_mk):
            nav_r.addWidget(b)
        ex.addl(nav_r)
        self.tbl = make_table(["Nombre", "Tipo", "Tamaño"])
        self.tbl.setMinimumHeight(240)
        ex.add(self.tbl)
        ar = QHBoxLayout()
        self.b_send = QPushButton("Enviar archivo a BOSGAME")
        self.b_send.setObjectName("primary")
        self.b_get = QPushButton("Descargar seleccionado")
        self.b_copy = QPushButton("Copiar en BOSGAME")
        for b in (self.b_send, self.b_get, self.b_copy):
            ar.addWidget(b)
        ar.addStretch()
        ex.addl(ar)
        self.fstatus = muted("")
        ex.add(self.fstatus)
        self.col.addWidget(ex)

        tr = Card("Transferencias", "Acciones 18, 19 y 25 · mediciones reales, la ventana sigue operativa")
        self.panel = TransferPanel(state)
        tr.add(self.panel)
        self.col.addWidget(tr)

        mt = Card("Respaldos y mantenimiento", "Acciones 20 a 25")
        r1 = QHBoxLayout()
        self.bk = QPushButton("Crear respaldo de la carpeta personal")
        self.bk.setObjectName("primary")
        self.rs_cb = QComboBox()
        self.rs_cb.setMinimumWidth(260)
        self.rs_refresh = QPushButton("↻")
        self.rs = QPushButton("Restaurar seleccionado")
        r1.addWidget(self.bk)
        r1.addStretch()
        r1.addWidget(self.rs_cb)
        r1.addWidget(self.rs_refresh)
        r1.addWidget(self.rs)
        mt.addl(r1)
        r2 = QHBoxLayout()
        self.b_tmp = QPushButton("Analizar y limpiar temporales…")
        self.b_rev = QPushButton("Recuperar desde ruta revelada…")
        r2.addWidget(self.b_tmp)
        r2.addWidget(self.b_rev)
        r2.addStretch()
        mt.addl(r2)
        self.mstatus = muted("")
        mt.add(self.mstatus)
        self.col.addWidget(mt)
        self.col.addStretch()

        self.b_refresh.clicked.connect(self.reload)
        self.b_up.clicked.connect(self._up)
        self.tbl.doubleClicked.connect(self._open)
        self.b_mk.clicked.connect(self._mkdir)
        self.b_send.clicked.connect(self._send)
        self.b_get.clicked.connect(self._get)
        self.b_copy.clicked.connect(self._copy)
        self.bk.clicked.connect(self._backup)
        self.rs_refresh.clicked.connect(self._load_backups)
        self.rs.clicked.connect(self._restore)
        self.b_tmp.clicked.connect(lambda: TempDialog(self.state.lab, self).exec() if self.lab() else None)
        self.b_rev.clicked.connect(lambda: RevealedDialog(self.state.lab, self.download_to, self).exec() if self.lab() else None)
        self.panel.finished.connect(self.reload)

    # ---- explorar (16)
    def on_connection(self, up):
        if up:
            self.reload()
            self._load_backups()

    def reload(self):
        if not self.state.lab:
            return
        self.do(lambda l: l.explore(self.rel), self._listed, self.fstatus)

    def _listed(self, r):
        if not r.ok:
            self.fstatus.setText("✖ " + r.message)
            return
        self.fstatus.setText("")
        self.path.setText(r.data["path"])
        self.entries = r.data["entries"]
        fill_table(self.tbl, [("📁 " + e["name"] if e["type"] == "Carpeta" else e["name"], e["type"],
                               "—" if e["size"] is None else fmt_bytes(e["size"])) for e in self.entries])

    def _up(self):
        if self.rel:
            self.rel = self.rel.replace("\\", "/").rpartition("/")[0]
            self.reload()

    def _open(self, idx):
        e = self.entries[idx.row()]
        if e["type"] == "Carpeta":
            self.rel = (self.rel + "/" if self.rel else "") + e["name"]
            self.reload()

    def _sel(self):
        r = self.tbl.currentRow()
        return self.entries[r] if 0 <= r < len(getattr(self, "entries", [])) else None

    # ---- 17
    def _mkdir(self):
        name, ok = QInputDialog.getText(self, "Crear subcarpeta", "Nombre de la carpeta:")
        if ok:
            self.do(lambda l: l.make_subfolder(name, self.rel),
                    lambda r: (self.fstatus.setText(("✔ " if r.ok else "✖ ") + r.message), self.reload()), self.fstatus)

    # ---- 18
    def _send(self):
        lab = self.lab()
        if not lab:
            return
        p, _ = QFileDialog.getOpenFileName(self, "Archivo a enviar a BOSGAME")
        if not p:
            return
        try:
            name = validate_name(os.path.basename(p))
            dst = safe_join(lab.base, *([self.rel] if self.rel else []), name)
        except ValidationError as e:
            Msg.warn(self, f"{e}\nRenombre el archivo local antes de enviarlo.")
            return
        self.panel.start("up", p, dst, "18 Enviar un archivo a BOSGAME")

    # ---- 19
    def download_to(self, remote_path: str, subdir: str, action: str):
        lab = self.lab()
        if not lab:
            return
        name = remote_path.replace("\\", "/").rsplit("/", 1)[-1]
        folder = os.path.join(self.state.cfg.local_dir, subdir)
        self.panel.start("down", remote_path, os.path.join(folder, name), action)

    def _get(self):
        e, lab = self._sel(), self.lab()
        if not lab or not e or e["type"] != "Archivo":
            Msg.warn(self, "Seleccione un archivo (no una carpeta).")
            return
        remote = safe_join(lab.base, *([self.rel] if self.rel else []), e["name"])
        self.download_to(remote, "Descargas", "19 Descargar un archivo de BOSGAME")

    # ---- 20
    def _copy(self):
        e = self._sel()
        if not e or e["type"] != "Archivo":
            Msg.warn(self, "Seleccione un archivo para copiar.")
            return
        rel = (self.rel + "/" if self.rel else "") + e["name"]
        self.do(lambda l: l.copy_file(rel.replace("/", l.sep)),
                lambda r: (self.fstatus.setText(("✔ " if r.verified else "✖ ") + r.message), self.reload()), self.fstatus)

    # ---- 21-22
    def _backup(self):
        self.do(lambda l: l.create_backup(), lambda r: (self.mstatus.setText(("✔ " if r.verified else "✖ ") + r.message),
                                                        self._load_backups(), self.reload()), self.mstatus, "Creando respaldo…")

    def _load_backups(self):
        lab = self.state.lab
        if lab:
            run_async(lab.list_backups, lambda names: (self.rs_cb.clear(), self.rs_cb.addItems(names)), lambda m: None)

    def _restore(self):
        n = self.rs_cb.currentText()
        if not n:
            Msg.warn(self, "No hay respaldos disponibles.")
            return
        self.do(lambda l: l.restore_backup(n), lambda r: (self.mstatus.setText(("✔ " if r.verified else "✖ ") + r.message), self.reload()),
                self.mstatus, "Restaurando y comparando sumas…")
