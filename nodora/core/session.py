"""Sesión remota. `RemoteSession` es la interfaz que usan las operaciones;
`SSHSession` la implementa con paramiko (SSH + SFTP). Las pruebas usan una sesión simulada."""
from __future__ import annotations

import base64
import os
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

from .config import app_dir


class RemoteError(Exception):
    """Fallo de conexión, autenticación o ejecución remota, con mensaje para el usuario."""


@dataclass
class CmdResult:
    rc: int
    out: str
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.rc == 0


@dataclass
class FileEntry:
    name: str
    is_dir: bool
    size: int
    mtime: float


class RemoteSession(Protocol):
    os_kind: str  # "windows" | "linux"
    host: str

    def run(self, command: str, timeout: float = 30) -> CmdResult: ...
    def listdir(self, path: str) -> list[FileEntry]: ...
    def exists(self, path: str) -> Optional[bool]: ...      # None = indeterminado
    def mkdir(self, path: str) -> None: ...
    def remove(self, path: str) -> None: ...
    def read_text(self, path: str) -> str: ...
    def write_text(self, path: str, text: str, append: bool = False) -> None: ...
    def put(self, local: str, remote: str, progress: Callable[[int, int], None],
            cancel: threading.Event) -> None: ...
    def get(self, remote: str, local: str, progress: Callable[[int, int], None],
            cancel: threading.Event) -> None: ...
    def rename(self, old: str, new: str) -> None: ...
    def stat_size(self, path: str) -> int: ...
    def close(self) -> None: ...


def ps_encode(script: str) -> str:
    """Comando PowerShell codificado (inmune a comillas de cmd/PowerShell/bash)."""
    b64 = base64.b64encode(script.encode("utf-16-le")).decode()
    return f"powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand {b64}"


class SSHSession:
    """Implementación real con paramiko."""

    def __init__(self, host: str, port: int, username: str, password: str | None = None,
                 key_path: str | None = None, timeout: int = 10,
                 confirm_host_key: Optional[Callable[[str, str, str], bool]] = None):
        try:
            import paramiko  # noqa: WPS433 (importación diferida)
        except ImportError as e:  # pragma: no cover
            raise RemoteError("Falta la biblioteca 'paramiko'. Ejecute: pip install -r requirements.txt") from e
        self._pm = paramiko
        self.host = host
        self.port = port
        self.username = username
        self.timeout = timeout
        self._lock = threading.RLock()
        self.client = paramiko.SSHClient()
        kh = app_dir() / "known_hosts"
        kh.touch(exist_ok=True)
        self.client.load_host_keys(str(kh))
        self.client.set_missing_host_key_policy(_TofuPolicy(kh, confirm_host_key))
        try:
            self.client.connect(
                host, port=port, username=username,
                password=password if not key_path else None,
                key_filename=key_path or None, passphrase=password if key_path and password else None,
                timeout=timeout, auth_timeout=timeout, banner_timeout=timeout,
                look_for_keys=False, allow_agent=False)
        except paramiko.AuthenticationException as e:
            raise RemoteError("Autenticación rechazada: revise usuario, contraseña o clave.") from e
        except paramiko.BadHostKeyException as e:
            raise RemoteError("La huella del equipo cambió: posible suplantación. Conexión cancelada.") from e
        except (socket.timeout, TimeoutError) as e:
            raise RemoteError(f"Sin respuesta de {host}:{port} (tiempo agotado).") from e
        except ConnectionRefusedError as e:
            raise RemoteError(f"{host}:{port} rechazó la conexión: ¿está activo el servidor SSH?") from e
        except (OSError, paramiko.SSHException) as e:
            raise RemoteError(f"No se pudo conectar: {e}") from e
        self.client.get_transport().set_keepalive(15)
        self._sftp = self.client.open_sftp()
        self.os_kind = self._detect_os()

    # ---- detección del sistema remoto
    def _detect_os(self) -> str:
        r = self._exec("uname -s", 10)
        if r.ok and r.out.strip().lower() in {"linux", "darwin"}:
            return "linux"
        return "windows"

    def _exec(self, command: str, timeout: float) -> CmdResult:
        with self._lock:
            try:
                _, so, se = self.client.exec_command(command, timeout=timeout)
                out = so.read().decode("utf-8", "replace")
                err = se.read().decode("utf-8", "replace")
                return CmdResult(so.channel.recv_exit_status(), out, err)
            except (socket.timeout, TimeoutError) as e:
                raise RemoteError("El comando remoto superó el tiempo de espera.") from e
            except (OSError, self._pm.SSHException) as e:
                raise RemoteError(f"Se perdió la sesión remota: {e}") from e

    def run(self, command: str, timeout: float = 30) -> CmdResult:
        return self._exec(command, timeout)

    # ---- SFTP
    def _p(self, path: str) -> str:
        from .validators import to_sftp_path
        return to_sftp_path(path) if self.os_kind == "windows" else path

    def listdir(self, path: str) -> list[FileEntry]:
        import stat as st
        try:
            return [FileEntry(a.filename, st.S_ISDIR(a.st_mode or 0), a.st_size or 0, a.st_mtime or 0)
                    for a in self._sftp.listdir_attr(self._p(path))]
        except PermissionError as e:
            raise RemoteError("Permiso insuficiente para leer esa ruta.") from e
        except FileNotFoundError as e:
            raise RemoteError("La ruta no existe en el equipo remoto.") from e
        except OSError as e:
            raise RemoteError(f"No se pudo listar la ruta: {e}") from e

    def exists(self, path: str) -> Optional[bool]:
        try:
            self._sftp.stat(self._p(path))
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return None

    def mkdir(self, path: str) -> None:
        try:
            self._sftp.mkdir(self._p(path))
        except PermissionError as e:
            raise RemoteError("Permiso insuficiente para crear la carpeta.") from e
        except OSError as e:
            raise RemoteError(f"No se pudo crear la carpeta: {e}") from e

    def remove(self, path: str) -> None:
        try:
            self._sftp.remove(self._p(path))
        except OSError as e:
            raise RemoteError(f"No se pudo eliminar: {e}") from e

    def rename(self, old: str, new: str) -> None:
        try:
            try:
                self._sftp.posix_rename(self._p(old), self._p(new))
            except (IOError, AttributeError):
                self._sftp.rename(self._p(old), self._p(new))
        except OSError as e:
            raise RemoteError(f"No se pudo renombrar: {e}") from e

    def stat_size(self, path: str) -> int:
        return int(self._sftp.stat(self._p(path)).st_size or 0)

    def read_text(self, path: str) -> str:
        with self._sftp.open(self._p(path), "rb") as f:
            return f.read().decode("utf-8", "replace")

    def write_text(self, path: str, text: str, append: bool = False) -> None:
        try:
            with self._sftp.open(self._p(path), "ab" if append else "wb") as f:
                f.write(text.encode("utf-8"))
        except OSError as e:
            raise RemoteError(f"No se pudo escribir en el equipo remoto: {e}") from e

    def put(self, local, remote, progress, cancel):
        total = os.path.getsize(local)
        done = 0
        try:
            with open(local, "rb") as src, self._sftp.open(self._p(remote), "wb") as dst:
                dst.set_pipelined(True)
                while True:
                    if cancel.is_set():
                        raise RemoteError("Transferencia cancelada.")
                    chunk = src.read(256 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
                    done += len(chunk)
                    progress(done, total)
            progress(total, total)
        except OSError as e:
            raise RemoteError(f"Transferencia interrumpida: {e}") from e

    def get(self, remote, local, progress, cancel):
        try:
            total = int(self._sftp.stat(self._p(remote)).st_size or 0)
            done = 0
            with self._sftp.open(self._p(remote), "rb") as src, open(local, "wb") as dst:
                src.prefetch()
                while True:
                    if cancel.is_set():
                        raise RemoteError("Transferencia cancelada.")
                    chunk = src.read(256 * 1024)
                    if not chunk:
                        break
                    dst.write(chunk)
                    done += len(chunk)
                    progress(done, total)
            progress(total, total)
        except PermissionError as e:
            raise RemoteError("Permiso insuficiente para leer el archivo remoto.") from e
        except FileNotFoundError as e:
            raise RemoteError("El archivo remoto no existe.") from e
        except OSError as e:
            raise RemoteError(f"Transferencia interrumpida: {e}") from e

    def close(self) -> None:
        for obj in (getattr(self, "_sftp", None), self.client):
            try:
                if obj:
                    obj.close()
            except Exception:  # noqa: BLE001 — cierre best-effort
                pass


class _TofuPolicy:
    """Confía en la primera huella solo si el usuario la confirma; luego la fija."""

    def __init__(self, path: Path, confirm):
        self.path, self.confirm = path, confirm

    def missing_host_key(self, client, hostname, key):
        import paramiko
        fp = ":".join(f"{b:02x}" for b in key.get_fingerprint())
        if self.confirm is None or not self.confirm(hostname, key.get_name(), fp):
            raise paramiko.SSHException(f"Huella de {hostname} no confirmada ({fp}).")
        client.get_host_keys().add(hostname, key.get_name(), key)
        client.save_host_keys(str(self.path))


def tcp_probe(host: str, port: int, timeout: float = 1.0) -> str:
    """'abierto' | 'rechazado' | 'sin respuesta'. Un timeout NO prueba que esté cerrado."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    t0 = time.perf_counter()
    try:
        s.connect((host, port))
        return "abierto"
    except ConnectionRefusedError:
        return "rechazado"
    except (socket.timeout, TimeoutError):
        return "sin respuesta"
    except OSError:
        return "sin respuesta"
    finally:
        s.close()
        _ = time.perf_counter() - t0
