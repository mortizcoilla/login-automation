"""REQ-104: la receta cronica vigente entra SIEMPRE a la ficha.

Diseno cerrado (11-10-2026; OK de implementacion 30-10). La prescripcion
ganadora de Plan -> Recetas — la [Cronica] con Vigencia mas reciente,
mismo criterio de REQ-029 — sale de la nota clinica que el paso 3 ya
extrajo de Rayen y se INYECTA en la base de anamnesis ANTES del LLM,
verbatim (farmacos y posologia sin tocar). Al quedar dentro de la base,
el ensamblador la mantiene byte-identica en la ficha aunque el modelo
la omita o la reformatee: la ficha siempre lleva la seccion.

La seccion se crea SIEMPRE: con la receta ganadora, o con el
placeholder "(sin receta cronica vigente)" cuando la atencion no trae
cronicas (agudas y de morbilidad no calzan: la seccion es de cronica).

Punto de insercion: ANTES del header INDICACIONES si la base trae la
seccion (meterla despues de los stubs haria que el llenado REQ-098
leyera el cuerpo como "ya escrito" y lo dejara vacio); si no, al final
(despues de un trigger ** mortadelo el ensamblador lo elimina y la
seccion queda como cola de la ficha, fuera del rango removido).

Solo se lee el Plan de la atencion actual (lo que el paso 3 ya extrajo):
no se navega al historico de Recetas/Farmacos de Rayen.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.nombres import safe_filename
from src.core.rutas import NOTAS_DIR
from src.mortadelo.ensamblador import (
    _SECCION_INDICACIONES_NUM_RE,
    _SECCION_INDICACIONES_RE,
)
from src.rayen.extraccion.plan import _parsear_vigencia

TITULO_SECCION = "RECETA CRONICA VIGENTE"
PLACEHOLDER_SIN_RECETA = "(sin receta cronica vigente)"

_SECCION_RECETAS_RE = re.compile(r"^##\s*Plan\s*-\s*Recetas\s*$")
_CRONICA_RE = re.compile(r"\[\s*cronica\s*\]", re.IGNORECASE)


def _lineas_seccion_recetas(nota_md: str) -> list[str]:
    """Lineas del cuerpo de '## Plan - Recetas' (hasta el proximo '## ')."""
    lineas = nota_md.splitlines()
    ini = next(
        (i for i, ln in enumerate(lineas) if _SECCION_RECETAS_RE.match(ln.strip())),
        None,
    )
    if ini is None:
        return []
    fin = len(lineas)
    for j in range(ini + 1, len(lineas)):
        if lineas[j].strip().startswith("## "):
            fin = j
            break
    return lineas[ini + 1 : fin]


def _normalizar_header(cuerpo: str) -> str:
    """Primera linea cruda de la prescripcion: '- [Cronica] Vigencia: ...'.

    La nota duplica la marca (el escritor anteponia '- ' a una linea
    cruda que ya la traia). Se deja una sola.
    """
    cuerpo = cuerpo.strip()
    if cuerpo.startswith("- "):
        return cuerpo
    return f"- {cuerpo}" if cuerpo else "-"


def extraer_prescripciones(nota_md: str) -> list[list[str]]:
    """Prescripciones de la nota, una por lista de lineas.

    Formato real de la nota (escritor de nota_clinica sobre la extraccion
    cruda, marcadores duplicados):
        - - [Cronica] Vigencia: 25 ago. 2027
          - \\t- Sertralina 50 mg comprimidos (2 Comprimidos cada 24 Horas)

    Devuelve una marca sola y el texto de farmaco/posologia byte-identico:
        - [Cronica] Vigencia: 25 ago. 2027
          - Sertralina 50 mg comprimidos (2 Comprimidos cada 24 Horas)
    """
    prescripciones: list[list[str]] = []
    for ln in _lineas_seccion_recetas(nota_md):
        if ln.startswith("- ") and ln.strip() != "-":
            prescripciones.append([_normalizar_header(ln[2:])])
        elif prescripciones and ln.startswith("  - "):
            cuerpo = ln[4:].lstrip("\t ").rstrip()
            if cuerpo.startswith("- "):
                cuerpo = cuerpo[2:].rstrip()
            if cuerpo:
                prescripciones[-1].append(f"  - {cuerpo}")
    return prescripciones


def ganadora(prescripciones: list[list[str]]) -> list[str] | None:
    """La [Cronica] con Vigencia mas reciente (None si no hay cronicas).

    Sin fechas parseables queda la ULTIMA del orden de Rayen (suele ir de
    mas viejo a mas nuevo), misma convencion de _filtrar_receta_mas_
    reciente (REQ-029).
    """
    cronicas = [p for p in prescripciones if p and _CRONICA_RE.search(p[0])]
    if not cronicas:
        return None
    if len(cronicas) == 1:
        return cronicas[0]
    con_fecha = [
        (i, d)
        for i, p in enumerate(cronicas)
        if (d := _parsear_vigencia(p[0])) is not None
    ]
    if not con_fecha:
        return cronicas[-1]
    i_ganadora = max(con_fecha, key=lambda x: x[1])[0]
    return cronicas[i_ganadora]


def cargar_receta_cronica(
    nombre: str, fecha: str, notas_dir: Path | None = None
) -> str | None:
    """Bloque de la receta cronica ganadora desde la nota del paso 3.

    None si la nota no existe o no trae cronicas.
    """
    notas_dir = notas_dir or NOTAS_DIR
    nota_path = notas_dir / f"{safe_filename(nombre)}_{fecha}.md"
    if not nota_path.exists():
        return None
    nota = nota_path.read_text(encoding="utf-8", errors="replace")
    bloque = ganadora(extraer_prescripciones(nota))
    return "\n".join(bloque) if bloque else None


def inyectar_receta_cronica(base: str, bloque: str | None) -> str:
    """Base con la seccion de receta cronica SIEMPRE creada.

    bloque: texto de la prescripcion ganadora (o None -> placeholder).
    """
    lineas = base.rstrip("\n").splitlines() if base.strip() else []
    cuerpo = [TITULO_SECCION]
    if bloque and bloque.strip():
        cuerpo.extend(bloque.strip("\n").splitlines())
    else:
        cuerpo.append(PLACEHOLDER_SIN_RECETA)

    if not lineas:
        return "\n".join(cuerpo) + "\n"

    idx = next(
        (
            i
            for i, ln in enumerate(lineas)
            if _SECCION_INDICACIONES_NUM_RE.match(ln) or _SECCION_INDICACIONES_RE.match(ln)
        ),
        None,
    )
    if idx is None:
        return "\n".join(lineas + ["", *cuerpo]) + "\n"
    return "\n".join(lineas[:idx] + ["", *cuerpo] + lineas[idx:]) + "\n"
