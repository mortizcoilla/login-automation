"""Convierte notas clinicas en formato .txt a .md en armonia con manuales_md.

Las notas originales usan el formato:
    === INICIO BLOQUE ===
    ...
    === FIN BLOQUE ===

El nuevo formato markdown replica la estructura de los manuales:
- YAML frontmatter (title, paciente, run, fecha_atencion, etc.)
- Headers (##) en vez de marcadores INICIO/FIN
- Bullets para listas (en vez de lineas planas)
- Blockquotes para motivo de atencion y flag de revision

Uso:
    python -m src.tools.convertir_notas_md             # convierte todas
    python -m src.tools.convertir_notas_md --force     # re-convierte aunque exista
    python -m src.tools.convertir_notas_md --delete    # borra los .txt despues

Las notas en .md viven en notas_clinicas/<paciente>_<fecha>.md (mismo dir).
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NOTAS_DIR = ROOT / "data" / "notas_clinicas"

# Mapeo de "=== INICIO X ===" / "=== FIN X ===" -> header markdown "## X".
# Mantiene el orden del archivo original (los manuales tambien respetan
# jerarquia visual con headers).
BLOQUES_HEADERS: dict[str, str] = {
    "IDENTIFICACION": "Identificacion",
    "HISTORIAL DE ATENCIONES": "Historial de atenciones (ultimos 6 meses)",
    "NOTA CLINICA": "Nota clinica de Yadira",
    "DIAGNOSTICOS": "Diagnosticos",
    "ESTRATIFICACION ECICEP": "Estratificacion ECICEP",
    "ACTIVIDADES": "Actividades",
    "PROFESIONALES": "Profesionales",
    "PLAN RECETAS": "Plan - Recetas",
    "PLAN LABORATORIO": "Plan - Laboratorio",
}

# Frontmatter -> inferencia desde cabecera (# Paciente:, # RUN:, etc.).
FRONTMATTER_FIELDS = (
    "title",
    "paciente",
    "paciente_rayen",
    "run",
    "fecha_atencion",
    "tipo_atencion",
)


def parsear_nota_txt(texto: str) -> dict:
    """Lee el .txt de una nota y devuelve dict con bloques + frontmatter."""
    bloques: dict[str, list[str]] = {}
    frontmatter: dict[str, str] = {}
    bloque_actual: str | None = None
    en_cabecera = True

    for line in texto.splitlines():
        if en_cabecera:
            # Cabecera: lineas "# ..." hasta encontrar bloque o vacio.
            if line.startswith("# "):
                key = line[2:].strip()
                # Mapear campos comunes.
                key_norm = (
                    key.lower()
                    .replace("á", "a")
                    .replace("é", "e")
                    .replace("í", "i")
                    .replace("ó", "o")
                    .replace("ú", "u")
                    .replace("ñ", "n")
                )
                if key_norm.startswith("nota clinica"):
                    # "# NOTA CLINICA — extraida de Rayen" -> saltar
                    continue
                if key_norm.startswith("paciente:"):
                    frontmatter["paciente"] = key.split(":", 1)[1].strip()
                    # Titulo derivado.
                    if "title" not in frontmatter:
                        frontmatter["title"] = (
                            f"Nota clinica - {frontmatter['paciente']}"
                        )
                    continue
                if key_norm.startswith("paciente (rayen):"):
                    frontmatter["paciente_rayen"] = key.split(":", 1)[1].strip()
                    continue
                if key_norm.startswith("run:"):
                    frontmatter["run"] = key.split(":", 1)[1].strip()
                    continue
                if key_norm.startswith("fecha atencion:"):
                    frontmatter["fecha_atencion"] = key.split(":", 1)[1].strip()
                    continue
                if key_norm.startswith("tipo atencion:"):
                    frontmatter["tipo_atencion"] = key.split(":", 1)[1].strip()
                    continue
                # Si no matchea ningun campo conocido, ignorar.
                continue

            # Linea vacia o "!" -> fin de cabecera.
            if line.strip() == "" or line.startswith("!"):
                en_cabecera = False
                continue
            en_cabecera = False

        # Detectar inicio/fin de bloque.
        if line.startswith("=== INICIO "):
            nombre = line.replace("=== INICIO ", "").replace(" ===", "").strip()
            # Normalizar: "NOTA CLINICA DE YADIRA" -> "NOTA CLINICA".
            if nombre == "NOTA CLINICA DE YADIRA":
                nombre = "NOTA CLINICA"
            bloque_actual = nombre
            bloques[bloque_actual] = []
            continue
        if line.startswith("=== FIN "):
            bloque_actual = None
            continue
        if line.startswith("=" * 10):
            # Separador (parte de los marcadores INICIO/FIN). Ignorar.
            continue
        if bloque_actual is not None:
            bloques[bloque_actual].append(line)

    # Post-procesar: trim trailing vacios.
    for k in bloques:
        while bloques[k] and bloques[k][-1].strip() == "":
            bloques[k].pop()

    return {"frontmatter": frontmatter, "bloques": bloques}


def bloque_a_markdown(nombre_bloque: str, lineas: list[str]) -> str:
    """Convierte las lineas de un bloque a markdown."""
    if not lineas:
        return ""
    # Header del bloque.
    header_text = BLOQUES_HEADERS.get(nombre_bloque, nombre_bloque.title())
    out = [f"## {header_text}", ""]

    if nombre_bloque == "NOTA CLINICA":
        # El motivo de atencion puede estar en una linea "Motivo de atencion: ..."
        # Bloqueamos como blockquote bold si existe.
        body: list[str] = []
        for line in lineas:
            if line.startswith("Motivo de atencion:"):
                resto = line[len("Motivo de atencion:"):].strip()
                out.append(f"> **Motivo de atencion:** {resto}")
                out.append(">")
                continue
            body.append(line)
        if body:
            out.extend(body)
            out.append("")
    elif nombre_bloque == "ACTIVIDADES":
        # Cada actividad va como bullet "- ...".
        out.extend(_a_bullets(lineas))
        out.append("")
    elif nombre_bloque in (
        "PROFESIONALES",
        "DIAGNOSTICOS",
        "PLAN RECETAS",
        "PLAN LABORATORIO",
    ):
        # Cada linea como bullet. Si la linea tiene sub-lineas (recetas),
        # las sangramos como sub-items.
        out.extend(_a_bullets_con_sublineas(lineas))
        out.append("")
    else:
        # Default: lineas planas (identificacion con pares clave:valor,
        # historial con lineas tipo fecha, etc.).
        if nombre_bloque == "IDENTIFICACION":
            out.extend(_identificacion_a_md(lineas))
        else:
            out.extend(lineas)
        out.append("")
    return "\n".join(out)


def _a_bullets(lineas: list[str]) -> list[str]:
    """Convierte lineas a bullets, descartando marcadores '(sin X)'."""
    out = []
    for line in lineas:
        s = line.strip()
        if not s:
            continue
        if s.startswith("(") and s.endswith(")"):
            # "(sin actividades)" -> nota al pie.
            out.append(f"_{s}_")
            continue
        out.append(f"- {s}")
    return out


def _a_bullets_con_sublineas(lineas: list[str]) -> list[str]:
    """Bullets donde las lineas indentadas (espacios) son sub-items."""
    out = []
    for line in lineas:
        s = line.rstrip()
        if not s.strip():
            continue
        stripped = s.lstrip()
        indent = len(s) - len(stripped)
        if indent >= 4:
            # Sub-item (mas de 4 espacios).
            out.append(f"  - {stripped}")
        elif s.startswith("(") and s.endswith(")"):
            out.append(f"_{s}_")
        else:
            # Quitar "- " inicial si existe para no duplicarlo al re-anadir.
            if stripped.startswith("- "):
                stripped = stripped[2:]
            out.append(f"- {stripped}")
    return out


def _identificacion_a_md(lineas: list[str]) -> list[str]:
    """Renderiza la tabla de identificacion como bullets clave: valor.
    Lineas tipo 'Médico de cabecera: Sin médico asignado' -> '- **Médico
    de cabecera:** Sin médico asignado'.
    """
    out = []
    for line in lineas:
        s = line.strip()
        if not s:
            continue
        if s.startswith("(") and s.endswith(")"):
            out.append(f"_{s}_")
            continue
        if ":" in s:
            k, _, v = s.partition(":")
            out.append(f"- **{k.strip()}:** {v.strip()}")
        else:
            out.append(s)
    return out


def nota_a_markdown(texto_txt: str, fecha_extraccion: str = "") -> str:
    """Convierte el texto .txt de una nota clinica a markdown."""
    parsed = parsear_nota_txt(texto_txt)
    frontmatter = parsed["frontmatter"]
    bloques = parsed["bloques"]

    # Completar frontmatter.
    if "title" not in frontmatter and "paciente" in frontmatter:
        frontmatter["title"] = f"Nota clinica - {frontmatter['paciente']}"
    if "fuente" not in frontmatter:
        frontmatter["fuente"] = (
            "Rayen APS - CESFAM Raul Cuevas, San Bernardo"
        )
    if "source_url" not in frontmatter:
        frontmatter["source_url"] = "https://clinico.rayenaps.cl/"
    if fecha_extraccion:
        frontmatter["fecha_extraccion"] = fecha_extraccion

    # Detectar flag de panel_cargo (lineas "!!! ATENCION ...").
    panel_cargo = True
    if "!!! ATENCION" in texto_txt and "NO CARGO" in texto_txt:
        panel_cargo = False
        frontmatter["panel_cargo"] = "false"
    else:
        frontmatter["panel_cargo"] = "true"

    # Renderizar frontmatter YAML.
    md = ["---"]
    for key, value in frontmatter.items():
        # Escapar comillas para YAML.
        v_safe = value.replace('"', '\\"')
        md.append(f'{key}: "{v_safe}"')
    md.append("---")
    md.append("")

    # Titulo.
    if "title" in frontmatter:
        md.append(f"# {frontmatter['title']}")
        md.append("")

    # Flag de revision si aplica.
    if not panel_cargo:
        md.append("> ⚠️ **ATENCION: panel del paciente NO CARGO en Rayen.**")
        md.append("> La nota tiene placeholders. Revisar manualmente en Rayen.")
        md.append("")

    # Bloques en orden segun el archivo original (preservando jerarquia).
    bloques_orden = [
        "IDENTIFICACION",
        "HISTORIAL DE ATENCIONES",
        "NOTA CLINICA",
        "DIAGNOSTICOS",
        "ESTRATIFICACION ECICEP",
        "ACTIVIDADES",
        "PROFESIONALES",
        "PLAN RECETAS",
        "PLAN LABORATORIO",
    ]
    for nombre in bloques_orden:
        if nombre in bloques:
            md.append(bloque_a_markdown(nombre, bloques[nombre]))

    return "\n".join(md)


def convertir_uno(txt_path: Path, force: bool = False) -> Path | None:
    """Convierte un .txt a .md. Devuelve el path .md o None si se skipeo."""
    md_path = txt_path.with_suffix(".md")
    if md_path.exists() and not force:
        logging.info(f"  SKIP {txt_path.name} (ya existe .md)")
        return None
    texto = txt_path.read_text(encoding="utf-8")
    md = nota_a_markdown(texto)
    md_path.write_text(md, encoding="utf-8")
    logging.info(f"  OK {txt_path.name} -> {md_path.name}")
    return md_path


def main() -> int:
    p = argparse.ArgumentParser(
        description="Convierte notas_clinicas/*.txt a .md."
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-convierte aunque el .md destino exista.",
    )
    p.add_argument(
        "--delete",
        action="store_true",
        help="Borra los .txt despues de convertirlos a .md.",
    )
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not NOTAS_DIR.exists():
        logging.warning(f"{NOTAS_DIR} no existe")
        return 1

    txts = sorted(NOTAS_DIR.glob("*.txt"))
    if not txts:
        logging.info(f"Ningun .txt en {NOTAS_DIR}")
        return 0

    convertidos = 0
    for txt in txts:
        result = convertir_uno(txt, force=args.force)
        if result is not None:
            convertidos += 1
            if args.delete:
                try:
                    txt.unlink()
                    logging.info(f"    DELETE {txt.name}")
                except OSError as e:
                    logging.warning(f"    No se pudo borrar {txt.name}: {e}")

    logging.info(
        f"Listo: {convertidos}/{len(txts)} convertidos"
        + (" (txts borrados)" if args.delete else "")
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())