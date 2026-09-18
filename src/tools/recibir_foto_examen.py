"""Rubicita — recibe examenes de Yadira (Telegram u otras fuentes) y los
RENOMBRA + ARCHIVA en `data/Examenes_crudos/`.

Alcance (decision Yadira/Miguel 2026-09-17):
  1. Recibe una imagen (path local descargado de Telegram o de donde sea).
  2. Si Yadira solo dio nombre parcial y/o fecha incorrecta, busca el
     match en `data/notas_clinicas/` y resuelve el nombre completo + la
     fecha real de la atencion.
  3. RENOMBRA con la convencion:
        <paciente_corto>_<n>_<dd-mm-aaaa>.<ext>
  4. ARCHIVA en `data/Examenes_crudos/`.

NO hace:
  - NO OCR / LLM vision.
  - NO archivado en `data/adjuntos/`.
  - NO archivado en `data/examenes/`.
  - NO clasificacion por tipo de examen.
  - NO re-encode de la imagen (es copia byte-a-bit).

Convencion de nombre:
    <paciente_corto>_<n>_<dd-mm-aaaa>.<ext>
Donde:
- paciente_corto: nombre que Yadira dio, normalizado (lowercase, sin
  tildes, espacios a `_`). Si se encontro match en data/notas_clinicas/,
  se usa el nombre COMPLETO del informe (resuelve "Benedicto Martin" a
  "Benedicto_Alfonso_Martin_Colimil").
- n: indice secuencial (1, 2, 3, ...) en el orden que Yadira mando las
  fotos en el mismo mensaje.
- dd-mm-aaaa: fecha de la atencion clinica. Si Yadira dio una fecha
  incorrecta (ej: la de hoy cuando los examenes son del 16), Rubicita
  busca en data/notas_clinicas/ y usa la fecha del informe.
- ext: extension original (.jpg, .jpeg, .png, .pdf, .webp). NO cambiar.

Uso:
    # Caso completo: Yadira da nombre completo + fecha
    python -m src.tools.recibir_foto_examen \\
        --input "C:/tmp/foto1.jpg" \\
        --paciente "Benedicto Alfonso Martin Colimil" \\
        --fecha 16-09-2026 \\
        --indice 1

    # Caso parcial: Yadira solo da "Benedicto Martin" + fecha de hoy
    python -m src.tools.recibir_foto_examen \\
        --input "C:/tmp/foto1.jpg" \\
        --paciente "Benedicto Martin" \\
        --indice 1
    # Rubicita busca en data/notas_clinicas/ y resuelve:
    #   nombre completo = "Benedicto Alfonso Martin Colimil"
    #   fecha            = "16-09-2026"

    # Caso sin fecha: Rubicita toma la fecha del match
    python -m src.tools.recibir_foto_examen \\
        --input "C:/tmp/foto1.jpg" \\
        --paciente "Benedicto Martin" \\
        --indice 1
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Optional


# Repo root (este archivo vive en src/tools/, subimos 2 niveles).
ROOT = Path(__file__).resolve().parents[2]

# UNICO directorio de salida de los examenes.
DESTINO_DIR = ROOT / "data" / "Examenes_crudos"

# Fuente de verdad para resolver matches de paciente y fecha.
NOTAS_DIR = ROOT / "data" / "notas_clinicas"

# Extensiones aceptadas.
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff",
    ".pdf",
}


def normalizar_texto(texto: str) -> str:
    """Quita tildes, pasa a minusculas, colapsa espacios/guiones."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[\s_]+", " ", sin_tildes).strip().lower()


def nombre_a_filename(nombre: str) -> str:
    """Normaliza un nombre para usarlo como parte de un nombre de archivo.
    lowercase, sin tildes, espacios a `_`.
    """
    return re.sub(r"\s+", "_", normalizar_texto(nombre))


def _parsear_frontmatter(texto: str) -> dict[str, str]:
    """Extrae los campos `key: "value"` del frontmatter YAML al inicio del .md.

    Solo soporta strings simples entre comillas dobles. Suficiente para
    el frontmatter que `crear_notas_clinicas` emite.
    """
    out: dict[str, str] = {}
    if not texto.startswith("---"):
        return out
    fin = texto.find("\n---", 3)
    if fin < 0:
        return out
    bloque = texto[3:fin]
    for m in re.finditer(r'^([a-zA-Z_][\w]*)\s*:\s*"([^"]*)"', bloque, re.MULTILINE):
        out[m.group(1)] = m.group(2)
    return out


def _indexar_notas_clinicas(notas_dir: Path) -> list[dict[str, str]]:
    """Lee todos los .md en notas_dir y extrae {paciente, fecha_atencion, file}.

    Si el directorio no existe, retorna lista vacia (matching deshabilitado).
    """
    if not notas_dir.exists():
        return []
    out: list[dict[str, str]] = []
    for path in sorted(notas_dir.glob("*.md")):
        try:
            texto = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta = _parsear_frontmatter(texto)
        paciente = meta.get("paciente", "").strip()
        fecha = meta.get("fecha_atencion", "").strip()
        if paciente and fecha:
            out.append({
                "paciente": paciente,
                "paciente_norm": normalizar_texto(paciente),
                "fecha_atencion": fecha,
                "file": path.name,
            })
    return out


def buscar_match_paciente(
    nombre_yadira: str,
    indice: list[dict[str, str]],
) -> Optional[dict[str, str]]:
    """Busca en el indice el paciente cuyo nombre matchee con lo que Yadira dijo.

    Matching por tokens:
    - Normaliza ambos (lowercase, sin tildes).
    - Cuenta cuantos tokens del nombre Yadira aparecen en el nombre completo.
    - Si >= 1 token coincide, es candidato.
    - Si hay varios candidatos, se prefiere el de fecha mas reciente
      (Yadira probablemente esta hablando del paciente activo).
    - Si no hay match, retorna None.

    Args:
        nombre_yadira: nombre tal como Yadira lo escribio
                       (ej: "Benedicto Martin", "pericode").
        indice: lista de dicts {paciente, paciente_norm, fecha_atencion, file}
                (tipicamente el resultado de _indexar_notas_clinicas).

    Returns:
        dict {paciente, fecha_atencion, file} del match, o None.
    """
    if not nombre_yadira.strip() or not indice:
        return None
    yadira_norm = normalizar_texto(nombre_yadira)
    tokens_yadira = [t for t in yadira_norm.split() if len(t) >= 3]

    candidatos: list[tuple[int, dict[str, str]]] = []
    for entry in indice:
        nombre_norm = entry["paciente_norm"]
        tokens_nombre = set(nombre_norm.split())
        coincidencias = sum(1 for t in tokens_yadira if t in tokens_nombre)
        if coincidencias > 0:
            candidatos.append((coincidencias, entry))

    if not candidatos:
        return None

    # Ordenar por: mas coincidencias primero, luego fecha mas reciente.
    candidatos.sort(
        key=lambda x: (x[0], x[1]["fecha_atencion"]),
        reverse=True,
    )
    return candidatos[0][1]


def construir_nombre_destino(
    paciente_norm_filename: str,
    fecha_dd_mm_yyyy: str,
    indice_n: int,
    extension: str,
) -> str:
    """Construye el nombre: <paciente>_<n>_<dd-mm-aaaa>.<ext>"""
    ext = extension.lower().lstrip(".")
    return f"{paciente_norm_filename}_{indice_n}_{fecha_dd_mm_yyyy}.{ext}"


def resolver_path_sin_colision(destino_dir: Path, nombre: str) -> Path:
    """Si el archivo existe, agrega _v2, _v3, ... NUNCA sobrescribe."""
    candidato = destino_dir / nombre
    if not candidato.exists():
        return candidato
    stem = candidato.stem
    suffix = candidato.suffix
    n = 2
    while True:
        nuevo = destino_dir / f"{stem}_v{n}{suffix}"
        if not nuevo.exists():
            return nuevo
        n += 1
        if n > 999:
            raise RuntimeError(f"Demasiadas colisiones para {nombre}")


def recibir_y_archivar(
    input_path: Path,
    indice_n: int,
    nombre_paciente: Optional[str] = None,
    fecha_atencion: Optional[str] = None,
    notas_dir: Path = NOTAS_DIR,
    destino_dir: Path = DESTINO_DIR,
) -> dict:
    """Recibe una imagen, resuelve paciente/fecha (si falta) y archiva.

    Args:
        input_path: ruta al archivo tal como llego (descargado de Telegram
            o de donde sea). Se copia BIT-A-BIT (shutil.copy2).
        indice_n: numero de orden de la foto en el mensaje (1, 2, 3, ...).
        nombre_paciente: nombre que dio Yadira (puede ser parcial, ej:
            "Benedicto Martin"). Si None o vacio, NO se busca match y el
            archivo falla (Yadira debe dar el nombre).
        fecha_atencion: fecha dd-mm-yyyy (puede ser la de hoy cuando
            Yadira envia tarde). Si None o vacio, se usa la fecha del match.
        notas_dir: directorio con las notas clinicas (fuente del match).
        destino_dir: directorio destino (default: data/Examenes_crudos/).

    Returns:
        dict con:
          - ok: bool
          - path: ruta absoluta del archivo archivado
          - nombre: nombre del archivo archivado
          - paciente_input: nombre que dio Yadira
          - paciente_matcheado: nombre completo del match (o None si no hubo)
          - paciente_resuelto: nombre final usado para el archivo
          - fecha_input: fecha que dio Yadira (o None)
          - fecha_matcheada: fecha del match (o None)
          - fecha_resuelta: fecha final usada para el archivo
          - indice: indice usado
          - match_candidatos: numero de candidatos encontrados
          - match_seleccionado: nombre del archivo del match seleccionado
          - tamano_kb: tamano del archivo
          - error: mensaje de error si ok=False
    """
    resultado = {
        "ok": False,
        "path": "",
        "nombre": "",
        "paciente_input": nombre_paciente or "",
        "paciente_matcheado": "",
        "paciente_resuelto": "",
        "fecha_input": fecha_atencion or "",
        "fecha_matcheada": "",
        "fecha_resuelta": "",
        "fecha_input_descartada": False,
        "motivo_descarte": "",
        "indice": indice_n,
        "match_candidatos": 0,
        "match_seleccionado": "",
        "tamano_kb": 0,
        "error": "",
    }

    # 1. Validar input
    if not input_path.exists():
        resultado["error"] = f"Archivo no existe: {input_path}"
        return resultado
    if not input_path.is_file():
        resultado["error"] = f"No es un archivo: {input_path}"
        return resultado

    extension = input_path.suffix.lower()
    if extension not in IMAGE_EXTENSIONS:
        resultado["error"] = (
            f"Extension '{extension}' no aceptada. "
            f"Aceptadas: {sorted(IMAGE_EXTENSIONS)}"
        )
        return resultado

    # 2. Validar indice
    if indice_n < 1:
        resultado["error"] = f"Indice debe ser >= 1, recibio {indice_n}"
        return resultado

    # 3. Resolver paciente y fecha
    indice_notas = _indexar_notas_clinicas(notas_dir)
    paciente_resuelto = ""
    fecha_resuelta = ""
    match_seleccionado = ""
    fecha_input_descartada = False
    motivo_descarte = ""

    if nombre_paciente and nombre_paciente.strip():
        # Tenemos nombre de Yadira. Buscar match por tokens.
        match = buscar_match_paciente(nombre_paciente, indice_notas)
        if match:
            # Match encontrado: usar nombre completo del informe.
            paciente_resuelto = match["paciente"]
            match_seleccionado = match["file"]
            resultado["paciente_matcheado"] = paciente_resuelto
            resultado["match_seleccionado"] = match_seleccionado
            resultado["match_candidatos"] = sum(
                1 for e in indice_notas
                if any(
                    t in e["paciente_norm"].split()
                    for t in normalizar_texto(nombre_paciente).split()
                    if len(t) >= 3
                )
            )

            # La fecha del informe es la fuente de verdad. Si Yadira dio
            # una fecha y coincide, OK. Si dio otra o no dio, usamos la
            # del informe (la fecha del informe es la fecha REAL de la
            # atencion clinica, no la fecha en que Yadira envio el
            # examen por Telegram).
            fecha_informe = match["fecha_atencion"]
            resultado["fecha_matcheada"] = fecha_informe

            if fecha_atencion and fecha_atencion.strip():
                fecha_input = fecha_atencion.strip()
                try:
                    datetime.strptime(fecha_input, "%d-%m-%Y")
                except ValueError:
                    resultado["error"] = (
                        f"Fecha '{fecha_input}' no es valida (dd-mm-yyyy)"
                    )
                    return resultado
                if fecha_input != fecha_informe:
                    # Yadira dio fecha distinta del informe. Probablemente
                    # puso la fecha de hoy cuando la atencion fue antes.
                    # Usamos la del informe (fuente de verdad) y marcamos.
                    fecha_input_descartada = True
                    motivo_descarte = (
                        f"Yadira dio '{fecha_input}' pero el informe dice "
                        f"'{fecha_informe}'. Usando la del informe."
                    )
                    fecha_resuelta = fecha_informe
                else:
                    fecha_resuelta = fecha_input
            else:
                # Yadira no dio fecha. Usar la del informe.
                fecha_resuelta = fecha_informe
        else:
            # No hay match. Usar lo que Yadira dio (si dio).
            paciente_resuelto = nombre_paciente.strip()
            if fecha_atencion and fecha_atencion.strip():
                fecha_input = fecha_atencion.strip()
                try:
                    datetime.strptime(fecha_input, "%d-%m-%Y")
                    fecha_resuelta = fecha_input
                except ValueError:
                    resultado["error"] = (
                        f"Fecha '{fecha_input}' no es valida (dd-mm-yyyy) "
                        f"y no se encontro match en notas_clinicas/ para "
                        f"resolver la fecha."
                    )
                    return resultado
            else:
                resultado["error"] = (
                    f"Yadira no dio fecha y no se encontro match en "
                    f"notas_clinicas/ para el paciente '{nombre_paciente}'."
                )
                return resultado
    else:
        # Yadira no dio nombre.
        resultado["error"] = (
            "Yadira debe dar el nombre del paciente. Rubicita NO adivina."
        )
        return resultado

    # 4. Validar fecha resuelta
    try:
        datetime.strptime(fecha_resuelta, "%d-%m-%Y")
    except ValueError as e:
        resultado["error"] = f"Fecha resuelta invalida '{fecha_resuelta}': {e}"
        return resultado

    # 5. Construir nombre y resolver colision
    try:
        destino_dir.mkdir(parents=True, exist_ok=True)
        paciente_filename = nombre_a_filename(paciente_resuelto)
        nombre_destino = construir_nombre_destino(
            paciente_filename, fecha_resuelta, indice_n, extension
        )
        destino = resolver_path_sin_colision(destino_dir, nombre_destino)
    except Exception as e:
        resultado["error"] = f"Error construyendo path destino: {e}"
        return resultado

    # 6. Copiar BIT-A-BIT
    try:
        shutil.copy2(input_path, destino)
    except Exception as e:
        resultado["error"] = f"Error copiando a {destino}: {e}"
        return resultado

    resultado.update({
        "ok": True,
        "path": str(destino),
        "nombre": destino.name,
        "paciente_resuelto": paciente_resuelto,
        "fecha_resuelta": fecha_resuelta,
        "fecha_input_descartada": fecha_input_descartada,
        "motivo_descarte": motivo_descarte,
        "tamano_kb": destino.stat().st_size // 1024,
    })
    return resultado


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Rubicita: recibe un examen (Telegram u otra fuente), "
            "resuelve paciente/fecha contra data/notas_clinicas/ si hace falta, "
            "lo RENOMBRA con la convencion <paciente>_<n>_<dd-mm-aaaa>.<ext> "
            "y lo ARCHIVA en data/Examenes_crudos/. Solo eso."
        )
    )
    p.add_argument(
        "--input", required=True,
        help="Ruta al archivo de imagen (descargado de Telegram, Rayen, etc.).",
    )
    p.add_argument(
        "--paciente", required=True,
        help=(
            "Nombre del paciente tal como Yadira lo escribio. "
            "Puede ser parcial (ej: 'Benedicto Martin'). "
            "Rubicita busca el nombre completo en data/notas_clinicas/."
        ),
    )
    p.add_argument(
        "--fecha", default=None,
        help=(
            "Fecha de la atencion dd-mm-yyyy. Opcional. "
            "Si Yadira envia con la fecha de hoy cuando la atencion fue antes, "
            "Rubicita usa la fecha del match en data/notas_clinicas/."
        ),
    )
    p.add_argument(
        "--indice", required=True, type=int,
        help="Indice secuencial de la foto en el mensaje (1, 2, 3, ...).",
    )
    p.add_argument(
        "--destino", default=None,
        help=f"Directorio destino (default: {DESTINO_DIR}).",
    )
    p.add_argument(
        "--notas-dir", default=None,
        help=f"Directorio de notas clinicas para matching (default: {NOTAS_DIR}).",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    destino = Path(args.destino) if args.destino else DESTINO_DIR
    notas = Path(args.notas_dir) if args.notas_dir else NOTAS_DIR
    resultado = recibir_y_archivar(
        input_path=Path(args.input),
        indice_n=args.indice,
        nombre_paciente=args.paciente,
        fecha_atencion=args.fecha,
        notas_dir=notas,
        destino_dir=destino,
    )
    print(json.dumps(resultado, ensure_ascii=False, indent=2))
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())