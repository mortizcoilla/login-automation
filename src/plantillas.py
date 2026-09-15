from __future__ import annotations

import os
import re
from datetime import date, datetime
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


def cargar_plantilla(
    tipo_atencion: str, edad_meses: int | None = None
) -> str | None:
    """Carga la plantilla canonica para el tipo de atencion dado.

    Usa `reglas_plantillas.resolver_plantilla` para decidir que archivo
    de plantilla cargar, segun la regla de uso mantenida por Yadira
    en PLANTILLAS.xlsx. Si el tipo no tiene plantilla asignada o la
    regla dice 'NO APLICA', devuelve None.

    Args:
        tipo_atencion: tipo que viene de Rayen.
        edad_meses: edad del paciente en meses. Necesario para resolver
            "Control de nino sano" (1 mes vs 3 meses). Si no se pasa
            y el tipo es "control salud", devuelve None.
    """
    from src.reglas_plantillas import resolver_plantilla

    nombre = resolver_plantilla(tipo_atencion, edad_meses=edad_meses)
    if nombre is None:
        return None
    ruta = os.path.join(PLANTILLAS_DIR, f"{nombre}.txt")
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


def calcular_edad_meses(
    fecha_nacimiento: date,
    fecha_referencia: date | None = None,
) -> int:
    """Calcula la edad del paciente en meses cumplidos.

    Args:
        fecha_nacimiento: fecha de nacimiento del paciente.
        fecha_referencia: fecha respecto a la cual se calcula la edad.
            Por defecto, hoy (date.today()). Se puede pasar otra fecha
            para tests o calculos en una fecha distinta (ej. fecha de
            la atencion, no hoy).

    Returns:
        Edad en meses cumplidos (entero). Negativo si
        `fecha_nacimiento` es posterior a `fecha_referencia`
        (caso patologico, no esperado en produccion).

    Raises:
        ValueError: si `fecha_nacimiento` es posterior a la fecha de
            referencia (un bebe no puede nacer en el futuro).

    Nota:
        La fuente de la `fecha_nacimiento` la define el caller (Mora
        API, Rayen, DB local, etc.). Esta funcion es la logica de
        calculo; no sabe de donde sale el dato.
    """
    if fecha_referencia is None:
        fecha_referencia = date.today()

    if fecha_nacimiento > fecha_referencia:
        raise ValueError(
            f"fecha_nacimiento ({fecha_nacimiento}) es posterior a "
            f"fecha_referencia ({fecha_referencia})"
        )

    # Calculo en meses cumplidos: anios * 12 + meses, ajustado si
    # el dia del mes aun no se cumple en el mes de referencia.
    anios = fecha_referencia.year - fecha_nacimiento.year
    meses = fecha_referencia.month - fecha_nacimiento.month
    total = anios * 12 + meses
    if fecha_referencia.day < fecha_nacimiento.day:
        total -= 1
    return total
