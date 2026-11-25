"""Transferencias (acciones 18, 19 y 25) con medición real, cancelación e integridad SHA-256."""
from __future__ import annotations

import hashlib
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..core.profiles import profile_for
from ..core.session import RemoteError
from ..core.validators import safe_join  # noqa: F401  (re-export para pruebas)

STATES = ("Conectando", "Transfiriendo", "Verificando", "Completado y verificado",
          "Cancelado", "Incompleto", "Error")


def fmt_speed(bps: float, unit: str = "MiB/s") -> str:
    div = 1_048_576 if unit == "MiB/s" else 1_000_000
    return f"{bps / div:.2f} {unit}"


def fmt_size(n: float, unit: str = "MiB/s") -> str:
    div, u = (1_048_576, "MiB") if unit == "MiB/s" else (1_000_000, "MB")
    return f"{n / div:.2f} {u}"


def fmt_eta(sec: Optional[float]) -> str:
    if sec is None:
        return "Calculando…"
    sec = int(sec)
    return f"{sec // 60:d}:{sec % 60:02d}"


def local_sha256(path: str, cb: Optional[Callable[[int], None]] = None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
            if cb:
                cb(len(chunk))
    return h.hexdigest()


@dataclass
class Progress:
    name: str = ""
    source: str = ""
    dest: str = ""
    host: str = ""
    total: int = 0
    done: int = 0
    state: str = "Conectando"
    t_connect: float = 0.0
    t_transfer: float = 0.0
    t_verify: float = 0.0
    src_hash: str = ""
    dst_hash: str = ""
    error: str = ""
    verified: bool = False
    _t0: float = 0.0
    _last: tuple = (0.0, 0)
    _cur_bps: float = 0.0

    # ---- mediciones
    def update(self, done: int, total: int) -> None:
        now = time.perf_counter()
        self.done, self.total = done, total
        lt, ld = self._last
        if now - lt >= 0.5:
            inst = (done - ld) / (now - lt)
            self._cur_bps = inst if self._cur_bps == 0 else 0.6 * self._cur_bps + 0.4 * inst
            self._last = (now, done)

    @property
    def percent(self) -> float:
        return 100.0 if self.total == 0 and self.state.startswith("Complet") else \
            (0.0 if self.total == 0 else min(100.0, 100.0 * self.done / self.total))

    @property
    def avg_bps(self) -> float:
        el = self.t_transfer_running
        return self.done / el if el > 0 else 0.0

    @property
    def t_transfer_running(self) -> float:
        if self.state == "Transfiriendo" and self._t0:
            return time.perf_counter() - self._t0
        return self.t_transfer

    @property
    def eta(self) -> Optional[float]:
        if self.total == 0 or self.done == 0 or self.t_transfer_running < 1.0 or self.avg_bps <= 0:
            return None  # sin estimación válida
        return max(0.0, (self.total - self.done) / self.avg_bps)

    @property
    def current_bps(self) -> float:
        return self._cur_bps


class TransferCancelled(Exception):
    pass


def _remote_hash(session, path: str) -> str:
    prof = profile_for(session.os_kind)
    r = session.run(prof.sha256(path).exec, timeout=600)
    if not r.ok:
        raise RemoteError(f"No se pudo calcular la suma remota: {r.err.strip()[:200]}")
    return prof.parse_hash(r.out)


def upload(session, local: str, remote: str, *, on_exists: Callable[[str], bool],
           cancel: threading.Event, on_progress: Callable[[Progress], None],
           t_connect: float = 0.0) -> Progress:
    p = Progress(name=os.path.basename(local), source=local, dest=remote, host=session.host, t_connect=t_connect)
    try:
        if not os.path.isfile(local):
            raise RemoteError("El archivo local no existe o no es un archivo.")
        p.total = os.path.getsize(local)
        if session.exists(remote):
            if not on_exists(remote):
                p.state = "Cancelado"
                p.error = "El usuario no autorizó sobrescribir."
                return p
        part = remote + ".part"
        p.state, p._t0 = "Transfiriendo", time.perf_counter()
        session.put(local, part, lambda d, t: (p.update(d, t), on_progress(p)), cancel)
        p.t_transfer = time.perf_counter() - p._t0
        p.state = "Verificando"
        on_progress(p)
        tv = time.perf_counter()
        p.src_hash = local_sha256(local)
        p.dst_hash = _remote_hash(session, part)
        p.t_verify = time.perf_counter() - tv
        if p.src_hash != p.dst_hash:
            session.remove(part)
            raise RemoteError("Integridad fallida: las sumas SHA-256 no coinciden. Se descartó el archivo parcial.")
        if session.exists(remote):
            session.remove(remote)
        session.rename(part, remote)
        p.verified, p.state = True, "Completado y verificado"
    except RemoteError as e:
        p.t_transfer = p.t_transfer or (time.perf_counter() - p._t0 if p._t0 else 0)
        p.state = "Cancelado" if cancel.is_set() else ("Incompleto" if p.state == "Transfiriendo" else "Error")
        p.error = str(e)
    finally:
        on_progress(p)
    return p


def download(session, remote: str, local: str, *, on_exists: Callable[[str], bool],
             cancel: threading.Event, on_progress: Callable[[Progress], None],
             t_connect: float = 0.0) -> Progress:
    p = Progress(name=os.path.basename(local), source=remote, dest=local, host=session.host, t_connect=t_connect)
    part = local + ".part"
    try:
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        if os.path.exists(local) and not on_exists(local):
            p.state, p.error = "Cancelado", "El usuario no autorizó sobrescribir."
            return p
        p.total = session.stat_size(remote)
        p.state, p._t0 = "Transfiriendo", time.perf_counter()
        session.get(remote, part, lambda d, t: (p.update(d, t), on_progress(p)), cancel)
        p.t_transfer = time.perf_counter() - p._t0
        p.state = "Verificando"
        on_progress(p)
        tv = time.perf_counter()
        p.dst_hash = local_sha256(part)
        p.src_hash = _remote_hash(session, remote)
        p.t_verify = time.perf_counter() - tv
        if p.src_hash != p.dst_hash or os.path.getsize(part) != p.total:
            raise RemoteError("Integridad fallida: la descarga no coincide con el original. Se conserva como .part.")
        os.replace(part, local)
        p.verified, p.state = True, "Completado y verificado"
    except RemoteError as e:
        p.t_transfer = p.t_transfer or (time.perf_counter() - p._t0 if p._t0 else 0)
        p.state = "Cancelado" if cancel.is_set() else ("Incompleto" if p.state == "Transfiriendo" else "Error")
        p.error = str(e)
    except OSError as e:
        p.state, p.error = "Error", f"Error de disco local: {e}"
    finally:
        on_progress(p)
    return p
