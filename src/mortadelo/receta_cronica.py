"""REQ-104: la receta cronica vigente entra SIEMPRE a la ficha.

Diseno cerrado (11-10-2026; OK de implementacion 30-10). La cadena:

 1. El paso 3 extrae la receta cronica MAS RECIENTE DEL PACIENTE desde
    el arbol "Receta" del historial (incluye atenciones pasadas; ver
    src/rayen/extraccion/receta_cronica.py) y la deja VERBATIM en la
    seccion "## Receta cronica" de la nota clinica (portador
    confirmado por Miguel).
 2. Esta funcion la lee de la nota y la INYECTA en la base de
    anamnesis ANTES del LLM. Al quedar en la base, el ensamblador la
    mantiene byte-identica en la ficha aunque el modelo la omita.

Reglas de inyeccion (vuelta 13/18/19/20 del diseño):
 - La base trae "Fármacos de uso diario" (control) o "Medicamentos"
   (morbilidad), match tolerante a tildes/mayusculas/numeracion de
   plantilla: cuerpo vacio -> se RELLENA; con contenido -> el bloque
   va DEBAJO del texto de Yadira (jamas se borra lo suyo).
 - La base NO trae la seccion -> se CREA con titulo canonico, antes
   del header INDICACIONES si existe (meterla tras los stubs haria
   que el llenado REQ-098 leyera el cuerpo como ya escrito), si no al
   final.
 - Estados: encontrada -> bloque verbatim; no_existe -> "Sin
   medicamentos de uso diario"; indeterminado -> "...(no verificado -
   revisar)" (el falso negativo esta prohibido: jamas se declara
   inexistencia sin la prueba positiva del extractor).
 - Nota sin la seccion "## Receta cronica" (feature no corrio o nota
   previa al despliegue) -> NO se inyecta nada (comportamiento actual).
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.nombres import safe_filename
from src.core.rutas import NOTAS_DIR
from src.mortadelo.ensamblador import (
    _SECCION_INDICACIONES_NUM_RE,
    _SECCION_INDICACIONES_RE,
    _STUB_VACIO_RE,
)

TITULO_SECCION_NUEVA = "FARMACOS DE USO DIARIO"
SIN_MEDICAMENTOS = "Sin medicamentos de uso diario"
NO_VERIFICADO = "Sin medicamentos de uso diario (no verificado - revisar)"

_ESTADO_ENCONTRADA = "encontrada"
_ESTADO_NO_EXISTE = "no_existe"
_ESTADO_INDETERMINADO = "indeterminado"

_SECCION_RECETA_RE = re.compile(r"^##\s*Receta cronica\s*$", re.IGNORECASE)
_PLACEHOLDER_SIN = "(sin receta cronica vigente)"
_PLACEHOLDER_NO_VERIFICADO = "(no verificado - revisar)"
# Numeracion de plantilla opcional: "3.3. ", "4) ", "5. "
_RX_NUMERACION = re.compile(r"^\d+(?:\.\d+)*[\.\)]?\s*")
# Siguiente seccion numerada CON texto: fin del cuerpo de una seccion.
_SIGUIENTE_SECCION_RE = re.compile(r"^\s*\d+(?:\.\d+)*[\.\)]\s+\S")


def normalizar(texto: str) -> str:
    """Minusculas, sin tildes, espacios colapsados."""
    import unicodedata

    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def _cuerpo_seccion_receta(nota_md: str) -> str | None:
    """Texto de '## Receta cronica' de la nota (None si no existe)."""
    lineas = nota_md.splitlines()
    ini = next(
        (i for i, ln in enumerate(lineas) if _SECCION_RECETA_RE.match(ln.strip())),
        None,
    )
    if ini is None:
        return None
    fin = len(lineas)
    for j in range(ini + 1, len(lineas)):
        if lineas[j].strip().startswith("## "):
            fin = j
            break
    return "\n".join(lineas[ini + 1 : fin]).strip()


def cargar_estado_receta(
    nombre: str, fecha: str, notas_dir: Path | None = None
) -> dict | None:
    """Estado + bloque verbatim desde la nota del paso 3.

    None si la nota no existe o no trae la seccion "## Receta cronica"
    (la feature no corrio para esta nota: no se inyecta nada).
    """
    notas_dir = notas_dir or NOTAS_DIR
    nota_path = notas_dir / f"{safe_filename(nombre)}_{fecha}.md"
    if not nota_path.exists():
        return None
    nota = nota_path.read_text(encoding="utf-8", errors="replace")
    cuerpo = _cuerpo_seccion_receta(nota)
    if cuerpo is None:
        return None
    if cuerpo == _PLACEHOLDER_SIN:
        return {"estado": _ESTADO_NO_EXISTE, "bloque": ""}
    if not cuerpo or cuerpo == _PLACEHOLDER_NO_VERIFICADO:
        return {"estado": _ESTADO_INDETERMINADO, "bloque": ""}
    return {"estado": _ESTADO_ENCONTRADA, "bloque": cuerpo}


def _es_header_farmacos(linea: str) -> bool:
    """True si la linea es el header 'Fármacos de uso diario' o
    'Medicamentos' (con o sin numeracion de plantilla y dos puntos)."""
    t = normalizar(linea).rstrip(":").strip()
    t = _RX_NUMERACION.sub("", t).strip()
    return t in ("farmacos de uso diario", "medicamentos")


def _contenido(estado_receta: dict | None) -> list[str] | None:
    """Lineas a inyectar segun el estado (None = no inyectar)."""
    estado = (estado_receta or {}).get("estado", "")
    if estado == _ESTADO_ENCONTRADA:
        bloque = (estado_receta or {}).get("bloque", "").strip()
        return bloque.splitlines() if bloque else [NO_VERIFICADO]
    if estado == _ESTADO_NO_EXISTE:
        return [SIN_MEDICAMENTOS]
    if estado == _ESTADO_INDETERMINADO:
        return [NO_VERIFICADO]
    return None


def _fin_de_cuerpo(lineas: list[str], idx_header: int) -> int:
    """Fin del cuerpo de la seccion de farmacos: la siguiente seccion
    numerada con texto, un header INDICACIONES (numerado o no) o EOF."""
    fin = len(lineas)
    for j in range(idx_header + 1, len(lineas)):
        ln = lineas[j]
        if _SIGUIENTE_SECCION_RE.match(ln) or _SECCION_INDICACIONES_NUM_RE.match(ln) or _SECCION_INDICACIONES_RE.match(ln):
            return j
    return fin


def inyectar_receta_cronica(base: str, estado_receta: dict | None) -> str:
    """Base con los farmacos de la receta cronica (o tal cual)."""
    contenido = _contenido(estado_receta)
    if contenido is None:
        return base

    lineas = base.rstrip("\n").splitlines() if base.strip() else []

    idx = next((i for i, ln in enumerate(lineas) if _es_header_farmacos(ln)), None)
    if idx is not None:
        fin = _fin_de_cuerpo(lineas, idx)
        cuerpo = lineas[idx + 1 : fin]
        if all(not ln.strip() or _STUB_VACIO_RE.match(ln) for ln in cuerpo):
            # Seccion vacia (stubs de plantilla): se rellena.
            nuevas = lineas[: idx + 1] + contenido + lineas[fin:]
        else:
            # Yadira escribio farmacos: el bloque va DEBAJO, sin borrar.
            nuevas = lineas[:fin] + ["", *contenido] + lineas[fin:]
        return "\n".join(nuevas) + "\n"

    # Sin la seccion: se crea antes del header INDICACIONES (si existe)
    # para no romper el llenado de stubs REQ-098, o al final.
    bloque = [TITULO_SECCION_NUEVA, *contenido]
    idx_ind = next(
        (
            i
            for i, ln in enumerate(lineas)
            if _SECCION_INDICACIONES_NUM_RE.match(ln) or _SECCION_INDICACIONES_RE.match(ln)
        ),
        None,
    )
    if idx_ind is None:
        return "\n".join(lineas + ["", *bloque]) + "\n"
    return "\n".join(lineas[:idx_ind] + ["", *bloque] + lineas[idx_ind:]) + "\n"
