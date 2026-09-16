"""Enriquece el informe del mes en curso con el motivo de atencion.

Se ejecuta DESPUES de crear_notas_clinicas --todos, cuando las notas
estan en notas_clinicas/.

Para cada paciente del informe, busca su nota y extrae la primera
ocurrencia de `Motivo de atencion:` que aparece DENTRO del bloque

    === INICIO NOTA CLINICA DE YADIRA ===
    ...
    === FIN NOTA CLINICA DE YADIRA ===

Reescribe el informe en su lugar agregando la columna
`Motivo de la atencion`. La columna `Razon de la cita` (que venia del
informe basico y no aportaba) ya no existe; este enriquecimiento la
sustituye.

================================================================
AISLAMIENTO (regla 2026-09-09):
- Solo toca el informe del MES EN CURSO (default).
- Rechaza el informe ANUAL (`_completo.txt`) por guard explicito.
- NO modifica notas clinicas (solo lectura).
- NO toca la DB.
- El anual queda intacto aunque se enriquezca el mensual.
================================================================

Uso:
    python -m src.analysis.enriquecer_informe                                # mes en curso
    python -m src.analysis.enriquecer_informe --informe path/al/informe.txt  # explicito
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent.parent
NOTAS_DIR = BASE_DIR / "data" / "notas_clinicas"

from src.analysis.informe_paths import informe_mes_actual_path


# Regex de fila NO se usa directamente; el parser usa re.split() y
# requiere 6 partes (basico o enriquecido tienen siempre 6 columnas;
# los campos vacios se renderizan como "(-)" para que re.split no los
# colapse con el separador). Ver _parsear_informe_basico.
# Orden de columnas (sesion 2026-09-09, pedido por Yadira):
#   Fecha | Nombre | Edad | Tipo de atencion | Motivo de la atencion | Plantilla

# Bloque Yadira: desde === INICIO NOTA CLINICA DE YADIRA === hasta
# === FIN NOTA CLINICA DE YADIRA === (o fin de archivo si no cierra).
# DOTALL para que . matchee newlines.
YADIRA_BLOCK_RE = re.compile(
    r"={3,}\s*\n\s*=== INICIO NOTA CLINICA DE YADIRA ===\s*\n=+\s*\n(.*?)(?:=+\s*\n\s*=== FIN NOTA CLINICA DE YADIRA ===|\Z)",
    re.DOTALL,
)

# Bloque Identificacion: desde === INICIO IDENTIFICACION === hasta
# === FIN IDENTIFICACION ===.
IDENTIFICACION_BLOCK_RE = re.compile(
    r"={3,}\s*\n\s*=== INICIO IDENTIFICACION ===\s*\n=+\s*\n(.*?)(?:=+\s*\n\s*=== FIN IDENTIFICACION ===|\Z)",
    re.DOTALL,
)

# Primera linea `Motivo de atencion: <valor>` dentro del bloque Yadira.
# MULTILINE para que ^/$ matcheen lineas.
MOTIVO_RE = re.compile(
    r"^Motivo de atencion:\s*(.+?)\s*$",
    re.MULTILINE,
)

# Primera linea `Edad Cronologica: <valor>` dentro del bloque
# Identificacion. Acepta tilde y sin tilde para tolerar OCR/encoding
# inconsistente.
EDAD_RE = re.compile(
    r"^Edad Cronol[oó]gica:\s*(.+?)\s*$",
    re.MULTILINE,
)


# ---------------------------------------------------------------------------
# Parser del informe basico
# ---------------------------------------------------------------------------

def _parsear_informe_basico(ruta: Path) -> list[dict[str, str]]:
    """Lee el informe (basico o enriquecido) y devuelve lista de filas.

    Requiere EXACTAMENTE 6 partes (sesion 2026-09-09, con la columna
    Edad agregada entre Nombre y Tipo). Los campos vacios en el informe
    basico se renderizan como "(-)" (marcador de faltante, consistente
    con el enriquecido) para que re.split() no los colapse con el
    separador.

    Orden: Fecha | Nombre | Edad | Tipo de atencion | Motivo | Plantilla

    Ignora headers, separadores `---`, la seccion de Distribucion, y
    lineas con cantidad de columnas != 6.
    """
    if not ruta.exists():
        return []
    filas: list[dict[str, str]] = []
    for line in ruta.read_text(encoding="utf-8").splitlines():
        parts = re.split(r"\s{2,}", line.rstrip())
        if len(parts) != 6:
            continue
        if not re.match(r"^\d{2}-\d{2}-\d{4}$", parts[0]):
            continue
        fecha, nombre, edad, tipo_atencion, motivo, plantilla = parts
        filas.append({
            "fecha": fecha,
            "nombre": nombre,
            "edad": edad,
            "tipo_atencion": tipo_atencion,
            "motivo": motivo,
            "plantilla": plantilla,
        })
    return filas


# ---------------------------------------------------------------------------
# Extraccion del motivo desde la nota clinica
# ---------------------------------------------------------------------------

def _safe_filename(nombre: str) -> str:
    """Convierte 'Eduardo Alfonso Serrano Carmona' a 'Eduardo_Alfonso_Serrano_Carmona'.

    Misma convencion que crear_notas_clinicas.py y el agente Mortadelo:
    - Strip chars no [\\w\\s-] (parentesis, comas, puntos, etc.).
    - Whitespace -> '_'.
    - Tildes y enhe se mantienen (son word chars Unicode en Python 3).
    """
    out = re.sub(r"[^\w\s\-]+", "", nombre, flags=re.UNICODE)
    out = re.sub(r"\s+", "_", out.strip())
    return out


def _extraer_motivo(nota_path: Path) -> Optional[str]:
    """Extrae 'Motivo de atencion:' del bloque Yadira de la nota.

    Devuelve:
        str  -> el motivo encontrado
        None -> la nota no existe, no se puede leer, o no tiene el campo
    La distincion entre None y string vacio es util para diagnosticar
    'nota sin el campo' vs 'nota no existe'.
    """
    if not nota_path.exists():
        return None
    try:
        text = nota_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    m = YADIRA_BLOCK_RE.search(text)
    if not m:
        return None
    bloque = m.group(1)

    m2 = MOTIVO_RE.search(bloque)
    if m2:
        return m2.group(1).strip()
    return None


def _extraer_edad(nota_path: Path) -> Optional[str]:
    """Extrae 'Edad Cronologica:' del bloque Identificacion de la nota.

    Devuelve:
        str  -> la edad encontrada (ej '40 anios 2 meses 30 dias')
        None -> la nota no existe, no se puede leer, o no tiene el campo

    Acepta tildes y sin tildes en el label (el OCR/encoding de Rayen
    a veces las pierde; ver la regex EDAD_RE).
    """
    if not nota_path.exists():
        return None
    try:
        text = nota_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    m = IDENTIFICACION_BLOCK_RE.search(text)
    if not m:
        return None
    bloque = m.group(1)

    m2 = EDAD_RE.search(bloque)
    if m2:
        return m2.group(1).strip()
    return None


# ---------------------------------------------------------------------------
# Render del informe enriquecido
# ---------------------------------------------------------------------------

# Anchos de columna (sesion 2026-09-09, incluye Edad entre Nombre y Tipo).
# _ANCHO_TOTAL es el ancho del borde '===', aproximado a la suma de
# columnas + separadores. Se redondea hacia arriba para que el border
# cubra la fila mas larga.
_ANCHO_FECHA = 12
_ANCHO_NOMBRE = 32
_ANCHO_EDAD = 24
_ANCHO_TIPO = 32
_ANCHO_MOTIVO = 24
_ANCHO_PLANTILLA = 40
_ANCHO_TOTAL = 180


def _formatear_tabla(filas: list[dict[str, str]], periodo: str) -> str:
    """Devuelve el informe completo como string, listo para escribir."""
    out = io.StringIO()

    out.write("\n")
    out.write("=" * _ANCHO_TOTAL + "\n")
    out.write(f"INFORME DE FICHAS ABIERTAS (ENRIQUECIDO) — {periodo}\n")
    out.write("=" * _ANCHO_TOTAL + "\n")
    out.write(f"Total: {len(filas)} fichas en estado 'Iniciado'\n")
    out.write("\n")

    if not filas:
        out.write("(sin fichas abiertas en este periodo)\n")
        out.write("=" * _ANCHO_TOTAL + "\n")
        return out.getvalue()

    # Orden de columnas (sesion 2026-09-09, pedido por Yadira):
    #   Fecha | Nombre | Edad | Tipo de atencion | Motivo | Plantilla
    # Edad se imprime ANTES de Tipo (entre Nombre y Tipo) para que la
    # info clinica del paciente (quien es, que edad) aparezca junta y
    # la metadata de tramite (tipo, motivo, plantilla) despues.
    header = "  ".join([
        f"{'Fecha':<{_ANCHO_FECHA}}",
        f"{'Nombre':<{_ANCHO_NOMBRE}}",
        f"{'Edad':<{_ANCHO_EDAD}}",
        f"{'Tipo de atencion':<{_ANCHO_TIPO}}",
        f"{'Motivo de la atencion':<{_ANCHO_MOTIVO}}",
        f"{'Plantilla':<{_ANCHO_PLANTILLA}}",
    ])
    out.write(header + "\n")
    out.write("-" * len(header) + "\n")

    for f in filas:
        # '(-)' = dato faltante (nota no existe, o no tiene el campo).
        # Si el dict no tiene la clave, tambien cae a '(-)'.
        edad = f.get("edad") or "(-)"
        motivo = f.get("motivo") or "(-)"
        cells = "  ".join([
            f"{f.get('fecha', '-'):<{_ANCHO_FECHA}}",
            f"{f.get('nombre', '-')[:_ANCHO_NOMBRE]:<{_ANCHO_NOMBRE}}",
            f"{edad[:_ANCHO_EDAD]:<{_ANCHO_EDAD}}",
            f"{f.get('tipo_atencion', '-')[:_ANCHO_TIPO]:<{_ANCHO_TIPO}}",
            f"{motivo[:_ANCHO_MOTIVO]:<{_ANCHO_MOTIVO}}",
            f"{f.get('plantilla', '-')[:_ANCHO_PLANTILLA]:<{_ANCHO_PLANTILLA}}",
        ])
        out.write(cells + "\n")
    out.write("=" * _ANCHO_TOTAL + "\n")

    tipos: Counter = Counter(f["tipo_atencion"] for f in filas)
    out.write("\n")
    out.write("Distribucion por tipo de atencion:\n")
    for tipo, cant in tipos.most_common():
        pct = 100 * cant / len(filas)
        out.write(f"  {tipo:<40s} {cant:3d}  ({pct:5.1f}%)\n")
    out.write("=" * _ANCHO_TOTAL + "\n")

    return out.getvalue()


def _extraer_periodo_desde_nombre(nombre: str) -> str:
    """Extrae 'MM-YYYY' o 'YYYY (completo)' del nombre del archivo."""
    m = re.search(r"_(\d{2}-\d{4})\.txt$", nombre)
    if m:
        return m.group(1)
    m = re.search(r"_(\d{4}_completo)\.txt$", nombre)
    if m:
        return f"anio {m.group(1).split('_')[0]} (completo)"
    return nombre


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Enriquece el informe del mes en curso con el motivo de "
            "atencion extraido de las notas clinicas. Reescribe el archivo "
            "en su lugar agregando la columna 'Motivo de la atencion'."
        )
    )
    p.add_argument(
        "--informe",
        type=Path,
        default=None,
        help=(
            "Path al informe a enriquecer. Default: informe del mes en curso "
            f"({informe_mes_actual_path().name})."
        ),
    )
    return p.parse_args()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    args = _parse_args()
    informe_path = args.informe or informe_mes_actual_path()

    # Guard: el anual NO se enriquece
    if "_completo" in informe_path.name:
        print(
            f"ERROR: {informe_path.name} es el informe ANUAL. "
            f"Esta operacion es solo para el mensual. Pasalo explicito "
            f"al flujo que corresponda si queres procesarlo aparte.",
            file=sys.stderr,
        )
        return 1

    if not informe_path.exists():
        print(
            f"ERROR: no existe el informe {informe_path}. "
            f"Primero genera el basico con: python -m src.analysis.informe_fichas_abiertas",
            file=sys.stderr,
        )
        return 1

    print(f"[enriquecer_informe] archivo: {informe_path.name}  (el anual NO se toca)")

    filas = _parsear_informe_basico(informe_path)
    if not filas:
        print("  no se encontraron filas para enriquecer")
        return 1

    print(f"  {len(filas)} pacientes en el informe")
    print()

    # Enriquecer cada fila con motivo y edad
    enriched_motivo = 0
    enriched_edad = 0
    missing_nota = 0
    missing_motivo = 0
    missing_edad = 0
    for fila in filas:
        fname = f"{_safe_filename(fila['nombre'])}_{fila['fecha']}.txt"
        nota_path = NOTAS_DIR / fname

        motivo = _extraer_motivo(nota_path)
        if motivo is None:
            if not nota_path.exists():
                missing_nota += 1
            else:
                missing_motivo += 1
            fila["motivo"] = "(-)"
        else:
            fila["motivo"] = motivo
            enriched_motivo += 1

        edad = _extraer_edad(nota_path)
        if edad is None:
            if not nota_path.exists():
                # ya contado arriba
                pass
            else:
                missing_edad += 1
            fila["edad"] = "(-)"
        else:
            fila["edad"] = edad
            enriched_edad += 1

        marker = []
        if not nota_path.exists():
            marker.append("sin nota")
        elif fila["motivo"] == "(-)":
            marker.append("sin Motivo")
        if fila["edad"] == "(-)" and nota_path.exists():
            marker.append("sin Edad")
        suffix = f"  [{', '.join(marker)}]" if marker else ""
        print(
            f"  {fila['nombre']:<40s} edad={fila['edad']:<25s} "
            f"motivo={fila['motivo']!r}{suffix}"
        )

    print()
    print(
        f"  motivo: {enriched_motivo} ok, {missing_motivo} sin campo, {missing_nota} sin nota\n"
        f"  edad:   {enriched_edad} ok, {missing_edad} sin campo, {missing_nota} sin nota"
    )
    print()

    periodo = _extraer_periodo_desde_nombre(informe_path.name)
    contenido = _formatear_tabla(filas, periodo)

    try:
        informe_path.write_text(contenido, encoding="utf-8")
        print(
            f"[output completo guardado en: {informe_path.relative_to(BASE_DIR)}]"
        )
    except OSError as e:
        print(f"WARN: no se pudo guardar: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
