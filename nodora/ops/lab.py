"""Operaciones del laboratorio (acciones 2 y 4-17, 20-25). Sin dependencias de interfaz.

Cada método ejecuta de verdad en el equipo remoto, comprueba el estado real y registra
la operación como 'ejecutada' o 'verificada'."""
from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

from ..core.activity import ActivityLog, Record
from ..core.config import APP_NAME, APP_VERSION, Settings
from ..core.profiles import profile_for
from ..core.session import RemoteError, RemoteSession, tcp_probe
from ..core.validators import (ValidationError, is_within, safe_join, validate_name,
                               validate_port_range, validate_revealed_path, validate_service_name,
                               validate_student_id)

SUBDIRS = ["Archivos", "Respaldos", "Restaurados", "Evidencias", "Informes", "Temporales"]


@dataclass
class Result:
    ok: bool
    message: str
    data: object = None
    verified: bool = False
    evidence: str = ""


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


class Lab:
    def __init__(self, session: RemoteSession, settings: Settings, log: ActivityLog):
        self.s, self.cfg, self.log = session, settings, log
        self.prof = profile_for(session.os_kind)
        self.sep = self.prof.sep
        self.sync_enabled = True
        self._tl = threading.local()

    @contextlib.contextmanager
    def quiet(self):
        """Lecturas automáticas del panel: no se registran (no son operaciones del estudiante)."""
        self._tl.quiet = True
        try:
            yield
        finally:
            self._tl.quiet = False

    # ------------------------------------------------------------------ utilidades
    @property
    def student_id(self) -> str:
        return validate_student_id(self.cfg.student_id)

    @property
    def base(self) -> str:
        """Carpeta personal remota (validada para no salir de remote_base)."""
        root = self.cfg.remote_base
        if self.s.os_kind == "linux" and re.match(r"^[A-Za-z]:", root):
            root = "/srv/laboratorio"
        return safe_join(root, self.student_id)

    def sub(self, name: str) -> str:
        return safe_join(self.base, name)

    def _rec(self, action: str, result: str, **kw) -> Record:
        if getattr(self._tl, "quiet", False):
            return Record(action=action, result=result)
        r = self.log.add(Record(action=action, result=result, **kw))
        if self.sync_enabled:
            self._try_sync()
        return r

    def _try_sync(self) -> None:
        try:
            if self.s.exists(self.base):
                self.log.sync(self.s, safe_join(self.base, "actividad.csv"))
        except Exception:  # noqa: BLE001 — queda pendiente y se sincroniza después
            pass

    def _fail(self, action: str, e: Exception, **kw) -> Result:
        self._rec(action, "error", error=str(e), **kw)
        return Result(False, str(e))

    def _run(self, cmd, timeout=60):
        return self.s.run(cmd.exec, timeout=timeout)

    def _require_base(self) -> None:
        if self.s.exists(self.base) is not True:
            raise ValidationError("Primero ejecute 'Preparar carpeta personal' (acción 4).")

    # ------------------------------------------------------------------ 2 identidad
    def identify(self, name: str, group: str, sid: str) -> Result:
        act = "2 Identificar al estudiante"
        try:
            name, group = name.strip(), group.strip()
            if len(name) < 3 or not group:
                raise ValidationError("Complete nombre completo y grupo.")
            sid = validate_student_id(sid)
            self.cfg.student_name, self.cfg.student_group, self.cfg.student_id = name, group, sid
            self.cfg.save()
            self.log.student = f"{name} ({sid})"
            txt = (f"Nombre: {name}\r\nGrupo: {group}\r\nIdentificador: {sid}\r\n"
                   f"Sesion: {self.log.session_id}\r\nEquipo: {self.s.host}\r\n"
                   f"Fecha: {datetime.now().astimezone().isoformat(timespec='seconds')}\r\n")
            os.makedirs(self.cfg.local_dir, exist_ok=True)
            with open(os.path.join(self.cfg.local_dir, "identificacion.txt"), "w", encoding="utf-8") as f:
                f.write(txt)
            remote = safe_join(self.base, "identificacion.txt")
            if self.s.exists(self.base) is not True:
                self._run(self.prof.make_dir(self.base))
            self.s.write_text(remote, txt)
            ok = self.s.read_text(remote) == txt
            self._rec(act, "verificada" if ok else "ejecutada", params={"id": sid, "grupo": group},
                      destination=remote, evidence=remote)
            return Result(ok, "identificacion.txt creado y verificado en BOSGAME." if ok else
                          "Archivo escrito pero la lectura posterior no coincide.", remote, ok, remote)
        except (ValidationError, RemoteError) as e:
            return self._fail(act, e)

    # ------------------------------------------------------------------ 4 carpeta personal
    def prepare_folder(self) -> Result:
        act = "4 Preparar la carpeta personal"
        try:
            base = self.base
            created, kept = [], []
            if self.s.exists(base) is not True:
                r = self._run(self.prof.make_dir(base))
                if not r.ok:
                    raise RemoteError(f"No se pudo crear {base}: {r.err.strip()[:200]}")
            for d in SUBDIRS:
                p = safe_join(base, d)
                if self.s.exists(p):
                    kept.append(d)
                else:
                    self.s.mkdir(p)
                    created.append(d)
            names = {e.name for e in self.s.listdir(base) if e.is_dir}
            missing = [d for d in SUBDIRS if d not in names]
            ok = not missing
            self._rec(act, "verificada" if ok else "ejecutada", params={"creadas": created, "existentes": kept},
                      destination=base)
            return Result(ok, (f"Carpeta lista en {base}. Creadas: {', '.join(created) or 'ninguna'}. "
                               f"Conservadas: {', '.join(kept) or 'ninguna'}.") if ok else
                          f"Faltan carpetas tras la creación: {missing}", base, ok)
        except (ValidationError, RemoteError) as e:
            return self._fail(act, e)

    # ------------------------------------------------------------------ 5-9 monitoreo
    def system_info(self) -> Result:
        act = "5 Consultar información del sistema"
        try:
            c = self.prof.sysinfo()
            r = self._run(c)
            if not r.ok:
                raise RemoteError(r.err.strip()[:200] or "Fallo al consultar el sistema.")
            d = self.prof.parse_sysinfo(r.out)
            d["_no_disponible"] = [k for k, v in d.items() if v in (None, "") and not k.startswith("_")]
            self._rec(act, "ejecutada", params={"comando": c.display[:120]})
            return Result(True, "Información obtenida.", d)
        except (RemoteError, ValueError) as e:
            return self._fail(act, e)

    def cpu(self) -> Result:
        act = "6 Consultar el uso de CPU"
        try:
            t0 = datetime.now().astimezone()
            r = self._run(self.prof.cpu(), 30)
            if not r.ok:
                raise RemoteError(r.err.strip()[:200] or "Fallo al leer la CPU.")
            v = self.prof.parse_cpu(r.out)
            d = {"percent": v, "at": t0.strftime("%H:%M:%S"), "interval_s": 1}
            self._rec(act, "ejecutada", params={"percent": v, "intervalo_s": 1})
            return Result(True, f"CPU {v:.1f} % (intervalo 1 s)", d)
        except (RemoteError, ValueError, IndexError) as e:
            return self._fail(act, e)

    def ram(self) -> Result:
        act = "7 Consultar el uso de RAM"
        try:
            r = self._run(self.prof.ram())
            if not r.ok:
                raise RemoteError(r.err.strip()[:200])
            d = self.prof.parse_ram(r.out)
            d["source"] = "Win32_OperatingSystem (CIM)" if self.s.os_kind == "windows" else "/proc/meminfo"
            self._rec(act, "ejecutada", params={"fuente": d["source"]})
            return Result(True, "RAM consultada.", d)
        except (RemoteError, ValueError, KeyError) as e:
            return self._fail(act, e)

    def storage(self) -> Result:
        act = "8 Consultar almacenamiento"
        try:
            r = self._run(self.prof.disks())
            if not r.ok:
                raise RemoteError(r.err.strip()[:200])
            d = self.prof.parse_disks(r.out)
            self._rec(act, "ejecutada", params={"unidades": [x["name"] for x in d]})
            return Result(True, f"{len(d)} unidad(es).", d)
        except (RemoteError, ValueError) as e:
            return self._fail(act, e)

    def processes(self, test_name: str = "") -> Result:
        act = "9 Consultar procesos"
        try:
            r = self._run(self.prof.processes())
            if not r.ok:
                raise RemoteError(r.err.strip()[:200])
            d = self.prof.parse_processes(r.out)
            found = [p for p in d if test_name and test_name.lower() in p["name"].lower()]
            self._rec(act, "verificada" if found else "ejecutada", params={"total": len(d), "buscado": test_name})
            return Result(True, f"{len(d)} procesos." + (f" Encontrado '{test_name}': PID {found[0]['pid']}." if found else ""),
                          {"processes": d, "found": found}, bool(found))
        except (RemoteError, ValueError) as e:
            return self._fail(act, e)

    # ------------------------------------------------------------------ 10-13 red y servicios
    def network(self) -> Result:
        act = "10 Consultar configuración de red"
        try:
            r = self._run(self.prof.network())
            if not r.ok:
                raise RemoteError(r.err.strip()[:200])
            d = self.prof.parse_network(r.out)
            self._rec(act, "ejecutada", params={"interfaces": len(d)})
            return Result(True, f"{len(d)} interfaz(ces).", d)
        except (RemoteError, ValueError) as e:
            return self._fail(act, e)

    def connectivity(self) -> Result:
        act = "11 Comprobar conectividad con BOSGAME"
        host, port = self.s.host, self.cfg.port
        out = {"icmp": None, "tcp": None}
        try:
            flag = ["-n", "1", "-w", "2000"] if sys.platform.startswith("win") else ["-c", "1", "-W", "2"]
            t0 = time.perf_counter()
            pr = subprocess.run(["ping", *flag, host], capture_output=True, text=True, timeout=6,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            m = re.search(r"(?:tiempo|time)[=<]\s*([\d.,]+)\s*ms", pr.stdout, re.I)
            out["icmp"] = {"ok": pr.returncode == 0 and bool(m),
                           "ms": float(m.group(1).replace(",", ".")) if m else None,
                           "text": "Respuesta" if pr.returncode == 0 else "Sin respuesta"}
        except (OSError, subprocess.SubprocessError):
            out["icmp"] = {"ok": False, "ms": None, "text": "Sin respuesta (ICMP no disponible o bloqueado)"}
        t0 = time.perf_counter()
        st = tcp_probe(host, port, 2.0)
        out["tcp"] = {"state": st, "ms": round((time.perf_counter() - t0) * 1000, 1) if st != "sin respuesta" else None}
        up = out["icmp"]["ok"] or st == "abierto"
        out["summary"] = ("Responde" if up else "Sin respuesta") + \
            ("" if up else " (un ping fallido no prueba que el equipo esté apagado)")
        self._rec(act, "verificada" if up else "ejecutada", params={"icmp": out["icmp"]["text"], "tcp": st})
        return Result(up, out["summary"], out, up)

    def scan_ports(self, range_text: str = "", progress: Callable[[int, int], None] | None = None,
                   cancel=None) -> Result:
        act = "12 Examinar puertos TCP autorizados"
        try:
            a, b = validate_port_range(range_text or self.cfg.lab_port_range)
            ports = list(range(a, b + 1))
            res: dict[int, str] = {}
            done = [0]

            def one(p):
                if cancel is not None and cancel.is_set():
                    return p, "cancelado"
                return p, tcp_probe(self.s.host, p, 1.0)

            with ThreadPoolExecutor(max_workers=32) as ex:
                for p, st in ex.map(one, ports):
                    res[p] = st
                    done[0] += 1
                    if progress:
                        progress(done[0], len(ports))
            opened = [p for p, s in res.items() if s == "abierto"]
            self._rec(act, "ejecutada", params={"rango": f"{a}-{b}", "abiertos": opened,
                                                "sin_respuesta": sum(v == "sin respuesta" for v in res.values())})
            return Result(True, f"Rango {a}-{b}: abiertos {opened or 'ninguno'}.", {"range": (a, b), "ports": res})
        except ValidationError as e:
            return self._fail(act, e)

    def services(self) -> Result:
        act = "13 Consultar servicios"
        try:
            names = [validate_service_name(n) for n in self.cfg.split_list(self.cfg.lab_services)]
            if not names:
                raise ValidationError("El docente no ha definido servicios (Configuración › Laboratorio).")
            r = self._run(self.prof.services(names))
            if not r.ok:
                raise RemoteError(r.err.strip()[:200])
            d = self.prof.parse_services(r.out)
            self._rec(act, "ejecutada", params={s["name"]: s["state"] for s in d})
            return Result(True, f"{len(d)} servicio(s).", d)
        except (ValidationError, RemoteError, ValueError) as e:
            return self._fail(act, e)

    # ------------------------------------------------------------------ 14 servicio de práctica
    def _service_state(self, name: str) -> str:
        r = self._run(self.prof.services([name]))
        return self.prof.parse_services(r.out)[0]["raw"] if r.ok else "Desconocido"

    def practice_service(self, action: str) -> Result:
        act = f"14 Administrar servicio de práctica ({action})"
        try:
            if action not in ("start", "stop", "restart"):
                raise ValidationError("Acción no permitida.")
            name = validate_service_name(self.cfg.practice_service)
            before = self._service_state(name)
            if before == "NotFound":
                raise ValidationError(f"El servicio de práctica '{name}' no existe en BOSGAME.")
            c = self.prof.service_action(name, action)
            r = self._run(c, 60)
            if not r.ok:
                low = (r.err + r.out).lower()
                hint = " Permisos insuficientes: use una cuenta administradora." if any(
                    w in low for w in ("denied", "acceso", "permission", "privileg", "sudo")) else ""
                raise RemoteError(f"No se pudo {action} el servicio: {r.err.strip()[:200]}{hint}")
            want = "Stopped" if action == "stop" else "Running"
            after = before
            for _ in range(15):
                after = self._service_state(name)
                if (after == want) or (want == "Stopped" and after in ("Stopped", "inactive", "failed")):
                    break
                time.sleep(1)
            ok = after == want or (want == "Stopped" and after in ("inactive", "failed"))
            self._rec(act, "verificada" if ok else "ejecutada",
                      params={"servicio": name, "antes": before, "despues": after})
            return Result(ok, f"{name}: {before} → {after}" + ("" if ok else " (no alcanzó el estado esperado)"),
                          {"before": before, "after": after, "command": c.display}, ok)
        except (ValidationError, RemoteError, ValueError) as e:
            return self._fail(act, e)

    # ------------------------------------------------------------------ 16-17 carpeta personal
    def explore(self, rel: str = "") -> Result:
        act = "16 Explorar la carpeta personal"
        try:
            self._require_base()
            path = safe_join(self.base, *([rel] if rel else []))
            if not is_within(self.base, path):
                raise ValidationError("La ruta sale de la carpeta personal.")
            ents = sorted(self.s.listdir(path), key=lambda e: (not e.is_dir, e.name.lower()))
            d = [{"name": e.name, "type": "Carpeta" if e.is_dir else "Archivo", "size": None if e.is_dir else e.size,
                  "mtime": e.mtime} for e in ents]
            self._rec(act, "ejecutada", params={"ruta": path, "elementos": len(d)}, source=path)
            return Result(True, path, {"path": path, "entries": d})
        except (ValidationError, RemoteError) as e:
            return self._fail(act, e)

    def make_subfolder(self, name: str, parent_rel: str = "") -> Result:
        act = "17 Crear una subcarpeta"
        try:
            self._require_base()
            name = validate_name(name)
            parent = safe_join(self.base, *([parent_rel] if parent_rel else []))
            path = safe_join(parent, name)
            if self.s.exists(path):
                self._rec(act, "ejecutada", params={"nombre": name, "resultado": "ya existía"}, destination=path)
                return Result(True, f"'{name}' ya existe; no se modificó su contenido.", path, True)
            self.s.mkdir(path)
            ok = self.s.exists(path) is True
            self._rec(act, "verificada" if ok else "ejecutada", destination=path)
            return Result(ok, f"Carpeta creada: {path}" if ok else "Se creó pero no se pudo comprobar.", path, ok)
        except (ValidationError, RemoteError) as e:
            return self._fail(act, e)

    # ------------------------------------------------------------------ 20 copia remota
    def unique_name(self, folder: str, name: str) -> str:
        stem, dot, ext = name.rpartition(".") if "." in name else (name, "", "")
        cand, n = name, 1
        while self.s.exists(safe_join(folder, cand)):
            n += 1
            cand = f"{stem} (copia {n}).{ext}" if dot else f"{name} (copia {n})"
        return cand

    def copy_file(self, src_rel: str, new_name: str = "") -> Result:
        act = "20 Copiar un archivo en BOSGAME"
        try:
            self._require_base()
            src = safe_join(self.base, src_rel)
            if self.s.exists(src) is not True:
                raise ValidationError("El archivo de origen no existe.")
            folder = src.rsplit(self.sep, 1)[0]
            base_name = src.rsplit(self.sep, 1)[1]
            if new_name:
                want = validate_name(new_name)
            else:
                stem, dot, ext = base_name.rpartition(".")
                want = f"{stem} - copia.{ext}" if dot else f"{base_name} - copia"
            final = self.unique_name(folder, want)
            dst = safe_join(folder, final)
            c = self.prof.copy(src, dst)
            r = self._run(c)
            if not r.ok:
                raise RemoteError(r.err.strip()[:200] or "La copia falló.")
            h1 = self.prof.parse_hash(self._run(self.prof.sha256(src)).out)
            h2 = self.prof.parse_hash(self._run(self.prof.sha256(dst)).out)
            ok = bool(h1) and h1 == h2 and self.s.exists(src) is True
            self._rec(act, "verificada" if ok else "ejecutada", source=src, destination=dst,
                      params={"sha256": h1[:16]})
            return Result(ok, f"Copia creada: {final}" + ("" if ok else " (suma distinta)"), dst, ok)
        except (ValidationError, RemoteError) as e:
            return self._fail(act, e)

    # ------------------------------------------------------------------ 21-22 respaldo
    def _manifest(self, folder: str, exclude: list[str]) -> list[dict]:
        r = self._run(self.prof.manifest(folder, exclude), 600)
        if not r.ok:
            raise RemoteError(f"No se pudo generar el manifiesto: {r.err.strip()[:200]}")
        return self.prof.parse_manifest(r.out)

    def create_backup(self) -> Result:
        act = "21 Crear un respaldo"
        try:
            self._require_base()
            ts = stamp()
            ext = self.prof.archive_ext()
            archive = safe_join(self.sub("Respaldos"), f"respaldo_{ts}{ext}")
            mani_path = safe_join(self.sub("Respaldos"), f"respaldo_{ts}.manifest.json")
            excl = ["Respaldos", "actividad.csv"]   # el historial vivo cambia durante el respaldo
            files = self._manifest(self.base, excl)
            if not files:
                raise ValidationError("No hay archivos que respaldar (la carpeta personal está vacía).")
            r = self._run(self.prof.backup(self.base, archive, excl), 900)
            if not r.ok:
                raise RemoteError(f"El respaldo falló: {r.err.strip()[:200]}")
            if self.s.exists(archive) is not True:
                raise RemoteError("El archivo de respaldo no apareció en BOSGAME.")
            ah = self.prof.parse_hash(self._run(self.prof.sha256(archive), 600).out)
            manifest = {"app": f"{APP_NAME} {APP_VERSION}", "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "sesion": self.log.session_id, "origen": self.base, "archivo": archive,
                        "sha256_archivo": ah, "tamano_archivo": self.s.stat_size(archive),
                        "excluido": excl, "archivos": files}
            self.s.write_text(mani_path, json.dumps(manifest, indent=2, ensure_ascii=False))
            ok = self.s.exists(mani_path) is True and bool(ah)
            self._rec(act, "verificada" if ok else "ejecutada", source=self.base, destination=archive,
                      params={"archivos": len(files)}, evidence=mani_path)
            return Result(ok, f"Respaldo creado con {len(files)} archivo(s).", {"archive": archive, "manifest": mani_path}, ok, mani_path)
        except (ValidationError, RemoteError, ValueError) as e:
            return self._fail(act, e)

    def list_backups(self) -> list[str]:
        try:
            return sorted((e.name for e in self.s.listdir(self.sub("Respaldos"))
                           if e.name.startswith("respaldo_") and e.name.endswith(self.prof.archive_ext())), reverse=True)
        except (RemoteError, ValidationError):
            return []

    def restore_backup(self, archive_name: str) -> Result:
        act = "22 Restaurar un respaldo"
        try:
            self._require_base()
            archive = safe_join(self.sub("Respaldos"), validate_name(archive_name))
            mani_path = archive[: -len(self.prof.archive_ext())] + ".manifest.json"
            if self.s.exists(archive) is not True or self.s.exists(mani_path) is not True:
                raise ValidationError("Falta el respaldo o su manifiesto.")
            mani = json.loads(self.s.read_text(mani_path))
            ah = self.prof.parse_hash(self._run(self.prof.sha256(archive), 600).out)
            if ah != mani["sha256_archivo"]:
                raise RemoteError("El respaldo está dañado: su suma SHA-256 no coincide con el manifiesto.")
            dest = safe_join(self.sub("Restaurados"), "restaurado_" + stamp())
            r = self._run(self.prof.restore(archive, dest), 900)
            if not r.ok:
                raise RemoteError(f"La restauración falló: {r.err.strip()[:200]}")
            got = {f["path"].replace("\\", "/"): f for f in self._manifest(dest, [])}
            bad, missing = [], []
            for f in mani["archivos"]:
                g = got.get(f["path"].replace("\\", "/"))
                if g is None:
                    missing.append(f["path"])
                elif g["sha256"] != f["sha256"] or g["size"] != f["size"]:
                    bad.append(f["path"])
            ok = not bad and not missing
            self._rec(act, "verificada" if ok else "error", source=archive, destination=dest,
                      params={"archivos": len(mani["archivos"]), "distintos": bad[:5], "faltantes": missing[:5]},
                      error="" if ok else "Comparación con el manifiesto fallida")
            return Result(ok, f"Restauración {'verificada' if ok else 'con diferencias'}: "
                              f"{len(mani['archivos']) - len(bad) - len(missing)}/{len(mani['archivos'])} idénticos.",
                          {"dest": dest, "bad": bad, "missing": missing}, ok)
        except (ValidationError, RemoteError, ValueError, KeyError) as e:
            return self._fail(act, e)

    # ------------------------------------------------------------------ 23 temporales
    def _walk(self, folder: str) -> list[tuple[str, int]]:
        out = []
        for e in self.s.listdir(folder):
            p = safe_join(folder, e.name)
            if e.is_dir:
                out += self._walk(p)
            else:
                out.append((p, e.size))
        return out

    def temp_candidates(self) -> Result:
        act = "23 Analizar temporales de práctica"
        try:
            self._require_base()
            files = self._walk(self.sub("Temporales"))
            total = sum(s for _, s in files)
            self._rec(act, "ejecutada", params={"candidatos": len(files), "bytes": total})
            return Result(True, f"{len(files)} archivo(s), {total} bytes.", [{"path": p, "size": s} for p, s in files])
        except (ValidationError, RemoteError) as e:
            return self._fail(act, e)

    def clean_temp(self, selected: list[str], confirmed: bool) -> Result:
        act = "23 Limpiar temporales de práctica"
        try:
            if not confirmed:
                raise ValidationError("Falta la confirmación explícita del borrado.")
            self._require_base()
            tmp = self.sub("Temporales")
            before = sum(s for _, s in self._walk(tmp))
            failed, deleted = [], []
            for p in selected:
                if not is_within(tmp, p) or p.rstrip("\\/") == tmp.rstrip("\\/"):
                    failed.append((p, "fuera de Temporales"))
                    continue
                try:
                    self.s.remove(p)
                    deleted.append(p)
                except RemoteError as e:
                    failed.append((p, str(e)))
            after = sum(s for _, s in self._walk(tmp))
            freed = before - after
            ok = not failed and all(self.s.exists(p) is False for p in deleted)
            self._rec(act, "verificada" if ok else "error", params={"borrados": len(deleted), "fallos": len(failed),
                                                                    "liberado_bytes": freed},
                      error="; ".join(f"{p}: {m}" for p, m in failed[:3]))
            return Result(ok, f"Borrados {len(deleted)}; fallos {len(failed)}; liberado {freed} bytes (medido).",
                          {"freed": freed, "failed": failed, "deleted": deleted}, ok)
        except (ValidationError, RemoteError) as e:
            return self._fail(act, e)

    # ------------------------------------------------------------------ 24 historial e informe
    def build_report(self) -> Result:
        act = "24 Guardar historial y generar el informe"
        try:
            rows = [r for r in self.log.all_rows() if r["session_id"] == self.log.session_id] or self.log.all_rows()[-200:]
            ver = sum(r["result"] == "verificada" for r in rows)
            err = [r for r in rows if r["result"] == "error"]
            nom = f"informe_{stamp()}.md"
            md = [f"# Informe {APP_NAME} {APP_VERSION}", "",
                  f"- **Estudiante:** {self.cfg.student_name} ({self.cfg.student_id}) — grupo {self.cfg.student_group}",
                  f"- **Equipo:** {self.s.host} ({self.s.os_kind})", f"- **Sesión:** {self.log.session_id}",
                  f"- **Generado:** {datetime.now().astimezone().isoformat(timespec='seconds')}",
                  f"- **Operaciones:** {len(rows)} (verificadas {ver}, con error {len(err)})", "",
                  "| Hora | Acción | Resultado | Evidencia / error |", "|---|---|---|---|"]
            for r in rows:
                md.append(f"| {r['timestamp'][11:19]} | {r['action']} | {r['result']} | {(r['evidence'] or r['error'])[:80]} |")
            md.append("\n> Ejecutada = el comando terminó. Verificada = se comprobó el estado real en BOSGAME.")
            text = "\n".join(md) + "\n"
            os.makedirs(os.path.join(self.cfg.local_dir, "Informes"), exist_ok=True)
            lp = os.path.join(self.cfg.local_dir, "Informes", nom)
            with open(lp, "w", encoding="utf-8") as f:
                f.write(text)
            rp = safe_join(self.sub("Informes"), nom)
            pending_note = ""
            try:
                self._require_base()
                self.s.write_text(rp, text)
                sent, dup = self.log.sync(self.s, safe_join(self.base, "actividad.csv"))
                pending_note = f" Historial sincronizado: {sent} nuevas, {dup} ya existían."
            except (RemoteError, ValidationError) as e:
                rp = ""
                pending_note = f" Escritura remota pendiente ({e}); {len(self.log.pending())} registro(s) en cola."
            self._rec(act, "verificada" if rp else "ejecutada", destination=rp or lp, evidence=lp)
            return Result(bool(rp), f"Informe local: {lp}.{pending_note}", {"local": lp, "remote": rp}, bool(rp), lp)
        except OSError as e:
            return self._fail(act, e)

    # ------------------------------------------------------------------ 25 ruta revelada
    def revealed_list(self, path: str) -> Result:
        act = "25 Recuperar archivo desde ruta revelada (listar)"
        try:
            p = validate_revealed_path(path)
            ents = self.s.listdir(p)
            files = [{"name": e.name, "size": e.size, "path": p.rstrip("\\/") + self.sep + e.name}
                     for e in ents if not e.is_dir]
            self._rec(act, "ejecutada", params={"archivos": len(files)}, source=p)
            return Result(True, f"{len(files)} archivo(s) en {p}.", {"path": p, "files": files})
        except (ValidationError, RemoteError) as e:
            return self._fail(act, e, source=path)

    # ------------------------------------------------------------------ evidencia genérica
    def save_evidence(self, name: str, payload: dict) -> str:
        """Guarda JSON en Evidencias (remoto) y en la carpeta local; devuelve la ruta remota."""
        text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        os.makedirs(os.path.join(self.cfg.local_dir, "Evidencias"), exist_ok=True)
        with open(os.path.join(self.cfg.local_dir, "Evidencias", name), "w", encoding="utf-8") as f:
            f.write(text)
        rp = safe_join(self.sub("Evidencias"), name)
        self.s.write_text(rp, text)
        return rp
