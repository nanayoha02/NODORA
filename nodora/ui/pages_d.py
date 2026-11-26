"""Página: Tráfico de red (acción 26 en vivo y acción 27 captura de paquetes)."""
from __future__ import annotations

import os
import threading
import time

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QSpinBox)

from ..core.validators import ValidationError
from ..ops import traffic
from .pages_a import Page
from .orb import NetworkOrb
from .widgets import Card, Msg, RateChart, eyebrow, fill_table, fmt_bytes, fmt_rate, make_table, muted, run_async

MAX_ROWS = 1000


class TrafficPage(Page):
    title, subtitle = "Tráfico de red", "Lo que entra y sale de tu equipo, a la vista."

    def __init__(self, state, nav=None):
        super().__init__(state, nav)
        self.hero("Cada paquete cuenta.", "Mide el tráfico de BOSGAME en vivo y captura paquetes para analizarlos en Wireshark.")
        self.mon = traffic.TrafficMonitor()
        self._busy = False
        self.packets: list = []
        self.last_local = ""

        # ---- red viva: animación alimentada con el tráfico y las conexiones reales
        vivo = Card("Red viva", "El anillo se acelera y se deforma con los bytes/s reales; los nodos son las conexiones TCP reales de BOSGAME", shadow=False)
        self.orb = NetworkOrb()
        vivo.add(self.orb)
        self.col.addWidget(vivo)
        self._ticks = 0

        # ---- en vivo (26)
        live = Card("Tráfico en vivo", "Acción 26 · bytes por segundo calculados con el tiempo real entre lecturas")
        top = QHBoxLayout()
        self.iface = QComboBox()
        self.iface.addItem("Todas las interfaces", "")
        self.b_start = QPushButton("Iniciar")
        self.b_start.setObjectName("primary")
        self.b_log = QPushButton("Registrar medición (acción 26)")
        top.addWidget(QLabel("Interfaz:"))
        top.addWidget(self.iface, 1)
        top.addWidget(self.b_start)
        top.addWidget(self.b_log)
        live.addl(top)
        nums = QHBoxLayout()
        self.n_rx, self.n_tx = QLabel("↓ —"), QLabel("↑ —")
        for n in (self.n_rx, self.n_tx):
            n.setObjectName("hero")
            nums.addWidget(n)
        nums.addStretch()
        live.addl(nums)
        self.chart = RateChart()
        live.add(self.chart)
        self.lbl_leg = muted("Amarillo = recibido (↓) · verde = enviado (↑)")
        live.add(self.lbl_leg)
        self.lbl_tot = muted("")
        live.add(self.lbl_tot)
        self.col.addWidget(live)

        # ---- conexiones
        cc = Card("Conexiones TCP establecidas", "Quién está hablando con BOSGAME ahora mismo")
        self.conns = make_table(["Local", "Remoto", "PID", "Proceso"])
        self.conns.setMinimumHeight(170)
        self.b_conn = QPushButton("Actualizar conexiones")
        cc.add(self.conns)
        cc.add(self.b_conn)
        self.col.addWidget(cc)

        # ---- captura (27)
        cap = Card("Captura de paquetes", "Acción 27 · se captura en BOSGAME, se descarga con verificación SHA-256 y se analiza aquí")
        f = QHBoxLayout()
        self.proto = QComboBox()
        for lbl, v in (("Cualquiera", "any"), ("TCP", "tcp"), ("UDP", "udp"), ("ICMP", "icmp")):
            self.proto.addItem(lbl, v)
        self.port = QLineEdit()
        self.port.setPlaceholderText("Puerto (opcional)")
        self.host = QLineEdit()
        self.host.setPlaceholderText("IP (opcional)")
        self.secs = QSpinBox()
        self.secs.setRange(5, 60)
        self.secs.setValue(15)
        self.secs.setSuffix(" s")
        self.maxp = QSpinBox()
        self.maxp.setRange(100, 5000)
        self.maxp.setValue(2000)
        self.maxp.setSuffix(" paq.")
        for w in (self.proto, self.port, self.host, self.secs, self.maxp):
            f.addWidget(w)
        cap.addl(f)
        cap.add(muted("Requiere administrador/root en BOSGAME: pktmon en Windows 10/11 o tcpdump en Linux. "
                      "El máximo de paquetes solo aplica en Linux."))
        r = QHBoxLayout()
        self.b_cap = QPushButton("Capturar")
        self.b_cap.setObjectName("primary")
        self.b_folder = QPushButton("Abrir carpeta de capturas")
        self.b_wire = QPushButton("Abrir en Wireshark")
        self.b_folder.setEnabled(False)
        self.b_wire.setEnabled(False)
        r.addWidget(self.b_cap)
        r.addWidget(self.b_wire)
        r.addWidget(self.b_folder)
        r.addStretch()
        cap.addl(r)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.hide()
        cap.add(self.bar)
        self.cap_status = muted("")
        cap.add(self.cap_status)
        self.summary = muted("")
        cap.add(self.summary)
        self.flt = QLineEdit()
        self.flt.setPlaceholderText("Filtrar la lista (texto, IP, protocolo…)")
        cap.add(self.flt)
        self.tbl = make_table(["N.º", "Hora", "Origen", "Destino", "Protocolo", "Long.", "Información"])
        self.tbl.setMinimumHeight(320)
        cap.add(self.tbl)
        self.col.addWidget(cap)
        self.col.addStretch()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.b_start.clicked.connect(self._toggle)
        self.b_log.clicked.connect(self._log)
        self.iface.currentIndexChanged.connect(self._iface_changed)
        self.b_conn.clicked.connect(self._conns)
        self.b_cap.clicked.connect(self._capture)
        self.b_wire.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_local)))
        self.b_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(self.last_local))))
        self.flt.textChanged.connect(self._filter)

    # ---- en vivo
    def _toggle(self):
        if self.timer.isActive():
            self.timer.stop()
            self.b_start.setText("Iniciar")
            self.orb.set_idle()
            return
        if not self.lab():
            return
        self.mon.reset()
        self.chart.clear()
        self._ticks = 0
        self.timer.start(1000)
        self.b_start.setText("Detener")
        self._tick()

    def _iface_changed(self):
        self.mon.reset()
        self.chart.clear()

    def _tick(self):
        lab = self.state.lab
        if not lab or self._busy:
            return
        self._busy = True

        def job():
            c = traffic.read_counters(lab)
            return c, time.monotonic()

        def done(res):
            self._busy = False
            counters, t = res
            names = sorted(k for k in counters if not traffic.LOOPBACK.match(k))
            have = [self.iface.itemData(i) for i in range(1, self.iface.count())]
            if names != have:
                cur = self.iface.currentData()
                self.iface.blockSignals(True)
                self.iface.clear()
                self.iface.addItem("Todas las interfaces", "")
                for n in names:
                    self.iface.addItem(n, n)
                i = self.iface.findData(cur)
                self.iface.setCurrentIndex(max(i, 0))
                self.iface.blockSignals(False)
            r = self.mon.update(counters, t, self.iface.currentData() or "")
            if r:
                self.orb.set_rates(r.rx_bps, r.tx_bps)
                self.chart.push(r.rx_bps, r.tx_bps)
                self.n_rx.setText(f"↓ {fmt_rate(r.rx_bps)}")
                self.n_tx.setText(f"↑ {fmt_rate(r.tx_bps)}")
                self.lbl_tot.setText(f"Desde que inició: recibido {fmt_bytes(self.mon.total_rx)} · enviado {fmt_bytes(self.mon.total_tx)} · "
                                     f"pico ↓ {fmt_rate(self.mon.peak_rx)} ↑ {fmt_rate(self.mon.peak_tx)}")

        self._ticks += 1
        if self._ticks % 6 == 1:                 # cada ~6 s refresca los nodos (lectura silenciosa: no ensucia el historial)
            def cjob():
                with lab.quiet():
                    return traffic.connections(lab)
            run_async(cjob, lambda r: self.orb.set_connections(r.data) if r.ok else None, lambda m: None)

        def err(m):
            self._busy = False
            self.timer.stop()
            self.b_start.setText("Iniciar")
            self.lbl_tot.setText("✖ " + m)
        run_async(job, done, err)

    def _log(self):
        self.do(lambda l: traffic.log_traffic_sample(l, self.mon, self.iface.currentData() or ""),
                lambda r: self.lbl_tot.setText(("✔ " if r.ok else "✖ ") + r.message))

    def _conns(self):
        def done(r):
            if r.ok:
                self.orb.set_connections(r.data)
                fill_table(self.conns, [(c["local"], c["remote"], c["pid"] or "—", c["process"] or "—") for c in r.data])
            else:
                Msg.warn(self, r.message)
        self.do(lambda l: traffic.connections(l), done)

    # ---- captura
    def _capture(self):
        lab = self.lab()
        if not lab:
            return
        port = self.port.text().strip()
        params = traffic.CaptureParams(self.proto.currentData(), port or None, self.host.text().strip(),
                                       self.secs.value(), self.maxp.value())
        try:
            params.validate()
        except ValidationError as e:
            self.cap_status.setText("✖ " + str(e))
            return
        self.b_cap.setEnabled(False)
        self.bar.setRange(0, 0)
        self.bar.show()
        self.cap_status.setText(f"Capturando {params.seconds} s en BOSGAME… la ventana sigue operativa. Genere tráfico (por ejemplo, un ping).")

        def done(r):
            self.bar.hide()
            self.b_cap.setEnabled(True)
            if not r.ok:
                self.cap_status.setText("✖ " + r.message)
                return
            self.cap_status.setText("✔ " + r.message)
            self.packets = r.data["packets"]
            self.last_local = r.data["local"]
            sm = r.data["summary"]
            prot = " · ".join(f"{k} {v}" for k, v in sm.protocols.items()) or "—"
            tk = " | ".join(f"{a} ({n} paq., {fmt_bytes(b)})" for a, n, b in sm.talkers) or "—"
            self.summary.setText(f"Protocolos: {prot}\nMayores flujos: {tk}\nArchivo local: {self.last_local}\n"
                                 f"SHA-256: {r.data['sha256']}\nCopia en BOSGAME: {r.data['remote']}")
            self.b_wire.setEnabled(True)
            self.b_folder.setEnabled(True)
            self._fill()

        def err(m):
            self.bar.hide()
            self.b_cap.setEnabled(True)
            self.cap_status.setText("✖ " + m)
        run_async(lambda: traffic.capture(lab, params, cancel=threading.Event()), done, err)

    def _fill(self):
        rows = [(p.n, p.time_str, p.src + (f":{p.sport}" if p.sport else ""), p.dst + (f":{p.dport}" if p.dport else ""),
                 p.proto, p.wirelen, p.info) for p in self.packets[:MAX_ROWS]]
        fill_table(self.tbl, rows)
        if len(self.packets) > MAX_ROWS:
            self.summary.setText(self.summary.text() + f"\nSe muestran los primeros {MAX_ROWS} de {len(self.packets)} paquetes; "
                                 "abra el archivo en Wireshark para verlos todos.")
        self._filter()

    def _filter(self):
        q = self.flt.text().strip().lower()
        for i in range(self.tbl.rowCount()):
            hit = not q or any(q in (self.tbl.item(i, c).text().lower() if self.tbl.item(i, c) else "")
                               for c in range(self.tbl.columnCount()))
            self.tbl.setRowHidden(i, not hit)

    def on_connection(self, up):
        if not up:
            self.timer.stop()
            self.b_start.setText("Iniciar")
            self.maxp.setEnabled(True)
        elif self.state.session is not None:
            self.maxp.setEnabled(self.state.session.os_kind == "linux")
