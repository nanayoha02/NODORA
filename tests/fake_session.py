"""Sesión 'remota' que opera sobre el equipo local (Linux): ejecuta los comandos del perfil
Linux con sh y usa el sistema de archivos real como SFTP. Permite pruebas de integración."""
import os
import shutil
import subprocess
from pathlib import Path

from nodora.core.session import CmdResult, FileEntry, RemoteError


class LocalSession:
    os_kind = "linux"
    host = "127.0.0.1"

    def __init__(self, fail_write_paths=()):
        self.fail_write_paths = fail_write_paths
        self.commands = []

    def run(self, command, timeout=30):
        self.commands.append(command)
        p = subprocess.run(["sh", "-c", command], capture_output=True, text=True, timeout=timeout)
        return CmdResult(p.returncode, p.stdout, p.stderr)

    def listdir(self, path):
        try:
            return [FileEntry(e.name, e.is_dir(), e.stat().st_size, e.stat().st_mtime) for e in os.scandir(path)]
        except FileNotFoundError as e:
            raise RemoteError("La ruta no existe en el equipo remoto.") from e
        except PermissionError as e:
            raise RemoteError("Permiso insuficiente para leer esa ruta.") from e

    def exists(self, path):
        return os.path.exists(path)

    def mkdir(self, path):
        try:
            os.mkdir(path)
        except OSError as e:
            raise RemoteError(str(e)) from e

    def remove(self, path):
        try:
            os.remove(path)
        except OSError as e:
            raise RemoteError(str(e)) from e

    def rename(self, old, new):
        os.rename(old, new)

    def stat_size(self, path):
        return os.path.getsize(path)

    def read_text(self, path):
        return Path(path).read_bytes().decode("utf-8")

    def write_text(self, path, text, append=False):
        if any(path.startswith(p) for p in self.fail_write_paths):
            raise RemoteError("Escritura remota simulada fallida.")
        with open(path, "a" if append else "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def _copy(self, a, b, progress, cancel, interrupt_at=None):
        total, done = os.path.getsize(a), 0
        with open(a, "rb") as s, open(b, "wb") as d:
            while chunk := s.read(4096):
                if cancel.is_set():
                    raise RemoteError("Transferencia cancelada.")
                d.write(chunk)
                done += len(chunk)
                progress(done, total)
                if interrupt_at and done >= interrupt_at:
                    raise RemoteError("Transferencia interrumpida: conexión perdida")
        progress(total, total)

    interrupt_at = None

    def put(self, local, remote, progress, cancel):
        self._copy(local, remote, progress, cancel, self.interrupt_at)

    def get(self, remote, local, progress, cancel):
        self._copy(remote, local, progress, cancel, self.interrupt_at)

    def close(self):
        pass
