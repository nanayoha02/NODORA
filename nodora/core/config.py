"""Configuración persistente. NUNCA guarda contraseñas ni frases de clave."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "NODORA"
APP_VERSION = "1.0.0"


def app_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    p = Path(base) / "NODORA"
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Settings:
    # Conexión (acción 1)
    host: str = "192.168.1.120"
    port: int = 22
    username: str = "admin"
    auth_method: str = "password"          # password | key
    key_path: str = ""
    connect_timeout: int = 10
    refresh_seconds: int = 5
    # Identidad (acción 2)
    student_name: str = ""
    student_group: str = ""
    student_id: str = ""
    # Rutas
    remote_base: str = r"C:\Laboratorio"   # el identificador se añade debajo
    local_dir: str = str(Path.home() / "NODORA")
    # Parámetros que fija el docente (sin tocar el código)
    lab_port_range: str = "8000-8010"
    lab_services: str = "sshd,Spooler,W32Time"          # servicios a consultar (acción 13)
    practice_service: str = "NodoraLab"                 # servicio de práctica (14 y 15)
    practice_process: str = ""                          # nombre de proceso de práctica (opcional)
    revealed_path: str = ""                             # acción 25 (puede quedar vacío)
    # Preferencias de interfaz
    theme: str = "light"                   # light | dark | system
    start_with_windows: bool = False
    minimize_to_tray: bool = True
    notify_alerts: bool = True
    notify_transfers: bool = True
    transfer_unit: str = "MiB/s"           # MiB/s | MB/s
    history_days: int = 90

    def save(self) -> None:
        data = asdict(self)
        for k in ("password", "passphrase"):
            data.pop(k, None)
        (app_dir() / "settings.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")

    @classmethod
    def load(cls) -> "Settings":
        f = app_dir() / "settings.json"
        s = cls()
        if f.exists():
            try:
                raw = json.loads(f.read_text("utf-8"))
                for k, v in raw.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
            except (OSError, ValueError):
                pass
        return s

    # utilidades
    def split_list(self, text: str) -> list[str]:
        return [x.strip() for x in text.replace(";", ",").split(",") if x.strip()]
