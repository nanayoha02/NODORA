"""Prueba de humo de la interfaz SIN Qt: sustituye PySide6 por un doble permisivo para detectar
errores de nombres, importaciones y lógica propia. No valida el aspecto visual (requiere Qt real)."""
import importlib.util
import os
import sys
import types

import pytest

REAL_QT = importlib.util.find_spec("PySide6") is not None
pytestmark = pytest.mark.skipif(REAL_QT, reason="con PySide6 real se prueba la app directamente")


class _M(type):
    def __getattr__(cls, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _S()


class _S(metaclass=_M):
    def __init__(self, *a, **k): pass
    def __getattr__(self, n):
        if n.startswith("__"):
            raise AttributeError(n)
        return _S()
    def __call__(self, *a, **k): return _S()
    def __iter__(self): return iter(())
    def __bool__(self): return True
    def __or__(self, o): return _S()
    __and__ = __ror__ = __or__
    def __int__(self): return 0
    def __index__(self): return 0
    def __float__(self): return 0.0
    def __gt__(self, o): return False
    __lt__ = __ge__ = __le__ = __gt__
    def __eq__(self, o): return False
    def __hash__(self): return id(self)


def _install():
    for name in ("PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"):
        m = types.ModuleType(name)
        if name != "PySide6":
            m.__getattr__ = lambda n: (_S if n[0].isupper() or n in ("Signal",) else _S)
        sys.modules[name] = m
    sys.modules["PySide6.QtCore"].Signal = lambda *a, **k: _S()
    sys.modules["PySide6.QtCore"].QObject = _S
    sys.modules["PySide6.QtCore"].Qt = _S


@pytest.fixture(scope="module")
def ui(tmp_path_factory):
    _install()
    from nodora.ui import widgets
    calls = []
    widgets.run_async = lambda fn, ok=None, err=None: (ok(fn()) if ok else fn())
    from nodora.ui import pages_a, pages_b, pages_c, dialogs, main_window, state as st  # noqa: F401
    for mod in (pages_a, pages_b, pages_c, dialogs):
        mod.run_async = widgets.run_async
    return types.SimpleNamespace(pa=pages_a, pb=pages_b, pc=pages_c, d=dialogs, st=st, mw=main_window)


@pytest.fixture
def state(ui, tmp_path, monkeypatch):
    from nodora.core import config
    monkeypatch.setattr(config, "app_dir", lambda: tmp_path)
    from nodora.ops.lab import Lab
    from tests.fake_session import LocalSession
    s = ui.st.AppState.__new__(ui.st.AppState)
    s.cfg = config.Settings(remote_base=str(tmp_path / "remote"), local_dir=str(tmp_path / "local"),
                            student_id="AMartinez", student_name="Ana", student_group="1IL")
    os.makedirs(s.cfg.remote_base)
    from nodora.core.activity import ActivityLog
    s.log = ActivityLog(s.cfg.local_dir)
    s.session = LocalSession()
    s.lab = Lab(s.session, s.cfg, s.log)
    s.latency_ms, s.sysinfo, s.connected_at = 12.0, {}, 0
    s.identity_changed = s.connection_changed = _S()
    return s


def test_all_pages_construct(ui, state):
    for cls in (ui.pa.DashboardPage, ui.pa.ConnectionPage, ui.pa.MonitorPage, ui.pb.NetworkPage,
                ui.pb.FilesPage, ui.pc.HistoryPage, ui.pc.SettingsPage):
        cls(state)


def test_dashboard_and_monitor_samples(ui, state):
    d, m = ui.pa.DashboardPage(state), ui.pa.MonitorPage(state)
    lab = state.lab
    with lab.quiet():
        sample = {"cpu": lab.cpu().data["percent"], "ram": lab.ram().data, "disks": lab.storage().data}
    state.sysinfo = lab.system_info().data
    for p in (d, m):
        p.on_sample(sample)
        p.on_connection(True)
    m._sys_done(lab.system_info())
    m._procs_done(lab.processes("sh"))
    m._cpu_done(lab.cpu())
    m._ram_done(lab.ram())


def test_connection_page_actions(ui, state):
    c = ui.pa.ConnectionPage(state)
    for w, t in ((c.sid, "AMartinez"), (c.name, "Ana Martinez"), (c.group, "1IL-131")):
        w.text = lambda t=t: t
    c.identify_()
    c.prepare_()
    assert os.path.isdir(os.path.join(state.cfg.remote_base, "AMartinez", "Archivos"))
    c.on_connection(True)


def test_files_page_flow(ui, state, tmp_path):
    f = ui.pb.FilesPage(state)
    state.lab.prepare_folder()
    f.reload()
    assert f.entries and f.entries[0]["type"] in ("Carpeta", "Archivo")
    f._backup() if False else None
    r = state.lab.make_subfolder("Nueva")
    f.reload()
    assert any(e["name"] == "Nueva" for e in f.entries)
    f._load_backups()


def test_history_page(ui, state):
    state.lab.prepare_folder()
    state.lab.system_info()
    h = ui.pc.HistoryPage(state)
    h.reload()
    h._report()
    assert ui.pc.category("23 Limpiar", "error") == "Error" and ui.pc.category("18 Enviar", "verificada") == "Transferencia"


def test_network_page_handlers(ui, state):
    n = ui.pb.NetworkPage(state)
    n._net_done(state.lab.network() if False else types.SimpleNamespace(ok=True, data=[
        {"name": "eth0", "mac": "", "ipv4": ["1.2.3.4"], "prefix": [24], "gateway": [], "dns": []}], message=""))
    c = state.lab.connectivity()
    n._conn_done(c)


def test_settings_save(ui, state):
    s = ui.pc.SettingsPage(state)
    for w, t in ((s.rng, "8000-8010"), (s.remote_base, state.cfg.remote_base), (s.local_dir, state.cfg.local_dir),
                 (s.svcs, "sshd"), (s.psvc, "NodoraLab"), (s.pproc, ""), (s.rev, ""),
                 (s.timeout, "10"), (s.interval, "5"), (s.unit, "MiB/s")):
        w.text = w.currentText = (lambda t=t: t)
    for w in (s.tray, s.n1, s.n2, s.sw):
        w.isChecked = lambda: False
    s.save()
    assert os.path.exists(os.path.join(os.path.dirname(state.cfg.local_dir), "settings.json"))


def test_dialogs_construct(ui, state):
    state.lab.prepare_folder()
    ui.d.TempDialog(state.lab)
    ui.d.RevealedDialog(state.lab, lambda *a: None)
    ui.d.QComboBox = type("C", (_S,), {"currentData": lambda self: 1})
    dlg = ui.d.PortDrillDialog(state.lab)
    dlg.step1()
    assert dlg.drill is not None


def test_main_window_constructs_and_samples(ui, state):
    state.sample = state.hostkey_request = _S()
    ui.mw.run_async = lambda fn, ok=None, err=None: (ok(fn()) if ok else fn())
    w = ui.mw.MainWindow(state)
    w._sample(first=True)
    assert state.sysinfo and w._sampling is False
    w._refresh_top()
    w._alerts({"cpu": 95})
