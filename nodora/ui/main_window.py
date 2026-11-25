"""Ventana principal: barra lateral, barra de contexto, páginas y muestreo periódico."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QGuiApplication
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)

from ..core.config import APP_NAME
from . import theme
from .pages_a import ConnectionPage, DashboardPage, MonitorPage
from .pages_b import FilesPage, NetworkPage
from .pages_c import HistoryPage, SettingsPage
from .pages_d import TrafficPage
from .state import AppState
from .widgets import Pill, muted, run_async

NAV = [("Panel principal", "▦"), ("Conexión SSH", "›_"), ("Monitoreo", "∿"), ("Red y servicios", "⌗"),
       ("Tráfico de red", "≈"), ("Archivos y mantenimiento", "▭"), ("Historial e informes", "↺"), ("Configuración", "⚙")]


class MainWindow(QMainWindow):
    def __init__(self, state: AppState, icon: QIcon | None = None, start_minimized: bool = False):
        super().__init__()
        self.state = state
        self.setWindowTitle(f"{APP_NAME} · Remote System Management")
        self.resize(1280, 820)
        if icon:
            self.setWindowIcon(icon)
        pal = theme.palette()
        self.rail = bool(pal.get("rail"))
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        m = pal["shell_margin"]
        outer.setContentsMargins(m, m, m, m)
        shell = QFrame()                       # panel ciruela con esquinas muy redondeadas sobre fondo lavanda
        shell.setObjectName("shell")
        outer.addWidget(shell)
        h = QHBoxLayout(shell)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # ---- barra lateral (riel de iconos en Ciruela; con etiquetas en los demás temas)
        sb = QWidget()
        sb.setObjectName("sidebar")
        sb.setFixedWidth(92 if self.rail else 250)
        sv = QVBoxLayout(sb)
        sv.setContentsMargins((20, 26, 20, 20) if self.rail else (18, 24, 18, 18))
        sv.setSpacing(10 if self.rail else 4)
        if self.rail:
            brand = QLabel(f'N<span style="color:{pal["accent"]};">●</span>')
        else:
            brand = QLabel(f'{APP_NAME} <span style="color:{pal["accent"]};">●</span>')
        brand.setObjectName("brand")
        brand.setTextFormat(Qt.RichText)
        brand.setToolTip(f"{APP_NAME} · Remote System Management")
        sv.addWidget(brand, alignment=Qt.AlignHCenter if self.rail else Qt.AlignLeft)
        if not self.rail:
            sub = QLabel("REMOTE SYSTEM MANAGEMENT")
            sub.setObjectName("eyebrow")
            sv.addWidget(sub)
            sv.addSpacing(22)
            ws = QLabel("ESPACIO DE TRABAJO")
            ws.setObjectName("eyebrow")
            sv.addWidget(ws)
        else:
            sv.addSpacing(14)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = []
        for i, (name, ico) in enumerate(NAV):
            b = QPushButton(ico if self.rail else f"{ico}   {name}")
            b.setObjectName("rail" if self.rail else "nav")
            b.setToolTip(name)
            b.setAccessibleName(name)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.group.addButton(b, i)
            self.buttons.append(b)
            sv.addWidget(b, alignment=Qt.AlignHCenter if self.rail else Qt.AlignLeft)
        sv.addStretch()
        if not self.rail:
            tg = QLabel("Your System.\nOur Control.")
            tg.setObjectName("tagline")
            sv.addWidget(tg)
            sv.addSpacing(10)
        self.side_status = Pill("" if self.rail else "Sin conectar", "err")
        self.side_status.setToolTip("Estado de la conexión")
        sv.addWidget(self.side_status, alignment=Qt.AlignHCenter if self.rail else Qt.AlignLeft)
        h.addWidget(sb)

        # ---- contenido
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        # barra de contexto: estudiante, equipo, IP y conexión SIEMPRE visibles antes de operar
        self.top = QFrame()
        self.top.setObjectName("topbar")
        tl = QHBoxLayout(self.top)
        tl.setContentsMargins(16, 8, 16, 8)
        self.lbl_student = QLabel()
        self.lbl_host = QLabel()
        self.lbl_state = Pill("Desconectado", "err")
        for w in (self.lbl_student, self.lbl_host):
            tl.addWidget(w)
            tl.addSpacing(18)
        tl.addStretch()
        tl.addWidget(self.lbl_state)
        wrap = QVBoxLayout()
        wrap.setContentsMargins(26, 14, 26, 0)
        wrap.addWidget(self.top)
        right.addLayout(wrap)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        h.addLayout(right, 1)

        s = state
        self.pages = [DashboardPage(s), ConnectionPage(s), MonitorPage(s), NetworkPage(s), TrafficPage(s), FilesPage(s),
                      HistoryPage(s), SettingsPage(s)]
        for p in self.pages:
            self.stack.addWidget(p)
        self.group.idClicked.connect(self.stack.setCurrentIndex)
        self.stack.currentChanged.connect(self._page_changed)
        self.buttons[0].setChecked(True)
        self.pages[0].goto_history.connect(lambda: self.go(6))
        self.pages[1].connection_changed.connect(self._connection)
        self.pages[7].theme_changed.connect(self.apply_theme)
        s.identity_changed.connect(self._refresh_top)
        s.hostkey_request.connect(self._hostkey)
        s.sample.connect(lambda d: [p.on_sample(d) for p in self.pages])

        # ---- muestreo periódico (lecturas silenciosas; no se registran como operaciones)
        self._sampling = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._sample)
        self.timer.start(max(2, s.cfg.refresh_seconds) * 1000)
        self._hi_cpu = 0

        # ---- bandeja del sistema
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon or QIcon(), self)
            m = QMenu()
            a1, a2 = QAction("Mostrar NODORA", self), QAction("Salir", self)
            a1.triggered.connect(self._show_from_tray)
            a2.triggered.connect(self._quit)
            m.addAction(a1)
            m.addAction(a2)
            self.tray.setContextMenu(m)
            self.tray.activated.connect(lambda r: self._show_from_tray() if r == QSystemTrayIcon.Trigger else None)
            self.tray.show()
        self._quitting = False
        self._refresh_top()

    # ---- navegación
    def go(self, i: int):
        self.buttons[i].setChecked(True)
        self.stack.setCurrentIndex(i)

    def _page_changed(self, i: int):
        pg = self.pages[i]
        if hasattr(pg, "refresh_activity"):
            pg.refresh_activity()
        if hasattr(pg, "reload") and i == 5:
            pg.reload()
        if hasattr(pg, "refresh_labels"):
            pg.refresh_labels()

    # ---- barra de contexto
    def _refresh_top(self):
        s = self.state
        self.lbl_student.setText(f"👤  <b>{s.who}</b>")
        self.lbl_host.setText(f"🖥  <b>BOSGAME</b> · {s.cfg.host}:{s.cfg.port}"
                              + (f" · {s.session.os_kind.capitalize()}" if s.session else ""))
        if s.is_connected:
            self.lbl_state.set("Conectado por SSH", "ok")
            self.side_status.set("" if self.rail else f"{s.cfg.host}", "ok")
        else:
            self.lbl_state.set("Desconectado", "err")
            self.side_status.set("" if self.rail else "Sin conectar", "err")

    def _connection(self, up: bool):
        self._refresh_top()
        s = self.state
        if up:
            s.sysinfo = {}
            self._hi_cpu = 0
            self._sample(first=True)
        for p in self.pages:
            p.on_connection(up)

    # ---- muestreo
    def _sample(self, first: bool = False):
        s = self.state
        lab = s.lab
        if not lab or self._sampling:
            return
        self._sampling = True

        def job():
            out = {}
            with lab.quiet():
                if not s.sysinfo:
                    r = lab.system_info()
                    if r.ok:
                        out["sysinfo"] = r.data
                r = lab.cpu()
                if r.ok:
                    out["cpu"] = r.data["percent"]
                r = lab.ram()
                if r.ok:
                    out["ram"] = r.data
                r = lab.storage()
                if r.ok:
                    out["disks"] = r.data
            return out

        def done(d):
            self._sampling = False
            if "sysinfo" in d:
                s.sysinfo = d["sysinfo"]
                self.pages[0].on_connection(True)
            s.sample.emit(d)
            self._alerts(d)

        def err(m):
            self._sampling = False
            if s.session and not s.session.client.get_transport().is_active():
                s.disconnect_remote(quiet=True)
                self._connection(False)
                self.pages[1].status.setText("✖ Se perdió la sesión remota: " + m)

        run_async(job, done, err)

    def _alerts(self, d):
        if not self.state.cfg.notify_alerts or "cpu" not in d:
            return
        self._hi_cpu = self._hi_cpu + 1 if d["cpu"] >= 90 else 0
        if self._hi_cpu == 3 and self.tray:
            self.tray.showMessage(APP_NAME, "CPU de BOSGAME por encima del 90 % durante varias lecturas.",
                                  QSystemTrayIcon.Warning, 6000)

    # ---- huella de host (primera conexión)
    def _hostkey(self, host, ktype, fp, box):
        box["ok"] = QMessageBox.question(
            self, "Confirmar equipo", f"Primera conexión con {host}.\n\nTipo de clave: {ktype}\nHuella: {fp}\n\n"
            "Compare la huella con la del equipo BOSGAME. ¿Confía en este equipo?") == QMessageBox.Yes
        box["ev"].set()

    # ---- tema
    def apply_theme(self):
        dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark \
            if hasattr(QGuiApplication.styleHints(), "colorScheme") else False
        theme.set_theme(self.state.cfg.theme, dark)
        QApplication.instance().setStyleSheet(theme.stylesheet())
        for p in self.pages:
            p.update()

    # ---- cierre / bandeja
    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()

    def _quit(self):
        self._quitting = True
        self.close()

    def closeEvent(self, e):
        if self.state.cfg.minimize_to_tray and self.tray and not self._quitting:
            e.ignore()
            self.hide()
            self.tray.showMessage(APP_NAME, "NODORA sigue activo en el área de notificación.", QSystemTrayIcon.Information, 3000)
            return
        try:
            self.state.disconnect_remote()
        finally:
            if self.tray:
                self.tray.hide()
            e.accept()
            QApplication.quit()
