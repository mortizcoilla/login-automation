"""Descarga y traduccion de un paper elegido por Yadira (REQ-096).

Flujo (cuando ella responde 1/2/3 al mensaje de la semana):
    1. descargar_texto(): texto completo desde PubMed Central si el
       paper es de acceso libre (pmcid); si no, el abstract extendido.
       Nunca se burlan paywalls: sin pmcid se traduce lo legalmente
       disponible y se le dice cual fue la fuente.
    2. traducir_paper(): Gemini resume/traduce con estructura fija
       (resumen ejecutivo, metodos, resultados, conclusiones,
       limitaciones) SIN recomendaciones clinicas.
    3. guardar_paper(): markdown en OneDrive/Login-Automation/papers/.
"""

from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import requests

from src.core.fechas import fecha_hoy_str
from src.core.rutas import PAPERS_DIR
from src.estudios.gemini_texto import GeminiTextoError, generar_texto
from src.estudios.pubmed import Paper, PubmedError, obtener_abstracts

logger = logging.getLogger(__name__)

_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_TIMEOUT = 60
_MAX_CARACTERES_PMC = 80_000  # cap del texto crudo que va al prompt

FUENTE_PMC = "texto completo (PubMed Central, acceso libre)"
FUENTE_ABSTRACT = "abstract (el paper completo no es de acceso libre)"


class DescargaPaperError(RuntimeError):
    """No se pudo obtener texto del paper."""


@dataclass
class PaperTraducido:
    """Un paper ya procesado, listo para guardar/mostrar."""

    paper: Paper
    fuente: str
    resumen_es: str
    ruta: Path | None = None


def _limpiar_xml_pmc(xml: str) -> str:
    """XML de PMC -> texto plano legible (sin tags, sin entidades)."""
    texto = re.sub(r"<[^>]+>", " ", xml)
    texto = html.unescape(texto)
    return re.sub(r"\s+", " ", texto).strip()


def descargar_texto(paper: Paper, get=requests.get) -> tuple[str, str]:
    """Devuelve (texto, fuente). Completo via PMC si hay pmcid.

    Raises:
        DescargaPaperError: si no queda NADA disponible (ni PMC ni
        abstract).
    """
    if paper.pmcid:
        try:
            resp = get(
                f"{_BASE}/efetch.fcgi",
                params={"db": "pmc", "id": paper.pmcid, "retmode": "xml"},
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            texto = _limpiar_xml_pmc(resp.text)
            if len(texto) > 500:
                return texto[:_MAX_CARACTERES_PMC], FUENTE_PMC
            logger.info("[papers] PMC devolvio poco texto para %s", paper.pmcid)
        except requests.RequestException as e:
            logger.warning("[papers] efetch PMC fallo (%s); caigo a abstract", e)

    try:
        abstracts = obtener_abstracts([paper.pmid])
    except PubmedError as e:
        raise DescargaPaperError(f"no se pudo obtener texto: {e}") from e
    abstract = abstracts.get(paper.pmid, "")
    if not abstract:
        raise DescargaPaperError(
            "el paper no tiene texto disponible (ni PMC ni abstract)"
        )
    return abstract, FUENTE_ABSTRACT


_PROMPT = """Tarea de resumen de texto medico (todo el material esta EN ESTE
mensaje; no falta ningun archivo). Resume en espanol la siguiente
publicacion, con esta estructura OBLIGATORIA en markdown:
OBLIGATORIA en markdown:

## Resumen ejecutivo
(4-6 bullets con lo esencial)

## Que estudiaron y como
## Resultados principales
## Conclusiones de los autores
## Limitaciones

Reglas:
- Solo lo que dice el paper; si un dato no viene, escribe "no informado".
- NUNCA agregues recomendaciones clinicas propias.
- Numeros y medidas exactos (dosis, RR, IC, p) traducidos sin redondear.
- Escribe "Resumen traducido del {fuente}; no es el paper completo."
  al final, entre cursivas, si la fuente no es el texto completo.

Paper: {titulo}
Journal: {journal} ({fecha_paper})

Texto:
{texto}
"""


def traducir_paper(paper: Paper, texto: str, fuente: str) -> str:
    """Resume/traduce via Gemini. Devuelve markdown en espanol."""
    prompt = _PROMPT.format(
        titulo=paper.titulo,
        journal=paper.journal,
        fecha_paper=paper.fecha,
        fuente=fuente,
        texto=texto,
    )
    return generar_texto(prompt)


def guardar_paper(paper: Paper, fuente: str, resumen_es: str) -> Path:
    """Escribe el markdown del paper traducido en OneDrive/papers/."""
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    ruta = PAPERS_DIR / f"paper_{paper.pmid}_{fecha_hoy_str()}.md"
    encabezado = (
        f"# {paper.titulo}\n\n"
        f"*{paper.journal} — {paper.fecha}* · [PubMed]({paper.url})*\n\n"
        f"Fuente traducida: {fuente} · Traduccion: Gemini (Google)\n\n"
        f"---\n\n{resumen_es}\n\n---\n\n"
        "*Resumen automatizado para lectura rapida; revisar con criterio "
        "clinico. No reemplaza el paper original.*\n"
    )
    ruta.write_text(encabezado, encoding="utf-8")
    return ruta


def procesar_eleccion(paper: Paper) -> PaperTraducido:
    """Pipeline completo: descarga -> traduce -> guarda."""
    texto, fuente = descargar_texto(paper)
    resumen = traducir_paper(paper, texto, fuente)
    ruta = guardar_paper(paper, fuente, resumen)
    return PaperTraducido(paper=paper, fuente=fuente, resumen_es=resumen, ruta=ruta)


__all__ = [
    "DescargaPaperError",
    "FUENTE_ABSTRACT",
    "FUENTE_PMC",
    "GeminiTextoError",
    "PaperTraducido",
    "descargar_texto",
    "guardar_paper",
    "procesar_eleccion",
    "traducir_paper",
]
