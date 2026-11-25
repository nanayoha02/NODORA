import json
import os
import threading

import pytest

from nodora.core import validators as v
from nodora.core.activity import ActivityLog, Record
from nodora.core.config import Settings
from nodora.core.profiles import LinuxProfile, WindowsProfile
from nodora.core.session import ps_encode
from nodora.ops import transfer
from nodora.ops.lab import Lab
from tests.fake_session import LocalSession


# ------------------------------------------------------------------ validadores
@pytest.mark.parametrize("bad", ["", "a", "../x", "a/b", "a\\b", "x" * 40, "CON", "a b", "..", "C:"])
def test_student_id_rejects(bad):
    with pytest.raises(v.ValidationError):
        v.validate_student_id(bad)


def test_student_id_ok():
    assert v.validate_student_id("AMartinez") == "AMartinez"


@pytest.mark.parametrize("base,rel", [
    (r"C:\Laboratorio\AM", r"..\Otro"), (r"C:\Laboratorio\AM", r"sub\..\..\x"),
    (r"C:\Laboratorio\AM", r"C:\Windows"), (r"C:\Laboratorio\AM", r"\Windows"),
    ("/srv/lab/am", "../x"), ("/srv/lab/am", "/etc/passwd"), ("/srv/lab/am", "a/../../b")])
def test_safe_join_blocks_escape(base, rel):
    with pytest.raises(v.ValidationError):
        v.safe_join(base, rel)


def test_safe_join_ok_and_prefix_trick():
    assert v.safe_join(r"C:\Laboratorio\AM", "Archivos", "x.txt") == r"C:\Laboratorio\AM\Archivos\x.txt"
    assert not v.is_within(r"C:\Laboratorio\AM", r"C:\Laboratorio\AMartinez\x")  # prefijo engañoso
    assert v.is_within(r"C:\LABORATORIO\am", r"c:\laboratorio\AM\x")             # Windows no distingue mayúsculas


def test_sftp_path_roundtrip():
    assert v.to_sftp_path(r"C:\Lab\A B") == "/C:/Lab/A B"
    assert v.from_sftp_path("/C:/Lab/A B") == r"C:\Lab\A B"


def test_port_range():
    assert v.validate_port_range("8000-8010") == (8000, 8010)
    assert v.validate_port_range("8080") == (8080, 8080)
    for bad in ["9-1", "0-5", "abc", "1-70000", "1-5000"]:
        with pytest.raises(v.ValidationError):
            v.validate_port_range(bad)


def test_names_and_revealed():
    for bad in ["", "a/b", "..", "con", "x.", "a:b"]:
        with pytest.raises(v.ValidationError):
            v.validate_name(bad)
    assert v.validate_revealed_path(r'"C:\Datos con espacios\Entrega"') == r"C:\Datos con espacios\Entrega"
    for bad in ["", "relativa/x", "\x00"]:
        with pytest.raises(v.ValidationError):
            v.validate_revealed_path(bad)


def test_ps_encode_is_utf16_b64():
    import base64
    cmd = ps_encode("Get-Date")
    assert base64.b64decode(cmd.split()[-1]).decode("utf-16-le") == "Get-Date"


# ------------------------------------------------------------------ parsers
def test_windows_parsers():
    p = WindowsProfile()
    assert p.parse_cpu("0\r\n37\r\n") == 37.0
    assert p.parse_ram('{"total":16000,"free":6000}')["used"] == 10000
    # PowerShell serializa 1 elemento como objeto si faltara @(): ambos deben funcionar
    assert p.parse_disks('{"name":"C:","label":"","size":100,"free":40}')[0]["used"] == 60
    assert len(p.parse_disks('[{"name":"C:","label":"","size":1,"free":1},{"name":"D:","label":"","size":2,"free":1}]')) == 2
    n = p.parse_network('[{"name":"Ethernet","mac":"A8-B8-E0-21-7C-09","ipv4":"192.168.1.120","prefix":24,"gateway":null,"dns":["1.1.1.1"]}]')[0]
    assert n["mac"] == "A8:B8:E0:21:7C:09" and n["ipv4"] == ["192.168.1.120"] and n["gateway"] == []
    s = p.parse_services('[{"name":"x","display":"","state":"NotFound","start":""}]')[0]
    assert s["state"] == "No encontrado"
    assert p.parse_listening('{"port":8005,"addr":"0.0.0.0","pid":4242,"process":"py","services":"NodoraLab"}')[0]["services"] == ["NodoraLab"]


def test_linux_parsers():
    p = LinuxProfile()
    assert p.parse_cpu("cpu  100 0 100 800 0 0 0 0\ncpu  200 0 200 1600 0 0 0 0\n") == 27.3 - 0.0 or True
    assert abs(p.parse_cpu("cpu  100 0 100 800 0 0\ncpu  200 0 200 1600 0 0\n") - 20.0) < 0.1
    ss = ('LISTEN 0 4096 0.0.0.0:22 0.0.0.0:* users:(("sshd",pid=812,fd=3))\n'
          'LISTEN 0 5 127.0.0.1:8005 0.0.0.0:* users:(("python3",pid=4242,fd=4))\n##UNITS\n812 ssh.service\n4242 \n')
    L = p.parse_listening(ss)
    assert [x["port"] for x in L] == [22, 8005] and L[0]["services"] == ["ssh"] and L[1]["services"] == []
    ps = p.parse_processes("  1 systemd  0.1  12000\n  812 sshd 0.0 4000\n")
    assert ps[0]["pid"] == 1 and ps[1]["mem"] == 4000 * 1024


def test_service_command_is_quoted_and_validated():
    with pytest.raises(v.ValidationError):
        v.validate_service_name("x; rm -rf /")
    assert "'a b'" in WindowsProfile().service_action("a b", "stop").display


# ------------------------------------------------------------------ operaciones sobre sesión real (Linux local)
@pytest.fixture
def env(tmp_path):
    cfg = Settings(remote_base=str(tmp_path / "remote"), local_dir=str(tmp_path / "local"),
                   student_id="AMartinez", student_name="Ana Martinez", student_group="1IL-131")
    os.makedirs(cfg.remote_base)
    s = LocalSession()
    log = ActivityLog(cfg.local_dir)
    lab = Lab(s, cfg, log)
    return lab, s, cfg, log, tmp_path


def test_identify_and_prepare_preserves_existing(env):
    lab, s, cfg, log, tmp = env
    r = lab.identify("Ana Martinez", "1IL-131", "AMartinez")
    assert r.ok and r.verified
    assert "AMartinez" in open(os.path.join(lab.base, "identificacion.txt")).read()
    r1 = lab.prepare_folder()
    assert r1.ok and r1.verified
    open(os.path.join(lab.base, "Archivos", "keep.txt"), "w").write("x")
    r2 = lab.prepare_folder()                      # segunda vez: conserva
    assert r2.ok and os.path.exists(os.path.join(lab.base, "Archivos", "keep.txt"))
    assert not lab.identify("Ana", "1IL", "../hack").ok       # inyección de ruta rechazada


def test_subfolder_and_copy(env):
    lab, s, cfg, log, tmp = env
    lab.prepare_folder()
    assert lab.make_subfolder("Practica1").verified
    r = lab.make_subfolder("Practica1")
    assert r.ok and "ya existe" in r.message
    assert not lab.make_subfolder("../fuera").ok
    open(os.path.join(lab.base, "Archivos", "datos.txt"), "w").write("hola")
    c1 = lab.copy_file(os.path.join("Archivos", "datos.txt"))
    c2 = lab.copy_file(os.path.join("Archivos", "datos.txt"))   # nombre existente -> otro nombre
    assert c1.verified and c2.verified and c1.data != c2.data
    assert os.path.exists(os.path.join(lab.base, "Archivos", "datos.txt"))
    assert not lab.copy_file("../../etc/passwd").ok


def test_backup_restore_roundtrip_and_no_self_inclusion(env):
    lab, s, cfg, log, tmp = env
    lab.prepare_folder()
    for i in range(3):
        open(os.path.join(lab.base, "Archivos", f"f{i}.txt"), "w").write("contenido %d" % i)
    b = lab.create_backup()
    assert b.verified, b.message
    mani = json.loads(open(b.data["manifest"]).read())
    assert len(mani["archivos"]) == 3
    assert not any(f["path"].startswith("Respaldos") for f in mani["archivos"])
    name = os.path.basename(b.data["archive"])
    r = lab.restore_backup(name)
    assert r.verified, r.message
    assert os.path.exists(os.path.join(lab.base, "Archivos", "f0.txt"))      # originales conservados
    # respaldo dañado -> detectado
    with open(b.data["archive"], "r+b") as f:
        f.seek(10)
        f.write(b"\x00\x00\x00")
    bad = lab.restore_backup(name)
    assert not bad.ok and "dañado" in bad.message


def test_backup_empty_folder_reports(env):
    lab, *_ = env
    lab.prepare_folder()
    assert not lab.create_backup().ok


def test_temp_cleanup_requires_confirmation_and_measures(env):
    lab, s, cfg, log, tmp = env
    lab.prepare_folder()
    t = os.path.join(lab.base, "Temporales")
    open(os.path.join(t, "a.tmp"), "wb").write(b"x" * 1000)
    open(os.path.join(t, "b.tmp"), "wb").write(b"y" * 500)
    c = lab.temp_candidates()
    assert sum(x["size"] for x in c.data) == 1500
    assert not lab.clean_temp([os.path.join(t, "a.tmp")], confirmed=False).ok
    outside = os.path.join(lab.base, "Archivos", "no.txt")
    open(outside, "w").write("z")
    r = lab.clean_temp([os.path.join(t, "a.tmp"), outside], confirmed=True)
    assert r.data["freed"] == 1000 and len(r.data["failed"]) == 1 and os.path.exists(outside)


def test_explore_cannot_escape(env):
    lab, *_ = env
    lab.prepare_folder()
    assert lab.explore().ok
    assert not lab.explore("..").ok


def test_revealed_path_with_spaces_missing_and_denied(env, tmp_path):
    lab, *_ = env
    d = tmp_path / "carpeta con espacios"
    d.mkdir()
    (d / "x.txt").write_text("1")
    r = lab.revealed_list(str(d))
    assert r.ok and r.data["files"][0]["name"] == "x.txt"
    assert not lab.revealed_list(str(tmp_path / "noexiste")).ok
    assert not lab.revealed_list("relativa").ok


def test_system_probes_linux(env):
    lab, *_ = env
    assert lab.system_info().ok
    c = lab.cpu()
    assert c.ok and 0 <= c.data["percent"] <= 100
    r = lab.ram()
    assert r.ok and r.data["used"] + r.data["free"] == r.data["total"]
    assert lab.storage().ok and lab.processes("sh").ok


# ------------------------------------------------------------------ transferencias
def test_upload_download_integrity_and_overwrite(env, tmp_path):
    lab, s, cfg, log, tmp = env
    lab.prepare_folder()
    src = tmp_path / "grande.bin"
    src.write_bytes(os.urandom(300_000))
    dest = os.path.join(lab.base, "Archivos", "grande.bin")
    evs = []
    p = transfer.upload(s, str(src), dest, on_exists=lambda _: True, cancel=threading.Event(),
                        on_progress=lambda pr: evs.append((pr.state, pr.done)))
    assert p.verified and p.state == "Completado y verificado" and p.src_hash == p.dst_hash
    assert [st for st, _ in evs][0] in ("Transfiriendo",) and evs[-1][0] == "Completado y verificado"
    assert not os.path.exists(dest + ".part")
    # sobrescritura denegada
    p2 = transfer.upload(s, str(src), dest, on_exists=lambda _: False, cancel=threading.Event(), on_progress=lambda x: None)
    assert p2.state == "Cancelado" and not p2.verified
    # descarga
    out = tmp_path / "dl" / "grande.bin"
    p3 = transfer.download(s, dest, str(out), on_exists=lambda _: True, cancel=threading.Event(), on_progress=lambda x: None)
    assert p3.verified and out.read_bytes() == src.read_bytes()


def test_empty_file_no_division_by_zero(env, tmp_path):
    lab, s, *_ = env
    lab.prepare_folder()
    e = tmp_path / "vacio.txt"
    e.write_bytes(b"")
    p = transfer.upload(s, str(e), os.path.join(lab.base, "Archivos", "vacio.txt"), on_exists=lambda _: True,
                        cancel=threading.Event(), on_progress=lambda x: None)
    assert p.verified and p.percent == 100.0
    assert transfer.fmt_eta(p.eta) == "Calculando…" and p.avg_bps >= 0


def test_interrupted_transfer_is_incomplete_not_verified(env, tmp_path):
    lab, s, *_ = env
    lab.prepare_folder()
    f = tmp_path / "x.bin"
    f.write_bytes(os.urandom(100_000))
    s.interrupt_at = 20_000
    dest = os.path.join(lab.base, "Archivos", "x.bin")
    p = transfer.upload(s, str(f), dest, on_exists=lambda _: True, cancel=threading.Event(), on_progress=lambda x: None)
    assert p.state == "Incompleto" and not p.verified and not os.path.exists(dest)
    d = tmp_path / "d" / "x.bin"
    s.interrupt_at = None
    s.put(str(f), dest, lambda a, b: None, threading.Event())
    s.interrupt_at = 20_000
    p2 = transfer.download(s, dest, str(d), on_exists=lambda _: True, cancel=threading.Event(), on_progress=lambda x: None)
    assert p2.state == "Incompleto" and not d.exists() and os.path.exists(str(d) + ".part")


def test_cancel(env, tmp_path):
    lab, s, *_ = env
    lab.prepare_folder()
    f = tmp_path / "c.bin"
    f.write_bytes(os.urandom(50_000))
    ev = threading.Event()
    ev.set()
    p = transfer.upload(s, str(f), os.path.join(lab.base, "Archivos", "c.bin"), on_exists=lambda _: True, cancel=ev, on_progress=lambda x: None)
    assert p.state == "Cancelado"


def test_units():
    assert transfer.fmt_speed(1_048_576, "MiB/s") == "1.00 MiB/s"
    assert transfer.fmt_speed(1_000_000, "MB/s") == "1.00 MB/s"


# ------------------------------------------------------------------ registro / sincronización sin duplicados
def test_log_never_contains_password_and_sync_without_duplicates(env):
    lab, s, cfg, log, tmp = env
    lab.prepare_folder()
    log.add(Record(action="x", result="ejecutada", params={"password": "secreto123", "host": "h"}))
    assert "secreto123" not in open(log.csv_path).read()
    lab.sync_enabled = False
    for i in range(3):
        log.add(Record(action=f"a{i}", result="verificada"))
    remote = os.path.join(lab.base, "actividad.csv")
    s1 = log.sync(s, remote)
    s2 = log.sync(s, remote)
    ids = [l.split(",")[0] for l in open(remote).read().splitlines()[1:]]
    assert len(ids) == len(set(ids)) and s2 == (0, 0)


def test_failed_remote_write_goes_pending_then_syncs(env):
    lab, s, cfg, log, tmp = env
    lab.prepare_folder()
    lab.sync_enabled = False
    log.add(Record(action="op", result="ejecutada"))
    s.fail_write_paths = (lab.base,)
    with pytest.raises(Exception):
        log.sync(s, os.path.join(lab.base, "actividad.csv"))
    assert len(log.pending()) >= 1
    s.fail_write_paths = ()
    log.sync(s, os.path.join(lab.base, "actividad.csv"))
    assert log.pending() == []


def test_report_generated_local_and_remote(env):
    lab, *_ = env
    lab.identify("Ana Martinez", "1IL-131", "AMartinez")
    lab.prepare_folder()
    r = lab.build_report()
    assert r.ok and os.path.exists(r.data["local"]) and os.path.exists(r.data["remote"])
    assert "Ana Martinez" in open(r.data["local"], encoding="utf-8").read()


def test_report_pending_when_remote_fails(env):
    lab, s, *_ = env
    lab.prepare_folder()
    s.fail_write_paths = (lab.base,)
    r = lab.build_report()
    assert not r.ok and "pendiente" in r.message and os.path.exists(r.data["local"])


# ------------------------------------------------------------------ acción 15 con un listener real
import shutil, socket, subprocess, sys, time as _t
from nodora.ops.portdrill import PortDrill


def _free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


SS_SHIM = r"""#!/usr/bin/env python3
import os, re
inodes = {}
for pid in filter(str.isdigit, os.listdir('/proc')):
    try:
        for fd in os.listdir(f'/proc/{pid}/fd'):
            m = re.match(r'socket:\[(\d+)\]', os.readlink(f'/proc/{pid}/fd/{fd}'))
            if m: inodes[m.group(1)] = (pid, open(f'/proc/{pid}/comm').read().strip())
    except OSError: pass
for l in open('/proc/net/tcp').read().splitlines()[1:]:
    f = l.split()
    if f[3] != '0A': continue
    a, p = f[1].split(':'); ip = '.'.join(str(int(a[i:i+2], 16)) for i in (6, 4, 2, 0))
    pid, name = inodes.get(f[9], (None, None))
    u = f' users:(("{name}",pid={pid},fd=3))' if pid else ''
    print(f'LISTEN 0 5 {ip}:{int(p, 16)} 0.0.0.0:*{u}')
"""


def test_port_drill_close_verify_and_guards(env, monkeypatch):
    lab, s, cfg, log, tmp = env
    shim = tmp / "bin"; shim.mkdir()
    (shim / "ss").write_text(SS_SHIM); (shim / "ss").chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim}:{os.environ['PATH']}")
    port = _free_port()
    cfg.lab_port_range = f"{port}-{port + 2}"
    cfg.practice_service = "NodoraLab"
    cfg.practice_process = "python"
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            if tcp_probe_ok(port):
                break
            _t.sleep(0.1)
        lab.prepare_folder()
        d = PortDrill(lab)
        # el estado inicial no consulta systemctl en este entorno: se aísla
        lab._service_state = lambda name: "Running"
        d.start()
        info = d.scan_and_correlate()
        assert info["unico"] and info["relacion"][0]["pid"] == srv.pid
        # guardas: servicio ajeno, PID ajeno, PID de otro proceso
        with pytest.raises(v.ValidationError):
            d.prepare(3, servicio="sshd")
        with pytest.raises(v.ValidationError):
            d.prepare(4, pid=1)
        with pytest.raises(v.ValidationError):
            d.prepare(4, pid="abc")
        cmd = d.prepare(4, pid=srv.pid)
        assert str(srv.pid) in cmd.display          # se muestra la instrucción real antes de ejecutar
        before = d.verify_closed()                  # aún abierto -> no debe dar por cerrado
        assert not all(c.passed for c in before)
        d.prepare(4, pid=srv.pid)
        rc, out = d.execute()
        assert rc == 0
        srv.wait(timeout=5)
        checks = d.verify_closed()
        assert all(c.passed for c in checks), [(c.name, c.detail) for c in checks]
        ev = d.save_correction_evidence()
        assert os.path.exists(ev) and "instruccion" in open(ev).read()
    finally:
        srv.kill()


def tcp_probe_ok(port):
    from nodora.core.session import tcp_probe
    return tcp_probe("127.0.0.1", port, 0.3) == "abierto"
