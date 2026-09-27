"""Cliente PubMed E-utilities (paso 10, REQ-083).

API gratuita, sin key (limite 3 req/s, suficiente para un boletin).
Flujo: esearch (PMIDs) -> esummary (titulo/journal/fecha)
      -> efetch (abstracts, en lote, un request por tema).
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

def parsear_abstracts(texto: str) -> dict[str, str]:
    """Parsea la salida de efetch rettype=abstract a {pmid: abstract}.

    El texto llega como bloques separados; cada bloque termina con una
    linea 'PMID: <n>'. El pie 'PMCID:' se descarta. Funcion pura (testeable
    sin red).
    """
    import re as _re

    partes = _re.split(r"\n\s*PMID:\s*(\d+)\s*\n?", texto)
    # _re.split con grupo: [bloque0, id1, bloque1, id2, bloque2, ...]
    # El abstract del idN vive en el bloque ANTERIOR a su linea PMID.
    resultado: dict[str, str] = {}
    for i in range(1, len(partes) - 1, 2):
        pmid, bloque = partes[i], partes[i - 1]
        lineas = [
            ln.strip()
            for ln in bloque.splitlines()
            if ln.strip() and not ln.strip().startswith("PMCID:")
        ]
        # Solo bloques con seccion 'Abstract': sin ella, lo que hay es
        # la cita (autores/titulo) y NO debe usarse como abstract.
        if "Abstract" not in lineas:
            continue
        lineas = lineas[lineas.index("Abstract") + 1 :]
        abstract = " ".join(lineas).strip()
        if abstract:
            resultado[pmid] = abstract
    return resultado


def obtener_abstracts(pmids: list[str]) -> dict[str, str]:
    """Trae los abstracts de varios PMIDs en UN request (efetch).

    Papers sin abstract no aparecen en el dict. Errores de red suben
    como PubmedError (el caller decide si es fatal).
    """
    if not pmids:
        return {}
    try:
        resp = requests.get(
            f"{_BASE}/efetch.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(pmids),
                "rettype": "abstract",
                "retmode": "text",
            },
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise PubmedError(f"efetch fallo: {e}") from e
    return parsear_abstracts(resp.text)

