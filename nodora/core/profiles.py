"""Perfiles por sistema operativo remoto: construyen comandos y analizan su salida.

Windows -> PowerShell (siempre con -EncodedCommand). Linux -> sh/coreutils/systemd.
Cada comando devuelve `Cmd(display, exec)`: `display` es el texto legible que la interfaz
muestra ANTES de ejecutar (requisito de la acción 15); `exec` es lo que realmente se envía."""
from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass

from .session import ps_encode


@dataclass
class Cmd:
    display: str
    exec: str


def q_ps(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _json(text: str):
    text = text.strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except ValueError as e:
        raise ValueError(f"Respuesta remota no interpretable: {text[:120]!r}") from e


def _as_list(x):
    if x is None:
        return []
    return x if isinstance(x, list) else [x]


# ======================================================================= Windows
class WindowsProfile:
    kind = "windows"
    sep = "\\"

    @staticmethod
    def _c(script: str) -> Cmd:
        return Cmd(script, ps_encode(script))

    def sysinfo(self) -> Cmd:
        return self._c(
            "$os=Get-CimInstance Win32_OperatingSystem;$cs=Get-CimInstance Win32_ComputerSystem;"
            "$cpu=Get-CimInstance Win32_Processor|Select-Object -First 1;"
            "[pscustomobject]@{hostname=$env:COMPUTERNAME;os=$os.Caption;version=$os.Version;"
            "build=$os.BuildNumber;arch=$os.OSArchitecture;cpu=$cpu.Name.Trim();cores=$cpu.NumberOfCores;"
            "threads=$cpu.NumberOfLogicalProcessors;ram_total=[int64]$cs.TotalPhysicalMemory;"
            "uptime_s=[int]((Get-Date)-$os.LastBootUpTime).TotalSeconds}|ConvertTo-Json -Compress")

    def parse_sysinfo(self, out: str) -> dict:
        d = _json(out)
        return {"hostname": d.get("hostname"), "os": f'{d.get("os")} (build {d.get("build")})',
                "version": d.get("version"), "arch": d.get("arch"), "cpu": d.get("cpu"),
                "cores": d.get("cores"), "threads": d.get("threads"),
                "ram_total": d.get("ram_total"), "uptime_s": d.get("uptime_s")}

    def cpu(self) -> Cmd:
        # Dos lecturas separadas 1 s: intervalo de medición definido, independiente del idioma
        return self._c(
            "$q={(Get-CimInstance Win32_PerfFormattedData_PerfOS_Processor -Filter \"Name='_Total'\")"
            ".PercentProcessorTime};$null=& $q;Start-Sleep -Seconds 1;& $q")

    def parse_cpu(self, out: str) -> float:
        return float(out.strip().splitlines()[-1].replace(",", "."))

    def ram(self) -> Cmd:
        return self._c("$o=Get-CimInstance Win32_OperatingSystem;"
                       "[pscustomobject]@{total=[int64]$o.TotalVisibleMemorySize*1024;"
                       "free=[int64]$o.FreePhysicalMemory*1024}|ConvertTo-Json -Compress")

    def parse_ram(self, out: str) -> dict:
        d = _json(out)
        return {"total": int(d["total"]), "free": int(d["free"]), "used": int(d["total"]) - int(d["free"])}

    def disks(self) -> Cmd:
        return self._c("$r=Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3'|ForEach-Object{"
                       "[pscustomobject]@{name=$_.DeviceID;label=$_.VolumeName;size=[int64]$_.Size;"
                       "free=[int64]$_.FreeSpace}};ConvertTo-Json -InputObject @($r) -Compress")

    def parse_disks(self, out: str) -> list[dict]:
        return [{"name": d["name"], "label": d.get("label") or "", "size": int(d["size"] or 0),
                 "free": int(d["free"] or 0), "used": int(d["size"] or 0) - int(d["free"] or 0)}
                for d in _as_list(_json(out))]

    def processes(self, limit: int = 60) -> Cmd:
        return self._c(f"$r=Get-Process|Sort-Object WorkingSet64 -Descending|Select-Object -First {limit}|"
                       "ForEach-Object{[pscustomobject]@{pid=$_.Id;name=$_.ProcessName;"
                       "mem=[int64]$_.WorkingSet64;cpu_s=[double]$_.CPU}};"
                       "ConvertTo-Json -InputObject @($r) -Compress")

    def parse_processes(self, out: str) -> list[dict]:
        return [{"pid": int(p["pid"]), "name": p["name"], "mem": int(p["mem"] or 0),
                 "cpu": (None if p.get("cpu_s") is None else float(p["cpu_s"])), "cpu_unit": "s"}
                for p in _as_list(_json(out))]

    def network(self) -> Cmd:
        return self._c(
            "$r=foreach($c in Get-NetIPConfiguration){$a=Get-NetAdapter -InterfaceIndex $c.InterfaceIndex "
            "-ErrorAction SilentlyContinue;[pscustomobject]@{name=$c.InterfaceAlias;mac=$a.MacAddress;"
            "ipv4=@($c.IPv4Address|ForEach-Object{$_.IPAddress});prefix=@($c.IPv4Address|ForEach-Object{$_.PrefixLength});"
            "gateway=@($c.IPv4DefaultGateway|ForEach-Object{$_.NextHop});"
            "dns=@($c.DNSServer|ForEach-Object{$_.ServerAddresses})}};"
            "ConvertTo-Json -InputObject @($r) -Compress -Depth 4")

    def parse_network(self, out: str) -> list[dict]:
        res = []
        for n in _as_list(_json(out)):
            res.append({"name": n.get("name") or "", "mac": (n.get("mac") or "").replace("-", ":"),
                        "ipv4": _as_list(n.get("ipv4")), "prefix": _as_list(n.get("prefix")),
                        "gateway": _as_list(n.get("gateway")), "dns": _as_list(n.get("dns"))})
        return res

    def services(self, names: list[str]) -> Cmd:
        arr = ",".join(q_ps(n) for n in names)
        return self._c(f"$r=foreach($n in @({arr})){{$s=Get-Service -Name $n -ErrorAction SilentlyContinue;"
                       "if($s){[pscustomobject]@{name=$n;display=$s.DisplayName;state=[string]$s.Status;"
                       "start=[string]$s.StartType}}else{[pscustomobject]@{name=$n;display='';"
                       "state='NotFound';start=''}}};ConvertTo-Json -InputObject @($r) -Compress")

    def parse_services(self, out: str) -> list[dict]:
        m = {"Running": "Activo", "Stopped": "Detenido", "NotFound": "No encontrado",
             "Paused": "Pausado", "StartPending": "Iniciando", "StopPending": "Deteniendo"}
        return [{"name": s["name"], "display": s.get("display") or "",
                 "state": m.get(s["state"], s["state"]), "raw": s["state"], "start": s.get("start") or ""}
                for s in _as_list(_json(out))]

    def service_action(self, name: str, action: str) -> Cmd:
        verb = {"start": "Start-Service", "stop": "Stop-Service", "restart": "Restart-Service"}[action]
        return self._c(f"{verb} -Name {q_ps(name)} -ErrorAction Stop")

    def listening(self) -> Cmd:
        return self._c(
            "$svc=@{};Get-CimInstance Win32_Service|Where-Object{$_.ProcessId -gt 0}|ForEach-Object{"
            "$svc[[int]$_.ProcessId]+=@($_.Name)};$r=Get-NetTCPConnection -State Listen|ForEach-Object{"
            "$p=Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue;[pscustomobject]@{"
            "port=$_.LocalPort;addr=$_.LocalAddress;pid=$_.OwningProcess;process=$p.ProcessName;"
            "services=@($svc[[int]$_.OwningProcess])}};ConvertTo-Json -InputObject @($r) -Compress")

    def parse_listening(self, out: str, session=None) -> list[dict]:
        return [{"port": int(p["port"]), "addr": p["addr"], "pid": int(p["pid"]),
                 "process": p.get("process") or "", "services": [s for s in _as_list(p.get("services")) if s]}
                for p in _as_list(_json(out))]

    def kill_pid(self, pid: int) -> Cmd:
        return self._c(f"Stop-Process -Id {int(pid)} -Force -ErrorAction Stop")

    # ---- archivos
    def sha256(self, path: str) -> Cmd:
        return self._c(f"(Get-FileHash -LiteralPath {q_ps(path)} -Algorithm SHA256).Hash.ToLower()")

    def parse_hash(self, out: str) -> str:
        return out.strip().lower()

    def copy(self, src: str, dst: str) -> Cmd:
        return self._c(f"Copy-Item -LiteralPath {q_ps(src)} -Destination {q_ps(dst)} -ErrorAction Stop")

    def manifest(self, base: str, exclude_top: list[str]) -> Cmd:
        ex = ",".join(q_ps(e) for e in exclude_top) or "''"
        return self._c(
            f"$b=(Resolve-Path -LiteralPath {q_ps(base)}).Path.TrimEnd('\\');$ex=@({ex});"
            "$r=Get-ChildItem -LiteralPath $b -Recurse -File -Force|Where-Object{"
            "$rel=$_.FullName.Substring($b.Length+1);$top=$rel.Split('\\')[0];$ex -notcontains $top}|"
            "ForEach-Object{[pscustomobject]@{path=$_.FullName.Substring($b.Length+1).Replace('\\','/');"
            "size=[int64]$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()}};"
            "ConvertTo-Json -InputObject @($r) -Compress")

    def parse_manifest(self, out: str) -> list[dict]:
        return [{"path": f["path"], "size": int(f["size"]), "sha256": f["sha256"]} for f in _as_list(_json(out))]

    def backup(self, base: str, archive: str, exclude_top: list[str]) -> Cmd:
        ex = ",".join(q_ps(e) for e in exclude_top) or "''"
        return self._c(
            f"$ex=@({ex});$items=@(Get-ChildItem -LiteralPath {q_ps(base)} -Force|Where-Object{{$ex -notcontains $_.Name}});"
            "if($items.Count -eq 0){Write-Error 'NADA_QUE_RESPALDAR';exit 3};"
            f"Compress-Archive -LiteralPath $items.FullName -DestinationPath {q_ps(archive)} -ErrorAction Stop")

    def restore(self, archive: str, dest: str) -> Cmd:
        return self._c(f"Expand-Archive -LiteralPath {q_ps(archive)} -DestinationPath {q_ps(dest)} -ErrorAction Stop")

    def archive_ext(self) -> str:
        return ".zip"

    def make_dir(self, path: str) -> Cmd:
        return self._c(f"New-Item -ItemType Directory -Force -Path {q_ps(path)}|Out-Null")

    # ---- tráfico y captura (acciones 26 y 27)
    def net_counters(self) -> Cmd:
        return self._c("$r=Get-NetAdapterStatistics|ForEach-Object{[pscustomobject]@{name=$_.Name;"
                       "rx=[int64]$_.ReceivedBytes;tx=[int64]$_.SentBytes}};"
                       "ConvertTo-Json -InputObject @($r) -Compress")

    def parse_net_counters(self, out: str) -> dict:
        return {n["name"]: (int(n["rx"] or 0), int(n["tx"] or 0)) for n in _as_list(_json(out))}

    def connections(self) -> Cmd:
        return self._c("$r=Get-NetTCPConnection -State Established|ForEach-Object{"
                       "$p=Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue;[pscustomobject]@{"
                       "laddr=$_.LocalAddress;lport=$_.LocalPort;raddr=$_.RemoteAddress;rport=$_.RemotePort;"
                       "pid=$_.OwningProcess;process=$p.ProcessName}};ConvertTo-Json -InputObject @($r) -Compress")

    def parse_connections(self, out: str) -> list[dict]:
        return [{"local": f"{c['laddr']}:{c['lport']}", "remote": f"{c['raddr']}:{c['rport']}",
                 "pid": int(c["pid"] or 0), "process": c.get("process") or ""} for c in _as_list(_json(out))]

    def capture(self, etl: str, pcap: str, seconds: int, proto: str, port, host) -> Cmd:
        """pktmon (incluido en Windows 10 1809+/11; requiere administrador). La sintaxis de pktmon
        cambia entre versiones: si falla, el mensaje de error se muestra tal cual."""
        f = ""
        if proto != "any" or port or host:
            args = ["filter", "add", "NODORA"]
            if proto != "any":
                args += ["-t", proto.upper()]
            if port:
                args += ["-p", str(int(port))]
            if host:
                args += ["-i", host]
            f = "pktmon " + " ".join(args) + "|Out-Null;"
        return self._c(
            "pktmon stop|Out-Null;pktmon filter remove|Out-Null;"
            f"{f}pktmon start --capture --pkt-size 128 --file-size 32 --file-name {q_ps(etl)}|Out-Null;"
            "if($LASTEXITCODE -ne 0){Write-Error 'PKTMON_NO_INICIO (¿cuenta administradora?)';exit 5};"
            f"Start-Sleep -Seconds {int(seconds)};pktmon stop|Out-Null;"
            f"pktmon etl2pcap {q_ps(etl)} --out {q_ps(pcap)}|Out-Null;"
            f"if(-not(Test-Path -LiteralPath {q_ps(pcap)})){{Write-Error 'CAPTURA_NO_GENERADA';exit 4}}")

    def capture_ext(self) -> str:
        return ".pcapng"


# ======================================================================= Linux
class LinuxProfile:
    kind = "linux"
    sep = "/"

    @staticmethod
    def _c(script: str) -> Cmd:
        return Cmd(script, script)

    def _priv(self, cmd: str) -> str:
        return f'if [ "$(id -u)" -eq 0 ]; then {cmd}; else sudo -n {cmd}; fi'

    def sysinfo(self) -> Cmd:
        return self._c("echo HOST=$(hostname); . /etc/os-release 2>/dev/null; echo OS=$PRETTY_NAME; "
                       "echo KERNEL=$(uname -r); echo ARCH=$(uname -m); "
                       "echo CPU=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | sed 's/^ //'); "
                       "echo THREADS=$(nproc); echo CORES=$(lscpu -p=core 2>/dev/null | grep -v '^#' | sort -u | wc -l); "
                       "echo MEMKB=$(awk '/MemTotal/{print $2}' /proc/meminfo); "
                       "echo UPTIME=$(cut -d. -f1 /proc/uptime)")

    def parse_sysinfo(self, out: str) -> dict:
        d = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
        return {"hostname": d.get("HOST"), "os": d.get("OS") or None, "version": d.get("KERNEL"),
                "arch": d.get("ARCH"), "cpu": d.get("CPU") or None,
                "cores": int(d["CORES"]) if d.get("CORES", "").isdigit() and int(d["CORES"]) else None,
                "threads": int(d["THREADS"]) if d.get("THREADS", "").isdigit() else None,
                "ram_total": int(d["MEMKB"]) * 1024 if d.get("MEMKB", "").isdigit() else None,
                "uptime_s": int(d["UPTIME"]) if d.get("UPTIME", "").isdigit() else None}

    def cpu(self) -> Cmd:
        return self._c("head -1 /proc/stat; sleep 1; head -1 /proc/stat")

    def parse_cpu(self, out: str) -> float:
        rows = [list(map(int, l.split()[1:])) for l in out.strip().splitlines() if l.startswith("cpu")]
        a, b = rows[0], rows[-1]
        idle = (b[3] + (b[4] if len(b) > 4 else 0)) - (a[3] + (a[4] if len(a) > 4 else 0))
        total = sum(b) - sum(a)
        return round(100.0 * (1 - idle / total), 1) if total > 0 else 0.0

    def ram(self) -> Cmd:
        return self._c("awk '/MemTotal|MemAvailable/{print $1,$2}' /proc/meminfo")

    def parse_ram(self, out: str) -> dict:
        d = {l.split()[0].rstrip(":"): int(l.split()[1]) * 1024 for l in out.splitlines() if l.strip()}
        return {"total": d["MemTotal"], "free": d["MemAvailable"], "used": d["MemTotal"] - d["MemAvailable"]}

    def disks(self) -> Cmd:
        return self._c("df -PB1 -x tmpfs -x devtmpfs -x squashfs -x overlay -x efivarfs 2>/dev/null | tail -n +2")

    def parse_disks(self, out: str) -> list[dict]:
        res = []
        for l in out.splitlines():
            p = l.split()
            if len(p) >= 6:
                res.append({"name": p[5], "label": p[0], "size": int(p[1]), "used": int(p[2]), "free": int(p[3])})
        return res

    def processes(self, limit: int = 60) -> Cmd:
        return self._c(f"ps -eo pid=,comm=,%cpu=,rss= --sort=-rss | head -n {limit}")

    def parse_processes(self, out: str) -> list[dict]:
        res = []
        for l in out.splitlines():
            p = l.split(None, 3)
            if len(p) == 4:
                res.append({"pid": int(p[0]), "name": p[1], "cpu": float(p[2]), "cpu_unit": "%",
                            "mem": int(p[3]) * 1024})
        return res

    def network(self) -> Cmd:
        return self._c("echo '##ADDR'; ip -j addr; echo '##ROUTE'; ip -j route; echo '##DNS'; "
                       "(resolvectl dns 2>/dev/null | sed 's/.*: //' ; grep '^nameserver' /etc/resolv.conf | awk '{print $2}') | tr ' ' '\\n' | sort -u")

    def parse_network(self, out: str) -> list[dict]:
        parts = re.split(r"^##(ADDR|ROUTE|DNS)\s*$", out, flags=re.M)
        sec = {parts[i]: parts[i + 1] for i in range(1, len(parts) - 1, 2)}
        addrs, routes = _as_list(_json(sec.get("ADDR", ""))), _as_list(_json(sec.get("ROUTE", "")))
        dns = [l.strip() for l in sec.get("DNS", "").splitlines() if re.match(r"^[\d.:a-fA-F]+$", l.strip())]
        gw = {r.get("dev"): r.get("gateway") for r in routes if r.get("dst") == "default"}
        res = []
        for a in addrs:
            if a.get("ifname") == "lo":
                continue
            v4 = [i for i in a.get("addr_info", []) if i.get("family") == "inet"]
            res.append({"name": a["ifname"], "mac": a.get("address", ""), "ipv4": [i["local"] for i in v4],
                        "prefix": [i["prefixlen"] for i in v4], "gateway": [gw[a["ifname"]]] if gw.get(a["ifname"]) else [],
                        "dns": dns})
        return res

    def services(self, names: list[str]) -> Cmd:
        parts = []
        for n in names:
            u = shlex.quote(n if "." in n else n + ".service")
            parts.append(f"echo '##{n}'; systemctl show {u} -p LoadState -p ActiveState -p UnitFileState -p Description 2>&1")
        return self._c("; ".join(parts))

    def parse_services(self, out: str) -> list[dict]:
        res = []
        for blk in re.split(r"^##", out, flags=re.M)[1:]:
            name, _, body = blk.partition("\n")
            d = dict(l.split("=", 1) for l in body.splitlines() if "=" in l)
            if d.get("LoadState") == "not-found" or not d:
                state, raw = "No encontrado", "NotFound"
            else:
                raw = d.get("ActiveState", "")
                state = {"active": "Activo", "inactive": "Detenido", "failed": "Fallido",
                         "activating": "Iniciando", "deactivating": "Deteniendo"}.get(raw, raw)
            res.append({"name": name.strip(), "display": d.get("Description", ""), "state": state,
                        "raw": "Running" if raw == "active" else raw, "start": d.get("UnitFileState", "")})
        return res

    def service_action(self, name: str, action: str) -> Cmd:
        u = shlex.quote(name if "." in name else name + ".service")
        return self._c(self._priv(f"systemctl {action} {u}"))

    def listening(self) -> Cmd:
        return self._c("ss -ltnpH; echo '##UNITS'; for p in $(ss -ltnpH | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u); do "
                       "echo \"$p $(grep -o '[^/]*\\.service' /proc/$p/cgroup 2>/dev/null | tail -1)\"; done")

    def parse_listening(self, out: str, session=None) -> list[dict]:
        main, _, units = out.partition("##UNITS")
        unit = {}
        for l in units.splitlines():
            p = l.split()
            if len(p) == 2:
                unit[int(p[0])] = p[1].removesuffix(".service")
        res = []
        for l in main.splitlines():
            p = l.split()
            if len(p) < 5 or p[0] != "LISTEN":
                continue
            addr, _, port = p[3].rpartition(":")
            m = re.search(r'\("([^"]+)",pid=(\d+)', l)
            pid = int(m.group(2)) if m else 0
            res.append({"port": int(port), "addr": addr.strip("[]"), "pid": pid,
                        "process": m.group(1) if m else "", "services": [unit[pid]] if pid in unit else []})
        return res

    def kill_pid(self, pid: int) -> Cmd:
        return self._c(self._priv(f"kill {int(pid)}"))

    def sha256(self, path: str) -> Cmd:
        return self._c(f"sha256sum -- {shlex.quote(path)} | cut -d' ' -f1")

    def parse_hash(self, out: str) -> str:
        return out.strip().lower()

    def copy(self, src: str, dst: str) -> Cmd:
        return self._c(f"cp -n -- {shlex.quote(src)} {shlex.quote(dst)}")

    def manifest(self, base: str, exclude_top: list[str]) -> Cmd:
        pr = " ".join(f"! -path {shlex.quote('./' + e)} ! -path {shlex.quote('./' + e + '/*')}" for e in exclude_top)
        return self._c(f"cd {shlex.quote(base)} && find . -type f {pr} -exec sh -c 'for f; do printf \"%s\\t%s\\t%s\\n\" "
                       "\"$(sha256sum \"$f\"|cut -d\" \" -f1)\" \"$(stat -c %s \"$f\")\" \"${f#./}\"; done' _ {} +")

    def parse_manifest(self, out: str) -> list[dict]:
        res = []
        for l in out.splitlines():
            p = l.split("\t")
            if len(p) == 3:
                res.append({"path": p[2], "size": int(p[1]), "sha256": p[0]})
        return res

    def backup(self, base: str, archive: str, exclude_top: list[str]) -> Cmd:
        ex = " ".join(f"--exclude={shlex.quote('./' + e)}" for e in exclude_top)
        return self._c(f"tar -czf {shlex.quote(archive)} {ex} -C {shlex.quote(base)} .")

    def restore(self, archive: str, dest: str) -> Cmd:
        return self._c(f"mkdir -p {shlex.quote(dest)} && tar -xzf {shlex.quote(archive)} -C {shlex.quote(dest)}")

    def archive_ext(self) -> str:
        return ".tar.gz"

    def make_dir(self, path: str) -> Cmd:
        return self._c(f"mkdir -p {shlex.quote(path)}")

    # ---- tráfico y captura (acciones 26 y 27)
    def net_counters(self) -> Cmd:
        return self._c("cat /proc/net/dev")

    def parse_net_counters(self, out: str) -> dict:
        res = {}
        for l in out.splitlines():
            if ":" not in l:
                continue
            name, _, rest = l.partition(":")
            f = rest.split()
            if len(f) >= 9 and f[0].isdigit():
                res[name.strip()] = (int(f[0]), int(f[8]))
        return res

    def connections(self) -> Cmd:
        return self._c("ss -tnpH state established")

    def parse_connections(self, out: str) -> list[dict]:
        res = []
        for l in out.splitlines():
            p = l.split()
            if p and not p[0].isdigit():      # algunas versiones de ss anteponen la columna de estado (ESTAB)
                p = p[1:]
            if len(p) >= 4:
                m = re.search(r'\("([^"]+)",pid=(\d+)', l)
                res.append({"local": p[2], "remote": p[3], "pid": int(m.group(2)) if m else 0,
                            "process": m.group(1) if m else ""})
        return res

    def capture(self, etl: str, pcap: str, seconds: int, proto: str, port, host, max_packets: int = 2000) -> Cmd:
        parts = []
        if proto != "any":
            parts.append(proto)
        if host:
            parts.append(f"host {host}")
        if port:
            parts.append(f"port {int(port)}")
        bpf = " and ".join(parts)
        # `timeout` devuelve 124 al cumplirse el tiempo: es el final normal de una captura temporizada
        cmd = (f"timeout {int(seconds)} tcpdump -i any -n -Z root -s 128 -c {int(max_packets)} -w {shlex.quote(pcap)}"
               + (f" {shlex.quote(bpf)}" if bpf else ""))
        return self._c(self._priv(cmd))

    def capture_ext(self) -> str:
        return ".pcap"


def profile_for(kind: str):
    return WindowsProfile() if kind == "windows" else LinuxProfile()
