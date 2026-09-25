"""Cliente PubMed E-utilities (paso 10, REQ-083).

API gratuita, sin key (limite 3 req/s, suficiente para un boletin).
Flujo: esearch (PMIDs) -> esummary (titulo/journal/fecha).
Sin filtro de idioma: el mejor material se traduce al espanol con el
LLM (decision de la usuaria 25-09-2026).
"""

from __future__ import annotations

from dataclasses import dataclass

import requests

_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_TIMEOUT = 30


class PubmedError(RuntimeError):
    """Error consultando la API de PubMed."""


@dataclass
class Paper:
    """Un paper de PubMed con su link."""

    pmid: str
    titulo: str
    journal: str
    fecha: str
    url: str


def buscar_papers(termino: str, max_papers: int = 3, reldate_meses: int = 24) -> list[Paper]:
    """Busca papers recientes (default: ultimos 24 meses) por termino.

    Returns:
        Hasta `max_papers` papers ordenados por relevancia de PubMed.
    """
    term = f"{termino} AND Humans"
    try:
        resp = requests.get(
            f"{_BASE}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": term,
                "retmax": str(max_papers),
                "sort": "relevance",
                "datetype": "pdat",
                "reldate": str(reldate_meses * 30),
                "retmode": "json",
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        ids = resp.json()["esearchresult"]["idlist"]
    except requests.RequestException as e:
        raise PubmedError(f"esearch fallo: {e}") from e
    except (KeyError, ValueError) as e:
        raise PubmedError(f"respuesta esearch malformada: {e}") from e
    if not ids:
        return []

    try:
        resp = requests.get(
            f"{_BASE}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        docs = resp.json()["result"]
    except requests.RequestException as e:
        raise PubmedError(f"esummary fallo: {e}") from e
    except (KeyError, ValueError) as e:
        raise PubmedError(f"respuesta esummary malformada: {e}") from e

    papers: list[Paper] = []
    for pmid in ids:
        doc = docs.get(pmid)
        if not doc:
            continue
        papers.append(
            Paper(
                pmid=pmid,
                titulo=str(doc.get("title", "")).strip(),
                journal=str(doc.get("source", "")).strip(),
                fecha=str(doc.get("pubdate", "")).strip(),
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            )
        )
    return papers
