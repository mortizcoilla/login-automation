"""Mapping del bundle nino_sano (Control de Nino Sano 0-9 anos en APS).

El bundle se dispara cuando `tipo_atencion == "Control salud"`. La
plantilla concreta se elige por EDAD segun `_resolver_control_nino_sano`
en `src.reglas_plantillas`:

    edad_meses < 3  ->  CONTROL NI\u00d1O SANO 1 MES
    edad_meses >= 3 ->  CONTROL NI\u00d1O SANO 3 MESES

Este bundle NO duplica el mapping. La fuente de verdad es `_REGLA` en
`src.reglas_plantillas`, que se consume via `resolver_plantilla`. Lo que
hace este modulo es:

1. Declarar las PLANTILLAS canonicas del bundle.
2. Exponer helpers que Mortadelo usa para responder preguntas sobre
   su propio alcance.
3. Recordar que la EDAD es necesaria para resolver el placeholder.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Final, Optional

from src.plantillas import calcular_edad_meses
from src.reglas_plantillas import (
    LIMITE_MESES_NINO_SANO,
    _PLACEHOLDER_NINO_SANO,
    listar_tipos_con_plantilla,
    resolver_plantilla,
)

# Plantillas canonicas que este bundle absorbe.
# (1 MES se usa para < 3 meses; 3 MESES para >= 3 meses. No hay otras.)
PLANTILLA_1MES: Final[str] = "CONTROL NI\u00d1O SANO 1 MES"
PLANTILLA_3MESES: Final[str] = "CONTROL NI\u00d1O SANO 3 MESES"
PLANTILLAS_NINO_SANO: Final[frozenset[str]] = frozenset({
    PLANTILLA_1MES,
    PLANTILLA_3MESES,
})

# Regex para parsear la seccion IDENTIFICACION de la nota clinica.
_RE_BLOQUE_IDENT = re.compile(
    r"=== INICIO IDENTIFICACION ={2,}\s*\n"
    r"(.*?)"
    r"=== FIN IDENTIFICACION ={2,}",
    re.DOTALL,
)

# Regex para "Edad Cronologica: X anos Y meses Z dias"
_RE_EDAD_CRON = re.compile(
    r"Edad\s+Cronol[oó]gica\s*:\s*"
    r"(?:(\d+)\s*a[nñ]os?)?\s*"
    r"(?:(\d+)\s*mes(?:es)?)?\s*"
    r"(?:(\d+)\s*d[ií]as?)?",
    re.IGNORECASE,
)

# Regex para "Fecha de nacimiento: dd-mm-yyyy [HH:MM]"
_RE_FECHA_NAC = re.compile(
    r"Fecha\s+de\s+nacimiento\s*:\s*"
    r"(\d{1,2}-\d{1,2}-\d{2,4})",
    re.IGNORECASE,
)


def extraer_edad_meses_de_identificacion(
    texto_nota: str,
    fecha_referencia: Optional[date] = None,
) -> Optional[int]:
    """Extrae la edad en meses del paciente desde la seccion IDENTIFICACION.

    Estrategia:
    1) Parsea "Edad Cronologica: X anos Y meses Z dias" y suma meses.
    2) Si no aparece, parsea "Fecha de nacimiento: dd-mm-yyyy" y calcula
       la edad con `calcular_edad_meses`.

    Args:
        texto_nota: contenido completo de la nota clinica (.txt).
        fecha_referencia: fecha respecto a la cual se calcula la edad
            si se usa Fecha de nacimiento. Por defecto, hoy.

    Returns:
        Edad en meses (entero), o None si no se encontro.
    """
    logger = logging.getLogger("nino_sano")
    m_bloque = _RE_BLOQUE_IDENT.search(texto_nota)
    if m_bloque is None:
        logger.info("[nino_sano] No se encontro bloque IDENTIFICACION en la nota")
        return None
    bloque = m_bloque.group(1)

    # 1) Intentar con Edad Cronologica.
    m_edad = _RE_EDAD_CRON.search(bloque)
    if m_edad:
        anos = int(m_edad.group(1) or 0)
        meses = int(m_edad.group(2) or 0)
        # Los dias no se suman (Mortadelo trabaja en meses para el
        # bundle; los dias harian impreciso el calculo del limite 3m).
        total = anos * 12 + meses
        logger.info(
            f"[nino_sano] Edad Cronologica: {anos}a + {meses}m = {total} meses"
        )
        return total

    # 2) Fallback: Fecha de nacimiento + calcular_edad_meses.
    m_fecha = _RE_FECHA_NAC.search(bloque)
    if m_fecha is None:
        logger.info("[nino_sano] No hay Edad Cronologica ni Fecha de nacimiento")
        return None
    try:
        fecha_nac = datetime.strptime(m_fecha.group(1), "%d-%m-%Y").date()
    except ValueError:
        try:
            fecha_nac = datetime.strptime(m_fecha.group(1), "%d-%m-%y").date()
            if fecha_nac.year < 1930:
                fecha_nac = fecha_nac.replace(year=fecha_nac.year + 100)
        except ValueError:
            logger.warning(
                f"[nino_sano] Fecha de nacimiento no parseable: {m_fecha.group(1)!r}"
            )
            return None
    try:
        edad = calcular_edad_meses(fecha_nac, fecha_referencia)
    except ValueError as e:
        logger.warning(f"[nino_sano] No se pudo calcular edad: {e}")
        return None
    logger.info(
        f"[nino_sano] Fecha de nacimiento {fecha_nac} -> {edad} meses"
    )
    return edad


def es_nino_sano(tipo_atencion: str, edad_meses: int | None = None) -> bool:
    """True si el tipo_atencion es Control de Nino Sano y la edad
    permite resolver la plantilla (>= 0 meses).

    Sin `edad_meses` devuelve False: no se puede elegir entre 1 MES y
    3 MESES sin edad. Esto es intencional: fuerza al caller a traer la
    edad antes de decidir.
    """
    if edad_meses is None:
        return False
    if edad_meses < 0:
        return False
    return resolver_plantilla(tipo_atencion, edad_meses) in PLANTILLAS_NINO_SANO


def es_tipo_control_salud(tipo_atencion: str) -> bool:
    """True si el tipo_atencion es 'Control salud' (independiente de edad).

    Util cuando aun no se tiene la edad y se necesita saber si el tipo
    es candidato al bundle. La plantilla final se decide despues con
    `plantilla_para` + edad.
    """
    canonica = resolver_plantilla(tipo_atencion, edad_meses=0)
    return canonica in PLANTILLAS_NINO_SANO


def plantilla_para(tipo_atencion: str, edad_meses: int | None = None) -> str | None:
    """Devuelve la plantilla canonica para el tipo_atencion + edad,
    o None si no es de Nino Sano o falta la edad.

    Wrapper de `resolver_plantilla` que filtra a las plantillas del bundle.
    """
    canonica = resolver_plantilla(tipo_atencion, edad_meses)
    if canonica in PLANTILLAS_NINO_SANO:
        return canonica
    return None


def tipos_atencion_del_bundle() -> frozenset[str]:
    """Set de tipo_atencion que este bundle absorbe (calculado en runtime).

    Solo los tipos cuya canonica es el placeholder de Nino Sano (se
    expande con edad). Hoy es un unico tipo: 'Control salud'. Igual lo
    dejamos generico por si maniana se agregan mas.
    """
    return frozenset(
        tipo for tipo, canonica in listar_tipos_con_plantilla()
        if canonica == _PLACEHOLDER_NINO_SANO
    )


def requiere_edad(tipo_atencion: str) -> bool:
    """True si el bundle necesita la edad del paciente para resolver
    la plantilla. Hoy: todos los tipos del bundle la necesitan.
    """
    return es_tipo_control_salud(tipo_atencion)


__all__ = [
    "LIMITE_MESES_NINO_SANO",
    "PLANTILLA_1MES",
    "PLANTILLA_3MESES",
    "PLANTILLAS_NINO_SANO",
    "es_nino_sano",
    "es_tipo_control_salud",
    "extraer_edad_meses_de_identificacion",
    "plantilla_para",
    "requiere_edad",
    "tipos_atencion_del_bundle",
]
