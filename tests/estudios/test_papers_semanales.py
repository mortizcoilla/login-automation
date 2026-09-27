"""Tests REQ-096: papers semanales (oferta + eleccion por Telegram).

Sin red ni LLM real. Cubren:
- _elegir_papers: capitulo top primero, cae al siguiente si no hay.
- armar_mensaje: listado numerado con titulo/journal/resumen.
- guardar/cargar_oferta: roundtrip JSON; sin archivo -> None.
- paper_de_la_oferta: mapea n -> Paper; opcion inexistente -> None.
- _limpiar_xml_pmc: XML -> texto plano.
- descargar_texto: PMC cuando hay pmcid; abstract como fallback.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from src.estudios import papers as mod_papers
from src.estudios.oferta_papers import (
    _elegir_papers,
    armar_mensaje,
    guardar_oferta,
)
from src.estudios.pubmed import Paper
from src.telegram_bot.handlers import papers as hp


def _paper(n: int = 1, pmcid: str = "PMC123") -> Paper:
    return Paper(
        pmid=f"1000000{n}",
        titulo=f"Trial {n}",
        journal="NEJM",
        fecha="2026",
        url=f"https://pubmed.ncbi.nlm.nih.gov/1000000{n}/",
        pmcid=pmcid,
    )


def _resumen(capitulos: list[tuple[str, int]], codigos: list[tuple[str, int]]):
    r = MagicMock()
    r.capitulos.most_common.return_value = capitulos
    r.codigos.most_common.return_value = codigos
    return r


def test_elegir_papers_prefiere_capitulo_top() -> None:
    resumen = _resumen(
        [("Salud mental", 9), ("Cardiovascular", 4)],
        [("F41", 9), ("I10", 4)],
    )
    seleccion, capitulo, atenciones = _elegir_papers(resumen)
    assert capitulo == "Salud mental" and atenciones == 9
    assert len(seleccion) == 3


def test_elegir_papers_cae_al_siguiente_capitulo() -> None:
    resumen = _resumen(
        [("Salud mental", 9), ("Cardiovascular", 4)],
        [("F41", 9), ("I10", 4)],
    )
    llamadas: list[str] = []

    def fake_buscar(query, max_papers=3, **kw):
        llamadas.append(query)
        if "anxiety" in query:
            return []  # el top no da papers
        return [_paper(1), _paper(2), _paper(3)]

    import src.estudios.oferta_papers as op

    original = op.buscar_papers
    op.buscar_papers = fake_buscar
    try:
        seleccion, capitulo, atenciones = _elegir_papers(resumen)
    finally:
        op.buscar_papers = original
    assert capitulo == "Cardiovascular" and len(llamadas) == 2


def test_armar_mensaje_listado_numerado() -> None:
    items = [
        {
            "n": 1,
            "titulo": "Trial A",
            "journal": "BMJ",
            "fecha": "2026",
            "resumen": "Estudio X funciona.",
        }
    ]
    msg = armar_mensaje(items, "Salud mental", 7)
    assert "1) Trial A" in msg
    assert "BMJ (2026)" in msg
    assert "Responde 1, 2 o 3" in msg


def test_oferta_roundtrip(tmp_path: Path, monkeypatch) -> None:
    import src.estudios.oferta_papers as op

    monkeypatch.setattr(op, "RUTA_OFERTA", tmp_path / "oferta.json")
    monkeypatch.setattr(hp, "_RUTA_OFERTA", tmp_path / "oferta.json")
    items = [
        {
            "n": 2,
            "paper": _paper(2),
            "titulo": "Trial 2",
            "journal": "NEJM",
            "fecha": "2026",
            "resumen": "r",
        }
    ]
    guardar_oferta(items, "Salud mental")
    datos = hp.cargar_oferta()
    assert datos is not None and datos["capitulo"] == "Salud mental"
    paper = hp.paper_de_la_oferta(datos, 2)
    assert paper is not None and paper.pmid == "10000002"
    assert hp.paper_de_la_oferta(datos, 3) is None


def test_cargar_oferta_sin_archivo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(hp, "_RUTA_OFERTA", tmp_path / "no_existe.json")
    assert hp.cargar_oferta() is None


def test_limpiar_xml_pmc() -> None:
    xml = (
        "<article><body><p>Hola &amp; adi&oacute;s</p>"
        "<p>Segundo parrafo</p></body></article>"
    )
    texto = mod_papers._limpiar_xml_pmc(xml)
    assert "Hola & adiós" in texto
    assert "<" not in texto


def test_descargar_texto_usa_pmc_cuando_hay_pmcid() -> None:
    resp = MagicMock()
    resp.text = "<article>" + ("x" * 900) + "</article>"
    resp.raise_for_status.return_value = None
    texto, fuente = mod_papers.descargar_texto(_paper(1), get=lambda *a, **k: resp)
    assert fuente == mod_papers.FUENTE_PMC
    assert len(texto) > 500


def test_descargar_texto_cae_a_abstract_sin_pmcid(monkeypatch) -> None:
    sin_pmc = _paper(1, pmcid="")
    monkeypatch.setattr(
        mod_papers,
        "obtener_abstracts",
        lambda pmids: {sin_pmc.pmid: "ABSTRACT extendido."},
    )
    texto, fuente = mod_papers.descargar_texto(sin_pmc)
    assert fuente == mod_papers.FUENTE_ABSTRACT
    assert texto.startswith("ABSTRACT")
