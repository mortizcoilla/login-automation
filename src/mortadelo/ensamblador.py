"""Ensamblador de la ficha final: el LLM propone, el CODIGO ensambla.

Hallazgo central de las pruebas (ver docs/REQUISITOS.md REQ-056): el
modelo cumple las reglas la mayoria de las veces, pero no siempre
(reformatea, cambia tiempos verbales, es inestable entre corridas).
Este modulo reconstruye la ficha con GARANTIAS:

- Las lineas de la anamnesis base van BYTE-IDENTICAS, salvo tres
  excepciones validadas:
  (a) campo vacio que el LLM lleno (mismo rotulo + contenido),
  (b) correccion ortografica validada palabra a palabra (acento/caso
      o UNA sola edicion por palabra, mismo numero de palabras),
  (c) nada mas.
- El bloque ** mortadelo se ELIMINA siempre.
- Las secciones pedidas (INDICACIONES / INTERCONSULTA A X) se extraen
  de la salida del LLM y se AGREGAN al final, tal cual.

Cualquier otra linea que el modelo haya inventado o reformateado se
descarta silenciosamente (queda la linea original).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from src.informes.enriquecer import TRIGGER_RE

# Rotulo de campo vacio: "Campo:", "- Campo:", "> Campo:", "? Campo:"
_LINEA_CAMPO_RE = re.compile(r"^\s*[-*?>\s]*[^:]{1,80}:\s*$")
_ROTULO_RE = re.compile(r"^\s*[-*?>\s]*([^:]{1,80}):")
_TITULO_SECCION_RE = re.compile(
    r"^\s*(INDICACIONES|INTERCONSULTA(?:\s+A\s+.+)?)\s*:?\s*$", re.IGNORECASE
)


@dataclass
class FichaEnsamblada:
    """Resultado del ensamblado + trazabilidad de lo que se acepto."""

    texto: str
    lineas_llenadas: list[str] = field(default_factory=list)
    correcciones: list[tuple[str, str]] = field(default_factory=list)
    secciones_agregadas: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Utilidades de comparacion
# ---------------------------------------------------------------------------


def _normalizar(texto: str) -> str:
    """Minusculas, sin tildes, espacios colapsados."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def _distancia_palabra(a: str, b: str) -> int:
    """Distancia de Levenshtein entre dos palabras (normalizadas)."""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def es_correccion_ortografica(original: str, corregida: str) -> bool:
    """True si 'corregida' solo corrige ortografia de 'original'.

    Regla palabra a palabra (mismo numero de palabras, alineadas 1:1).
    Cada palabra puede diferir SOLO por:
    - tildes o mayusculas (misma palabra tras normalizar), o
    - UNA edicion (letra insertada, borrada o sustituida).
    Palabra nueva, borrada, reordenada o con 2+ ediciones => NO es
    ortografia (ej: "operan" -> "operaron" son 2 ediciones => rechazado).
    """
    raw_o = original.lower().split()
    raw_c = corregida.lower().split()
    if len(raw_o) != len(raw_c):
        return False
    hubo_cambio = False
    for po, pc in zip(raw_o, raw_c, strict=True):
        no, nc = _normalizar(po), _normalizar(pc)
        if po == pc:
            continue
        hubo_cambio = True
        if no == nc:
            continue  # solo tildes/mayusculas: correccion valida
        if _distancia_palabra(no, nc) != 1:
            return False
    return hubo_cambio


# ---------------------------------------------------------------------------
# Deteccion del bloque trigger
# ---------------------------------------------------------------------------


def _rango_trigger(lineas: list[str]) -> tuple[int, int] | None:
    """Rango [ini, fin) del bloque ** mortadelo (o None si no hay)."""
    ini = None
    for i, ln in enumerate(lineas):
        if TRIGGER_RE.search(ln):
            ini = i
            break
    if ini is None:
        return None
    fin = len(lineas)
    for j in range(ini + 1, len(lineas)):
        ln = lineas[j].strip()
        if ln == "**":
            fin = j + 1
            break
        # Nueva seccion de la anamnesis tras el trigger: bullets vacios,
        # texto en vineta o vacio siguen siendo del bloque.
        if ln and not ln.startswith(("-", "*")) and not TRIGGER_RE.search(ln):
            fin = j
            break
    return (ini, fin)


# ---------------------------------------------------------------------------
# Ensamblado
# ---------------------------------------------------------------------------


def _rotulo(linea: str) -> str | None:
    m = _ROTULO_RE.match(linea)
    return _normalizar(m.group(1)) if m else None


def _extraer_secciones(salida: list[str]) -> dict[str, str]:
    """Extrae INDICACIONES / INTERCONSULTA de la salida del LLM."""
    secciones: dict[str, str] = {}
    actual: str | None = None
    buffer: list[str] = []
    for ln in salida:
        m = _TITULO_SECCION_RE.match(ln)
        if m:
            if actual:
                secciones[actual] = "\n".join(buffer).strip()
            actual = m.group(1).upper().split(":")[0].strip()
            buffer = []
        elif actual:
            buffer.append(ln)
    if actual:
        secciones[actual] = "\n".join(buffer).strip()
    return secciones


def ensamblar_ficha(
    base: str,
    salida_llm: str,
    pedir_indicaciones: bool = False,
    especialidad_interconsulta: str | None = None,
) -> FichaEnsamblada:
    """Construye la ficha final con garantias estructurales.

    Args:
        base: anamnesis cruda (motivo blockquote + texto de Yadira).
        salida_llm: lo que el LLM devolvio para la ficha.
        pedir_indicaciones / especialidad_interconsulta: secciones que
            el trigger pidio; si es None/False no se agregan aunque el
            modelo las haya escrito.

    Returns:
        FichaEnsamblada con el texto final y la trazabilidad.
    """
    resultado = FichaEnsamblada(texto="")
    base_lineas = base.splitlines()
    llm_lineas = salida_llm.splitlines()

    rango = _rango_trigger(base_lineas)
    lineas_sin_trigger = (
        [ln for i, ln in enumerate(base_lineas) if not (rango and rango[0] <= i < rango[1])]
        if rango
        else list(base_lineas)
    )

    # Indice de lineas del LLM por version normalizada (para matching).
    llm_norm: dict[str, str] = {}
    for ln in llm_lineas:
        llm_norm.setdefault(_normalizar(ln), ln)

    finales: list[str] = []
    for linea_base in lineas_sin_trigger:
        norm = _normalizar(linea_base)
        if norm in llm_norm:
            finales.append(linea_base)  # identica: base tal cual
            continue

        rotulo = _rotulo(linea_base)
        es_campo_vacio = bool(_LINEA_CAMPO_RE.match(linea_base)) and rotulo

        aceptada: str | None = None
        if es_campo_vacio and rotulo:
            # Buscar en el LLM una linea con el mismo rotulo y contenido.
            for ln in llm_lineas:
                r2 = _rotulo(ln)
                if r2 == rotulo and _normalizar(ln) != norm:
                    aceptada = ln  # campo vacio llenado
                    resultado.lineas_llenadas.append(ln.strip())
                    break

        if aceptada is None:
            # Correccion ortografica validada (solo lineas llenas).
            for ln in llm_lineas:
                if es_correccion_ortografica(linea_base, ln):
                    aceptada = ln
                    resultado.correcciones.append((linea_base.strip(), ln.strip()))
                    break

        finales.append(aceptada if aceptada is not None else linea_base)

    # Secciones condicionales al final.
    secciones_llm = _extraer_secciones(llm_lineas)
    if pedir_indicaciones and secciones_llm.get("INDICACIONES"):
        finales += ["", "INDICACIONES:", secciones_llm["INDICACIONES"]]
        resultado.secciones_agregadas.append("INDICACIONES")
    if especialidad_interconsulta:
        titulo = f"INTERCONSULTA A {especialidad_interconsulta.upper()}:"
        cuerpo = next(
            (v for k, v in secciones_llm.items() if k.startswith("INTERCONSULTA")),
            "",
        )
        if cuerpo:
            finales += ["", titulo, cuerpo]
            resultado.secciones_agregadas.append(titulo.rstrip(":"))

    resultado.texto = "\n".join(finales).strip() + "\n"
    return resultado
