"""Eleccion de paper semanal: Yadira responde 1, 2 o 3 (REQ-096).

Flujo:
    - Sabado 09:00 un job manda el listado de 3 papers (src.estudios.
      oferta_papers) y guarda la oferta en data/estados/oferta_papers.json.
    - Ella responde "1"/"2"/"3" -> este handler descarga el paper
      (PMC si es libre; si no, abstract), lo traduce/resume con Gemini
      y responde con el resumen. El documento queda en
      OneDrive/Login-Automation/papers/.
    - Si responde "enviar" -> se le manda el .md como documento.

No hay estado en memoria entre reinicios: todo sale del JSON de la
oferta y de la carpeta papers/ (archivos de hoy).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from src.core.fechas import fecha_hoy_str
from src.core.rutas import PAPERS_DIR
from src.estudios.papers import (
    DescargaPaperError,
    PaperTraducido,
    procesar_eleccion,
)
from src.estudios.pubmed import Paper

logger = logging.getLogger(__name__)

_RUTA_OFERTA = None  # se resuelve lazy (import de rutas al primer uso)


def _ruta_oferta() -> Path:
    global _RUTA_OFERTA
    if _RUTA_OFERTA is None:
        from src.core.rutas import ESTADOS_DIR

        _RUTA_OFERTA = ESTADOS_DIR / "oferta_papers.json"
    return _RUTA_OFERTA


def cargar_oferta() -> dict | None:
    """La oferta vigente (la ultima guardada), o None si no hay."""
    try:
        datos = json.loads(_ruta_oferta().read_text(encoding="utf-8"))
        return datos if datos.get("papers") else None
    except (OSError, ValueError):
        return None


def paper_de_la_oferta(datos: dict, eleccion: int) -> Paper | None:
    for item in datos.get("papers", []):
        if item.get("n") == eleccion:
            return Paper(
                pmid=item["pmid"],
                titulo=item.get("titulo", ""),
                journal=item.get("journal", ""),
                fecha=item.get("fecha", ""),
                url=item.get("url", ""),
                pmcid=item.get("pmcid", ""),
            )
    return None


def _ultimo_paper_de_hoy() -> Path | None:
    """El paper traducido mas reciente de HOY (para 'enviar')."""
    if not PAPERS_DIR.exists():
        return None
    de_hoy = [
        p
        for p in PAPERS_DIR.glob(f"paper_*_{fecha_hoy_str()}.md")
    ]
    return max(de_hoy, key=lambda p: p.stat().st_mtime) if de_hoy else None


async def cmd_elegir_paper(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Yadira respondio 1/2/3 tras el listado semanal."""
    message = update.effective_message
    if message is None or not (message.text or "").strip():
        return
    eleccion = int(message.text.strip()[0])
    datos = cargar_oferta()
    if datos is None:
        await message.reply_text(
            "No tengo papers ofrecidos esta semana, mama. "
            "El sabado te llegan 3 nuevos."
        )
        return
    paper = paper_de_la_oferta(datos, eleccion)
    if paper is None:
        await message.reply_text(
            f"Esa opcion ({eleccion}) no esta en la lista de esta semana. "
            f"Responde 1, 2 o 3."
        )
        return

    # Una traduccion a la vez (pueden tardar minutos con papers largos).
    if context.application.bot_data.get("paper_en_curso"):
        await message.reply_text(
            "Ya estoy traduciendo un paper, dame un minutito mas 💜"
        )
        return
    context.application.bot_data["paper_en_curso"] = True

    await message.reply_text(
        f"Descargando y traduciendo el paper {eleccion} "
        f"(puede tardar un par de minutos)..."
    )
    try:
        resultado: PaperTraducido = await asyncio.to_thread(
            procesar_eleccion, paper
        )
    except (DescargaPaperError, Exception) as exc:  # noqa: BLE001
        logger.exception("[papers] fallo procesar la eleccion")
        await message.reply_text(
            f"No pude traducir ese paper: {exc}. "
            f"Intentalo con otra opcion o escribenos."
        )
        return
    finally:
        context.application.bot_data["paper_en_curso"] = False

    fuente_nota = (
        ""
        if "texto completo" in resultado.fuente
        else (
            "\n\nOjo: este paper no es de acceso libre, traduje el "
            "abstract (lo disponible legalmente)."
        )
    )
    # Telegram: max ~4096 chars por mensaje; el resumen completo vive
    # en el archivo — aca van los primeros ~3000.
    cuerpo = resultado.resumen_es[:3000]
    if len(resultado.resumen_es) > 3000:
        cuerpo += "\n\n(...resumen cortado; el completo esta en el archivo)"
    await message.reply_text(
        f"Listo 💜 Traduje el paper {eleccion}.\n\n{cuerpo}{fuente_nota}\n\n"
        f"Archivo: {resultado.ruta.name} (en OneDrive/papers/).\n"
        f"Responde ENVIAR si quieres el documento aca.",
    )
    context.application.bot_data["ultimo_paper"] = str(resultado.ruta)


async def cmd_enviar_paper(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """'enviar' -> manda el .md del ultimo paper como documento."""
    message = update.effective_message
    if message is None:
        return
    ruta_str = context.application.bot_data.get("ultimo_paper")
    ruta = Path(ruta_str) if ruta_str else None
    if ruta is None or not ruta.exists():
        ruta = _ultimo_paper_de_hoy()
    if ruta is None:
        await message.reply_text(
            "No tengo un paper traducido de hoy para enviarte. "
            "Responde 1, 2 o 3 al listado de la semana primero."
        )
        return
    try:
        await message.reply_document(
            document=ruta.open("rb"),
            filename=ruta.name,
            caption=f"Paper traducido: {ruta.name}",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception:
        logger.exception("[papers] fallo enviar el documento")
        await message.reply_text(
            f"No pude adjuntar el archivo, pero esta en OneDrive/papers/"
            f"con el nombre {ruta.name}."
        )
