"""Registro de actividad: local + remoto con cola de pendientes sin duplicados.

Distingue 'ejecutada' (el comando se completó) de 'verificada' (se comprobó el estado real)."""
from __future__ import annotations

import csv
import io
import json
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

FIELDS = ["op_id", "session_id", "student", "host", "timestamp", "timezone", "action",
          "params", "source", "destination", "result", "error", "evidence"]
RESULTS = ("ejecutada", "verificada", "error", "cancelada")
SENSITIVE = ("pass", "secret", "token", "key", "pwd", "credencial")


def _clean(params: dict | None) -> str:
    out = {}
    for k, v in (params or {}).items():
        out[k] = "***" if any(s in k.lower() for s in SENSITIVE) else v
    return json.dumps(out, ensure_ascii=False)


def now_iso() -> tuple[str, str]:
    n = datetime.now().astimezone()
    return n.isoformat(timespec="seconds"), (n.tzname() or time.tzname[0])


@dataclass
class Record:
    action: str
    result: str
    params: dict = field(default_factory=dict)
    source: str = ""
    destination: str = ""
    error: str = ""
    evidence: str = ""
    op_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    session_id: str = ""
    student: str = ""
    host: str = ""
    timestamp: str = ""
    timezone: str = ""

    def row(self) -> dict:
        d = asdict(self)
        d["params"] = _clean(self.params)
        return {k: d.get(k, "") for k in FIELDS}


def _to_csv(rows: list[dict], header: bool) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\r\n")
    if header:
        w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


class ActivityLog:
    def __init__(self, local_dir: str):
        self.dir = Path(local_dir) / "Historial"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.csv_path = self.dir / "actividad.csv"
        self.pending_path = self.dir / "pendientes.jsonl"
        self.session_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        self.student = ""
        self.host = ""
        self._lock = threading.Lock()

    # ---- escritura
    def add(self, rec: Record) -> Record:
        rec.session_id = rec.session_id or self.session_id
        rec.student = rec.student or self.student
        rec.host = rec.host or self.host
        rec.timestamp, rec.timezone = now_iso()
        assert rec.result in RESULTS, rec.result
        with self._lock:
            new = not self.csv_path.exists() or self.csv_path.stat().st_size == 0
            with open(self.csv_path, "a", encoding="utf-8", newline="") as f:
                f.write(_to_csv([rec.row()], new))
            with open(self.pending_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec.row(), ensure_ascii=False) + "\n")
        return rec

    # ---- lectura
    def all_rows(self) -> list[dict]:
        if not self.csv_path.exists():
            return []
        with open(self.csv_path, encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def pending(self) -> list[dict]:
        if not self.pending_path.exists():
            return []
        rows, seen = [], set()
        for line in self.pending_path.read_text("utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r["op_id"] not in seen:
                seen.add(r["op_id"])
                rows.append(r)
        return rows

    # ---- sincronización con BOSGAME (sin duplicados)
    def sync(self, session, remote_csv: str) -> tuple[int, int]:
        """Devuelve (enviadas, ya_existentes). Si falla, deja todo como pendiente."""
        pend = self.pending()
        if not pend:
            return 0, 0
        existing_ids: set[str] = set()
        has_file = bool(session.exists(remote_csv))
        if has_file:
            txt = session.read_text(remote_csv)
            existing_ids = {r.get("op_id") for r in csv.DictReader(io.StringIO(txt))}
        todo = [r for r in pend if r["op_id"] not in existing_ids]
        if todo:
            session.write_text(remote_csv, _to_csv(todo, header=not has_file),
                               append=has_file)
        # verificar escritura antes de limpiar pendientes
        txt = session.read_text(remote_csv)
        now_ids = {r.get("op_id") for r in csv.DictReader(io.StringIO(txt))}
        still = [r for r in pend if r["op_id"] not in now_ids]
        with self._lock:
            self.pending_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in still), "utf-8")
        return len(todo) - len(still), len(pend) - len(todo)
