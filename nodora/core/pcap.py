"""Lector mínimo de capturas .pcap y .pcapng y disector de protocolos comunes.

Sin dependencias. Soporta Ethernet, IP crudo y Linux cooked (SLL/SLL2); IPv4, IPv6, ARP, TCP, UDP, ICMP,
ICMPv6 y consultas DNS. Nunca ejecuta ni interpreta cargas útiles: solo cabeceras."""
from __future__ import annotations

import ipaddress
import socket
import struct
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

LINK_ETH, LINK_RAW, LINK_SLL, LINK_RAW2, LINK_SLL2 = 1, 101, 113, 228, 276
MAX_PACKETS = 200_000


class PcapError(ValueError):
    pass


@dataclass
class Packet:
    n: int
    ts: float
    caplen: int
    wirelen: int
    proto: str = "?"
    src: str = ""
    dst: str = ""
    sport: Optional[int] = None
    dport: Optional[int] = None
    info: str = ""

    @property
    def time_str(self) -> str:
        return datetime.fromtimestamp(self.ts).strftime("%H:%M:%S.%f")[:-3]


# ----------------------------------------------------------------------------- contenedores
def read_file(path: str) -> list[Packet]:
    with open(path, "rb") as f:
        return parse(f.read())


def parse(data: bytes) -> list[Packet]:
    if len(data) < 12:
        raise PcapError("Archivo de captura vacío o truncado.")
    magic = data[:4]
    if magic == b"\x0a\x0d\x0d\x0a":
        raw = _pcapng(data)
    elif magic in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d"):
        raw = _pcap(data)
    else:
        raise PcapError("No es un archivo .pcap ni .pcapng válido.")
    out = []
    for i, (ts, caplen, wirelen, link, frame) in enumerate(raw, 1):
        p = Packet(i, ts, caplen, wirelen)
        try:
            _dissect(p, link, frame)
        except (struct.error, IndexError, ValueError):
            p.proto, p.info = p.proto if p.proto != "?" else "Malformado", "Paquete truncado o malformado"
        out.append(p)
    return out


def _pcap(data: bytes):
    big = data[:4] in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d")
    nano = data[:4] in (b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\x3c\x4d")
    e = ">" if big else "<"
    if len(data) < 24:
        raise PcapError("Cabecera pcap truncada.")
    link = struct.unpack(e + "I", data[20:24])[0] & 0x0FFFFFFF
    pos, n = 24, 0
    while pos + 16 <= len(data):
        sec, frac, caplen, wirelen = struct.unpack(e + "IIII", data[pos:pos + 16])
        pos += 16
        if caplen > 0x40000 or pos + caplen > len(data):
            break  # registro final incompleto (captura interrumpida): se ignora
        yield sec + frac / (1e9 if nano else 1e6), caplen, wirelen, link, data[pos:pos + caplen]
        pos += caplen
        n += 1
        if n >= MAX_PACKETS:
            break


def _pcapng(data: bytes):
    e = "<"
    pos, ifaces, n = 0, [], 0
    while pos + 12 <= len(data):
        btype = struct.unpack(e + "I", data[pos:pos + 4])[0]
        if btype == 0x0A0D0D0A:  # SHB: detecta endianness
            bom = data[pos + 8:pos + 12]
            e = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
            ifaces = []
        blen = struct.unpack(e + "I", data[pos + 4:pos + 8])[0]
        if blen < 12 or blen % 4 or pos + blen > len(data):
            break
        body = data[pos + 8:pos + blen - 4]
        if btype == 1 and len(body) >= 8:  # IDB
            link = struct.unpack(e + "H", body[:2])[0]
            res = 1e-6
            opt = body[8:]
            while len(opt) >= 4:
                code, ln = struct.unpack(e + "HH", opt[:4])
                if code == 0:
                    break
                if code == 9 and ln >= 1:  # if_tsresol
                    v = opt[4]
                    res = 2.0 ** -(v & 0x7F) if v & 0x80 else 10.0 ** -v
                opt = opt[4 + ((ln + 3) & ~3):]
            ifaces.append((link, res))
        elif btype == 6 and len(body) >= 20:  # EPB
            iid, th, tl, caplen, wirelen = struct.unpack(e + "IIIII", body[:20])
            link, res = ifaces[iid] if iid < len(ifaces) else (1, 1e-6)
            frame = body[20:20 + caplen]
            yield ((th << 32 | tl) * res), caplen, wirelen, link, frame
            n += 1
            if n >= MAX_PACKETS:
                break
        elif btype == 3 and len(body) >= 4 and ifaces:  # SPB
            wirelen = struct.unpack(e + "I", body[:4])[0]
            link, _ = ifaces[0]
            frame = body[4:]
            yield 0.0, len(frame), wirelen, link, frame
        pos += blen


# ----------------------------------------------------------------------------- disector
def _dissect(p: Packet, link: int, f: bytes) -> None:
    if link == LINK_ETH:
        et = struct.unpack("!H", f[12:14])[0]
        off = 14
        while et in (0x8100, 0x88A8):
            et = struct.unpack("!H", f[off + 2:off + 4])[0]
            off += 4
        _l3(p, et, f[off:], f[6:12], f[0:6])
    elif link == LINK_SLL:
        _l3(p, struct.unpack("!H", f[14:16])[0], f[16:], b"", b"")
    elif link == LINK_SLL2:
        _l3(p, struct.unpack("!H", f[0:2])[0], f[20:], b"", b"")
    elif link in (LINK_RAW, LINK_RAW2):
        _l3(p, 0x0800 if f[0] >> 4 == 4 else 0x86DD, f, b"", b"")
    else:
        p.proto, p.info = "?", f"Tipo de enlace {link} no soportado"


def _mac(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in b)


def _l3(p: Packet, et: int, d: bytes, smac: bytes, dmac: bytes) -> None:
    if et == 0x0806:  # ARP
        op = struct.unpack("!H", d[6:8])[0]
        spa, tpa = socket.inet_ntoa(d[14:18]), socket.inet_ntoa(d[24:28])
        p.proto, p.src, p.dst = "ARP", spa, tpa
        p.info = f"¿Quién tiene {tpa}? Dígalo a {spa}" if op == 1 else f"{spa} está en {_mac(d[8:14])}"
    elif et == 0x0800:  # IPv4
        ihl = (d[0] & 0x0F) * 4
        proto = d[9]
        p.src, p.dst = socket.inet_ntoa(d[12:16]), socket.inet_ntoa(d[16:20])
        frag = struct.unpack("!H", d[6:8])[0] & 0x1FFF
        _l4(p, proto, d[ihl:], frag)
    elif et == 0x86DD:  # IPv6
        nh = d[6]
        p.src, p.dst = str(ipaddress.IPv6Address(d[8:24])), str(ipaddress.IPv6Address(d[24:40]))
        _l4(p, nh, d[40:], 0)
    else:
        p.proto, p.src, p.dst = f"0x{et:04x}", _mac(smac), _mac(dmac)
        p.info = "Protocolo de capa 3 no analizado"


TCP_FLAGS = [(0x02, "SYN"), (0x10, "ACK"), (0x01, "FIN"), (0x04, "RST"), (0x08, "PSH"), (0x20, "URG")]
ICMP_T = {0: "Respuesta de eco", 3: "Destino inalcanzable", 8: "Solicitud de eco", 11: "Tiempo excedido"}
ICMP6_T = {128: "Solicitud de eco", 129: "Respuesta de eco", 135: "Solicitud de vecino", 136: "Anuncio de vecino"}


def _l4(p: Packet, proto: int, d: bytes, frag: int) -> None:
    if frag:
        p.proto, p.info = "IP", "Fragmento IP"
        return
    if proto == 6:
        sp, dp, seq, ack, off = struct.unpack("!HHIIB", d[:13])
        flags = d[13]
        hl = (off >> 4) * 4
        pl = max(0, len(d) - hl)
        p.proto, p.sport, p.dport = "TCP", sp, dp
        fl = ",".join(n for b, n in TCP_FLAGS if flags & b) or "—"
        p.info = f"{sp} → {dp} [{fl}] len={pl}"
        if 80 in (sp, dp) and pl and d[hl:hl + 4] in (b"GET ", b"POST", b"HTTP", b"PUT ", b"HEAD"):
            p.proto = "HTTP"
            p.info = d[hl:hl + 80].split(b"\r\n")[0].decode("ascii", "replace")
        elif 443 in (sp, dp) and pl and d[hl] == 0x16:
            p.proto, p.info = "TLS", f"{sp} → {dp} handshake len={pl}"
    elif proto == 17:
        sp, dp, ln = struct.unpack("!HHH", d[:6])
        p.proto, p.sport, p.dport = "UDP", sp, dp
        p.info = f"{sp} → {dp} len={max(0, ln - 8)}"
        if 53 in (sp, dp) or 5353 in (sp, dp):
            _dns(p, d[8:])
    elif proto == 1:
        p.proto, p.info = "ICMP", ICMP_T.get(d[0], f"Tipo {d[0]}")
    elif proto == 58:
        p.proto, p.info = "ICMPv6", ICMP6_T.get(d[0], f"Tipo {d[0]}")
    else:
        p.proto, p.info = f"IP/{proto}", "Protocolo de transporte no analizado"


def _dns(p: Packet, d: bytes) -> None:
    tid, flags, qd = struct.unpack("!HHH", d[:6])
    name, i = [], 12
    while True:
        ln = d[i]
        if ln == 0 or ln & 0xC0:
            break
        name.append(d[i + 1:i + 1 + ln].decode("ascii", "replace"))
        i += ln + 1
    p.proto = "DNS"
    p.info = ("Respuesta " if flags & 0x8000 else "Consulta ") + (".".join(name) or "<raíz>")


# ----------------------------------------------------------------------------- resumen
@dataclass
class Summary:
    packets: int = 0
    bytes: int = 0
    duration_s: float = 0.0
    protocols: dict = field(default_factory=dict)
    talkers: list = field(default_factory=list)       # (origen→destino, paquetes, bytes)
    first: str = ""
    last: str = ""


def summarize(pkts: list[Packet], top: int = 5) -> Summary:
    s = Summary(packets=len(pkts))
    if not pkts:
        return s
    s.bytes = sum(p.wirelen for p in pkts)
    ts = [p.ts for p in pkts if p.ts > 0]
    if ts:
        s.duration_s = max(ts) - min(ts)
        s.first, s.last = pkts[0].time_str, pkts[-1].time_str
    s.protocols = dict(Counter(p.proto for p in pkts).most_common())
    flows: dict[tuple, list] = {}
    for p in pkts:
        if p.src or p.dst:
            k = (p.src, p.dst)
            f = flows.setdefault(k, [0, 0])
            f[0] += 1
            f[1] += p.wirelen
    s.talkers = [(f"{a} → {b}", v[0], v[1]) for (a, b), v in sorted(flows.items(), key=lambda kv: -kv[1][1])[:top]]
    return s
