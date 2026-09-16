"""Enriquece el informe del mes en curso con motivo, edad y requerimientos.

Se ejecuta DESPUES de crear_notas_clinicas --todos, cuando las notas
estan en notas_clinicas/.

Para cada paciente del informe, busca su nota y extrae:

1. **Motivo de atencion** del bloque Yadira (`Motivo de atencion:` o
   blockquote `> **Motivo de atencion:**`).
2. **Edad Cronologica** del bloque Identificacion.
3. **Requerimientos de Yadira a Mortadelo** (sesion 2026-09-16): detecta
   en la nota clinica el bloque `** mortadelo` con bullets como:
   - `examenes adjuntos`   -> columna "Examenes adjuntos" = si/no
   - `crear interconsulta` -> columna "Crear interconsulta" = si/no

Estos requerimientos Yadira los deja dentro del bloque anamnesis en
formato:

    ** mortadelo

    - examenes adjuntos
    - crear interconsulta

    **

La deteccion es format-agnostic (regex sobre el texto completo de la
nota, no sobre bloques parseados), asi funciona tanto con .md como con
.txt legacy.

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
from src.mortadelo.trigger import TRIGGER_RE


# Regex de fila NO se usa directamente; el parser usa re.split() y
# requiere 8 partes (basico o enriquecido tienen siempre 8 columnas;
# los campos vacios se renderizan como "(-)" para que re.split no los
# colapse con el separador). Ver _parsear_informe_basico.
# Orden de columnas:
#   Fecha | Nombre | Edad | Tipo de atencion | Motivo de la atencion
#   | Plantilla | Examenes adjuntos | Crear interconsulta
# (Sesion 2026-09-16: +2 cols de requerimientos Yadira->Mortadelo).
# Back-compat: acepta 6 cols (informe pre-2026-09-16, sin las 2 nuevas).

# Bloque Yadira: desde === INICIO NOTA CLINICA DE YADIRA === hasta
# === FIN NOTA CLINICA DE YADIRA === (o fin de archivo si no cierra).
# DOTALL para que . matchee newlines.
# Sesion 2026-09-16: ya NO se usa. Las notas son .md sin estos
# marcadores. Se conserva como referencia historica.
# YADIRA_BLOCK_RE = re.compile(
#     r"={3,}\s*\n\s*=== INICIO NOTA CLINICA DE YADIRA ===\s*\n=+\s*\n(.*?)(?:=+\s*\n\s*=== FIN NOTA CLINICA DE YADIRA ===|\Z)",
#     re.DOTALL,
# )

# Bloque Identificacion: desde === INICIO IDENTIFICACION === hasta
# === FIN IDENTIFICACION ===.
# Sesion 2026-09-16: ya NO se usa. Las notas son .md sin estos
# marcadores. Se conserva como referencia historica.
# IDENTIFICACION_BLOCK_RE = re.compile(
#     r"={3,}\s*\n\s*=== INICIO IDENTIFICACION ===\s*\n=+\s*\n(.*?)(?:=+\s*\n\s*=== FIN IDENTIFICACION ===|\Z)",
#     re.DOTALL,
# )

# Primera linea `Motivo de atencion: <valor>` en el texto de la nota.
# Sesion 2026-09-16: busqueda whole-file (no en bloque parseado) porque
# las notas .md no usan marcadores `=== INICIO/FIN ===`.
#
# Formatos aceptados (cualquier combinacion):
# - `- **Motivo de atencion:** <valor>` (.md bullet + bold)
# - `> **Motivo de atencion:** <valor>` (.md blockquote, dentro de Yadira)
# - `- Motivo de atencion: <valor>` (.md bullet sin bold)
# - `Motivo de atencion: <valor>` (.txt legacy, linea plana)
#
# El prefijo (bullet / blockquote + opcional bold) se consume con el
# non-capturing group al inicio. El valor se captura greedy hasta fin
# de linea; luego _limpiar_valor_campo() le quita `**` y espacios
# (porque Yadira puede envolver el valor en `**` para bold).
MOTIVO_RE = re.compile(
    r"(?:^|>\s*\*{0,2}\s*|-\s*\*{0,2}\s*)Motivo de atenci[oó]n:\s*(.+?)\s*$",
    re.MULTILINE,
)

# Primera linea `Edad Cronologica: <valor>` en el texto de la nota.
# Misma logica que MOTIVO_RE (whole-file, multi-formato).
#
# Formatos aceptados:
# - `- **Edad Cronologica:** <valor>` (.md bullet + bold)
# - `- Edad Cronologica: <valor>` (.md bullet sin bold)
# - `Edad Cronologica: <valor>` (.txt legacy)
EDAD_RE = re.compile(
    r"(?:^|-\s*\*{0,2}\s*)Edad Cronol[oó]gica:\s*(.+?)\s*$",
    re.MULTILINE,
)


def _limpiar_valor_campo(raw: str) -> str:
    """Limpia un valor capturado de MOTIVO_RE / EDAD_RE.

    Sesion 2026-09-16: Yadira puede envolver el valor en uno o mas
    pares de `**` (bold de markdown anidado). El regex consume el
    prefijo (bullet + bold del label) pero NO los `**` dentro del
    valor. Asi que aqui strip iterativo:
    - Strip leading/trailing whitespace
    - Mientras empiece con `** ` o termine con ` **`, los quitamos
    - Esto maneja `** ** value`, `** ** value **`, etc.
    """
    s = raw.strip()
    changed = True
    while changed:
        changed = False
        # Patron: "** value" -> "value"
        if s.startswith("** "):
            s = s[3:].strip()
            changed = True
        # Patron: "value **" -> "value"
        elif s.endswith(" **"):
            s = s[:-3].strip()
            changed = True
        # Patron: "**value" (sin espacio) -> "value"
        elif s.startswith("**"):
            s = s[2:].strip()
            changed = True
        elif s.endswith("**"):
            s = s[:-2].strip()
            changed = True
    return s

# Keywords de requerimientos Yadira->Mortadelo (sesion 2026-09-16).
# Se buscan en el texto que sigue a cada trigger `** mortadelo`.
# Case-insensitive, tolerante a tildes (examenes/exámenes) y typos comunes.
KEYWORDS_REQUERIMIENTOS = {
    "examenes_adjuntos": re.compile(
        r"ex[aá]men(?:es)?\s+adjuntos?",  # examen/examenes/exámenes
        re.IGNORECASE,
    ),
    "crear_interconsulta": re.compile(
        r"crea[r]?\s+interconsulta",  # crear/crear/crea (typo)
        re.IGNORECASE,
    ),
}


# ---------------------------------------------------------------------------
# Parser del informe basico
# ---------------------------------------------------------------------------

def _parsear_informe_basico(ruta: Path) -> list[dict[str, str]]:
    """Lee el informe (basico o enriquecido) y devuelve lista de filas.

    Sesion 2026-09-16: acepta 6 u 8 columnas. Si vienen 6, las 2 nuevas
    (examenes_adjuntos, crear_interconsulta) quedan vacias y se
    enriquecen despues. Si vienen 8, ya estan pobladas (re-corrida) y
    se re-enriquecen (sobrescribe). Los campos vacios se renderizan
    como "(-)" para que re.split() no los colapse con el separador.

    Orden 8 cols (sesion 2026-09-16, pedido por Yadira):
        Fecha | Nombre | Edad | Tipo de atencion | Motivo | Plantilla
        | Examenes adjuntos | Crear interconsulta

    Ignora headers, separadores `---`, la seccion de Distribucion, y
    lineas con cantidad de columnas != 6 y != 8.
    """
    if not ruta.exists():
        return []
    filas: list[dict[str, str]] = []
    for line in ruta.read_text(encoding="utf-8").splitlines():
        parts = re.split(r"\s{2,}", line.rstrip())
        if len(parts) not in (6, 8):
            continue
        if not re.match(r"^\d{2}-\d{2}-\d{4}$", parts[0]):
            continue
        fecha, nombre, edad, tipo_atencion, motivo, plantilla = parts[:6]
        fila = {
            "fecha": fecha,
            "nombre": nombre,
            "edad": edad,
            "tipo_atencion": tipo_atencion,
            "motivo": motivo,
            "plantilla": plantilla,
        }
        # Si vienen 8 cols, las 2 nuevas ya tienen datos (re-corrida)
        if len(parts) == 8:
            fila["examenes_adjuntos"] = parts[6]
            fila["crear_interconsulta"] = parts[7]
        filas.append(fila)
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
    """Extrae 'Motivo de atencion:' del texto de la nota.

    Sesion 2026-09-16: cambio a busqueda format-agnostic (whole-file)
    porque las notas son .md con frontmatter y NO usan los marcadores
    `=== INICIO/FIN ===` del formato .txt legacy.

    Formatos soportados:
    - `.md` (actual): `- **Motivo de atencion:**` (bullet + bold) o
      `> **Motivo de atencion:**` (blockquote en bloque Yadira)
    - `.txt` (legacy): `Motivo de atencion:` (linea plana)

    Devuelve:
        str  -> el motivo encontrado (trimmed)
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
    if not text:
        return None

    # Sesion 2026-09-16: buscar en el texto completo (no en bloques
    # parseados). El .md actual pone el motivo como blockquote dentro
    # del bloque Yadira, fuera de cualquier marcador.
    m = MOTIVO_RE.search(text)
    if m:
        return _limpiar_valor_campo(m.group(1))
    return None


def _extraer_edad(nota_path: Path) -> Optional[str]:
    """Extrae 'Edad Cronologica:' del texto de la nota.

    Sesion 2026-09-16: cambio a busqueda format-agnostic (whole-file)
    por la misma razon que _extraer_motivo().

    Formatos soportados:
    - `.md` (actual): `- **Edad Cronologica:**` (bullet + bold)
    - `.txt` (legacy): `Edad Cronologica:` (linea plana)

    Acepta tildes y sin tildes en el label (el OCR/encoding de Rayen
    a veces las pierde; ver la regex EDAD_RE).

    Devuelve:
        str  -> la edad encontrada (ej '40 anios 2 meses 30 dias')
        None -> la nota no existe, no se puede leer, o no tiene el campo
    """
    if not nota_path.exists():
        return None
    try:
        text = nota_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not text:
        return None

    # Sesion 2026-09-16: whole-file search (mismo approach que motivo)
    m = EDAD_RE.search(text)
    if m:
        return _limpiar_valor_campo(m.group(1))
    return None


def _extraer_requerimientos(nota_path: Path) -> dict[str, bool]:
    """Detecta los requerimientos de Yadira a Mortadelo en la nota clinica.

    Sesion 2026-09-16 (pedido por Yadira): la nota clinica puede tener
    un bloque `** mortadelo` con bullets listando lo que Mortadelo debe
    hacer. Por ahora se trackean 2 requerimientos:

    - `examenes adjuntos`   -> True si esta en algun bloque trigger
    - `crear interconsulta` -> True si esta en algun bloque trigger

    Formato esperado (Yadira escribe asi en la anamnesis):
        ** mortadelo

        - examenes adjuntos
        - crear interconsulta

        **

    Deteccion format-agnostic: busca `** mortadelo` con TRIGGER_RE,
    luego mira el texto que sigue al trigger (hasta el proximo trigger
    o fin de archivo) y testea los keywords.

    Args:
        nota_path: ruta al .md (o .txt legacy) en data/notas_clinicas/.

    Returns:
        dict con keys 'examenes_adjuntos' y 'crear_interconsulta',
        ambas bool. Si la nota no existe, ambas False.
    """
    resultado = {"examenes_adjuntos": False, "crear_interconsulta": False}

    if not nota_path.exists():
        return resultado
    try:
        text = nota_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return resultado

    if not text:
        return resultado

    # Encontrar todos los triggers ** mortadelo en la nota
    matches = list(TRIGGER_RE.finditer(text))
    if not matches:
        return resultado

    # Para cada trigger, examinar el texto hasta el proximo trigger
    # (o fin de archivo)
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        bloque = text[start:end]

        for key, regex in KEYWORDS_REQUERIMIENTOS.items():
            if not resultado[key] and regex.search(bloque):
                resultado[key] = True

    return resultado


# ---------------------------------------------------------------------------
# Render del informe enriquecido
# ---------------------------------------------------------------------------

# Anchos de columna (sesion 2026-09-16, incluye 2 cols nuevas de
# requerimientos Yadira->Mortadelo: Examenes adjuntos y Crear
# interconsulta). _ANCHO_TOTAL es el ancho del borde '===',
# aproximado a la suma de columnas + separadores.
_ANCHO_FECHA = 12
_ANCHO_NOMBRE = 32
_ANCHO_EDAD = 24
_ANCHO_TIPO = 32
_ANCHO_MOTIVO = 24
_ANCHO_PLANTILLA = 40
_ANCHO_EXAMENES_ADJUNTOS = 18
_ANCHO_CREAR_INTERCONSULTA = 20
_ANCHO_TOTAL = 222


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

    # Orden de columnas (sesion 2026-09-16, pedido por Yadira):
    #   Fecha | Nombre | Edad | Tipo de atencion | Motivo | Plantilla
    #   | Examenes adjuntos | Crear interconsulta
    # Edad se imprime ANTES de Tipo (entre Nombre y Tipo) para que la
    # info clinica del paciente (quien es, que edad) aparezca junta y
    # la metadata de tramite (tipo, motivo, plantilla) despues.
    # Las 2 ultimas columnas son requerimientos que Yadira deja a
    # Mortadelo en el bloque ** mortadelo de la anamnesis.
    header = "  ".join([
        f"{'Fecha':<{_ANCHO_FECHA}}",
        f"{'Nombre':<{_ANCHO_NOMBRE}}",
        f"{'Edad':<{_ANCHO_EDAD}}",
        f"{'Tipo de atencion':<{_ANCHO_TIPO}}",
        f"{'Motivo de la atencion':<{_ANCHO_MOTIVO}}",
        f"{'Plantilla':<{_ANCHO_PLANTILLA}}",
        f"{'Examenes adjuntos':<{_ANCHO_EXAMENES_ADJUNTOS}}",
        f"{'Crear interconsulta':<{_ANCHO_CREAR_INTERCONSULTA}}",
    ])
    out.write(header + "\n")
    out.write("-" * len(header) + "\n")

    for f in filas:
        # '(-)' = dato faltante (nota no existe, o no tiene el campo).
        # Si el dict no tiene la clave, tambien cae a '(-)'.
        edad = f.get("edad") or "(-)"
        motivo = f.get("motivo") or "(-)"
        examenes = "si" if f.get("examenes_adjuntos") else "no"
        ic = "si" if f.get("crear_interconsulta") else "no"
        cells = "  ".join([
            f"{f.get('fecha', '-'):<{_ANCHO_FECHA}}",
            f"{f.get('nombre', '-')[:_ANCHO_NOMBRE]:<{_ANCHO_NOMBRE}}",
            f"{edad[:_ANCHO_EDAD]:<{_ANCHO_EDAD}}",
            f"{f.get('tipo_atencion', '-')[:_ANCHO_TIPO]:<{_ANCHO_TIPO}}",
            f"{motivo[:_ANCHO_MOTIVO]:<{_ANCHO_MOTIVO}}",
            f"{f.get('plantilla', '-')[:_ANCHO_PLANTILLA]:<{_ANCHO_PLANTILLA}}",
            f"{examenes:<{_ANCHO_EXAMENES_ADJUNTOS}}",
            f"{ic:<{_ANCHO_CREAR_INTERCONSULTA}}",
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
            "Enriquece el informe del mes en curso con motivo, edad y "
            "requerimientos Yadira->Mortadelo extraidos de las notas "
            "clinicas. Reescribe el archivo en su lugar agregando las "
            "columnas 'Motivo de la atencion', 'Edad', 'Examenes adjuntos' "
            "y 'Crear interconsulta'."
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

    # Enriquecer cada fila con motivo, edad y requerimientos Yadira
    enriched_motivo = 0
    enriched_edad = 0
    enriched_examenes = 0
    enriched_ic = 0
    missing_nota = 0
    missing_motivo = 0
    missing_edad = 0
    for fila in filas:
        fname = f"{_safe_filename(fila['nombre'])}_{fila['fecha']}.md"
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

        # Requerimientos Yadira -> Mortadelo (sesion 2026-09-16)
        reqs = _extraer_requerimientos(nota_path)
        fila["examenes_adjuntos"] = reqs["examenes_adjuntos"]
        fila["crear_interconsulta"] = reqs["crear_interconsulta"]
        if reqs["examenes_adjuntos"]:
            enriched_examenes += 1
        if reqs["crear_interconsulta"]:
            enriched_ic += 1

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
            f"motivo={fila['motivo']!r}{suffix} "
            f"examenes={('si' if reqs['examenes_adjuntos'] else 'no')} "
            f"ic={('si' if reqs['crear_interconsulta'] else 'no')}"
        )

    print()
    print(
        f"  motivo:    {enriched_motivo} ok, {missing_motivo} sin campo, {missing_nota} sin nota\n"
        f"  edad:      {enriched_edad} ok, {missing_edad} sin campo, {missing_nota} sin nota\n"
        f"  examenes:  {enriched_examenes} con requerimiento, {len(filas) - enriched_examenes} sin\n"
        f"  IC:        {enriched_ic} con requerimiento, {len(filas) - enriched_ic} sin"
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
