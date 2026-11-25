"""Acción 15: diagnosticar, cerrar y restaurar el puerto de práctica.

La aplicación NO elige la solución: ofrece un menú de plantillas controladas con parámetros
validados, muestra la instrucción real antes de ejecutarla y exige comprobar el cierre con
evidencia de la sesión remota (un timeout por sí solo no demuestra el cierre)."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..core.profiles import Cmd
from ..core.session import RemoteError, tcp_probe
from ..core.validators import (ValidationError, validate_port_range, validate_service_name)
from .lab import Lab

MENU = {
    1: ("Consultar puertos en escucha", "Mostrar puertos TCP locales y PID mediante la sesión remota", []),
    2: ("Consultar proceso o servicio", "Consultar el PID o nombre e identificar el responsable", ["pid_o_nombre"]),
    3: ("Detener servicio", "Detener únicamente el servicio de práctica autorizado", ["servicio"]),
    4: ("Terminar proceso", "Terminar únicamente el PID validado del proceso de práctica", ["pid"]),
    5: ("Restaurar servicio", "Iniciar nuevamente el servicio preparado y comprobarlo", ["servicio"]),
}


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class DrillState:
    started: str = ""
    initial: dict = field(default_factory=dict)
    port: Optional[int] = None
    pid: Optional[int] = None
    process: str = ""
    services: list = field(default_factory=list)
    instruction: str = ""
    output: str = ""
    rc: Optional[int] = None
    corrected: list = field(default_factory=list)       # Check
    restored: list = field(default_factory=list)        # Check
    evidence_remote: str = ""
    ready_for_next: bool = False


class PortDrill:
    def __init__(self, lab: Lab):
        self.lab = lab
        self.st = DrillState()
        self.range = validate_port_range(lab.cfg.lab_port_range)
        self._pending: Optional[tuple[int, Cmd, dict]] = None

    # ---- 1. estado inicial
    def start(self) -> dict:
        l = self.lab
        self.st = DrillState(started=datetime.now().astimezone().isoformat(timespec="seconds"))
        svc = validate_service_name(l.cfg.practice_service)
        self.st.initial = {"estudiante": l.cfg.student_name, "id": l.cfg.student_id, "sesion": l.log.session_id,
                           "equipo": l.s.host, "so": l.s.os_kind, "rango": f"{self.range[0]}-{self.range[1]}",
                           "servicio_practica": svc, "estado_servicio": l._service_state(svc),
                           "escucha": self.listening_in_range()}
        l._rec("15 Diagnóstico del puerto: estado inicial", "ejecutada",
               params={"rango": self.st.initial["rango"], "servicio": svc})
        return self.st.initial

    def listening_all(self) -> list[dict]:
        r = self.lab._run(self.lab.prof.listening(), 60)
        if not r.ok:
            raise RemoteError(f"No se pudo consultar los puertos en escucha: {r.err.strip()[:200]}")
        return self.lab.prof.parse_listening(r.out)

    def listening_in_range(self) -> list[dict]:
        a, b = self.range
        return [p for p in self.listening_all() if a <= p["port"] <= b]

    # ---- 2. explorar y relacionar
    def scan_and_correlate(self) -> dict:
        res = self.lab.scan_ports(f"{self.range[0]}-{self.range[1]}")
        ports = res.data["ports"] if res.ok else {}
        accepting = [p for p, s in ports.items() if s == "abierto"]
        listeners = {p["port"]: p for p in self.listening_in_range()}
        info = {"abiertos": accepting, "indeterminados": [p for p, s in ports.items() if s == "sin respuesta"],
                "relacion": []}
        for p in accepting:
            li = listeners.get(p)
            info["relacion"].append({"puerto": p, "pid": li["pid"] if li else None,
                                     "proceso": li["process"] if li else "",
                                     "servicios": li["services"] if li else []})
        if len(accepting) == 1 and listeners.get(accepting[0]):
            li = listeners[accepting[0]]
            self.st.port, self.st.pid, self.st.process, self.st.services = accepting[0], li["pid"], li["process"], li["services"]
        info["unico"] = len(accepting) == 1
        self.lab._rec("15 Diagnóstico del puerto: exploración", "verificada" if info["unico"] else "ejecutada",
                      params={"abiertos": accepting, "relacion": info["relacion"]})
        return info

    # ---- 3. menú: preparar (valida y devuelve la instrucción real) y ejecutar
    def prepare(self, option: int, **params) -> Cmd:
        l = self.lab
        if option not in MENU:
            raise ValidationError("Opción de menú no válida.")
        practice = validate_service_name(l.cfg.practice_service)
        if option == 1:
            cmd = l.prof.listening()
        elif option == 2:
            key = str(params.get("pid_o_nombre", "")).strip()
            if not key or len(key) > 80:
                raise ValidationError("Indique un PID o un nombre.")
            cmd = l.prof.listening()
            params["filtro"] = key
        elif option in (3, 5):
            name = validate_service_name(params.get("servicio", practice))
            if name.lower() != practice.lower():
                raise ValidationError(f"Solo se permite el servicio de práctica autorizado: {practice}.")
            cmd = l.prof.service_action(name, "stop" if option == 3 else "start")
        else:  # 4
            try:
                pid = int(str(params.get("pid", "")).strip())
            except ValueError:
                raise ValidationError("El PID debe ser un número.") from None
            if pid <= 4:
                raise ValidationError("PID no permitido.")
            a, b = self.range
            owner = [p for p in self.listening_in_range() if p["pid"] == pid]
            if not owner:
                raise ValidationError(f"El PID {pid} no escucha en el rango autorizado {a}-{b}.")
            want = l.cfg.practice_process.strip().lower()
            if want and not any(want in (p["process"] or "").lower() for p in owner):
                raise ValidationError(f"El PID {pid} no corresponde al proceso de práctica '{want}'.")
            cmd = l.prof.kill_pid(pid)
        self._pending = (option, cmd, params)
        return cmd

    def execute(self) -> tuple[int, str]:
        if not self._pending:
            raise ValidationError("Prepare una instrucción antes de ejecutarla.")
        option, cmd, params = self._pending
        self._pending = None
        r = self.lab.s.run(cmd.exec, timeout=60)
        out = (r.out + ("\n" + r.err if r.err.strip() else "")).strip()
        if option == 2:
            key = params["filtro"].lower()
            rows = [p for p in self.lab.prof.parse_listening(r.out)
                    if key in str(p["pid"]) or key in p["process"].lower() or any(key in s.lower() for s in p["services"])]
            out = "\n".join(f"puerto {p['port']}  PID {p['pid']}  {p['process']}  servicios: {', '.join(p['services']) or '-'}"
                            for p in rows) or "Sin coincidencias."
        elif option == 1:
            out = "\n".join(f"{p['addr']}:{p['port']}  PID {p['pid']}  {p['process']}" for p in
                            sorted(self.lab.prof.parse_listening(r.out), key=lambda x: x["port"]))
        if option in (3, 4):
            self.st.instruction, self.st.output, self.st.rc = cmd.display, out, r.rc
        self.lab._rec(f"15 Diagnóstico del puerto: {MENU[option][0]}", "ejecutada" if r.ok else "error",
                      params={"opcion": option, "rc": r.rc}, error="" if r.ok else out[:200])
        return r.rc, out

    # ---- 4. verificar el cierre
    def verify_closed(self) -> list[Check]:
        port, pid = self.st.port, self.st.pid
        if port is None:
            raise ValidationError("No hay un puerto identificado: ejecute la exploración primero.")
        checks = []
        now = self.listening_in_range()
        still = [p for p in now if p["port"] == port]
        checks.append(Check("El puerto ya no figura en escucha (consulta remota)", not still,
                            f"Sigue escuchando PID {still[0]['pid']}" if still else "Sin listener"))
        if still and still[0]["pid"] != pid:
            checks.append(Check("Reinicio automático detectado", False,
                                f"Un proceso nuevo (PID {still[0]['pid']}) volvió a abrir el puerto: "
                                "detenga el servicio de práctica con la opción 3."))
        probe = tcp_probe(self.lab.s.host, port, 2.0)
        checks.append(Check("Prueba de conexión TCP desde el cliente", probe == "rechazado",
                            {"rechazado": "Conexión rechazada (cierre confirmado)",
                             "abierto": "Aún acepta conexiones",
                             "sin respuesta": "Sin respuesta: indeterminado; por sí sola NO prueba el cierre"}[probe]))
        self.st.corrected = checks
        ok = all(c.passed for c in checks)
        self.lab._rec("15 Diagnóstico del puerto: verificación del cierre", "verificada" if ok else "error",
                      params={"puerto": port, "checks": [(c.name, c.passed) for c in checks]})
        return checks

    def save_correction_evidence(self) -> str:
        payload = {"tipo": "correccion", "inicial": self.st.initial, "puerto": self.st.port, "pid": self.st.pid,
                   "proceso": self.st.process, "instruccion": self.st.instruction, "salida": self.st.output,
                   "codigo_salida": self.st.rc,
                   "comprobaciones": [vars(c) for c in self.st.corrected]}
        self.st.evidence_remote = self.lab.save_evidence(f"puerto_correccion_{datetime.now():%Y%m%d_%H%M%S}.json", payload)
        self.lab._rec("15 Diagnóstico del puerto: evidencia de corrección", "verificada", evidence=self.st.evidence_remote)
        return self.st.evidence_remote

    # ---- 5. restaurar
    def verify_restored(self) -> list[Check]:
        l, svc = self.lab, validate_service_name(self.lab.cfg.practice_service)
        port = self.st.port
        checks = []
        state = "Desconocido"
        for _ in range(15):
            state = l._service_state(svc)
            if state == "Running":
                break
            time.sleep(1)
        checks.append(Check("Servicio de práctica activo", state == "Running", f"Estado: {state}"))
        probe = "sin respuesta"
        for _ in range(10):
            probe = tcp_probe(l.s.host, port, 1.5) if port else "sin respuesta"
            if probe == "abierto":
                break
            time.sleep(1)
        checks.append(Check("Puerto de práctica accesible", probe == "abierto", f"Prueba TCP: {probe}"))
        try:
            ssh_ok = l.s.run("echo ok", 10).ok
        except RemoteError:
            ssh_ok = False
        checks.append(Check("Administración remota disponible", ssh_ok, "Sesión SSH responde" if ssh_ok else "Sin respuesta"))
        self.st.restored = checks
        self.st.ready_for_next = all(c.passed for c in checks)
        try:
            payload = {"tipo": "restauracion", "servicio": svc, "puerto": port, "listo": self.st.ready_for_next,
                       "comprobaciones": [vars(c) for c in checks]}
            self.st.evidence_remote = l.save_evidence(f"puerto_restauracion_{datetime.now():%Y%m%d_%H%M%S}.json", payload)
        except (RemoteError, ValidationError):
            pass
        l._rec("15 Diagnóstico del puerto: restauración", "verificada" if self.st.ready_for_next else "error",
               params={"checks": [(c.name, c.passed) for c in checks]}, evidence=self.st.evidence_remote)
        return checks
