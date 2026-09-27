"""Oferta semanal de papers para Yadira (REQ-096).

SABADO 09:00 (tarea de Windows) o manual:
    python -m src.estudios.oferta_papers

Hace:
    1. analiza las notas -> capitulo mas atendido (su trabajo real).
    2. busca los 3 papers mas recientes/relevantes de ese tema.
    3. mini-resumen en espanol de cada uno (Gemini, 1-2 frases).
    4. UN mensaje de Rubicita a Yadira con el listado 1/2/3.
    5. guarda la oferta en data/estados/oferta_papers.json para que el
       bot sepa a que paper corresponde su "1", "2" o "3".

Cuando ella responde el numero, src/telegram_bot/handlers/papers.py
descarga y traduce el elegido (src/estudios/papers.py).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import date
from pathlib import Path

from src.core.fechas import fecha_hoy_str
from src.core.rutas import ESTADOS_DIR, NOTAS_DIR
from src.estudios.boletin import _capitulo_de, _query_por_codigo
from src.estudios.gemini_texto import GeminiTextoError, generar_texto
from src.estudios.pubmed import PubmedError, buscar_papers, obtener_abstracts
from src.estudios.temas import ResumenTemas, analizar_notas

logger = logging.getLogger(__name__)

RUTA_OFERTA = ESTADOS_DIR / "oferta_papers.json"
_MAX_TEMAS_A_PROBAR = 3  # si el capitulo top no da papers, prueba el siguiente


def _elegir_papers(resumen: ResumenTemas, max_papers: int = 3):
    """Los papers del capitulo MAS atendido (el mas cercano a su trabajo).

    Devuelve (papers, capitulo, atenciones). Recorre capitulos por
    frecuencia hasta conseguir papers.
    """
    codigos_por_capitulo: dict[str, list[tuple[str, int]]] = {}
    for codigo, n in resumen.codigos.most_common():
        capitulo = _capitulo_de(codigo)
        codigos_por_capitulo.setdefault(capitulo, []).append((codigo, n))

    probados = 0
    for capitulo, atenciones in resumen.capitulos.most_common():
        if probados >= _MAX_TEMAS_A_PROBAR:
            break
        probados += 1
        top_codigo = codigos_por_capitulo.get(capitulo, [("?", 0)])[0][0]
        query = _query_por_codigo(top_codigo)
        try:
            papers = buscar_papers(query, max_papers=max_papers)
        except PubmedError as e:
            logger.warning("[oferta] pubmed fallo para %s: %s", capitulo, e)
            continue
        if papers:
            return papers, capitulo, atenciones
    return [], "", 0


def _mini_resumen(titulo: str, journal: str, fecha: str, abstract: str) -> str:
    """1-2 frases en espanol sobre que estudia el paper (LLM de papers)."""
    datos = f"Titulo: {titulo} | Revista: {journal} ({fecha})"
    if abstract:
        datos += f" | Resumen de la publicacion: {abstract[:900]}"
        tarea = (
            "Resume en espanol, en 1-2 frases (maximo 45 palabras), que "
            "estudia la publicacion y su hallazgo principal."
        )
    else:
        tarea = (
            "No hay resumen disponible: traduce el titulo al espanol y "
            "describe en 1 frase de que parece tratar la publicacion, "
            "senalando que es solo por el titulo."
        )
    prompt = (
        "Tarea de resumen de texto medico. NO falta ningun archivo: todo "
        "el material disponible esta en este mensaje. " + tarea + " "
        "Responde UNICAMENTE las frases, sin recomendaciones. " + datos
    )
    return " ".join(generar_texto(prompt).split())


def armar_mensaje(
    papers_resumenes: list[dict], capitulo: str, atenciones: int
) -> str:
    """El mensaje de Rubicita con el listado numerado."""
    lineas = [
        "Papers de la semana, mama 💜",
        "",
        f"Tema detectado en tus atenciones: {capitulo} "
        f"({atenciones} atenciones). Te elegi los 3 papers mas cercanos:",
        "",
    ]
    for item in papers_resumenes:
        lineas.append(
            f"{item['n']}) {item['titulo']}\n"
            f"    {item['journal']} ({item['fecha']})\n"
            f"    {item['resumen']}\n"
        )
    lineas.append(
        "Responde 1, 2 o 3 y te lo traduzco completo con resumen "
        "estructurado. El documento te lo dejo en OneDrive 💜"
    )
    return "\n".join(lineas)


def guardar_oferta(papers_resumenes: list[dict], capitulo: str) -> Path:
    """Persiste la oferta para que el bot resuelva el 1/2/3."""
    ESTADOS_DIR.mkdir(parents=True, exist_ok=True)
    datos = {
        "fecha": fecha_hoy_str(),
        "capitulo": capitulo,
        "papers": [
            {
                "n": item["n"],
                "pmid": item["paper"].pmid,
                "pmcid": item["paper"].pmcid,
                "titulo": item["paper"].titulo,
                "journal": item["paper"].journal,
                "fecha": item["paper"].fecha,
                "url": item["paper"].url,
                "resumen": item["resumen"],
            }
            for item in papers_resumenes
        ],
    }
    RUTA_OFERTA.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return RUTA_OFERTA


def ofrecer(
    enviar=None,
    notas_dir: Path | None = None,
    resumen_override: ResumenTemas | None = None,
    mini_resumen=None,
) -> tuple[str, Path | None]:
    """Arma la oferta completa y la envia por Telegram.

    Returns:
        (mensaje, ruta_oferta) — ruta None si no hubo papers.
    """
    from dotenv import load_dotenv

    load_dotenv()
    enviar = enviar or _enviar_por_defecto
    mini_resumen = mini_resumen or _mini_resumen

    resumen = resumen_override or analizar_notas(notas_dir or NOTAS_DIR)
    if resumen.notas_leidas == 0:
        logger.warning("[oferta] sin notas; no hay oferta esta semana")
        return "", None

    papers, capitulo, atenciones = _elegir_papers(resumen)
    if not papers:
        logger.warning("[oferta] sin papers esta semana")
        return "", None

    try:
        abstracts = obtener_abstracts([p.pmid for p in papers])
    except PubmedError as e:
        logger.warning("[oferta] efetch fallo (%s); resumenes sin abstract", e)
        abstracts = {}

    items: list[dict] = []
    for i, paper in enumerate(papers, 1):
        try:
            resumen_es = mini_resumen(
                paper.titulo, paper.journal, paper.fecha,
                abstracts.get(paper.pmid, ""),
            )
        except GeminiTextoError as e:
            logger.warning("[oferta] mini-resumen fallo (%s): va el titulo", e)
            resumen_es = ""
        items.append(
            {
                "n": i,
                "paper": paper,
                "titulo": paper.titulo,
                "journal": paper.journal,
                "fecha": paper.fecha,
                "resumen": resumen_es or "(sin resumen esta semana)",
            }
        )

    mensaje = armar_mensaje(items, capitulo, atenciones)
    ruta = guardar_oferta(items, capitulo)
    enviar(mensaje)
    return mensaje, ruta


def _enviar_por_defecto(texto: str) -> None:
    """Usa el sendMessage directo del scheduler (mismo chat de avisos)."""
    from src.scheduler.avisos import enviar as enviar_aviso

    if not enviar_aviso(texto):
        raise RuntimeError("el aviso de Telegram no se envio (ver logs)")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        mensaje, ruta = ofrecer()
    except Exception as e:
        logger.error("[oferta] fallo: %s", e)
        return 1
    if ruta is None:
        print("[oferta] sin oferta esta semana (sin notas o sin papers)")
        return 0
    print(f"[oferta] enviada; oferta guardada en {ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
