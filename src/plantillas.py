from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any

from src.constants import (
    DATE_FORMAT,
    INSTRUMENTO_PREFIXES,
    PLACEHOLDERS,
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTILLAS_DIR = os.path.join(BASE_DIR, "plantillas")
COMPLETADAS_DIR = os.path.join(PLANTILLAS_DIR, "completadas")

_PREFIX_RE = re.compile(
    r"^(?:" + "|".join(re.escape(p) for p in INSTRUMENTO_PREFIXES) + r")\s*", re.IGNORECASE
)


def sanitizar_tipo(tipo_atencion: str) -> str:
    if not tipo_atencion:
        return ""
    return _PREFIX_RE.sub("", tipo_atencion.strip()).strip()


def listar_tipos_atencion() -> list[str]:
    if not os.path.isdir(PLANTILLAS_DIR):
        return []
    return sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(PLANTILLAS_DIR)
        if f.endswith(".txt") and os.path.isfile(os.path.join(PLANTILLAS_DIR, f))
    )


def cargar_plantilla(tipo_atencion: str) -> str | None:
    tipo = sanitizar_tipo(tipo_atencion)
    ruta = os.path.join(PLANTILLAS_DIR, f"{tipo}.txt")
    if not os.path.exists(ruta):
        return None
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def rellenar_plantilla(texto: str, datos: dict[str, Any]) -> str:
    hoy = datetime.now().strftime(DATE_FORMAT)
    reemplazos = {
        "{PACIENTE}": str(datos.get("nombre", "")),
        "{RUT}": str(datos.get("rut", "")),
        "{FECHA}": str(datos.get("fecha", hoy)),
        "{RAZON}": str(datos.get("razon", "")),
        "{TIPO_ATENCION}": sanitizar_tipo(str(datos.get("tipo_atencion", ""))),
        "{OBSERVACION}": str(datos.get("observacion", "")),
        "{HORA}": str(datos.get("hora", "")),
    }
    for placeholder, valor in reemplazos.items():
        texto = texto.replace(placeholder, valor)
    return texto


def guardar_plantilla(texto: str, nombre_paciente: str) -> str:
    os.makedirs(COMPLETADAS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^\w\-. ]+", "_", nombre_paciente).strip().replace(" ", "_")
    nombre_archivo = f"{safe_name}_{timestamp}.txt"
    ruta = os.path.join(COMPLETADAS_DIR, nombre_archivo)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    return ruta


def placeholders_disponibles() -> list[str]:
    return list(PLACEHOLDERS)
