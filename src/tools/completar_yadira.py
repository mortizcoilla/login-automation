"""Enriquece el bloque "## Nota clinica de Yadira" de las notas clinicas.

Sesion 2026-09-16 (corregido 13:42 tras feedback de Yadira): el bloque
Yadira contiene la **anamnesis cruda** que Yadira lleno en Rayen al abrir
la ficha. Este script orquesta el ENRIQUECIMIENTO de esa anamnesis con
informacion cruzada de la nota estructurada + manuales MINSAL + conocimiento
medico del LLM.

Flujo:
1. Lee una nota de `notas_clinicas/<paciente>_<fecha>.md` (que ya tiene la
   anamnesis cruda en el bloque Yadira, mas los otros bloques estructurados).
2. Construye un prompt que contiene:
   - Los OTROS bloques de la nota (identificacion, historial, diagnosticos,
     estratificacion, actividades, profesionales, plan) como contexto.
   - Lista de manuales disponibles en `manuales_md/` para que el LLM
     pueda citarlos con [manual: minsal-ECICEP, p.42].
   - Instrucciones claras: "eres un medico experto; toma la anamnesis
     cruda de Yadira como insumo principal y enriquécela con info
     cruzada de los bloques estructurados + manuales + conocimiento
     medico. Cita fuentes con [manual: id, p.N]".
3. Invoca al LLM via `opencode` (CLI agent con system prompt medico).
4. Reemplaza la anamnesis cruda del bloque Yadira con la version
   enriquecida del LLM.
5. Guarda la nota enriquecida en
   `notas_clinicas_completadas/<paciente>_<fecha>.md`.

Estado actual: skeleton listo. La llamada al LLM (#3) esta marcada como
TODO porque vive en la zona a corregir (Mortadelo/opencode). Cuando
Yadira (o Mortadelo en la proxima sesion) implemente la integracion con
opencode, este script queda como punto de entrada.

Uso:
    python -m src.tools.completar_yadira                      # procesa todas las notas pendientes
    python -m src.tools.completar_yadira --nota <path>       # procesa 1 nota especifica
    python -m src.tools.completar_yadira --dry-run            # muestra el prompt sin invocar LLM
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
NOTAS_DIR = ROOT / "notas_clinicas"
NOTAS_COMPLETADAS_DIR = ROOT / "notas_clinicas_completadas"
MANUALES_DIR = ROOT / "manuales_md"


def leer_bloques_nota(nota_md: str) -> dict[str, str]:
    """Lee un .md de nota y devuelve dict con los bloques por nombre.

    Cada bloque va del `## Nombre` al siguiente `## Nombre` (o fin de archivo).
    El frontmatter (--- al inicio) se ignora.
    """
    bloques: dict[str, str] = {}
    nombre_actual: str | None = None
    contenido_actual: list[str] = []
    en_frontmatter = True

    for line in nota_md.splitlines():
        if en_frontmatter:
            if line.strip() == "---":
                en_frontmatter = False
            continue
        if line.startswith("## "):
            # Cierra bloque anterior.
            if nombre_actual is not None:
                bloques[nombre_actual] = "\n".join(contenido_actual).strip()
            nombre_actual = line[3:].strip()
            contenido_actual = []
        else:
            contenido_actual.append(line)

    # Cierra ultimo bloque.
    if nombre_actual is not None:
        bloques[nombre_actual] = "\n".join(contenido_actual).strip()
    return bloques


def construir_prompt(
    bloques: dict[str, str],
    manuales_disponibles: list[str],
    paciente_dict: dict[str, str] | None = None,
) -> str:
    """Construye el prompt que se envia al LLM para enriquecer el bloque Yadira.

    Args:
        bloques: dict con los bloques extraidos de la nota (incluye el
            bloque "Nota clinica de Yadira" con la anamnesis CRUDA de
            Yadira como insumo principal).
        manuales_disponibles: lista de IDs de manuales (nombres de carpeta
            en manuales_md/) que el LLM puede leer/consultar.
        paciente_dict: opcional, datos del paciente (RUN, edad, etc.)
            extraidos del frontmatter.

    Returns:
        Prompt completo en markdown. El LLM debe responder con la version
        ENRIQUECIDA del bloque "## Nota clinica de Yadira" (sin la
        seccion ni el titulo).
    """
    anamnesis_cruda = bloques.get("Nota clinica de Yadira", "").strip()

    prompt = """# TAREA

Eres un **medico experto** (medico familiar / internista chileno, MINSAL CESFAM).
Tu trabajo es **enriquecer la nota clinica de Yadira** que esta en el bloque
"## Nota clinica de Yadira" del archivo de entrada.

# INSUMO PRINCIPAL: ANAMNESIS CRUDA DE YADIRA

Este es el texto que Yadira escribio en Rayen al abrir la ficha del paciente.
ES LA FUENTE PRIMARIA de tu trabajo. NO la descartes, NO la reescribas de
cero. Tu rol es **enriquecerla** con informacion cruzada de los bloques
estructurados, los manuales MINSAL disponibles, y tu propio conocimiento
medico. Lo que Yadira ya escribio se preserva (puede ser parafraseado
ligeramente, pero el contenido clinico no se pierde).

```
"""
    prompt += anamnesis_cruda if anamnesis_cruda else "_(sin anamnesis)_"
    prompt += "\n```\n\n"

    prompt += """# DATOS DEMOGRAFICOS DEL PACIENTE

"""
    if paciente_dict:
        for k, v in paciente_dict.items():
            prompt += f"- **{k}:** {v}\n"
    else:
        prompt += "_(no disponibles)_\n"
    prompt += "\n"

    prompt += "# BLOQUES YA EXTRAIDOS (contexto)\n\n"
    for nombre in [
        "Identificacion",
        "Historial de atenciones (ultimos 6 meses)",
        "Diagnosticos",
        "Estratificacion ECICEP",
        "Actividades",
        "Profesionales",
        "Plan - Recetas",
        "Plan - Laboratorio",
    ]:
        if nombre in bloques and nombre != "Nota clinica de Yadira":
            prompt += f"## {nombre}\n\n"
            prompt += bloques[nombre] or "_(vacio)_"
            prompt += "\n\n"

    prompt += """# INSTRUCCIONES PARA ENRIQUECER LA ANAMNESIS DE YADIRA

Tu trabajo es tomar la anamnesis cruda de Yadira (el insumo principal
arriba) y producir una version enriquecida que conserve su contenido
clinico pero agregue:

1. **Contexto cruzado**: integra los datos estructurados (diagnosticos,
   historial, actividades) con la anamnesis. Si Yadira menciono "control
   de HTA" y el bloque Diagnosticos tiene I10X, conectalos con evidencia
   clinica de los manuales MINSAL.

2. **Examen fisico**: si la anamnesis menciona sintomas que requieren
   examen fisico especifico, agregalo (ej: "soplo carotideo" sugiere
   describir pulsos, PA en 4 extremidades).

3. **Impresion diagnostica**: integrando los diagnosticos existentes con
   el cuadro clinico de la anamnesis.

4. **Plan**: indicaciones, controles, derivaciones segun manuales.

5. **Red flags**: senales de alarma para esta patologia + este paciente.

Cada sugerencia/afirmacion clinica NO obvia debe citar fuente:
    [manual: minsal-ECICEP, p.42]

# MANUALES DISPONIBLES (consultables)

Tienes acceso a estos manuales en `manuales_md/<id>/<id>.md` (frontmatter
YAML con `title`, `source`, `source_url`, `pages`). Citálos en formato:
    [manual: minsal-ECICEP, p.42]

Donde "minsal-ECICEP" es el id (nombre de carpeta) y p.N es la pagina.

Lista actual:
"""
    for m in sorted(manuales_disponibles):
        prompt += f"- {m}\n"
    prompt += "\n"

    prompt += """# HERRAMIENTAS ADEMAS DE MANUALES

Ademas de los manuales, puedes:

- **Buscar en internet** (`webfetch` / `websearch`): solo fuentes confiables
  (minsal.cl, oms.int, pubmed.ncbi.nlm.nih.gov, scielo.org, etc.).
- **Usar tu conocimiento medico** pre-entrenado para patologias comunes.
- **Cruzar info** entre bloques (ej: si el paciente tiene diagnostico de
  HTA + medicamento Losartan, redactar la evoluci\u00f3n esperada).

# FORMATO DE SALIDA

Devuelve SOLO el contenido enriquecido del bloque "## Nota clinica de Yadira"
(sin el titulo `## `), en markdown con prosa clinica + bullets cuando
corresponda. NO agregues el titulo del bloque. NO incluyas meta-planning
("procedo a redactar...", "voy a consultar..."). NO uses metaforas.

Empieza directamente con el contenido clinico enriquecido (puede incluir
la anamnesis original parafraseada + contexto agregado).
"""
    return prompt


def invocar_llm(prompt: str) -> str:
    """Invoca al LLM via opencode. TODO: zona a corregir (Mortadelo).

    Por ahora, retorna un placeholder claro para que el flujo se pueda
    integrar de extremo a extremo cuando el LLM este cableado.

    Args:
        prompt: prompt completo generado por construir_prompt().

    Returns:
        El contenido que el LLM escribio para el bloque Yadira.

    Raises:
        NotImplementedError: hasta que la zona a corregir implemente el
            cableado con opencode / mortadelo.
    """
    raise NotImplementedError(
        "completar_yadira.invocarprompt(): cableado con LLM es TODO "
        "(zona a corregir). Usar --dry-run para ver el prompt sin invocar."
    )


def insertar_bloque_yadira(nota_md: str, contenido_yadira: str) -> str:
    """Reemplaza la anamnesis cruda en el bloque Nota clinica de Yadira por
    el contenido enriquecido generado por el LLM.

    El bloque conserva su header `## Nota clinica de Yadira`. Si motivo_consulta
    esta como blockquote al inicio, se preserva. La anamnesis cruda original
    se reemplaza por el contenido del LLM (que incluye esa anamnesis
    parafraseada + el enriquecimiento).
    """
    lineas = nota_md.splitlines()
    out: list[str] = []
    en_bloque = False
    bloque_reemplazado = False
    for line in lineas:
        if line.startswith("## Nota clinica de Yadira"):
            en_bloque = True
            out.append(line)
            out.append("")
            # Si la siguiente linea no-vacia es el blockquote de motivo,
            # copiarlo primero (se preserva como dato de Yadira).
            idx = lineas.index(line) + 1
            while idx < len(lineas) and lineas[idx].strip() == "":
                idx += 1
            if idx < len(lineas) and lineas[idx].startswith(">"):
                while idx < len(lineas) and (
                    lineas[idx].startswith(">") or lineas[idx].strip() == ""
                ):
                    out.append(lineas[idx])
                    idx += 1
            # Luego el contenido enriquecido del LLM.
            out.append(contenido_yadira)
            bloque_reemplazado = True
            # Saltamos hasta el siguiente header (ignoramos la anamnesis
            # cruda original).
            while idx < len(lineas) and not lineas[idx].startswith("## "):
                idx += 1
            continue
        if en_bloque and line.startswith("## "):
            en_bloque = False
        if en_bloque:
            continue
        out.append(line)

    if not bloque_reemplazado:
        raise ValueError(
            "No se encontro el bloque '## Nota clinica de Yadira'"
        )
    return "\n".join(out)


def completar_una_nota(
    nota_path: Path,
    output_dir: Path = NOTAS_COMPLETADAS_DIR,
    dry_run: bool = False,
) -> Path | None:
    """Procesa una nota individual.

    Args:
        nota_path: path al .md incompleto en notas_clinicas/.
        output_dir: donde guardar la version completada.
        dry_run: si True, solo muestra el prompt, NO invoca el LLM.

    Returns:
        Path al .md completado, o None si dry_run.
    """
    texto = nota_path.read_text(encoding="utf-8")
    bloques = leer_bloques_nota(texto)

    # Extraer paciente_dict del frontmatter (simple: lineas `paciente: ...` etc.)
    paciente_dict: dict[str, str] = {}
    en_fm = False
    for line in texto.splitlines():
        if line.strip() == "---":
            if not en_fm:
                en_fm = True
                continue
            break
        if en_fm and ":" in line:
            k, _, v = line.partition(":")
            paciente_dict[k.strip()] = v.strip().strip('"')

    # Listar manuales disponibles.
    manuales: list[str] = []
    if MANUALES_DIR.exists():
        manuales = sorted(p.name for p in MANUALES_DIR.iterdir() if p.is_dir())

    prompt = construir_prompt(bloques, manuales, paciente_dict)

    if dry_run:
        print(f"\n=== DRY RUN: {nota_path.name} ===\n")
        print(prompt)
        print(f"\n=== FIN DRY RUN ({nota_path.name}) ===\n")
        return None

    contenido_yadira = invocar_llm(prompt)
    nota_completada = insertar_bloque_yadira(texto, contenido_yadira)

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / nota_path.name
    out_path.write_text(nota_completada, encoding="utf-8")
    logging.info(f"  OK {nota_path.name} -> {out_path.relative_to(ROOT)}")
    return out_path


def main() -> int:
    p = argparse.ArgumentParser(
        description="Completa el bloque 'Nota clinica de Yadira' via LLM."
    )
    p.add_argument(
        "--nota",
        type=Path,
        default=None,
        help="Path a 1 nota especifica. Default: procesa todas en notas_clinicas/.",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=NOTAS_COMPLETADAS_DIR,
        help="Directorio de salida para notas completadas.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Solo mostrar el prompt generado, no invocar LLM.",
    )
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.nota:
        notas = [args.nota]
    else:
        if not NOTAS_DIR.exists():
            logging.warning(f"{NOTAS_DIR} no existe")
            return 1
        notas = sorted(NOTAS_DIR.glob("*.md"))

    if not notas:
        logging.info(f"Ningun .md en {NOTAS_DIR}")
        return 0

    procesadas = 0
    for nota in notas:
        try:
            result = completar_una_nota(
                nota,
                output_dir=args.output_dir,
                dry_run=args.dry_run,
            )
            if result is not None:
                procesadas += 1
        except NotImplementedError as e:
            logging.warning(f"  {nota.name}: {e}")
            continue
        except Exception as e:
            logging.error(f"  {nota.name}: {e}")
            continue

    if args.dry_run:
        logging.info(f"Dry run: {len(notas)} prompts mostrados")
    else:
        logging.info(f"Listo: {procesadas}/{len(notas)} completadas")
    return 0


if __name__ == "__main__":
    sys.exit(main())