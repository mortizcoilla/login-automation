"""Tests del extractor de temas CIE-10 (paso 10, REQ-083)."""

from __future__ import annotations

from pathlib import Path

from src.estudios.temas import analizar_notas, extraer_de_nota, resumen_markdown

_NOTA = """## Diagnosticos

- CIE 10 [Nueva, Principal, Sospecha]: Clasificación: F41Trastorno de ansiedad

## Estratificacion ECICEP

Diagnosticos cronicos (2):
- Hipertension esencial (primaria)
  CIE-10: I10
  Descripcion: Hipertension esencial (primaria)
- Diabetes mellitus tipo 2
  CIE-10: E11.9

Paciente de 74 años de edad, acude sola.
"""


def test_extrae_atencion_y_cronicos_sin_duplicar() -> None:
    codigos, edad = extraer_de_nota(_NOTA)
    assert "F41" in codigos
    assert "I10" in codigos
    assert "E11.9" in codigos
    assert codigos.count("F41") == 1
    assert edad == 74


def test_nota_sin_cie10_devuelve_vacio() -> None:
    codigos, edad = extraer_de_nota("Nota sin diagnosticos. Paciente de 30 años.")
    assert codigos == []
    assert edad == 30


def test_analizar_notas_agrega_capitulos(tmp_path: Path) -> None:
    (tmp_path / "nota_A.md").write_text(_NOTA, encoding="utf-8")
    (tmp_path / "nota_B.md").write_text(
        "- CIE 10 [Nueva]: Clasificación: F90.0Trastorno\n"
        "Paciente de 9 años de edad.",
        encoding="utf-8",
    )
    r = analizar_notas(tmp_path)
    assert r.notas_leidas == 2
    assert r.capitulos["Salud mental"] == 2
    assert r.capitulos["Circulatorias"] == 1
    assert r.adulto_mayor() == 1
    assert r.con_edad() == 2


def test_markdown_sin_datos_identificables() -> None:
    (tmp_path := Path(__file__).parent / "_tmp_temas").mkdir(exist_ok=True)
    (tmp_path / "nota.md").write_text(_NOTA, encoding="utf-8")
    r = analizar_notas(tmp_path)
    md = resumen_markdown(r)
    assert "Salud mental" in md
    # REQ-044: el resumen agregado nunca incluye el nombre del archivo
    # (que lleva el nombre del paciente)
    assert "nota.md" not in md and "nota_A" not in md
