"""Estado compartido de la aplicación: configuración, sesión remota, laboratorio y registro."""
from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, Signal

from ..core.activity import ActivityLog, Record
from ..core.config import Settings
from ..core.session import RemoteError, SSHSession
from ..core.validators import ValidationError, validate_host, validate_port
from ..ops.lab import Lab


class AppState(QObject):
    connection_changed = Signal(bool)
    identity_changed = Signal()
    hostkey_request = Signal(str, str, str, object)   # host, tipo, huella, caja de respuesta
    activity = Signal()
    sample = Signal(dict)

    def __init__(self):
        super().__init__()
        self.cfg = Settings.load()
        self.log = ActivityLog(self.cfg.local_dir)
        self.session: SSHSession | None = None
        self.lab: Lab | None = None
        self.connected_at: float | None = None
        self.latency_ms: float | None = None
        self.sysinfo: dict = {}
        self._busy = threading.Lock()

    # ---- identidad mostrada en la barra superior
    @property
    def who(self) -> str:
        return f"{self.cfg.student_name} ({self.cfg.student_id})" if self.cfg.student_id else "Sin identificar"

    @property
    def is_connected(self) -> bool:
        return self.session is not None

    def log_reload(self) -> None:
        """Recrea el registro (p. ej. si cambió la carpeta local) conservando sesión y equipo."""
        old = self.log
        self.log = ActivityLog(self.cfg.local_dir)
        self.log.session_id, self.log.host = old.session_id, old.host
        if self.cfg.student_id:
            self.log.student = self.who
        if self.lab:
            self.lab.log = self.log

    # ---- acción 3: conectar / desconectar (se ejecuta en un hilo)
    def _confirm_hostkey(self, host: str, ktype: str, fp: str) -> bool:
        box = {"ev": threading.Event(), "ok": False}
        self.hostkey_request.emit(host, ktype, fp, box)
        box["ev"].wait(120)
        return box["ok"]

    def connect_remote(self, password: str) -> Lab:
        cfg = self.cfg
        host, port = validate_host(cfg.host), validate_port(cfg.port)
        if not cfg.username.strip():
            raise ValidationError("Indique el usuario.")
        if cfg.auth_method == "key" and not cfg.key_path:
            raise ValidationError("Seleccione el archivo de clave privada.")
        if cfg.auth_method == "password" and not password:
            raise ValidationError("Escriba la contraseña (no se guarda en disco).")
        self.disconnect_remote(quiet=True)
        self.log.host = host
        t0 = time.perf_counter()
        try:
            s = SSHSession(host, port, cfg.username.strip(), password or None,
                           cfg.key_path if cfg.auth_method == "key" else None,
                           cfg.connect_timeout, self._confirm_hostkey)
        except RemoteError as e:
            self.log.add(Record(action="3 Conectar la sesión remota", result="error", error=str(e),
                                params={"host": host, "puerto": port, "usuario": cfg.username}))
            raise
        self.latency_ms = round((time.perf_counter() - t0) * 1000, 0)
        self.session, self.connected_at = s, time.time()
        self.lab = Lab(s, cfg, self.log)
        if cfg.student_id:
            self.log.student = self.who
        self.log.add(Record(action="3 Conectar la sesión remota", result="verificada",
                            params={"host": host, "puerto": port, "usuario": cfg.username, "so_remoto": s.os_kind}))
        return self.lab

    def disconnect_remote(self, quiet: bool = False) -> None:
        if self.session:
            try:
                if self.lab and not quiet:
                    self.lab._try_sync()
                self.session.close()
            finally:
                if not quiet:
                    self.log.add(Record(action="3 Desconectar la sesión remota", result="verificada",
                                        params={"recursos_liberados": True}))
                self.session = self.lab = self.connected_at = None
