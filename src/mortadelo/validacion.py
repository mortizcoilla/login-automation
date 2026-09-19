"""Validaciones post-generacion del paso 7 (REQ-056).

Las 5 reglas acumuladas de las pruebas. NO bloquean: producen
Advertencias que Yadira ve (la supervisión humana es el control final).
El ensamblador ya garantiza lo estructural; aqui se verifica el
resultado y su coherencia con los insumos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.informes.enriquecer import TRIGGER_RE

_EDAD_RE = re.compile(r"(\d{1,3})\s*a[ñn]os")


@dataclass
class Advertencia:
    codigo: str
    mensaje: str


def validar_ficha(
    ficha: str,
    base: str,
    info_paciente: str = "",
) -> list[Advertencia]:
    """Corre las 5 reglas sobre la ficha ensamblada."""
    advertencias: list[Advertencia] = []

    # V1: primera linea de la base presente al inicio de la ficha.
    primera_base = next((ln for ln in base.splitlines() if ln.strip()), "")
    if primera_base and not ficha.startswith(primera_base):
        advertencias.append(
            Advertencia(
                "V1_PRIMERA_LINEA", "La ficha no comienza con la primera linea de la anamnesis"
            )
        )

    # V2: el trigger no debe existir en la ficha final.
    if TRIGGER_RE.search(ficha):
        advertencias.append(
            Advertencia("V2_TRIGGER", "El bloque ** mortadelo sigue presente en la ficha")
        )

    # V3: edad consistente ficha <-> info_paciente.
    edad_ficha = _EDAD_RE.search(ficha)
    edad_info = _EDAD_RE.search(info_paciente)
    if edad_ficha and edad_info and edad_ficha.group(1) != edad_info.group(1):
        advertencias.append(
            Advertencia(
                "V3_EDAD",
                f"Edad distinta entre ficha ({edad_ficha.group(1)}) e "
                f"info_paciente ({edad_info.group(1)}); verificar",
            )
        )

    # V4: la ficha no puede ser mucho mas corta que la base sin trigger
    # (truncamiento). Tolerancia generosa: las secciones agregadas
    # alargan, nunca acortan.
    base_sin_trigger = TRIGGER_RE.split(base)[0]
    if len(ficha.strip()) < len(base_sin_trigger.strip()) * 0.8:
        advertencias.append(
            Advertencia("V4_TRUNCADA", "La ficha es notablemente mas corta que la anamnesis base")
        )

    # V5: sin bloques de codigo ni preambulos del modelo.
    if ficha.strip().startswith("```") or "```" in ficha:
        advertencias.append(
            Advertencia("V5_FORMATO", "La ficha contiene bloques de codigo (```) del modelo")
        )

    return advertencias


def validar_informe(informe: str) -> list[Advertencia]:
    """Coherencia basica del informe de trazabilidad."""
    advertencias: list[Advertencia] = []
    for seccion in ("## ALERTAS", "## Llenados realizados", "## Sin informacion suficiente"):
        if seccion not in informe:
            advertencias.append(
                Advertencia("V6_SECCION", f"El informe no trae la seccion '{seccion}'")
            )
    return advertencias
