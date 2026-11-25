import socket
import struct

import pytest

from nodora.core import pcap


def eth(payload, et=0x0800):
    return bytes.fromhex("aabbccddeeff") + bytes.fromhex("112233445566") + struct.pack("!H", et) + payload


def ipv4(proto, src, dst, l4):
    h = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(l4), 1, 0, 64, proto, 0, socket.inet_aton(src), socket.inet_aton(dst))
    return h + l4


def tcp(sp, dp, flags, payload=b""):
    return struct.pack("!HHIIBBHHH", sp, dp, 1, 0, 5 << 4, flags, 8192, 0, 0) + payload


def udp(sp, dp, payload):
    return struct.pack("!HHHH", sp, dp, 8 + len(payload), 0) + payload


def dns_query(name):
    q = b"".join(bytes([len(x)]) + x.encode() for x in name.split(".")) + b"\x00" + struct.pack("!HH", 1, 1)
    return struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0) + q


def arp_req():
    return struct.pack("!HHBBH6s4s6s4s", 1, 0x0800, 6, 4, 1, bytes.fromhex("112233445566"),
                       socket.inet_aton("192.168.1.5"), b"\0" * 6, socket.inet_aton("192.168.1.1"))


FRAMES = [
    eth(ipv4(6, "192.168.1.5", "192.168.1.120", tcp(51000, 22, 0x02))),                         # SYN
    eth(ipv4(6, "192.168.1.120", "192.168.1.5", tcp(22, 51000, 0x12))),                         # SYN,ACK
    eth(ipv4(17, "192.168.1.5", "8.8.8.8", udp(40000, 53, dns_query("www.ejemplo.com")))),      # DNS
    eth(ipv4(1, "192.168.1.5", "192.168.1.120", b"\x08\x00\x00\x00\x00\x01\x00\x01")),         # ping
    eth(arp_req(), 0x0806),
    eth(ipv4(6, "192.168.1.5", "10.0.0.9", tcp(50000, 80, 0x18, b"GET /index.html HTTP/1.1\r\nHost: x\r\n\r\n"))),
]


def make_pcap(frames, big=False, nano=False, link=1):
    e = ">" if big else "<"
    magic = 0xA1B23C4D if nano else 0xA1B2C3D4
    out = struct.pack(e + "IHHiIII", magic, 2, 4, 0, 0, 65535, link)
    for i, f in enumerate(frames):
        out += struct.pack(e + "IIII", 1700000000 + i, 123456 if not nano else 123456789, len(f), len(f)) + f
    return out


def make_pcapng(frames):
    def block(t, body):
        body += b"\0" * (-len(body) % 4)
        return struct.pack("<II", t, len(body) + 12) + body + struct.pack("<I", len(body) + 12)
    shb = block(0x0A0D0D0A, struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1))
    idb = block(1, struct.pack("<HHI", 1, 0, 65535) + struct.pack("<HHB3x", 9, 1, 6) + struct.pack("<HH", 0, 0))
    epbs = b""
    for i, f in enumerate(frames):
        ts = (1700000000 + i) * 10**6
        epbs += block(6, struct.pack("<IIIII", 0, ts >> 32, ts & 0xFFFFFFFF, len(f), len(f)) + f)
    return shb + idb + epbs


@pytest.mark.parametrize("data", [make_pcap(FRAMES), make_pcap(FRAMES, big=True), make_pcap(FRAMES, nano=True),
                                  make_pcapng(FRAMES)])
def test_formats_and_dissection(data):
    pk = pcap.parse(data)
    assert [p.proto for p in pk] == ["TCP", "TCP", "DNS", "ICMP", "ARP", "HTTP"]
    assert pk[0].src == "192.168.1.5" and pk[0].dport == 22 and "SYN" in pk[0].info
    assert "SYN" in pk[1].info and "ACK" in pk[1].info
    assert pk[2].info == "Consulta www.ejemplo.com"
    assert pk[3].info == "Solicitud de eco"
    assert "192.168.1.1" in pk[4].info
    assert pk[5].info.startswith("GET /index.html")
    assert abs(pk[1].ts - pk[0].ts - 1) < 1e-3


def test_summary():
    s = pcap.summarize(pcap.parse(make_pcap(FRAMES)))
    assert s.packets == 6 and s.protocols["TCP"] == 2 and s.duration_s == 5
    assert s.talkers[0][1] >= 1


def test_truncated_last_record_is_ignored_and_garbage_rejected():
    data = make_pcap(FRAMES)
    assert len(pcap.parse(data[:-10])) == 5               # captura interrumpida: se conserva lo completo
    with pytest.raises(pcap.PcapError):
        pcap.parse(b"esto no es una captura de red")
    with pytest.raises(pcap.PcapError):
        pcap.parse(b"")


def test_malformed_packet_does_not_crash():
    pk = pcap.parse(make_pcap([eth(b"\x45\x00")]))        # IPv4 truncado
    assert pk[0].proto in ("Malformado", "?", "IP") or "malformado" in pk[0].info.lower()


def test_linux_cooked_and_raw():
    ip = ipv4(6, "1.1.1.1", "2.2.2.2", tcp(1, 2, 0x10))
    sll = b"\0\0" + b"\0\1" + b"\0\6" + b"\0" * 8 + struct.pack("!H", 0x0800) + ip
    assert pcap.parse(make_pcap([sll], link=113))[0].proto == "TCP"
    assert pcap.parse(make_pcap([ip], link=101))[0].dst == "2.2.2.2"
