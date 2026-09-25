"""Parser UNICO del informe de fichas abiertas (Fase 4b).

Unifica las dos gramáticas paralelas que existian (parsear_informe en
crear_notas_clinicas y _parsear_informe_basico en enriquecer_informe).

Layouts soportados (columnas separadas por 2+ espacios, fecha dd-mm-yyyy):
  4 (legacy pre-09-09):  Fecha | Nombre | Tipo | Plantilla
  5 (ACTUAL, paso 5):    Fecha | Nombre | Edad | Tipo | Motivo
  6 (legacy pre-09-16):  Fecha | Nombre | Edad | Tipo | Motivo | Plantilla
  7 (intermedio 16:30):  Fecha | Nombre | Edad | Tipo | Motivo | Examenes | IC
  8 (AMBIGUO, ver abajo): 8 columnas

REQ-043 (8 columnas, disambiguacion): el layout deprecado del 16-09 17:26
era Fecha|Nombre|Edad|Edad_decimal|Tipo|Motivo|Exam|IC (parts[3] es una
edad decimal); el layout actual es Fecha|Nombre|Edad|Tipo|Motivo|Exam|IC|Ind
(parts[3] es un Tipo de atencion). Se disambigua por parts[3]: si es
edad-decimal-like -> deprecado; si no -> actual. Antes de este fix, correr
el paso 6 dos veces sin paso 5 en medio corrompia tipo/motivo.

REQ-053 (bugfix 5 columnas): parsear_informe (crear_notas) mapeaba 5 cols
con el layout legacy sin Edad, produciendo tipo_atencion="(-)" y motivo=tipo
en las notas de septiembre 2026. El layout actual 5-cols tiene Edad en
parts[2]; Tipo=parts[3], Motivo=parts[4].

La Edad NUNCA se lee del informe: siempre se re-deriva de la nota (REQ-041).
Los prefijos "(atencion preferente/prioritario/urgente)" se quitan del nombre
antes del match contra Rayen.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.notas.modelos import PacienteObjetivo

# Prefijos que Rayen antepone al nombre en el informe (no son parte del
# nombre real del paciente; rompen el match contra la tabla de Rayen).
_PREFIJO_PREF_RE = re.compile(
    r"^\s*\(?\s*(atenci[oó]n preferente|prioritario|urgente)\s*\)?\s*",
    re.IGNORECASE,
)

# Edad decimal "40,19" o entero "40" (para disambiguar 8 columnas).
_EDAD_LIKE_RE = re.compile(r"^\d{1,3}(?:,\d{1,2})?$")


def _quitar_prefijo_prioridad(nombre: str) -> str:
    return _PREFIJO_PREF_RE.sub("", nombre).strip()


def parsear_linea_informe(linea: str) -> dict[str, str] | None:
    """Parsea UNA linea del informe. None si no es una fila de datos.

    Returns:
        dict con keys: fecha, nombre, tipo_atencion, motivo, plantilla
        (plantilla="" si el layout no la trae). La Edad se ignora
        (siempre se re-deriva de la nota, REQ-041).
    """
    parts = re.split(r"\s{2,}", linea.rstrip())
    if len(parts) not in (4, 5, 6, 7, 8, 9):
        return None
    if not re.match(r"^\d{2}-\d{2}-\d{4}$", parts[0]):
        return None
    fecha = parts[0]
    nombre = _quitar_prefijo_prioridad(parts[1])

    if len(parts) == 4:
        # Legacy pre-09-09: Fecha|Nombre|Tipo|Plantilla
        tipo_atencion, motivo, plantilla = parts[2], "", parts[3]
    elif len(parts) == 5:
        # ACTUAL (paso 5): Fecha|Nombre|Edad|Tipo|Motivo  (REQ-053)
        tipo_atencion, motivo, plantilla = parts[3], parts[4], ""
    elif len(parts) == 6:
        # Legacy pre-09-16: Fecha|Nombre|Edad|Tipo|Motivo|Plantilla
        tipo_atencion, motivo, plantilla = parts[3], parts[4], parts[5]
    elif len(parts) == 7:
        # Intermedio 16:30: Fecha|Nombre|Edad|Tipo|Motivo|Exam|IC
        tipo_atencion, motivo, plantilla = parts[3], parts[4], ""
    else:
        # 8-9 columnas (9 = con Mortadelo, REQ-084): disambiguacion REQ-043
        if _EDAD_LIKE_RE.match(parts[3].strip()):
            # Deprecado 17:26: Fecha|Nombre|Edad|Edad_dec|Tipo|Motivo|Ex|IC
            tipo_atencion, motivo, plantilla = parts[4], parts[5], ""
        else:
            # Actual (salida del paso 6): Fecha|Nombre|Edad|Tipo|Motivo|Ex|IC|Ind
            tipo_atencion, motivo, plantilla = parts[3], parts[4], ""

    return {
        "fecha": fecha.strip(),
        "nombre": nombre,
        "tipo_atencion": tipo_atencion.strip(),
        "motivo": motivo.strip(),
        "plantilla": plantilla.strip(),
    }


def parsear_pacientes_objetivo(ruta: Path) -> list[PacienteObjetivo]:
    """Lista de PacienteObjetivo desde el informe (input del paso 3 --todos)."""
    if not ruta.exists():
        return []
    out: list[PacienteObjetivo] = []
    for line in ruta.read_text(encoding="utf-8").splitlines():
        fila = parsear_linea_informe(line)
        if fila is None:
            continue
        out.append(
            PacienteObjetivo(
                fecha=fila["fecha"],
                nombre=fila["nombre"],
                tipo_atencion=fila["tipo_atencion"],
                razon=fila["motivo"],  # compat: 'razon' es el nombre del campo
            )
        )
    return out


def parsear_filas_enriquecidas(ruta: Path) -> list[dict]:
    """Filas para el paso 6 (enriquecer). Acepta 5/7/8 columnas.

    Los campos edad/examenes/interconsulta/indicaciones salen en None:
    el paso 6 SIEMPRE los re-deriva de la nota clinica (REQ-041/042).
    """
    if not ruta.exists():
        return []
    filas: list[dict] = []
    for line in ruta.read_text(encoding="utf-8").splitlines():
        parts = re.split(r"\s{2,}", line.rstrip())
        if len(parts) not in (5, 7, 8, 9):
            continue
        fila = parsear_linea_informe(line)
        if fila is None:
            continue
        filas.append(
            {
                "fecha": fila["fecha"],
                "nombre": fila["nombre"],
                "tipo_atencion": fila["tipo_atencion"],
                "motivo": fila["motivo"],
                "examenes": None,
                "interconsulta": None,
                "indicaciones": None,
                "edad": None,
            }
        )
    return filas
