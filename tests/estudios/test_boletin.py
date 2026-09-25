"""Tests del boletin de lectura (paso 10, REQ-083). Sin red ni LLM real."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.estudios import boletin as boletin_mod
from src.estudios.boletin import armar_boletin
from src.estudios.pubmed import Paper
from src.estudios.temas import analizar_notas

_NOTA = """## Diagnosticos

- CIE 10 [Nueva, Principal]: Clasificación: F41Trastorno de ansiedad

Paciente de 30 años de edad.
"""


@pytest.fixture()
def resumen(tmp_path: Path):
    (tmp_path / "nota.md").write_text(_NOTA, encoding="utf-8")
    return analizar_notas(tmp_path)


def _mock_pubmed(monkeypatch: pytest.MonkeyPatch, papers: list[Paper]) -> list[str]:
    llamadas: list[str] = []

    def _fake(termino: str, max_papers: int = 3, reldate_meses: int = 24):
        llamadas.append(termino)
        return papers

    monkeypatch.setattr(boletin_mod, "buscar_papers", _fake)
    return llamadas


def _paper(pmid: str = "123") -> Paper:
    return Paper(
        pmid=pmid,
        titulo="Anxiety management in primary care: a review",
        journal="Fam Pract",
        fecha="2026 Jan",
        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    )


def test_boletin_sin_llm_tiene_titulo_y_link(resumen: object) -> None:
    md, temas = armar_boletin(resumen)  # type: ignore[arg-type]
    assert temas, "el tema top (salud mental) debe estar"
    assert "## " in md
    assert "https://pubmed.ncbi.nlm.nih.gov/" in md
    assert "no una recomendación" in md  # disclaimer obligatorio


def test_boletin_con_llm_traduce(resumen: object, monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_pubmed(monkeypatch, [_paper()])
    llamadas_llm: list[str] = []

    def _llm(prompt: str):
        llamadas_llm.append(prompt)
        return "Resumen en español.", "modelo-falso"

    md, temas = armar_boletin(resumen, llm_run=_llm)  # type: ignore[arg-type]
    assert temas[0].resumenes.get("123") == "Resumen en español."
    assert "Resumen en español." in md
    assert llamadas_llm and "Traduce al espanol" in llamadas_llm[0]


def test_queries_curadas_para_codigos_aps() -> None:
    assert boletin_mod._query_por_codigo("F41.1").startswith("anxiety")
    assert boletin_mod._query_por_codigo("F90.0").startswith("ADHD")
    assert boletin_mod._query_por_codigo("E11.9").startswith("type 2 diabetes")
    # fallback por capitulo para codigos no curados
    assert boletin_mod._query_por_codigo("M75.1") == "musculoskeletal primary care"
