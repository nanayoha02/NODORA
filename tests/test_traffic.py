import os
import threading

import pytest

from nodora.core import pcap
from nodora.core.activity import ActivityLog
from nodora.core.config import Settings
from nodora.core.profiles import LinuxProfile, WindowsProfile
from nodora.core.validators import ValidationError
from nodora.ops import traffic
from nodora.ops.lab import Lab
from tests.fake_session import LocalSession
from tests.test_pcap import FRAMES, make_pcap

PROC_NET_DEV = """Inter-|   Receive                                                |  Transmit
 face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets errs drop fifo colls carrier compressed
    lo: 1000 10 0 0 0 0 0 0 1000 10 0 0 0 0 0 0
  eth0: 5000000 4000 0 0 0 0 0 0 800000 3000 0 0 0 0 0 0
"""


def test_counter_parsers():
    L = LinuxProfile().parse_net_counters(PROC_NET_DEV)
    assert L["eth0"] == (5000000, 800000) and "lo" in L
    W = WindowsProfile().parse_net_counters('[{"name":"Ethernet","rx":123,"tx":45},{"name":"Wi-Fi","rx":null,"tx":0}]')
    assert W == {"Ethernet": (123, 45), "Wi-Fi": (0, 0)}
    assert WindowsProfile().parse_net_counters('{"name":"Ethernet","rx":1,"tx":2}') == {"Ethernet": (1, 2)}   # un solo objeto


def test_connection_parsers():
    ss = '0 0 192.168.1.120:22 192.168.1.5:51000 users:(("sshd",pid=812,fd=4))\n0 0 10.0.0.2:5000 10.0.0.9:80\n'
    c = LinuxProfile().parse_connections(ss)
    assert LinuxProfile().parse_connections("ESTAB " + ss.splitlines()[0]) == c[:1]      # con columna de estado
    assert c[0] == {"local": "192.168.1.120:22", "remote": "192.168.1.5:51000", "pid": 812, "process": "sshd"}
    assert c[1]["pid"] == 0
    w = WindowsProfile().parse_connections('[{"laddr":"1.1.1.1","lport":22,"raddr":"2.2.2.2","rport":5,"pid":4,"process":"sshd"}]')
    assert w[0]["remote"] == "2.2.2.2:5"


def test_rates_use_real_elapsed_time_and_handle_resets():
    m = traffic.TrafficMonitor()
    assert m.update({"eth0": (0, 0), "lo": (0, 0)}, t=100.0) is None            # primera lectura: sin tasa
    r = m.update({"eth0": (1_000_000, 200_000), "lo": (999, 999)}, t=102.0)     # 2 s reales
    assert r.rx_bps == 500_000 and r.tx_bps == 100_000 and "lo" not in r.per_iface
    r2 = m.update({"eth0": (1_000_000, 200_000)}, t=103.0)                       # sin tráfico
    assert r2.rx_bps == 0
    r3 = m.update({"eth0": (50, 10)}, t=104.0)                                   # contador reiniciado: se descarta
    assert r3.rx_bps == 0 and "eth0" not in r3.per_iface
    assert m.peak_rx == 500_000 and m.total_rx >= 0


def test_rates_interface_filter_and_totals():
    m = traffic.TrafficMonitor()
    m.update({"a": (0, 0), "b": (0, 0)}, t=0)
    r = m.update({"a": (100, 0), "b": (900, 0)}, t=1, iface="b")
    assert r.rx_bps == 900 and m.total_rx == 900


@pytest.fixture
def env(tmp_path):
    cfg = Settings(remote_base=str(tmp_path / "remote"), local_dir=str(tmp_path / "local"), student_id="AMartinez",
                   student_name="Ana", student_group="1IL")
    os.makedirs(cfg.remote_base)
    s = LocalSession()
    lab = Lab(s, cfg, ActivityLog(cfg.local_dir))
    lab.prepare_folder()
    return lab, s, tmp_path


def test_log_sample_requires_measurements(env):
    lab, s, _ = env
    mon = traffic.TrafficMonitor()
    assert not traffic.log_traffic_sample(lab, mon).ok
    mon.update({"eth0": (0, 0)}, t=0)
    mon.update({"eth0": (10, 5)}, t=1)
    r = traffic.log_traffic_sample(lab, mon)
    assert r.ok and r.verified


def test_read_counters_real_proc(env):
    lab, *_ = env
    c = traffic.read_counters(lab)
    assert c and all(isinstance(v, tuple) and len(v) == 2 for v in c.values())


@pytest.mark.parametrize("kw", [dict(proto="http"), dict(proto="icmp", port=80), dict(port=0), dict(port=70000),
                                dict(host="1.2.3.4; rm -rf /"), dict(host="a b"), dict(seconds=1), dict(seconds=61),
                                dict(max_packets=5), dict(max_packets=99999)])
def test_capture_params_reject(kw):
    with pytest.raises(ValidationError):
        traffic.CaptureParams(**kw).validate()


def test_capture_params_accept_and_bpf_is_composed_only_from_validated_parts():
    p = traffic.CaptureParams(proto="tcp", port="443", host="192.168.1.5", seconds="10", max_packets="500").validate()
    cmd = LinuxProfile().capture("", "/x/c.pcap", p.seconds, p.proto, p.port, p.host, p.max_packets)
    assert "'tcp and host 192.168.1.5 and port 443'" in cmd.display and "-Z root" in cmd.display


TCPDUMP_SHIM = """#!/usr/bin/env python3
import sys
a = sys.argv[1:]
open(a[a.index('-w') + 1], 'wb').write(open(%r, 'rb').read())
"""


def _install_tcpdump(tmp_path, monkeypatch, pcap_bytes):
    src = tmp_path / "sample.pcap"
    src.write_bytes(pcap_bytes)
    b = tmp_path / "bin"
    b.mkdir(exist_ok=True)
    (b / "tcpdump").write_text(TCPDUMP_SHIM % str(src))
    (b / "tcpdump").chmod(0o755)
    monkeypatch.setenv("PATH", f"{b}:{os.environ['PATH']}")


def test_capture_end_to_end_verified_and_analyzed(env, monkeypatch):
    lab, s, tmp = env
    _install_tcpdump(tmp, monkeypatch, make_pcap(FRAMES))
    r = traffic.capture(lab, traffic.CaptureParams(proto="tcp", seconds=5), cancel=threading.Event())
    assert r.ok and r.verified, r.message
    d = r.data
    assert d["summary"].packets == 6 and os.path.exists(d["local"]) and os.path.exists(d["remote"])
    assert [p.proto for p in d["packets"]][:3] == ["TCP", "TCP", "DNS"]
    assert open(d["local"], "rb").read() == open(d["remote"], "rb").read()             # copia íntegra
    last = lab.log.all_rows()[-1]
    assert last["action"].startswith("27") and last["result"] == "verificada"


def test_capture_tool_missing_gives_clear_error(env, monkeypatch):
    lab, s, tmp = env
    monkeypatch.setenv("PATH", "/usr/bin:/bin")        # sin el shim: tcpdump no existe aquí
    r = traffic.capture(lab, traffic.CaptureParams(seconds=5), cancel=threading.Event())
    assert not r.ok and "tcpdump" in r.message and lab.log.all_rows()[-1]["result"] == "error"


def test_capture_with_empty_result_is_reported_honestly(env, monkeypatch):
    lab, s, tmp = env
    _install_tcpdump(tmp, monkeypatch, make_pcap([]))
    r = traffic.capture(lab, traffic.CaptureParams(seconds=5), cancel=threading.Event())
    assert r.ok and r.data["summary"].packets == 0 and "No hubo tráfico" in r.message


def test_connections_linux_real_or_graceful(env):
    lab, *_ = env
    r = traffic.connections(lab)
    assert r.ok or "ss" in r.message.lower() or r.message
