"""Acciones 26 (tráfico en vivo) y 27 (captura de paquetes, descargable a Wireshark)."""
from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..core import pcap
from ..core.session import RemoteError
from ..core.validators import ValidationError, safe_join, validate_host, validate_port
from . import transfer
from .lab import Lab, Result, stamp

LOOPBACK = re.compile(r"^(lo|loopback.*)$", re.I)


# ============================================================================ 26 · tráfico en vivo
@dataclass
class Rates:
    at: float
    per_iface: dict            # nombre -> (rx_bps, tx_bps)
    rx_bps: float = 0.0
    tx_bps: float = 0.0


class TrafficMonitor:
    """Convierte contadores acumulados en tasas (bytes/s) usando el tiempo REAL entre lecturas.

    Si un contador baja (reinicio de interfaz o desbordamiento) se descarta ese intervalo."""

    def __init__(self):
        self.prev: Optional[tuple[float, dict]] = None
        self.start: Optional[dict] = None
        self.peak_rx = self.peak_tx = 0.0
        self.total_rx = self.total_tx = 0

    def reset(self) -> None:
        self.__init__()

    def update(self, counters: dict, t: float | None = None, iface: str = "") -> Optional[Rates]:
        t = time.monotonic() if t is None else t
        use = {k: v for k, v in counters.items() if not LOOPBACK.match(k)}
        if self.start is None:
            self.start = use
        out = None
        if self.prev and t > self.prev[0]:
            dt = t - self.prev[0]
            per = {}
            for k, (rx, tx) in use.items():
                if k in self.prev[1]:
                    prx, ptx = self.prev[1][k]
                    if rx >= prx and tx >= ptx:
                        per[k] = ((rx - prx) / dt, (tx - ptx) / dt)
            sel = {k: v for k, v in per.items() if not iface or k == iface}
            out = Rates(t, per, sum(v[0] for v in sel.values()), sum(v[1] for v in sel.values()))
            self.peak_rx, self.peak_tx = max(self.peak_rx, out.rx_bps), max(self.peak_tx, out.tx_bps)
        sel_now = {k: v for k, v in use.items() if not iface or k == iface}
        sel0 = {k: v for k, v in self.start.items() if not iface or k == iface}
        self.total_rx = sum(v[0] - sel0.get(k, v)[0] for k, v in sel_now.items())
        self.total_tx = sum(v[1] - sel0.get(k, v)[1] for k, v in sel_now.items())
        self.prev = (t, use)
        return out


def read_counters(lab: Lab) -> dict:
    r = lab._run(lab.prof.net_counters())
    if not r.ok:
        raise RemoteError(f"No se pudieron leer los contadores de red: {r.err.strip()[:200]}")
    return lab.prof.parse_net_counters(r.out)


def log_traffic_sample(lab: Lab, mon: TrafficMonitor, iface: str = "") -> Result:
    """Acción 26: registra el resultado de la medición en curso (valores reales, no simulados)."""
    act = "26 Medir el tráfico de red"
    if mon.prev is None or mon.start is None:
        lab._rec(act, "error", error="Sin mediciones: inicie la gráfica primero.")
        return Result(False, "Inicie la gráfica en vivo y espere al menos dos lecturas.")
    d = {"interfaz": iface or "todas", "pico_rx_Bps": round(mon.peak_rx), "pico_tx_Bps": round(mon.peak_tx),
         "recibido_B": mon.total_rx, "enviado_B": mon.total_tx}
    lab._rec(act, "verificada", params=d)
    return Result(True, "Medición registrada.", d, True)


def connections(lab: Lab) -> Result:
    act = "26 Consultar conexiones TCP establecidas"
    try:
        r = lab._run(lab.prof.connections())
        if not r.ok:
            raise RemoteError(r.err.strip()[:200] or "Fallo al consultar conexiones.")
        d = lab.prof.parse_connections(r.out)
        lab._rec(act, "ejecutada", params={"conexiones": len(d)})
        return Result(True, f"{len(d)} conexión(es) establecida(s).", d)
    except (RemoteError, ValueError) as e:
        return lab._fail(act, e)


# ============================================================================ 27 · captura de paquetes
@dataclass
class CaptureParams:
    proto: str = "any"
    port: Optional[int] = None
    host: str = ""
    seconds: int = 15
    max_packets: int = 2000

    def validate(self) -> "CaptureParams":
        if self.proto not in ("any", "tcp", "udp", "icmp"):
            raise ValidationError("Protocolo no permitido (use cualquiera, TCP, UDP o ICMP).")
        if self.port not in (None, ""):
            self.port = validate_port(self.port)
            if self.proto in ("icmp",):
                raise ValidationError("ICMP no usa puertos: quite el puerto o elija TCP/UDP.")
        else:
            self.port = None
        self.host = validate_host(self.host) if self.host else ""
        if not 5 <= int(self.seconds) <= 60:
            raise ValidationError("La duración debe estar entre 5 y 60 segundos.")
        if not 100 <= int(self.max_packets) <= 5000:
            raise ValidationError("El máximo de paquetes debe estar entre 100 y 5000.")
        self.seconds, self.max_packets = int(self.seconds), int(self.max_packets)
        return self


def capture(lab: Lab, params: CaptureParams, *, cancel: threading.Event,
            on_progress: Callable[[transfer.Progress], None] = lambda p: None) -> Result:
    """Captura en BOSGAME, descarga el archivo con SHA-256 verificado y lo analiza localmente."""
    act = "27 Captura de paquetes"
    try:
        params.validate()
        lab._require_base()
        ts = stamp()
        ev = lab.sub("Evidencias")
        ext = lab.prof.capture_ext()
        remote_pcap = safe_join(ev, f"captura_{ts}{ext}")
        remote_etl = safe_join(ev, f"captura_{ts}.etl")
        if lab.s.os_kind == "windows":
            cmd = lab.prof.capture(remote_etl, remote_pcap, params.seconds, params.proto, params.port, params.host)
        else:
            cmd = lab.prof.capture(remote_etl, remote_pcap, params.seconds, params.proto, params.port, params.host,
                                   params.max_packets)
        r = lab.s.run(cmd.exec, timeout=params.seconds + 90)
        have = lab.s.exists(remote_pcap) is True
        if (not r.ok and not (r.rc == 124 and have)) or not have:
            low = (r.err + r.out).lower()
            hint = ""
            if any(w in low for w in ("not found", "no se reconoce", "no es un comando", "command not found")):
                hint = " La herramienta de captura (tcpdump/pktmon) no está instalada en BOSGAME."
            elif any(w in low for w in ("permission", "denied", "privileg", "admin", "sudo", "pktmon_no_inicio")):
                hint = " Se necesitan privilegios de administrador/root en BOSGAME."
            raise RemoteError(f"La captura falló (código {r.rc}).{hint} Detalle: {(r.err or r.out).strip()[:200]}")
        local = os.path.join(lab.cfg.local_dir, "Capturas", f"captura_{ts}{ext}")
        p = transfer.download(lab.s, remote_pcap, local, on_exists=lambda _: True, cancel=cancel, on_progress=on_progress)
        if not p.verified:
            raise RemoteError(f"Descarga de la captura sin verificar ({p.state}): {p.error}")
        pk = pcap.read_file(local)
        sm = pcap.summarize(pk)
        lab._rec(act, "verificada", source=remote_pcap, destination=local, evidence=remote_pcap,
                 params={"filtro": f"{params.proto} {params.host} {params.port or ''}".strip(), "segundos": params.seconds,
                         "paquetes": sm.packets, "bytes": sm.bytes, "sha256": p.src_hash[:16],
                         "protocolos": sm.protocols})
        msg = (f"Captura verificada: {sm.packets} paquetes, {sm.bytes} bytes. "
               + ("" if sm.packets else "No hubo tráfico que cumpliera el filtro durante el tiempo indicado. "))
        return Result(True, msg, {"packets": pk, "summary": sm, "local": local, "remote": remote_pcap,
                                  "sha256": p.src_hash}, True, remote_pcap)
    except (ValidationError, RemoteError, pcap.PcapError) as e:
        return lab._fail(act, e)
