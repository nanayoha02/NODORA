"""Validaciones de entradas: identificadores, nombres, rutas remotas y rangos de puertos.

Todas las rutas remotas se normalizan de forma PURA (sin tocar el disco local) con
ntpath / posixpath, para que el cliente Windows valide igual rutas Windows y Linux.
"""
from __future__ import annotations

import ntpath
import posixpath
import re
import socket

ID_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")
NAME_RE = re.compile(r"^[A-Za-z0-9 ._()\-áéíóúÁÉÍÓÚñÑ]{1,100}$")
HOST_RE = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.\-]{0,251}[A-Za-z0-9])?$")
SERVICE_RE = re.compile(r"^[A-Za-z0-9_.@\-]{1,80}$")
WIN_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}


class ValidationError(ValueError):
    """Entrada inválida (mensaje apto para mostrar al usuario)."""


def validate_student_id(value: str) -> str:
    v = (value or "").strip()
    if not ID_RE.match(v):
        raise ValidationError(
            "Identificador inválido: use 2-32 caracteres (letras, números, guion o guion bajo). "
            "No se admiten separadores de ruta ni '..'.")
    if v.upper() in WIN_RESERVED:
        raise ValidationError("Identificador reservado por Windows.")
    return v


def validate_host(value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValidationError("Indique la dirección IP o el nombre del equipo.")
    try:
        socket.inet_pton(socket.AF_INET, v)
        return v
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, v)
        return v
    except OSError:
        pass
    if not HOST_RE.match(v):
        raise ValidationError("Dirección o nombre de equipo no válido.")
    return v


def validate_port(value) -> int:
    try:
        p = int(str(value).strip())
    except ValueError:
        raise ValidationError("El puerto debe ser un número.") from None
    if not 1 <= p <= 65535:
        raise ValidationError("El puerto debe estar entre 1 y 65535.")
    return p


def validate_port_range(text: str) -> tuple[int, int]:
    """Acepta '8000-8010' o '8080'. Devuelve (inicio, fin)."""
    t = (text or "").strip()
    m = re.fullmatch(r"(\d{1,5})(?:\s*-\s*(\d{1,5}))?", t)
    if not m:
        raise ValidationError("Rango de puertos inválido. Ejemplo: 8000-8010.")
    a = validate_port(m.group(1))
    b = validate_port(m.group(2) or m.group(1))
    if a > b:
        raise ValidationError("El inicio del rango no puede ser mayor que el final.")
    if b - a > 1024:
        raise ValidationError("El rango autorizado no puede superar 1025 puertos.")
    return a, b


def validate_name(value: str) -> str:
    """Nombre de archivo o subcarpeta simple (sin separadores)."""
    v = (value or "").strip()
    if not v or not NAME_RE.match(v):
        raise ValidationError("Nombre inválido: use letras, números, espacios, punto, guion o guion bajo.")
    if v in {".", ".."} or v.endswith(".") or v.endswith(" "):
        raise ValidationError("El nombre no puede ser '.', '..' ni terminar en punto o espacio.")
    if v.split(".")[0].upper() in WIN_RESERVED:
        raise ValidationError("Nombre reservado por Windows.")
    return v


def validate_service_name(value: str) -> str:
    v = (value or "").strip()
    if not SERVICE_RE.match(v):
        raise ValidationError("Nombre de servicio inválido.")
    return v


def _flavor(path: str):
    return ntpath if (re.match(r"^[A-Za-z]:", path) or "\\" in path) else posixpath


def is_windows_path(path: str) -> bool:
    return _flavor(path) is ntpath


def normalize_remote(path: str) -> str:
    mod = _flavor(path)
    return mod.normpath(path)


def safe_join(base: str, *parts: str) -> str:
    """Une `parts` a `base` y garantiza que el resultado NO salga de `base`."""
    mod = _flavor(base)
    base_n = mod.normpath(base)
    for p in parts:
        if "\x00" in p:
            raise ValidationError("Ruta con caracteres no válidos.")
        if mod is ntpath and (ntpath.isabs(p) or re.match(r"^[A-Za-z]:", p) or p.startswith(("\\", "/"))):
            raise ValidationError("No se admiten rutas absolutas dentro de la carpeta personal.")
        if mod is posixpath and p.startswith("/"):
            raise ValidationError("No se admiten rutas absolutas dentro de la carpeta personal.")
    joined = mod.normpath(mod.join(base_n, *[p.replace("/", mod.sep) if mod is ntpath else p for p in parts]))
    if not is_within(base_n, joined):
        raise ValidationError("La ruta sale de la carpeta personal asignada.")
    return joined


def is_within(base: str, path: str) -> bool:
    mod = _flavor(base)
    b = mod.normcase(mod.normpath(base)).rstrip("\\/")
    p = mod.normcase(mod.normpath(path)).rstrip("\\/")
    return p == b or p.startswith(b + mod.sep)


def to_sftp_path(path: str) -> str:
    """C:\\Laboratorio\\X -> /C:/Laboratorio/X (formato de OpenSSH para Windows)."""
    if is_windows_path(path):
        p = path.replace("\\", "/")
        return p if p.startswith("/") else "/" + p
    return path


def from_sftp_path(path: str) -> str:
    m = re.match(r"^/([A-Za-z]:.*)$", path)
    return m.group(1).replace("/", "\\") if m else path


def validate_revealed_path(path: str) -> str:
    """Ruta entregada por el docente (acción 25): admite espacios; rechaza NUL y vacíos."""
    p = (path or "").strip().strip('"')
    if not p or "\x00" in p:
        raise ValidationError("Ruta vacía o con caracteres no válidos.")
    if not (re.match(r"^[A-Za-z]:[\\/]", p) or p.startswith(("/", "\\\\"))):
        raise ValidationError("Indique una ruta absoluta (ej. C:\\Datos\\Entrega o /srv/entrega).")
    return normalize_remote(p)
