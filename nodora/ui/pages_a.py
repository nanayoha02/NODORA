"""Páginas: Panel principal, Conexión SSH y Monitoreo (acciones 1-9)."""
from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSpinBox,
                               QVBoxLayout, QWidget)

from ..core.config import Settings
from ..core.session import tcp_probe
from ..core.validators import ValidationError, validate_host, validate_port, validate_student_id
from . import theme
from .widgets import (Card, Msg, DonutGauge, PastelTile, Pill, Sparkline, eyebrow, fill_table, fmt_bytes, fmt_uptime, make_table, muted,
                      run_async)


class Page(QScrollArea):
    """Base: título, subtítulo y columna de contenido con desplazamiento."""
    title, subtitle = "", ""

    def __init__(self, state, nav=None):
        super().__init__()
        self.state, self.nav = state, nav
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        self.setWidget(body)
        self.col = QVBoxLayout(body)
        self.col.setContentsMargins(26, 18, 26, 26)
        self.col.setSpacing(16)
        t = QLabel(self.title)
        t.setObjectName("pageTitle")
        s = QLabel(self.subtitle)
        s.setObjectName("pageSub")
        self.col.addWidget(t)
        self.col.addWidget(s)

    def hero(self, title: str, sub: str) -> None:
        h = QLabel(title)
        h.setObjectName("hero")
        self.col.addSpacing(8)
        self.col.addWidget(h)
        self.col.addWidget(muted(sub))

    def lab(self):
        if not self.state.lab:
            Msg.warn(self, "Primero conecte con BOSGAME (sección Conexión SSH).")
            return None
        return self.state.lab

    def show_result(self, res, out=None) -> None:
        if out is not None:
            out.setPlainText(("✔ " if res.verified else ("• " if res.ok else "✖ ")) + res.message)

    def do(self, fn, ok, label: QLabel | None = None, busy: str = "Trabajando…"):
        """Ejecuta `fn` (operación del laboratorio) en segundo plano y llama `ok(resultado)`."""
        lab = self.lab()
        if not lab:
            return
        if label:
            label.setText(busy)
        run_async(lambda: fn(lab), ok, lambda m: (label.setText("✖ " + m) if label else Msg.warn(self, m)))

    def on_theme(self) -> None: ...
    def on_connection(self, up: bool) -> None: ...
    def on_sample(self, s: dict) -> None: ...


# ======================================================================== Panel principal
class DashboardPage(Page):
    title, subtitle = "Panel principal", "Una vista clara de todo tu sistema."
    goto_history = Signal()

    def __init__(self, state, nav=None):
        super().__init__(state, nav)
        self.hero("Bienvenido a NODORA", "Aquí tienes el estado de tu sistema.")
        dev = Card()
        row = QHBoxLayout()
        icon = QLabel("🖥")
        icon.setFixedSize(76, 76)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:34px; background:%s; border-radius:14px;" % theme.palette()["accent_soft"])
        self.icon = icon
        row.addWidget(icon)
        info = QVBoxLayout()
        info.addWidget(eyebrow("Tu dispositivo"))
        self.name = QLabel("BOSGAME")
        self.name.setObjectName("hero")
        self.sub = muted("Sin conexión")
        self.pill = Pill("Desconectado", "err")
        info.addWidget(self.name)
        info.addWidget(self.sub)
        info.addWidget(self.pill, alignment=Qt.AlignLeft)
        row.addLayout(info, 2)
        self.ip = self._kv("Dirección IP", "—", "")
        self.up = self._kv("Tiempo activo", "—", "")
        self.who = self._kv("Estudiante", "—", "")
        for w in (self.ip, self.up, self.who):
            row.addLayout(w[0], 1)
        dev.addl(row)
        self.col.addWidget(dev)

        tiles = QHBoxLayout()
        self.cpu_n, self.cpu_s, self.cpu_chart = self._tile("CPU", "—", "")
        self.ram_n, self.ram_s, self.ram_chart = self._tile("Memoria RAM", "—", "")
        self.dsk_n, self.dsk_s, self.dsk_bar = self._tile("Almacenamiento", "—", "", bar=True)
        for t in (self.cpu_chart[0], self.ram_chart[0], self.dsk_bar[0]):
            tiles.addWidget(t, 1)
        self.col.addLayout(tiles)

        act = Card("Actividad reciente", "Las últimas acciones registradas.")
        self.actlist = make_table(["Resultado", "Acción", "Hora"])
        self.actlist.setMinimumHeight(250)
        act.add(self.actlist)
        b = QPushButton("Ver historial")
        b.clicked.connect(self.goto_history.emit)
        act.add(b)
        self.col.addWidget(act)
        self.col.addStretch()
        self.refresh_activity()

    def _kv(self, k, v, s):
        lay = QVBoxLayout()
        lay.addWidget(eyebrow(k))
        val = QLabel(v)
        val.setStyleSheet("font-size:16px; font-weight:600;")
        sub = muted(s)
        lay.addWidget(val)
        lay.addWidget(sub)
        return lay, val, sub

    def _tile(self, title, val, sub, bar=False):
        idx = {"CPU": 0, "Memoria RAM": 1}.get(title, 2)
        c = PastelTile(idx)
        c.add(eyebrow(title))
        n = QLabel(val)
        n.setObjectName("bigNumber")
        s = muted(sub)
        c.add(n)
        c.add(s)
        if theme.palette().get("tabs"):
            g = DonutGauge()
            c.add(g)
            return n, s, (c, g)
        if bar:
            pb = QProgressBar()
            pb.setRange(0, 100)
            pb.setTextVisible(False)
            c.add(pb)
            return n, s, (c, pb)
        sp = Sparkline(c.ink, ink=c.ink)
        sp.setMinimumHeight(60)
        c.add(sp)
        return n, s, (c, sp)

    def on_connection(self, up):
        st = self.state
        if up:
            sysi = getattr(st, "sysinfo", {}) or {}
            self.name.setText(sysi.get("hostname") or "BOSGAME")
            self.sub.setText(f"{sysi.get('os') or st.session.os_kind.capitalize()} · {sysi.get('cpu') or ''}".strip(" ·"))
            self.pill.set(f"Conectado por SSH", "ok")
            self.ip[1].setText(st.cfg.host)
            self.ip[2].setText(f"Puerto {st.cfg.port} · {st.cfg.username}")
            self.who[1].setText(st.cfg.student_id or "—")
            self.who[2].setText(st.cfg.student_name or "Sin identificar")
        else:
            self.pill.set("Desconectado", "err")
            self.sub.setText("Sin conexión")
            for k in (self.ip, self.up, self.who):
                k[1].setText("—")
                k[2].setText("")
        self.refresh_activity()

    def on_sample(self, s):
        if "cpu" in s:
            self.cpu_n.setText(f"{s['cpu']:.0f}%")
            self.cpu_s.setText(f"{(getattr(self.state, 'sysinfo', {}) or {}).get('threads') or '?'} hilos lógicos")
            self.cpu_chart[1].push(s["cpu"])
        if "ram" in s:
            r = s["ram"]
            self.ram_n.setText(fmt_bytes(r["used"]))
            self.ram_s.setText(f"{fmt_bytes(r['free'])} disponibles de {fmt_bytes(r['total'])}")
            self.ram_chart[1].push(100 * r["used"] / r["total"] if r["total"] else 0)
        if s.get("disks"):
            d = s["disks"][0]
            self.dsk_n.setText(fmt_bytes(d["used"]))
            self.dsk_s.setText(f"{fmt_bytes(d['free'])} libres de {fmt_bytes(d['size'])} ({d['name']})")
            self.dsk_bar[1].setValue(int(100 * d["used"] / d["size"]) if d["size"] else 0)
        up = (getattr(self.state, "sysinfo", {}) or {}).get("uptime_s")
        self.up[1].setText(fmt_uptime(up))

    def refresh_activity(self):
        rows = self.state.log.all_rows()[-8:][::-1]
        fill_table(self.actlist, [(r["result"].capitalize(), r["action"], r["timestamp"][11:19]) for r in rows])


# ======================================================================== Conexión SSH
class ConnectionPage(Page):
    title, subtitle = "Conexión SSH", "Una conexión segura. Todo bajo control."
    connection_changed = Signal(bool)

    def __init__(self, state, nav=None):
        super().__init__(state, nav)
        self.hero("Acceso remoto, sin complicaciones.", "Administra tu conexión al BOSGAME de forma segura.")
        c = Card("Configuración de conexión", "Acción 1 · Los datos se guardan en tu equipo, nunca en el código.")
        f = QFormLayout()
        f.setLabelAlignment(Qt.AlignLeft)
        self.host, self.port, self.user = QLineEdit(), QSpinBox(), QLineEdit()
        self.port.setRange(1, 65535)
        self.method = QComboBox()
        self.method.addItems(["Contraseña", "Clave privada SSH"])
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("Solo se mantiene en memoria · nunca se guarda ni se registra")
        self.key = QLineEdit()
        self.key.setPlaceholderText("Ruta de la clave privada (.pem / id_ed25519)")
        kb = QPushButton("Examinar…")
        kb.clicked.connect(self._pick_key)
        keyrow = QHBoxLayout()
        keyrow.addWidget(self.key)
        keyrow.addWidget(kb)
        self.keyw = QWidget()
        self.keyw.setLayout(keyrow)
        keyrow.setContentsMargins(0, 0, 0, 0)
        f.addRow("Dirección IP o hostname", self.host)
        f.addRow("Puerto SSH", self.port)
        f.addRow("Nombre de usuario", self.user)
        f.addRow("Método de autenticación", self.method)
        f.addRow("Contraseña / frase de clave", self.pw)
        f.addRow("Clave privada", self.keyw)
        c.addl(f)
        btns = QHBoxLayout()
        self.b_connect = QPushButton("Conectar")
        self.b_connect.setObjectName("primary")
        self.b_disc = QPushButton("Desconectar")
        self.b_test = QPushButton("Probar conexión")
        self.b_save = QPushButton("Guardar configuración")
        for b in (self.b_connect, self.b_disc, self.b_test, self.b_save):
            btns.addWidget(b)
        btns.addStretch()
        c.addl(btns)
        self.status = QLabel("Sin conexión.")
        self.status.setWordWrap(True)
        c.add(self.status)
        self.col.addWidget(c)

        ident = Card("Identificación del estudiante", "Acción 2 · Cada operación queda asociada a esta identidad y sesión.")
        g = QFormLayout()
        self.name, self.group, self.sid = QLineEdit(), QLineEdit(), QLineEdit()
        self.sid.setPlaceholderText("Ej.: AMartinez (letras, números, - y _)")
        g.addRow("Nombre completo", self.name)
        g.addRow("Grupo", self.group)
        g.addRow("Identificador", self.sid)
        ident.addl(g)
        ib = QHBoxLayout()
        self.b_ident = QPushButton("Guardar identidad (identificacion.txt)")
        self.b_prep = QPushButton("Preparar carpeta personal")
        self.b_prep.setObjectName("primary")
        ib.addWidget(self.b_ident)
        ib.addWidget(self.b_prep)
        ib.addStretch()
        ident.addl(ib)
        self.ident_out = QPlainTextEdit()
        self.ident_out.setReadOnly(True)
        self.ident_out.setFixedHeight(90)
        ident.add(self.ident_out)
        self.col.addWidget(ident)
        self.col.addStretch()

        self.method.currentIndexChanged.connect(self._method_changed)
        self.b_connect.clicked.connect(self.connect_)
        self.b_disc.clicked.connect(self.disconnect_)
        self.b_test.clicked.connect(self.test_)
        self.b_save.clicked.connect(self.save_)
        self.b_ident.clicked.connect(self.identify_)
        self.b_prep.clicked.connect(self.prepare_)
        self.load()
        self.on_connection(False)

    def load(self):
        c = self.state.cfg
        self.host.setText(c.host)
        self.port.setValue(c.port)
        self.user.setText(c.username)
        self.method.setCurrentIndex(1 if c.auth_method == "key" else 0)
        self.key.setText(c.key_path)
        self.name.setText(c.student_name)
        self.group.setText(c.student_group)
        self.sid.setText(c.student_id)
        self._method_changed()

    def _method_changed(self):
        self.keyw.setVisible(self.method.currentIndex() == 1)

    def _pick_key(self):
        p, _ = QFileDialog.getOpenFileName(self, "Clave privada SSH")
        if p:
            self.key.setText(p)

    def _read_form(self) -> bool:
        try:
            c = self.state.cfg
            c.host = validate_host(self.host.text())
            c.port = validate_port(self.port.value())
            c.username = self.user.text().strip()
            c.auth_method = "key" if self.method.currentIndex() == 1 else "password"
            c.key_path = self.key.text().strip()
            return True
        except ValidationError as e:
            self.status.setText("✖ " + str(e))
            return False

    def save_(self):
        if self._read_form():
            self.state.cfg.save()
            self.status.setText("✔ Configuración guardada (sin contraseñas).")

    def test_(self):
        if not self._read_form():
            return
        self.status.setText("Probando…")
        host, port = self.state.cfg.host, self.state.cfg.port

        def job():
            t0 = time.perf_counter()
            r = tcp_probe(host, port, 3.0)
            return r, round((time.perf_counter() - t0) * 1000)

        def done(res):
            st, ms = res
            self.status.setText({"abierto": f"✔ {host}:{port} acepta conexiones ({ms} ms). Falta autenticar.",
                                 "rechazado": f"✖ {host}:{port} rechazó la conexión: el servidor SSH no está activo en ese puerto.",
                                 "sin respuesta": f"✖ Sin respuesta de {host}:{port}. Un firewall o un equipo apagado dan este resultado; no es concluyente."}[st])
        run_async(job, done)

    def connect_(self):
        if not self._read_form():
            return
        self.state.cfg.save()
        pw = self.pw.text()
        self.status.setText("Conectando…")
        self.b_connect.setEnabled(False)

        def done(lab):
            self.pw.clear()
            self.b_connect.setEnabled(True)
            self.status.setText(f"✔ Conectado a {self.state.cfg.host} ({lab.s.os_kind}) en {self.state.latency_ms:.0f} ms.")
            self.connection_changed.emit(True)

        def err(m):
            self.b_connect.setEnabled(True)
            self.status.setText("✖ " + m)

        run_async(lambda: self.state.connect_remote(pw), done, err)

    def disconnect_(self):
        def done(_):
            self.status.setText("✔ Sesión cerrada y recursos liberados.")
            self.connection_changed.emit(False)
        run_async(lambda: self.state.disconnect_remote(), done)

    def identify_(self):
        c = self.state.cfg
        try:
            sid = validate_student_id(self.sid.text())
        except ValidationError as e:
            self.ident_out.setPlainText("✖ " + str(e))
            return
        c.student_name, c.student_group, c.student_id = self.name.text().strip(), self.group.text().strip(), sid
        c.save()
        self.state.log_reload()
        if not self.state.lab:
            self.ident_out.setPlainText("• Identidad guardada localmente. Conecte con BOSGAME para crear identificacion.txt remoto.")
            self.state.identity_changed.emit()
            return
        self.state.lab.log = self.state.log
        self.do(lambda lab: lab.identify(self.name.text(), self.group.text(), sid),
                lambda r: (self.show_result(r, self.ident_out), self.state.identity_changed.emit()), None)

    def prepare_(self):
        if not self.state.cfg.student_id:
            self.ident_out.setPlainText("✖ Guarde primero la identidad del estudiante.")
            return
        self.do(lambda lab: lab.prepare_folder(), lambda r: self.show_result(r, self.ident_out), None)

    def on_connection(self, up):
        for b in (self.b_disc,):
            b.setEnabled(up)
        self.b_connect.setEnabled(True)
        for b in (self.b_prep,):
            b.setEnabled(up)


# ======================================================================== Monitoreo
class MonitorPage(Page):
    title, subtitle = "Monitoreo", "El pulso de tu equipo, en tiempo real."

    def __init__(self, state, nav=None):
        super().__init__(state, nav)
        self.hero("Cada recurso, en tiempo real.", "BOSGAME · Vista de rendimiento")
        top = QHBoxLayout()
        cc = Card("Procesador")
        self.cpu_n = QLabel("—")
        self.cpu_n.setObjectName("bigNumber")
        self.cpu_info = muted("")
        self.cpu_ch = Sparkline(axes=True)
        self.b_cpu = QPushButton("Medir CPU y registrar (acción 6)")
        cc.add(self.cpu_n)
        cc.add(self.cpu_info)
        cc.add(self.cpu_ch)
        cc.add(self.b_cpu)
        rc = Card("Memoria RAM")
        self.ram_n = QLabel("—")
        self.ram_n.setObjectName("bigNumber")
        self.ram_info = muted("")
        self.ram_ch = Sparkline(theme.palette()["chart2"], axes=True)
        self.b_ram = QPushButton("Consultar RAM y registrar (acción 7)")
        rc.add(self.ram_n)
        rc.add(self.ram_info)
        rc.add(self.ram_ch)
        rc.add(self.b_ram)
        top.addWidget(cc, 1)
        top.addWidget(rc, 1)
        self.col.addLayout(top)

        row2 = QHBoxLayout()
        self.dcard = Card("Almacenamiento", "Acción 8 · capacidad, usado y libre por unidad")
        self.disks = make_table(["Unidad", "Capacidad", "Usado", "Libre", "Uso"])
        self.disks.setMinimumHeight(150)
        self.b_disk = QPushButton("Consultar y registrar (acción 8)")
        self.dcard.add(self.disks)
        self.dcard.add(self.b_disk)
        self.scard = Card("Sistema", "Acción 5 · los datos no disponibles se indican")
        self.sys = make_table(["Dato", "Valor"])
        self.sys.setMinimumHeight(220)
        self.b_sys = QPushButton("Consultar y registrar (acción 5)")
        self.scard.add(self.sys)
        self.scard.add(self.b_sys)
        row2.addWidget(self.dcard, 1)
        row2.addWidget(self.scard, 1)
        self.col.addLayout(row2)

        pc = Card("Procesos", "Acción 9 · nombre, PID y consumo disponibles. Busque un proceso de prueba.")
        sr = QHBoxLayout()
        self.pf = QLineEdit()
        self.pf.setPlaceholderText("Nombre del proceso de prueba (opcional)")
        self.b_proc = QPushButton("Listar procesos")
        self.b_proc.setObjectName("primary")
        sr.addWidget(self.pf, 1)
        sr.addWidget(self.b_proc)
        pc.addl(sr)
        self.proc_status = muted("")
        pc.add(self.proc_status)
        self.procs = make_table(["PID", "Nombre", "Memoria", "CPU"])
        self.procs.setMinimumHeight(300)
        pc.add(self.procs)
        self.col.addWidget(pc)
        self.col.addStretch()

        self.b_cpu.clicked.connect(lambda: self.do(lambda l: l.cpu(), self._cpu_done, self.cpu_info, "Midiendo 1 s…"))
        self.b_ram.clicked.connect(lambda: self.do(lambda l: l.ram(), self._ram_done, self.ram_info))
        self.b_disk.clicked.connect(lambda: self.do(lambda l: l.storage(), lambda r: self._disks(r.data)))
        self.b_sys.clicked.connect(lambda: self.do(lambda l: l.system_info(), self._sys_done))
        self.b_proc.clicked.connect(self._procs)

    def _cpu_done(self, r):
        if r.ok:
            d = r.data
            self.cpu_n.setText(f"{d['percent']:.0f}%")
            self.cpu_info.setText(f"Consulta a las {d['at']} · intervalo de medición {d['interval_s']} s")
            self.cpu_ch.push(d["percent"])
        else:
            self.cpu_info.setText("✖ " + r.message)

    def _ram_done(self, r):
        if r.ok:
            d = r.data
            self.ram_info.setText(f"Total {fmt_bytes(d['total'])} · usada {fmt_bytes(d['used'])} · disponible {fmt_bytes(d['free'])} · fuente: {d['source']}")
        else:
            self.ram_info.setText("✖ " + r.message)

    def _disks(self, data):
        if not data:
            return
        fill_table(self.disks, [(d["name"], fmt_bytes(d["size"]), fmt_bytes(d["used"]), fmt_bytes(d["free"]),
                                 f"{100 * d['used'] / d['size']:.0f}%" if d["size"] else "—") for d in data])

    def _sys_done(self, r):
        if not r.ok:
            Msg.warn(self, r.message)
            return
        d = r.data
        nd = "No disponible"
        rows = [("Nombre del equipo", d.get("hostname") or nd), ("Sistema operativo", d.get("os") or nd),
                ("Versión", d.get("version") or nd), ("Arquitectura", d.get("arch") or nd),
                ("Procesador", d.get("cpu") or nd), ("Núcleos / hilos", f"{d.get('cores') or nd} / {d.get('threads') or nd}"),
                ("Memoria instalada", fmt_bytes(d["ram_total"]) if d.get("ram_total") else nd),
                ("Tiempo activo", fmt_uptime(d.get("uptime_s")))]
        fill_table(self.sys, rows)

    def _procs(self):
        name = self.pf.text().strip()
        self.do(lambda l: l.processes(name), self._procs_done, self.proc_status)

    def _procs_done(self, r):
        self.proc_status.setText(("✔ " if r.verified else "") + r.message if r.ok else "✖ " + r.message)
        if r.ok:
            rows = [(p["pid"], p["name"], fmt_bytes(p["mem"]),
                     "—" if p["cpu"] is None else (f"{p['cpu']:.1f} %" if p["cpu_unit"] == "%" else f"{p['cpu']:.0f} s CPU"))
                    for p in r.data["processes"]]
            fill_table(self.procs, rows)
            found = {p["pid"] for p in r.data["found"]}
            for i in range(self.procs.rowCount()):
                if int(self.procs.item(i, 0).text()) in found:
                    for j in range(4):
                        self.procs.item(i, j).setBackground(self.palette().highlight().color().lighter(180))

    def on_sample(self, s):
        if "cpu" in s:
            self.cpu_n.setText(f"{s['cpu']:.0f}%")
            self.cpu_ch.push(s["cpu"])
        if "ram" in s:
            r = s["ram"]
            self.ram_n.setText(fmt_bytes(r["used"]))
            self.ram_ch.push(100 * r["used"] / r["total"] if r["total"] else 0)
            self.ram_info.setText(f"{fmt_bytes(r['free'])} disponibles de {fmt_bytes(r['total'])}")
        if s.get("disks"):
            self._disks(s["disks"])
        si = getattr(self.state, "sysinfo", None)
        if si and self.sys.rowCount() == 0:
            self.cpu_info.setText(f"{si.get('cpu') or ''}")
