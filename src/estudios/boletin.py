"""Boletin de lectura para Yadira (paso 10, REQ-083).

Flujo:
  1. analizar_notas() -> temas del periodo (CIE-10, Nivel 1).
  2. Los codigos top se mapean a busquedas PubMed (tabla curada para
     los codigos frecuentes de APS; fallback por capitulo).
  3. Top 3 papers por tema (recencia <= 24 meses, sin filtro de
     idioma — el LLM traduce/resume al espanol, decision usuaria).
  4. Markdown para OneDrive + texto corto para Telegram.

Regla dura: el LLM solo TRADUCE/RESUME abstracts; nunca recomienda
conductas clinicas (los papers hablan por si mismos). Queries con
terminos de tema, JAMAS datos de pacientes (REQ-044).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.estudios.pubmed import Paper, PubmedError, buscar_papers
from src.estudios.temas import ResumenTemas, analizar_notas

logger = logging.getLogger(__name__)

# CIE-10 (prefijos) -> termino de busqueda PubMed. Curado para los
# codigos frecuentes de APS observados en las notas de Yadira.
_QUERIES_POR_CODIGO: list[tuple[str, str]] = [
    ("F41", "anxiety disorders primary care management"),
    ("F90", "ADHD children management"),
    ("F43", "adjustment disorder intervention"),
    ("F32", "depression primary care"),
    ("F33", "depression primary care"),
    ("E78", "dyslipidemia management guideline"),
    ("E11", "type 2 diabetes primary care"),
    ("I10", "hypertension primary care"),
    ("K02", "dental caries children prevention"),
    ("H52", "refractive errors children screening"),
    ("Z71", "health counseling primary care"),
]

# Fallback por capitulo (primera letra del codigo).
_QUERIES_POR_CAPITULO: dict[str, str] = {
    "F": "mental health primary care",
    "E": "endocrine metabolic primary care",
    "I": "cardiovascular primary care",
    "K": "oral health primary care",
    "J": "respiratory primary care",
    "H": "vision hearing primary care",
    "M": "musculoskeletal primary care",
    "N": "genitourinary primary care",
    "Z": "preventive medicine primary care",
}


@dataclass
class TemaBoletin:
    """Un tema del boletin con sus papers."""

    codigo: str
    query: str
    atenciones: int
    papers: list[Paper] = field(default_factory=list)
    resumenes: dict[str, str] = field(default_factory=dict)  # pmid -> español


def _capitulo_de(codigo: str) -> str:
    from src.estudios.temas import CAPITULOS

    return CAPITULOS.get(codigo[0].upper(), f"Otro ({codigo[0]})")


def _query_por_codigo(codigo: str) -> str:
    for prefijo, query in _QUERIES_POR_CODIGO:
        if codigo.startswith(prefijo):
            return query
    return _QUERIES_POR_CAPITULO.get(
        codigo[0].upper(), f"{codigo} primary care"
    )


def _traducir_resumen(llm_run, paper: Paper) -> str:
    """Resume/traduce el paper al espanol (2-3 frases) via el LLM."""
    prompt = (
        "Eres asistente de una medica de familia en APS (Chile). "
        "Traduce al espanol y resume en 2-3 frases claras el siguiente "
        "paper (titulo + datos). NO agregues recomendaciones clinicas, "
        "solo describe que estudia y el hallazgo principal:\n\n"
        f"Titulo: {paper.titulo}\nJournal: {paper.journal} ({paper.fecha})"
    )
    try:
        texto, _modelo = llm_run(prompt)
        return " ".join(texto.split())
    except Exception as e:
        logger.warning("[boletin] traduccion fallo (%s): sin resumen", e)
        return ""


def armar_boletin(
    resumen: ResumenTemas,
    logger: logging.Logger | None = None,
    max_temas: int = 3,
    max_papers: int = 3,
    llm_run=None,
) -> tuple[str, list[TemaBoletin]]:
    """Arma el boletin: temas top -> papers PubMed -> markdown.

    Args:
        resumen: el agregado de analizar_notas().
        llm_run: si se pasa, cada paper se resume/traduce al espanol.
            Si es None, el boletin sale sin resumenes (modo rapido).

    Returns:
        (markdown del boletin, lista de temas con sus papers).
    """
    logger = logger or logging.getLogger(__name__)
    temas: list[TemaBoletin] = []
    # Ranking por CAPITULO (agregado clinico real), no por codigo suelto:
    # el top de codigos puede repartir un mismo tema en varios codigos.
    # Para la query se usa el codigo mas frecuente del capitulo.
    codigos_por_capitulo: dict[str, list[tuple[str, int]]] = {}
    for codigo, n in resumen.codigos.most_common():
        capitulo = _capitulo_de(codigo)
        codigos_por_capitulo.setdefault(capitulo, []).append((codigo, n))
    for capitulo, atenciones in resumen.capitulos.most_common():
        top_codigo = codigos_por_capitulo.get(capitulo, [("?", 0)])[0][0]
        query = _query_por_codigo(top_codigo)
        if any(t.query == query for t in temas):
            continue  # mismo termino: un solo bloque por tema
        try:
            papers = buscar_papers(query, max_papers=max_papers)
        except PubmedError as e:
            logger.warning("[boletin] pubmed fallo para %s: %s", capitulo, e)
            papers = []
        if not papers:
            continue
        tema = TemaBoletin(
            codigo=f"{capitulo} ({top_codigo})",
            query=query,
            atenciones=atenciones,
            papers=papers,
        )
        if llm_run is not None:
            for paper in papers:
                resumen_es = _traducir_resumen(llm_run, paper)
                if resumen_es:
                    tema.resumenes[paper.pmid] = resumen_es
        temas.append(tema)
        if len(temas) >= max_temas:
            break
    return _markdown(temas), temas


def _markdown(temas: list[TemaBoletin]) -> str:
    lineas = ["# Boletín de lectura — sugerencias para la Dra. Yadira", ""]
    if not temas:
        lineas.append("(sin papers disponibles en esta edicion)")
        return "\n".join(lineas) + "\n"
    for tema in temas:
        lineas.append(
            f"## {tema.codigo} — visto {tema.atenciones} vez(es) "
            f"({tema.query})"
        )
        lineas.append("")
        for paper in tema.papers:
            lineas.append(f"### {paper.titulo}")
            lineas.append(f"*{paper.journal} — {paper.fecha}*")
            lineas.append(f"[PubMed]({paper.url})")
            resumen = tema.resumenes.get(paper.pmid)
            if resumen:
                lineas.append("")
                lineas.append(resumen)
            lineas.append("")
    lineas.append(
        "*Material sugerido por Rubicita a partir de los temas de tus "
        "atenciones. Revísalo con criterio clínico: es literatura, no "
        "una recomendación.*"
    )
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="boletin",
        description="Boletin de lectura para Yadira (REQ-083).",
    )
    parser.add_argument("--notas-dir", type=Path, default=None)
    parser.add_argument("--salida", type=Path, default=None)
    parser.add_argument(
        "--traducir",
        action="store_true",
        help="resume/traduce cada paper al espanol con el LLM (mas lento)",
    )
    parser.add_argument("--max-temas", type=int, default=3)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    notas_dir = args.notas_dir
    if notas_dir is None:
        from src.core.rutas import NOTAS_DIR

        notas_dir = NOTAS_DIR

    resumen = analizar_notas(notas_dir)
    if resumen.notas_leidas == 0:
        print(f"[boletin] sin notas en {notas_dir}")
        return 1
    llm: object | None = None
    if args.traducir:
        from src.mortadelo.llm_cli import llm_run

        llm = llm_run
    markdown, temas = armar_boletin(
        resumen, logger=logging.getLogger("boletin"), llm_run=llm
    )
    print(markdown)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(markdown, encoding="utf-8")
        print(f"[boletin] guardado en: {args.salida}")
    print(f"[boletin] {len(temas)} tema(s) incluidos")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
