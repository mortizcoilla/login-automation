"""Tests REQ-083 (fix 27-09): abstracts reales en el boletin.

- parsear_abstracts: bloques alineados con su PMID, cita sin 'Abstract'
  descartada, pie PMCID fuera.
- obtener_abstracts: 1 solo request, respuesta parseada.
- armar_boletin con llm_run falso: el prompt de traduccion recibe el
  ABSTRACT (antes solo llegaba el titulo — bug: Yadira leia solo el
  titulo traducido).
- main sin --salida: escribe en la raiz de OneDrive (default).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.estudios import boletin as bol
from src.estudios.pubmed import Paper, parsear_abstracts

_TEXTO_EFETCH = (
    "1. N Engl J Med. 2026 Jan 5. doi: 1.0.\n\n"
    "Autor A, Autor B.\n\n"
    "Trial of X in primary care.\n\n"
    "Abstract\n"
    "BACKGROUND Patients with X. METHODS Randomized.\n"
    "RESULTS Intervention worked (RR 0.5).\n\n"
    "PMID: 11111111\n\n"
    "2. BMJ. 2026 Feb. doi: 2.0.\n\n"
    "Short report without abstract section.\n\n"
    "PMID: 22222222\n"
    "PMCID: PMC999\n"
)


def test_parsear_abstracts_alinea_bloques_con_pmid() -> None:
    res = parsear_abstracts(_TEXTO_EFETCH)
    assert set(res) == {"11111111"}  # el 22222222 no tiene 'Abstract'
    assert "RR 0.5" in res["11111111"]
    assert "Autor A" not in res["11111111"]  # cita fuera
    assert "PMCID" not in res["11111111"]


def test_obtener_abstracts_un_solo_request() -> None:
    resp = MagicMock()
    resp.text = _TEXTO_EFETCH
    resp.raise_for_status.return_value = None
    with patch("src.estudios.pubmed.requests.get", return_value=resp) as mock_get:
        res = bol.obtener_abstracts(["11111111", "22222222"])
    assert mock_get.call_count == 1  # batch, no 1-request-por-paper
    assert set(res) == {"11111111"}


def _paper(pmid: str = "11111111") -> Paper:
    return Paper(pmid=pmid, titulo="Trial of X", journal="NEJM", fecha="2026", url="u")


def test_traduccion_recibe_el_abstract() -> None:
    prompts: list[str] = []

    def fake_llm(prompt: str):
        prompts.append(prompt)
        return ("resumen en espanol", "flash")

    out = bol._traducir_resumen(fake_llm, _paper(), abstract="RESULTS worked (RR 0.5).")
    assert out == "resumen en espanol"
    assert prompts, "el LLM no fue llamado"
    assert "RESULTS worked (RR 0.5)." in prompts[0]
    assert "Abstract" in prompts[0]


def test_traduccion_sin_abstract_cahe_a_titulo() -> None:
    prompts: list[str] = []

    def fake_llm(prompt: str):
        prompts.append(prompt)
        return ("titulo traducido", "flash")

    out = bol._traducir_resumen(fake_llm, _paper(), abstract="")
    assert out == "titulo traducido"
    assert "Abstract" not in prompts[0]
    assert "Trial of X" in prompts[0]


def test_armar_boletin_pide_abstracts_cuando_hay_llm() -> None:
    resumen = MagicMock()
    resumen.codigos.most_common.return_value = [("F41", 3)]
    resumen.capitulos.most_common.return_value = [("Salud mental", 3)]
    with (
        patch.object(bol, "buscar_papers", return_value=[_paper()]),
        patch.object(bol, "obtener_abstracts", return_value={"11111111": "ABSTRACT X"}) as mock_abs,
        patch.object(
            bol,
            "_traducir_resumen",
            side_effect=lambda llm, p, abstract="": f"R({abstract[:9]})",
        ) as mock_tr,
    ):
        markdown, temas = bol.armar_boletin(resumen, llm_run=lambda p: ("t", "m"))
    mock_abs.assert_called_once()
    # el abstract viaja al traductor (posicional, 3er argumento)
    assert mock_tr.call_args.args[-1] == "ABSTRACT X"
    assert "R(ABSTRACT" in temas[0].resumenes["11111111"]
    assert "revísalo" in markdown.lower() or "revísalo" in markdown


def test_main_sin_salida_guarda_en_onedrive(tmp_path, monkeypatch) -> None:
    resumen = MagicMock()
    resumen.notas_leidas = 2
    resumen.codigos.most_common.return_value = []
    resumen.capitulos.most_common.return_value = []
    onedrive_root = tmp_path / "Login-Automation"
    with (
        patch.object(bol, "analizar_notas", return_value=resumen),
        patch.object(bol, "armar_boletin", return_value=("# Boletin", [])),
        monkeypatch.context() as mp,
    ):
        mp.setattr("src.core.rutas.INFORMES_FICHAS_DIR", onedrive_root)
        rc = bol.main([])
    assert rc == 0
    archivos = list(onedrive_root.glob("boletin_lectura_*.md"))
    assert len(archivos) == 1
    assert archivos[0].read_text(encoding="utf-8") == "# Boletin"
